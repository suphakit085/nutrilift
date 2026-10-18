"""UAT Q1: retain research sources and explain real personal target operands."""

from types import SimpleNamespace

import pytest
from google.genai import types

from app.api.chat import turn_events
from app.services import chat
from app.services.nutrition import ACTIVITY_FACTORS, ProfileInput, calc_nutrition_targets
from app.services.target_explanation import (
    ISSN_PROTEIN_URL,
    MIFFLIN_URL,
    explicit_target_explanation_reply,
    requests_target_explanation,
)
from tests.test_chat_stream import CONV_ID, FakeSession, messages

QUESTION = "จากโปรไฟล์ตอนนี้ ฉันควรกินพลังงานและโปรตีนวันละเท่าไร ใช้สูตรอะไร ขอแหล่งอ้างอิงด้วย"
PASSAGES = [{"label": "S1"}, {"label": "S2"}]


def adult(**changes):
    return ProfileInput(**{
        "sex": "male", "birth_year": 2000, "birth_month": 1,
        "height_cm": 175, "weight_kg": 70, "activity_level": "moderate",
        "goal": "maintain", **changes,
    })


@pytest.mark.parametrize("separator", ["\n", "\n- ", "\n2. ", ". ", "; ", "\n\n"])
@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_paragraph_preserves_research_source(separator, reverse):
    policy = "พลังงานเป้าหมายจากโปรไฟล์ 2587 kcal [S2]"
    study = "โปรตีนสำหรับผู้ฝึกออกกำลังกายอยู่ในช่วง 1.4\u20132.0 กรัม/กก./วัน [S1]"
    raw = separator.join([study, policy] if reverse else [policy, study])
    cleaned = chat.clean_answer(raw, PASSAGES)
    assert study in cleaned
    assert "2587 kcal" in cleaned and "[S2]" not in cleaned
    assert chat.cited_only(cleaned, PASSAGES) == [PASSAGES[0]]
    assert chat.clean_answer(cleaned, PASSAGES) == cleaned


def test_original_uncited_calculation_line_does_not_erase_next_research_citation():
    raw = ("พลังงานเป้าหมายจากโปรไฟล์ 2587 kcal\n"
           "- โปรตีนสำหรับผู้ฝึกออกกำลังกายอยู่ในช่วง 1.4\u20132.0 กรัม/กก./วัน [S1]")
    assert chat.clean_answer(raw, PASSAGES) == raw


def test_multiple_markers_after_policy_and_markdown_links():
    raw = ("พลังงานเป้าหมาย 2587 kcal [S1][s2]\n"
           "หลักฐานโปรตีน [s1; S2; S9] [เอกสาร](https://example.com)")
    result = chat.clean_answer(raw, PASSAGES)
    assert result.startswith("พลังงานเป้าหมาย 2587 kcal \n")
    assert "หลักฐานโปรตีน [S1, S2]" in result
    assert "[เอกสาร](https://example.com)" in result and "S9" not in result


def test_research_claim_can_mention_energy_target_without_becoming_a_calculator_result():
    raw = "บททบทวนอภิปรายการปรับพลังงานเป้าหมายระหว่างการเตรียมแข่งขัน [S1]"
    assert chat.clean_answer(raw, PASSAGES) == raw


@pytest.mark.parametrize("claim,keep", [
    ("พลังงานเป้าหมาย: 2587 kcal", False),
    ("พลังงานเป้าหมายจากโปรไฟล์ 2587 kcal", False),
    ("หลักฐานโปรตีนสำหรับผู้ใหญ่ที่ออกกำลังกาย", True),
])
def test_standalone_marker_line_still_belongs_to_preceding_claim(claim, keep):
    result = chat.clean_answer(claim + "\n[S1]", PASSAGES)
    assert ("[S1]" in result) is keep


@pytest.mark.parametrize("question", [
    QUESTION,
    "ช่วยสรุปเป้าพลังงานตามโปรไฟล์ พร้อมสูตรและที่มา",
    "โปรไฟล์นี้คำนวณพลังงานอย่างไร",
    "ทำไมเป้าหมายโปรตีนของผมเป็นตัวเลขนี้",
    "ผมควรกินโปรตีนวันละเท่าไหร่ ขออ้างอิง",
    "Explain my calorie and protein targets with formula and references",
    "คํานวณพลังงานตามโปรไฟล์ยังไงครับ",
])
def test_explicit_target_method_questions_are_recognized(question):
    assert requests_target_explanation(question)


