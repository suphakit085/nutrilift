"""Bind the active knowledge files and citation policy to the new release."""
import hashlib
import json
from pathlib import Path

from app.services.prompts import BASE_SYSTEM_PROMPT, GOAL_GUIDANCE_TH

ROOT = Path(__file__).resolve().parents[2]


def test_active_card_hashes_match_v9_manifest():
    path = ROOT / "knowledge/evidence/content-fixes-v9/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf8"))
    canonical = json.loads(
        (Path(__file__).parent / "fixtures/active-card-text-hashes.json").read_text(encoding="utf8")
    )
    assert len(manifest["cards"]) == 26
    assert {r["card"] for r in manifest["cards"] if r["changed"]} == {
        "energy-balance-cut-bulk", "fiber", "sodium-water"
    }
    for row in manifest["cards"]:
        path = ROOT / "knowledge/cards" / (row["card"] + ".md")
        recorded = canonical[row["card"]]
        assert recorded["recorded_sha256"] == row["candidate_sha256"]
        # Git normalizes text line endings. Preserve the original evidence hash
        # above while checking identical UTF-8 text on both Windows and Linux.
        actual = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(actual).hexdigest() == recorded["utf8_lf_sha256"]


def test_direct_2009_citation_discloses_abstract_only_access():
    card = (ROOT / "knowledge/cards/creatine-myths.md").read_text(encoding="utf8")
    assert "PMID:19741313" in card
    assert "ตรวจบทคัดย่อต้นฉบับ ไม่ใช่ฉบับเต็ม" in card
    assert "ไม่เรียกงานใหม่ว่าลบล้างผลทุกข้อของงานเดิม" in card


def test_prompt_separates_operational_facts_and_recipe_uncertainty_from_papers():
    assert "ห้ามนำ S ของบทความมาอ้างว่าระบบไม่มีรายการอาหาร" in BASE_SYSTEM_PROMPT
    assert "โดยไม่มีข้อมูลสูตรหรือฉลาก" in BASE_SYSTEM_PROMPT
    assert "ไม่ใช่เพียงอยู่ในหัวข้อเดียวกัน" in BASE_SYSTEM_PROMPT
    assert "แนวปฏิบัติของโครงการ" in GOAL_GUIDANCE_TH["maintain"]
