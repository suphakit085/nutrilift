"""User intent, real supplemental portions and independently verified totals."""

import csv
from copy import deepcopy

import pytest

from app.services import meal_plan
from app.services.meal_plan import MealPlanError, build_day_plan, plan_day_menu, validate_day_plan
from app.services.menu_context import conversation_profile, menu_planning_options
from tests.test_meal_plan import FOODS_CSV
from tests.test_profile_chat_context import saved

HIGH_TARGETS = {"kcal": 4238, "protein_g": 198, "carb_g": 639, "fat_g": 99}


@pytest.fixture(scope="module")
def foods():
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def high_plans(foods):
    return {n: build_day_plan(foods, HIGH_TARGETS, meal_count=n, practical_portions=True)
            for n in range(3, 7)}


@pytest.mark.parametrize("message,count,allow,suggest", [
    ("จัดเมนูให้หน่อย", None, None, True),
    ("ขอ 3 มื้อ", 3, False, True),
    ("ขอสามมื้อหลักและสองมื้อเสริม", 5, False, True),
    ("ขอ ๖ มื้อ", 6, False, True),
    ("มื้อเสริม 2 มื้อ", 5, False, True),
    ("ขอแค่ 3 มื้อ", 3, False, False),
    ("ขอ 3 มื้อ เท่านั้น", 3, False, False),
    ("ไม่เอามื้อเสริม", 3, False, False),
    ("ไม่ต้องเพิ่มของว่าง", 3, False, False),
    ("อย่าเพิ่มมื้อเสริม", 3, False, False),
    ("เพิ่มมื้อเสริมได้", None, True, True),
    ("จัดอาหารว่างได้", None, True, True),
    ("ไม่เอา 4 มื้อ ขอสามมื้อ", 3, False, True),
    ("ขอ 7 มื้อ", 7, False, True),
    ("ขอ 7 มื้อ ไม่เพิ่มมื้อเสริม", 7, False, False),
    ("ขอ 5 มื้อ ไม่เพิ่มมื้อเสริม", 5, False, False),
    ("ไม่เอามื้อเสริม แต่ตอนนี้เพิ่มมื้อเสริมได้", 3, True, True),
    ("เพิ่มมื้อเสริมได้ แต่ตอนนี้ไม่เอามื้อเสริม", 3, False, False),
    ("มื้อเสริม 1 มื้อ เปลี่ยนใจขอมื้อเสริม 2 มื้อ", 5, False, True),
])
def test_explicit_user_choices(message, count, allow, suggest):
    assert menu_planning_options([], message) == {
        "meal_count": count, "allow_extra_meals": allow, "suggest_extra_meals": suggest,
    }


def test_followups_withdraw_permission_and_ignore_assistant():
    history = [{"role": "user", "content": "ขอ 5 มื้อ เพิ่มมื้อเสริมได้"},
               {"role": "assistant", "content": "จะเพิ่มเป็น 6 มื้อ"}]
    assert menu_planning_options(history, "ไม่เอามื้อเสริมแล้ว") == {
        "meal_count": 3, "allow_extra_meals": False, "suggest_extra_meals": False,
    }
    assert menu_planning_options(history, "เพิ่มอีก 1 มื้อ")["meal_count"] == 6
    assert menu_planning_options(history, "จัดตามความเหมาะสม")["meal_count"] is None
    assert menu_planning_options(history[:1], "ขอ 3 มื้อ")["allow_extra_meals"] is False


@pytest.mark.parametrize("message", ["ไม่เอามื้อเสริม", "ไม่เอาของว่าง", "ไม่เอาอาหารว่าง"])
def test_meal_preference_does_not_become_a_food_allergy(message):
    profile = saved()
    effective, _ = conversation_profile(profile, [], message)
    assert effective.restrictions == profile.restrictions


@pytest.mark.parametrize("message", [
    "ฉันแพ้นมวัวและแพ้ถั่ว ช่วยจัดเมนู", "แพ้นมวัว กับแพ้ถั่วด้วย",
])
def test_repeated_allergy_verbs_keep_both_recognized_allergies(message):
    effective, _ = conversation_profile(saved(), [], message)
    assert {"แพ้นมวัว", "แพ้ถั่ว"}.issubset(effective.restrictions)
    assert not any(r.startswith("ข้อจำกัดที่ยังไม่รองรับ:") for r in effective.restrictions)


def test_real_high_energy_plan_needs_extras_instead_of_larger_main_portions(foods, high_plans):
    assert not high_plans[3]["within_tolerance"]
    assert high_plans[6]["within_tolerance"], high_plans[6]["deviation_pct"]
    by_name = {f["name_th"]: f for f in foods}
    for count, plan in high_plans.items():
        validate_day_plan(plan, foods)
        assert len(plan["meals"]) == count
        assert sum(m["kind"] == "main" for m in plan["meals"]) == 3
        assert sum(m["kind"] == "supplemental" for m in plan["meals"]) == count - 3
        assert plan["practicality"]["meal_weights_within_preference"]
        for meal in plan["meals"]:
            assert sum(i["grams"] for i in meal["items"]) == pytest.approx(meal["food_weight_g"])
            for item in meal["items"]:
                source = by_name[item["name_th"]]
                if source["category"] == "ไข่" and "ไข่ขาว" not in source["name_th"]:
                    assert meal_plan._is_countable(source)
                    assert item["portion"].is_integer()
                assert item["grams"] <= item["portion_policy"]["planning_max_grams"]
                if item["role"] == "carb":
                    assert item["grams"] <= (200 if meal["kind"] == "supplemental" else 300)
                if meal["kind"] == "supplemental":
                    assert item["portion_policy"]["key"] != "added-fat"