@pytest.mark.parametrize("question", [
    "สรุปงานวิจัยเรื่องโปรตีน", "หลักฐานครีเอทีนสำหรับผมมีอะไรบ้าง",
    "ช่วยสรุปหลักฐานโปรตีนตามโปรไฟล์", "ตามโปรไฟล์ช่วยจัดเมนูพร้อมอ้างอิง",
    "ขอเป้าพลังงานตามโปรไฟล์พร้อมวิธีแบ่ง 3 มื้อ",
    "เปรียบเทียบเป้าพลังงานของผมกับงานวิจัย", "ถ้าผมหนัก 90 กก ควรใช้สูตรอะไร",
    "พลังงานจากข้าว 180 กรัมใช้สูตรอะไร", "ตามโปรไฟล์วันนี้กินถึงเป้าหรือยัง",
    "เป้าหมายโปรตีนตามโปรไฟล์", "Why is my creatine dose 3 grams?",
    "ผมอยากรู้หลักฐานเรื่องพลังงานกับการเพิ่มกล้ามเนื้อ",
    "ผมขอสูตรพลังงานจากโปรตีนและไขมัน 1 กรัม",
    "ผมอยากทราบงานวิจัยว่าพลังงานขาดดุลส่งผลอย่างไร",
    "เป้าพลังงานตามโปรไฟล์และครีเอทีนควรใช้เท่าไร ขออ้างอิง",
])
def test_other_tasks_are_not_replaced_by_a_target_template(question):
    assert not requests_target_explanation(question)


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("goal", ["cut", "maintain", "bulk"])
@pytest.mark.parametrize("level", list(ACTIVITY_FACTORS))
def test_explanation_uses_actual_formula_and_rounding_not_a_fixed_uat_answer(sex, goal, level):
    profile = adult(sex=sex, goal=goal, activity_level=level, weight_kg=70.125, height_cm=175.25)
    targets = calc_nutrition_targets(profile)
    result = explicit_target_explanation_reply(QUESTION, targets)
    details = targets["calculation_details"]
    # Independently reconstruct the existing equations using raw profile input.
    bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age()
    bmr += 5 if sex == "male" else -161
    tdee = bmr * ACTIVITY_FACTORS[level]
    coefficient = 2 if goal == "cut" else 1.8
    adjustment = {"cut": -.175, "maintain": 0, "bulk": .125}[goal]
    assert details["bmr_unrounded_kcal"] == pytest.approx(bmr)
    assert details["tdee_unrounded_kcal"] == pytest.approx(tdee)
    assert targets["energy_target_kcal"] == round(tdee * (1 + adjustment))
    assert details["protein_g_per_kg"] == coefficient
    assert targets["macros"]["protein_g"] == round(70.125 * coefficient)
    assert "70.125" in result and "175.25" in result
    assert f"≈ {targets['energy_target_kcal']}" in result
    assert f"70.125 \u00d7 {coefficient:g}" in result
    assert MIFFLIN_URL in result and ISSN_PROTEIN_URL in result
    assert "การเลือกของเครื่องคำนวณโครงการ" in result
    assert "1.4\u20132.0" in result and "[S" not in result
    assert ("+ 5 ≈" if sex == "male" else "\u2212 161 ≈") in result
    assert all(w in result for w in targets["warnings"])


def test_original_uat_numbers_have_auditable_protein_arithmetic_and_links():
    targets = calc_nutrition_targets(adult())
    reply = explicit_target_explanation_reply(QUESTION, targets)
    assert "70 \u00d7 1.8 ≈ 126" in reply
    assert "2587 กิโลแคลอรี/วัน" in reply
    assert "Jäger" in reply and "Mifflin" in reply
    assert "अ" not in reply


def test_body_fat_formula_never_borrows_the_mifflin_reference():
    targets = calc_nutrition_targets(adult(body_fat_pct=17.25))
    result = explicit_target_explanation_reply(QUESTION, targets)
    assert "Katch-McArdle" in result and "21.6" in result and "17.25" in result
    assert "ยังไม่มีลิงก์เอกสารต้นฉบับ" in result and MIFFLIN_URL not in result
    assert ISSN_PROTEIN_URL in result
    assert targets["calculation_details"]["lean_mass_kg"] == pytest.approx(70 * .8275)


def test_legacy_payload_is_not_given_invented_operands():
    targets = calc_nutrition_targets(adult())
    targets.pop("calculation_details")
    assert explicit_target_explanation_reply(QUESTION, targets) is None


def no_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Target provenance must not depend on model completion")
    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", lambda *args: [])


@pytest.mark.parametrize("rag", [True, False])
def test_stream_explains_targets_without_inventing_retrieval_labels(monkeypatch, rag):
    no_provider(monkeypatch)
    events = list(chat.stream_chat(SimpleNamespace(commit=lambda: None),
        user_message=QUESTION, profile=adult(), use_rag=rag))
    result = events[-1]
    assert [e["type"] for e in events] == ["sources", "delta", "done"]
    assert result["model"] == "rule:target_explanation"
    assert result["usage"]["total_tokens"] == 0 and result["citations"] == []
    assert MIFFLIN_URL in result["text"] and "70 \u00d7 1.8 ≈ 126" in result["text"]


