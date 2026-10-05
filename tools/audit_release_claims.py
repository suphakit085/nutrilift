"""Record a scoped AI claim review with primary-source anchors and file hashes.

This is an audit receipt, not an automatic entailment judge or human approval.
Historical browser answers stay unchanged, including the failures we found.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/source-audit/claim-review-20261005"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads((ROOT / "knowledge/evidence/source-manifest.json").read_text(encoding="utf8"))["sources"]
    by_id = {s["source_id"]: s for s in sources}
    anchors = []
    specs = [
        ("CREATINE-MYTHS-2021", "Does creatine cause hair loss / baldness?", [1, 2, 3]),
        ("CREATINE-MYTHS-2021", "Is a creatine ‘loading-phase’ required?", [2]),
        ("CREATINE-HAIR-2025", "Discussion", [1, 2, 3]),
        ("HELMS-2014", "Fat", [5]),
        ("IRAKI-2019", "Positive Energy Balance", [2, 3, 4]),
        ("IRAKI-2019", "8. Summary", [1]),
    ]
    for sid, heading, positions in specs:
        source = by_id[sid]
        path = ROOT / source["local_path"]
        assert digest(path) == source["sha256"]
        sections = [s for s in ET.parse(path).getroot().findall(".//body//sec")
                    if s.find("title") is not None and " ".join("".join(s.find("title").itertext()).split()) == heading]
        assert len(sections) == 1, (sid, heading)
        for position in positions:
            paragraph = " ".join("".join(sections[0].findall("p")[position - 1].itertext()).split())
            anchors.append({"source_id": sid, "local_path": source["local_path"],
                            "source_sha256": digest(path), "heading": heading, "paragraph_1based": position,
                            "paragraph_sha256": hashlib.sha256(paragraph.encode()).hexdigest()})
    originals = []
    for path in [OUT / "creatine-2009-record.json",
                 ROOT / "knowledge/sources/evidence-2026-10-01/WHO-SUGAR-2015-SUMMARY.html",
                 ROOT / "knowledge/sources/residuals-2026-10-03/dietitians-canada-joint-position-revised-2016.pdf"]:
        originals.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)})
    findings = [
        {"answer": "U02", "decision": "revise", "claims": 3,
         "finding": "125/5=25 is correct. Timing guidance was unsolicited; fixed via protein_split. The source is nutrient timing, not a proof that this user's five meals need fixed intervals."},
        {"answer": "U03", "decision": "revise", "claims": 3,
         "finding": "Tool targets agree with saved results. Weekly weight averages have support in Iraki; 2-4 weeks is a project monitoring rule, not a result established by the cited TDEE passage. Prompt now identifies it as project practice."},
        {"answer": "U10", "decision": "supported_with_limits", "claims": 5,
         "finding": "2009 N=20 recruited, three-week protocol and DHT endpoints checked against original abstract; completion N=16 in 2021 review must not be confused with enrolled N. No direct hair measurement supported by 2021/2025. 2025 12-week male-only null finding and missing family history are supported, not a lifetime guarantee. Added direct 2009 bibliography with abstract-only disclosure."},
        {"answer": "U11", "decision": "supported_with_limits", "claims": 3,
         "finding": "0.3 g/kg/day is supported by 2021 loading section. 69.3*0.3=20.79 and /5=4.158, rounded 4.16. Arithmetic is project calculation, not an independently studied dose. Non-loading storage findings do not establish identical long-term training results."},
        {"answer": "TEA01", "decision": "revise", "claims": 3,
         "finding": "DB absence is verified by database/search, not WHO. WHO supports definitions of free sugars, not a specific unlabelled drink's fat/protein/energy classification. Prompt now forbids this attribution and unsupported recipe conclusions."},
    ]
    answer_inputs = []
    for name in ["account-uat-20261004", "remove-bubble-tea-20261005"]:
        path = ROOT / "output/playwright" / name / "results.json"
        rows = json.loads(path.read_text(encoding="utf8"))["results"]
        answer_inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
                              "reviewed_ids": [r["id"] for r in rows if r.get("citations")]})
    report = {"reviewed_at": datetime.now(UTC).isoformat(), "reviewer": "Codex AI; independent nutrition review pending",
              "scope": "Five cited real-browser answers, 17 grouped claims, selected primary-source anchors; not an exhaustive atomic review of every possible answer or every sentence in all 26 cards.",
              "answer_inputs": answer_inputs, "findings": findings, "primary_anchors": anchors,
              "other_primary_files": originals, "medical_scope": "Disease, drug, symptom and lab-result questions are refused; no medical advice validation is asserted.",
              "independent_review": "pending", "fresh_evaluation": "required after deployment"}
    (OUT / "claim-review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    previous = json.loads((ROOT / "knowledge/evidence/content-fixes-v6/manifest.json").read_text(encoding="utf8"))
    old = {r["card"]: r["candidate_sha256"] for r in previous["cards"]}
    cards = [{"card": p.stem, "previous_sha256": old[p.stem], "candidate_sha256": digest(p),
              "changed": old[p.stem] != digest(p)} for p in sorted((ROOT / "knowledge/cards").glob("*.md")) if not p.name.startswith("_")]
    manifest = {"version": "v7", "cards": cards, "review_receipt": "output/source-audit/claim-review-20261005/claim-review.json",
                "review_receipt_sha256": digest(OUT / "claim-review.json"), "independent_review": "pending"}
    target = ROOT / "knowledge/evidence/content-fixes-v7"
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"reviewed_answers": len(findings), "grouped_claims": sum(f["claims"] for f in findings),
                      "changed_cards": [c["card"] for c in cards if c["changed"]]}))


if __name__ == "__main__":
    main()
