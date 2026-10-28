"""The expert review table (docs/calculator-rules-review.csv) must match the code.

Each row that names a constant also records its value; if the calculator
changes, this fails until the table, and so what the expert signed, is updated.
"""

import ast
import csv
import io
import re
from pathlib import Path

from app.services import nutrition, profile_safety

TABLE = Path(__file__).resolve().parents[2] / "docs" / "calculator-rules-review.csv"


def _rows() -> list[dict]:
    return list(csv.DictReader(io.StringIO(TABLE.read_text(encoding="utf-8-sig"))))


def _resolve(name: str):
    match = re.fullmatch(r"(\w+)(?:\['(\w+)'\])?", name)
    assert match, name
    module = nutrition if hasattr(nutrition, match[1]) else profile_safety
    value = getattr(module, match[1])
    return value[match[2]] if match[2] else value


def test_table_values_match_the_calculator():
    checked = 0
    for row in _rows():
        if not row["ค่าคงที่ในโค้ด"]:
            continue
        expected = ast.literal_eval(row["ค่าในโค้ด"])
        assert _resolve(row["ค่าคงที่ในโค้ด"]) == expected, row["รหัส"]
        checked += 1
    assert checked >= 18


def test_maintain_and_bulk_share_the_protein_row():
    # R16 covers both goals with one row.
    assert nutrition.PROTEIN_G_PER_KG["maintain"] == nutrition.PROTEIN_G_PER_KG["bulk"]


def test_unpinned_rules_match_the_code():
    # Rows without a constant: input bounds (R02) and per-gram energy (R23).
    assert nutrition.KCAL_PER_G_PROTEIN == nutrition.KCAL_PER_G_CARB == 4.0
    source = Path(nutrition.__file__).read_text(encoding="utf-8")
    for bound in (
        "120 <= p.height_cm <= 230", "30 <= p.weight_kg <= 300", "3 <= p.body_fat_pct <= 60",
    ):
        assert bound in source
    assert nutrition.MAX_AGE == 100


def test_ids_are_unique_and_review_columns_exist():
    rows = _rows()
    assert len({row["รหัส"] for row in rows}) == len(rows)
    prefixes = ("ความเห็นผู้เชี่ยวชาญ", "ค่าที่เสนอแทน", "เหตุผลหรือหมายเหตุ")
    review = [k for k in rows[0] if k.startswith(prefixes)]
    assert len(review) == 3