def test_target_explanation_does_not_depend_on_retrieval_availability(monkeypatch):
    no_provider(monkeypatch)
    def unavailable(*args, **kwargs):
        pytest.fail("Known calculator sources do not require retrieval")
    monkeypatch.setattr(chat.retrieval, "search", unavailable)
    events = list(chat.stream_chat(SimpleNamespace(commit=lambda: None),
        user_message=QUESTION, profile=adult()))
    result = events[-1]
    assert events[0]["retrieval_status"] == "not_required"
    assert result["model"] == "rule:target_explanation" and MIFFLIN_URL in result["text"]


def test_history_uses_effective_goal_and_warns_without_changing_saved_profile(monkeypatch):
    no_provider(monkeypatch)
    saved = adult(goal="bulk")
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None),
        user_message=QUESTION, profile=saved,
        history=[{"role": "user", "content": "เปลี่ยนเป้าหมายชั่วคราวเป็นรักษาน้ำหนัก"}])
    assert result["model"] == "rule:target_explanation"
    assert "รักษาน้ำหนัก" in result["text"] and "ชั่วคราว" in result["text"]
    assert "70 \u00d7 1.8 ≈ 126" in result["text"] and saved.goal == "bulk"


def test_underweight_uses_actual_maintenance_with_warning_before_numbers(monkeypatch):
    no_provider(monkeypatch)
    profile = adult(weight_kg=50, height_cm=180, goal="cut")
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None),
        user_message=QUESTION, profile=profile)
    text = result["text"]
    assert result["model"] == "rule:target_explanation"
    assert "รักษาน้ำหนัก" in text and "50 \u00d7 1.8 ≈ 90" in text
    assert text.index("BMI") < text.index("- พลังงานเป้าหมาย")
    assert profile.goal == "cut"


@pytest.mark.parametrize("message,profile", [
    ("ผมเป็นโรคไต ขอสูตรพลังงานและโปรตีนจากโปรไฟล์พร้อมอ้างอิง", adult()),
    ("ตั้งครรภ์ ขอสูตรพลังงานตามโปรไฟล์", adult(sex="female")),
    (QUESTION, adult(birth_year=2012)),
    ("ขอพลังงานวันละ 800 แคลตามโปรไฟล์พร้อมสูตร", adult()),
])
def test_safety_precedes_target_explanation(monkeypatch, message, profile):
    no_provider(monkeypatch)
    result = chat.collect_answer(SimpleNamespace(commit=lambda: None),
        user_message=message, profile=profile)
    assert result["model"] != "rule:target_explanation"
    assert MIFFLIN_URL not in result["text"] and "calculation_details" not in result["text"]


def test_target_explanation_and_links_survive_persisted_history(monkeypatch):
    import json
    no_provider(monkeypatch)
    session = FakeSession()
    events = list(turn_events(lambda: session, conversation_id=CONV_ID,
        user_message=QUESTION, profile=adult(), history=[], use_rag=True,
        is_first_message=True, stream=chat.stream_chat))
    done = json.loads(events[-1]["data"])
    stored = messages(session, "assistant")[0]
    assert stored.content == done["text"]
    assert MIFFLIN_URL in stored.content and ISSN_PROTEIN_URL in stored.content
    assert stored.citations == []


def test_model_mixed_paragraph_is_cleaned_in_stream_and_saved_turn(monkeypatch):
    import json
    raw = ("พลังงานเป้าหมายจากโปรไฟล์ 2587 kcal [S2]\n"
           "- หลักฐานโปรตีนจากงานวิจัย [S1]")
    passage = SimpleNamespace(as_citation=lambda: {"label": "S1"},
                             as_dict=lambda: {"label": "S1", "title": "โปรตีน",
                                              "content": "หลักฐานโปรตีน"})
    monkeypatch.setattr(chat.retrieval, "search", lambda *args: [passage])
    chunk = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part.from_text(text=raw)]), finish_reason="STOP")])
    client = SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=lambda **kw: iter([chunk])))
    monkeypatch.setattr(chat, "get_client", lambda: client)
    session = FakeSession()
    # General research question remains a model/RAG response, not the new route.
    events = list(turn_events(lambda: session, conversation_id=CONV_ID,
        user_message="ช่วยอธิบายหลักฐานโปรตีนทั่วไป", profile=None, history=[], use_rag=True,
        is_first_message=True, stream=chat.stream_chat))
    done = json.loads(events[-1]["data"])
    assert "[S1]" in done["text"] and "[S2]" not in done["text"]
    assert done["citations"] == [{"label": "S1"}]
    assert messages(session, "assistant")[0].citations == done["citations"]
