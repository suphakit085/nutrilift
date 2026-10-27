"""Bind the 8 knowledge-base batch 2 cards to their release manifest.

The cards were measured before merge (retrieval simulator plus answer runs, see the
release file's ``evaluation`` entry). Any later edit has to be re-measured, so the
text is pinned here the same way as batch 1 (test_kb_batch1_release).
"""
import hashlib
import json
from pathlib import Path

import frontmatter

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "knowledge/releases/kb-batch2-v1.json"


def _release() -> dict:
    return json.loads(RELEASE.read_text(encoding="utf8"))


def test_batch2_card_text_matches_the_measured_release():
    release = _release()
    assert len(release["cards"]) == 8
    for row in release["cards"]:
        path = ROOT / "knowledge/cards" / (row["card"] + ".md")
        text = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(text).hexdigest() == row["utf8_lf_sha256"], row["card"]


def test_batch2_cards_are_marked_pending_independent_review():
    for row in _release()["cards"]:
        post = frontmatter.load(ROOT / "knowledge/cards" / (row["card"] + ".md"))
        assert post["slug"] == row["card"]
        assert post["review_status"] == "ai_reviewed_pending_independent_review"
        assert post.get("sources"), row["card"]


def test_batch2_cards_stay_coarse_grained():
    # Batch 1 showed that fine-grained cards crowd older cards out of retrieval;
    # batch 2 was written and measured at two sections per card.
    for row in _release()["cards"]:
        post = frontmatter.load(ROOT / "knowledge/cards" / (row["card"] + ".md"))
        headings = [line for line in post.content.splitlines() if line.startswith("# ")]
        assert 1 <= len(headings) <= 3, row["card"]
