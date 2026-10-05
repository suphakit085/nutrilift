"""Source integrity and safety checks for the creatine clarity follow-up."""

import hashlib
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import chat, prompts

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = [
    json.loads(line)
    for line in (ROOT / "knowledge/evidence/creatine-clarity-v1/questions.jsonl")
    .read_text(encoding="utf8")
    .splitlines()
]


def test_card_has_exact_arithmetic_and_canonical_name():
    text = (ROOT / "knowledge/cards/creatine.md").read_text(encoding="utf8")
    assert "International Society of Sports Nutrition" in text
    assert "สมาคมโภชนาการการกีฬานานาชาติ" in text
    assert "21 ÷ 4 = 5.25" in text and "5.25 × 4 = 21" in text  # noqa: RUF001
    assert "21 ÷ 5 = 4.2" in text and "4.2 × 5 = 21" in text  # noqa: RUF001


def test_prompt_requires_fixed_count_and_checked_daily_total():
    assert "เลือกจำนวนครั้งแน่นอน" in prompts.BASE_SYSTEM_PROMPT
    assert "คูณกลับได้ยอดเดิม" in prompts.BASE_SYSTEM_PROMPT
    assert "International Society of Sports Nutrition" in prompts.BASE_SYSTEM_PROMPT


def test_new_card_manifest_and_primary_paragraph_are_reproducible():
    manifest = json.loads(
        (ROOT / "knowledge/evidence/content-fixes-v6/manifest.json").read_text(encoding="utf8")
    )
    assert len(manifest["cards"]) == 26
    assert [r["card"] for r in manifest["cards"] if r["changed"]] == ["creatine"]
    for card in manifest["cards"]:
        assert (
            hashlib.sha256(
                (ROOT / "knowledge/evidence/content-fixes-v6" / (card["card"] + ".md")).read_bytes()
            ).hexdigest()
            == card["candidate_sha256"]
        )
    ref = manifest["evidence"][0]
    source = ROOT / ref["local_path"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ref["source_sha256"]
    paragraphs = [
        " ".join("".join(p.itertext()).split())
        for p in ET.parse(source).getroot().findall(".//body//p")
    ]
    assert ref["paragraph_text"] in paragraphs
    assert hashlib.sha256(ref["paragraph_text"].encode()).hexdigest() == ref["paragraph_sha256"]
    assert (
        "0.3 g/kg/d" in ref["paragraph_text"]
        and "21 g/day for a 70 kg individual" in ref["paragraph_text"]
    )


@pytest.mark.parametrize(
    "case", [q for q in QUESTIONS if q["expected"] == "arithmetic"], ids=lambda q: q["id"]
)
def test_preregistered_arithmetic_expectations(case):
    total = Decimal("0.3") * Decimal(str(case["weight_kg"]))
    dose = total / Decimal(case["doses"])
    assert total == Decimal(str(case["daily_g"]))
    assert dose == Decimal(str(case["per_dose_g"]))
    assert dose * case["doses"] == total


@pytest.mark.parametrize(
    "case", [q for q in QUESTIONS if q["expected"].startswith("rule:")], ids=lambda q: q["id"]
)
@pytest.mark.parametrize("rag", [False, True])
def test_loading_arithmetic_does_not_bypass_safety(case, rag):
    with (
        patch.object(chat, "get_client", side_effect=AssertionError("Provider forbidden")),
        patch.object(chat.retrieval, "search", side_effect=AssertionError("Retrieval forbidden")),
        patch.object(
            chat, "calc_nutrition_targets", side_effect=AssertionError("Calculator forbidden")
        ),
    ):
        answer = chat.collect_answer(
            SimpleNamespace(commit=lambda: None, rollback=lambda: None),
            user_message=case["question"],
            use_rag=rag,
        )
    assert answer["type"] == "done" and answer["model"] == case["expected"]
    assert not answer["tool_calls"] and not answer["citations"]
    assert "5.25" not in answer["text"] and "5.475" not in answer["text"]
