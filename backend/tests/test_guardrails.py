"""Tests for the rule-based safety pre-check.

These double as the evidence that safety behaviour is deterministic and
reproducible - it does not depend on what the LLM happens to do that run.
"""

import pytest

from app.services.guardrails import Flag, check, instructions_for


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
