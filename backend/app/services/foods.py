"""Lookup against the Thai food nutrition table.

The LLM must never guess kcal/macros for a dish - it calls ``lookup_food`` and
reports whatever this returns, including "not found".
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Food
from app.services.thai_text import compose_sara_am

MAX_RESULTS = 5

#: Rows whose macros are still an estimate rather than a value read out of a
#: composition table. `source` says so, but a bare "TOVERIFY-LABEL" means nothing
#: to the model, which would report the number as a database fact like any
#: other. The meal planner already drops these rows; lookup_food kept handing
#: them over unlabelled, so the two paths treated the same data differently.
#: Down to 1 of 356 rows - ชานมไข่มุก - since 7 ก.ย. 2569 (see knowledge/README.md).
_ESTIMATE_SOURCE_PREFIX = "TOVERIFY"

_ESTIMATE_WARNING = (
    "รายการที่ estimated เป็น true ยังเป็นค่าประมาณ ไม่ได้อ่านจากตารางคุณค่าทางโภชนาการ "
    "ถ้าจะรายงานตัวเลขของรายการนั้น ต้องบอกผู้ใช้ให้ชัดว่าเป็นค่าประมาณที่ยังไม่ได้ยืนยัน "
    "และไม่ควรใช้ในการนับแคลอรี่อย่างจริงจัง"
)


_PARTIAL_WARNING = (
    "ไม่พบชื่อที่ตรงกับคำค้นทั้งคำ รายการด้านล่างมีคำบางส่วนตรงกันเท่านั้นและอาจเป็นคนละอาหาร "
    "ยังไม่มีตัวเลขสารอาหารที่ยืนยันได้สำหรับคำค้นนี้ ห้ามเดาค่าหรือใช้ตัวเลขของรายการใกล้เคียงแทน "
    "ให้บอกชื่อรายการที่พบตาม name_th และขอให้ผู้ใช้ยืนยันชื่ออาหารที่ต้องการ"
)


def _row_to_dict(food: Food) -> dict:
    return {
        "estimated": str(food.source or "").startswith(_ESTIMATE_SOURCE_PREFIX),
        "name_th": food.name_th,
        "name_en": food.name_en,
        "category": food.category,
        "serving_desc": food.serving_desc,
        "serving_g": food.serving_g,
        "kcal": food.kcal,
        "protein_g": food.protein_g,
        "carb_g": food.carb_g,
        "fat_g": food.fat_g,
        "fiber_g": food.fiber_g,
        "source": food.source,
    }


def _escape_like(text: str) -> str:
    """``%`` and ``_`` are LIKE wildcards; "100%" must not match every row."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def query_terms(q: str) -> list[str]:
    """The syllables of a query, for the every-part-must-appear pass.

    Row names come from composition tables, which list descriptors in table
    order - "ไก่, อก, ดิบ", "อกไก่ไม่มีหนัง, ย่าง" - while a person types them in
    spoken order: "อกไก่ดิบ", "อกไก่ย่างไม่มีหนัง". No substring bridges the two,
    and Thai has no spaces to split on.

    Syllables, not words: the word segmenter BM25 uses treats "อกไก่" and
    "ไก่ย่าง" as single dictionary entries, and neither is a substring of
    "ไก่, อก, ดิบ". Syllables - อก, ไก่, ย่าง - are, in any order. Bare numbers
    and units are dropped: "100 กรัม" is a quantity, not part of any name.
    """
    from pythainlp.tokenize import syllable_tokenize

    terms: list[str] = []
    for raw in syllable_tokenize(q.lower(), engine="dict"):
        token = raw.strip()
        if len(token) < 2 or not any(ch.isalnum() for ch in token):
            continue
        if token.isdigit() or token in _QUANTITY_WORDS or token in terms:
            continue
        terms.append(token)
    return terms


#: Units and quantity words that ride along in a query ("อกไก่ย่าง 100 กรัม")
#: but are never part of a food's name.
_QUANTITY_WORDS = frozenset({
    "กรัม", "กิโลกรัม", "กก.", "มิลลิลิตร", "มล.", "ลิตร",
    "แคล", "แคลอรี่", "กิโลแคลอรี่", "g", "kg", "ml", "kcal",
})


def _name_matches(term: str):
    pattern = f"%{_escape_like(term)}%"
    return or_(Food.name_th.ilike(pattern, escape="\\"), Food.name_en.ilike(pattern, escape="\\"))


MatchLevel = Literal["exact", "partial"]


def _search_rows(db: Session, q: str, limit: int) -> list[Food]:
    return search_with_level(db, q, limit)[0]


