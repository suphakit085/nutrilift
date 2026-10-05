"""Research questions cannot silently become personal dietary constraints."""
import pytest

from app.services import chat, prompts
from app.services.menu_context import conversation_profile
from app.services.nutrition import ProfileInput


@pytest.mark.parametrize("question", [
    "อาหารวีแกนทุกแบบให้ผลเท่าเวย์ได้ไหมตามงานวิจัย",
    "งานศึกษาอาหารมังสวิรัติยืนยันทุกคนไหม",
    "เมนูฮาลาลในงานวิจัยนี้มีข้อจำกัดอะไร",
])
def test_population_question_does_not_change_diet(question):
    saved = ProfileInput(sex="male", birth_year=1991, height_cm=171, weight_kg=74,
                         activity_level="moderate", goal="bulk")
    effective, note = conversation_profile(saved, [], question)
    assert effective == saved and note is None


@pytest.mark.parametrize("question,name", [
    ("ผมกินวีแกนครับ", "วีแกน"),
    ("เป็นมังสวิรัติ", "มังสวิรัติ"),
    ("ขอเมนูอาหารฮาลาล", "ฮาลาล"),
    ("จัดเมนูวีแกนให้หน่อย", "วีแกน"),
])
def test_explicit_self_disclosure_or_menu_request_changes_temporary_diet(question, name):
    saved = ProfileInput(sex="male", birth_year=1991, height_cm=171, weight_kg=74,
                         activity_level="moderate", goal="bulk")
    effective, note = conversation_profile(saved, [], question)
    assert name in effective.restrictions and note
    assert saved.restrictions == []


def test_reference_prompt_omits_unasked_profile_targets_and_guidance():
    question = "หลักฐานอาหารวีแกนทุกแบบให้ผลเท่าเวย์ได้ไหม"
    assert chat._reference_question(question)
    prompt = prompts.build_system_prompt(
        profile_summary="เพศชาย", targets_summary="2858 kcal", goal="bulk", sex="male",
        reference_only=chat._reference_question(question),
    )
    assert "2858" not in prompt and prompts.GOAL_GUIDANCE_TH["bulk"] not in prompt
    assert "ยังไม่ได้กรอกโปรไฟล์" not in prompt
    assert not chat._reference_question("ตามหลักฐาน ช่วยจัดเมนูสำหรับผมตามโปรไฟล์")


def test_explicit_database_portion_uses_tool_but_not_research_question():
    assert chat._database_food_request("ชานมไข่มุกแก้ว 430 มล. ขอแคลโปรตีนจากฐานข้อมูล")
    assert chat._database_food_request("ข้าวสวย 150 กรัม ขอพลังงานจากฐานข้อมูล")
    assert not chat._database_food_request("หลักฐานใยอาหารหยาบ 0 กรัมในฐานข้อมูลคืออะไร")
    assert not chat._database_food_request("จัดเมนูหนึ่งวัน 2500 แคล จากฐานข้อมูล")


@pytest.mark.parametrize("text", [
    "ไขมันขั้นต่ำ 20% เป็นกติกาของระบบ [S1]",
    "ไม่มีการเปลี่ยนแปลงข้อมูลในโปรไฟล์จริง [S1]",
    "ฐานข้อมูลอาหารของระบบยังไม่มีข้อมูลชานม [S1]",
])
def test_application_state_and_project_policy_do_not_cite_publications(text):
    assert "[S1]" not in chat.clean_answer(text, [{"label": "S1"}])
    study = "Helms กล่าวถึงสัดส่วน 15-20% ในบางบริบท [S1]"
    assert study in chat.clean_answer(text + "\n\n" + study, [{"label": "S1"}])
