"""Carry explicit menu constraints from user turns, never assistant guesses.

These choices are temporary to the conversation. A new room starts from the
saved profile. Unknown exclusions stop planning rather than being ignored.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.services.nutrition import ProfileInput
from app.services.thai_text import normalize_thai

_FOODS = {
    "ถั่วเหลือง": "แพ้ถั่วเหลือง",
    "เต้าหู้": "แพ้ถั่วเหลือง",
    "เทมเป้": "แพ้ถั่วเหลือง",
    "โปรตีนเกษตร": "แพ้ถั่วเหลือง",
    "นมถั่วเหลือง": "แพ้ถั่วเหลือง",
    "นมวัว": "แพ้นมวัว",
    "ถั่ว": "แพ้ถั่ว",
    "อาหารทะเล": "แพ้อาหารทะเล",
    "เนื้อวัว": "ไม่กินเนื้อวัว",
    "ไก่": "ไม่กินไก่",
    "ไข่": "ไม่กินไข่",
    "soy": "แพ้ถั่วเหลือง",
    "milk": "แพ้นมวัว",
    "nuts": "แพ้ถั่ว",
    "chicken": "ไม่กินไก่",
    "eggs": "ไม่กินไข่",
    "egg": "ไม่กินไข่",
}
_FOODS = {normalize_thai(k): v for k, v in _FOODS.items()}
_EXCLUSION = re.compile(
    r"(?:ไม่(?:กิน|เอา|ใส่)|ห้าม(?:มี|ใส่)|งด(?:กิน)?|แพ้|ไม่มี|"
    r"allergic to |allergy to |avoid |without |don't eat |no )\s*"
    r"(.+?)(?=แต่|ครับ|ค่ะ|นะ|เลย|ช่วย|อยาก|ด้วย|แล้ว|ไม่มี|ไม่(?:กิน|เอา|ใส่)|"
    r"\s+(?:no|without|avoid|allergic to|don't eat)\s+|\s*[.!?\n]|$)",
    re.I,
)
_GOALS = {
    "รักษาน้ำหนัก": "maintain",
    "ลดไขมัน": "cut",
    "เพิ่มกล้าม": "bulk",
    "maintain": "maintain",
    "cut": "cut",
    "bulk": "bulk",
}
_GOALS = {normalize_thai(k): v for k, v in _GOALS.items()}
_GOAL_NAMES = "|".join(_GOALS)
_CHANGE_GOAL = re.compile(r"เปลี่ยน.{0,60}?เป็น\s*(" + _GOAL_NAMES + r")", re.I)
_WANT_GOAL = re.compile(
    normalize_thai(
        r"(?:คำนวณ|เป้า(?:หมาย)?|เมนู(?:หนึ่งวัน|อาหาร|สำหรับ)?|อยาก|ต้องการ|ขอ)\s*("
        + _GOAL_NAMES + r")"
    ), re.I,
)


def _saved_profile_reset(text: str) -> tuple[bool, bool]:
    """Only explicit user instructions withdraw conversation overrides."""
    saved = re.search(
        normalize_thai(r"(?:โปรไฟล์|ข้อมูลในโปรไฟล์).{0,35}(?:บันทึก|ล่าสุด)|saved profile"),
        text, re.I,
    )
    action = re.search(
        normalize_thai(
            r"กลับ(?:ไป)?(?:มา)?(?:ใช้|ไปใช้)|ยกเลิก|เลิกใช้|อัปเดต|"
            r"บันทึก.{0,15}ใหม่|reset|return to|use my saved"
        ),
        text, re.I,
    )
    if not saved or not action:
        return False, False
    if re.search(r"(?:ไม่|ไม่ต้อง|อย่า)\s*$", text[:action.start()]):
        return False, False
    diet = bool(re.search(normalize_thai("ข้อจำกัดอาหาร|ข้อจำกัดชั่วคราว|ความชอบอาหาร"), text))
    goal = bool(re.search("เป้าหมายชั่วคราว|เป้าชั่วคราว", text))
    return not diet or goal, not goal or diet


def requested_meal_count(history: list[dict], user_message: str) -> int:
    """Carry only counts explicitly supplied by the user, never model guesses."""
    count = 4
    words = {"สาม": 3, "สี่": 4}
    turns = [t.get("content", "") for t in history if t.get("role") == "user"]
    for turn in [*turns, user_message]:
        for match in re.finditer(r"(\d+|สาม|สี่)\s*มื้อ", normalize_thai(turn)):
            raw = match.group(1)
            count = words[raw] if raw in words else int(raw)
    return count


def conversation_profile(
    profile: ProfileInput | None, history: list[dict], user_message: str
) -> tuple[ProfileInput | None, str | None]:
    if profile is None:
        return None, None
    restrictions = list(profile.restrictions)
    goal = profile.goal
    explicit_exclusions: set[str] = set()
    allergies: list[str] = []
    current_reset = (False, False)
    turns = [t.get("content", "") for t in history if t.get("role") == "user"]
    turns.append(user_message)
    for index, turn in enumerate(turns):
        text = normalize_thai(turn)
        reset_goal, reset_diet = _saved_profile_reset(text)
        if index == len(turns) - 1:
            current_reset = reset_goal, reset_diet
        if reset_goal:
            goal = profile.goal
        if reset_diet:
            restrictions = list(dict.fromkeys([*profile.restrictions, *allergies]))
            explicit_exclusions = set(allergies)
        # A reference to a rejected old goal is not a new goal request.
        positive = re.split(r"ไม่ใช่|ไม่เอาเป้า|ไม่ต้องการ", text)[0]
        if reset_goal:
            # A withdrawn goal named in the reset instruction is not a new goal.
            positive = re.split(r"แต่|\bbut\b", positive, maxsplit=1)[-1] if re.search(
                r"แต่|\bbut\b", positive,
            ) else ""
        change = _CHANGE_GOAL.search(positive)
        wants = list(_WANT_GOAL.finditer(positive))
        if change:
            goal = _GOALS[change.group(1).lower()]
        elif wants:
            goal = _GOALS[wants[-1].group(1).lower()]
        for match in _EXCLUSION.finditer(text):
            if match.group(0).startswith("แพ้") and text[: match.start()].endswith(
                ("ไม่", "ไม่ได้", "ไม่เคย")
            ):
                continue
            if reset_diet and not re.match(r"แพ้|allergic to |allergy to ", match.group(0), re.I):
                new_choices = re.search(r"แต่|\bbut\b", text)
                if new_choices is None or match.start() < new_choices.end():
                    continue  # A withdrawn preference is not a new exclusion.
            phrase = match.group(1).strip().lower()
            if (phrase in {"สองอย่างเมื่อกี้", "สองรายการเมื่อกี้", "ทั้งสองอย่างเมื่อกี้"}
                    and len(explicit_exclusions) == 2):
                continue  # Exactly two explicit exclusions are already carried.
            for food in re.split(r"\s*(?:และ|กับ|,|/|\band\b|&)\s*", phrase):
                food = food.strip()
                if not food:
                    continue
                # Longest prefix matters: soy allergy must not turn into a nut rule.
                key = next(
                    (v for k, v in sorted(_FOODS.items(), key=lambda p: -len(p[0]))
                     if food.startswith(k)),
                    None,
                )
                if key is None and (match.group(0).startswith("ไม่มี") or
                                    re.match(normalize_thai(r"จัดเมนู|ขอ|คำนวณ|ช่วย"), food)):
                    continue  # A separate request/data gap is not a food exclusion.
                if key is None:
                    key = "ข้อจำกัดที่ยังไม่รองรับ: " + food[:80]
                else:
                    explicit_exclusions.add(key)
                if key not in restrictions:
                    restrictions.append(key)
                # Withdrawing a preference must never erase an allergy disclosure.
                if (re.match(r"แพ้|allergic to |allergy to ", match.group(0), re.I)
                        and key not in allergies):
                    allergies.append(key)
        for name in ("วีแกน", "มังสวิรัติ", "ฮาลาล"):
            if (
                re.search(
                    r"(?:^(?:เป็น|กิน)|(?:ผม|ฉัน|ดิฉัน|เรา)\s*(?:เป็น|กิน)|"
                    r"(?:ขอ|จัด|แนะนำ|ต้องการ|อยาก).{0,25}?(?:อาหาร|เมนู)(?:แบบ)?)\s*" + name,
                    positive,
                )
                and name not in restrictions
            ):
                restrictions.append(name)
    effective = replace(profile, goal=goal, restrictions=restrictions)
    if any(current_reset):
        scope = "เป้าหมายและข้อจำกัดอาหาร" if all(current_reset) else (
            "เป้าหมาย" if current_reset[0] else "ข้อจำกัดอาหาร"
        )
        note = f"กลับไปใช้{scope}จากโปรไฟล์ที่บันทึกล่าสุดตามที่ขอ โดยไม่ได้แก้ไขโปรไฟล์"
        if allergies:
            note += " และยังคงหลีกเลี่ยงอาหารที่คุณเคยแจ้งว่าแพ้ในห้องนี้"
        return effective, note
    if effective == profile:
        return profile, None
    return effective, ("ใช้เป้าหมายหรือข้อจำกัดอาหารที่คุณแจ้งในห้องแชตนี้เป็นการชั่วคราว ไม่ได้เปลี่ยนโปรไฟล์ที่บันทึกไว้")
