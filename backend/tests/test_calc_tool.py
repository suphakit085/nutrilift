"""Tests for the calc_nutrition_targets tool wrapper.

Covers the defensive normalisation of tool arguments. The model does not always
omit optional parameters - it often sends a placeholder like ``body_fat_pct: 0``.
Letting that through made the calculators reject the call, which in turn made
the model claim (falsely) that body fat is required and refuse to answer.
"""

import pytest

from app.services.chat import _clean_overrides, _run_calc_tool
from app.services.nutrition import ProfileInput

PROFILE = ProfileInput(
    sex="male",
    birth_year=2001,
    height_cm=175.0,
    weight_kg=70.0,
    activity_level="moderate",
    goal="cut",
    training_days=4,
)


# --- argument normalisation ------------------------------------------------


def test_drops_none_values():
    assert _clean_overrides({"weight_kg": 85, "goal": None}) == {"weight_kg": 85}


@pytest.mark.parametrize("placeholder", [0, 0.0, -1, -12.5])
def test_drops_non_positive_body_fat(placeholder):
    assert "body_fat_pct" not in _clean_overrides({"body_fat_pct": placeholder})


def test_drops_non_positive_weight_and_height():
    assert _clean_overrides({"weight_kg": 0, "height_cm": 0, "goal": "bulk"}) == {"goal": "bulk"}


def test_keeps_real_measurements():
    args = {"weight_kg": 85, "height_cm": 180.5, "body_fat_pct": 15, "goal": "bulk"}
    assert _clean_overrides(args) == args


def test_keeps_non_numeric_fields_untouched():
    assert _clean_overrides({"activity_level": "active"}) == {"activity_level": "active"}


# --- tool behaviour --------------------------------------------------------


def test_placeholder_body_fat_still_produces_an_answer():
    """The regression this module exists for: 0% must not break the call."""
    result = _run_calc_tool(PROFILE, {"weight_kg": 85, "body_fat_pct": 0})
    assert "error" not in result
    assert result["bmr_formula"] == "Mifflin-St Jeor"
    # BMR = 10*85 + 6.25*175 - 5*25 + 5 = 1823.75 -> 1824
    assert result["bmr_kcal"] == 1824
    assert result["used_overrides"] == {"weight_kg": 85}


def test_user_supplied_body_fat_switches_formula():
    result = _run_calc_tool(PROFILE, {"body_fat_pct": 15})
    assert result["bmr_formula"] == "Katch-McArdle"


def test_no_overrides_uses_profile_as_is():
    result = _run_calc_tool(PROFILE, {})
    assert result["used_overrides"] is None
    assert "disclosure_required" not in result
    assert result["inputs"]["weight_kg"] == 70.0


def test_overrides_require_disclosure():
    result = _run_calc_tool(PROFILE, {"weight_kg": 85})
    assert "weight_kg=85" in result["disclosure_required"]


def test_missing_profile_returns_actionable_error():
    result = _run_calc_tool(None, {"weight_kg": 85})
    assert result["error"] == "no_profile"


def test_out_of_range_override_returns_error_not_exception():
    result = _run_calc_tool(PROFILE, {"weight_kg": 500})
    assert result["error"] == "invalid_input"
    assert "น้ำหนัก" in result["message"]
