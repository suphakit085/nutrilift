"""Bind the 11 knowledge-base batch 1 cards to their release manifest.

The cards were measured before merge (retrieval simulator plus answer runs, see the
release file's ``evaluation`` entry). Any later edit has to be re-measured, so the
text is pinned here the same way the v9 cards are pinned in test_claim_release.
"""
import hashlib
import json
from pathlib import Path

import frontmatter

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "knowledge/releases/kb-batch1-v1.json"


def _release() -> dict:
    return json.loads(RELEASE.read_text(encoding="utf8"))


def test_batch1_card_text_matches_the_measured_release():
    release = _release()
    assert len(release["cards"]) == 11
    for row in release["cards"]:
        path = ROOT / "knowledge/cards" / (row["card"] + ".md")
        text = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(text).hexdigest() == row["utf8_lf_sha256"], row["card"]


def test_batch1_cards_are_marked_pending_independent_review():
    for row in _release()["cards"]:
        post = frontmatter.load(ROOT / "knowledge/cards" / (row["card"] + ".md"))
        assert post["slug"] == row["card"]
        assert post["review_status"] == "ai_reviewed_pending_independent_review"
        assert post.get("sources"), row["card"]


def test_batch1_cards_stay_coarse_grained():
    # v1 of these cards had 4-6 headings each and their 50 chunks crowded older
    # cards out of retrieval (8 labelled eval questions lost their card). Two or
    # three self-contained sections per card is what was measured.
    for row in _release()["cards"]:
        post = frontmatter.load(ROOT / "knowledge/cards" / (row["card"] + ".md"))
        headings = [line for line in post.content.splitlines() if line.startswith("# ")]
        assert 1 <= len(headings) <= 3, row["card"]
