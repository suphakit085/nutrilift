"""Source-bound regressions for every active food and the authorized corrections."""

import csv
import hashlib
import io
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.foods import _row_to_dict
from app.services.meal_plan import build_day_plan
from ingest import __main__ as ingest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from extract_asean_fcd import FOOD_ID_RE, parse  # noqa: E402


def rows(path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


ACTIVE = rows(ROOT / "knowledge/foods.csv")
PRE_REMOVAL = rows(ROOT / "knowledge/evidence/food-fixes-v6/foods.csv")
ACTIVE_BY_NAME = {row["name_th"]: row for row in ACTIVE}
AUDIT = [
    json.loads(s)
    for s in (ROOT / "knowledge/evidence/food-audit-v1/rows.jsonl")
    .read_text(encoding="utf8")
    .splitlines()
]


@lru_cache
def source_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_audit_row(index):
    # Frozen audit positions identify the prior row, not the current CSV's
    # position: removing a food must not shift checks onto another food.
    return ACTIVE_BY_NAME[PRE_REMOVAL[index]["name_th"]]


def test_bubble_tea_removal_preserves_every_other_source_and_nutrient():
    assert len(ACTIVE) == 386
    remaining = [r for r in PRE_REMOVAL if r["name_th"] != "ชานมไข่มุก"]
    for previous, active in zip(remaining, ACTIVE, strict=True):
        if active["source"] == "FINELI-THL:33026":
            previous, active = dict(previous), dict(active)
            previous.pop("nutrition_meta")
            active.pop("nutrition_meta")
        assert previous == active
    assert all(r["source"] != "TOVERIFY-LABEL" for r in ACTIVE)


@pytest.mark.parametrize("row", ACTIVE, ids=[r["source"] for r in ACTIVE])
def test_every_food_has_valid_values_and_bound_primary_source_or_quarantine(row):
    meta = json.loads(row["nutrition_meta"])
    assert meta["human_review_status"] == "pending"
    assert row["name_th"] and float(row["serving_g"]) > 0
    for key in ("kcal", "protein_g", "carb_g", "fat_g"):
        assert 0 <= float(row[key]) < float("inf")
    if meta["verification_status"] in {"unverified", "proxy_unverified"}:
        assert row["source"] in {"FINELI-THL:33026", "ASEAN-FCD-2014-INMU:AAH14", "TOVERIFY-LABEL"}
    else:
        source = ROOT / meta["source_path"]
        assert source.resolve().is_relative_to(ROOT)
        assert source_hash(source) == meta["source_sha256"]
    if meta["fiber_definition"] == "unknown":
        assert row["fiber_g"] == "", "Missing fibre must never become a measured zero"


@pytest.mark.parametrize(
    "index", [i for i, a in enumerate(AUDIT) if "source_per_100ml_used_as_per_100g" in a["flags"]]
)
def test_all_19_volume_sources_are_converted_once_using_density(index):
    row, audit = active_audit_row(index), AUDIT[index]
    assert row["serving_desc"] == "100 กรัม" and row["serving_g"] == "100"
    comp = audit["source_comparison"]
    for field, value in comp["raw_per_100ml"].items():
        if value is not None and str(value):
            expected = (Decimal(str(value)) / Decimal(comp["source_density_g_per_ml"])).quantize(
                Decimal("1" if field == "kcal" else "0.1"), rounding=ROUND_HALF_UP
            )
            assert Decimal(row[field]) == expected


@pytest.mark.parametrize(
    "index",
    [
        i
        for i, a in enumerate(AUDIT)
        if {"value_without_source_cell:fiber_g", "crude_fiber_stored_in_generic_fiber_field"}
        & set(a["flags"])
    ],
)
def test_all_27_missing_or_crude_fibres_are_unknown(index):
    row = active_audit_row(index)
    assert row["fiber_g"] == ""
    assert json.loads(row["nutrition_meta"])["fiber_definition"] == "unknown"


def test_canonical_ids_match_all_26_primary_proposals():
    proposals = json.loads(
        (ROOT / "knowledge/evidence/food-audit-v1/asean-identifier-fragments.json").read_text(
            encoding="utf8"
        )
    )["rows"]
    assert len(proposals) == 26
    for old, canonical, _, category, *_ in proposals:
        assert not FOOD_ID_RE.match(old + " description")
        matching = [r for r in ACTIVE if r["source"] == "ASEAN-FCD-2014-INMU:" + canonical]
        assert len(matching) == 1 and matching[0]["category"] == category


def test_fresh_primary_extraction_recovers_all_26_canonical_rows_and_density_shift():
    primary = ROOT / "knowledge/sources/evidence-2026-10-01/ASEAN-2014.pdf"
    parsed = {r["food_id"]: r for r in parse(primary)}
    proposals = json.loads(
        (ROOT / "knowledge/evidence/food-audit-v1/asean-identifier-fragments.json").read_text(
            encoding="utf8"
        )
    )["rows"]
    assert all(p[1] in parsed for p in proposals)
    assert {k: parsed["AAD58"][k] for k in ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g")} == {
        "kcal": "26",
        "protein_g": "3.6",
        "carb_g": "1.2",
        "fat_g": "0.2",
        "fiber_g": "2.7",
    }
    assert parsed["AAD10"]["kcal"] == "32" and parsed["AAD10"]["fiber_g"] == "3.2"
    assert parsed["AAD10"]["name_en"].startswith("Banana, flower")
    assert parsed["AAD58"]["source_sha256"] == source_hash(primary)


def test_rebuilding_volume_row_does_not_undo_conversion_or_quality(tmp_path, monkeypatch):
    import build_foods_csv as builder

    audit = next(a for a in AUDIT if "source_per_100ml_used_as_per_100g" in a["flags"])
    raw = audit["source_comparison"]
    active = active_audit_row(audit["csv_line"] - 2)
    extracted = {
        "food_id": active["source"].split(":")[1],
        "name_th": active["name_th"],
        "name_en": active["name_en"],
        "nutrient_basis": "per_100ml",
        "density": raw["source_density_g_per_ml"],
        **raw["raw_per_100ml"],
        "source_path": raw["source_path"],
        "source_sha256": raw["source_sha256"],
    }
    input_csv = tmp_path / "asean.csv"
    with input_csv.open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=extracted)
        w.writeheader()
        w.writerow(extracted)
    output_csv = tmp_path / "foods.csv"
    output_csv.write_bytes((ROOT / "knowledge/foods.csv").read_bytes())
    monkeypatch.setattr(builder, "ASEAN_CSV", input_csv)
    monkeypatch.setattr(builder, "FOODS_CSV", output_csv)
    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)
    assert builder.main() == 0
    first = rows(output_csv)[0]
    for key in ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g", "source", "serving_g"):
        assert first[key] == active[key]
    meta = json.loads(first["nutrition_meta"])
    assert (
        meta["human_review_status"] == "pending" and meta["source_sha256"] == raw["source_sha256"]
    )


