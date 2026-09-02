from datetime import date

from app.db.models import FoodLogEntry
from app.services.food_log import daily_totals


def make_entry(**overrides) -> FoodLogEntry:
    base = dict(
        user_id=None,
        food_id=None,
        food_name_th="ข้าวสวย",
        serving_desc="1 ทัพพี",
        serving_g=100.0,
        serving_kcal=130.0,
        serving_protein_g=2.7,
        serving_carb_g=28.0,
        serving_fat_g=0.3,
        quantity_servings=1.0,
        meal_type="breakfast",
        logged_date=date(2026, 9, 2),
    )
    base.update(overrides)
    return FoodLogEntry(**base)


def test_daily_totals_sums_across_meals():
    entries = [
        make_entry(meal_type="breakfast", quantity_servings=1.0),
        make_entry(meal_type="lunch", quantity_servings=2.0),
    ]
    agg = daily_totals(entries)
    assert agg["totals"]["kcal"] == 130.0 + 260.0
    assert agg["by_meal"]["breakfast"]["kcal"] == 130.0
    assert agg["by_meal"]["lunch"]["kcal"] == 260.0
    assert agg["by_meal"]["dinner"]["kcal"] == 0.0
    assert agg["by_meal"]["snack"]["kcal"] == 0.0


def test_daily_totals_scales_all_macros_by_quantity():
    entries = [make_entry(quantity_servings=1.5)]
    agg = daily_totals(entries)
    assert agg["totals"]["protein_g"] == round(2.7 * 1.5, 1)
    assert agg["totals"]["carb_g"] == round(28.0 * 1.5, 1)
    assert agg["totals"]["fat_g"] == round(0.3 * 1.5, 1)


def test_daily_totals_empty():
    agg = daily_totals([])
    assert agg["totals"] == {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    for meal in ("breakfast", "lunch", "dinner", "snack"):
        assert agg["by_meal"][meal] == {
            "kcal": 0.0,
            "protein_g": 0.0,
            "carb_g": 0.0,
            "fat_g": 0.0,
        }
