"""Research questions cannot silently become personal dietary constraints."""
import pytest

from app.services import chat, guardrails, prompts
from app.services.menu_context import conversation_profile
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from app.services.protein_split import equal_protein_split_reply


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
    assert chat._reference_question(
        "โปรตีนพืชหลายแหล่งที่ได้ EAA และโปรตีนรวมพอ "
        "พอสรุปว่าอาหารวีแกนทุกแบบให้ผลเท่าเวย์ได้ทันทีไหมครับ"
    )


def test_explicit_database_portion_uses_tool_but_not_research_question():
    assert chat._database_food_request("ชานมไข่มุกแก้ว 430 มล. ขอแคลโปรตีนจากฐานข้อมูล")
    assert chat._database_food_request("ข้าวสวย 150 กรัม ขอพลังงานจากฐานข้อมูล")
    assert not chat._database_food_request("หลักฐานใยอาหารหยาบ 0 กรัมในฐานข้อมูลคืออะไร")
    assert not chat._database_food_request("จัดเมนูหนึ่งวัน 2500 แคล จากฐานข้อมูล")


@pytest.mark.parametrize("text", [
    "ไขมันขั้นต่ำ 20% เป็นกติกาของระบบ [S1]",
    "ไม่มีการเปลี่ยนแปลงข้อมูลในโปรไฟล์จริง [S1]",
    "ฐานข้อมูลอาหารของระบบยังไม่มีข้อมูลชานม [S1]",
    "ไขมัน 20% เป็นกติกาของเครื่องคำนวณโครงการนี้ [S1]",
    "ไขมัน 20% เป็นกติกาและการกำหนดค่าของระบบเอง [S1]",
    "โครงการมีกติกาว่าไม่มีข้อมูลไม่ใช่ศูนย์ [S1]",
    "แนะนำติดตามน้ำหนักตัวจริงในช่วง 2-4 สัปดาห์ [S1]",
    "**พลังงานเป้าหมาย:** 2858 kcal [S1]",
])
def test_application_state_and_project_policy_do_not_cite_publications(text):
    assert "[S1]" not in chat.clean_answer(text, [{"label": "S1"}])
    study = "Helms กล่าวถึงสัดส่วน 15-20% ในบางบริบท [S1]"
    assert study in chat.clean_answer(text + "\n\n" + study, [{"label": "S1"}])


def test_new_room_prefix_does_not_add_timing_or_profile_arithmetic():
    reply = equal_protein_split_reply(
        "ห้องใหม่นี้โปรตีน 75 กรัมต่อวันแบ่ง 3 มื้อเท่ากันได้มื้อละเท่าไรครับ",
        daily_protein_g=133,
    )
    assert "25 กรัมต่อมื้อ" in reply and "133" not in reply and "ชั่วโมง" not in reply


def test_calculator_warning_and_bibliography_distinguish_policy_from_helms():
    targets = calc_nutrition_targets(ProfileInput(sex="male", birth_year=2005, birth_month=1,
        height_cm=178, weight_kg=69.3, activity_level="moderate", goal="bulk"))
    assert any("กติกาเครื่องคำนวณ" in w for w in targets["warnings"])
    helms = next(r for r in targets["references"] if r.startswith("Helms"))
    assert "15-20%" in helms and "ไม่ใช่ข้อกำหนดขั้นต่ำ" in helms


@pytest.mark.parametrize("question", [
    "ค่า LDL ในใบตรวจผม 156 ช่วยกำหนดแคลกับโปรตีนสำหรับผมครับ",
    "ค่า HDL ในผลแล็บของผมระบุไว้ 40 ขอจัดเมนู",
    "ใบแลบค่า TSH ของฉันอยู่ 7 ขอคิดโปรตีน",
])
def test_nonadjacent_lab_value_is_refused_before_retrieval_or_provider(question, monkeypatch):
    from types import SimpleNamespace
    def forbidden(*args, **kwargs):
        raise AssertionError("Safety must run before this call")
    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", forbidden)
    assert guardrails.Flag.MEDICAL in guardrails.check(question).flags
    answer = chat.collect_answer(SimpleNamespace(commit=lambda: None), user_message=question)
    assert answer["model"] == "rule:medical_scope" and not answer["tool_calls"]


def test_generic_study_dose_question_does_not_receive_personal_targets():
    assert not chat._personal_context_requested(
        "ข้อมูลคาเฟอีน 3-6 มิลลิกรัมต่อกิโล เป็นปริมาณที่ศึกษาเพื่อการฝึกหรือเพดานรวมทั้งวัน"
    )
    assert chat._personal_context_requested("ผมควรกินโปรตีนกี่กรัมต่อวัน")
    assert chat._personal_context_requested("ขอเป้าพลังงานตามโปรไฟล์เดิม")
