"""Behavioural regressions: actual portions, source math, failures and chat notes."""

import csv
from copy import deepcopy
from types import SimpleNamespace

import pytest
from google.genai import types

from app.services import meal_plan
from app.services.meal_plan import MealPlanError, build_day_plan, validate_day_plan
from tests.test_meal_plan import FOODS_CSV, TARGETS, TINY_TABLE, food


@pytest.fixture(scope="module")
def real_foods():
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def verified_plan():
    return build_day_plan(TINY_TABLE, TARGETS)


@pytest.mark.parametrize("count", [3, 4])
def test_primary_proteins_are_not_tiny_and_starches_stay_within_cap(real_foods, count):
    plan = build_day_plan(real_foods, TARGETS, meal_count=count)
    for meal in plan["meals"]:
        for item in meal["items"]:
            if item["role"] == "protein" and meal["key"] != "snack":
                assert item["grams"] >= 50
            if item["role"] == "carb":
                assert item["grams"] <= 400
    validate_day_plan(plan, real_foods)


def test_reference_weight_does_not_change_physical_portions_or_nutrients():
    row = food("น้ำมันมะกอก", "น้ำมันและไขมัน", 884, 0, 0, 100)
    small = {**row, "serving_g": 10, "serving_desc": "10 กรัม", "kcal": 88.4, "fat_g": 10}
    slot = meal_plan.Slot("fat", 0.25, 2, 110)
    meal = meal_plan.MEAL_TEMPLATE[1]
    first = meal_plan._Item(row, meal, slot, 1)
    second = meal_plan._Item(small, meal, slot, 1)
    assert [m * 100 for m in first.choices] == pytest.approx([m * 10 for m in second.choices])
    assert min(first.choices) * 100 >= 2.5
    assert max(first.choices) * 100 <= 20
    assert 5 in [m * 100 for m in first.choices]
    for a, b in zip(first.choices, second.choices, strict=True):
        first.mult, second.mult = a, b
        assert first.macros() == pytest.approx(second.macros())


def test_concentrated_solid_fat_does_not_become_a_large_breakfast_portion():
    butter = food("เนยสด, ชนิดจืด", "น้ำมันและไขมัน", 717, 0.9, 0.1, 81.1)
    item = meal_plan._Item(butter, meal_plan.MEAL_TEMPLATE[0],
                          meal_plan.Slot("fat", 0.25, 2, 110), 1)
    assert max(item.choices) * 100 <= 20


@pytest.mark.parametrize("goal,restrictions", [
    ("bulk", []), ("bulk", ["มังสวิรัติ", "แพ้ถั่ว"]),
    ("maintain", ["มังสวิรัติ", "แพ้ถั่ว"]),
])
def test_three_meal_repair_uses_bounded_food_alternatives(real_foods, goal, restrictions):
    from app.services.nutrition import ProfileInput, calc_nutrition_targets

    profile = ProfileInput(sex="male", birth_year=1998, birth_month=1, height_cm=175,
                           weight_kg=75, activity_level="moderate", goal=goal)
    result = calc_nutrition_targets(profile)
    targets = {"kcal": result["energy_target_kcal"],
               **{k: result["macros"][k] for k in ("protein_g", "carb_g", "fat_g")}}
    plan = build_day_plan(real_foods, targets, restrictions, variant=1, meal_count=3)
    assert plan["within_tolerance"], plan["deviation_pct"]
    validate_day_plan(plan, real_foods)


def test_whole_unit_that_exceeds_cap_is_rejected_instead_of_forced_to_one():
    oversized = food("ไข่ไก่ต้ม", "ไข่", 1590, 132, 15, 111,
                     serving_g=1000, serving="1 ฟอง (1000 กรัม)")
    plan = build_day_plan([*TINY_TABLE, oversized], TARGETS)
    assert all(i["name_th"] != oversized["name_th"] for m in plan["meals"] for i in m["items"])


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf")])
def test_invalid_targets_cannot_be_reported_as_a_valid_plan(invalid):
    with pytest.raises(MealPlanError):
        build_day_plan(TINY_TABLE, {**TARGETS, "kcal": invalid})


@pytest.mark.parametrize("where,key,value", [
    ("item", "grams", 999), ("item", "protein_g", 999),
    ("item", "kcal", float("nan")), ("item", "grams", float("nan")),
    ("meal", "kcal", 999), ("meal", "kcal", float("nan")),
    ("total", "kcal", 999), ("total", "kcal", float("nan")),
])
def test_validator_rejects_wrong_or_nonfinite_reported_values(verified_plan, where, key, value):
    plan = deepcopy(verified_plan)
    location = {"item": plan["meals"][0]["items"][0], "meal": plan["meals"][0],
                "total": plan["totals"]}[where]
    location[key] = value
    with pytest.raises(MealPlanError):
        validate_day_plan(plan, TINY_TABLE)


