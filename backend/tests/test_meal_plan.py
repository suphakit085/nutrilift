"""Unit tests for the deterministic one-day menu builder.

The planner is a pure function over food rows, so these drive it with a small
hand-written table where every expected total can be checked by hand, plus the
real ``knowledge/foods.csv`` for the properties that only mean something against
the actual data (does a real profile's menu land on target, does an allergy
filter remove what it should).
"""

import csv
from pathlib import Path

import pytest

from app.services.meal_plan import (
    MEAL_TEMPLATE,
    PORTION_STEP,
    TOLERANCE,
    MealPlanError,
    build_day_plan,
    excluded_by,
    normalize_thai,
    roles_of,
    summarize_plan_th,
)
from app.services.nutrition import ProfileInput, calc_nutrition_targets

FOODS_CSV = Path(__file__).resolve().parents[2] / "knowledge" / "foods.csv"


def food(name, category, kcal, p, c, f, *, serving_g=100.0, serving="100 กรัม",
         fiber=1.0, source="TEST", name_en=""):
    return {
        "name_th": name, "name_en": name_en, "category": category,
        "serving_desc": serving, "serving_g": serving_g, "kcal": kcal,
        "protein_g": p, "carb_g": c, "fat_g": f, "fiber_g": fiber, "source": source,
    }


#: Enough rows to fill every slot in MEAL_TEMPLATE several times over.
TINY_TABLE = [
    food("อกไก่", "เนื้อสัตว์", 165, 31.0, 0.0, 3.6),
    food("ปลานิล", "ปลาและอาหารทะเล", 128, 26.0, 0.0, 2.7),
    food("ไข่ไก่, ทั้งฟอง", "ไข่", 159, 13.2, 1.5, 11.1),
    food("เต้าหู้ขาวแข็ง", "โปรตีนพืช", 126, 12.9, 0.0, 7.2),
    food("ข้าวสวย", "ข้าว-แป้ง", 77, 1.3, 17.6, 0.1, serving_g=60.0, serving="1 ทัพพี"),
    food("ข้าวเจ้า, สุก", "ข้าว-แป้ง", 129, 2.2, 29.4, 0.2),
    food("มันเทศ", "หัวและมันต่าง ๆ", 120, 1.6, 28.0, 0.1),
    food("เผือก", "หัวและมันต่าง ๆ", 117, 1.7, 26.1, 0.1),
    food("ผักกาดหอม", "ผัก", 15, 1.4, 2.9, 0.2, fiber=1.3),
    food("แครอท", "ผัก", 41, 0.9, 9.6, 0.2, fiber=2.8),
    food("ฝรั่ง", "ผลไม้", 68, 2.6, 14.3, 1.0, fiber=5.4),
    food("กล้วยหอม", "ผลไม้", 109, 1.3, 24.8, 0.1, fiber=2.6),
    food("งาขาว", "ถั่วและเมล็ด", 602, 22.8, 0.0, 52.0),
    food("เนยสด, ชนิดจืด", "น้ำมันและไขมัน", 717, 0.9, 0.1, 81.1),
]

TARGETS = {"kcal": 2000.0, "protein_g": 140.0, "carb_g": 220.0, "fat_g": 60.0}


@pytest.fixture(scope="module")
def real_foods():
    rows = list(csv.DictReader(FOODS_CSV.open(encoding="utf-8-sig")))
    for row in rows:
        for key in ("serving_g", "kcal", "protein_g", "carb_g", "fat_g", "fiber_g"):
            row[key] = float(row[key]) if row[key] else 0.0
    return rows


# --------------------------------------------------------------------------
# Thai normalisation - foods.csv spells "น้ำ" two ways
# --------------------------------------------------------------------------


def test_both_spellings_of_nam_normalise_together():
    assert normalize_thai("นํ้าปลา") == normalize_thai("น้ำปลา")
    assert normalize_thai("ต้มยำกุ้ง") == normalize_thai("ต้มยํากุ้ง")


def test_normalisation_does_not_merge_unrelated_words():
    assert normalize_thai("ข้าว") != normalize_thai("ขาว")


def test_fish_sauce_is_excluded_in_either_spelling():
    for name in ("นํ้าปลา", "น้ำปลา"):
        assert excluded_by(food(name, "เครื่องปรุง", 60, 8.0, 4.0, 0.0), ["มังสวิรัติ"]) == "มังสวิรัติ"


# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------


def test_lean_meat_is_a_protein_anchor_and_rice_is_a_carb_anchor():
    assert "protein" in roles_of(TINY_TABLE[0])
    assert "carb" in roles_of(TINY_TABLE[4])
    assert "carb" not in roles_of(TINY_TABLE[0])


def test_condiment_and_low_calorie_drink_fill_no_role():
    assert roles_of(food("ซุปไก่สกัด", "อื่น ๆ", 32, 8.1, 0.0, 0.0)) == frozenset()
    assert roles_of(food("น้ำปลา", "เครื่องปรุง", 60, 8.0, 4.0, 0.0)) == frozenset()


def test_uncooked_grain_is_not_a_carb_anchor():
    # Composition tables list rice by dry weight; 100 g of it is not a portion.
    assert "carb" not in roles_of(food("ข้าวเจ้า, พันธุ์ต่างๆ", "ข้าว-แป้ง", 354, 6.8, 79.7, 0.7))
    assert "carb" in roles_of(food("ข้าวเจ้า, สุก", "ข้าว-แป้ง", 129, 2.2, 29.4, 0.2))


def test_bread_stays_a_carb_anchor_despite_high_density():
    assert "carb" in roles_of(food("ขนมปังโฮลวีท", "ข้าว-แป้ง", 273, 11.9, 41.3, 5.4))


# --------------------------------------------------------------------------
# Restrictions
# --------------------------------------------------------------------------


def test_vegetarian_keeps_eggs_but_vegan_does_not():
    egg = TINY_TABLE[2]
    assert excluded_by(egg, ["มังสวิรัติ"]) is None
    assert excluded_by(egg, ["วีแกน"]) == "วีแกน"


def test_vegetarian_still_excludes_fish_roe():
    assert excluded_by(food("ไข่ปลากระบอก, เค็ม", "ไข่", 480, 41.7, 0.0, 34.8), ["มังสวิรัติ"])


def test_dairy_allergy_does_not_catch_bread_or_fermented_pork():
    # "นม" is a substring of ขนมปัง and แหนม; the rule must not fire on either.
    assert excluded_by(food("ขนมปังโฮลวีท", "ข้าว-แป้ง", 273, 11.9, 41.3, 5.4), ["แพ้นมวัว"]) is None
    assert excluded_by(food("แหนม, หมู", "เนื้อสัตว์", 200, 15.0, 2.0, 14.0), ["แพ้นมวัว"]) is None
    assert excluded_by(TINY_TABLE[13], ["แพ้นมวัว"]) == "แพ้นมวัว"


def test_seafood_allergy_and_halal_exclude_what_they_should():
    assert excluded_by(TINY_TABLE[1], ["แพ้อาหารทะเล"]) == "แพ้อาหารทะเล"
    assert excluded_by(food("หมูสามชั้น", "เนื้อสัตว์", 428, 21.1, 0.0, 38.2), ["ฮาลาล"]) == "ฮาลาล"
    assert excluded_by(TINY_TABLE[0], ["ฮาลาล"]) is None


def test_unknown_restriction_is_never_silently_applied():
    plan = build_day_plan(TINY_TABLE, TARGETS, ["แพ้อะไรสักอย่าง"])
    assert plan["restrictions_unknown"] == ["แพ้อะไรสักอย่าง"]
    assert any("ไม่รู้จักข้อจำกัด" in w for w in plan["warnings"])


# --------------------------------------------------------------------------
# Plan construction
# --------------------------------------------------------------------------


def test_totals_are_the_sum_of_the_items():
    plan = build_day_plan(TINY_TABLE, TARGETS)
    for key in ("kcal", "protein_g", "carb_g", "fat_g"):
        summed = sum(item[key] for meal in plan["meals"] for item in meal["items"])
        assert plan["totals"][key] == pytest.approx(summed, abs=0.5)


def test_every_portion_sits_on_the_quarter_serving_grid():
    plan = build_day_plan(TINY_TABLE, TARGETS)
    for meal in plan["meals"]:
        for item in meal["items"]:
            steps = item["portion"] / PORTION_STEP
            assert steps == pytest.approx(round(steps)), item


def test_no_food_is_served_twice_when_the_table_is_big_enough(real_foods):
    plan = build_day_plan(real_foods, TARGETS)
    names = [item["name_th"] for meal in plan["meals"] for item in meal["items"]]
    assert len(names) == len(set(names))


