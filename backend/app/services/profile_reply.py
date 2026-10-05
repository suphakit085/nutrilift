"""Render explicit stored-profile summaries without model omissions."""

import re

from app.services.nutrition import ProfileInput
from app.services.thai_text import normalize_thai


def explicit_profile_summary_reply(
    message: str, profile: ProfileInput, targets: dict, context_note: str | None = None,
) -> str | None:
    text = normalize_thai(message)
    if (not re.search(r"ทวน|สรุป", text)
            or not re.search(normalize_thai(r"โปรไฟล์|ข้อมูลที่บันทึก|เป้าหมายปัจจุบัน"), text)
            or not re.search(normalize_thai(
                r"พลังงาน|โปรตีน|สารอาหาร|คาร์บ|ไขมัน|เป้า|ข้อจำกัดอาหาร|ระดับกิจกรรม|เล่นเวท"
            ), text)
            or re.search(normalize_thai(
                r"เมนู|ตารางอาหาร|ทำไม|อย่างไร|ยังไง|งานวิจัย|หลักฐาน|งบ|เวลา|วันนี้|"
                r"ต่อมื้อ|มื้อละ|แบ่ง|หาร\s*\d|ถ้า|สมมติ|เปรียบเทียบ|เทียบ|สัดส่วน|ต่อครั้ง"
            ), text)):
        return None
    inputs, macros = targets["inputs"], targets["macros"]
    numeric = bool(re.search(r"พลังงาน|โปรตีน|สารอาหาร|คาร์บ|ไขมัน", text))
    lines = ["ข้อมูลและเป้าหมายที่ใช้คำนวณตอนนี้จากระบบครับ"]
    if context_note:
        lines += [context_note]
    lines += [
        "",
        f"- ระดับกิจกรรม: {inputs['activity_label_th']}",
        f"- เล่นเวท: {profile.training_days} วัน/สัปดาห์",
        f"- เป้าหมาย: {targets['effective_goal_label_th']}",
        f"- ข้อจำกัดอาหาร: {', '.join(profile.restrictions) or 'ไม่มีข้อจำกัดอาหารที่ใช้ในคำถามนี้'}",
    ]
    if not numeric:
        return "\n".join(lines)
    lines += [
        f"- พลังงานเป้าหมาย: {targets['energy_target_kcal']} กิโลแคลอรี/วัน",
        f"- โปรตีน: {macros['protein_g']} กรัม/วัน",
        f"- คาร์โบไฮเดรต: {macros['carb_g']} กรัม/วัน",
        f"- ไขมัน: {macros['fat_g']} กรัม/วัน",
        "",
        (f"BMR {targets['bmr_kcal']} และ TDEE {targets['tdee_kcal']} กิโลแคลอรี/วัน "
         f"คำนวณด้วยสูตร {targets['bmr_formula']}"),
    ]
    if targets.get("warnings"):
        lines += ["", "ข้อควรทราบจากเครื่องคำนวณ:"]
        lines += ["- " + warning for warning in targets["warnings"]]
    lines += ["", "ตัวเลขเป็นค่าประมาณจากข้อมูลที่กรอก ไม่ใช่การตรวจวัดความต้องการจริงรายบุคคล"]
    return "\n".join(lines)