def test_automatic_chooses_first_working_count_and_fixed_count_only_offers_it(
    monkeypatch, high_plans,
):
    calls = []

    def build(_foods, _targets, _restrictions, _variant, count, **_kwargs):
        calls.append(count)
        return deepcopy(high_plans[count])

    monkeypatch.setattr(meal_plan, "build_day_plan", build)
    expected = next(n for n, p in high_plans.items() if p["within_tolerance"])
    automatic = plan_day_menu([], HIGH_TARGETS)
    assert automatic["meal_count"] == expected
    assert calls == list(range(3, expected + 1))
    fixed = plan_day_menu([], HIGH_TARGETS, meal_count=3)
    assert fixed["meal_count"] == 3
    assert fixed["totals"] == high_plans[3]["totals"]
    assert fixed["extra_meal_options"][0]["meal_count"] == expected
    assert fixed["extra_meal_options"][0]["totals"] == automatic["totals"]
    allowed = plan_day_menu([], HIGH_TARGETS, meal_count=3, allow_extra_meals=True)
    assert allowed["meal_count"] == expected
    calls.clear()
    refused = plan_day_menu([], HIGH_TARGETS, **menu_planning_options([], "ไม่เอามื้อเสริม"))
    assert calls == [3]
    assert refused["extra_meal_options"] == []


def test_cached_pair_score_matches_full_source_calculation(foods, high_plans):
    plan = high_plans[6]
    by_name = {f["name_th"]: f for f in foods}
    template = {m.key: m for m in meal_plan.meal_template(6, True)}
    items = []
    for result in plan["meals"]:
        meal = template[result["key"]]
        for row in result["items"]:
            slot = next(s for s in meal.slots if s.role == row["role"])
            items.append(meal_plan._Item(by_name[row["name_th"]], meal, slot, row["portion"], True))
    for first, second in [(items[0], items[1]), (items[0], items[-1]), (items[-2], items[-1])]:
        score = meal_plan._pair_scorer(items, first, second, HIGH_TARGETS, 6)
        for a in (first.choices[0], first.choices[-1]):
            for b in (second.choices[0], second.choices[-1]):
                first.mult, second.mult = a, b
                assert score() == pytest.approx(meal_plan._score(items, HIGH_TARGETS, 6), abs=1e-10)


def test_option_rendering_keeps_the_original_table_totals(high_plans, monkeypatch):
    from app.services.chat import _menu_reply

    monkeypatch.setattr(meal_plan, "build_day_plan",
                        lambda _f, _t, _r, _v, n, **_kw: deepcopy(high_plans[n]))
    plan = plan_day_menu([], HIGH_TARGETS, meal_count=3)
    answer = _menu_reply(plan)
    assert f"| รวมทั้งวัน | | {plan['totals']['kcal']:.1f} |" in answer
    assert "ทางเลือกที่คำนวณแล้วเข้าเกณฑ์" in answer
    assert "ยังไม่ได้รวมอยู่ในตารางและยอดรวมด้านบน" in answer
    assert "| มื้อเสริมที่" not in answer


@pytest.mark.parametrize("field,value", [
    ("main_meal_count", 4), ("supplemental_meal_count", 99),
    ("kind", "main"), ("food_weight_g", 999),
    ("meal_weights_within_preference", False),
])
def test_validator_rejects_false_structure_and_weight_claims(foods, high_plans, field, value):
    plan = deepcopy(high_plans[6])
    location = (plan["meals"][-1] if field in {"kind", "food_weight_g"} else
                plan["practicality"] if field == "meal_weights_within_preference" else plan)
    location[field] = value
    with pytest.raises(MealPlanError):
        validate_day_plan(plan, foods)


def test_impossible_targets_remain_unsuccessful_with_no_false_option(monkeypatch, high_plans):
    def impossible(_f, _t, _r, _v, n, **_kw):
        plan = deepcopy(high_plans[n])
        plan["within_tolerance"] = False
        return plan

    monkeypatch.setattr(meal_plan, "build_day_plan", impossible)
    result = plan_day_menu([], HIGH_TARGETS)
    assert not result["within_tolerance"]
    assert result["meal_count"] == 3 and not result["extra_meal_options"]


@pytest.mark.parametrize("restrictions", [["แพ้ถั่ว"], ["มังสวิรัติ", "แพ้ถั่ว"], ["วีแกน"]])
def test_all_extra_meals_keep_dietary_filters(foods, restrictions):
    targets = {"kcal": 2000, "protein_g": 99, "carb_g": 274, "fat_g": 50}
    plan = plan_day_menu(foods, targets, restrictions, meal_count=6)
    validate_day_plan(plan, foods)
    assert plan["meal_count"] == 6
    by_name = {f["name_th"]: f for f in foods}
    assert all(meal_plan.excluded_by(by_name[i["name_th"]], restrictions) is None
               for m in plan["meals"] for i in m["items"])
