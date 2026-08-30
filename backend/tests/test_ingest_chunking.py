"""Tests for the knowledge-card chunker.

No network or database needed - these cover the part of ingest that decides what
a citation will point at.
"""

from ingest.__main__ import TARGET_CHARS, chunk_card, split_long, split_sections


def test_split_sections_splits_on_headings():
    body = "# หัวข้อ 1\nเนื้อหา ก\n\n# หัวข้อ 2\nเนื้อหา ข\n"
    assert split_sections(body) == [("หัวข้อ 1", "เนื้อหา ก"), ("หัวข้อ 2", "เนื้อหา ข")]


def test_split_sections_keeps_preamble_without_heading():
    sections = split_sections("บทนำ\n\n# หัวข้อ\nเนื้อหา")
    assert sections[0] == (None, "บทนำ")
    assert sections[1] == ("หัวข้อ", "เนื้อหา")


def test_split_sections_without_headings():
    assert split_sections("ข้อความล้วน") == [(None, "ข้อความล้วน")]


def test_split_sections_drops_empty_sections():
    sections = split_sections("# ว่าง\n\n# มีเนื้อหา\nข้อความ")
    assert sections == [("มีเนื้อหา", "ข้อความ")]


def test_split_long_returns_single_part_when_short():
    assert split_long("สั้น") == ["สั้น"]


def test_split_long_splits_on_paragraphs():
    paragraph = "ก" * 500
    parts = split_long("\n\n".join([paragraph] * 5), target=1200, overlap=100)
    assert len(parts) > 1
    assert all(len(part) <= 1200 + 100 + 500 for part in parts)


def test_split_long_overlaps_between_parts():
    paragraph = "ก" * 500
    parts = split_long("\n\n".join([paragraph] * 4), target=1000, overlap=50)
    # every part after the first starts with the tail of the previous one
    assert parts[1].startswith(parts[0][-50:])


def test_chunk_card_prefixes_title_and_heading():
    chunks = chunk_card("การ์ดทดสอบ", "# หัวข้อย่อย\nเนื้อหา")
    assert len(chunks) == 1
    heading, text = chunks[0]
    assert heading == "หัวข้อย่อย"
    assert text.startswith("การ์ดทดสอบ - หัวข้อย่อย\n")
    assert "เนื้อหา" in text


def test_chunk_card_prefixes_title_when_no_heading():
    heading, text = chunk_card("การ์ดทดสอบ", "เนื้อหาล้วน")[0]
    assert heading is None
    assert text.startswith("การ์ดทดสอบ\n")


def test_chunk_card_indexes_are_contiguous_for_long_cards():
    body = "# หัวข้อ\n" + "\n\n".join(["ย่อหน้า " + "ก" * 400] * 6)
    chunks = chunk_card("การ์ดยาว", body)
    assert len(chunks) > 1
    assert all(heading == "หัวข้อ" for heading, _ in chunks)


def test_real_cards_produce_chunks():
    """The three seed cards must chunk into something retrievable."""
    from pathlib import Path

    import frontmatter

    cards_dir = Path(__file__).resolve().parents[2] / "knowledge" / "cards"
    files = [p for p in cards_dir.glob("*.md") if not p.name.startswith("_")]
    assert files, "no knowledge cards found"

    for path in files:
        post = frontmatter.load(path)
        assert post.get("slug"), f"{path.name} missing slug"
        assert post.get("title"), f"{path.name} missing title"
        assert post.get("sources"), f"{path.name} missing sources"

        chunks = chunk_card(post["title"], post.content)
        assert chunks, f"{path.name} produced no chunks"
        for _, text in chunks:
            assert text.strip()
            assert len(text) <= TARGET_CHARS * 2
