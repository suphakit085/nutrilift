"""Carry explicit menu constraints from user turns, never assistant guesses.

These choices are temporary to the conversation. A new room starts from the
saved profile. Unknown exclusions stop planning rather than being ignored.
"""

from __future__ import annotations

import re
from dataclasses import replace

from pythainlp.tokenize import word_tokenize

from app.services.dietary_preferences import confirmed_settings
from app.services.nutrition import ProfileInput
from app.services.thai_text import normalize_thai

_FOODS = {
    "ถั่วลิสง": "แพ้ถั่วลิสง",
    "ถั่วเปลือกแข็ง": "แพ้ถั่วเปลือกแข็ง",
    "อัลมอนด์": "แพ้ถั่วเปลือกแข็ง",
    "มะม่วงหิมพานต์": "แพ้ถั่วเปลือกแข็ง",
    "เม็ดมะม่วงหิมพานต์": "แพ้ถั่วเปลือกแข็ง",
    "วอลนัท": "แพ้ถั่วเปลือกแข็ง",
    "งา": "แพ้งา",
    "peanut": "แพ้ถั่วลิสง",
    "tree nuts": "แพ้ถั่วเปลือกแข็ง",
    "almond": "แพ้ถั่วเปลือกแข็ง",
    "cashew": "แพ้ถั่วเปลือกแข็ง",
    "sesame": "แพ้งา",
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
_SUPPLEMENTS = tuple(normalize_thai(name) for name in (
    "อาหารเสริม", "ผลิตภัณฑ์เสริมอาหาร", "โปรตีนผง", "ผงโปรตีน", "เวย์",
    "supplement", "dietary supplement", "protein powder", "whey",
))
_SUPPLEMENT_DENIAL = (
    r"ไม่(?:ใช้|ต้อง(?:การ)?)(?=\s*(?:"
    + "|".join(re.escape(name) for name in _SUPPLEMENTS) + r"))"
)
# A request for output is a clause boundary, not another item in a food list.
# Require an action AND a topic: bare "ขอ"/"บอก" also start real food names
# (e.g. ของหมัก/บอกฉ่อย), whose unknown allergies must still block planning.
_DETAIL_REQUEST = re.compile(normalize_thai(
    r"(?:ขอ(?:ให้)?|พร้อม(?:ทั้ง)?|(?:ช่วย)?(?:แสดง|ระบุ|บอก|สรุป|แจกแจง|คำนวณ|จัด)|"
    r"ให้(?:แสดง|ระบุ|บอก))\s*"
    r"(?:ชื่อ(?:อาหาร|เมนู)|ปริมาณ|ยอด|พลังงาน|แคลอรี่?|แคลอรี|โปรตีน|สารอาหาร|"
    r"คาร์บ|ไขมัน|ตาราง|เมนู|รายละเอียด|แหล่งอ้างอิง|ส่วนที่(?:ยัง)?ขาด)"
), re.I)
_ALLERGY = re.compile(r"แพ้|\b(?:allergic|allergy) to\b", re.I)
_EXCLUSION = re.compile(
    r"(?:" + _SUPPLEMENT_DENIAL + r"|ไม่(?:กิน|เอา|ใส่)|ห้าม(?:มี|ใส่|ใช้)|"
    r"งด(?:กิน)?|แพ้|ไม่มี|"
    r"\b(?:allergic to|allergy to|avoid|without|don't eat|no)\s+)\s*"
    r"(.+?)(?=" + _DETAIL_REQUEST.pattern + r"|แต่|ครับ|ค่ะ|นะ|เลย|ช่วย|อยาก|ด้วย|แล้ว|ไม่มี|"
    r"ไม่(?:กิน|เอา|ใส่|ใช้|ต้อง(?:การ)?)|"
    r"(?:และ|กับ)?\s*(?:ยัง)?\s*แพ้|"
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


def _abstinence_positions(text: str) -> set[int]:
    """Find the verb งด, not a substring of อ้างอิงด้วย/แตงดอง/งดงาม.

    Use the existing offline Thai tokenizer only for this ambiguous marker;
    a list of pronoun prefixes would miss free-form Thai without spaces.
    """
    positions = set()
    offset = 0
    for word in word_tokenize(text, engine="newmm", keep_whitespace=True):
        if word == "งด":
            positions.add(offset)
        offset += len(word)
    return positions


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


def menu_planning_options(history: list[dict], user_message: str) -> dict:
    """Only user turns can fix a count, allow extras or withdraw permission.

    No explicit count means automatic planning. Extra occasions are distinct
    from the three main meals. Assistant suggestions never grant permission.
    """
    count = None
    allow = None
    suggest = True
    words = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6}
    numbers = r"\d+|หนึ่ง|สอง|สาม|สี่|ห้า|หก"
    turns = [t.get("content", "") for t in history if t.get("role") == "user"]
    # A later clause can withdraw or restore an earlier choice in the same turn.
    clauses = [part for turn in [*turns, user_message]
               for part in re.split(r"แต่|เปลี่ยนใจ", turn)]
    for turn in clauses:
        explicit_count = False
        text = normalize_thai(turn).translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
        text = re.sub(r"ของว่าง|อาหารว่าง|มื้อย่อย", "มื้อเสริม", text)
        if re.search("อัตโนมัติ|ไม่จำกัดจำนวนมื้อ|จัดตามความเหมาะสม", text):
            count, allow, suggest = None, True, True
        for match in re.finditer(r"(" + numbers + r")\s*มื้อ(หลัก|เสริม|ว่าง)?", text):
            prefix = text[max(0, match.start() - 20):match.start()]
            if re.search(r"(?:ไม่เอา|ไม่ต้องการ|ไม่ต้อง)\s*$", prefix):
                continue
            raw = match.group(1)
            explicit_count = True
            number = words[raw] if raw in words else int(raw)
            if match.group(2) in {"เสริม", "ว่าง"}:
                count, allow = 3 + number, False
            elif re.search(r"เพิ่ม(?:อีก)?\s*$", prefix):
                count, allow = (count or 3) + number, False
            else:
                count, allow = number, False
            suggest = True
        # Also recognise "มื้อเสริม 2 มื้อ" without counting it as two total meals.
        for extra in re.finditer(r"มื้อ(?:เสริม|ว่าง)\s*(" + numbers + r")\s*มื้อ", text):
            explicit_count = True
            raw = extra.group(1)
            count, allow = 3 + (words[raw] if raw in words else int(raw)), False
        denied = re.search(
            r"(?:ไม่เอา|ไม่ต้อง(?:การ)?|ไม่เพิ่ม|ห้ามเพิ่ม|อย่าเพิ่ม|ไม่มี|งด).{0,12}มื้อ(?:เสริม|ว่าง)", text
        )
        strict = re.search(
            r"(?:แค่|เพียง)\s*(?:" + numbers + r")\s*มื้อ|มื้อ(?:หลัก)?\s*เท่านั้น", text
        )
        if denied or strict:
            allow, suggest = False, False
            if (denied and not explicit_count) or count is None:
                count = 3
        elif re.search(r"(?:เพิ่ม|มี|จัด|เอา|ขอ).{0,15}มื้อ(?:เสริม|ว่าง).{0,8}(?:ได้|ตามเหมาะสม)", text):
            allow, suggest = True, True
    return {"meal_count": count, "allow_extra_meals": allow,
            "suggest_extra_meals": suggest}


def requested_meal_count(history: list[dict], user_message: str) -> int:
    """Compatibility for callers needing a number rather than automatic mode."""
    count = menu_planning_options(history, user_message)["meal_count"]
    return 4 if count is None else count


def _conversation_settings(
    profile: ProfileInput | None, history: list[dict], user_message: str
) -> tuple[list[str], str | None, str | None]:
    saved_restrictions = list(profile.restrictions) if profile else []
    saved_goal = profile.goal if profile else None
    restrictions = list(saved_restrictions)
    goal = saved_goal
    explicit_exclusions: set[str] = set()
    allergies: list[str] = []
    current_reset = (False, False)
    turns = [t for t in history if t.get("role") == "user"]
    turns.append({"role": "user", "content": user_message})
    for index, turn in enumerate(turns):
        confirmed = confirmed_settings(turn)
        if confirmed is not None:
            # Keep restrictions added to the saved profile AFTER this room's
            # explicit choice; an old room must not erase a new allergy.
            added = [r for r in saved_restrictions if r not in confirmed["saved_restrictions"]]
            restrictions = list(dict.fromkeys([*confirmed["restrictions"], *added]))
            allergies = [r for r in restrictions if r.startswith(("แพ้", "ข้อจำกัดที่ยังไม่รองรับ:"))]
            explicit_exclusions = set(restrictions)
            continue
        text = normalize_thai(turn.get("content", ""))
        reset_goal, reset_diet = _saved_profile_reset(text)
        if index == len(turns) - 1:
            current_reset = reset_goal, reset_diet
        if reset_goal:
            goal = saved_goal
        if reset_diet:
            restrictions = list(dict.fromkeys([*saved_restrictions, *allergies]))
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
        abstinence_positions = None
        for match in _EXCLUSION.finditer(text):
            if match.group(0).startswith("งด"):
                if abstinence_positions is None:
                    abstinence_positions = _abstinence_positions(text)
                if match.start() not in abstinence_positions:
                    continue
            if match.group(0).startswith("แพ้") and text[: match.start()].endswith(
                ("ไม่", "ไม่ได้", "ไม่เคย")
            ):
                continue
            if reset_diet and not _ALLERGY.match(match.group(0)):
                new_choices = re.search(r"แต่|\bbut\b", text)
                if new_choices is None or match.start() < new_choices.end():
                    continue  # A withdrawn preference is not a new exclusion.
            phrase = match.group(1).strip().lower()
            if (phrase in {"สองอย่างเมื่อกี้", "สองรายการเมื่อกี้", "ทั้งสองอย่างเมื่อกี้"}
                    and len(explicit_exclusions) == 2):
                continue  # Exactly two explicit exclusions are already carried.
            for food in re.split(r"\s*(?:และ|กับ|หรือ|รวมถึง|,|/|\band\b|\bor\b|&)\s*", phrase):
                food = food.strip()
                if not food:
                    continue
                if re.match(r"มื้อ(?:เสริม|ว่าง|ย่อย)|ของว่าง|อาหารว่าง", food):
                    continue  # Meal preferences are not unknown food allergies.
                # A preference against supplements is actionable; a vague
                # supplement allergy still requires clarification of ingredients.
                supplement_preference = (
                    food.startswith(_SUPPLEMENTS)
                    and not _ALLERGY.match(match.group(0))
                )
                # Longest prefix matters: soy allergy must not turn into a nut rule.
                key = "ไม่ใช้อาหารเสริม" if supplement_preference else next(
                    (v for k, v in sorted(_FOODS.items(), key=lambda p: -len(p[0]))
                     if food.startswith(k)),
                    None,
                )
                is_allergy = bool(_ALLERGY.match(match.group(0)))
                if key is None and (match.group(0).startswith("ไม่มี") or
                                    (not is_allergy and _DETAIL_REQUEST.match(food))):
                    continue  # A separate request/data gap is not a food exclusion.
                if key is None:
                    key = "ข้อจำกัดที่ยังไม่รองรับ: " + food[:80]
                else:
                    explicit_exclusions.add(key)
                if key not in restrictions:
                    restrictions.append(key)
                # Withdrawing a preference must never erase an allergy disclosure.
                if is_allergy and key not in allergies:
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
    if any(current_reset):
        scope = "เป้าหมายและข้อจำกัดอาหาร" if all(current_reset) else (
            "เป้าหมาย" if current_reset[0] else "ข้อจำกัดอาหาร"
        )
        note = f"กลับไปใช้{scope}จากโปรไฟล์ที่บันทึกล่าสุดตามที่ขอ โดยไม่ได้แก้ไขโปรไฟล์"
        if allergies:
            note += " และยังคงหลีกเลี่ยงอาหารที่คุณเคยแจ้งว่าแพ้ในห้องนี้"
        return restrictions, goal, note
    if restrictions == saved_restrictions and goal == saved_goal:
        return restrictions, goal, None
    return restrictions, goal, (
        "ใช้เป้าหมายหรือข้อจำกัดอาหารที่คุณแจ้งในห้องแชตนี้เป็นการชั่วคราว "
        "ไม่ได้เปลี่ยนโปรไฟล์ที่บันทึกไว้"
    )


def conversation_restrictions(profile: ProfileInput | None, history: list[dict]) -> list[str]:
    return _conversation_settings(profile, history, "")[0]


def conversation_profile(
    profile: ProfileInput | None, history: list[dict], user_message: str,
) -> tuple[ProfileInput | None, str | None]:
    if profile is None:
        return None, None
    restrictions, goal, note = _conversation_settings(profile, history, user_message)
    return replace(profile, goal=goal, restrictions=restrictions), note
