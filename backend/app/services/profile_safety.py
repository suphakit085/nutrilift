"""Conservative product support boundaries, not diagnosis or treatment rules."""

from __future__ import annotations

UNDERWEIGHT_BMI = 18.5
BULK_REVIEW_BMI = 30.0
SPECIALIST_BMI_LOW = 16.0
SPECIALIST_BMI_HIGH = 40.0
MAX_SELF_SERVICE_WEIGHT_KG = 200.0
POLICY_VERSION = "profile-support-20261021"
WHO_BMI_SOURCE = "https://www.who.int/data/nutrition/nlis/info/malnutrition-in-women"
NICE_SOURCE = "https://www.nice.org.uk/guidance/ng246/chapter/Identifying-and-assessing-overweight-obesity-and-central-adiposity"


def support_boundary_reply() -> str:
    return (
        "ข้อมูลน้ำหนักและส่วนสูงนี้อยู่นอกขอบเขตที่ระบบรองรับการวางแผนเฉพาะบุคคล "
        "(น้ำหนักตั้งแต่ 200 กก. หรือ BMI ต่ำกว่า 16 หรือตั้งแต่ 40) "
        "ระบบจึงไม่กำหนดพลังงาน โปรตีน หรือเมนู bulk/cut/รักษาน้ำหนักให้โดยอัตโนมัติ "
        "กรุณาปรึกษาแพทย์หรือนักกำหนดอาหารเพื่อประเมินก่อนวางแผน "
        "นี่เป็นเกณฑ์ส่งต่อและขอบเขตของโครงการ "
        "ไม่ใช่การวินิจฉัยโรคหรือยืนยันว่าน้ำหนักอื่นปลอดภัย"
    )


def support_boundary(weight_kg: float, height_cm: float) -> str | None:
    if height_cm <= 0 or weight_kg <= 0:
        return None  # Ordinary input validation owns malformed values.
    value = weight_kg / (height_cm / 100) ** 2
    if (
        weight_kg >= MAX_SELF_SERVICE_WEIGHT_KG
        or value < SPECIALIST_BMI_LOW
        or value >= SPECIALIST_BMI_HIGH
    ):
        return support_boundary_reply()
    return None
