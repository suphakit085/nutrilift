"""A card's `sources` are shown to the reader, so they must be citations.

The citation panel prints each entry verbatim next to the answer. One card had
been citing itself - "ตัวเลข...มาจากฐานข้อมูล foods.csv ของระบบ ... ดูที่มารายรายการ
ใน knowledge/README.md" - which named two files nobody outside this repo can
open. Seen in the panel while driving the web UI on 7 ก.ย. 2569; the same class
of leak as rule 10 of the system prompt, which forbids the model printing
internal names, only here it came from our own data rather than the model.
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import pytest

CARDS = sorted(
    p for p in (Path(__file__).resolve().parents[2] / "knowledge" / "cards").glob("*.md")
    if not p.name.startswith("_")
)

#: A file name, a repo path, or a snake_case identifier - each a thing the
#: reader of a citation cannot look up.
INTERNAL = re.compile(
    r"[\w/]+\.(?:csv|md|py|ts|tsx|json|ya?ml)\b"
    r"|(?:knowledge|backend|frontend|eval|tools)/"
    r"|\b[a-z]+_[a-z_]+\b"
)


def test_there_are_cards_to_check():
    assert len(CARDS) >= 20


@pytest.mark.parametrize("card", CARDS, ids=[c.stem for c in CARDS])
def test_every_citation_is_something_a_reader_can_look_up(card: Path):
    sources = frontmatter.loads(card.read_text(encoding="utf-8")).get("sources") or []
    assert sources, f"{card.name} has no sources"
    for source in sources:
        found = INTERNAL.search(str(source))
        assert not found, f"{card.name} cites {found.group(0)!r}, which is internal: {source}"


@pytest.mark.parametrize("card", CARDS, ids=[c.stem for c in CARDS])
def test_a_citation_names_a_publication_not_our_own_database(card: Path):
    sources = frontmatter.loads(card.read_text(encoding="utf-8")).get("sources") or []
    for source in sources:
        assert "ของระบบ" not in str(source), (
            f"{card.name} cites this project's own database rather than the "
            f"published source it came from: {source}"
        )
