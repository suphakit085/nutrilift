"""Tests for the rule-based safety pre-check.

These double as the evidence that safety behaviour is deterministic and
reproducible - it does not depend on what the LLM happens to do that run.
"""

from datetime import UTC, datetime

import pytest

from app.services.guardrails import Flag, check, check_profile, combine, instructions_for
from app.services.nutrition import ProfileInput

THIS_YEAR = datetime.now(UTC).year


def profile(**overrides) -> ProfileInput:
    base = {
        "sex": "female",
        "birth_year": THIS_YEAR - 30,
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "activity_level": "moderate",
        "goal": "cut",
        "training_days": 3,
    }
    base.update(overrides)
    return ProfileInput(**base)


@pytest.mark.parametrize(
    "message, expected",
    [
        ("อยากรู้วิธีฉีดเทสโทสเตอโรน ขนาดเท่าไหร่", Flag.PED),
        ("กินสเตียรอยด์แล้วต้องกินโปรตีนเพิ่มไหม", Flag.PED),
        ("SARMs ตัวไหนดีสุด", Flag.PED),
        ("เป็นเบาหวานกินคาร์บได้ไหม", Flag.MEDICAL),
        ("เป็นโรคไต กินโปรตีนเยอะได้ไหม", Flag.MEDICAL),
        ("อดอาหาร 3 วันแล้วจะผอมเร็วขึ้นไหม", Flag.DISORDERED_EATING),
        ("กินเสร็จแล้วล้วงคอออกจะช่วยลดน้ำหนักไหม", Flag.DISORDERED_EATING),
        ("ตั้งครรภ์อยู่ กินเวย์ได้ไหม", Flag.PREGNANCY),
        ("ช่วยเขียนโค้ด Python ให้หน่อย", Flag.OUT_OF_SCOPE),
    ],
)
def test_flags_fire(message, expected):
    assert expected in check(message).flags


@pytest.mark.parametrize(
    "message",
    [
        "หนูอายุ 15 อยากลดน้ำหนัก",
        "ผมอายุ 16 ปี เล่นเวทได้ไหม",
        "อายุ17ปี ควรกินโปรตีนเท่าไหร่",
    ],
)
def test_minor_detected(message):
    assert Flag.MINOR in check(message).flags


@pytest.mark.parametrize("message", ["อายุ 25 ปี ควรกินโปรตีนเท่าไหร่", "ผมอายุ 30 เล่นเวท 4 วัน"])
def test_adult_not_flagged_as_minor(message):
    assert Flag.MINOR not in check(message).flags


@pytest.mark.parametrize(
    "message",
    [
        "ควรกินโปรตีนวันละกี่กรัม",
        "ครีเอทีนกินตอนไหนดี",
        "ข้าวมันไก่กี่แคล",
        "ช่วง cut ควรลดแคลอรี่เท่าไหร่",
    ],
)
def test_normal_questions_are_clean(message):
    result = check(message)
    assert not result.triggered, f"unexpected flags: {result.flags}"


def test_multiple_flags_can_fire_together():
    result = check("หนูอายุ 16 เป็นเบาหวาน อยากอดอาหารลดน้ำหนัก")
    assert Flag.MINOR in result.flags
    assert Flag.MEDICAL in result.flags
    assert Flag.DISORDERED_EATING in result.flags


def test_instructions_empty_when_clean():
    assert instructions_for(check("ควรกินโปรตีนวันละกี่กรัม")) == ""


def test_instructions_mention_every_flag():
    result = check("อายุ 15 อยากใช้สเตียรอยด์")
    text = instructions_for(result)
    assert text
    assert "แพทย์" in text or "ผู้ปกครอง" in text
    assert text.count("- ") == len(result.flags)


def test_as_json_is_serialisable():
    result = check("อยากใช้สเตียรอยด์")
    assert result.as_json() == ["performance_enhancing_drugs"]


def test_case_insensitive_english():
    assert Flag.PED in check("Where can I buy ANABOLIC steroids?").flags


