"""Keep individual claims tied to their named source, rather than card bibliography."""
import hashlib
import json
from pathlib import Path

import pytest

from app.services.prompts import BASE_SYSTEM_PROMPT, build_system_prompt

ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "knowledge/cards/energy-balance-cut-bulk.md"


def test_specific_fat_range_paragraph_only_attributes_helms():
    paragraphs = CARD.read_text(encoding="utf-8").split("\n\n")
    matches = [p for p in paragraphs if "15-20% ของพลังงาน" in p]
    assert len(matches) == 1
    claim = matches[0]
    assert "Helms et al., 2014, Fat" in claim
    assert "Aragon" not in claim
    assert "เตรียมแข่งขันเพาะกาย" in claim
    assert "หากไขมันสูงกว่านี้" in claim
    assert "ไม่ใช่ขั้นต่ำสำหรับทุกคน" in claim


def test_aragon_kept_for_diet_comparison_in_its_own_paragraph():
    paragraphs = CARD.read_text(encoding="utf-8").split("\n\n")
    comparisons = [p for p in paragraphs if "รูปแบบอาหารหลายแบบ" in p]
    assert len(comparisons) == 1
    assert "Aragon et al., 2017" in comparisons[0]
    assert "พลังงานและโปรตีนเท่ากัน" in comparisons[0]
    assert "15-20%" not in comparisons[0]


def test_new_correction_keeps_historical_manifest_immutable():
    correction = json.loads((ROOT / "knowledge/releases/q5-attribution-v1.json").read_text())
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/active-card-text-hashes.json").read_text()
    )
    assert correction["base_utf8_lf_sha256"] == fixture[correction["card"]]["utf8_lf_sha256"]
    actual = hashlib.sha256(CARD.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert correction["utf8_lf_sha256"] == actual
    assert correction["base_utf8_lf_sha256"] != correction["utf8_lf_sha256"]


@pytest.mark.parametrize("label", ["S1", "S4"])
def test_prompt_scopes_authors_even_when_passage_has_multiple_studies(label):
    content = "ผล A (Helms et al., 2014, Fat)\n\nผล B (Aragon et al., 2017)"
    prompt = build_system_prompt(passages=[{
        "label": label, "title": "หลายงานในหัวข้อเดียว", "heading": "ข้อสรุป",
        "content": content,
        "source_refs": ["Helms 2014", "Aragon 2017"],
    }])
    assert f"[{label}]" in prompt
    assert content in prompt
    assert "เมื่อระบุผู้แต่งหรือปี ต้องจับคู่กับข้อสรุป" in prompt
    assert "รายชื่อบรรณานุกรมหรือชื่อหลายงานท้ายย่อหน้าไม่แปลว่าทุกงานรองรับทุกประโยค" in prompt
    assert "ห้ามนำผู้แต่งจากอีกประโยค อีกหัวข้อ หรือแหล่ง S อื่น" in prompt
    assert "ไม่เดาชื่อผู้แต่งหรือปี" in prompt


def test_general_rule_does_not_replace_authors_in_generated_answers():
    assert "ถ้างานหลายชิ้นรองรับคนละประเด็น ให้แยกประโยค" in BASE_SYSTEM_PROMPT
    assert "ให้บอกข้อจำกัดนี้" in BASE_SYSTEM_PROMPT
