"""lookup_food must find a row whatever order the words come in.

Composition tables name foods in table order - "ไก่, อก, ดิบ",
"อกไก่ไม่มีหนัง, ย่าง" - and people type them in spoken order. Found on
7 ก.ย. 2569, minutes after the placeholder rows were replaced with properly
named ones: "อกไก่ย่างไม่มีหนัง" no longer matched anything, and the model told
the user the food was not in the database. Every ASEAN row had the same
problem all along; the rename just made it visible on the most-asked food.

Runs against an in-memory SQLite copy of the foods table, so the SQL that
ships is the SQL under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Food
from app.services.foods import _search_rows, lookup_food, query_terms

NAMES = [
    ("ไก่, อก, ดิบ", "Chicken, breast, w/ skin, raw"),
    ("อกไก่ไม่มีหนัง, ย่าง", "Chicken, breast, skinless, boneless, meat only, cooked, grilled"),
    ("อกไก่ไม่มีหนัง, ต้ม", "Chicken, breast, meat only, cooked, stewed"),
    ("ไก่, สะโพก, ดิบ", "Chicken, thigh, w/ skin, raw"),
    ("ก๋วยเตี๋ยวผัดไทย, ใส่ไข่", "Rice noodles, fried, Thai style, with egg"),
    ("ข้าวสวย", "Cooked jasmine rice"),
    ("น้ำพริกกะปิ", "Shrimp-paste chilli dip"),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Food.__table__.create(engine)
    with Session(engine) as session:
        for th, en in NAMES:
            session.add(Food(name_th=th, name_en=en, serving_desc="100 กรัม", serving_g=100,
                             kcal=100, protein_g=10, carb_g=0, fat_g=5, fiber_g=0,
                             source="ASEAN-FCD-2014-INMU:X1"))
        session.commit()
        yield session


def names(rows) -> list[str]:
    return [r.name_th for r in rows]


def test_spoken_order_finds_the_table_order_row(db):
    assert names(_search_rows(db, "อกไก่ย่างไม่มีหนัง", 5)) == ["อกไก่ไม่มีหนัง, ย่าง"]


def test_asean_rows_were_unreachable_the_same_way(db):
    assert names(_search_rows(db, "อกไก่ดิบ", 5)) == ["ไก่, อก, ดิบ"]


def test_a_plain_substring_still_wins_outright(db):
    assert names(_search_rows(db, "ผัดไทย", 5)) == ["ก๋วยเตี๋ยวผัดไทย, ใส่ไข่"]
    assert names(_search_rows(db, "ข้าวสวย", 5)) == ["ข้าวสวย"]


def test_quantities_in_the_query_are_ignored(db):
    assert names(_search_rows(db, "อกไก่ย่าง 100 กรัม", 5)) == ["อกไก่ไม่มีหนัง, ย่าง"]
    assert "100" not in query_terms("อกไก่ย่าง 100 กรัม")
    assert "กรัม" not in query_terms("อกไก่ย่าง 100 กรัม")


def test_an_extra_word_degrades_to_best_partial_match(db):
    # "สด" appears in no name, so the every-word pass finds nothing; the
    # any-word pass must then rank by how many words matched, not name length.
    found = names(_search_rows(db, "อกไก่ย่างสด", 5))
    assert found[0] == "อกไก่ไม่มีหนัง, ย่าง"
    assert "ไก่, สะโพก, ดิบ" not in found[:2]


def test_sara_am_is_folded_before_every_pass(db):
    assert names(_search_rows(db, "นํ้าพริก", 5)) == ["น้ำพริกกะปิ"]


def test_english_words_in_any_order(db):
    assert names(_search_rows(db, "grilled chicken breast", 5)) == ["อกไก่ไม่มีหนัง, ย่าง"]


def test_nothing_in_common_is_still_not_found(db):
    assert lookup_food(db, "ทุเรียน")["found"] is False
