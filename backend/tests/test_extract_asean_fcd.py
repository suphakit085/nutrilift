"""Guards on the ASEAN PDF extractor's column-alignment checks.

The extractor lives in tools/ and needs the 900 KB source PDF to run end to
end, so what is locked here is the part that decides whether a row's columns
line up - the part that was wrong, and that no test would have noticed.

The bug (found 7 ก.ย. 2569): the energy check used plain Atwater 4/4/9. This
table lists *available* carbohydrate with fibre in its own column and counts
that fibre at ~2 kcal/g, so every high-fibre food failed the check while
correctly aligned. ``realign`` then shifted the row until something passed, and
published wrong numbers under a real INMU source ID - พริกขี้หนู as 81 kcal
instead of 56, ขมิ้น as 87 instead of 38.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "extract_asean_fcd.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_asean_fcd", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = _load()


def row(**values) -> dict:
    """One table row, defaulting every column the checks read to blank."""
    base = dict.fromkeys(extract.COLUMNS, "")
    base.update({k: str(v) for k, v in values.items()})
    return base


#: Real rows, transcribed from the PDF, all correctly aligned as written.
HIGH_FIBRE_ROWS = [
    ("AAN4 พริกขี้หนู", row(kcal=56, water_g=81.2, protein_g=3.7, fat_g=1.1, carb_g=2.9,
                           fiber_g=9.9, ash_g=1.2)),
    ("THN8 ขมิ้น", row(kcal=38, water_g=86.7, protein_g=1.1, fat_g=0.3, carb_g=4.4,
                       fiber_g=6.5, ash_g=1.0)),
    ("AAC72 ถั่วแดง, เมล็ดแห้ง", row(kcal=300, water_g=9.7, protein_g=22.5, fat_g=2.1,
                                     carb_g=33.9, fiber_g=27.8, ash_g=4.0)),
]

#: The two that plain 4/4/9 rejected outright, and so actually got corrupted.
#: ถั่วแดง is off by 18.5% - inside the old tolerance, which is why a dried
#: legume survived while a fresh chilli did not.
CORRUPTED_BY_THE_OLD_CHECK = HIGH_FIBRE_ROWS[:2]


@pytest.mark.parametrize("name,record", HIGH_FIBRE_ROWS, ids=[n for n, _ in HIGH_FIBRE_ROWS])
def test_high_fibre_rows_are_accepted_as_they_stand(name, record):
    assert extract.energy_is_consistent(record), (
        f"{name} is correctly aligned; rejecting it is what sends realign() hunting "
        "for a shift that corrupts the row"
    )


@pytest.mark.parametrize("name,record", HIGH_FIBRE_ROWS, ids=[n for n, _ in HIGH_FIBRE_ROWS])
def test_high_fibre_rows_balance_to_100_g(name, record):
    assert extract.mass_balances(record)


def test_energy_check_would_fail_without_the_fibre_term():
    """The regression is only guarded if 4/4/9 really does reject these rows."""
    for name, record in CORRUPTED_BY_THE_OLD_CHECK:
        kcal = float(record["kcal"])
        atwater = (
            4 * float(record["protein_g"])
            + 4 * float(record["carb_g"])
            + 9 * float(record["fat_g"])
        )
        assert abs(atwater - kcal) / kcal > 0.25, f"{name} no longer demonstrates the bug"


def test_fibre_is_worth_about_two_kcal_per_gram_in_this_table():
    """Where the 2 comes from: it is measured off the table, not assumed."""
    for name, record in HIGH_FIBRE_ROWS:
        stated = float(record["kcal"])
        computed = (
            4 * float(record["protein_g"])
            + 4 * float(record["carb_g"])
            + 9 * float(record["fat_g"])
            + 2 * float(record["fiber_g"])
        )
        assert abs(computed - stated) <= 1.0, f"{name}: {computed} vs {stated}"


def test_shifted_row_is_rejected_by_mass_balance():
    """The exact corruption that shipped: พริกขี้หนู's cells shifted one left."""
    shifted = row(kcal=81.2, water_g=3.7, protein_g=1.1, fat_g=2.9, carb_g=9.9,
                  fiber_g=1.2, ash_g=24)
    assert extract.energy_is_consistent(shifted), (
        "this shift passes the energy check by coincidence - that is the whole problem"
    )
    assert not extract.mass_balances(shifted), "42.8 g per 100 g must not be believed"


def test_realign_leaves_a_correct_row_alone():
    cells = "- 56 81.2 3.7 1.1 2.9 9.9 1.2 24 95 22 461 1.2 0.19 0.4 0 1106 92 0.22 0.06 1.10 52"
    record = row()
    record["_cells"] = cells.split()
    extract.apply_cells(record, record["_cells"])
    assert record["kcal"] == "56"
    assert extract.energy_is_consistent(record) and extract.mass_balances(record)


def test_realign_still_repairs_a_genuinely_shifted_row():
    """ผักตำลึง (AAD58) really is shifted in the PDF, and must still be rescued."""
    record = row()
    # As captured: the run of cells begins one column early, so 26 lands under
    # density and every later value is one heading to the left.
    cells = "26 91.0 3.6 0.2 1.2 2.7 1.3 57"
    record["_cells"] = cells.split()
    extract.apply_cells(record, record["_cells"])
    assert record["kcal"] == "91.0" and not extract.mass_balances(record)
    assert extract.realign(record)
    assert record["_realigned"] == "-1"
    assert record["kcal"] == "26"
    assert record["water_g"] == "91.0"
    assert extract.mass_balances(record)


def test_drinks_measured_per_100_ml_are_not_rejected():
    """Sums to ~106 g because the table gives drinks per 100 ml, not per 100 g."""
    orange_juice = row(kcal=56, water_g=91.1, protein_g=0.6, fat_g=0.1, carb_g=13.1,
                       fiber_g=0.1, ash_g=0.5)
    assert extract.mass_balances(orange_juice)


def test_row_without_a_water_column_is_left_to_the_energy_check():
    assert extract.mass_balances(row(kcal=100, protein_g=5, fat_g=1, carb_g=18))


def test_sara_am_is_composed_in_the_extracted_name():
    """The PDF writes ำ decomposed; composing it downstream did not survive a rebuild."""
    assert extract.thai_name("Ubi Kayu(MY), มันสําปะหลัง(TH)") == "มันสำปะหลัง"


def test_space_before_a_comma_is_dropped_from_the_name():
    assert extract.thai_name("Kacang(MY), ถั่วพุ่ม , ฝักสด(TH)") == "ถั่วพุ่ม, ฝักสด"
