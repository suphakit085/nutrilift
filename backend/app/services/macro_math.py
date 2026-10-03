"""Energy shares for explicitly supplied grams, with one common denominator."""

from __future__ import annotations

import re


def explicit_macro_energy_reply(message: str) -> str | None:
    if not re.search(r"คำนวณ|สัดส่วน|แคล|พลังงาน|เปอร์เซ็นต์|kcal|calorie", message, re.I):
        return None
    values = []
    for label, names, factor in (
        ("โปรตีน", r"โปรตีน|protein", 4),
        ("คาร์โบไฮเดรต", r"คาร์บ|คาร์โบไฮเดรต|carbs?|carbohydrate", 4),
        ("ไขมัน", r"ไขมัน|fat", 9),
    ):
        match = re.search(r"(?:" + names + r")\s*(\d+(?:\.\d+)?)\s*(?:กรัม|g\b)", message, re.I)
        if not match:
            return None
        grams = float(match.group(1))
        if grams > 10000:
            return None
        values.append((label, grams, factor, grams * factor))
    total = sum(v[3] for v in values)
    if total <= 0:
        return "จำนวนกรัมที่ระบุรวมเป็นพลังงาน 0 kcal จึงยังคำนวณสัดส่วนร้อยละไม่ได้ครับ"
    lines = ["คำนวณจากจำนวนกรัมที่คุณระบุ โดยใช้โปรตีนและคาร์บ 4 kcal/กรัม และไขมัน 9 kcal/กรัม:"]
    for label, grams, factor, energy in values:
        lines.append(
            f"- {label} {grams:g} กรัม x {factor} = {energy:g} kcal "
            f"({energy / total * 100:.1f}% ของผลรวม)"
        )
    lines.extend(
        [
            f"รวม {total:g} kcal ใช้ผลรวมนี้เป็นฐานของทุกเปอร์เซ็นต์ จึงรวมได้ประมาณ 100% หลังปัดเศษ",
            (
                "ถ้าเป้าที่คุณเทียบต่างเพียงเล็กน้อย อาจเกิดจากการปัดกรัมของมาโคร "
                "แต่ถ้าเป็นคนละชุดตัวเลขหรือคนละโปรไฟล์ ไม่ควรอธิบายว่าทั้งหมดเป็นเพียงการปัดเศษครับ"
            ),
            "นี่เป็นการแปลงหน่วยตามตัวเลขที่ให้ ไม่ใช่คำแนะนำให้เปลี่ยนเป้าหมายพลังงานของคุณ",
        ]
    )
    return "\n\n".join(lines)