def test_a_tiny_table_reuses_a_food_rather_than_leaving_a_slot_empty():
    # TINY_TABLE has fewer distinct foods than the template has slots. Repeating
    # is the documented last resort in _pick; the alternative (dropping slots)
    # would quietly shrink the day and make the totals miss for a reason the
    # user could not see.
    plan = build_day_plan(TINY_TABLE, TARGETS)
    slots = sum(len(meal.slots) for meal in MEAL_TEMPLATE)
    assert sum(len(m["items"]) for m in plan["meals"]) == slots


def test_every_meal_in_the_template_is_present():
    plan = build_day_plan(TINY_TABLE, TARGETS)
    assert [m["key"] for m in plan["meals"]] == [m.key for m in MEAL_TEMPLATE]


def test_same_inputs_give_the_same_menu_and_variant_changes_it():
    first = build_day_plan(TINY_TABLE, TARGETS, variant=0)
    again = build_day_plan(TINY_TABLE, TARGETS, variant=0)
    other = build_day_plan(TINY_TABLE, TARGETS, variant=1)
    assert summarize_plan_th(first) == summarize_plan_th(again)
    assert summarize_plan_th(first) != summarize_plan_th(other)


def test_estimated_rows_are_never_used():
    table = [*TINY_TABLE, food("ผัดผักรวม", "กับข้าว", 110, 3.0, 10.0, 7.0, source="TOVERIFY-INMU")]
    plan = build_day_plan(table, TARGETS)
    assert plan["estimated_rows_dropped"] == 1
    names = [item["name_th"] for meal in plan["meals"] for item in meal["items"]]
    assert "ผัดผักรวม" not in names


def test_zero_target_is_rejected():
    with pytest.raises(MealPlanError):
        build_day_plan(TINY_TABLE, {**TARGETS, "protein_g": 0})


def test_no_usable_protein_source_raises():
    with pytest.raises(MealPlanError, match="โปรตีน"):
        build_day_plan([f for f in TINY_TABLE if "protein" not in roles_of(f)], TARGETS)


def test_missing_target_is_reported_not_hidden():
    # 500 g of protein cannot be reached from any table; the plan must come back
    # flagged rather than presented as if it had hit the number.
    plan = build_day_plan(TINY_TABLE, {**TARGETS, "protein_g": 500.0})
    assert plan["within_tolerance"] is False
    assert plan["deviation_pct"]["protein_g"] < -30
    assert any("เข้าเป้าไม่ครบ" in w for w in plan["warnings"])


# --------------------------------------------------------------------------
# Against the real food table
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("goal", ["cut", "bulk", "maintain"])
def test_real_table_hits_target_for_unrestricted_profiles(real_foods, sex, goal):
    profile = ProfileInput(
        sex=sex, birth_year=1996, height_cm=172, weight_kg=68,
        activity_level="moderate", goal=goal, training_days=4,
    )
    targets = calc_nutrition_targets(profile)
    plan = build_day_plan(
        real_foods,
        {"kcal": targets["energy_target_kcal"],
         **{k: targets["macros"][k] for k in ("protein_g", "carb_g", "fat_g")}},
    )
    assert plan["within_tolerance"], plan["deviation_pct"]
    for key, tol in TOLERANCE.items():
        assert abs(plan["deviation_pct"][key]) <= tol * 100


def test_real_table_respects_a_seafood_allergy(real_foods):
    plan = build_day_plan(real_foods, TARGETS, ["แพ้อาหารทะเล"])
    for meal in plan["meals"]:
        for item in meal["items"]:
            assert "ปลา" not in item["name_th"], item
            assert "กุ้ง" not in item["name_th"], item
    assert plan["excluded_counts"]["แพ้อาหารทะเล"] > 50


def test_vegan_shortfall_is_reported_rather_than_hidden(real_foods):
    # The food table's only plant proteins are tofu and soybeans, so a 140 g
    # protein target is genuinely unreachable. Documented in architecture.md;
    # this test pins the behaviour (report it) rather than the gap itself.
    plan = build_day_plan(real_foods, TARGETS, ["วีแกน"])
    assert plan["within_tolerance"] is False
    assert plan["deviation_pct"]["protein_g"] < 0
    assert plan["warnings"]
