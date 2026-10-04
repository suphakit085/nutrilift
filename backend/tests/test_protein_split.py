from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.services import chat, guardrails
from app.services.nutrition import ProfileInput
from app.services.protein_split import equal_protein_split_reply


def adult():
    return ProfileInput(
        sex="male", birth_year=2005, birth_month=1, height_cm=178, weight_kg=69.3,
        activity_level="moderate", goal="bulk",
    )


@pytest.mark.parametrize("question", [
    "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อ มื้อละกี่กรัมครับ",
    "ถ้าแบ่งโปรตีน125gเป็น5มื้อเท่า ๆ กัน จะได้มื้อละกี่กรัม",
    "split 125 g protein into 5 meals equally",
])
def test_explicit_total_is_divided_without_unsolicited_timing(question):
    reply = equal_protein_split_reply(question, daily_protein_g=150)
    assert "125 ÷ 5 = **25 กรัมต่อมื้อ**" in reply
    assert "ชั่วโมง" not in reply and "ISSN" not in reply and "[S" not in reply


def test_fractional_total_and_repeating_result_are_rounded_honestly():
    assert "25.1 กรัมต่อมื้อ" in equal_protein_split_reply("แบ่งโปรตีน 125.5 กรัมเป็น 5 มื้อ")
    assert "ประมาณ 33.33 กรัมต่อมื้อ" in equal_protein_split_reply("แบ่งโปรตีน 100 กรัมเป็น 3 มื้อ")


def test_original_followup_uses_known_target():
    reply = equal_protein_split_reply(
        "ถ้าแบ่งโปรตีนตามเป้าข้างบนเป็น 5 มื้อ มื้อละกี่กรัมครับ", daily_protein_g=125,
    )
    assert "125 ÷ 5 = **25 กรัมต่อมื้อ**" in reply


def test_unknown_target_asks_for_total_instead_of_inventing_it():
    reply = equal_protein_split_reply("แบ่งโปรตีนตามเป้าเป็น 5 มื้อ")
    assert "รวมต่อวันของคุณกี่กรัม" in reply and "25" not in reply


@pytest.mark.parametrize("history", [
    [{"role": "user", "content": "แบ่งโปรตีน 150 กรัมเป็น 3 มื้อ"}],
    [{"role": "assistant", "content": "สารอาหารหลักที่แนะนำต่อวัน:\n- **โปรตีน:** 150 กรัม"}],
    [{"role": "user", "content": "ผมตั้งเป้าโปรตีน 150 กรัมต่อวัน"}],
])
def test_clear_conversation_total_overrides_saved_profile(history):
    reply = equal_protein_split_reply(
        "แบ่งโปรตีนตามเป้าข้างบนเป็น 5 มื้อ", daily_protein_g=125, history=history,
    )
    assert "150 ÷ 5 = **30 กรัมต่อมื้อ**" in reply


def test_incidental_food_amount_is_not_a_daily_target():
    reply = equal_protein_split_reply(
        "แบ่งโปรตีนตามเป้าเป็น 5 มื้อ", daily_protein_g=125,
        history=[{"role": "assistant", "content": "ข้าวสวยมีโปรตีน 3.9 กรัม"}],
    )
    assert "125 ÷ 5" in reply


@pytest.mark.parametrize("prior", [
    "โปรตีน 120 กรัมต่อวันหรือโปรตีน 150 กรัมต่อวัน",
    "ผมไม่เอาโปรตีน 150 กรัมต่อวัน",
    "สมมติว่ามีคนอื่นกินโปรตีน 150 กรัมต่อวัน",
])
def test_uncertain_prior_daily_totals_are_not_replaced_with_profile_guess(prior):
    assert equal_protein_split_reply(
        "แบ่งโปรตีนตามข้างบนเป็น 5 มื้อ", daily_protein_g=125,
        history=[{"role": "user", "content": prior}],
    ) is None


@pytest.mark.parametrize("question", [
    "แบ่งโปรตีน 125 กรัมเป็น 0 มื้อ", "แบ่งโปรตีน 125 กรัมเป็น -5 มื้อ",
    "แบ่งโปรตีน 125 กรัมเป็น 2.5 มื้อ", "แบ่งโปรตีน -125 กรัมเป็น 5 มื้อ",
    "แบ่งโปรตีน 125 หรือ 150 กรัมเป็น 5 มื้อ",
    "แบ่งโปรตีน 125 กรัมเป็น 3 หรือ 5 มื้อ", "แบ่งโปรตีนมื้อละ 25 กรัมเป็น 5 มื้อ",
    "แบ่งโปรตีน 25 กรัมต่อมื้อเป็น 5 มื้อ", "แบ่งโปรตีน 1.8 g/kg เป็น 5 มื้อ",
    "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อ ควรห่างกี่ชั่วโมง",
    "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อดีไหม", "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อจัดเมนูให้ด้วย",
    "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อแล้วคาร์บล่ะ", "โปรตีนมื้อละ 25 กรัมดูดซึมหมดไหม",
    "แบ่งโปรตีนเป็น 5 มื้อ", "แบ่งไก่ 125 กรัมเป็น 5 มื้อ",
])
def test_ambiguous_invalid_or_additional_questions_fall_through(question):
    assert equal_protein_split_reply(question, daily_protein_g=125) is None


def test_stream_followup_bypasses_model_and_preserves_profile(monkeypatch):
    def forbidden():
        pytest.fail("Simple division must not be rewritten by the model")

    monkeypatch.setattr(chat, "get_client", forbidden)
    saved = adult()
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    done = list(chat.stream_chat(
        db, profile=saved,
        user_message="ถ้าแบ่งโปรตีนตามเป้าข้างบนเป็น 5 มื้อ มื้อละกี่กรัมครับ",
        history=[{"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ยังไม่แก้โปรไฟล์"}],
        use_rag=False,
    ))[-1]
    assert done["model"] == "rule:protein_split"
    assert "125 ÷ 5 = **25 กรัมต่อมื้อ**" in done["text"]
    assert done["citations"] == [] and done["tool_calls"] == []
    assert done["usage"]["total_tokens"] == 0 and saved.goal == "bulk"


@pytest.mark.parametrize("profile,question,flags", [
    (adult(), "ผมเป็นโรคไต แบ่งโปรตีน 125 กรัมเป็น 5 มื้อ", None),
    (replace(adult(), birth_year=2012), "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อ", None),
    (adult(), "แบ่งโปรตีน 125 กรัมเป็น 5 มื้อ", [guardrails.Flag.MEDICAL.value]),
])
def test_safety_routes_take_priority_over_division(monkeypatch, profile, question, flags):
    def forbidden():
        pytest.fail("Medical and underage guard must not need an LLM")

    monkeypatch.setattr(chat, "get_client", forbidden)
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    done = list(chat.stream_chat(
        db, profile=profile, user_message=question, use_rag=False,
        persistent_safety_flags=flags,
    ))[-1]
    assert done["model"] != "rule:protein_split"
    assert "25 กรัมต่อมื้อ" not in done["text"]
