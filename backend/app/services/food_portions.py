"""Scale a confirmed food row to an explicit weight without model arithmetic."""

import re
from decimal import Decimal, InvalidOperation

_GRAMS = re.compile(r"(?<![\d.])(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:กรัม|grams?|g)(?![a-z])", re.I)


def verified_food_portion_reply(results: list[dict], user_message: str) -> str | None:
    quantities = _GRAMS.findall(user_message)
    rows = [row for result in results if result.get("found") for row in result.get("results", [])]
    # Multiple amounts or food rows need an explicit association; do not guess.
    if len(quantities) != 1 or len(rows) != 1:
        return None
    row = rows[0]
    try:
        weight = Decimal(quantities[0].replace(",", ""))
        serving = Decimal(str(row["serving_g"]))
        if not weight.is_finite() or not serving.is_finite() or weight <= 0 or serving <= 0:
            return None
        ratio = weight / serving
        amounts = {
            key: Decimal(str(row[key])) * ratio
            for key in ("kcal", "protein_g", "carb_g", "fat_g")
        }
        if any(not amount.is_finite() or amount < 0 for amount in amounts.values()):
            return None
    except (KeyError, TypeError, InvalidOperation):
        return None

    def display(amount: Decimal) -> str:
        if 0 < amount < Decimal("0.001"):
            return "น้อยกว่า 0.001"
        return format(amount, ".3f").rstrip("0").rstrip(".") or "0"

    lines = [
        f"ข้อมูลจากฐานข้อมูลอาหารของระบบ สำหรับ {row['name_th']} ปริมาณ {weight:g} กรัม",
        f"คำนวณตามสัดส่วนจากค่าต่อ {serving:g} กรัม x {weight:g} ÷ {serving:g}",
        f"- พลังงาน: {display(amounts['kcal'])} kcal",
        f"- โปรตีน: {display(amounts['protein_g'])} กรัม",
        f"- คาร์โบไฮเดรต: {display(amounts['carb_g'])} กรัม",
        f"- ไขมัน: {display(amounts['fat_g'])} กรัม",
    ]
    fiber = row.get("fiber_g")
    if (row.get("nutrition_meta") or {}).get("fiber_definition") in {"unknown", "crude"}:
        fiber = None
    try:
        fiber_amount = Decimal(str(fiber)) * ratio if fiber is not None else None
        if fiber_amount is not None and (not fiber_amount.is_finite() or fiber_amount < 0):
            fiber_amount = None
    except (TypeError, InvalidOperation):
        fiber_amount = None
    lines.append(
        f"- ใยอาหาร: {display(fiber_amount)} กรัม"
        if fiber_amount is not None
        else "- ใยอาหาร: ยังไม่มีข้อมูลที่ยืนยันได้ ไม่ใช่ศูนย์กรัม"
    )
    if row.get("estimated"):
        lines.append("ตัวเลขนี้เป็นค่าประมาณที่ยังไม่ได้ยืนยัน ไม่ควรใช้เป็นค่าที่แน่นอน")
    return "\n".join(lines)
