"""A per-meal question divides the calculator's own daily target (24 Oct retest)."""

from types import SimpleNamespace

from app.services import chat
from app.services.nutrition import calc_nutrition_targets
from app.services.protein_split import target_split_reply
from app.services.request_understanding import _checked
from tests.test_functional_prompt_fixes import adult, client_for, understood

TARGET_TURN = "ผมควรกินโปรตีนวันละกี่กรัมครับ ตามเป้าหมายของผม"
FOLLOW_UP = "แล้วถ้ากิน 4 มื้อ มื้อละกี่กรัมครับ"
HISTORY = [
    {"role": "user", "content": TARGET_TURN},
    {"role": "assistant", "content": "เป้าหมายที่คำนวณจากข้อมูลที่ใช้ในห้องนี้ครับ\n- โปรตีน: 162 กรัม/วัน"},
]


def split(**changes):
    return {"meal_count": 4, "nutrient": "protein", "user_turn": 1, "quote": "4 มื้อ"} | changes


def reading(meal_split, **changes):
    return understood(meal_split=meal_split, **changes).model_dump_json()


def test_grounded_split_is_kept():
    value = _checked(reading(split()), [TARGET_TURN, FOLLOW_UP])
    assert value.meal_split.meal_count == 4


def test_thai_number_word_grounds_the_count():
    turns = [TARGET_TURN, "ถ้าแบ่งเป็นสี่มื้อล่ะ"]
    value = _checked(reading(split(quote="สี่มื้อ")), turns)
    assert value.meal_split.meal_count == 4


def test_ungrounded_split_is_dropped_not_fatal():
    turns = [TARGET_TURN, FOLLOW_UP]
    for bad in (split(meal_count=5), split(user_turn=0, quote="โปรตีน"), split(quote="5 มื้อ")):
        value = _checked(reading(bad), turns)
        assert value.meal_split is None and value.task == "knowledge"


def test_medical_reading_drops_the_split():
    value = _checked(reading(split(), medical_self_context=True), [TARGET_TURN, FOLLOW_UP])
    assert value.meal_split is None


def test_split_uses_the_calculator_target():
    targets = calc_nutrition_targets(adult())
    protein = targets["macros"]["protein_g"]
    reply = target_split_reply(targets, 4, "protein")
    assert f"วันละ {protein} กรัม" in reply and f"{protein} ÷ 4" in reply
    energy = target_split_reply(targets, 3, "energy")
    assert f"{targets['energy_target_kcal']} ÷ 3" in energy and "กิโลแคลอรีต่อมื้อ" in energy


def _answer(monkeypatch, state):
    client, calls = client_for(state)
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message=FOLLOW_UP, history=HISTORY,
        profile=adult(),
    )
    return result, calls


def test_split_reading_beats_the_target_explanation(monkeypatch):
    # The interpreter chose calculate_targets for this follow-up in 2 of 3 runs.
    result, calls = _answer(monkeypatch, reading(split(), task="calculate_targets",
                                                 personal_context=True))
    protein = calc_nutrition_targets(adult())["macros"]["protein_g"]
    assert result["type"] == "done" and result["model"] == "rule:target_split"
    assert f"{protein} ÷ 4" in result["text"]
    assert "วิธีคำนวณของระบบ" not in result["text"]
    assert len(calls) == 1  # interpreter only, no answer model


def test_without_split_the_target_explanation_is_unchanged(monkeypatch):
    result, _ = _answer(monkeypatch, reading(None, task="calculate_targets", personal_context=True))
    assert result["model"] == "rule:target_explanation"


def test_stated_total_is_divided_instead_of_the_target():
    # 24 Oct probe M4-r2: the user's own 150 g must not become the 117 g target.
    turn = "ผมกินโปรตีนวันละ 150 กรัม แบ่ง 5 มื้อ มื้อละกี่กรัม"
    value = _checked(reading(split(meal_count=5, user_turn=0, quote="5 มื้อ", stated_total=150,
                                   total_quote="150 กรัม")), [turn])
    reply = target_split_reply(calc_nutrition_targets(adult()), 5, "protein",
                               value.meal_split.stated_total)
    assert "150 ÷ 5 = **30 กรัมต่อมื้อ**" in reply


def test_ungrounded_stated_total_drops_the_split():
    turn = "ผมกินโปรตีนวันละ 150 กรัม แบ่ง 5 มื้อ มื้อละกี่กรัม"
    for bad in ({"stated_total": 120, "total_quote": "150 กรัม"},
                {"stated_total": 150, "total_quote": None},
                {"stated_total": None, "total_quote": "150 กรัม"}):
        value = _checked(reading(split(meal_count=5, user_turn=0, quote="5 มื้อ", **bad)), [turn])
        assert value.meal_split is None
