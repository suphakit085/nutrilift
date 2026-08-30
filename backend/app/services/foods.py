"""Lookup against the Thai food nutrition table.

The LLM must never guess kcal/macros for a dish - it calls ``lookup_food`` and
reports whatever this returns, including "not found".
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Food

MAX_RESULTS = 5


def _row_to_dict(food: Food) -> dict:
    return {
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


def lookup_food(db: Session, query: str, limit: int = MAX_RESULTS) -> dict:
    """Search the food table by Thai or English name.

    Strategy: exact (case-insensitive) match first, then substring match, then
    word-prefix match on each token of the query. Returns a dict so the payload
    handed to the model always has the same shape.
    """
    q = (query or "").strip()
    if not q:
        return {"query": query, "found": False, "results": [], "note": "ไม่ได้ระบุชื่ออาหาร"}

    pattern = f"%{q}%"
    stmt = (
        select(Food)
        .where(or_(Food.name_th.ilike(pattern), Food.name_en.ilike(pattern)))
        .order_by(func.length(Food.name_th))
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())

    if not rows:
        # Fall back to matching any token of the query (handles "ข้าวผัดกุ้ง ใหญ่").
        tokens = [t for t in q.split() if len(t) >= 3]
        if tokens:
            conditions = [Food.name_th.ilike(f"%{t}%") for t in tokens]
            conditions += [Food.name_en.ilike(f"%{t}%") for t in tokens]
            rows = list(
                db.execute(
                    select(Food).where(or_(*conditions)).order_by(func.length(Food.name_th)).limit(limit)
                ).scalars()
            )

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

    return {
        "query": q,
        "found": True,
        "results": [_row_to_dict(f) for f in rows],
        "note": "ค่าต่อ 1 หน่วยเสิร์ฟตามที่ระบุใน serving_desc",
    }
