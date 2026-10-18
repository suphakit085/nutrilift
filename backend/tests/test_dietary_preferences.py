"""Granular allergy combinations and explicit persistence through the actual API."""

import json
from copy import deepcopy

import pytest
from sqlalchemy.orm import Session

from app.api import chat as chat_api
from app.services import chat
from app.services.dietary_preferences import CLARIFY_TOOL, DIETARY_VALUES, SETTING_TOOL
from app.services.meal_plan import _RESTRICTION_RULES, MealPlanError, excluded_by, plan_day_menu
from app.services.menu_context import conversation_profile, conversation_restrictions
from tests.test_account_lifecycle import account_app as account_app
from tests.test_account_lifecycle import signup
from tests.test_verified_menu_routing import adult, no_model, run
from tests.test_verified_menu_routing import foods as foods

PROFILE = {
    "sex": "male",
    "birth_year": 2000,
    "birth_month": 1,
    "height_cm": 175,
    "weight_kg": 70,
    "body_fat_pct": None,
    "activity_level": "moderate",
    "training_days": 3,
    "goal": "maintain",
    "restrictions": ["วีแกน", "แพ้ถั่ว"],
}


def setting(values, saved=None, role="user"):
    return {
        "role": role,
        "content": "ยืนยันข้อจำกัด",
        "tool_calls": [
            {
                "name": SETTING_TOOL,
                "status": "success",
                "arguments": {
                    "version": 1,
                    "scope": "conversation",
                    "restrictions": values,
                    "saved_restrictions": list(saved) if saved is not None else ["วีแกน", "แพ้ถั่ว"],
                },
            }
        ],
    }


@pytest.mark.parametrize("restriction", ["แพ้เห็ด", "ข้อจำกัดที่ยังไม่รองรับ: เห็ด", "ไม่กินข้าวสาลี"])
def test_unknown_saved_restrictions_never_silently_allow_a_menu(restriction):
    result = chat._run_menu_tool(None, adult(restrictions=[restriction]), {"meal_count": 3})
    assert result["error"] == "unsupported_menu_constraint"
    assert "meals" not in result


def test_versioned_profile_write_and_catalog_require_verified_owner(account_app):
    state = account_app
    headers = signup(state)
    catalog = state.client.get("/dietary-options", headers=headers)
    assert catalog.status_code == 200
    assert catalog.json()["version"] == 1
    assert {o["value"] for g in catalog.json()["groups"] for o in g["options"]} == DIETARY_VALUES
    assert state.client.get("/dietary-options").status_code == 401
    value = {**PROFILE, "restrictions": ["วีแกน", "แพ้ถั่วลิสง"]}
    assert state.client.put("/profile/settings", headers=headers, json=value).status_code == 200
    assert (
        state.client.get("/profile", headers=headers).json()["restrictions"]
        == value["restrictions"]
    )


def test_catalog_only_offers_supported_filters():
    assert set(_RESTRICTION_RULES) >= DIETARY_VALUES


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ผมแพ้ถั่วลิสง", "แพ้ถั่วลิสง"),
        ("ฉันแพ้ถั่วเปลือกแข็ง", "แพ้ถั่วเปลือกแข็ง"),
        ("แพ้ถั่วเหลือง", "แพ้ถั่วเหลือง"),
        ("ฉันแพ้งา", "แพ้งา"),
        ("allergic to peanuts", "แพ้ถั่วลิสง"),
        ("allergic to tree nuts", "แพ้ถั่วเปลือกแข็ง"),
        ("แพ้อัลมอนด์", "แพ้ถั่วเปลือกแข็ง"),
        ("แพ้ถั่ว", "แพ้ถั่ว"),
    ],
)
def test_chat_distinguishes_specific_allergy_from_broad_nuts(text, expected):
    profile = adult()
    before = deepcopy(profile)
    effective, _ = conversation_profile(profile, [], text)
    assert effective.restrictions == [expected]
    assert profile == before


@pytest.mark.parametrize(
    "restrictions",
    [
        ["วีแกน", "แพ้ถั่วลิสง"],
        ["วีแกน", "แพ้ถั่วเปลือกแข็ง"],
        ["วีแกน", "แพ้งา"],
        ["วีแกน", "แพ้ถั่วลิสง", "แพ้ถั่วเปลือกแข็ง"],
    ],
)
@pytest.mark.parametrize("count", [3, 4, 6])
def test_actual_food_combinations_use_only_allowed_items(foods, restrictions, count):
    plan = plan_day_menu(
        foods,
        {"kcal": 2000, "protein_g": 104, "carb_g": 279, "fat_g": 52},
        restrictions,
        meal_count=count,
        allow_extra_meals=False,
    )
    by_name = {f["name_th"]: f for f in foods}
    assert plan["meals"]
    assert all(
        excluded_by(by_name[item["name_th"]], restrictions) is None
        for meal in plan["meals"]
        for item in meal["items"]
    )


