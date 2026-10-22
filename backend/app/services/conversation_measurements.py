"""Explicit, temporary body measurements from user turns, never assistant guesses."""

import re

from app.services.thai_text import normalize_thai


def stated_measurements(history: list[dict], message: str) -> dict[str, float]:
    values = {}
    for turn in [*history, {"role": "user", "content": message}]:
        if turn.get("role") != "user":
            continue
        text = normalize_thai(turn.get("content", "")).translate(
            str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
        )
        text = re.sub(r"(?<=\d),(?=\d)", "", text)
        if re.search(
            normalize_thai(r"กลับไปใช้(?:ข้อมูล|น้ำหนัก|ส่วนสูง)?(?:จาก|ใน)?โปรไฟล์|ยกเลิกค่าร่างกายที่แจ้ง"), text
        ):
            values.clear()
            continue
        if re.search(normalize_thai(r"สมมติ|ตัวอย่าง|ถ้า|งานวิจัย|งานทดลอง|คนหนัก"), text):
            continue
        for key, noun, unit in [
            ("weight_kg", r"น้ำหนัก(?:ตัว)?|หนัก", r"กก\.?|กิโล(?:กรัม)?|โล|kg\b"),
            ("height_cm", r"ส่วนสูง|สูง", r"ซม\.?|เซนติเมตร|cm\b"),
        ]:
            patterns = [
                rf"(?:{noun})\s*(?:คือ|เป็น|ตอนนี้)?\s*(\d+(?:[.]\d+)?)\s*(?:{unit})",
                (
                    rf"(?:{noun}).{{0,60}}?(?:ที่ถูก(?:ต้อง)?(?:คือ)?|แก้เป็น|เปลี่ยนเป็น)"
                    rf"\s*(\d+(?:[.]\d+)?)\s*(?:{unit})"
                ),
            ]
            matches = sorted(
                (match for p in patterns for match in re.finditer(normalize_thai(p), text)),
                key=lambda match: match.start(1),
            )
            for match in matches:
                prefix = text[max(0, match.start() - 12) : match.start()]
                if re.search(normalize_thai(r"ไม่ใช่|ไม่ถึง|ไม่ได้|เกิน|ต่ำกว่า|มากกว่า"), prefix):
                    continue
                value = float(match.group(1))
                if value > 0:
                    values[key] = value
    return values
