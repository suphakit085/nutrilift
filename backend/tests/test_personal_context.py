from types import SimpleNamespace

import pytest

from app.services import chat
from app.services.personal_context import missing_personal_context_reply


@pytest.mark.parametrize("message,expected", [
    ("ช่วยจัดเมนูตามงบของฉัน ยังไม่ได้แจ้งงบ", "เท่าไร"),
    ("จัดเมนูตามงบผม", "บาท"),
    ("จัดเวลากินให้ตรงตารางของฉัน ยังไม่ได้บอกเวลาเริ่มฝึก", "กี่โมง"),
    ("จัดเมนูตามอาหารในบ้าน ยังไม่ได้บอกว่ามีอะไร", "วัตถุดิบ"),
    ("จัดเมนูตามวิธีทำอาหารที่สะดวก ยังไม่ได้บอกวิธีทำ", "อุปกรณ์"),
    ("วันนี้ฉันกินถึงเป้าโปรตีนหรือยัง ยังไม่ได้บันทึกอาหาร", "ปริมาณ"),
    ("วันนี้ฉันกินถึงเป้าหมายโปรตีนหรือยัง ยังไม่ได้บอกอาหาร", "ไม่ใช่"),
])
def test_missing_inputs_are_asked_for(message, expected):
    reply = missing_personal_context_reply(message, [], has_profile=True)
    assert reply and expected in reply
    assert "| มื้อ" not in reply


def test_unknown_profile_does_not_receive_invented_ranges():
    reply = missing_personal_context_reply(
        "ฉันควรกินพลังงานและโปรตีนกี่กรัมต่อวัน คำนวณให้เลย", [], has_profile=False,
    )
    assert reply and "โปรไฟล์" in reply and "ไม่จำเป็น" in reply
    assert "1.4" not in reply and "kcal" not in reply


@pytest.mark.parametrize("message", [
    "โปรตีนคืออะไร", "งานวิจัยโปรตีน 1.6 กรัมต่อกิโลหมายถึงอะไร",
    "ฉันควรกินโปรตีนเท่าไร", "จัดเมนู 3 มื้อตามโปรไฟล์",
    "งบ 150 บาท ขอแนวทาง ไม่ต้องรับรองราคา", "กินหลังเวทสำคัญไหม",
])
def test_general_and_answerable_questions_are_not_blocked(message):
    assert missing_personal_context_reply(message, [], has_profile=True) is None


def test_user_budget_persists_but_assistant_guess_does_not():
    question = "จัดเมนูตามงบของฉัน"
    assert missing_personal_context_reply(question, [
        {"role": "user", "content": "งบ 150 บาทต่อวัน"},
    ], has_profile=True) is None
    assert missing_personal_context_reply(question, [
        {"role": "assistant", "content": "งบคุณ 150 บาท"},
    ], has_profile=True)


def test_explicit_measurements_without_profile_can_reach_calculator():
    assert missing_personal_context_reply(
        "ฉันชายอายุ 26 หนัก 75 กก สูง 175 ซม คำนวณพลังงาน", [], has_profile=False,
    ) is None


@pytest.mark.parametrize("message", ["ฉันควรกินโปรตีนจากอะไร", "ฉันควรกินพลังงานก่อนเวทไหม"])
def test_general_personal_questions_do_not_require_profile(message):
    assert missing_personal_context_reply(message, [], has_profile=False) is None


def test_missing_context_does_not_call_provider_or_menu_tool(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Must clarify without model/tool calls")
    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat, "_execute_tool", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", lambda *args: [])
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None),
                                 user_message="จัดเมนูตามงบของฉัน ยังไม่ได้แจ้งงบ")
    assert result["model"] == "rule:missing_personal_context"
    assert result["tool_calls"] == [] and result["usage"]["total_tokens"] == 0


def test_medical_refusal_precedes_clarification(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Safety must precede this")
    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", forbidden)
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None),
        user_message="ฉันเป็นเบาหวาน จัดเมนูตามงบของฉัน ยังไม่ได้แจ้งงบ")
    assert result["model"] == "rule:medical_scope" and result["tool_calls"] == []


def test_verified_menu_keeps_budget_disclosure():
    plan = {
        "targets":{"kcal":2000,"protein_g":140,"carb_g":220,"fat_g":60},
        "totals":{"kcal":2000,"protein_g":140,"carb_g":220,"fat_g":60},
        "within_tolerance":True,"meals":[],
        "budget_note":"ยังไม่ได้คำนวณราคาหรือยืนยันว่าอยู่ในงบ",
    }
    assert plan["budget_note"] in chat._menu_reply(plan)
