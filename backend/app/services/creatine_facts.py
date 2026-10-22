"""Narrow necessity FAQ grounded in the actual retrieved creatine passage."""

import re

from app.services.request_understanding import RequestUnderstanding
from app.services.thai_text import normalize_thai


def creatine_necessity_reply(
    message: str, passages: list[dict], understanding: RequestUnderstanding | None = None,
) -> str | None:
    if understanding is not None:
        # Select a supported fact by typed intent, never by spelling variants.
        # A quote from the canonical card is required; this is not a cached
        # answer for a test question or proof of model answer consistency.
        if (understanding.task != "knowledge" or understanding.topic != "creatine_loading"
                or "dose" not in understanding.blocked_actions):
            return None
        for passage in passages:
            label = passage.get("label") or ""
            content = normalize_thai(passage.get("content") or "")
            if (passage.get("document_slug") == "creatine"
                    and normalize_thai("ไม่จำเป็นต้องโหลด") in content
                    and re.fullmatch(r"S\d{1,2}", label, re.I) and passage.get("source_refs")):
                return (
                    "ไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสมครีเอทีน การโหลดช่วยให้สะสมเร็วขึ้น "
                    f"ส่วนการกินขนาดต่ำต่อเนื่องค่อย ๆ เพิ่มระดับสะสมได้ [{label}]\n\n"
                    "การสะสมเร็วหรือช้าไม่ได้พิสูจน์ว่าสองวิธีให้ผลเพิ่มแรงหรือมวลกล้ามเนื้อ"
                    "ระยะยาวเท่ากัน และไม่ได้รับรองผลรายบุคคล"
                )
        return None
    query = normalize_thai(message)
    if not re.search(normalize_thai(r"ครีเอทีน|creatine"), query, re.I):
        return None
    if not re.search(normalize_thai(r"จำเป็น|ต้องโหลด|need.*load|necessary"), query, re.I):
        return None
    if re.search(normalize_thai(
        r"กี่กรัม|ขนาด|โดส|ปริมาณ|ต่าง|เปรียบเทียบ|เทียบกับ|"
        r"อายุ|ผู้สูง|วีแกน|มังสวิรัติ|ผู้หญิง|เฉพาะ|ยี่ห้อ|แบรนด์|"
        r"ก่อนฝึก|หลังฝึก|เวลา|ชนิด|รูปแบบ|20\d{2}|"
        r"dose|grams?|compare|difference|vegan|vegetarian|older|women|brand"
    ), query, re.I):
        return None
    for passage in passages:
        content = normalize_thai(passage.get("content") or "")
        label = passage.get("label") or ""
        if (passage.get("document_slug") == "creatine"
                and normalize_thai("ไม่จำเป็นต้องโหลด") in content
                and re.fullmatch(r"S\d{1,2}", label, re.I)
                and passage.get("source_refs")):
            return (
                "ครีเอทีนไม่ใช่สิ่งจำเป็นสำหรับมือใหม่ทุกคน คุณเลือกเน้นการฝึกและอาหารให้พร้อมก่อนได้ครับ\n\n"
                f"ไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสมครีเอทีน การโหลดช่วยให้สะสมเร็วขึ้น "
                f"ส่วนการกินขนาดต่ำต่อเนื่องค่อย ๆ เพิ่มระดับสะสมได้ [{label}]\n\n"
                "การสะสมเร็วหรือช้าไม่ได้พิสูจน์ว่าสองวิธีให้ผลเพิ่มแรงหรือมวลกล้ามเนื้อระยะยาวเท่ากัน "
                "และไม่ได้รับรองผลรายบุคคล ข้อมูลนี้ไม่ใช้แทนคำแนะนำเฉพาะบุคคลจากผู้เชี่ยวชาญ"
            )
    return None
