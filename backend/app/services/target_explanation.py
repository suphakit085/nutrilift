"""Explain actual calculator operands and scoped primary sources on request.

These links describe the equation and general evidence, not retrieved passages
or proof that a particular calorie/protein target is right for an individual.
"""

import re

from app.services.request_constraints import affirmative_actions, excludes_personal_calculation
from app.services.thai_text import normalize_thai

MIFFLIN_URL = "https://pubmed.ncbi.nlm.nih.gov/2305711/"
ISSN_PROTEIN_URL = "https://link.springer.com/article/10.1186/s12970-017-0177-8"
KATCH_METHOD_URL = "https://www.frontiersin.org/journals/nutrition/articles/10.3389/fnut.2025.1543263/full"


def requests_target_explanation(message: str) -> bool:
    if excludes_personal_calculation(message):
        return False
    text = normalize_thai(message)
    def search(pattern: str) -> re.Match | None:
        return re.search(normalize_thai(pattern), text, re.I)

    personal = search("โปรไฟล์") or (
        search(r"ผม|ฉัน|ดิฉัน|ตัวเอง|\bmy\b")
        and search(r"เป้า(?:หมาย)?|(?:ควร|ต้อง)(?:กิน|ทาน)|กี่|เท่าไร|เท่าไหร่|"
                   r"\b(?:targets?|bmr|tdee)\b")
    )
    target = search(
        r"พลังงาน|แคล|\bbmr\b|\btdee\b|เป้า(?:หมาย)?|"
        r"โปรตีน.{0,15}(?:กี่|เท่าไร|เท่าไหร่|ต่อวัน|วันละ)|"
        r"(?:กี่|เท่าไร|เท่าไหร่).{0,12}โปรตีน|calori|protein target",
    )
    explain = search(
        r"สูตร|ที่มา|อ้างอิง|หลักฐาน|งานวิจัย|ทำไม|"
        r"คำนวณ.{0,40}(?:อย่างไร|ยังไง)|วิธีคำนวณ|"
        r"equation|formula|reference|source|\bwhy\b|\bhow\b",
    )
    calculate = re.search(normalize_thai(r"คำนวณ|คิด(?:ค่า|เป้า)|calculate|compute"),
                          affirmative_actions(message), re.I)
    if calculate and target and not search(r"งานวิจัย|งานทดลอง|บททบทวน|สมมติ|ตัวอย่าง|ถ้า"):
        personal = True  # An imperative calculator request need not repeat "ผม".
    # Keep compound tasks and study interpretation on the normal chat route.
    other = search(
        r"เมนู|ตารางอาหาร|ต่อมื้อ|มื้อละ|แบ่ง|เปรียบเทียบ|เทียบกับ|"
        r"ถ้า|สมมติ|กินไปแล้ว|กินถึง|ขาดอีก|เหลืออีก|"
        r"ครีเอทีน|คาเฟอีน|อาหารเสริม|meal|compare|\bif\b",
    )
    return bool(personal and target and (explain or calculate) and not other)


def _number(value: float) -> str:
    # Show enough precision for fractional user inputs; mark intermediate
    # displays as approximate because the calculator uses unrounded operands.
    return f"{value:.6f}".rstrip("0").rstrip(".")


