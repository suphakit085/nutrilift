"""Behavioral regressions and unseen paraphrases from functional prompt testing."""

from types import SimpleNamespace

import pytest
from google.genai import types

from app.services import chat, guardrails, prompts
from app.services.answer_validation import (
    answer_issues,
    format_issue,
    requested_format,
    without_target_citations,
)
from app.services.creatine_facts import creatine_necessity_reply
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from app.services.personal_context import missing_personal_context_reply
from app.services.request_constraints import incomplete_pairing_reply
from app.services.target_explanation import requests_target_explanation


def adult(**changes):
    return ProfileInput(
        **{
            "sex": "male",
            "birth_year": 2000,
            "height_cm": 175,
            "weight_kg": 70,
            "activity_level": "moderate",
            "goal": "maintain",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "message",
    [
        "โปรตีนช่วยผู้ที่ฝึกเวทอย่างไร สรุปเฉพาะหลักการ ไม่ต้องคำนวณให้ผม",
        "ผมอยากรู้หลักฐานเรื่องโปรตีน ไม่ได้ขอให้คำนวณแคลอรี",
        "อธิบายโปรตีนให้ฉันฟัง อย่าคำนวณเป้าหมาย",
        "ขอหลักการ ไม่ขอคำนวณพลังงานของผม",
    ],
)
def test_negated_calculation_does_not_require_profile(message):
    assert missing_personal_context_reply(message, [], has_profile=False) is None
    assert not chat._personal_context_requested(message)
    assert not requests_target_explanation(message)


@pytest.mark.parametrize(
    "message",
    [
        "ไม่ต้องจัดเมนู แต่ช่วยคำนวณโปรตีนให้ผม",
        "ผมยังไม่ได้คำนวณโปรตีนต่อวัน ต้องกินเท่าไร",
        "ไม่ต้องคำนวณเมนู แต่คำนวณโปรตีนของผมต่อวันให้หน่อย",
    ],
)
def test_later_affirmative_request_is_not_masked(message):
    assert missing_personal_context_reply(message, [], has_profile=False)


@pytest.mark.parametrize(
    "message",
    [
        "เวย์ทานคู่กับ ... ได้ไหมครับ",
        "ผงโปรตีนผสมกับ ___ ดีไหม",
        "เครื่องดื่มกินกับได้ไหม",
        "อาหารเสริมทานร่วมกับ … ได้หรือไม่",
    ],
)
def test_incomplete_pairing_clarifies_without_assuming_a_partner(message):
    assert "อะไร" in incomplete_pairing_reply(message)


@pytest.mark.parametrize(
    "message",
    [
        "เวย์กินคู่กับนมได้ไหม",
        "เวย์กินกับอะไรได้บ้าง",
        "เวย์กับนม...ดีไหม",
        "ฉันอยากกินโปรตีนเพิ่ม",
    ],
)
def test_answerable_pairing_does_not_trigger_placeholder_rule(message):
    assert incomplete_pairing_reply(message) is None


@pytest.mark.parametrize(
    "message",
    [
        "กังวลเรื่องค่าตรวจไต แต่อยากเพิ่มกล้าม",
        "ค่าการตรวจการทำงานของไตของฉันน่าห่วง ควร bulk ไหม",
        "worried about kidney function test results, calculate my protein",
        "ผลการตรวจเลือดออกแล้วช่วยอ่านให้ที",
    ],
)
def test_lab_wording_and_history_remain_medical(message):
    flags = guardrails.check(message)
    assert guardrails.Flag.MEDICAL in flags.flags
    assert not guardrails.personalization_allowed(flags)
    assert (
        guardrails.Flag.MEDICAL
        in guardrails.check_history([{"role": "user", "content": message}]).flags
    )


@pytest.mark.parametrize(
    "message", ["อยากเล่นไตรเซปส์", "ตรวจฉลากโปรตีนให้หน่อย", "ค่าพลังงานของข้าว", "ตรวจคำตอบโปรตีน"]
)
def test_lab_matching_does_not_block_ordinary_food_queries(message):
    assert guardrails.Flag.MEDICAL not in guardrails.check(message).flags


@pytest.mark.parametrize(
    "message",
    [
        "แก้น้ำหนักเป็น 70 กก. ช่วยคำนวณเป้าหมายโปรตีนรักษาน้ำหนักให้ผม",
        "ช่วยคำนวณเป้าหมาย cut จากโปรไฟล์ให้ผม",
        "คำนวณพลังงานตามโปรไฟล์ของฉัน",
    ],
)
def test_personal_calculation_uses_structured_calculator_without_formula_request(message):
    assert requests_target_explanation(message)


def test_personal_targets_never_acquire_publication_citations():
    targets = calc_nutrition_targets(adult())
    raw = "- **โปรตีน:** 126 กรัม/วัน [S1]\n- หลักฐานทั่วไปเสนอ 1.4\u20132.0 กรัม/กก. [S2]"
    cleaned = without_target_citations(raw, targets)
    assert "[S1]" not in cleaned and "[S2]" in cleaned
    assert "126 กรัม/วัน" in cleaned
    assert without_target_citations(cleaned, targets) == cleaned
    assert without_target_citations(raw, None) == raw


def test_dose_prohibition_with_typo_reaches_evidence_bound_faq():
    passage = {
        "document_slug": "creatine",
        "label": "S1",
        "source_refs": ["source"],
        "content": "ไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสม",
    }
    message = "ครีเอตีนต้องโหลด้มั้ยคับ ขอหลักการสั้นๆไม่ต้องให้โดส"
    answer = creatine_necessity_reply(message, [passage])
    assert answer and "ไม่จำเป็นต้องโหลด" in answer and "[S1]" in answer
    assert "ไม่ได้พิสูจน์" in answer and not answer_issues(message, answer, [passage], use_rag=True)
    assert creatine_necessity_reply(message, []) is None
    assert "ไม่แจกขนาดใช้" in prompts.answer_focus_th(message)


def test_percentages_must_come_from_cited_passage_not_another_card():
    sources = [
        {"label": "S1", "content": "ช่วง cut ลด 0.5-1% ต่อสัปดาห์"},
        {"label": "S2", "content": "ช่วง bulk กล่าวถึง 0.25-0.5% ต่อสัปดาห์"},
    ]
    assert answer_issues(
        "ติดตาม bulk อย่างไร", "น้ำหนักเพิ่ม 0.25-0.5% ต่อสัปดาห์ [S1]", sources, use_rag=True
    )
    assert not answer_issues(
        "ติดตาม bulk อย่างไร", "น้ำหนักเพิ่ม 0.25-0.5% ต่อสัปดาห์ [S2]", sources, use_rag=True
    )


def test_explicit_dose_exclusion_is_enforced_on_output():
    assert answer_issues("ครีเอทีนไม่ต้องบอกโดส", "กิน 3-5 กรัมต่อวัน", [], use_rag=False)
    assert not answer_issues("ครีเอทีนกี่กรัมต่อวัน", "กิน 3-5 กรัมต่อวัน", [], use_rag=False)


@pytest.mark.parametrize(
    "message,valid,invalid",
    [
        (
            "ตาราง Markdown เท่านั้น",
            "| A | B |\n| --- | --- |\n| ก | ข |",
            "บทนำ\n| A | B |\n| --- | --- |\n| ก | ข |",
        ),
        ("JSON object เท่านั้น", '{"answer":"ก","caveat":"ข"}', '```json\n{"a":1}\n```'),
        ("bullet จำนวน 3 ข้อเท่านั้น", "- ก\n- ข\n- ค", "เกริ่น\n- ก\n- ข\n- ค"),
    ],
)
def test_format_is_checked_before_display(message, valid, invalid):
    spec = requested_format(message)
    assert spec and format_issue(valid, spec) is None and format_issue(invalid, spec)


def fake_provider(monkeypatch, answers):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        text = answers[min(len(calls) - 1, len(answers) - 1)]
        yield types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part.from_text(text=text)]),
                    finish_reason="STOP",
                )
            ]
        )

    monkeypatch.setattr(
        chat,
        "get_client",
        lambda: SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate)),
    )
    monkeypatch.setattr(chat.retrieval, "search", lambda *args: [])
    return calls


