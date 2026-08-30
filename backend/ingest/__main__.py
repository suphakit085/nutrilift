"""Ingest CLI: knowledge cards + the Thai food table into Postgres.

Usage (from backend/, with the venv active):

    python -m ingest                 # cards + foods, only re-embedding changed cards
    python -m ingest --only cards
    python -m ingest --only foods
    python -m ingest --rebuild       # wipe documents/chunks and re-embed everything

Chunking: knowledge cards are split on markdown headings, then long sections are
split further on blank lines to stay near ``TARGET_CHARS``. Each chunk keeps its
heading so citations can point at a section, not just a file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

import frontmatter
from sqlalchemy import delete, select

from app.db.models import Chunk, Document, Food
from app.db.session import SessionLocal
from app.services.llm import embed_texts

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = REPO_ROOT / "knowledge" / "cards"
FOODS_CSV = REPO_ROOT / "knowledge" / "foods.csv"

TARGET_CHARS = 1200
OVERLAP_CHARS = 150
EMBED_BATCH = 64


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def split_sections(body: str) -> list[tuple[str | None, str]]:
    """Split markdown into (heading, text) sections."""
    matches = list(_HEADING_RE.finditer(body))
    if not matches:
        return [(None, body.strip())]

    sections: list[tuple[str | None, str]] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        sections.append((None, preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[match.end() : end].strip()
        if text:
            sections.append((match.group(2).strip(), text))
    return sections


def split_long(text: str, target: int = TARGET_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split a long section on paragraph boundaries, with a small overlap."""
    if len(text) <= target:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > target:
            parts.append(current)
            current = current[-overlap:] + "\n\n" + paragraph if overlap else paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts


def chunk_card(title: str, body: str) -> list[tuple[str | None, str]]:
    """Return [(heading, chunk_text)]. The card title is prepended to every chunk
    so an isolated chunk still carries its topic into the embedding."""
    chunks: list[tuple[str | None, str]] = []
    for heading, text in split_sections(body):
        for part in split_long(text):
            prefix = f"{title} - {heading}\n" if heading else f"{title}\n"
            chunks.append((heading, prefix + part))
    return chunks


def content_hash(post: frontmatter.Post) -> str:
    payload = f"{post.metadata}\n{post.content}".encode()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def embed_in_batches(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        vectors.extend(embed_texts(batch))
        print(f"    embedded {min(start + EMBED_BATCH, len(texts))}/{len(texts)}")
    return vectors


def ingest_cards(session, *, rebuild: bool = False) -> None:
    if not CARDS_DIR.exists():
        print(f"! no cards directory at {CARDS_DIR}")
        return

    if rebuild:
        session.execute(delete(Chunk))
        session.execute(delete(Document))
        session.commit()
        print("  wiped existing documents and chunks")

    # files starting with "_" are templates/notes, not knowledge
    paths = sorted(p for p in CARDS_DIR.glob("*.md") if not p.name.startswith("_"))
    if not paths:
        print(f"! no .md cards found in {CARDS_DIR}")
        return

    for path in paths:
        post = frontmatter.load(path)
        slug = post.get("slug") or path.stem
        title = post.get("title") or slug
        digest = content_hash(post)

        document = session.execute(
            select(Document).where(Document.slug == slug)
        ).scalar_one_or_none()

        if document is not None:
            unchanged = document.content_hash == digest
            if unchanged and not rebuild:
                print(f"  = {slug} (unchanged)")
                continue
            session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            document.title = title
            document.topic = post.get("topic")
            document.source_refs = post.get("sources") or []
            document.content_hash = digest
        else:
            document = Document(
                slug=slug,
                title=title,
                topic=post.get("topic"),
                source_type="knowledge_card",
                source_refs=post.get("sources") or [],
                lang=post.get("lang", "th"),
                content_hash=digest,
            )
            session.add(document)
            session.flush()

        pieces = chunk_card(title, post.content)
        vectors = embed_in_batches([text for _, text in pieces])
        for index, ((heading, text), vector) in enumerate(zip(pieces, vectors, strict=True)):
            session.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    heading=heading,
                    content=text,
                    embedding=vector,
                    meta={"source_file": path.name},
                )
            )
        session.commit()
        print(f"  + {slug}: {len(pieces)} chunks")


REQUIRED_FOOD_COLUMNS = {
    "name_th",
    "serving_desc",
    "serving_g",
    "kcal",
    "protein_g",
    "carb_g",
    "fat_g",
}


def ingest_foods(session) -> None:
    if not FOODS_CSV.exists():
        print(f"! no foods CSV at {FOODS_CSV}")
        return

    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        print("! foods.csv is empty")
        return

    missing = REQUIRED_FOOD_COLUMNS - set(rows[0])
    if missing:
        print(f"! foods.csv is missing columns: {sorted(missing)}")
        return

    session.execute(delete(Food))
    for row in rows:
        session.add(
            Food(
                name_th=row["name_th"].strip(),
                name_en=(row.get("name_en") or "").strip() or None,
                category=(row.get("category") or "").strip() or None,
                serving_desc=row["serving_desc"].strip(),
                serving_g=float(row["serving_g"]),
                kcal=float(row["kcal"]),
                protein_g=float(row["protein_g"]),
                carb_g=float(row["carb_g"]),
                fat_g=float(row["fat_g"]),
                fiber_g=float(row["fiber_g"]) if (row.get("fiber_g") or "").strip() else None,
                source=(row.get("source") or "").strip() or None,
            )
        )
    session.commit()
    print(f"  + foods: {len(rows)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest knowledge cards and the food table")
    parser.add_argument("--only", choices=["cards", "foods"], help="ingest just one source")
    parser.add_argument(
        "--rebuild", action="store_true", help="delete and re-embed all cards"
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.only in (None, "cards"):
            print("knowledge cards:")
            ingest_cards(session, rebuild=args.rebuild)
        if args.only in (None, "foods"):
            print("food table:")
            ingest_foods(session)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