def test_validator_rejects_wrong_success_flag_and_allergy_violation(verified_plan):
    plan = deepcopy(verified_plan)
    plan["within_tolerance"] = not plan["within_tolerance"]
    with pytest.raises(MealPlanError):
        validate_day_plan(plan, TINY_TABLE)
    plan = deepcopy(verified_plan)
    plan["restrictions_applied"] = ["วีแกน"]
    with pytest.raises(MealPlanError):
        validate_day_plan(plan, TINY_TABLE)


def test_vegan_three_meal_example_does_not_concentrate_protein_in_breakfast(real_foods):
    targets = {"kcal": 1959, "protein_g": 99, "carb_g": 287, "fat_g": 45}
    plan = build_day_plan(real_foods, targets, ["วีแกน"], meal_count=3)
    assert plan["within_tolerance"]
    # Original example concentrated about 60% of the day's protein at breakfast.
    assert max(m["protein_g"] / plan["totals"]["protein_g"] for m in plan["meals"]) < 0.5
    assert plan["practicality"]["review_status"] == "pending_dietitian_review"


def test_awkward_ladle_fraction_is_displayed_as_grams():
    row = {"serving_desc": "1 ทัพพี", "serving_g": 60}
    assert meal_plan.portion_text(125 / 60, row) == "125 กรัม"


def test_unreachable_target_still_reports_failure_instead_of_relaxing_bounds(real_foods):
    plan = build_day_plan(real_foods, {**TARGETS, "protein_g": 500}, meal_count=3)
    assert not plan["within_tolerance"]
    assert "protein_g" in plan["out_of_tolerance"]
    validate_day_plan(plan, real_foods)


def test_chat_shows_practicality_limit_and_unrounded_failure(verified_plan):
    from app.services.chat import _append_menu_data_notes, _menu_reply

    plan = deepcopy(verified_plan)
    plan["practicality"]["meal_balance_within_preference"] = False
    plan["within_tolerance"] = False
    plan["meal_count"] = 3
    plan["supplemental_meal_count"] = 0
    plan["out_of_tolerance"] = ["carb_g"]
    plan["deviation_pct"]["carb_g"] = -15.0
    text = _append_menu_data_notes(_menu_reply(plan), [plan])
    assert "ยังเข้าเป้าไม่ครบ" in text
    assert "คาร์โบไฮเดรตขาด 15.0%" in text
    assert "ยังกระจายระหว่างมื้อ" in text
    assert "ยังไม่ได้รับการทบทวนโดยนักกำหนดอาหาร" in text
    assert "ลองขอเมนูอีกแบบได้" in text


@pytest.mark.parametrize("count", [3, 4])
def test_tool_reports_no_eligible_foods_without_exposing_an_exception(
    real_foods, monkeypatch, count
):
    from app.services import chat
    from app.services.nutrition import ProfileInput

    profile = ProfileInput(sex="female", birth_year=1998, birth_month=1, weight_kg=55,
                           height_cm=160, activity_level="moderate", goal="maintain",
                           restrictions=["วีแกน", "แพ้ถั่วเหลือง"])
    monkeypatch.setattr(chat, "all_foods", lambda _db: real_foods)
    result = chat._run_menu_tool(None, profile, {"meal_count": count})
    assert result["error"] == "cannot_build_menu"
    assert "ไม่พบแหล่งโปรตีน" in result["message"]
    assert "meals" not in result


@pytest.mark.parametrize("count,restrictions", [
    (3, []), (4, []), (3, ["วีแกน"]), (4, ["แพ้ถั่วลิสง"]), (5, []), (6, []),
])
def test_chat_stream_uses_real_planner_and_requested_meals(
    real_foods, monkeypatch, count, restrictions
):
    from app.services import chat
    from app.services.nutrition import ProfileInput

    profile = ProfileInput(sex="female", birth_year=1998, birth_month=1, weight_kg=55,
                           height_cm=160, activity_level="moderate", goal="maintain",
                           restrictions=restrictions)
    monkeypatch.setattr(chat, "all_foods", lambda _db: real_foods)
    expected = chat._run_menu_tool(None, profile, {"meal_count": count})
    calls = []
    chunk = SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(parts=[
        types.Part(function_call=types.FunctionCall(
            name="suggest_day_menu", args={"meal_count": 4}
        ))
    ]), finish_reason="STOP")], text="", usage_metadata=None)

    def generate(**kwargs):
        calls.append(kwargs)
        assert len(calls) == 1, "The model must not rewrite calculated portions"
        return iter([chunk])

    monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=generate)))
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    events = list(chat.stream_chat(db, user_message=f"จัดเมนูอาหาร {count} มื้อ",
                                  profile=profile, use_rag=False))
    final = events[-1]
    assert final["type"] == "done"
    assert "| มื้อเช้า |" in final["text"] and "| มื้อเย็น |" in final["text"]
    assert ("| มื้อเสริมที่ 1 |" in final["text"]) == (count >= 4)
    assert ("| มื้อเสริมที่ 3 |" in final["text"]) == (count == 6)
    assert f"| รวมทั้งวัน | | {expected['totals']['kcal']:.1f} |" in final["text"]
    assert "within_tolerance" not in final["text"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == final["text"]
