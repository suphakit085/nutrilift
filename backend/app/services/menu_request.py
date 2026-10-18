"""Recognize explicit planning actions, separately from nutrition discussion.

This routes operations, not nutrient calculations. User turns establish the
request context; persisted tool outcomes only determine the next menu variant.
"""
from __future__ import annotations

import re

from app.services.thai_text import normalize_thai

_MENU_ACTION = re.compile(normalize_thai(
    r"(?:จัด|สร้าง|วาง|ออกแบบ|แนะนำ|เสนอ|อยากได้|ต้องการ|ขอ)\s*"
    r"(?:ตัวอย่าง\s*)?(?:เมนู(?!โปรไฟล์|ตั้งค่า|บัญชี|ด้านข้าง)|ตารางอาหาร|แผนอาหาร|มื้ออาหาร)|"
    r"(?:จัด|แนะนำ|ขอ)อาหาร.{0,30}\d+\s*มื้อ|"
    r"(?:จัด|วาง)(?:ให้|ครบ|ตาม|เป้า(?:หมาย)?|โปรไฟล์|เพียง|แค่|รวม|เป็น|จำนวน|กิน|ทาน|\s)*"
    r"\d+\s*มื้อ|"
    r"(?:วันนี้|ทั้งวัน|หนึ่งวัน).{0,12}(?:กิน|ทาน)อะไร(?:บ้าง)?|"
    r"\b(?:create|make|build|design|suggest|give|plan)\s+(?:(?:me|a|my|an|daily|example)\s+)*"
    r"(?:meal\s*plan|menu)\b"
), re.I)
_EXPLANATION = re.compile(normalize_thai(
    r"(?:อธิบาย|สอน|หลักการ|วิธี|ขั้นตอน|ทำไม|วิจัย|หลักฐาน).{0,20}"
    r"(?:จัด|วาง|สร้าง|ออกแบบ|แนะนำ).{0,10}(?:เมนู|อาหาร)|"
    r"\b(?:how to|explain|research|evidence).{0,30}(?:meal\s*plan|menu)\b"
), re.I)
_DECLINE = re.compile(normalize_thai(
    r"(?:ไม่ต้อง(?:การ)?|ไม่เอา|อย่า|ห้าม)\s*(?:จัด|สร้าง|แนะนำ|เสนอ|วาง)?\s*"
    r"(?:เมนู|ตารางอาหาร|แผนอาหาร)|\b(?:don't|do not)\s+(?:make|create|suggest|give).{0,15}"
    r"(?:meal\s*plan|menu)\b"
), re.I)
_FOLLOWUP = re.compile(normalize_thai(
    r"ขอ(?:อีก|ใหม่|เป็น|แค่)?\s*(?:แบบ|ชุด|เมนู|\d+\s*มื้อ)|"
    r"จัดใหม่|เปลี่ยน.{0,15}(?:เมนู|มื้อ)|(?:เพิ่ม|ไม่เพิ่ม|ไม่เอา|ไม่ต้องเพิ่ม).{0,12}"
    r"(?:มื้อเสริม|มื้อว่าง|ของว่าง|\d+\s*มื้อ)|ยังเอาแค่\s*\d+\s*มื้อ|"
    r"\b(?:another|different)\s+(?:one|menu|plan)|\b(?:add|remove)\s+.*\b(?:meal|snack)"
), re.I)


def _direct_request(message: str) -> bool:
    text = normalize_thai(message)
    # A later clause may withdraw or restore the request in the same turn.
    requested = False
    for clause in re.split(r"แต่|เปลี่ยนใจ|แล้ว|และ(?:ช่วย|ขอ)|\bbut\b|\bactually\b", text):
        if _DECLINE.search(clause):
            requested = False
        elif _MENU_ACTION.search(clause) and not _EXPLANATION.search(clause):
            requested = True
    return requested


