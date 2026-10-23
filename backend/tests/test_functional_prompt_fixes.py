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
    """Fake client. Review calls may run concurrently, so a JSON answer goes to
    the call whose response schema it fits; other answers keep their order."""
    calls = []
    used: set[int] = set()

    def pick(kwargs) -> str:
        schema = getattr(kwargs.get("config"), "response_json_schema", None) or {}
        wanted = set(schema.get("properties") or {})
        for index, answer in enumerate(answers):
            if index in used or not wanted:
                continue
            try:
                keys = set(json.loads(answer))
            except (ValueError, TypeError):
                continue
            if keys and keys <= wanted and keys & {"units", "sentences", "pairs"}:
                used.add(index)
                return answer
        for index, answer in enumerate(answers):
            if index not in used:
                used.add(index)
                return answer
        return answers[-1]

    def generate(**kwargs):
        calls.append(kwargs)
        answer = pick(kwargs)
        yield types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part.from_text(text=answer)]),
                    finish_reason="STOP",
                )
            ]
        )

    return SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate)), calls


def call_for(calls, schema):
    """The one call made with this response schema (review calls may run concurrently)."""
    matches = [c for c in calls if c["config"].response_json_schema == schema.model_json_schema()]
    assert len(matches) == 1, len(matches)
    return matches[0]


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
    state = understood(task="clarify", missing_information="food_quantity")
    client, calls = client_for(state.model_dump_json())
    monkeypatch.setattr(chat, "get_client", lambda: client)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="คำถามที่เว้นข้อมูล"
    )
    assert len(calls) == 1 and "ปริมาณที่กิน" in result["text"]
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
    client, calls = client_for(
        ledger("research", support={0: ["S1.1"]}),
        claim_with("evidence_or_effect"),
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="หลักฐานคืออะไร",
        draft="ข้อความ [S1]",
        passages=[{"label": "S1", "content": "หลักฐานจริง"}, {"label": "S9", "content": "เรื่องอื่น"}],
        understanding=understood(),
    )
    payload = json.loads(call_for(calls, EvidenceReview)["contents"][0].parts[0].text)
    assert payload["draft_units"] == [{"unit": 0, "text": "ข้อความ [S1]", "labels": ["S1"]}]
    assert [p["id"] for p in payload["source_paragraphs"]] == ["S1.1", "S9.1"]
    assert verdict.accepted and verdict.ledger[0]["support"] == ["S1.1"]


def test_units_split_json_leaves_and_label_boundaries():
    draft = json.dumps({"answer": "ก [S1] ข [S2, S3] ค", "caveat": "ง"}, ensure_ascii=False)
    assert [(u["text"], u["labels"]) for u in draft_units(draft)] == [
        ("answer: ก [S1]", ["S1"]),
        ("answer: ข [S2, S3]", ["S2", "S3"]),
        ("answer: ค", []),
        ("caveat: ง", []),
    ]
    nested = json.dumps({"plan": {"items": [{"dose": "5 g"}]}}, ensure_ascii=False)
    assert [u["text"] for u in draft_units(nested)] == ["plan.items[0].dose: 5 g"]
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
    claim = (
        '{"sentences":[{"sentence":0,"claims_evidence_backing":%s,"states_outcome":false,"type":"evidence_or_effect"}]}'
        % ("true" if names_source else "false")
    )
    client, _ = client_for(review, claim)
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
    not_a_claim = claim_with("instruction")
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
        "note: ก",
    ]
    review = ledger(
        "framing",
        "framing",
        "framing",
        issues=[{"unit": 1, "category": "unsupported_fact", "reason": "ไม่มีแหล่งรับรองความปลอดภัย"}],
    )
    claims = json.dumps(
        {
            "sentences": [
                {
                    "sentence": 0,
                    "claims_evidence_backing": False,
                    "states_outcome": False,
                    "type": "framing",
                },
                {
                    "sentence": 1,
                    "claims_evidence_backing": False,
                    "states_outcome": False,
                    "type": "permission_or_safety",
                },
                {
                    "sentence": 2,
                    "claims_evidence_backing": False,
                    "states_outcome": False,
                    "type": "framing",
                },
            ]
        }
    )
    client, _ = client_for(review, claims)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and verdict.issues[0].fragment == "safe_for_kidney: true"


