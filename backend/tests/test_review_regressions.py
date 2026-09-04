"""Non-guardrail regressions from the 4 ก.ย. 2569 pre-deploy review."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas import ProfileIn
from app.services.chat import _history_to_contents
from app.services.foods import _escape_like
from app.services.meal_plan import build_day_plan, excluded_by
from app.services.nutrition import MIN_CARB_G, ProfileInput, calc_nutrition_targets
from app.services.thai_text import compose_sara_am

# --- age gate rounds down --------------------------------------------------


def _profile(**overrides) -> ProfileInput:
    base = dict(
        sex="male", birth_year=2008, birth_month=12, height_cm=175, weight_kg=70,
        activity_level="moderate", goal="cut",
    )
    base.update(overrides)
    return ProfileInput(**base)


def test_december_birthday_is_still_17_in_september() -> None:
    today = datetime(2026, 9, 4, tzinfo=UTC)
    assert _profile(birth_year=2008, birth_month=12).age(today) == 17


def test_birth_month_itself_counts_as_not_yet() -> None:
    """The day is unknown, so within the birth month the gate stays closed."""
    today = datetime(2026, 9, 4, tzinfo=UTC)
    assert _profile(birth_year=2008, birth_month=9).age(today) == 17
    assert _profile(birth_year=2008, birth_month=8).age(today) == 18


def test_unknown_month_falls_back_to_year_difference() -> None:
    today = datetime(2026, 9, 4, tzinfo=UTC)
    assert _profile(birth_year=2008, birth_month=None).age(today) == 18


# --- Buddhist-era years -----------------------------------------------------


def _profile_in(**overrides) -> dict:
    base = dict(
        sex="male", birth_year=2004, birth_month=5, height_cm=175, weight_kg=70,
        activity_level="moderate", goal="cut",
    )
    base.update(overrides)
    return base


def test_buddhist_era_year_is_converted() -> None:
    assert ProfileIn(**_profile_in(birth_year=2547)).birth_year == 2004


def test_out_of_range_year_has_a_thai_message() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ProfileIn(**_profile_in(birth_year=1800))
    assert "ปีเกิด" in str(excinfo.value)


def test_birth_month_is_required_and_bounded() -> None:
    with pytest.raises(ValidationError):
        ProfileIn(**{k: v for k, v in _profile_in().items() if k != "birth_month"})
    with pytest.raises(ValidationError):
        ProfileIn(**_profile_in(birth_month=13))


# --- macro split at high BMI -----------------------------------------------


def test_vanishing_carbohydrate_is_flagged() -> None:
    heavy = ProfileInput(
        sex="female", birth_year=1990, birth_month=1, height_cm=160, weight_kg=90,
        activity_level="sedentary", goal="cut",
    )
    result = calc_nutrition_targets(heavy)
    assert result["macros"]["carb_g"] < MIN_CARB_G
    assert any("คาร์โบไฮเดรต" in w and "ต่ำมาก" in w for w in result["warnings"])


def test_ordinary_profile_has_no_carb_warning() -> None:
    result = calc_nutrition_targets(_profile(birth_year=2000, birth_month=1))
    assert not any("ต่ำมาก" in w for w in result["warnings"])


# --- empty assistant turns ---------------------------------------------------


def test_empty_history_turns_are_dropped() -> None:
    contents = _history_to_contents(
        [
            {"role": "user", "content": "สวัสดี"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "ครีเอทีนกินยังไง"},
        ]
    )
    assert [c.role for c in contents] == ["user", "user"]


# --- food lookup spelling ----------------------------------------------------


def test_split_sara_am_is_composed() -> None:
    assert compose_sara_am("นํ้าพริก") == "น้ำพริก"
    assert compose_sara_am("ข้าวเหนียวดํา") == "ข้าวเหนียวดำ"
    assert compose_sara_am("น้ำพริก") == "น้ำพริก"


def test_like_wildcards_are_escaped() -> None:
    assert _escape_like("100%") == "100\\%"
    assert _escape_like("a_b") == "a\\_b"


# --- meal plan restrictions ----------------------------------------------------


def _food(name: str, category: str, kcal: float, p: float, c: float, f: float) -> dict:
    return {
        "name_th": name, "category": category, "serving_desc": "100 กรัม", "serving_g": 100,
        "kcal": kcal, "protein_g": p, "carb_g": c, "fat_g": f, "fiber_g": 0.0,
        "source": "ASEAN-FCD-2014-INMU:TEST",
    }


@pytest.mark.parametrize("name", ["ไก่, เลือด, ต้ม", "เป็ด, เลือด, ต้ม", "เขียด", "กบ, ย่าง"])
def test_halal_excludes_blood_and_amphibians(name: str) -> None:
    assert excluded_by(_food(name, "เนื้อสัตว์", 100, 15, 0, 3), ["ฮาลาล"]) == "ฮาลาล"


def test_turtle_eggs_are_never_suggested() -> None:
    table = [
        _food("ไข่จะละเม็ด(ไข่ของเต่าตนุ/ เต่าแสงอาทิตย์)", "ไข่", 160, 13, 1, 11),
        _food("ไข่ไก่, ต้ม", "ไข่", 155, 13, 1, 11),
        _food("ข้าวสวย", "ข้าว-แป้ง", 130, 2.5, 28, 0.3),
        _food("ผักบุ้งผัด", "ผัก", 60, 2, 5, 3),
        _food("เต้าหู้ขาว", "โปรตีนพืช", 80, 8, 2, 4),
        _food("กล้วยน้ำว้า", "ผลไม้", 90, 1, 23, 0.3),
        _food("น้ำมันพืช", "ไขมัน", 900, 0, 0, 100),
        _food("นมสด", "นมและผลิตภัณฑ์", 60, 3, 5, 3),
    ]
    targets = {"kcal": 2000, "protein_g": 120, "carb_g": 220, "fat_g": 60}
    plan = build_day_plan(table, targets, ["มังสวิรัติ"])
    served = {item["name_th"] for meal in plan["meals"] for item in meal["items"]}
    assert not any("เต่า" in n for n in served)
    assert "ไข่ไก่, ต้ม" in served
