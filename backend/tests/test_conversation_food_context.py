from dataclasses import replace

import pytest

from app.services import chat
from app.services.macro_math import explicit_macro_energy_reply
from app.services.meal_plan import excluded_by
from app.services.menu_context import conversation_profile
from app.services.nutrition import ProfileInput, calc_nutrition_targets


def adult():
    return ProfileInput(
        sex="male",
        birth_year=1996,
        birth_month=1,
        height_cm=175,
        weight_kg=70,
        activity_level="moderate",
        goal="cut",
    )


@pytest.mark.parametrize(
    "message",
    [
        "ไม่กินไก่และไม่กินไข่ ช่วยจัดใหม่",
        "ขอเมนูไม่มีไก่ไม่มีไข่",
        "avoid chicken and no eggs",
    ],
)
def test_explicit_exclusions_reach_the_planner(message):
    p, note = conversation_profile(adult(), [], message)
    assert {"ไม่กินไก่", "ไม่กินไข่"} <= set(p.restrictions)
    assert excluded_by({"name_th": "สะโพกไก่ไม่มีหนัง, อบ"}, p.restrictions)
    assert excluded_by({"name_th": "ไข่ดาว", "category": "ไข่"}, p.restrictions)
    assert note and "ไม่ได้เปลี่ยนโปรไฟล์" in note


def test_soy_disclosure_persists_across_long_room_but_not_new_room():
    saved = replace(adult(), restrictions=["วีแกน", "แพ้นมวัว"])
    history = [{"role": "user", "content": "ฉันแพ้ถั่วเหลืองด้วย"}]
    history.extend({"role": "user", "content": "คำถามอื่น"} for _ in range(50))
    p, _ = conversation_profile(saved, history, "จัดเมนูอีกแบบ")
    for name in ("เต้าหู้ขาวแข็ง", "เทมเป้สุก", "ผงโปรตีนถั่วเหลืองไอโซเลท", "โปรตีนเกษตร"):
        assert excluded_by({"name_th": name}, p.restrictions)
    fresh, _ = conversation_profile(saved, [], "จัดเมนูอีกแบบ")
    assert fresh == saved and saved.restrictions == ["วีแกน", "แพ้นมวัว"]


def test_do_not_treat_assistant_guess_or_negated_allergy_as_disclosure():
    p, _ = conversation_profile(
        adult(), [{"role": "assistant", "content": "คุณแพ้ถั่วเหลือง"}], "ผมไม่แพ้นมวัว และไม่ได้แพ้ถั่ว"
    )
    assert p.restrictions == []


def test_unknown_constraint_stops_planning_before_reading_foods():
    p, _ = conversation_profile(adult(), [], "แพ้ผลไม้ทุกชนิด ช่วยจัดเมนู")
    result = chat._run_menu_tool(None, p, {})
    assert result["error"] == "unsupported_menu_constraint"


def test_hypothetical_goal_and_followup_use_matching_target_without_saving():
    saved = replace(adult(), goal="bulk")
    history = [{"role": "user", "content": "สมมติเปลี่ยนจากเพิ่มกล้ามเป็นรักษาน้ำหนัก ยังไม่แก้โปรไฟล์"}]
    p, _ = conversation_profile(saved, history, "ขอเมนูสำหรับเป้ารักษาน้ำหนัก ไม่ใช่เป้าเพิ่มกล้ามเดิม")
    assert p.goal == "maintain"
    result = calc_nutrition_targets(p)
    assert result["energy_target_kcal"] == result["tdee_kcal"]
    assert saved.goal == "bulk"


def test_prior_explicit_food_name_unlocks_followup_but_not_model_suggestion(monkeypatch):
    monkeypatch.setattr(
        chat, "lookup_food", lambda *_: {"found": True, "results": [{"name_th": "ข้าวสวย"}]}
    )
    common = {
        "user_message": "แล้วข้าวเดิม 2.5 กรัมล่ะ",
        "pending_confirmations": [],
        "partial_candidates_this_turn": [],
    }
    assert chat._run_food_lookup(None, "ข้าวสวย", earlier_user_messages=["ข้าวสวยครึ่งหน่วย"], **common)[
        "found"
    ]
    assert not chat._run_food_lookup(None, "ข้าวสวย", earlier_user_messages=["ข้าวอะไรดี"], **common)[
        "found"
    ]
    common["pending_confirmations"] = ["ข้าวสวย"]
    assert not chat._run_food_lookup(None, "ข้าวสวย", earlier_user_messages=["ข้าวสวย"], **common)[
        "found"
    ]


def test_explicit_macro_percentages_share_one_denominator():
    reply = explicit_macro_energy_reply("คำนวณสัดส่วนแคลอรี่ โปรตีน 140 กรัม คาร์บ 245 กรัม ไขมัน 63 กรัม")
    for value in ("560", "980", "567", "2107", "26.6%", "46.5%", "26.9%"):
        assert value in reply
    assert "$" not in reply
    assert explicit_macro_energy_reply("โปรตีนเท่าไร") is None


def test_zero_macro_percentages_do_not_divide_by_zero():
    assert "0 kcal" in explicit_macro_energy_reply("แคล โปรตีน 0 กรัม คาร์บ 0 กรัม ไขมัน 0 กรัม")


def test_food_names_do_not_become_fake_citation_markers():
    assert chat.clean_answer("เต้าหู้ 126 kcal [เต้าหู้ขาวแข็ง] [S1, S2]") == "เต้าหู้ 126 kcal  [S1, S2]"
    assert chat.clean_answer("[ข้อมูลอาหาร](https://example.com)") == "[ข้อมูลอาหาร](https://example.com)"