def test_specific_filters_do_not_blanket_ban_soy_or_change_legacy(foods):
    tofu = next(f for f in foods if f["name_th"] == "เต้าหู้ขาวแข็ง")
    for restriction in ["แพ้ถั่วลิสง", "แพ้ถั่วเปลือกแข็ง", "แพ้งา"]:
        assert excluded_by(tofu, [restriction]) is None
    assert excluded_by(tofu, ["แพ้ถั่ว"]) == "แพ้ถั่ว"
    assert excluded_by(tofu, ["แพ้ถั่วเหลือง"]) == "แพ้ถั่วเหลือง"
    with pytest.raises(MealPlanError):
        plan_day_menu(
            foods,
            {"kcal": 2000, "protein_g": 104, "carb_g": 279, "fat_g": 52},
            ["วีแกน", "แพ้ถั่วเหลือง"],
            meal_count=3,
        )


@pytest.mark.parametrize(
    "profile,message",
    [
        (adult(restrictions=["วีแกน", "แพ้ถั่ว"]), "ช่วยจัดเมนูทั้งหมด 3 มื้อให้ตรงกับเป้าหมายของผม"),
        (adult(), "ผมกินวีแกนและแพ้ถั่ว ช่วยจัดอาหารให้หน่อย"),
        (None, "ผมแพ้ถั่ว"),
    ],
)
def test_ambiguous_allergy_asks_before_model_or_planner(monkeypatch, foods, profile, message):
    no_model(monkeypatch, foods)
    before = deepcopy(profile)
    events = run(message, profile)
    assert sum(event["type"] == "sources" for event in events) == 1
    done = events[-1]
    assert done["model"] == "rule:dietary_clarification"
    assert done["tool_calls"] == [{"name": CLARIFY_TOOL, "status": "confirmation_required"}]
    assert "ถั่วลิสง" in done["text"] and "เฉพาะห้องนี้" in done["text"]
    assert "โปรไฟล์" in done["text"] and "| มื้อ" not in done["text"]
    assert profile == before


def test_confirmed_choice_replaces_ambiguous_nuts_but_retains_other_allergies():
    profile = adult(restrictions=["วีแกน", "แพ้ถั่ว", "แพ้นมวัว"])
    history = [
        {"role": "user", "content": "ผมแพ้ถั่วและแพ้นมวัว"},
        setting(["วีแกน", "แพ้ถั่วลิสง", "แพ้นมวัว"], profile.restrictions),
    ]
    effective, _ = conversation_profile(profile, history, "ขอเมนู 3 มื้อ")
    assert effective.restrictions == ["วีแกน", "แพ้ถั่วลิสง", "แพ้นมวัว"]
    assert "แพ้ถั่ว" in profile.restrictions
    # A later saved allergy must survive this room's older choice.
    profile.restrictions.append("แพ้งา")
    assert "แพ้งา" in conversation_restrictions(profile, history)
    effective, _ = conversation_profile(profile, history, "ผมแพ้เห็ดด้วย")
    assert any(r.startswith("ข้อจำกัดที่ยังไม่รองรับ:") for r in effective.restrictions)


def test_assistant_cannot_clear_user_allergies_and_no_profile_can_hold_room_settings():
    profile = adult(restrictions=["แพ้ถั่ว"])
    assert conversation_restrictions(profile, [setting([], role="assistant")]) == ["แพ้ถั่ว"]
    assert conversation_restrictions(None, [setting(["วีแกน"], [])]) == ["วีแกน"]


