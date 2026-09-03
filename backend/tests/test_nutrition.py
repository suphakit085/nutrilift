"""Unit tests for the deterministic calculators.

Expected values are computed by hand in the comments so the thesis can show the
numbers were verified against the published formulas, not against the code.
"""

from datetime import UTC, datetime

import pytest

from app.services.nutrition import (
    ACTIVITY_FACTORS,
    NutritionInputError,
    ProfileInput,
    bmr_katch_mcardle,
    bmr_mifflin_st_jeor,
    calc_nutrition_targets,
    lean_body_mass,
    summarize_targets_th,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_profile(**overrides) -> ProfileInput:
    base = {
        "sex": "male",
        "birth_year": 2001,
        "height_cm": 175.0,
        "weight_kg": 70.0,
        "activity_level": "moderate",
        "goal": "maintain",
    }
    base.update(overrides)
    return ProfileInput(**base)


# --------------------------------------------------------------------------
# BMR formulas
# --------------------------------------------------------------------------


def test_mifflin_male():
    # 10*70 + 6.25*175 - 5*25 + 5 = 700 + 1093.75 - 125 + 5 = 1673.75
    assert bmr_mifflin_st_jeor("male", 70, 175, 25) == pytest.approx(1673.75)


def test_mifflin_female():
    # 10*60 + 6.25*165 - 5*30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
    assert bmr_mifflin_st_jeor("female", 60, 165, 30) == pytest.approx(1320.25)


def test_lean_body_mass():
    assert lean_body_mass(80, 20) == pytest.approx(64.0)


def test_katch_mcardle():
    # LBM = 80 * 0.80 = 64;  370 + 21.6*64 = 370 + 1382.4 = 1752.4
    assert bmr_katch_mcardle(80, 20) == pytest.approx(1752.4)


def test_katch_mcardle_used_when_body_fat_known():
    with_bf = calc_nutrition_targets(make_profile(body_fat_pct=15))
    without_bf = calc_nutrition_targets(make_profile())
    assert with_bf["bmr_formula"] == "Katch-McArdle"
    assert without_bf["bmr_formula"] == "Mifflin-St Jeor"


# --------------------------------------------------------------------------
# Full target calculation
# --------------------------------------------------------------------------


def test_maintain_targets_male_25():
    """Male 25y, 175cm, 70kg, moderate activity, maintain.

    BMR  = 1673.75
    TDEE = 1673.75 * 1.55            = 2594.31
    kcal = TDEE (no adjustment)      = 2594.31
    protein = 70 * 1.8               = 126 g  -> 504 kcal
    fat     = 70 * 0.9               = 63 g   -> 567 kcal (floor 57.7 g not binding)
    carb    = (2594.31-504-567) / 4  = 380.83 g
    """
    r = calc_nutrition_targets(make_profile())

    assert r["bmr_kcal"] == 1674
    assert r["tdee_kcal"] == 2594
    assert r["energy_target_kcal"] == 2594
    assert r["macros"]["protein_g"] == 126
    assert r["macros"]["fat_g"] == 63
    assert r["macros"]["carb_g"] == 381
    assert r["warnings"] == []


def test_macro_kcal_sum_matches_energy_target():
    for goal in ("cut", "maintain", "bulk"):
        r = calc_nutrition_targets(make_profile(goal=goal))
        m = r["macros"]
        total = m["protein_kcal"] + m["fat_kcal"] + m["carb_kcal"]
        # rounding of each component can move the sum by a few kcal
        assert total == pytest.approx(r["energy_target_kcal"], abs=5)


def test_cut_is_below_and_bulk_above_maintenance():
    cut = calc_nutrition_targets(make_profile(goal="cut"))
    maintain = calc_nutrition_targets(make_profile(goal="maintain"))
    bulk = calc_nutrition_targets(make_profile(goal="bulk"))

    assert cut["energy_target_kcal"] < maintain["energy_target_kcal"]
    assert bulk["energy_target_kcal"] > maintain["energy_target_kcal"]
    # cut = TDEE * (1 - 0.175) = 2594.31 * 0.825 = 2140.3
    assert cut["energy_target_kcal"] == 2140
    # bulk = TDEE * 1.125 = 2918.6
    assert bulk["energy_target_kcal"] == 2919


def test_cut_uses_higher_protein_than_bulk():
    cut = calc_nutrition_targets(make_profile(goal="cut"))
    bulk = calc_nutrition_targets(make_profile(goal="bulk"))
    assert cut["macros"]["protein_g"] > bulk["macros"]["protein_g"]


def test_fat_floor_applied_on_aggressive_deficit():
    """A light, small person cutting: 0.9 g/kg fat falls under 20% of energy."""
    r = calc_nutrition_targets(
        make_profile(sex="female", weight_kg=45.0, height_cm=155.0, goal="bulk")
    )
    fat_energy_share = r["macros"]["fat_kcal"] / r["energy_target_kcal"]
    assert fat_energy_share >= 0.20 - 0.005
    assert r["macros"]["fat_g"] >= 45 * 0.9


def test_activity_factor_scales_tdee():
    prev = 0
    for level in ("sedentary", "light", "moderate", "active", "very_active"):
        r = calc_nutrition_targets(make_profile(activity_level=level))
        assert r["inputs"]["activity_factor"] == ACTIVITY_FACTORS[level]
        assert r["tdee_kcal"] > prev
        prev = r["tdee_kcal"]


def test_payload_carries_references_and_disclaimer():
    r = calc_nutrition_targets(make_profile())
    assert r["references"]
    assert "ไม่ใช่คำแนะนำทางการแพทย์" in r["disclaimer"]


def test_summary_is_thai_and_mentions_key_numbers():
    r = calc_nutrition_targets(make_profile())
    s = summarize_targets_th(r)
    assert "TDEE" in s
    assert str(r["macros"]["protein_g"]) in s


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"sex": "other"},
        {"goal": "shred"},
        {"activity_level": "olympian"},
        {"height_cm": 40.0},
        {"weight_kg": 5.0},
        {"body_fat_pct": 90.0},
        {"birth_year": 2020},
    ],
)
def test_invalid_input_raises(overrides):
    with pytest.raises(NutritionInputError):
        calc_nutrition_targets(make_profile(**overrides))


