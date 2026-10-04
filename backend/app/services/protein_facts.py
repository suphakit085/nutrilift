"""Conservative deterministic replies for common protein evidence traps."""

import re


def explicit_single_meal_absorption_reply(question: str) -> str | None:
    """Avoid invented absorption percentages and per-meal ceilings."""
    text = question.casefold()
    asks_absorption = "ดูดซึม" in text or "absorb" in text
    asks_single_meal = any(
        term in text for term in ("มื้อเดียว", "ครั้งเดียว", "one meal", "single meal")
    )
    mentions_protein = "โปรตีน" in text or "protein" in text
    mentions_large_amount = bool(re.search(r"(?<!\d)100\s*(?:กรัม|g|grams?)", text))
    if not (asks_absorption and asks_single_meal and mentions_protein and mentions_large_amount):
        return None

    return (
        "ไม่มีหลักฐานในข้อมูลที่ค้นได้ซึ่งระบุเป็นตัวเลขแน่นอนว่าโปรตีน 100 กรัมจากมื้อเดียว "
        "จะถูกดูดซึมกี่กรัม จึงไม่ควรสรุปว่าเกิน 20-30 กรัมแล้วไม่ถูกดูดซึมหรือเสียเปล่า "
        "การดูดซึมเป็นคนละเรื่องกับปริมาณที่ใช้กระตุ้นการสร้างโปรตีนกล้ามเนื้อในช่วงหนึ่ง "
        "และไม่สามารถบอกได้ว่ากรดอะมิโนทั้งหมดจะไปสร้างกล้ามเนื้อทันที "
        "ให้เน้นปริมาณโปรตีนรวมต่อวัน และแบ่งมื้อตามความสะดวก โดยไม่จำเป็นต้องยึดช่วงห่างตายตัว"
    )