def test_bad_format_is_repaired_before_any_draft_reaches_stream(monkeypatch):
    table = "| A | B |\n| --- | --- |\n| เวย์ | โปรตีน |"
    calls = fake_provider(monkeypatch, ["บทนำที่ห้าม\n" + table, table])
    events = list(
        chat.stream_chat(
            SimpleNamespace(commit=lambda: None),
            user_message="เปรียบเทียบโปรตีนเป็นตาราง Markdown เท่านั้น",
        )
    )
    assert len(calls) == 2 and events[-1]["type"] == "done"
    assert events[-1]["text"] == table
    assert "".join(e["text"] for e in events if e["type"] == "delta") == table
    assert events[-1]["answer_validation"]["repairs"] == 1


def test_repeated_invalid_output_fails_closed_without_loop(monkeypatch):
    calls = fake_provider(monkeypatch, ["บทนำ\n| A | B |\n| --- | --- |\n| ก | ข |"])
    events = list(
        chat.stream_chat(
            SimpleNamespace(commit=lambda: None), user_message="ขอข้อมูลโปรตีนเป็นตาราง Markdown เท่านั้น"
        )
    )
    assert len(calls) == 2 and events[-1]["code"] == "answer_validation_failed"
    assert not any(e["type"] == "delta" for e in events)


def test_medical_scope_precedes_calculator_and_formatting(monkeypatch):
    fake_provider(monkeypatch, ["ต้องไม่ถูกเรียก"])
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: pytest.fail("medical retrieval"))
    monkeypatch.setattr(
        chat, "calc_nutrition_targets", lambda *_: pytest.fail("medical calculator")
    )
    done = chat.collect_answer(
        SimpleNamespace(commit=lambda: None),
        user_message="กังวลค่าตรวจไต ขอคำนวณโปรตีนตามโปรไฟล์เป็น JSON เท่านั้น",
    )
    assert done["model"] == "rule:medical_scope" and "บันทึกและคำนวณ" not in done["text"]
