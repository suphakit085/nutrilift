"""Incrementally update reference cards and verify food/card alignment safely."""
import csv
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/source-audit/claim-release-20261005"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "backend"))
url = dotenv_values(r"C:\project_1\chat-bot-nutrition\backend\supabase.env")["DATABASE_URL"]
assert "lyvsvixmbjxrkvevuxoi" in url
for file in [r"C:\project_1\chat-bot-nutrition\backend\.env", r"C:\project_1\chat-bot-nutrition\backend\railway.env"]:
    for key, value in dotenv_values(file).items():
        if value is not None:
            os.environ[key] = value
os.environ["DATABASE_URL"] = url
from app.db.session import SessionLocal
from ingest.__main__ import card_paths, content_hash, ingest_cards
import frontmatter

engine = create_engine(url, connect_args={"prepare_threshold": None, "connect_timeout": 20})


def fingerprint(conn, table):
    key = "user_id" if table == "profiles" else "id"
    rows = [dict(r) for r in conn.execute(text(f"SELECT * FROM {table} ORDER BY {key}")).mappings()]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


with engine.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    before = {table: fingerprint(conn, table) for table in ["foods", "profiles", "food_log_entries"]}
    documents_before = {r.slug: str(r.id) for r in conn.execute(text("SELECT slug,id FROM documents"))}
    backup = {table: [dict(r) for r in conn.execute(text(f"SELECT * FROM {table}")).mappings()]
              for table in ["documents", "chunks"]}
backup_path = OUT / "cards-before.json"
assert not backup_path.exists(), "Do not overwrite original reference backup"
backup_path.write_text(json.dumps(backup, default=str), encoding="utf8")
with SessionLocal() as session:
    assert ingest_cards(session) == 0
with engine.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    after = {table: fingerprint(conn, table) for table in before}
    assert before == after, "Foods/profile/diary data changed during card update"
    docs = list(conn.execute(text("SELECT slug,id,content_hash FROM documents")))
    assert {r.slug: str(r.id) for r in docs} == documents_before, "Existing card IDs changed"
    expected = {frontmatter.load(p).get("slug", p.stem): content_hash(frontmatter.load(p)) for p in card_paths()}
    assert {r.slug: r.content_hash for r in docs} == expected
    count, missing = conn.execute(text("SELECT count(*),count(*) FILTER(WHERE embedding IS NULL) FROM chunks")).one()
    assert missing == 0
    foods = list(conn.execute(text("SELECT name_th,serving_g,kcal,protein_g,carb_g,fat_g,fiber_g,source,nutrition_meta FROM foods")).mappings())
with (ROOT / "knowledge/foods.csv").open(encoding="utf-8-sig", newline="") as handle:
    expected_foods = {r["name_th"]: r for r in csv.DictReader(handle)}
assert len(foods) == len(expected_foods) == 386
for food in foods:
    row = expected_foods[food["name_th"]]
    for field in ["serving_g", "kcal", "protein_g", "carb_g", "fat_g", "fiber_g"]:
        assert food[field] == (float(row[field]) if row.get(field) else None), (food["name_th"], field)
    assert food["source"] == row["source"]
    assert food["nutrition_meta"] == json.loads(row["nutrition_meta"])
report = {"verified_at": datetime.now(UTC).isoformat(), "documents": len(docs), "chunks": count,
          "null_embeddings": missing, "foods": len(foods), "food_mismatches": 0, "card_hash_mismatches": 0,
          "existing_document_ids_preserved": True, "foods_profiles_diary_unchanged": before == after,
          "independent_nutrition_review": "pending", "fineli_direct_acquisition": "see separate attempt receipts"}
(OUT / "database-after.json").write_text(json.dumps(report, indent=2), encoding="utf8")
print(json.dumps(report))