def test_age_derived_from_birth_year():
    assert make_profile(birth_year=2001).age(NOW) == 25


# --------------------------------------------------------------------------
# Profile-level safety (2026-09-03): the service is for adults (18+), and a cut
# is never prescribed to someone under the WHO underweight threshold.
# inputs.goal keeps the request, effective_goal is what the numbers were built
# from.
# --------------------------------------------------------------------------

THIS_YEAR = datetime.now(UTC).year


@pytest.mark.parametrize("age", [17, 15, 10])
def test_under_18_gets_no_numbers_at_all(age):
    # Not downgraded, refused: the profile route turns this into a 422 so the
    # row is never saved, and a legacy row shows no targets in chat.
    with pytest.raises(NutritionInputError, match="18-100"):
        calc_nutrition_targets(make_profile(birth_year=THIS_YEAR - age, goal="cut"))


def test_exactly_18_is_accepted_with_normal_cut():
    r = calc_nutrition_targets(make_profile(birth_year=THIS_YEAR - 18, goal="cut"))
    assert r["effective_goal"] == "cut"
    assert r["deficit_suppressed_reason"] is None
    assert r["energy_target_kcal"] < r["tdee_kcal"]


def test_underweight_cut_is_served_as_maintenance():
    # 45 kg / 1.65^2 = 16.53
    r = calc_nutrition_targets(
        make_profile(sex="female", height_cm=165.0, weight_kg=45.0, goal="cut")
    )
    assert r["bmi"] == 16.5
    assert r["underweight"] is True
    assert r["effective_goal"] == "maintain"
    assert r["deficit_suppressed_reason"] == "underweight"
    assert r["energy_target_kcal"] == r["tdee_kcal"]
    assert any("BMI" in w for w in r["warnings"])


def test_normal_adult_cut_still_gets_deficit():
    # 70 kg / 1.75^2 = 22.86
    r = calc_nutrition_targets(make_profile(goal="cut"))
    assert r["bmi"] == 22.9
    assert r["underweight"] is False
    assert r["effective_goal"] == "cut"
    assert r["deficit_suppressed_reason"] is None
    assert r["energy_target_kcal"] < r["tdee_kcal"]


def test_low_target_warning_no_longer_requires_cut():
    # female 25y, 30 kg, 120 cm, sedentary: BMR 764, TDEE 917 - under the
    # 1,200 kcal floor even at maintenance, so the warning must still fire.
    r = calc_nutrition_targets(
        make_profile(
            sex="female", weight_kg=30.0, height_cm=120.0,
            activity_level="sedentary", goal="maintain",
        )
    )
    assert r["energy_target_kcal"] < 1200
    assert any("1,200" in w for w in r["warnings"])


def test_summary_carries_warnings_and_effective_goal():
    r = calc_nutrition_targets(
        make_profile(sex="female", height_cm=165.0, weight_kg=45.0, goal="cut")
    )
    s = summarize_targets_th(r)
    assert "ระบบปรับเป็น" in s
    assert "คำเตือนจากระบบคำนวณ" in s
    assert "BMI" in s


def test_summary_has_no_warning_line_when_clean():
    s = summarize_targets_th(calc_nutrition_targets(make_profile()))
    assert "คำเตือน" not in s