def search_with_level(db: Session, q: str, limit: int) -> tuple[list[Food], MatchLevel]:
    """Matching strategy shared by lookup_food (LLM tool) and search_foods
    (REST /foods/search), three passes, each only if the one before found
    nothing:

    1. the whole query as a substring of the name - ``"exact"``;
    2. every syllable of the query somewhere in the name, in any order
       ("อกไก่ย่างไม่มีหนัง" -> "อกไก่ไม่มีหนัง, ย่าง") - ``"partial"``;
    3. *more than half* of the syllables, ranked by how many the name contains,
       so "อกไก่ย่างสด" still surfaces the grilled breast - ``"partial"``.

    Passes 2 and 3 match syllables, which also sit inside unrelated words, so
    their results are labelled ``partial`` for the caller to present as "not
    this name exactly". Until 2026-09-24 pass 3 accepted a single syllable and
    everything came back as found: "อเมริกาโน่" returned พริกหยวก, "น้ำอัดลม"
    returned บวบกลม, and the chatbot answered "มันหวาน 100 กรัม" with the 339 kcal
    of a sweetened condensed-milk row (production_review_2026-09-24.md, B2).
    """
    # The table stores สระอำ composed (ingest rewrites the ASEAN source's
    # นิคหิต+สระอา form); fold the query the same way so "น้ำพริก" typed on any
    # keyboard finds "น้ำพริก" however the row was originally spelled. Before
    # this, 20 of the 28 rows containing น้ำ were unreachable.
    q = compose_sara_am(q)
    by_shortest_name = func.length(Food.name_th)

    rows = list(
        db.execute(select(Food).where(_name_matches(q)).order_by(by_shortest_name).limit(limit))
        .scalars()
    )
    if rows:
        return rows, "exact"

    terms = query_terms(q)
    if not terms:
        return [], "partial"
    if len(terms) >= 2:
        stmt = (
            select(Food)
            .where(and_(*(_name_matches(t) for t in terms)))
            .order_by(by_shortest_name)
            .limit(limit)
        )
        rows = list(db.execute(stmt).scalars())
        if rows:
            return rows, "partial"

    matched = sum(case((_name_matches(t), 1), else_=0) for t in terms)
    needed = len(terms) // 2 + 1
    stmt = (
        select(Food)
        .where(or_(*(_name_matches(t) for t in terms)))
        .where(matched >= needed)
        .order_by(desc(matched), by_shortest_name)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars()), "partial"


def lookup_food(db: Session, query: str, limit: int = MAX_RESULTS) -> dict:
    """Search the food table by Thai or English name.

    Returns a dict so the payload handed to the model always has the same
    shape. Deliberately omits `id` - this dict is only ever fed to the LLM as
    text, and every extra field costs tokens on every tool call.
    """
    q = (query or "").strip()
    if not q:
        return {"query": query, "found": False, "results": [], "note": "ไม่ได้ระบุชื่ออาหาร"}

    rows, level = search_with_level(db, q, limit)

    if not rows:
        return {
            "query": q,
            "found": False,
            "results": [],
            "note": (
                "ไม่พบเมนูนี้ในฐานข้อมูล ห้ามเดาค่าพลังงานหรือสารอาหาร "
                "ให้บอกผู้ใช้ว่ายังไม่มีข้อมูลเมนูนี้ และอาจเสนอเมนูใกล้เคียงที่มีข้อมูล"
            ),
        }

    if level == "partial":
        # A shared Thai syllable is not proof of food identity: "มันหวาน" can
        # match the "น้ำมัน ... หวาน" in condensed milk. Do not hand the model
        # nutrition numbers it could accidentally attribute to the query.
        return {
            "query": q,
            "found": False,
            "match": "partial",
            "results": [],
            "candidates": [f.name_th for f in rows],
            "note": _PARTIAL_WARNING,
        }

    results = [_row_to_dict(f) for f in rows]
    note = "ค่าต่อ 1 หน่วยเสิร์ฟตามที่ระบุใน serving_desc"
    if any(r["estimated"] for r in results):
        note += " · " + _ESTIMATE_WARNING
    return {"query": q, "found": True, "match": level, "results": results, "note": note}


def all_foods(db: Session) -> list[dict]:
    """Every row as a plain dict, for the meal planner.

    The planner scores the whole table to rank candidates per role, so it needs
    all rows rather than a search hit. Ordered by name so a given database
    always yields the same menu for the same profile.
    """
    rows = db.execute(select(Food).order_by(Food.name_th)).scalars()
    return [_row_to_dict(f) for f in rows]


def search_foods(db: Session, query: str, limit: int = 20) -> tuple[list[Food], MatchLevel]:
    """Food search for the diary UI. Returns ORM rows (with `id`, needed to
    log an entry) unlike lookup_food's dict payload, which is fed to the LLM
    as text and deliberately omits it, plus the match level so the page can
    say "not this name exactly" instead of presenting a near-miss as the food.
    """
    q = (query or "").strip()
    if not q:
        return [], "exact"
    return search_with_level(db, q, limit)
