"""lookup_food must say when a row is still an estimate.

`source` already carried TOVERIFY, but a bare source string means nothing to the
model, which reported the number as a database fact like any other. The meal
planner has always dropped these rows; lookup_food handed them over unlabelled,
so the two paths treated the same data to different standards. Found while
answering "do the known limitations touch anything medical?" on 2026-09-04.
"""

import pytest

from app.services.foods import _ESTIMATE_WARNING, _row_to_dict


class _Row:
    """Just the attributes _row_to_dict reads."""

    def __init__(self, source):
        self.name_th = "ผัดผักรวม"
        self.name_en = "stir-fried vegetables"
        self.category = "กับข้าว"
        self.serving_desc = "1 จาน"
        self.serving_g = 100.0
        self.kcal = 110.0
        self.protein_g = 3.0
        self.carb_g = 10.0
        self.fat_g = 7.0
        self.fiber_g = 2.0
        self.source = source


@pytest.mark.parametrize("source", ["TOVERIFY-INMU", "TOVERIFY-LABEL"])
def test_estimated_rows_are_flagged(source):
    assert _row_to_dict(_Row(source))["estimated"] is True


@pytest.mark.parametrize(
    "source", ["ASEAN-FCD-2014-INMU:AAA19", "DOH-NSS-2018:11045", "ThaiFCD-Online-v3:T184", None]
)
def test_sourced_rows_are_not_flagged(source):
    assert _row_to_dict(_Row(source))["estimated"] is False


def test_the_warning_tells_the_model_what_to_do_about_it():
    # Not just "this is estimated" - the model has to pass that on to the user.
    assert "ค่าประมาณ" in _ESTIMATE_WARNING
    assert "บอกผู้ใช้" in _ESTIMATE_WARNING
