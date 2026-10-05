"""Bind the active knowledge files and citation policy to the new release."""
import hashlib
import json
from pathlib import Path

from app.services.prompts import BASE_SYSTEM_PROMPT, GOAL_GUIDANCE_TH

ROOT = Path(__file__).resolve().parents[2]


def test_active_card_hashes_match_v7_manifest():
    path = ROOT / "knowledge/evidence/content-fixes-v7/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf8"))
    assert len(manifest["cards"]) == 26
    assert {r["card"] for r in manifest["cards"] if r["changed"]} == {
        "body-fat-by-sex", "creatine-myths", "energy-balance-cut-bulk"
    }
    for row in manifest["cards"]:
        path = ROOT / "knowledge/cards" / (row["card"] + ".md")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["candidate_sha256"]


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
