"""Describe the recorded food state without inventing cooked/raw conversions."""

import re

from app.services.thai_text import normalize_thai


def food_preparation(food: dict) -> dict:
    thai = normalize_thai(food.get("name_th") or "")
    english = (food.get("name_en") or "").lower()
    raw = bool(re.search(r"(?<!วัตถุ)ดิบ", thai)) or bool(re.search(r"\braw\b", english))
    cooked = any(token in thai for token in ("ต้ม", "นึ่ง", "ย่าง", "อบ", "ทอด", "ลวก", "คั่ว"))
    cooked = cooked or bool(re.search(r"\bcooked\b|\bboiled\b|\broasted\b|\bgrilled\b", english))
    # Ripe fruit is not a cooked food: สุก alone must not classify fruit.
    cooked = cooked or (food.get("category") != "ผลไม้" and "สุก" in thai)
    cooked = cooked or thai == "ข้าวสวย"
    if raw and cooked:
        state, label = "unknown", "ข้อมูลดิบ/สุกไม่สอดคล้องกัน"
    elif cooked:
        state, label = "cooked", "น้ำหนักสุกตามรายการ"
    elif raw:
        state, label = "raw", "น้ำหนักดิบตามรายการ"
    elif "ขนมปัง" in thai or "bread" in english:
        state, label = "as_sold", "น้ำหนักขนมปังตามรายการ"
    elif food.get("category") == "ผลไม้":
        state, label = "as_recorded", "น้ำหนักส่วนที่กินได้ตามรายการ"
    else:
        state, label = "unknown", "ข้อมูลไม่ระบุดิบ/สุก"
    return {"state": state, "label_th": label, "basis": "recorded_food_name"}


def ready_supplemental_carb(food: dict) -> bool:
    """Prefer cooked staples or bread over raw roots/fresh noodles in mini meals.

    This is a product selection constraint, not a food-safety certification.
    No restriction is relaxed and no nutrient value or food state is changed.
    """
    return food_preparation(food)["state"] in {"cooked", "as_sold"}