def test_unverified_foods_are_labeled_and_excluded_from_generated_menu():
    foods = []
    for raw in ACTIVE:
        food = dict(raw, nutrition_meta=json.loads(raw["nutrition_meta"]))
        for field in ("serving_g", "kcal", "protein_g", "carb_g", "fat_g", "fiber_g"):
            food[field] = float(raw[field]) if raw[field] else None
        foods.append(food)
        result = _row_to_dict(SimpleNamespace(**food))
        assert result["estimated"] == (
            food["nutrition_meta"]["verification_status"] in {"unverified", "proxy_unverified"}
        )
        if result["estimated"] or food["fiber_g"] is None:
            assert result["warnings"]
    excluded = {
        r["name_th"]
        for r in foods
        if r["nutrition_meta"]["verification_status"] in {"unverified", "proxy_unverified"}
    }
    assert excluded == set()
    for restrictions in ([], ["วีแกน"], ["แพ้ถั่ว"], ["มังสวิรัติ", "แพ้ถั่ว"]):
        plan = build_day_plan(
            foods, {"kcal": 2100, "protein_g": 130, "carb_g": 260, "fat_g": 60}, restrictions
        )
        assert not excluded & {i["name_th"] for m in plan["meals"] for i in m["items"]}


def test_fineli_tvp_row_matches_archived_primary_render_with_explicit_provenance():
    # Retain the historical cached-capture receipt; current provenance is direct.
    row = next(r for r in PRE_REMOVAL if r["source"] == "FINELI-THL:33026")
    meta = json.loads(row["nutrition_meta"])
    source = ROOT / meta["source_path"]
    assert source_hash(source) == meta["source_sha256"]
    rendered = source.read_text(encoding="utf8")
    rendered_values = [
        "Elintarvikkeen tunniste: 33026",
        "533 kJ (127 kcal)",
        "18.8 g",
        "8.0 g",
        "5.7 g",
    ]
    assert all(
        value in rendered for value in rendered_values
    )
    expected = ["127", "18.8", "8.0", "0.9", "5.7"]
    nutrient_fields = ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g")
    assert [row[k] for k in nutrient_fields] == expected
    assert meta["verification_status"] == "source_compared_AI"
    assert meta["carb_definition"] == "available" and meta["fiber_definition"] == "total_dietary"
    assert meta["human_review_status"] == "pending"
    assert "cached" in meta["capture_scope"] and "not a direct" in meta["capture_scope"]
    quality = _row_to_dict(SimpleNamespace(**dict(row, nutrition_meta=meta)))
    assert not quality["estimated"]
    assert any("cached rendering" in warning for warning in quality["warnings"])