def test_support_ids_are_normalised_and_nonexistent_ones_never_count():
    from app.services.answer_review import normalize_support

    paragraphs = [
        {"id": "S1.1", "text": "ก"},
        {"id": "S1.2", "text": "ข"},
        {"id": "S2.1", "text": "ค"},
    ]
    assert normalize_support(["S1-2", "[S2.1]", "S1", "s1.2", "S9.4", "S1.7", "x"], paragraphs) == (
        ["S1.2", "S2.1", "S1"],
        ["S9.4", "S1.7", "x"],
    )
    claim = claim_with("evidence_or_effect")
    client, calls = client_for(ledger("research", support={0: ["S9.4"]}), claim)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft="ข้อความ [S1]",
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and len(calls) == 2  # no retry, no crash
    assert verdict.ledger[0]["invalid_support"] == ["S9.4"]


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
        claim_with("evidence_or_effect"),
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
    assert json.loads(call_for(calls, EvidenceClaimCheck)["contents"][0].parts[0].text) == {
        "sentences": [{"sentence": 0, "text": draft}]
    }


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
    client2, calls2 = client_for(ledger("personal"), claim_json("instruction"))
    review_answer(
        client2,
        model="test",
        question="q",
        draft="เป้าหมายโปรตีน 126 กรัม",
        passages=PASSAGES,
        understanding=understood(),
    )
    # Without sources there is no claim check. With sources it now runs at the
    # same time as the ledger (no added wait); verdicts on personal units are
    # ignored, as before.
    assert len(calls) == 1 and len(calls2) == 2


@pytest.mark.parametrize("draft", ["{}", "[]", '{"a": {}}', " - "])
def test_draft_without_content_is_rejected_without_a_model_call(draft):
    client, calls = client_for(ledger())
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and not calls