@pytest.mark.parametrize("message", [
    "อยากเพิ่มกล้าม ช่วยจัดเมนู 3 มื้อจากโปรไฟล์ ไม่เอาอาหารเสริม",
    "ไม่ต้องการอาหารเสริม", "ไม่ใช้อาหารเสริม", "งดผลิตภัณฑ์เสริมอาหาร",
    "ไม่กินโปรตีนผง", "ไม่เอาเวย์", "no supplements", "without protein powder",
])
def test_supplement_preference_reaches_food_filter_and_persists(message):
    saved = adult()
    first, _ = conversation_profile(saved, [], message)
    followup, _ = conversation_profile(saved, [{"role": "user", "content": message}],
        "งั้นใช้แต่อาหารปกติก็ได้ ช่วยจัดเมนู 3 มื้อที่กินได้จริง")
    for profile in (first, followup):
        assert profile.restrictions == ["ไม่ใช้อาหารเสริม"]
        for row in (
            {"name_th": "เวย์โปรตีน (ผงชงดื่ม)"},
            {"name_th": "ผงโปรตีนถั่วเหลืองไอโซเลท (ทั่วไป)"},
            {"name_en": "Soy protein isolate"},
            {"name_th": "ผลิตภัณฑ์ชงดื่ม", "category": "อาหารเสริม"},
        ):
            assert excluded_by(row, profile.restrictions)
        for name in ("นมผง", "นมวัว", "ไข่ไก่ต้ม", "เต้าหู้ขาวแข็ง", "ถั่วลิสง"):
            assert not excluded_by({"name_th": name}, profile.restrictions)
    assert saved.restrictions == []


def test_supplement_preference_preserves_allergies_and_extra_meal_permission():
    from app.services.menu_context import menu_planning_options

    history = [{"role": "user", "content": "แพ้ถั่วเหลืองและนมวัว"}]
    message = "ไม่เอาอาหารเสริม แต่เพิ่มมื้อเสริมได้ตามเหมาะสม"
    profile, _ = conversation_profile(adult(), history, message)
    assert set(profile.restrictions) == {"แพ้ถั่วเหลือง", "แพ้นมวัว", "ไม่ใช้อาหารเสริม"}
    assert menu_planning_options(history, message)["allow_extra_meals"]
    assert excluded_by({"name_th": "เต้าหู้ขาวแข็ง"}, profile.restrictions)
    assert excluded_by({"name_th": "นมวัว"}, profile.restrictions)


@pytest.mark.parametrize("message", ["แพ้อาหารเสริม", "allergic to supplements"])
def test_vague_supplement_allergy_requires_clarification_even_after_normal_food_followup(message):
    p, _ = conversation_profile(adult(), [{"role": "user", "content": message}],
        "ใช้อาหารปกติ ไม่เอาอาหารเสริม")
    assert chat._run_menu_tool(None, p, {})["error"] == "unsupported_menu_constraint"


def test_assistant_supplement_preference_does_not_override_user():
    profile, _ = conversation_profile(adult(), [
        {"role": "assistant", "content": "ไม่เอาอาหารเสริม"}], "จัดเมนู")
    assert profile.restrictions == []


def test_unrelated_no_use_instruction_is_not_a_food_restriction():
    profile, _ = conversation_profile(adult(), [],
        "ช่วยจัดเมนู ไม่ต้องคำนวณใหม่ ไม่ใช้ตัวเลขสมมติ")
    assert profile.restrictions == []


def test_supplement_preference_does_not_leak_to_new_room_and_can_be_reset():
    saved = adult()
    history = [{"role": "user", "content": "ไม่เอาอาหารเสริม"}]
    reset, _ = conversation_profile(saved, history, "กลับไปใช้โปรไฟล์ที่บันทึกล่าสุด")
    fresh, _ = conversation_profile(saved, [], "จัดเมนู")
    assert reset.restrictions == fresh.restrictions == []


@pytest.mark.parametrize("count", [3, 4, 6])
def test_actual_menu_tool_plans_without_supplements(monkeypatch, count):
    import csv

    from app.services.meal_plan import validate_day_plan
    from tests.test_meal_plan import FOODS_CSV

    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        foods = list(csv.DictReader(handle))
    monkeypatch.setattr(chat, "all_foods", lambda *_: foods)
    p, _ = conversation_profile(adult(), [], "ไม่เอาอาหารเสริม")
    plan = chat._run_menu_tool(None, p, {"meal_count": count, "allow_extra_meals": False})
    assert "error" not in plan, plan
    assert len(plan["meals"]) == count
    assert all(not excluded_by(item, ["ไม่ใช้อาหารเสริม"])
               for meal in plan["meals"] for item in meal["items"])
    validate_day_plan(plan, foods)


def test_food_named_in_any_earlier_user_turn_answers_a_portion_followup(monkeypatch):
    # 23 Oct retest: "ข้าวมันไก่ 1 จานกี่แคลอรี่" then "ถ้ากินครึ่งจานล่ะ" asked the
    # user to confirm the food name again.
    monkeypatch.setattr(
        chat, "lookup_food", lambda *_: {"found": True, "results": [{"name_th": "ข้าวมันไก่"}]}
    )
    common = {"pending_confirmations": [], "partial_candidates_this_turn": []}
    earlier = ["ข้าวมันไก่ 1 จานกี่แคลอรี่", "แล้วโปรตีนล่ะ"]
    assert chat._run_food_lookup(
        None, "ข้าวมันไก่", user_message="ถ้ากินครึ่งจานล่ะ", earlier_user_messages=earlier, **common
    )["found"]
    # A name only the assistant mentioned still needs the user to say it.
    assert not chat._run_food_lookup(
        None, "ข้าวมันไก่", user_message="ถ้ากินครึ่งจานล่ะ",
        earlier_user_messages=["ขอเมนูกลางวันหน่อย"], **common,
    )["found"]