def requests_menu(message: str, history: list[dict]) -> bool:
    if _direct_request(message):
        return True
    text = normalize_thai(message)
    if _DECLINE.search(text) or _EXPLANATION.search(text) or not _FOLLOWUP.search(text):
        return False
    context = False
    for turn in history:
        if turn.get("role") == "user":
            old = turn.get("content", "")
            context = _direct_request(old) or (
                context and bool(_FOLLOWUP.search(normalize_thai(old)))
                and not _DECLINE.search(normalize_thai(old))
            )
        elif turn.get("role") == "assistant":
            # Only actual recorded tool outcomes establish a completed menu.
            if any(c.get("name") == "suggest_day_menu" and c.get("status") in
                   {"success", "partial"} for c in turn.get("tool_calls") or []):
                context = True
    return context


def next_menu_variant(message: str, history: list[dict]) -> int:
    explicit = re.search(r"(?:ชุด(?:ที่)?|\bvariant)\s*([1-9][0-9]{0,2})(?![0-9])",
                         normalize_thai(message), re.I)
    if explicit:
        return int(explicit.group(1)) - 1
    if not re.search(normalize_thai(r"อีก|ใหม่|เปลี่ยน|ต่าง|\banother\b|\bdifferent\b"),
                     normalize_thai(message), re.I):
        return 0
    last = -1
    for turn in history:
        if turn.get("role") != "assistant":
            continue
        for call in turn.get("tool_calls") or []:
            if (call.get("name") != "suggest_day_menu"
                    or call.get("status") not in {"success", "partial"}):
                continue
            try:
                value = int((call.get("arguments") or {}).get("variant", 0))
            except (ValueError, TypeError):
                continue
            if 0 <= value <= 999:
                last = value
    return (last + 1) % 1000 if last >= 0 else 1


def requests_multiple_days(message: str) -> bool:
    text = normalize_thai(message)
    return bool(re.search(r"สัปดาห์|ทั้งอาทิตย์|\bweekly\b|\bweek\b", text, re.I) or any(
        int(m.group(1)) > 1 for m in re.finditer(r"(\d{1,3})\s*(?:วัน|days?\b)", text, re.I)
    ))


def requests_single_meal(message: str) -> bool:
    text = normalize_thai(message)
    return bool(
        re.search(r"มื้อ(?:เช้า|กลางวัน|เย็น)|\b(?:breakfast|lunch|dinner)\b", text, re.I)
        and not re.search(normalize_thai(
            r"ทั้งวัน|หนึ่งวัน|1\s*วัน|ต่อวัน|\d+\s*มื้อ|สามมื้อ|สี่มื้อ|ห้ามื้อ|หกมื้อ|"
            r"\b(?:daily|day|meals)\b"
        ), text, re.I)
    )


def unverified_menu_table(answer: str) -> bool:
    """Food tables or several labelled meals cannot replace a verified plan.

    Ordinary examples of protein distribution and discussion of meal timing
    are not food/portion tables and remain available to the model.
    """
    if re.search(
        r"\|[^\n]*มื้อ(?:อาหาร)?[^\n]*\|[^\n]*(?:อาหาร|เมนู|วัตถุดิบ)|"
        r"\|[^\n]*meal[^\n]*\|[^\n]*(?:food|menu|ingredient)", answer, re.I,
    ):
        return True
    text = normalize_thai(answer)
    labels = set(re.findall(r"มื้อ(?:เช้า|กลางวัน|เย็น)|\b(?:breakfast|lunch|dinner)\b", text))
    if len(labels) < 2:
        return False
    # General macro distribution remains available; food weights/household
    # portions across labelled meals require a verified plan instead.
    macro = r"(?:โปรตีน|คาร์โบไฮเดรต|คาร์บ|ไขมัน|ใยอาหาร|protein|carbohydrates?|carbs?|fat|fiber)"
    amount = r"\d+(?:\.\d+)?\s*(?:กรัม|grams?\b|g\b)"
    text = re.sub(macro + r"\s*(?:ประมาณ|ราว)?\s*[:=]?\s*" + amount, "", text, flags=re.I)
    text = re.sub(amount + r"\s*" + macro, "", text, flags=re.I)
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:กรัม|ทัพพี|ฟอง|ถ้วย|ช้อน|grams?\b|g\b)", text))
