"""Read explicit user constraints before routing or validating an answer."""

import re

from app.services.thai_text import normalize_thai


def affirmative_actions(message: str) -> str:
    """Mask negated actions, retaining later affirmative requests in the turn.

    Do not treat 'ยังไม่ได้คำนวณ' as a prohibition. Do not strip the whole
    sentence: 'ไม่ต้องจัดเมนู แต่คำนวณโปรตีนให้ผม' still requests a calculator.
    """
    text = normalize_thai(message)
    return re.sub(
        normalize_thai(
            r"(?:ไม่ต้อง|ไม่เอา|ไม่ขอ|ไม่ได้ขอ(?:ให้)?|อย่า|งด)\s*"
            r"(?:การ|ให้|ช่วย)?\s*(?:คำนวณ|คิด(?:ค่า|แคล|เป้า)|จัด(?:เมนู|อาหาร|ตารางอาหาร))"
        ),
        " ",
        text,
    )


def excludes_personal_calculation(message: str) -> bool:
    text = normalize_thai(message)
    return bool(
        re.search(normalize_thai(r"(?:ไม่ต้อง|ไม่ขอ|ไม่ได้ขอ(?:ให้)?|อย่า)\s*(?:ให้|ช่วย)?\s*คำนวณ"), text)
    ) and not re.search(normalize_thai(r"คำนวณ|คิด(?:ค่า|เป้า)"), affirmative_actions(message))


def excludes_dose(message: str) -> bool:
    return bool(
        re.search(
            normalize_thai(
                r"(?:ไม่ต้อง|ไม่เอา|ไม่ขอ|อย่า|งด)\s*(?:ให้|บอก|ระบุ|แนะนำ|แจก)?\s*"
                r"(?:โดส|ขนาด|ปริมาณใช้)|(?:no|without)\s+(?:dose|dosage)"
            ),
            normalize_thai(message),
            re.I,
        )
    )


def incomplete_pairing_reply(message: str) -> str | None:
    text = normalize_thai(message)
    # A placeholder directly after the pairing preposition has no referent.
    # 'เวย์กับนม...ได้ไหม' and 'เวย์กินกับอะไรได้บ้าง' are answerable questions.
    missing = re.search(
        normalize_thai(
            r"(?:คู่กับ|ร่วมกับ|ผสมกับ|พร้อมกับ|กินกับ|ทานกับ)\s*"
            r"(?:(?:\.{2,}|_+|\?{2,})\s*)?(?:ได้ไหม|ได้มั้ย|ได้หรือไม่|ดีไหม|$)"
        ),
        text,
    )
    if missing:
        return (
            "ต้องการกินหรือผสมอะไรคู่กับอะไรครับ? กรุณาระบุชื่ออาหาร เครื่องดื่ม "
            "หรืออาหารเสริมทั้งสองอย่างก่อน เพื่อให้ตอบได้ตรงคำถามครับ"
        )
    return None
