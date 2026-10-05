"""Ask for missing personal inputs instead of inventing them."""

import re

from app.services.thai_text import normalize_thai


def missing_personal_context_reply(
    message: str, history: list[dict], *, has_profile: bool,
) -> str | None:
    text = normalize_thai(message)
    user_text = "\n".join(
        normalize_thai(t.get("content", "")) for t in history if t.get("role") == "user"
    ) + "\n" + text
    if "งบ" in text and re.search(normalize_thai(r"จัด|ตามงบ|งบของ|งบฉัน|งบผม"), text):
        has_budget = re.search(r"\d+(?:\.\d+)?\s*บาท|฿\s*\d+", user_text)
        if not has_budget:
            return (
                "งบอาหารของคุณเท่าไรครับ ระบุจำนวนบาทต่อวันหรือต่อมื้อ และจำนวนมื้อที่ต้องการได้เลย "
                "ฐานข้อมูลอาหารของระบบยังไม่มีข้อมูลราคา จึงยังยืนยันว่าเมนูอยู่ในงบไม่ได้ "
                "ถ้ามีราคาวัตถุดิบหรืออาหารที่ซื้อจริง ช่วยแจ้งด้วยครับ"
            )
    unknown = re.search(normalize_thai(r"ยังไม่ได้|ยังไม่(?:ได้)?บอก|ยังไม่(?:ได้)?แจ้ง|ไม่รู้"), text)
    if unknown and re.search(normalize_thai(r"จัดเวลา|เวลากิน|ตาราง.{0,15}ฝึก"), text):
        return (
            "คุณเริ่มและเลิกฝึกกี่โมงครับ และมื้อก่อนฝึกปกติกินเวลาไหน "
            "โปรไฟล์ยังไม่มีข้อมูลเวลาเหล่านี้ จึงยังจัดเวลากินให้ตรงกับตารางจริงไม่ได้ "
            "แจ้งเวลาที่สะดวกและข้อจำกัดของตารางมาได้เลยครับ"
        )
    if unknown and re.search(normalize_thai(r"ถึงเป้า|ครบเป้า|พอหรือ|พอไหม"), text) and "วันนี้" in text:
        return (
            "ยังบอกไม่ได้ครับว่าวันนี้กินถึงเป้าหมายแล้วหรือยัง "
            "ช่วยบอกรายการอาหารและปริมาณที่กินวันนี้ หรือยอดสารอาหารจากบันทึกอาหารครับ "
            "แชทไม่ได้อ่านบันทึกอาหารให้เอง และข้อมูลที่ยังไม่แจ้งไม่ใช่การกินศูนย์กรัม"
        )
    if unknown and "เมนู" in text and re.search(normalize_thai(r"ในบ้าน|วิธีทำอาหาร|วัตถุดิบที่มี"), text):
        return (
            "ในบ้านมีอาหารหรือวัตถุดิบอะไร ปริมาณเท่าไรครับ "
            "และสะดวกทำอาหารแบบไหน มีอุปกรณ์อะไรหรือใช้เวลาทำได้เท่าไร "
            "โปรไฟล์ยังไม่มีข้อมูลเหล่านี้ จึงยังจัดเมนูให้ตรงกับของที่มีและวิธีทำที่สะดวกไม่ได้ครับ"
        )
    if (not has_profile and re.search(r"ผม|ฉัน|ดิฉัน|ของตัวเอง|โปรไฟล์", text)
            and re.search(normalize_thai(r"คำนวณ|กี่(?:กรัม|แคล)|เท่า(?:ไร|ไหร่)"), text)
            and re.search(r"พลังงาน|โปรตีน|แคล", text)
            and not re.search(r"\d+(?:\.\d+)?\s*(?:กก|kg|ซม|cm|กรัม)", text, re.I)):
        return (
            "ยังไม่มีข้อมูลเพียงพอสำหรับคำนวณเป้าหมายของคุณครับ "
            "กรุณากรอกและบันทึกเพศ ปีและเดือนเกิด ส่วนสูง น้ำหนัก ระดับกิจกรรม และเป้าหมายในหน้าโปรไฟล์ก่อน "
            "เปอร์เซ็นต์ไขมันเป็นข้อมูลเสริม ไม่จำเป็นต้องกรอกหากไม่ทราบ"
        )
    return None
