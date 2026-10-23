"""An answer whose only defects are unbacked sentences keeps its verified part."""

from types import SimpleNamespace

import pytest

from app.services import chat
from app.services.answer_review import (
    AnswerReview,
    ReviewIssue,
    draft_units,
    has_answer_content,
    trim_unverified,
)
from tests.test_functional_prompt_fixes import adult, client_for, understood

GOOD = "ควรได้โปรตีนรวมต่อวันให้ถึงเป้า [S1]"
BAD = "ขนมปังกับนมอย่างเดียวไม่พอสำหรับสร้างกล้ามเนื้อ"
DRAFT = f"- {GOOD}\n- {BAD}"
#: The review reports a unit by its full text, bullet included.
BAD_UNIT, GOOD_UNIT = f"- {BAD}", f"- {GOOD}"


def verdict(draft, flagged=(), category="unsupported_fact", kinds=None):
    ledger = [
        {**unit, "kind": (kinds or {}).get(unit["raw"], "research")}
        for unit in draft_units(draft)
    ]
    issues = [ReviewIssue(category=category, fragment=text, reason="ไม่มีในแหล่ง") for text in flagged]
    return AnswerReview(accepted=not issues, issues=issues, ledger=ledger)


def test_flagged_unit_is_removed_with_its_empty_bullet():
    text, removed = trim_unverified(DRAFT, verdict(DRAFT, [BAD_UNIT]))
    assert text == f"- {GOOD}"
    assert removed == [BAD_UNIT]


@pytest.mark.parametrize("category", ["user_fact", "instruction", "language"])
def test_non_evidence_defects_are_never_trimmed(category):
    assert trim_unverified(DRAFT, verdict(DRAFT, [BAD_UNIT], category=category)) is None


def test_json_and_ambiguous_positions_are_not_trimmed():
    data = '{"advice": "ขนมปังกับนมไม่พอ"}'
    assert trim_unverified(data, verdict(data, ["advice: ขนมปังกับนมไม่พอ"])) is None
    twice = f"{BAD}\n{BAD}"
    assert trim_unverified(twice, verdict(twice, [BAD])) is None


def test_framing_and_coverage_alone_are_not_an_answer():
    only_framing = verdict("สรุปได้ดังนี้ครับ", kinds={"สรุปได้ดังนี้ครับ": "framing"})
    assert not has_answer_content(only_framing)
    assert has_answer_content(verdict(GOOD, kinds={GOOD: "advice"}))


def _run(monkeypatch, reviews):
    client, _ = client_for(understood().model_dump_json(), DRAFT, DRAFT)
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    monkeypatch.setattr(chat, "answer_issues", lambda *_, **__: [])
    queue = list(reviews)
    monkeypatch.setattr(chat, "review_answer", lambda *_, **__: (queue.pop(0), {}))
    return chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message="ขนมปังกับนมพอไหม", profile=adult()
    )


def test_answer_keeps_its_verified_part_after_the_repair_also_fails(monkeypatch):
    trimmed = f"- {GOOD}"
    result = _run(monkeypatch, [
        verdict(DRAFT, [BAD_UNIT]),  # first draft
        verdict(DRAFT, [BAD_UNIT]),  # repaired draft, same defect
        verdict(trimmed, kinds={GOOD_UNIT: "advice"}),  # trimmed text passes
    ])
    assert result["type"] == "done"
    # No passages in this test, so the app drops the [S1] label as usual.
    assert GOOD.split(" [")[0] in result["text"] and BAD not in result["text"]
    assert result["text"].endswith(chat.TRIMMED_NOTE)


def test_trimmed_text_that_fails_its_own_review_is_still_withheld(monkeypatch):
    trimmed = f"- {GOOD}"
    result = _run(monkeypatch, [
        verdict(DRAFT, [BAD_UNIT]), verdict(DRAFT, [BAD_UNIT]), verdict(trimmed, [GOOD_UNIT]),
    ])
    assert result["type"] == "error" and result["code"] == "answer_validation_failed"


def test_trimmed_text_with_only_framing_is_still_withheld(monkeypatch):
    trimmed = f"- {GOOD}"
    result = _run(monkeypatch, [
        verdict(DRAFT, [BAD_UNIT]),
        verdict(DRAFT, [BAD_UNIT]),
        verdict(trimmed, kinds={GOOD_UNIT: "framing"}),
    ])
    assert result["type"] == "error"


def test_excluded_action_defect_still_withholds_the_answer(monkeypatch):
    result = _run(monkeypatch, [
        verdict(DRAFT, [BAD_UNIT], category="instruction"),
        verdict(DRAFT, [BAD_UNIT], category="instruction"),
    ])
    assert result["type"] == "error" and result["code"] == "answer_validation_failed"
