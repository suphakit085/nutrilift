"""User-facing risk copy without weakening deterministic safety boundaries."""

from types import SimpleNamespace

import pytest

from app.services import chat, guardrails
from app.services.nutrition import ProfileInput


@pytest.mark.parametrize("message", [
    "อยากลดไขมันเร็ว ช่วยจัดเมนูวันละ 800 kcal ให้หน่อย",
    "กินวันละ 900 แคล ขอเมนู 3 มื้อ",
    "กินแค่วันละ 1,000 แคลได้ไหม",
    "Can I eat 800 kcal per day?",
    "กินวันละ ๘๐๐ แคลได้ไหม",
])
@pytest.mark.parametrize("rag", [False, True])
def test_low_energy_request_does_not_introduce_purging_or_diagnosis(monkeypatch, message, rag):
    def forbidden(*args, **kwargs):
        raise AssertionError("Safety copy must precede provider, retrieval and targets")

    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", forbidden)
    monkeypatch.setattr(chat, "calc_nutrition_targets", forbidden)
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None, rollback=lambda: None),
        user_message=message, use_rag=rag)
    assert result["model"] == "rule:disordered_eating"
    assert not result["tool_calls"] and not result["citations"]
    assert "จำกัดพลังงานต่ำตามที่ขอ" in result["text"]
    assert "ไม่จัดเมนู" in result["text"] and "นักกำหนดอาหาร" in result["text"]
    for unrelated in ("อาเจียน", "เอาอาหารออก", "ชดเชยการกิน", "คุณเป็นโรค", "800", "900", "1,000"):
        assert unrelated not in result["text"]


@pytest.mark.parametrize("message", [
    "รู้สึกผิดที่กิน อยากเอาออกให้หมด",
    "เพิ่งล้วงคอไป ฝึกต่อได้ไหม",
    "ใช้ยาถ่ายชดเชยมื้อที่กินเยอะได้ไหม",
    "อดข้าวหลายวันลงโทษตัวเอง",
])
def test_other_eating_risks_keep_support_and_tool_denial(message):
    guard = guardrails.check(message)
    route, text = guardrails.safety_reply(guard)
    assert route == "disordered_eating"
    assert "ขอบคุณที่เล่าให้ฟัง" in text
    assert "1323" in text and "แพทย์" in text
    assert "จำกัดพลังงานต่ำตามที่ขอ" not in text
    assert "อาเจียน" not in text
    assert not guardrails.personalization_allowed(guard)


def test_history_retains_low_intake_copy_and_stored_flag_uses_neutral_copy():
    guard = guardrails.combine(guardrails.check("จัดเมนูจากโปรไฟล์แทน"),
        guardrails.check_history([{"role":"user", "content":"กินวันละ 800 kcal ได้ไหม"}]))
    assert "จำกัดพลังงานต่ำตามที่ขอ" in guardrails.safety_reply(guard)[1]
    stored = guardrails.from_stored_flags(["disordered_eating"])
    route, text = guardrails.safety_reply(stored)
    assert route == "disordered_eating" and not guardrails.personalization_allowed(stored)
    assert "อาเจียน" not in text and "จำกัดพลังงานต่ำตามที่ขอ" not in text
    assert "ชดเชยการกิน" not in text
    assert "1323" in text


@pytest.mark.parametrize("message,route,contact", [
    ("กินวันละ 800 แคล ตอนนี้เจ็บหน้าอก หายใจไม่ออก", "emergency", "1669"),
    ("อยากทำร้ายตัวเอง จะกินวันละ 800 kcal", "self_harm", "1323"),
    ("ล้วงคอแล้วหายใจไม่ออก", "emergency", "1669"),
])
def test_urgent_risk_still_precedes_eating_copy(message, route, contact):
    actual, text = guardrails.safety_reply(guardrails.check(message))
    assert actual == route and contact in text


@pytest.mark.parametrize("message", [
    "ข้าวมันไก่ 600 แคลจริงไหม", "โค้กซีโร่ 0 แคล", "ควรลดวันละ 500 แคลไหม",
    "กินวันละ 1800 แคลได้ไหม",
])
def test_food_facts_and_ordinary_deficits_are_not_newly_blocked(message):
    assert guardrails.Flag.DISORDERED_EATING not in guardrails.check(message).flags


@pytest.mark.parametrize("message", ["กินวันละ 800 kcal ขอเมนู", "เพิ่งล้วงคอไป"])
@pytest.mark.parametrize("tool", ["calc_nutrition_targets", "suggest_day_menu"])
def test_both_personal_tools_remain_blocked(message, tool):
    profile = ProfileInput(sex="male", birth_year=1996, birth_month=1, height_cm=175,
        weight_kg=70, activity_level="moderate", goal="cut")
    result = chat._execute_tool(None, profile, tool, {}, guardrails.check(message))
    assert result["error"] == "safety_boundary"
    assert "meals" not in result and "energy_target_kcal" not in result