def test_empty_message_is_safe():
    assert not check("").triggered


# --- daily-intake rule (replaces the bare "0 แคล" substring, 2026-09-03) ----
#
# The old substring matched every amount ending in a zero: "800 แคล" fired by
# luck, but so did "1500 แคล". The rule now needs a daily phrase *and* an
# amount under the 1,200 kcal self-managed floor.


@pytest.mark.parametrize(
    "message",
    [
        "อยากลดน้ำหนักเร็ว ๆ กินวันละ 800 แคลได้ไหม",
        "กินวันละ 0 แคลไปเลยได้ไหม",
        "วันละ 1,000 แคล พอไหม",
        "eat 600 kcal a day, ok?",
    ],
)
def test_low_daily_intake_flagged(message):
    result = check(message)
    assert Flag.DISORDERED_EATING in result.flags
    assert any(h.startswith("วันละ ") for h in result.matched[str(Flag.DISORDERED_EATING)])


@pytest.mark.parametrize(
    "message",
    [
        "อยากกินวันละ 1500 แคล พอไหม",
        "ข้าวมันไก่ 600 แคล จริงไหม",
        "โค้กซีโร่ 0 แคล กินได้ไหม",
        "กินไปแล้ว 300 แคล",
    ],
)
def test_ordinary_kcal_mentions_not_flagged(message):
    assert Flag.DISORDERED_EATING not in check(message).flags


# --- profile-derived flags (2026-09-03) ------------------------------------
#
# check() only sees the message text. A logged-in user's age lives in the
# profile and is rarely retyped, so these are the cases the text rules missed.


def test_profile_minor_flagged_without_age_in_text():
    result = check_profile(profile(birth_year=THIS_YEAR - 15))
    assert Flag.MINOR in result.flags
    assert result.matched[str(Flag.MINOR)] == ["profile:age=15"]


def test_profile_adult_normal_weight_is_clean():
    assert not check_profile(profile()).triggered


def test_profile_underweight_flagged():
    result = check_profile(profile(weight_kg=45.0))  # 165 cm -> BMI 16.5
    assert Flag.UNDERWEIGHT in result.flags
    assert result.matched[str(Flag.UNDERWEIGHT)] == ["profile:bmi=16.5"]


def test_profile_low_energy_target_flagged_from_targets():
    result = check_profile(profile(), targets={"energy_target_kcal": 1100})
    assert Flag.LOW_ENERGY_TARGET in result.flags
    assert result.matched[str(Flag.LOW_ENERGY_TARGET)] == ["profile:energy_target_kcal=1100"]


def test_profile_without_targets_skips_energy_rule():
    assert Flag.LOW_ENERGY_TARGET not in check_profile(profile(), targets=None).flags


def test_profile_none_is_clean():
    assert not check_profile(None).triggered


def test_combine_dedupes_minor_from_text_and_profile():
    from_text = check("หนูอายุ 15 อยากลดน้ำหนัก")
    from_profile = check_profile(profile(birth_year=THIS_YEAR - 15))
    merged = combine(from_text, from_profile)
    assert merged.flags.count(Flag.MINOR) == 1
    assert "อายุ 15" in merged.matched[str(Flag.MINOR)]
    assert "profile:age=15" in merged.matched[str(Flag.MINOR)]


def test_combine_keeps_text_order_first():
    merged = combine(check("อยากใช้สเตียรอยด์"), check_profile(profile(birth_year=THIS_YEAR - 15)))
    assert merged.flags == [Flag.PED, Flag.MINOR]


def test_instructions_cover_every_profile_flag():
    result = check_profile(
        profile(birth_year=THIS_YEAR - 15, weight_kg=45.0),
        targets={"energy_target_kcal": 1100},
    )
    text = instructions_for(result)
    assert text.count("- ") == 3
    assert "ผู้ปกครอง" in text
    assert "BMI" in text
    assert "1,200" in text
