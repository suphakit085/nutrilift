"""Turn the published Thai FCD food index PDF into a CSV worklist.

Why: the Online Thai Food Composition Database (INMU) is search-only - there is
no bulk export - so filling knowledge/foods.csv means looking items up one at a
time. INMU does publish the index as a PDF appendix listing every food ID with
its English and Thai names. Converting that to CSV turns "search blindly and
hope the dish exists" into "pick the rows you need, then look up only those".

This extracts *names and IDs only*. It carries no nutrient values - those must
still come from the database itself, with the attribution INMU requires.

    curl -sL -o knowledge/sources/Food_Index.pdf \
        https://inmu.mahidol.ac.th/thaifcd/pdf/Food_Index.pdf
    python tools/extract_thaifcd_index.py

Output: knowledge/sources/thaifcd_index.csv (gitignored - it is INMU's
material, not ours to redistribute; regenerate it locally with the above).

Attribution required by INMU when the data is used:
    Kunchit Judprasong, Prapasri Puwastien, et al. Institute of Nutrition,
    Mahidol University (2025). Thai Food Composition Database, Online version 3,
    August 2025, Thailand. https://inmu.mahidol.ac.th/thaifcd/home
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = REPO_ROOT / "knowledge" / "sources" / "Food_Index.pdf"
CSV_PATH = REPO_ROOT / "knowledge" / "sources" / "thaifcd_index.csv"

#: A row starts with a food ID such as "A124" or "Z7".
ROW_RE = re.compile(r"^([A-Z]\d+)\s+(.*)$")

#: Trailing provenance codes, e.g. "p1", "u1, p88", "t43".
SOURCE_RE = re.compile(r"((?:[a-z]\d+)(?:\s*,\s*[a-z]\d+)*)\s*$")

THAI_RE = re.compile(r"[฀-๿]")

#: Food-group headings that appear between the rows.
GROUP_RE = re.compile(r"^([A-Z])\s+([A-Z][a-z].*)$")

#: Thai vowel signs and tone marks that attach to the preceding consonant.
#: The PDF text layer emits a stray space before each of them, so a dish name
#: extracts as "ข ้าว" and no exact-match search for a real
#: Thai name will ever hit.
THAI_COMBINING = (
    "ัิีึืฺุู"
    "็่้๊๋์ํ๎"
)
STRAY_SPACE_RE = re.compile("[ \t]+([" + THAI_COMBINING + "])")


def normalise_thai(text: str) -> str:
    """Repair PDF extraction artefacts in Thai text.

    Keep the mark and drop only the space in front of it. Dropping the whole
    match instead silently deletes the vowel and turns the word for rice into a
    different word - which still looks like plausible Thai, so it is easy to
    miss unless you check a known dish name afterwards.
    """
    text = STRAY_SPACE_RE.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def split_row(food_id: str, rest: str, group: str) -> dict:
    """Split one index line into its columns.

    The PDF has no delimiters, so the Thai script itself is the boundary: what
    precedes the first Thai character is the English and scientific name, what
    follows is the Thai name plus the trailing source codes.
    """
    match = THAI_RE.search(rest)
    if match:
        english_part = rest[: match.start()].strip()
        thai_part = rest[match.start() :].strip()
    else:
        english_part, thai_part = rest.strip(), ""

    source = ""
    source_match = SOURCE_RE.search(thai_part)
    if source_match:
        source = source_match.group(1).strip()
        thai_part = thai_part[: source_match.start()].strip()

    # A lone "-" stands in for "no scientific name".
    english_part = re.sub(r"\s+-\s*$", "", english_part).strip()

    return {
        "food_id": food_id,
        "group": group,
        "name_en": re.sub(r"\s+", " ", english_part),
        "name_th": normalise_thai(thai_part),
        "source_code": source,
    }


def parse(pdf_path: Path) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    rows: list[dict] = []
    group = ""

    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            line = raw.strip()
            if not line:
                continue

            row_match = ROW_RE.match(line)
            if row_match:
                rows.append(split_row(row_match.group(1), row_match.group(2), group))
                continue

            group_match = GROUP_RE.match(line)
            if group_match and not THAI_RE.search(line):
                # The heading repeats as "... (continued)" at every page break;
                # strip that so each group is one bucket rather than two.
                title = re.sub(r"\s*\(continued\)\s*$", "", group_match.group(2))
                title = re.sub(r"\s{2,}", " ", title).strip()
                group = f"{group_match.group(1)} {title}".strip()

    # The same ID can repeat in page headers; keep the first occurrence.
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        if row["food_id"] in seen:
            continue
        seen.add(row["food_id"])
        unique.append(row)
    return unique


def main() -> int:
    if not PDF_PATH.exists():
        print(f"! not found: {PDF_PATH}")
        print("  download it first:")
        print("  curl -sL -o knowledge/sources/Food_Index.pdf \\")
        print("      https://inmu.mahidol.ac.th/thaifcd/pdf/Food_Index.pdf")
        return 1

    try:
        rows = parse(PDF_PATH)
    except ImportError:
        print("! pypdf is required:  pip install pypdf")
        return 1

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["food_id", "group", "name_en", "name_th", "source_code"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"parsed {len(rows)} food items -> {CSV_PATH.relative_to(REPO_ROOT)}")

    groups: dict[str, int] = {}
    for row in rows:
        key = row["group"] or "(ungrouped)"
        groups[key] = groups.get(key, 0) + 1
    print("\nitems per group:")
    for name, count in sorted(groups.items()):
        print(f"  {count:>5}  {name}")

    missing = sum(1 for r in rows if not r["name_th"])
    if missing:
        print(f"\n! {missing} rows have no Thai name (mostly imported foods) - check by eye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
