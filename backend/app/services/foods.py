"""Lookup against the Thai food nutrition table.

The LLM must never guess kcal/macros for a dish - it calls ``lookup_food`` and
reports whatever this returns, including "not found".
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Food

MAX_RESULTS = 5

#: Rows whose macros are still an estimate rather than a value read out of a
#: composition table. `source` says so, but a bare "TOVERIFY-INMU" means nothing
#: to the model, which would report the number as a database fact like any
#: other. The meal planner already drops these rows; lookup_food kept handing
#: them over unlabelled, so the two paths treated the same data differently.
#: 10 of 339 rows (see knowledge/README.md).
_ESTIMATE_SOURCE_PREFIX = "TOVERIFY"

_ESTIMATE_WARNING = (
    "รายการที่ estimated เป็น true ยังเป็นค่าประมาณ ไม่ได้อ่านจากตารางคุณค่าทางโภชนาการ "
    "ถ้าจะรายงานตัวเลขของรายการนั้น ต้องบอกผู้ใช้ให้ชัดว่าเป็นค่าประมาณที่ยังไม่ได้ยืนยัน "
    "และไม่ควรใช้ในการนับแคลอรี่อย่างจริงจัง"
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


def _search_rows(db: Session, q: str, limit: int) -> list[Food]:
    """Matching strategy shared by lookup_food (LLM tool) and search_foods
    (REST /foods/search): exact/substring on name, falling back to per-token
    matching for multi-word queries (handles "ข้าวผัดกุ้ง ใหญ่").
    """
    pattern = f"%{q}%"
    stmt = (
        select(Food)
        .where(or_(Food.name_th.ilike(pattern), Food.name_en.ilike(pattern)))
        .order_by(func.length(Food.name_th))
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())
    if rows:
        return rows

    tokens = [t for t in q.split() if len(t) >= 3]
    if not tokens:
        return []
    conditions = [Food.name_th.ilike(f"%{t}%") for t in tokens]
    conditions += [Food.name_en.ilike(f"%{t}%") for t in tokens]
    return list(
        db.execute(
            select(Food).where(or_(*conditions)).order_by(func.length(Food.name_th)).limit(limit)
        ).scalars()
    )


def lookup_food(db: Session, query: str, limit: int = MAX_RESULTS) -> dict:
    """Search the food table by Thai or English name.

    Returns a dict so the payload handed to the model always has the same
    shape. Deliberately omits `id` - this dict is only ever fed to the LLM as
    text, and every extra field costs tokens on every tool call.
    """
    q = (query or "").strip()
    if not q:
        return {"query": query, "found": False, "results": [], "note": "ไม่ได้ระบุชื่ออาหาร"}

    rows = _search_rows(db, q, limit)

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

    results = [_row_to_dict(f) for f in rows]
    note = "ค่าต่อ 1 หน่วยเสิร์ฟตามที่ระบุใน serving_desc"
    if any(r["estimated"] for r in results):
        note += " · " + _ESTIMATE_WARNING
    return {"query": q, "found": True, "results": results, "note": note}


def all_foods(db: Session) -> list[dict]:
    """Every row as a plain dict, for the meal planner.

    The planner scores the whole table to rank candidates per role, so it needs
    all rows rather than a search hit. Ordered by name so a given database
    always yields the same menu for the same profile.
    """
    rows = db.execute(select(Food).order_by(Food.name_th)).scalars()
    return [_row_to_dict(f) for f in rows]


def search_foods(db: Session, query: str, limit: int = 20) -> list[Food]:
    """Food search for the diary UI. Returns ORM rows (with `id`, needed to
    log an entry) unlike lookup_food's dict payload, which is fed to the LLM
    as text and deliberately omits it.
    """
    q = (query or "").strip()
    if not q:
        return []
    return _search_rows(db, q, limit)