def room(state, headers):
    response = state.client.post("/conversations", headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def context(state, headers, identifier):
    response = state.client.get(f"/conversations/{identifier}/dietary-preferences", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def save(state, headers, identifier, values, scope="conversation", version=None, confirm=True):
    before = context(state, headers, identifier)
    return state.client.put(
        f"/conversations/{identifier}/dietary-preferences",
        headers=headers,
        json={
            "restrictions": values,
            "scope": scope,
            "context_version": version or before["context_version"],
            "confirm_allergy_changes": confirm,
        },
    )


def setup(state, with_profile=True):
    headers = signup(state)
    if with_profile:
        assert state.client.put("/profile", headers=headers, json=PROFILE).status_code == 200
    return headers, room(state, headers)


def test_room_only_survives_reload_and_drives_real_menu_without_profile_write(
    account_app, monkeypatch, foods
):
    state = account_app
    headers, identifier = setup(state)
    before_profile = state.client.get("/profile", headers=headers).json()
    before_history = state.client.get("/profile/history", headers=headers).json()
    values = ["วีแกน", "แพ้ถั่วลิสง"]
    assert save(state, headers, identifier, values, confirm=False).status_code == 422
    response = save(state, headers, identifier, values)
    assert response.status_code == 200, response.text
    assert response.json()["profile_saved"] is False
    assert context(state, headers, identifier)["restrictions"] == values
    assert state.client.get("/profile", headers=headers).json() == before_profile
    assert state.client.get("/profile/history", headers=headers).json() == before_history
    assert context(state, headers, room(state, headers))["restrictions"] == PROFILE["restrictions"]
    no_model(monkeypatch, foods)
    monkeypatch.setattr(chat_api, "SessionLocal", lambda: Session(state.engine))
    response = state.client.post(
        f"/conversations/{identifier}/chat",
        headers=headers,
        json={"message": "ช่วยจัดเมนู 3 มื้อตามเป้าหมาย"},
    )
    assert response.status_code == 200
    done_block = next(
        b for b in response.text.replace("\r\n", "\n").split("\n\n") if "event: done" in b
    )
    done = json.loads(
        next(line[6:] for line in done_block.splitlines() if line.startswith("data: "))
    )
    assert done["model"] == "rule:verified_menu"
    assert done["tool_calls"][0]["status"] in {"success", "partial"}
    assert "ถั่วลิสง," not in done["text"]
    assert state.client.get("/profile", headers=headers).json() == before_profile


def test_save_profile_is_explicit_records_revision_and_applies_to_new_rooms(account_app):
    state = account_app
    headers, identifier = setup(state)
    original = state.client.get("/profile", headers=headers).json()
    revisions = state.client.get("/profile/history", headers=headers).json()
    values = ["วีแกน", "แพ้ถั่วเปลือกแข็ง"]
    response = save(state, headers, identifier, values, scope="profile")
    assert response.status_code == 200, response.text
    assert response.json()["profile_saved"] is True
    after = state.client.get("/profile", headers=headers).json()
    assert after["restrictions"] == values
    assert {k: v for k, v in after.items() if k not in {"restrictions", "updated_at"}} == {
        k: v for k, v in original.items() if k not in {"restrictions", "updated_at"}
    }
    after_revisions = state.client.get("/profile/history", headers=headers).json()
    assert len(after_revisions) == len(revisions) + 1
    assert after_revisions[0]["profile"]["restrictions"] == values
    assert context(state, headers, room(state, headers))["restrictions"] == values


def test_stale_confirmation_cannot_overwrite_new_profile_allergy(account_app):
    state = account_app
    headers, identifier = setup(state)
    old = context(state, headers, identifier)
    assert (
        state.client.put(
            "/profile",
            headers=headers,
            json={**PROFILE, "restrictions": [*PROFILE["restrictions"], "แพ้งา"]},
        ).status_code
        == 200
    )
    assert (
        save(
            state, headers, identifier, ["วีแกน", "แพ้ถั่วลิสง"], version=old["context_version"]
        ).status_code
        == 409
    )
    assert context(state, headers, identifier)["restrictions"] == [*PROFILE["restrictions"], "แพ้งา"]


def test_new_saved_allergy_survives_older_room_override(account_app):
    state = account_app
    headers, identifier = setup(state)
    assert save(state, headers, identifier, ["วีแกน", "แพ้ถั่วลิสง"]).status_code == 200
    assert (
        state.client.put(
            "/profile",
            headers=headers,
            json={**PROFILE, "restrictions": [*PROFILE["restrictions"], "แพ้นมวัว"]},
        ).status_code
        == 200
    )
    assert context(state, headers, identifier)["restrictions"] == ["วีแกน", "แพ้ถั่วลิสง", "แพ้นมวัว"]


def test_missing_profile_ownership_and_bad_input_never_write_profile(account_app):
    state = account_app
    headers, identifier = setup(state, with_profile=False)
    assert save(state, headers, identifier, ["วีแกน"], scope="profile").status_code == 409
    assert save(state, headers, identifier, ["วีแกน"]).status_code == 200
    assert state.client.get("/profile", headers=headers).status_code == 404
    other = signup(state, email="other@example.com")
    assert (
        state.client.get(
            f"/conversations/{identifier}/dietary-preferences", headers=other
        ).status_code
        == 404
    )
    assert save(state, headers, identifier, ["bad\nvalue"]).status_code == 422
    assert state.client.get(f"/conversations/{identifier}/dietary-preferences").status_code == 401
