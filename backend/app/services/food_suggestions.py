"""List foods from the food database for "suggest high-protein foods" requests.

The 24 Oct live test asked "แนะนำอาหารโปรตีนสูงที่หาง่ายหน่อย" and got "the
documents do not cover this", and "ขออาหารไม่มีนม 3 อย่าง" got a whole-day
menu. The knowledge cards have no food lists, but the food database does.
Selection reuses the meal planner's filters and roles, so a suggested food is
one the planner itself would accept for the same restrictions.
"""

from __future__ import annotations

from app.services.meal_plan import (
    KCAL_PER_G_CARB,
    KCAL_PER_G_PROTEIN,
    _energy_share,
    _is_countable,
    _never_suggest,
    excluded_by,
    roles_of,
)
from app.services.thai_text import normalize_thai

DEFAULT_COUNT = 5
#: Foods, not supplements: a protein powder tops any protein-share ranking.
SUPPLEMENT_CATEGORY = "อาหารเสริม"

def _share(nutrient: str, kcal_per_g: float):
    def key(food: dict) -> tuple[float, float]:
        grams = float(food[nutrient])
        return _energy_share(grams, kcal_per_g, float(food["kcal"])), grams
    return key


#: focus -> (Thai label, planner role, ranking key)
_FOCUS = {
    "protein": ("โปรตีนสูง", "protein", _share("protein_g", KCAL_PER_G_PROTEIN)),
    "carbohydrate": ("คาร์โบไฮเดรตเป็นหลัก", "carb", _share("carb_g", KCAL_PER_G_CARB)),
}


def _usable(food: dict) -> bool:
    """Same verification and practical-portion gates as build_day_plan."""
    meta = food.get("nutrition_meta") or {}
    name = normalize_thai(food.get("name_th") or "")
    dry_legume = "แห้ง" in name and any(
        token in name for token in ("ถั่วเหลือง", "ถั่วเขียว", "ถั่วแดง", "ถั่วดำ"))
    source_only_egg = (food.get("category") == "ไข่" and "ไข่ขาว" not in name
                       and not _is_countable(food))
    return not (
        food.get("estimated")
        or str(food.get("source") or "").startswith("TOVERIFY")
        or (isinstance(meta, dict) and meta.get("verification_status")
            in {"unverified", "proxy_unverified"})
        or _never_suggest(food)
        or food.get("category") == SUPPLEMENT_CATEGORY
        or dry_legume
        or source_only_egg
    )


def _base_name(food: dict) -> str:
    """'อกไก่ไม่มีหนัง, ต้ม' and 'อกไก่ไม่มีหนัง, ย่าง' are one suggestion."""
    return (food.get("name_th") or "").split(",")[0].strip()


def _record(food: dict) -> str:
    """One composition record listed under two names is one food: 'ข้าวเจ้า, สุก'
    (100 g) and 'ข้าวสวย' (120 g) share ASEAN-FCD MYA14 and filled two places
    in a four-item list (25 Oct live test)."""
    return str(food.get("source") or "") or _base_name(food)


def suggest_foods(
    foods: list[dict], focus: str, restrictions: list[str], count: int | None = None,
) -> list[dict]:
    _label, role, key = _FOCUS[focus]
    wanted = count or DEFAULT_COUNT
    candidates = [
        f for f in foods
        if _usable(f) and role in roles_of(f) and not excluded_by(f, restrictions)
    ]
    candidates.sort(key=key, reverse=True)
    # One food per category in turn (best category first), so the list spans
    # meat, fish, eggs, plant proteins and dairy instead of five fish.
    by_category: dict[str, list[dict]] = {}
    names: set[str] = set()
    records: set[str] = set()
    for food in candidates:
        base, record = _base_name(food), _record(food)
        if base not in names and record not in records:
            names.add(base)
            records.add(record)
            by_category.setdefault(food.get("category") or "", []).append(food)
    chosen: list[dict] = []
    while len(chosen) < wanted and any(by_category.values()):
        for queue in by_category.values():
            if queue and len(chosen) < wanted:
                chosen.append(queue.pop(0))
    return chosen


def suggestion_reply(
    items: list[dict], focus: str, requested: int | None, applied: list[str],
    request_only: list[str],
) -> str:
    label = _FOCUS[focus][0]
    if not items:
        return (f"ยังไม่พบอาหาร{label}ในฐานข้อมูลอาหารของระบบที่ผ่านข้อจำกัด "
                f"{', '.join(applied)} ครับ")
    lines = [f"อาหาร{label}จากฐานข้อมูลอาหารของระบบ ค่าต่อ 1 หน่วยบริโภคตามฐานข้อมูล:"]
    for number, food in enumerate(items, start=1):
        lines.append(
            f"{number}. {food['name_th']} ({food['serving_desc']}): "
            f"{float(food['kcal']):.0f} kcal, โปรตีน {float(food['protein_g']):.1f} g, "
            f"คาร์บ {float(food['carb_g']):.1f} g, ไขมัน {float(food['fat_g']):.1f} g"
        )
    order = "สัดส่วนพลังงานจากโปรตีน" if focus == "protein" else "สัดส่วนพลังงานจากคาร์โบไฮเดรต"
    lines.append("")
    lines.append(f"เลือกตาม{order} โดยเลือกจากแต่ละหมวดอาหารสลับกัน ไม่รวมผลิตภัณฑ์เสริมอาหาร")
    if requested and len(items) < requested:
        lines.append(f"พบที่เข้าเงื่อนไข {len(items)} รายการ จากที่ขอ {requested} รายการ")
    if applied:
        lines.append("ข้อจำกัดอาหารที่ใช้คัด: " + ", ".join(applied))
    if request_only:
        lines.append(
            "ข้อจำกัด " + ", ".join(request_only)
            + " ใช้เฉพาะคำตอบนี้ ถ้าต้องการให้ใช้ทุกคำตอบ บันทึกได้ที่ \"ข้อจำกัดอาหาร\""
        )
    return "\n".join(lines)
