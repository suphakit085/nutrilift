"""Build knowledge/foods.csv from the extracted ASEAN data, keeping any
hand-entered dishes the source does not cover.

The chatbot must never state a calorie figure it cannot attribute, so every row
this writes carries a `source` column. Rows sourced from ASEAN are real,
published values that passed the energy-vs-macros check in
tools/extract_asean_fcd.py. Rows the source has no entry for keep whatever
placeholder marker they already had, so `TOVERIFY-*` still means "not yet real".

ASEAN publishes per 100 g edible portion, so those rows are written with
serving_desc "100 กรัม". Composite Thai dishes such as ข้าวมันไก่ are not in the
ASEAN table at all and stay as they were - they need a per-serving source.

    python tools/extract_asean_fcd.py     # produces the CSV this reads
    python tools/build_foods_csv.py

Attribution carried in the source column:
    ASEAN-FCD-2014-INMU
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASEAN_CSV = REPO_ROOT / "knowledge" / "sources" / "asean_thai_foods.csv"
FOODS_CSV = REPO_ROOT / "knowledge" / "foods.csv"

FIELDS = [
    "name_th", "name_en", "category", "serving_desc", "serving_g",
    "kcal", "protein_g", "carb_g", "fat_g", "fiber_g", "source",
]

#: ASEAN food IDs start with a letter for the group; map it to a Thai label.
GROUP_LABELS = {
    "A": "ข้าว-แป้ง",
    "B": "หัวและมันต่าง ๆ",
    "C": "ถั่วและเมล็ด",
    "D": "ผัก",
    "E": "ผลไม้",
    "F": "เนื้อสัตว์",
    "G": "ปลาและอาหารทะเล",
    "H": "ไข่",
    "J": "นมและผลิตภัณฑ์",
    "K": "น้ำมันและไขมัน",
    "M": "น้ำตาลและขนมหวาน",
    "N": "เครื่องปรุง",
    "Q": "เครื่องดื่ม",
    "S": "อาหารจานด่วน",
    "T": "อาหารจานเดียว",
    "U": "อื่น ๆ",
}

GROUP_RE = re.compile(r"^[A-Z]{2,3}([A-Z])\d+$")

#: The exact shape of a source string this script writes: the prefix, a colon,
#: and a bare food ID with nothing after it.
GENERATED_SOURCE_RE = re.compile(r"^ASEAN-FCD-2014-INMU:[A-Z0-9]+$")

#: The serving every generated row carries, because ASEAN publishes per 100 g.
GENERATED_SERVING = "100 กรัม"


def is_generated(row: dict) -> bool:
    """Was this row written by a previous run of this script?

    Only rows this script produced may be thrown away and rebuilt. Deciding
    that by source *prefix* alone was wrong and quietly destructive: a
    hand-entered household serving cites an ASEAN ID too - ข้าวสวย 1 ทัพพี is
    MYA14 scaled to 60 g - so a rebuild deleted four curated rows, ข้าวสวย
    among them, and nothing said so. A generated row is recognised by its whole
    shape instead: the per-100 g serving *and* a bare, un-annotated source.
    """
    source = (row.get("source") or "").strip()
    serving = (row.get("serving_desc") or "").strip()
    return serving == GENERATED_SERVING and bool(GENERATED_SOURCE_RE.match(source))


def category_for(food_id: str) -> str:
    match = GROUP_RE.match(food_id)
    return GROUP_LABELS.get(match.group(1), "") if match else ""


def round_or_blank(value: str, digits: int = 1) -> str:
    if not value:
        return ""
    try:
        return f"{round(float(value), digits):g}"
    except ValueError:
        return ""


def load_existing() -> list[dict]:
    if not FOODS_CSV.exists():
        return []
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    if not ASEAN_CSV.exists():
        print(f"! not found: {ASEAN_CSV}")
        print("  run tools/extract_asean_fcd.py first")
        return 1

    with ASEAN_CSV.open(encoding="utf-8-sig", newline="") as handle:
        asean = list(csv.DictReader(handle))

    rows: list[dict] = []
    names: set[str] = set()
    for item in asean:
        name = item["name_th"].strip()
        # A few entries share a Thai name after cleanup; keep the first.
        if not name or name in names:
            continue
        names.add(name)
        rows.append(
            {
                "name_th": name,
                "name_en": item["name_en"].strip(),
                "category": category_for(item["food_id"]),
                "serving_desc": "100 กรัม",
                "serving_g": "100",
                "kcal": round_or_blank(item["kcal"], 0),
                "protein_g": round_or_blank(item["protein_g"]),
                "carb_g": round_or_blank(item["carb_g"]),
                "fat_g": round_or_blank(item["fat_g"]),
                "fiber_g": round_or_blank(item["fiber_g"]),
                "source": f"ASEAN-FCD-2014-INMU:{item['food_id']}",
            }
        )

    # Keep everything this script did not write itself. Rows it wrote on a
    # previous run are regenerated, so carrying them over would duplicate the
    # whole ASEAN set every time the extractor's name cleanup changed slightly.
    existing = load_existing()
    kept = [
        r
        for r in existing
        if not is_generated(r) and r.get("name_th", "").strip() not in names
    ]
    # A row the extractor has stopped producing disappears here, and that is the
    # case worth announcing - MYB73 (แป้งมันสำปะหลัง) went precisely because its
    # values turned out to be impossible. Say out loud what left the file.
    current_ids = {item["food_id"] for item in asean}
    dropped = [
        r
        for r in existing
        if is_generated(r) and r["source"].split(":")[-1] not in current_ids
    ]

    FOODS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with FOODS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        writer.writerows(kept)

    still_placeholder = sum(1 for r in kept if "TOVERIFY" in (r.get("source") or ""))
    print(f"from ASEAN (real values) : {len(rows)}")
    print(f"kept from previous file  : {len(kept)}  (of which {still_placeholder} still TOVERIFY)")
    print(f"total rows               : {len(rows) + len(kept)}")
    print(f"written                  : {FOODS_CSV.relative_to(REPO_ROOT)}")
    if dropped:
        print()
        print(f"removed {len(dropped)} row(s) the extractor no longer accepts:")
        for row in dropped:
            print(f"  {row['name_th']}  ({row['source']})")
    if still_placeholder:
        print("\nstill needing a real source (composite dishes ASEAN does not list):")
        for row in kept:
            if "TOVERIFY" in (row.get("source") or ""):
                print(f"  {row['name_th']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
