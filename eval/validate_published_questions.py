"""Check frozen title provenance; does not certify authorship or gold answers."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def main():
    root = Path(__file__).parent / "datasets/published-questions-20261021"
    assert not list(root.glob("published-questions-en.*")), "English candidates are excluded"
    assert {path.name for path in root.glob("published-questions-*.jsonl")} == {
        "published-questions-th.jsonl",
    }, "Only the original Thai question set is in scope"
    seen = set()
    report = {}
    for language, expected, domain in [
        ("th", 20, "pantip.com"),
    ]:
        path = root / f"published-questions-{language}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == expected, (language, len(rows))
        hashes = set()
        for row in rows:
            assert row["id"] not in seen, row["id"]
            seen.add(row["id"])
            digest = hashlib.sha256(row["question_original"].encode()).hexdigest()
            assert digest == row["original_sha256"], row["id"]
            assert digest not in hashes, ("duplicate title", row["id"])
            hashes.add(digest)
            assert urlparse(row["source_url"]).hostname == domain, row["id"]
            assert row["human_review_status"] == "pending", row["id"]
            assert row["evaluation_status"] == "not_run", row["id"]
            assert row["selection_status"] == "candidate_not_held_out", row["id"]
            assert row["input_language"] == language
            assert row.get("gold_answer") is None and row.get("expected_answer") is None
        report[language] = {
            "count": len(rows), "unique_titles": len(hashes),
            "missing_license_metadata": sum(not row.get("source_license") for row in rows),
        }
    print(json.dumps({"input_languages": ["th"], "provenance_checks": report,
                      "evaluation_performed": False}))


if __name__ == "__main__":
    main()
