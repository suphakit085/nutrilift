"""Compare Fineli 33026 with original API/components and official CSV, then update provenance only."""
import csv
import hashlib
import io
import json
import shutil
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/source-audit/fineli-direct-20261005"
SOURCE = ROOT / "knowledge/sources/fineli-direct-20261005"
SOURCE.mkdir(parents=True, exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for old, new in [("food-33026-browser.json", "food-33026.json"), ("components-browser.json", "components.json")]:
    if (SOURCE / new).exists():
        assert digest(OUT / old) == digest(SOURCE / new), "Preserve original acquisition"
    else:
        shutil.copyfile(OUT / old, SOURCE / new)
food = json.loads((SOURCE / "food-33026.json").read_text(encoding="utf8"))
components = json.loads((SOURCE / "components.json").read_text(encoding="utf8"))
assert food["id"] == 33026 and food["amount"] == food["mass"] == 100
assert food["name"]["en"].lower() == "soya mince, white or dark, boiled without salt"
assert len(food["data"]) == len(components) == 55
indices = {c["code"]: i for i, c in enumerate(components)}
assert indices["FIBT"] == 15 and components[15]["name"]["en"] == "fibre, total"
assert components[indices["CHO"]]["name"]["en"] == "carbohydrate, available"
with zipfile.ZipFile(OUT / "package-49-browser.zip") as package:
    def rows(name):
        return list(csv.DictReader(io.StringIO(package.read(name).decode("latin1")), delimiter=";"))
    values = [r for r in rows("component_value.csv") if r["FOODID"] == "33026"]
    names = [r for r in rows("foodname_EN.csv") if r["FOODID"] == "33026"]
    assert names[0]["FOODNAME"].lower() == food["name"]["en"].lower()
    description = package.read("descript.txt").decode("latin1")
    assert "Release. 20.0" in description
raw = {r["EUFDNAME"]: Decimal(r["BESTLOC"].replace(",", ".")) for r in values}
assert "0,239" in components[0]["description"]["en"], "Use Fineli's documented kJ conversion"
expected = {"kcal": raw["ENERC"] * Decimal("0.239"), "protein_g": raw["PROT"],
            "carb_g": raw["CHOAVL"], "fat_g": raw["FAT"], "fiber_g": raw["FIBC"]}
expected = {k: str(v.quantize(Decimal("1" if k == "kcal" else "0.1"), rounding=ROUND_HALF_UP)) for k, v in expected.items()}
api_expected = {"kcal": str(Decimal(str(food["energyKcal"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                **{field: str(Decimal(str(food["data"][indices[code]])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
                   for field, code in [("protein_g", "PROT"), ("carb_g", "CHO"), ("fat_g", "FAT"), ("fiber_g", "FIBT")]}}
assert expected == api_expected
extraction = {"source_url": "https://fineli.fi/fineli/content/file/49", "package_release": "20.0",
              "package_sha256": digest(OUT / "package-49-browser.zip"), "name_rows": names,
              "component_rows": values, "description": description}
(SOURCE / "csv-33026.json").write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf8")
csv_path = ROOT / "knowledge/foods.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    fields, current = reader.fieldnames, list(reader)
row = next(r for r in current if r["source"] == "FINELI-THL:33026")
assert {k: row[k] for k in expected} == expected
meta = json.loads(row["nutrition_meta"])
assert meta["source_comparison"] == "official_primary_web_rendering_compared_cached_capture"
previous = dict(row)
meta.update(source_path="knowledge/sources/fineli-direct-20261005/food-33026.json",
            source_sha256=digest(SOURCE / "food-33026.json"),
            source_url="https://fineli.fi/fineli/api/v1/foods/33026",
            source_comparison="official_json_and_csv_compared",
            components_path="knowledge/sources/fineli-direct-20261005/components.json",
            components_sha256=digest(SOURCE / "components.json"),
            csv_extract_path="knowledge/sources/fineli-direct-20261005/csv-33026.json",
            csv_extract_sha256=digest(SOURCE / "csv-33026.json"),
            csv_package_release="20.0", source_retrieved_at=datetime.now(UTC).isoformat(),
            capture_scope="Direct official JSON and CSV acquired by ordinary headed browser; CSV release 20.0, retrieval date is not a new publication date",
            fiber_component_code="FIBT", csv_fiber_component_code="FIBC",
            source_api_fiber_caveat="Top-level fiber=0 differs from data[FIBT]=5.7; use the indexed total-fibre component, confirmed by CSV FIBC=5.716",
            rounding="API displayed components; CSV HALF_UP to whole kcal and 1 decimal gram, using Fineli's documented 0.239 kcal/kJ for ENERC; energyKcal also rounds to 127")
row["nutrition_meta"] = json.dumps(meta, ensure_ascii=False, sort_keys=True)
url = dotenv_values(r"C:\project_1\chat-bot-nutrition\backend\supabase.env")["DATABASE_URL"]
assert "lyvsvixmbjxrkvevuxoi" in url
engine = create_engine(url, connect_args={"prepare_threshold": None, "connect_timeout": 20})
backup_path = OUT / "food-before.json"
assert not backup_path.exists()
with engine.begin() as conn:
    all_before = [dict(r) for r in conn.execute(text("SELECT * FROM foods ORDER BY id")).mappings()]
    target = next(r for r in all_before if r["source"] == "FINELI-THL:33026")
    assert len(all_before) == len(current) == 386 and target["nutrition_meta"] == json.loads(previous["nutrition_meta"])
    backup_path.write_text(json.dumps(target, default=str, ensure_ascii=False, indent=2), encoding="utf8")
    conn.execute(text("UPDATE foods SET nutrition_meta=CAST(:meta AS jsonb) WHERE id=:id"), {"id": target["id"], "meta": row["nutrition_meta"]})
    all_after = [dict(r) for r in conn.execute(text("SELECT * FROM foods ORDER BY id")).mappings()]
    assert len(all_after) == len(all_before)
    for before, after in zip(all_before, all_after, strict=True):
        if before["id"] == target["id"]:
            assert after["nutrition_meta"] == meta
            before, after = dict(before), dict(after)
            before.pop("nutrition_meta"); after.pop("nutrition_meta")
        assert before == after, "Only the target provenance may change"
with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader(); writer.writerows(current)
report = {"verified_at": datetime.now(UTC).isoformat(), "food_id": 33026, "rounded_per_100g": expected,
          "original_api_vs_csv": "matched", "nutrient_values_changed": False, "food_ids_preserved": True,
          "production_rows_updated": 1, "cached_capture_warning_resolved": True,
          "independent_review": "pending", "source_api_fiber_caveat": meta["source_api_fiber_caveat"],
          "source_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in sorted(SOURCE.glob("*.json"))]}
(OUT / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(report, ensure_ascii=False))