def explicit_target_explanation_reply(
    message: str, targets: dict, context_note: str | None = None,
) -> str | None:
    if not requests_target_explanation(message):
        return None
    details = targets.get("calculation_details")
    if not details:
        return None  # Legacy payloads must not acquire invented operands.
    macros = targets["macros"]
    lines = ["เป้าหมายที่คำนวณจากข้อมูลที่ใช้ในห้องนี้ครับ"]
    if context_note:
        lines += [context_note]
    # Preserve calculator warnings before displaying a target as actionable.
    lines += targets.get("warnings", [])
    lines += [
        "",
        f"- เป้าหมายที่ใช้คำนวณ: {targets['effective_goal_label_th']}",
        f"- พลังงานเป้าหมาย: {targets['energy_target_kcal']} กิโลแคลอรี/วัน",
        f"- โปรตีน: {macros['protein_g']} กรัม/วัน",
        "",
        "### วิธีคำนวณของระบบ",
    ]
    weight = _number(details["weight_kg"])
    if targets["bmr_formula"] == "Mifflin-St Jeor":
        constant = details["sex_constant"]
        sign = "+" if constant >= 0 else "\u2212"
        lines += [
            (f"- BMR ใช้สมการ Mifflin-St Jeor: 10 \u00d7 {weight} + "
            f"6.25 \u00d7 {_number(details['height_cm'])} \u2212 5 \u00d7 {details['age']} "
            f"{sign} {abs(constant)} ≈ {targets['bmr_kcal']} กิโลแคลอรี/วัน"),
            "",
            (f"ที่มาของสมการ: [Mifflin และคณะ (1990)]({MIFFLIN_URL}) "
            "ศึกษาการประมาณพลังงานขณะพักในผู้ใหญ่สุขภาพดี "
            "ไม่ใช่การตรวจวัดพลังงานที่คุณใช้จริงทั้งวัน"),
        ]
    elif targets["bmr_formula"] == "Katch-McArdle":
        lines += [
            (f"- มวลไร้ไขมัน = {weight} \u00d7 (1 \u2212 {_number(details['body_fat_pct'])} ÷ 100) "
            f"≈ {_number(details['lean_mass_kg'])} กิโลกรัม"),
            (f"- BMR ใช้สมการ Katch-McArdle ที่ระบบใช้อยู่: 370 + 21.6 \u00d7 มวลไร้ไขมัน "
            f"≈ {targets['bmr_kcal']} กิโลแคลอรี/วัน"),
            "",
            (f"อ้างอิงรูปสมการ: [Katch-McArdle: Tang และคณะ (2025)]({KATCH_METHOD_URL}) "
             "ส่วนวิธีการระบุสมการเดียวกัน งานนี้ศึกษาผู้มีน้ำหนักเกิน/โรคอ้วน "
             "ไม่ได้เป็นต้นกำเนิดสมการ และไม่ได้ยืนยันว่าสมการแม่นยำสำหรับคุณ "
             "ผลขึ้นกับเปอร์เซ็นต์ไขมันที่กรอก"),
        ]
    else:
        return None
    adj_low, adj_high = targets["energy_adjustment_pct"]
    midpoint = details["energy_adjustment_fraction"] * 100
    protein_low, protein_high = macros["protein_g_per_kg_range"]
    lines += [
        "",
        (f"- TDEE = BMR \u00d7 ตัวคูณกิจกรรม {_number(details['activity_factor'])} "
        f"≈ {targets['tdee_kcal']} กิโลแคลอรี/วัน "
        f"(ระดับที่เลือก: {targets['inputs']['activity_label_th']})"),
        (f"- พลังงานเป้าหมาย = TDEE \u00d7 (1 + ({_number(midpoint)} ÷ 100)) "
        f"≈ {targets['energy_target_kcal']} กิโลแคลอรี/วัน "
        f"ระบบเลือกค่ากลางของช่วงปรับพลังงาน {adj_low} ถึง {adj_high}% สำหรับเป้าหมายนี้"),
        (f"- โปรตีน = {weight} \u00d7 {_number(details['protein_g_per_kg'])} "
        f"≈ {macros['protein_g']} กรัม/วัน "
        f"ระบบเลือกค่ากลางของช่วง {_number(protein_low)}\u2013{_number(protein_high)} "
        "กรัมต่อน้ำหนักตัว 1 กิโลกรัมต่อวัน"),
        "",
        ("ตัวคูณกิจกรรม ช่วงปรับพลังงาน และค่ากลางโปรตีนเป็นการเลือกของเครื่องคำนวณโครงการ "
        "ไม่ได้เป็นค่าที่บทความกำหนดให้คุณโดยตรง ระบบคำนวณด้วยค่าก่อนปัดเศษ "
        "จึงอาจต่างเล็กน้อยหากนำ BMR หรือ TDEE ที่แสดงไปคูณซ้ำ"),
        "",
        "### หลักฐานเรื่องโปรตีน",
        (f"[ISSN: Jäger และคณะ (2017)]({ISSN_PROTEIN_URL}) "
        "เสนอช่วงโปรตีนรวม 1.4\u20132.0 กรัมต่อน้ำหนักตัว 1 กิโลกรัมต่อวัน "
        "สำหรับผู้ใหญ่สุขภาพดีที่ออกกำลังกายส่วนใหญ่ "
        "ช่วงนี้เป็นหลักฐานทั่วไป ไม่ได้กำหนดค่ากลางที่ระบบเลือก "
        "และไม่ได้รับรองว่าช่วงโปรตีนของโครงการทุกเป้าหมายเหมาะกับทุกคน"),
        "",
        "ตัวเลขทั้งหมดเป็นค่าประมาณจากข้อมูลที่กรอก ไม่ใช่คำแนะนำทางการแพทย์หรือการรับรองผลรายบุคคล",
    ]
    return "\n".join(lines)