def test_framing_unit_with_an_evidence_claim_is_checked():
    draft = "เวย์เป็นอาหารเสริมที่มีหลักฐานรองรับเด่นชัด"
    client, calls = client_for(
        ledger("framing"),
        claim_with("evidence_or_effect"),
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and len(calls) == 2


@pytest.mark.parametrize(
    "answer",
    [
        '{"sentences":[{"sentence":0,"claims_evidence_backing":false,"states_outcome":false,"type":"instruction"},{"sentence":0,"claims_evidence_backing":false,"states_outcome":false,"type":"evidence_or_effect"}]}',
        '{"sentences":[{"sentence":0,"claims_evidence_backing":false,"states_outcome":false,"type":"instruction"},{"sentence":0,"claims_evidence_backing":false,"states_outcome":false,"type":"instruction"}]}',
        '{"sentences":[]}',
    ],
)
def test_claim_check_with_duplicate_or_missing_sentences_fails_closed(monkeypatch, answer):
    monkeypatch.setattr("app.services.answer_review.time.sleep", lambda _: None)
    client, calls = client_for(ledger("advice"), answer, ledger("advice"), answer)
    with pytest.raises(ValueError):
        review_answer(
            client,
            model="test",
            question="q",
            draft="ตรวจฉลากอาหารก่อนซื้อ",
            passages=PASSAGES,
            understanding=understood(),
        )
    assert len(calls) == 4  # one retry of the whole review, then it stops


PERMISSION_PASSAGES = [{"label": "S3", "content": "เลือกโปรตีนตามปริมาณรวม คุณภาพ และข้อจำกัดอาหาร"}]


@pytest.mark.parametrize(("stated", "accepted"), [(False, False), (True, True)])
def test_cited_permission_must_be_stated_by_its_own_paragraph(stated, accepted):
    draft = "เวย์กินคู่กับนมได้ตามความสะดวก [S3]"  # VX03: permission from a silent source
    client, calls = client_for(
        ledger("advice", support={0: ["S3.1"]}),
        claim_with("permission_or_safety"),
        json.dumps({"pairs": [{"pair": 0, "stated": stated}]}),
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PERMISSION_PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted is accepted and len(calls) == 3
    pair = json.loads(calls[2]["contents"][0].parts[0].text)["pairs"][0]
    assert pair == {
        "pair": 0,
        "claim": "เวย์กินคู่กับนมได้ตามความสะดวก",
        "evidence": ["เลือกโปรตีนตามปริมาณรวม คุณภาพ และข้อจำกัดอาหาร"],
    }


def test_cited_non_permission_claim_skips_the_permission_check():
    client, calls = client_for(
        ledger("research", support={0: ["S3.1"]}),
        claim_with("instruction"),
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft="เลือกโปรตีนตามปริมาณรวม [S3]",
        passages=PERMISSION_PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted and len(calls) == 2


def test_ledger_research_label_on_a_practical_tip_does_not_reject_it():
    # A whole-draft ledger may call "check the label" research and note it as
    # unsupported; the per-sentence check types it as an instruction.
    draft = "ตรวจฉลากอาหารก่อนเลือกซื้อ"
    review = ledger(
        "research",
        issues=[{"unit": 0, "category": "unsupported_fact", "reason": "ไม่มีในแหล่ง"}],
    )
    claim = claim_with("instruction")
    client, _ = client_for(review, claim)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted and verdict.ledger[0]["cleared_unsupported_note"] is True


def test_numeric_instruction_keeps_the_ledger_unsupported_note():
    draft = "กินโปรตีนวันละ 3 กรัมต่อกิโลกรัม"
    review = ledger(
        "advice",
        issues=[{"unit": 0, "category": "unsupported_fact", "reason": "ตัวเลขไม่มีในแหล่ง"}],
    )
    claim = claim_with("instruction")
    client, _ = client_for(review, claim)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted


def test_evidence_backing_in_an_introduction_is_rejected_even_when_typed_framing():
    draft = "ครีเอทีนและเวย์เป็นอาหารเสริมที่มีหลักฐานรองรับเด่นชัด ดังนี้ครับ"
    claim = claim_with("framing", backing=True)
    client, _ = client_for(ledger("framing"), claim)
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=draft,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and verdict.issues[0].category == "unsupported_fact"


def claim_json(*types_):
    return json.dumps(
        {
            "sentences": [
                {
                    "sentence": i,
                    "claims_evidence_backing": False,
                    "states_outcome": False,
                    "type": t,
                }
                for i, t in enumerate(types_)
            ]
        }
    )


def test_coverage_note_with_labels_is_accepted_and_its_labels_removed():
    cover = "ข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้ [S1, S2]"
    client, _ = client_for(ledger("evidence_gap"), claim_json("coverage_statement"))
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=cover,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted
    assert verdict.label_edits == [[cover, "ข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้"]]


def test_instruction_keeps_only_labels_its_sources_state():
    tip = "ผู้มีโรคไตควรให้ผู้รักษากำหนดอาหาร [S1, S2]"
    client, _ = client_for(ledger("advice", support={0: ["S2.1"]}), claim_json("instruction"))
    verdict, _ = review_answer(
        client, model="test", question="q", draft=tip, passages=PASSAGES, understanding=understood()
    )
    assert verdict.accepted
    assert verdict.label_edits == [[tip, "ผู้มีโรคไตควรให้ผู้รักษากำหนดอาหาร [S2]"]]


def test_claim_with_an_unsupported_label_is_still_rejected():
    claim = "เวย์ช่วยเพิ่มกล้ามเนื้อ [S1, S2]"
    client, _ = client_for(
        ledger("research", support={0: ["S2.1"]}), claim_json("evidence_or_effect")
    )
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=claim,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and not verdict.label_edits


def test_chat_shows_the_answer_with_surplus_labels_removed(monkeypatch):
    draft = "เลือกโปรตีนตามปริมาณรวม [S1]\n\nข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้ [S1, S2]"
    passages = [
        chat.retrieval.Passage(**p)
        for p in [
            {
                "label": "S1",
                "score": 0.9,
                "chunk_id": "c1",
                "document_id": "d1",
                "document_slug": "a",
                "title": "t",
                "heading": "h",
                "content": "เลือกโปรตีนตามปริมาณรวม",
                "source_refs": [],
            },
            {
                "label": "S2",
                "score": 0.8,
                "chunk_id": "c2",
                "document_id": "d2",
                "document_slug": "b",
                "title": "t",
                "heading": "h",
                "content": "อื่น",
                "source_refs": [],
            },
        ]
    ]
    client, _ = client_for(
        understood().model_dump_json(),
        draft,
        ledger("advice", "evidence_gap", support={0: ["S1.1"]}),
        claim_json("instruction", "coverage_statement"),
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: passages)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="เลือกโปรตีนยังไง"
    )
    assert result["type"] == "done"
    assert result["text"].endswith("ข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้")
    assert [c["label"] for c in result["citations"]] == ["S1"]


def test_label_standing_alone_joins_the_previous_sentence():
    units = draft_units("ก ข [S1] [S3]\n[S4]\nค")
    assert [(u["text"], u["labels"]) for u in units] == [
        ("ก ข [S1] [S3] [S4]", ["S1", "S3", "S4"]),
        ("ค", []),
    ]


def test_labelled_coverage_note_is_not_rejected_by_a_ledger_unsupported_note():
    cover = "ข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้ [S1]"
    review = ledger(
        "evidence_gap",
        issues=[{"unit": 0, "category": "unsupported_fact", "reason": "แหล่งไม่ได้บอกว่าไม่ครอบคลุม"}],
    )
    client, _ = client_for(review, claim_json("coverage_statement"))
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=cover,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted and verdict.label_edits == [[cover, "ข้อมูลอ้างอิงยังไม่ครอบคลุมเรื่องนี้"]]


def test_labels_are_not_removed_when_the_ledger_calls_the_sentence_research():
    risky = "เวย์กินคู่กับนมได้ [S1]"  # claim check mistyped it as an instruction
    client, _ = client_for(ledger("research"), claim_json("instruction"))
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=risky,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert not verdict.accepted and not verdict.label_edits


def claim_with(type_, *, outcome=False, backing=False):
    return json.dumps(
        {
            "sentences": [
                {
                    "sentence": 0,
                    "claims_evidence_backing": backing,
                    "states_outcome": outcome,
                    "type": type_,
                }
            ]
        }
    )


@pytest.mark.parametrize(("stated", "accepted"), [(False, False), (True, True)])
def test_cited_instruction_stating_an_outcome_is_checked_against_its_source(stated, accepted):
    # PT10-r2: "track weight with training so the weight gained is muscle [S2]",
    # where S2 is protein evidence.
    tip = "บันทึกน้ำหนักร่วมกับการฝึกเพื่อให้มั่นใจว่าน้ำหนักที่เพิ่มมาจากกล้ามเนื้อ [S2]"
    client, calls = client_for(
        ledger("advice", support={0: ["S2.1"]}),
        claim_with("instruction", outcome=True),
        json.dumps({"pairs": [{"pair": 0, "stated": stated}]}),
    )
    verdict, _ = review_answer(
        client, model="test", question="q", draft=tip, passages=PASSAGES, understanding=understood()
    )
    assert verdict.accepted is accepted and not verdict.label_edits and len(calls) == 3
    assert json.loads(calls[2]["contents"][0].parts[0].text)["pairs"][0]["evidence"] == [
        "ปริมาณโปรตีนรวมต่อวัน"
    ]


def test_cited_instruction_without_an_outcome_skips_the_conclusion_check():
    client, calls = client_for(ledger("advice", support={0: ["S2.1"]}), claim_with("instruction"))
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft="ตรวจฉลากอาหารก่อนเลือกซื้อ [S2]",
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted and len(calls) == 2


def test_coverage_note_loses_labels_even_when_the_ledger_calls_it_research():
    cover = "ข้อมูลอ้างอิงที่ระบุไว้ไม่ได้กล่าวถึงเรื่องนี้ [S1, S2]"  # TH02-r2
    client, _ = client_for(ledger("research"), claim_with("coverage_statement"))
    verdict, _ = review_answer(
        client,
        model="test",
        question="q",
        draft=cover,
        passages=PASSAGES,
        understanding=understood(),
    )
    assert verdict.accepted
    assert verdict.label_edits == [[cover, "ข้อมูลอ้างอิงที่ระบุไว้ไม่ได้กล่าวถึงเรื่องนี้"]]


@pytest.mark.parametrize("slot", ["goal", "profile"])
def test_saved_profile_answers_profile_and_goal_clarifications(slot):
    # Production 23 Oct: "ควรกินโปรตีนวันละกี่กรัม" with a saved goal was asked for
    # the goal, then told to fill in the profile again.
    state = understood(task="clarify", missing_information=slot).model_dump_json()
    client, calls = client_for(state)
    result, _ = interpret_request(
        client, model="test", message="ควรกินโปรตีนวันละกี่กรัม", history=[], profile=adult()
    )
    assert result.task == "knowledge" and result.missing_information is None
    assert result.personal_context is True
    # The saved goal is not sent: the model copied it into the goal field
    # without a user quote, which then failed grounding (live check 23 Oct).
    payload = json.loads(calls[0]["contents"][0].parts[0].text)
    assert set(payload) == {"user_turns", "saved_profile_present"}


def test_other_clarifications_and_profileless_users_are_unchanged():
    food = understood(task="clarify", missing_information="food_quantity").model_dump_json()
    client, _ = client_for(food)
    result, _ = interpret_request(
        client, model="test", message="กินไปเท่าไรแล้ว", history=[], profile=adult()
    )
    assert result.task == "clarify"
    goal = understood(task="clarify", missing_information="goal").model_dump_json()
    client, _ = client_for(goal)
    result, _ = interpret_request(
        client, model="test", message="ควรกินเท่าไร", history=[], profile=None
    )
    assert result.task == "clarify"


def test_chat_answers_a_saved_profile_user_instead_of_asking_for_the_goal(monkeypatch):
    client, _ = client_for(
        understood(task="clarify", missing_information="goal").model_dump_json(),
        "โปรตีนของคุณประมาณ 162 กรัมต่อวัน",
        ledger("personal"),
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="ควรกินโปรตีนวันละกี่กรัม", profile=adult()
    )
    assert result["type"] == "done" and result["model"] != "rule:missing_information"
    assert "ต้องการลดไขมัน เพิ่มกล้ามเนื้อ หรือรักษาน้ำหนัก" not in result["text"]


@pytest.mark.parametrize("message", [
    # Complete questions the fixed "name both items" reply refused: 23 Oct
    # real-question runs (TH11) and the production user test.
    "เวย์โปรตีน กับ โปรตีนสกัดจากถั่วเหลือง อันไหนดีกว่าคะ",
    "กินเวย์ผสมนมได้ไหมครับ",
    # A genuinely blank pair is also the answer model's call to make.
    "คำถามยอดฮิต  เวย์ทานคู่กับ .. !!",
])
def test_pair_readings_go_to_the_answer_model(monkeypatch, message):
    client, calls = client_for(
        understood(task="clarify", missing_information="pair_partner").model_dump_json(),
        "ต้องการให้เทียบเรื่องใดเป็นพิเศษครับ",
        ledger("framing"),
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message=message, profile=adult()
    )
    assert result["type"] == "done" and result["model"] != "rule:missing_information"
    assert "ระบุทั้งสองอย่าง" not in result["text"]
    assert len(calls) >= 2  # the answer model was called


def test_review_sees_the_saved_profile_and_calculator_targets():
    client, calls = client_for(ledger("personal"), claim_json("instruction"))
    review_answer(
        client,
        model="test",
        question="ควรกินโปรตีนวันละเท่าไร",
        draft="เป้าโปรตีนของคุณคือ 117 กรัมต่อวัน",
        passages=PASSAGES,
        understanding=understood(),
        user_context={"user_profile": "หนัก 65 กก.", "calculated_targets": "โปรตีน 117 กรัม/วัน"},
    )
    payload = json.loads(call_for(calls, EvidenceReview)["contents"][0].parts[0].text)
    assert payload["user_profile"] == "หนัก 65 กก."
    assert payload["calculated_targets"] == "โปรตีน 117 กรัม/วัน"


def test_chat_passes_profile_and_targets_to_the_review(monkeypatch):
    seen = {}

    def fake_review(client, **kwargs):
        seen.update(kwargs)
        from app.services.answer_review import AnswerReview

        return AnswerReview(accepted=True), {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    client, _ = client_for(understood(personal_context=True).model_dump_json(), "ฝึกและกินโปรตีนให้พอ")
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    monkeypatch.setattr(chat, "review_answer", fake_review)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="ควรกินยังไง", profile=adult()
    )
    assert result["type"] == "done"
    assert "90" in seen["user_context"]["user_profile"]
    assert seen["user_context"]["calculated_targets"]


def test_profile_note_is_sent_only_with_profile_data():
    client, calls = client_for(ledger("framing"))
    review_answer(
        client,
        model="test",
        question="q",
        draft="สวัสดี",
        passages=[],
        understanding=understood(),
    )
    assert "user_context_note" not in json.loads(calls[0]["contents"][0].parts[0].text)


def test_unverified_pair_answer_falls_back_to_the_clarification(monkeypatch):
    # The model-first path must never be worse than the fixed reply: when the
    # answer cannot be verified the user is asked, not shown an error.
    client, _ = client_for(
        understood(task="clarify", missing_information="pair_partner").model_dump_json(),
        "เวย์ทานคู่กับนมได้",
    )
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])

    def unavailable(*_, **__):
        raise RuntimeError("review down")

    monkeypatch.setattr(chat, "review_answer", unavailable)
    events = list(chat.stream_understood_chat(
        SimpleNamespace(commit=lambda: None), user_message="เวย์ทานคู่กับ .. !!", profile=adult(),
    ))
    done = events[-1]
    assert done["type"] == "done" and done["text"] == chat.PAIR_CLARIFICATION
    assert done["request_understanding"]["missing_information"] == "pair_partner"
    assert not any(e["type"] == "error" for e in events)
    assert [e["text"] for e in events if e["type"] == "delta"] == [chat.PAIR_CLARIFICATION]


def test_other_readings_keep_their_error(monkeypatch):
    client, _ = client_for(understood().model_dump_json(), "คำตอบ")
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    def unavailable(*_, **__):
        raise RuntimeError("review down")

    monkeypatch.setattr(chat, "review_answer", unavailable)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="โปรตีนคืออะไร", profile=adult(),
    )
    assert result["type"] == "error" and result["code"] == "answer_review_unavailable"


def test_interpreter_prompt_defines_every_task():
    # lookup_food was the only task without a definition (24 Oct probe).
    from app.services.request_understanding import SYSTEM

    for task in ("calculate_targets", "plan_menu", "lookup_food", "clarify"):
        assert f"task={task}" in SYSTEM, task
