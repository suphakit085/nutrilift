"""Execution tests; language generalization is tested separately with real models."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types
from pydantic import ValidationError

from app.services import chat
from app.services.answer_review import (
    EvidenceClaimCheck,
    EvidenceReview,
    draft_units,
    review_answer,
    source_paragraphs,
)
from app.services.answer_validation import answer_issues, format_issue, without_target_citations
from app.services.creatine_facts import creatine_necessity_reply
from app.services.menu_context import conversation_profile
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from app.services.request_understanding import (
    RequestUnderstanding,
    interpret_request,
    validate_grounding,
)


def adult(**changes):
    return ProfileInput(
        **(
            {
                "sex": "male",
                "birth_year": 2000,
                "height_cm": 175,
                "weight_kg": 90,
                "activity_level": "moderate",
                "goal": "maintain",
            }
            | changes
        )
    )


def understood(**changes):
    return RequestUnderstanding.model_validate(
        {
            "task": "knowledge",
            "personal_context": False,
            "medical_self_context": False,
            "exclusion_phrases": [],
            "blocked_actions": [],
            "missing_information": None,
            "weight_kg": None,
            "height_cm": None,
            "goal": None,
            "goal_quote": None,
            "goal_user_turn": None,
            "output_format": "text",
            "bullet_count": None,
            "topic": "other",
            "evidence_only": False,
        }
        | changes
    )


def ledger(*kinds, support=None, issues=None):
    support = support or {}
    return json.dumps(
        {
            "units": [
                {"unit": i, "kind": k, "names_source": False, "support": support.get(i, [])}
                for i, k in enumerate(kinds)
            ],
            "issues": issues or [],
        },
        ensure_ascii=False,
    )


def client_for(*answers):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        answer = answers[min(len(calls) - 1, len(answers) - 1)]
        yield types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part.from_text(text=answer)]),
                    finish_reason="STOP",
                )
            ]
        )

    return SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate)), calls


def test_schema_and_user_only_grounding():
    state = understood(
        task="calculate_targets",
        personal_context=True,
        weight_kg={"value": 77, "user_turn": 1, "quote": "น้ำหนักที่ถูกคือ 77 กก."},
    )
    client, calls = client_for(state.model_dump_json())
    result, _ = interpret_request(
        client,
        model="test",
        message="น้ำหนักที่ถูกคือ 77 กก.",
        history=[
            {"role": "user", "content": "เดิม 85 กก."},
            {"role": "assistant", "content": "หนัก 50 กก."},
        ],
        profile=adult(),
    )
    assert result.weight_kg.value == 77
    assert calls[0]["config"].response_json_schema == RequestUnderstanding.model_json_schema()
    payload = json.loads(calls[0]["contents"][0].parts[0].text)
    assert payload["user_turns"] == ["เดิม 85 กก.", "น้ำหนักที่ถูกคือ 77 กก."]


@pytest.mark.parametrize(
    "measurement",
    [
        {"value": 70, "user_turn": 0, "quote": "หนัก 70 กก."},
        {"value": 70, "user_turn": 9, "quote": "หนัก 77 กก."},
        {"value": 70, "user_turn": 0, "quote": "หนัก 77 กก."},
    ],
)
def test_invented_quote_turn_or_value_is_rejected(measurement):
    with pytest.raises(ValueError):
        validate_grounding(understood(weight_kg=measurement), ["หนัก 77 กก."])


@pytest.mark.parametrize(
    "changes",
    [
        {"task": "calculate_targets", "blocked_actions": ["calculate"]},
        {"task": "plan_menu", "blocked_actions": ["menu"]},
        {"task": "clarify"},
        {"output_format": "bullets"},
        {"goal": "cut", "goal_quote": "ลดไขมัน", "goal_user_turn": 2},
    ],
)
def test_incomplete_or_contradictory_state_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_grounding(understood(**changes), ["ขอข้อมูลทั่วไป"])


def test_unknown_fields_and_nonfinite_measurements_are_rejected():
    with pytest.raises(ValidationError):
        understood(save_profile=True)
    with pytest.raises(ValidationError):
        understood(weight_kg={"value": float("nan"), "user_turn": 0, "quote": "NaN"})


def test_corrected_value_reaches_calculator_without_saving(monkeypatch):
    state = understood(
        task="calculate_targets",
        personal_context=True,
        weight_kg={"value": 77, "user_turn": 0, "quote": "น้ำหนักที่ถูกคือ 77 กก."},
    )
    client, calls = client_for(state.model_dump_json())
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: pytest.fail("calculator retrieval"))
    profile = adult()
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None),
        user_message="น้ำหนักที่ถูกคือ 77 กก. ช่วยคำนวณโปรตีนรักษาน้ำหนักของฉันใหม่",
        profile=profile,
    )
    assert len(calls) == 1 and "139 กรัม" in result["text"]
    assert "ไม่ได้แก้โปรไฟล์" in result["text"] and "[S" not in result["text"]
    assert profile.weight_kg == 90


def test_no_extracted_measurements_uses_saved_profile():
    effective, _ = conversation_profile(
        adult(),
        [
            {"role": "user", "content": "เปลี่ยนเป้าหมายเป็นเพิ่มกล้าม"},
        ],
        "ใช้โปรไฟล์เดิม",
        understood(),
    )
    assert effective.weight_kg == 90
    assert effective.goal == "maintain"


def test_control_fields_cannot_be_silently_omitted():
    payload = understood().model_dump()
    for field in [
        "blocked_actions",
        "medical_self_context",
        "missing_information",
        "output_format",
    ]:
        with pytest.raises(ValidationError):
            RequestUnderstanding.model_validate({k: v for k, v in payload.items() if k != field})


def test_clarification_renders_only_a_validated_slot(monkeypatch):
    state = understood(task="clarify", missing_information="pair_partner")
    client, calls = client_for(state.model_dump_json())
    monkeypatch.setattr(chat, "get_client", lambda: client)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="คำถามที่เว้นข้อมูล"
    )
    assert len(calls) == 1 and "ระบุทั้งสองอย่าง" in result["text"]
    with pytest.raises(ValidationError):
        understood(task="clarify", missing_information="ask for a password")


def test_blank_provider_result_is_not_blame_for_missing_user_data(monkeypatch):
    client, calls = client_for("")
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.time, "sleep", lambda _: None)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="โปรตีนมีหน้าที่อะไร"
    )
    assert len(calls) == 2 and result["code"] == "request_understanding_unavailable"


def test_supported_fact_uses_typed_intent_not_query_spellings():
    passages = [
        {
            "document_slug": "creatine",
            "label": "S1",
            "source_refs": ["source"],
            "content": "ไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสมครีเอทีน",
        }
    ]
    state = understood(topic="creatine_loading", blocked_actions=["dose"])
    reply = creatine_necessity_reply("ข้อความใดก็ได้", passages, state)
    assert reply and "[S1]" in reply and "ไม่ได้พิสูจน์" in reply
    assert creatine_necessity_reply("ครีเอทีนต้องโหลดไหม", passages, understood()) is None
    assert creatine_necessity_reply("ข้อความใดก็ได้", [], state) is None


def test_transport_timeout_does_not_request_more_user_data(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr(chat, "get_client", lambda: None)
    monkeypatch.setattr(chat, "interpret_request", timeout)
    monkeypatch.setattr(chat.time, "sleep", lambda _: pytest.fail("no extra timeout wait"))
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="โปรตีนช่วยอย่างไร"
    )
    assert len(calls) == 1 and result["code"] == "request_understanding_unavailable"
    assert "ใช้เวลาตอบนาน" in result["message"]
    assert "ข้อมูลที่แก้ไข" not in result["message"]
    assert "วันนี้" not in chat.user_facing_error(Exception("429 quota"))


def test_evidence_review_receives_program_units_and_numbered_paragraphs():
    client, calls = client_for(ledger("research", support={0: ["S1.1"]}))
    verdict, _ = review_answer(
        client,
        model="test",
        question="หลักฐานคืออะไร",
        draft="ข้อความ [S1]",
        passages=[{"label": "S1", "content": "หลักฐานจริง"}, {"label": "S9", "content": "เรื่องอื่น"}],
        understanding=understood(),
    )
    payload = json.loads(calls[0]["contents"][0].parts[0].text)
    assert payload["draft_units"] == [{"unit": 0, "text": "ข้อความ [S1]", "labels": ["S1"]}]
    assert [p["id"] for p in payload["source_paragraphs"]] == ["S1.1", "S9.1"]
    assert calls[0]["config"].response_json_schema == EvidenceReview.model_json_schema()
    assert verdict.accepted and verdict.ledger[0]["support"] == ["S1.1"]


def test_units_split_json_leaves_and_label_boundaries():
    draft = json.dumps({"answer": "ก [S1] ข [S2, S3] ค", "caveat": "ง"}, ensure_ascii=False)
    assert [(u["text"], u["labels"]) for u in draft_units(draft)] == [
        ("ก [S1]", ["S1"]),
        ("ข [S2, S3]", ["S2", "S3"]),
        ("ค", []),
        ("ง", []),
    ]
    assert [u["text"] for u in draft_units("| A |\n| --- |\n\n* ข้อ")] == ["| A |", "* ข้อ"]
    assert source_paragraphs([{"label": "S2", "content": "หัวข้อ\n\nย่อหน้า"}]) == [
        {"id": "S2.1", "text": "หัวข้อ"},
        {"id": "S2.2", "text": "ย่อหน้า"},
    ]


PASSAGES = [
    {"label": "S1", "content": "บททบทวนปี 2023 พบว่าโปรตีนถั่วเหลืองใกล้เคียงเวย์"},
    {"label": "S2", "content": "ปริมาณโปรตีนรวมต่อวัน"},
]


@pytest.mark.parametrize(
    ("draft", "kind", "names_source", "support", "category"),
    [
        # A label on a sentence that its source does not state (PT10/VX03 class).
        ("ชั่งน้ำหนักเพื่อแยกกล้ามเนื้อ [S2]", "advice", False, [], "citation"),
        ("ชงคู่นมได้เพราะไม่มีข้อห้าม [S2]", "research", False, [], "citation"),
        # A research claim a source supports but that carries no label (PT22 class).
        ("บททบทวนปี 2023 ระบุว่าถั่วเหลืองใกล้เคียงเวย์", "research", True, ["S1.1"], "citation"),
        # A comparison no supplied paragraph states (PT20 class).
        ("เวย์ไม่ได้ดีกว่าอาหารหลัก", "research", False, [], "unsupported_fact"),
        # One supported label cannot carry another unsupported one.
        ("ข้อความ [S1, S2]", "research", False, ["S1.1"], "citation"),
    ],
)
def test_ledger_rejects_unsupported_or_unlabelled_evidence(
    draft, kind, names_source, support, category
):
    review = json.dumps(
        {
            "units": [{"unit": 0, "kind": kind, "names_source": names_source, "support": support}],
            "issues": [],
        },
        ensure_ascii=False,
    )
    client, _ = client_for(review)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted
    assert verdict.issues[0].category == category and verdict.issues[0].fragment == draft


@pytest.mark.parametrize(
    ("kind", "passages"),
    [("advice", PASSAGES), ("evidence_gap", PASSAGES), ("framing", PASSAGES), ("research", [])],
)
def test_ledger_accepts_unlabelled_non_evidence_and_sourceless_principles(kind, passages):
    not_a_claim = '{"sentences":[{"sentence":0,"evidence_or_effect_claim":false}]}'
    client, _ = client_for(ledger(kind), not_a_claim)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft="ติดตามการฝึกสม่ำเสมอ",
        passages=passages,
        understanding=understood(),
    )
    assert verdict.accepted


def test_sourceless_named_study_is_rejected():
    review = '{"units":[{"unit":0,"kind":"research","names_source":true,"support":[]}],"issues":[]}'
    client, _ = client_for(review)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft="งานวิจัยปี 2020 พบว่า",
        passages=[],
        understanding=understood(),
    )
    assert verdict.issues[0].category == "unsupported_fact"


def test_incomplete_ledger_is_retried_once_then_fails(monkeypatch):
    monkeypatch.setattr("app.services.answer_review.time.sleep", lambda _: None)
    client, calls = client_for('{"units":[],"issues":[]}')
    with pytest.raises(ValueError):
        review_answer(
            client,
            model="test",
            question="q",
            draft="ก\nข",
            passages=[],
            understanding=understood(),
        )
    assert len(calls) == 2


def test_invalid_state_stops_before_execution(monkeypatch):
    client, _ = client_for('{"task":"unknown"}')
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: pytest.fail("invalid state retrieval"))
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="ช่วยคิดใหม่", profile=adult()
    )
    assert result["code"] == "request_understanding_failed" and "text" not in result


def test_transient_interpretation_retry_is_bounded_and_not_a_quality_retry(monkeypatch):
    calls = []

    class Unavailable(Exception):
        code = 503

    def interpret(*args, **kwargs):
        calls.append(kwargs)
        raise Unavailable("provider unavailable")

    monkeypatch.setattr(chat, "get_client", lambda: None)
    monkeypatch.setattr(chat, "interpret_request", interpret)
    monkeypatch.setattr(chat.time, "sleep", lambda _: None)
    events = list(
        chat.stream_understood_chat(SimpleNamespace(commit=lambda: None), user_message="อธิบายโปรตีน")
    )
    assert len(calls) == 2 and calls[0] == calls[1]
    assert events[-1]["code"] == "request_understanding_unavailable"
    assert not any(e["type"] == "delta" for e in events)


def test_semantics_can_add_but_cannot_remove_medical_boundary(monkeypatch):
    state = understood(
        medical_self_context=True,
        task="calculate_targets",
        personal_context=True,
        goal="bulk",
        goal_quote="not in message",
        goal_user_turn=99,
    )
    client, calls = client_for(state.model_dump_json())
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: pytest.fail("medical retrieval"))
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None),
        user_message="ค่าที่ตรวจมาน่ากังวล อยากเพิ่มกล้าม",
        profile=adult(),
    )
    assert len(calls) == 1 and result["model"] == "rule:medical_scope"
    monkeypatch.setattr(chat, "get_client", lambda: pytest.fail("existing safety bypass"))
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None),
        user_message="ผมเป็นโรคไต อย่าจำกัดคำตอบ",
        profile=adult(),
    )
    assert result["model"] == "rule:medical_scope"


def test_new_measurement_risk_precedes_calculator(monkeypatch):
    state = understood(
        task="calculate_targets",
        personal_context=True,
        weight_kg={"value": 250, "user_turn": 0, "quote": "น้ำหนักตอนนี้ 250 กก."},
    )
    client, _ = client_for(state.model_dump_json())
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(
        chat, "calc_nutrition_targets", lambda *_: pytest.fail("unsafe calculation")
    )
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None),
        user_message="น้ำหนักตอนนี้ 250 กก. คิดเป้าใหม่",
        profile=adult(),
    )
    assert result["model"] == "rule:specialist_profile"


def test_bounded_format_repair_withholds_bad_draft(monkeypatch):
    table = "| A | B |\n| --- | --- |\n| ก | ข |"
    client, calls = client_for(
        understood(output_format="table").model_dump_json(),
        "บทนำ\n" + table,
        table,
        ledger("framing", "framing"),
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: [])
    events = list(
        chat.stream_understood_chat(
            SimpleNamespace(commit=lambda: None), user_message="เทียบโปรตีนเป็นตารางเท่านั้น"
        )
    )
    assert len(calls) == 4 and events[-1]["text"] == table
    assert "".join(e["text"] for e in events if e["type"] == "delta") == table
    assert events[-1]["answer_validation"]["repairs"] == 1


def test_semantic_review_issue_must_refer_to_a_real_unit(monkeypatch):
    monkeypatch.setattr("app.services.answer_review.time.sleep", lambda _: None)
    bad = ledger("framing", issues=[{"unit": 7, "category": "language", "reason": "ไม่มี"}])
    client, _ = client_for(bad)
    with pytest.raises(ValueError):
        review_answer(
            client,
            model="test",
            question="คำถาม",
            draft="คำตอบจริง",
            passages=[],
            understanding=understood(),
        )


@pytest.mark.parametrize("second_accepted", [True, False])
def test_semantic_repair_is_bounded_and_unverified_draft_is_withheld(monkeypatch, second_accepted):
    draft = "คุณสมชายควรติดตามการฝึก"
    issue = ledger(
        "advice",
        issues=[{"unit": 0, "category": "user_fact", "reason": "ไม่มีชื่อในข้อมูลผู้ใช้"}],
    )
    fixed = "ติดตามการฝึกตามหลักการทั่วไป" if second_accepted else draft
    verdict = ledger("advice") if second_accepted else issue
    client, calls = client_for(
        understood().model_dump_json(),
        draft,
        issue,
        fixed,
        verdict,
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_: [])
    events = list(
        chat.stream_understood_chat(
            SimpleNamespace(commit=lambda: None), user_message="ติดตามการฝึกอย่างไร"
        )
    )
    assert len(calls) == 5
    shown = "".join(e["text"] for e in events if e["type"] == "delta")
    if second_accepted:
        assert shown == fixed and events[-1]["type"] == "done"
    else:
        assert not shown and events[-1]["code"] == "answer_validation_failed"
    assert calls[2]["config"].response_json_schema == EvidenceReview.model_json_schema()


def test_format_dose_and_percentage_checks():
    assert format_issue('บทนำ {"a":1}', ("json", None))
    assert format_issue('{"a":1}', ("json", None)) is None
    assert answer_issues(
        "คำถาม",
        "กิน 3-5 กรัมต่อวัน",
        [],
        use_rag=False,
        understanding=understood(blocked_actions=["dose"]),
    )
    sources = [
        {"label": "S1", "content": "cut 0.5-1%"},
        {"label": "S2", "content": "bulk 0.25-0.5%"},
    ]
    assert answer_issues("คำถาม", "เพิ่ม 0.25-0.5% [S1]", sources, use_rag=True)
    assert not answer_issues("คำถาม", "เพิ่ม 0.25-0.5% [S2]", sources, use_rag=True)
    targets = calc_nutrition_targets(adult(weight_kg=70))
    assert without_target_citations("โปรตีน 126 กรัม [S1]", targets) == "โปรตีน 126 กรัม "


def test_ungrounded_interpretation_gets_one_correction_with_the_exact_error():
    bad = understood(
        task="calculate_targets", goal="cut", goal_quote="ลดเขียนไขมัน", goal_user_turn=0
    )
    good = bad.model_copy(update={"goal_quote": "ลดไขมัน"})
    client, calls = client_for(bad.model_dump_json(), good.model_dump_json())
    result, _ = interpret_request(
        client, model="test", message="ช่วยคำนวณเป้าหมายลดไขมันจากโปรไฟล์", history=[], profile=adult()
    )
    assert result.goal_quote == "ลดไขมัน" and len(calls) == 2
    correction = calls[1]["contents"][-1].parts[0].text
    assert "goal_quote" in correction and "user turn 0" in correction
    assert calls[1]["contents"][-2].role == "model"


def test_escaped_thai_quote_correction_names_the_escape_problem():
    bad = understood(goal="cut", goal_quote="ลดเขียนไขมัน", goal_user_turn=0).model_dump_json()
    assert "ลด" in bad
    escaped = json.dumps(json.loads(bad), ensure_ascii=True)
    good = understood(goal="cut", goal_quote="ลดไขมัน", goal_user_turn=0).model_dump_json()
    client, calls = client_for(escaped, good)
    interpret_request(client, model="test", message="ช่วยลดไขมัน", history=[], profile=None)
    assert "Unicode escape" in calls[1]["contents"][-1].parts[0].text


def test_second_ungrounded_interpretation_still_fails_closed():
    bad = understood(goal="bulk", goal_quote="ที่ลัดขลัด", goal_user_turn=0).model_dump_json()
    client, calls = client_for(bad, bad)
    with pytest.raises(ValueError):
        interpret_request(client, model="test", message="เพิ่มกล้าม", history=[], profile=None)
    assert len(calls) == 2


def test_exclusion_phrases_precede_and_scaffold_blocked_actions():
    schema = RequestUnderstanding.model_json_schema()
    order = list(schema["properties"])
    assert "exclusion_phrases" in schema["required"]
    assert order.index("exclusion_phrases") < order.index("blocked_actions")


def test_json_numbers_and_booleans_are_reviewed_as_claims():
    draft = json.dumps({"protein_g": 180, "safe_for_kidney": True, "note": "ก"}, ensure_ascii=False)
    assert [u["text"] for u in draft_units(draft)] == [
        "protein_g: 180",
        "safe_for_kidney: true",
        "ก",
    ]
    review = ledger(
        "framing",
        "framing",
        "framing",
        issues=[{"unit": 1, "category": "unsupported_fact", "reason": "ไม่มีแหล่งรับรองความปลอดภัย"}],
    )
    client, _ = client_for(review)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and verdict.issues[0].fragment == "safe_for_kidney: true"


def test_ledger_citing_a_nonexistent_paragraph_is_retried_then_fails(monkeypatch):
    monkeypatch.setattr("app.services.answer_review.time.sleep", lambda _: None)
    client, calls = client_for(ledger("research", support={0: ["S1.1", "S9.4"]}))
    with pytest.raises(ValueError):
        review_answer(
            client,
            model="test",
            question="q",
            draft="ข้อความ [S1]",
            passages=PASSAGES,
            understanding=understood(),
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"exclusion_phrases": ["ไม่ต้องคำนวณ"], "blocked_actions": ["calculate"]},
        {"exclusion_phrases": [], "blocked_actions": ["dose"]},
        {"exclusion_phrases": [""], "blocked_actions": []},
    ],
)
def test_exclusions_must_come_from_the_user(changes):
    with pytest.raises(ValueError):
        validate_grounding(understood(**changes), ["ช่วยคำนวณให้หน่อย"])


def test_grounded_exclusion_and_medical_override_are_accepted():
    validate_grounding(
        understood(exclusion_phrases=["ไม่ต้องให้โดส"], blocked_actions=["dose"]),
        ["ขอหลักการสั้นๆไม่ต้องให้โดส"],
    )
    validate_grounding(
        understood(medical_self_context=True, blocked_actions=["calculate", "menu", "dose"]),
        ["เป็นโรคไต"],
    )


@pytest.mark.parametrize(
    ("support", "category"), [([], "unsupported_fact"), (["S1.1"], "citation")]
)
def test_exempted_unit_that_is_an_evidence_claim_is_rejected(support, category):
    draft = "หลักฐานส่วนใหญ่รองรับเวย์"  # PT20: ledger called this a general fact
    client, calls = client_for(
        ledger("general_fact", support={0: support}),
        '{"sentences":[{"sentence":0,"evidence_or_effect_claim":true}]}',
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.issues[0].category == category and len(calls) == 2
    assert json.loads(calls[1]["contents"][0].parts[0].text) == {
        "sentences": [{"sentence": 0, "text": draft}]
    }
    assert calls[1]["config"].response_json_schema == EvidenceClaimCheck.model_json_schema()


def test_claim_check_is_skipped_without_sources_or_exempt_units():
    client, calls = client_for(ledger("advice"))
    review_answer(
        client,
        model="test",
        question="q",
        draft="ฝึกสม่ำเสมอ",
        passages=[],
        understanding=understood(),
    )
    client2, calls2 = client_for(ledger("framing"))
    review_answer(
        client2,
        model="test",
        question="q",
        draft="สรุปดังนี้",
        passages=PASSAGES,
        understanding=understood(),
    )
    assert len(calls) == 1 and len(calls2) == 1