def test_active_fineli_has_direct_api_and_csv_with_correct_fibre_component():
    row = next(r for r in ACTIVE if r["source"] == "FINELI-THL:33026")
    meta = json.loads(row["nutrition_meta"])
    assert meta["source_comparison"] == "official_json_and_csv_compared"
    food = json.loads((ROOT / meta["source_path"]).read_text(encoding="utf8"))
    components = json.loads((ROOT / meta["components_path"]).read_text(encoding="utf8"))
    extract = json.loads((ROOT / meta["csv_extract_path"]).read_text(encoding="utf8"))
    for path_key, hash_key in [("source_path", "source_sha256"),
                               ("components_path", "components_sha256"),
                               ("csv_extract_path", "csv_extract_sha256")]:
        assert source_hash(ROOT / meta[path_key]) == meta[hash_key]
    assert food["id"] == 33026 and food["amount"] == 100
    index = next(i for i, c in enumerate(components) if c["code"] == "FIBT")
    assert components[index]["name"]["en"] == "fibre, total"
    assert food["fiber"] == 0 and food["data"][index] == 5.7
    csv_values = {
        r["EUFDNAME"]: Decimal(r["BESTLOC"].replace(",", ".")) for r in extract["component_rows"]
    }
    assert csv_values["FIBC"] == Decimal("5.716")
    for key, code in [
        ("protein_g", "PROT"), ("carb_g", "CHOAVL"), ("fat_g", "FAT"), ("fiber_g", "FIBC")
    ]:
        expected = csv_values[code].quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        assert Decimal(row[key]) == expected
    assert row["kcal"] == "127" and meta["human_review_status"] == "pending"
    assert extract["package_release"] == "20.0"
    quality = _row_to_dict(SimpleNamespace(**dict(row, nutrition_meta=meta)))
    assert not quality["estimated"]
    assert not any("cached rendering" in w for w in quality["warnings"])


def test_cooked_egg_white_matches_official_fndds_nutrients_and_portion():
    row = next(r for r in ACTIVE if r["source"] == "USDA-FDC-FNDDS:2707170")
    meta = json.loads(row["nutrition_meta"])
    data = json.loads((ROOT / meta["source_path"]).read_bytes())
    assert data["fdcId"] == 2707170 and data["dataType"] == "Survey (FNDDS)"
    assert data["description"] == row["name_en"] == "Egg, white, cooked, no added fat"
    assert "ต้ม" not in row["name_th"] and "ประมาณการ" not in row["name_th"]
    assert meta["replaces_source"] == "ASEAN-FCD-2014-INMU:AAH14"
    assert "preparation_mismatch" not in meta
    assert any(
        p["gramWeight"] == 33 and p["portionDescription"] == "1 egg white"
        for p in data["foodPortions"]
    )
    amounts = {n["nutrient"]["number"]: n["amount"] for n in data["foodNutrients"]}
    for field, number in {
        "kcal": "208",
        "protein_g": "203",
        "carb_g": "205",
        "fat_g": "204",
        "fiber_g": "291",
    }.items():
        expected = (Decimal(str(amounts[number])) * Decimal("0.33")).quantize(
            Decimal("1" if field == "kcal" else "0.1"), rounding=ROUND_HALF_UP
        )
        assert Decimal(row[field]) == expected
    assert row["protein_g"] == "3.5" and row["carb_g"] == "0.8"
    assert not _row_to_dict(SimpleNamespace(**dict(row, nutrition_meta=meta)))["estimated"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("kcal", "nan"),
        ("kcal", "inf"),
        ("protein_g", "-1"),
        ("serving_g", "0"),
        ("fiber_g", "bad"),
        ("name_th", ""),
        ("serving_desc", ""),
        ("nutrition_meta", "[]"),
        ("nutrition_meta", "{bad"),
    ],
)
def test_bad_food_input_cannot_delete_existing_database_rows(tmp_path, monkeypatch, field, value):
    row = dict(ACTIVE[0])
    row[field] = value
    csv_path = tmp_path / "foods.csv"
    with csv_path.open("w", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row)
        writer.writeheader()
        writer.writerow(ACTIVE[1])
        writer.writerow(row)
    monkeypatch.setattr(ingest, "FOODS_CSV", csv_path)

    class Untouched:
        def execute(self, *a):
            raise AssertionError("Must validate before DELETE")

        def add_all(self, *a):
            raise AssertionError("Must validate before INSERT")

        def commit(self):
            raise AssertionError("Must validate before commit")

    with pytest.raises((ValueError, TypeError)):
        ingest.ingest_foods(Untouched())
