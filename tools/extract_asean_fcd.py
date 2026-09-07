"""Extract Thai foods and their nutrient values from the ASEAN Food Composition
Database PDF into a CSV.

Why this source: the Online Thai FCD is search-only, and the Department of
Health's own 148-page table is a scan with no text layer. The ASEAN Food
Composition Database - published by the same institute (INMU, as ASEANFOODS
regional centre) - is the one machine-readable table available, and its Thai
entries carry Thai names and are marked "(TH)".

Column order is fixed by the table header, verified against foods whose values
are independently known:

    Chicken, breast, w/ skin, raw  -> 152 kcal, 19.9 g protein, 8.0 g fat
    Egg, hen, whole, boiled       -> 152 kcal, 13.4 g protein, 10.4 g fat

All values are per 100 g edible portion.

    curl -sL -o knowledge/sources/ASEAN-FCD-v1-2014.pdf \
        https://inmu.mahidol.ac.th/aseanfoods/doc/OnlineASEAN_FCD_V1_2014.pdf
    python tools/extract_asean_fcd.py

Output: knowledge/sources/asean_thai_foods.csv (gitignored - INMU's data, not
ours to redistribute; regenerate locally).

Attribution required:
    Institute of Nutrition, Mahidol University. ASEAN Food Composition
    Database, Electronic version 1, February 2014. ASEANFOODS Regional Centre
    and INFOODS Regional Database Centre.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# One definition of the สระอำ rule, shared with the retrieval and food-lookup
# code, so the CSV and the queries run against it can never drift apart.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.thai_text import compose_sara_am

REPO_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = REPO_ROOT / "knowledge" / "sources" / "ASEAN-FCD-v1-2014.pdf"
CSV_PATH = REPO_ROOT / "knowledge" / "sources" / "asean_thai_foods.csv"

#: Order of the value columns, taken from the table header.
COLUMNS = [
    "density", "kcal", "water_g", "protein_g", "fat_g", "carb_g", "fiber_g",
    "ash_g", "ca_mg", "p_mg", "na_mg", "k_mg", "fe_mg", "cu_mg", "zn_mg",
    "retinol_mcg", "carotene_mcg", "vita_rae_mcg", "b1_mg", "b2_mg",
    "niacin_mg", "vitc_mg",
]

#: A food record starts with an ASEAN-style ID: two-or-three letters then digits.
FOOD_ID_RE = re.compile(r"^([A-Z]{2,3}[A-Z]?\d+)\b")

#: One value cell: a number, a dash for "not measured", or a trace marker such
#: as "0p" / "tr". Trailing letters flag how the value was derived.
CELL = r"(?:-|tr|\d+(?:\.\d+)?[a-z]*)"
VALUES_RE = re.compile(rf"((?:{CELL}\s+){{15,}}{CELL})\s*$")

THAI_RE = re.compile(r"[฀-๿]")

#: The PDF is full of non-breaking spaces, which silently defeat both plain
#: string matching and whitespace patterns. Named rather than written inline
#: so the character is never invisible in this file.
NBSP = chr(0xA0)


#: In some rows the PDF's text layer breaks each number into single characters,
#: so "4.74" arrives as "4 . 7 4". Those rows parse into meaningless cells that
#: can still pass a tolerance check by luck, which is worse than failing loudly.
#: A bare "." among the cells is the giveaway.
FRAGMENTED_RE = re.compile(r"(?:^|\s)\.(?:\s|$)")


def is_fragmented(values: str) -> bool:
    """True when the text layer split numbers into separate characters."""
    if FRAGMENTED_RE.search(values):
        return True
    cells = values.split()
    if len(cells) < 8:
        return False
    # A healthy row is mostly multi-character cells; a shattered one is not.
    singles = sum(1 for c in cells if len(c) == 1 and c not in {"-", "0"})
    return singles > len(cells) * 0.4


def parse_cell(raw: str) -> str:
    """Turn one table cell into a plain number, or "" when unmeasured."""
    if raw in {"-", "tr"}:
        return ""
    m = re.match(r"^(\d+(?:\.\d+)?)", raw)
    return m.group(1) if m else ""


def thai_name(text: str) -> str:
    """Pull the Thai name out of a block of alternate names.

    Names are comma-joined per country and tagged, e.g.
    "Daging ayam(MY), Manok pitso(PH), ไก่, อก, ดิบ(TH)". The Thai one is the
    run of Thai text immediately before the "(TH)" tag.
    """
    idx = text.find("(TH)")
    if idx == -1:
        return ""
    head = text[:idx]
    start = None
    for i in range(len(head) - 1, -1, -1):
        if THAI_RE.match(head[i]) or head[i] in ", .()/-0123456789" or head[i].isspace():
            start = i
        elif start is not None:
            break
    if start is None:
        return ""
    name = head[start:]
    # The PDF sprinkles spaces inside Thai words - before vowel signs and tone
    # marks, and sometimes mid-syllable. Thai is written without spaces, so a
    # space with a Thai letter on both sides is always an artefact. Commas and
    # Latin text are unaffected, so "ไก่, อก, ดิบ" keeps its separators.
    name = re.sub(r"(?<=[ก-๛])[ \t]+(?=[ก-๛])", "", name)
    name = re.sub(r"\s+", " ", name)
    # ...and a space before the comma survives that rule, because the character
    # on its left is a comma rather than a Thai letter: "ถั่วพุ่ม , ฝักสด".
    name = re.sub(r"\s+,", ",", name)
    # Drop punctuation left over from the preceding country tag, e.g. "), ไก่".
    name = re.sub(r"^[\s,)\-.]+", "", name)
    # The PDF writes สระอำ decomposed, as นิคหิต + สระอา ("นํ้า", "มันสําปะหลัง").
    # Composing it here rather than in the finished foods.csv is the difference
    # between a fix that survives and one that does not: this pipeline is
    # re-runnable, so a correction applied only downstream is undone the next
    # time anyone follows the documented steps.
    return compose_sara_am(name.strip(" ,"))


def energy_is_consistent(row: dict, tolerance: float = 0.25) -> bool:
    """Does the stated energy match its own macronutrients?

    4 kcal/g for protein and carbohydrate, 9 for fat, and 2 for dietary fibre.

    The fibre term is not optional. This table's carbohydrate column is
    *available* carbohydrate, with fibre listed separately, and its energy
    column counts that fibre at roughly 2 kcal/g - the value INMU publishes.
    Three rows pin it down exactly:

        AAC72 ถั่วแดง, เมล็ดแห้ง  4(22.5+33.9) + 9(2.1) + 2(27.8) = 300.1, table says 300
        AAN4  พริกขี้หนู          4(3.7+2.9)  + 9(1.1) + 2(9.9)  =  56.1, table says 56
        THN8  ขมิ้น               4(1.1+4.4)  + 9(0.3) + 2(6.5)  =  37.7, table says 38

    Leaving fibre out made every high-fibre food fail this check *at its
    correct alignment*, and ``realign`` then shifted it into whatever offset
    happened to pass - silently publishing wrong numbers under a real source
    ID. That corrupted three of the four rows it "repaired": พริกขี้หนู was
    written as 81 kcal instead of 56, ขมิ้น as 87 instead of 38.
    """
    try:
        kcal = float(row["kcal"])
        protein = float(row["protein_g"] or 0)
        fat = float(row["fat_g"] or 0)
        carb = float(row["carb_g"] or 0)
        fibre = float(row["fiber_g"] or 0)
    except (TypeError, ValueError):
        return False
    if kcal <= 0:
        return False
    computed = 4 * protein + 4 * carb + 9 * fat + 2 * fibre
    if computed == 0:
        return False
    return abs(computed - kcal) / kcal <= tolerance


def apply_cells(row: dict, cells: list[str], offset: int = 0) -> dict:
    """Map raw value cells onto the named columns, optionally shifted.

    Every column is written even when the shift runs the cells short, so a
    caller can always read all of them back.
    """
    shifted = cells[offset:] if offset > 0 else ([""] * -offset + cells)
    for i, column in enumerate(COLUMNS):
        row[column] = parse_cell(shifted[i]) if i < len(shifted) else ""
    return row


def realign(row: dict) -> bool:
    """Try to repair a row whose columns slipped, and report whether it worked.

    When a line wraps in the PDF, the captured run of values can start one or
    two columns late, so every value lands under the wrong heading. Rather than
    guess, each candidate shift is tested against the same checks used to detect
    the problem, mass balance included - shifting is how a row gets corrupted,
    so it is exactly where the weaker energy-only test could not be trusted.
    """
    cells = row.get("_cells") or []
    for offset in (-1, 1, -2, 2):
        candidate = dict(row)
        apply_cells(candidate, cells, offset)
        if (
            energy_is_consistent(candidate)
            and plausible(candidate)
            and mass_balances(candidate)
        ):
            row.update({k: candidate[k] for k in COLUMNS})
            row["_realigned"] = str(offset)
            return True
    return False


def plausible(row: dict) -> bool:
    """Reject physically impossible values, whatever the alignment says."""
    try:
        kcal = float(row["kcal"])
        macros = [float(row[k] or 0) for k in ("protein_g", "fat_g", "carb_g")]
    except (TypeError, ValueError):
        return False
    return 0 < kcal <= 950 and all(0 <= m <= 100 for m in macros)


#: How far the constituents may stray from 100 g and still be believed.
#: Drinks are the reason this is not tighter: the table gives them per 100 *ml*,
#: so a 1.05-density soft drink legitimately sums to ~106 g.
MASS_BALANCE_TOLERANCE = 8.0


def mass_balances(row: dict) -> bool:
    """Do water, protein, fat, carbohydrate, fibre and ash add up to 100 g?

    A far stronger alignment test than energy alone. Energy is one number
    derived from four others, so a shifted row can satisfy it by coincidence -
    and three of them did. This constrains six independent columns at once,
    which a wrong shift has essentially no way to satisfy: the shifted
    พริกขี้หนู summed to 42.8 g, ขมิ้น to 63.3 g.

    Rows whose water column the PDF never carried cannot be checked, and are
    left to the energy test rather than dropped.
    """
    try:
        water = float(row["water_g"] or 0)
    except (TypeError, ValueError):
        return True
    if water <= 0:
        return True
    try:
        parts = [float(row[k] or 0) for k in ("protein_g", "fat_g", "carb_g", "fiber_g", "ash_g")]
    except (TypeError, ValueError):
        return True
    return abs(water + sum(parts) - 100.0) <= MASS_BALANCE_TOLERANCE


def parse(pdf_path: Path) -> list[dict]:
    """Read every data row out of the table pages.

    The page is first cut into *records* at each line that starts a new ASEAN
    food ID, then each record is parsed on its own. An earlier version streamed
    line by line and kept a rolling buffer, which produced a genuinely dangerous
    bug: the values of "Egg, hen, white" were published under the Thai name for
    "Egg, hen, steamed", because the ID came from one record's continuation line
    while the Thai name was still in the buffer from the record before it.
    A wrong label on right numbers is worse than a missing row, so identity and
    values now have to come from the same block or the row is dropped.

    Non-breaking spaces are normalised first; the PDF is full of them and they
    silently defeat both plain string matching and whitespace patterns.
    """
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    records: list[dict] = []

    for page in reader.pages:
        text = (page.extract_text() or "").replace(NBSP, " ")
        if "composition per 100" not in text:
            continue

        # Cut the page into blocks, each starting at a line whose first token is
        # an ASEAN food ID (AA*, or a country ID when that food has no AA entry).
        blocks: list[list[str]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if FOOD_ID_RE.match(line):
                blocks.append([line])
            elif blocks:
                blocks[-1].append(line)

        for block in blocks:
            record = parse_block(block)
            if record:
                records.append(record)

    return records


def parse_block(block: list[str]) -> dict | None:
    """Parse one food record. Returns None when the block is unusable."""
    joined = " ".join(block)

    values_match = VALUES_RE.search(joined)
    if not values_match or is_fragmented(values_match.group(1)):
        return None

    head = FOOD_ID_RE.match(block[0])
    if not head:
        return None
    food_id = head.group(1)

    names = joined[head.end(): values_match.start()]
    row = {
        "food_id": food_id,
        "name_en": clean_english(names),
        "name_th": thai_name(names),
    }
    cells = values_match.group(1).split()
    row["_cells"] = cells
    apply_cells(row, cells)
    return row


#: Alternate-ID lists such as "VNF265,PHF003" sit between the ID and the name.
ALT_IDS_RE = re.compile(r"^(?:\([A-Z]\)\s*)?(?:[A-Z]{2,3}\d+[,\s]*)+")


def clean_english(text: str) -> str:
    """Strip alternate country IDs and country-tagged names off the English name.

    A record's first line often continues with more IDs - "AAH14 PHH002,MYH390
    THH1,VNH371 Egg, hen, white" - so IDs are stripped repeatedly until the text
    stops shrinking and what is left starts with the name itself.
    """
    text = text.strip()
    for _ in range(4):
        stripped = ALT_IDS_RE.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    # Everything from the first country-tagged alternate name onwards is not
    # part of the English name.
    text = re.split(r"\([A-Z]{2}\)", text)[0]
    # Alternate names in other scripts get appended without a tag.
    thai_start = THAI_RE.search(text)
    if thai_start:
        text = text[: thai_start.start()]
    return re.sub(r"\s+", " ", text).strip(" ,")


def main() -> int:
    if not PDF_PATH.exists():
        print(f"! not found: {PDF_PATH}")
        print("  curl -sL -o knowledge/sources/ASEAN-FCD-v1-2014.pdf \\")
        print("      https://inmu.mahidol.ac.th/aseanfoods/doc/OnlineASEAN_FCD_V1_2014.pdf")
        return 1

    try:
        rows = parse(PDF_PATH)
    except ImportError:
        print("! pypdf is required:  pip install pypdf")
        return 1

    # The same food can appear on more than one page; keep the first.
    seen: set[str] = set()
    unique = []
    for row in rows:
        if row["food_id"] in seen:
            continue
        seen.add(row["food_id"])
        unique.append(row)

    thai = [r for r in unique if r["name_th"] and r["name_en"]]
    complete = [r for r in thai if r.get("kcal") and r.get("protein_g") and r.get("fat_g")]
    usable, rejected, repaired = [], [], 0
    for row in complete:
        if energy_is_consistent(row) and plausible(row) and mass_balances(row):
            usable.append(row)
        elif realign(row):
            usable.append(row)
            repaired += 1
        else:
            rejected.append(row)

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["food_id", "name_en", "name_th", *COLUMNS]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(usable)

    print(f"records parsed         : {len(rows)}")
    print(f"unique food ids        : {len(unique)}")
    print(f"with Thai + English    : {len(thai)}")
    print(f"with kcal/protein/fat  : {len(complete)}")
    print(f"energy check passed    : {len(usable)} (of which {repaired} needed a column shift)")
    print(f"written                : {CSV_PATH.relative_to(REPO_ROOT)}")
    if rejected:
        print()
        print(f"rejected {len(rejected)} row(s) failing the energy or 100 g mass-balance check")
        print("(usually a column that slipped in the PDF text layer):")
        for row in rejected[:8]:
            print(f"  {row['food_id']:<9} {row['name_en'][:34]:<36} "
                  f"kcal={row['kcal']} P={row['protein_g']} F={row['fat_g']} C={row['carb_g']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
