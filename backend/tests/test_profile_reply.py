from types import SimpleNamespace

import pytest

from app.services import chat
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from app.services.profile_reply import explicit_profile_summary_reply


def profile():
    return ProfileInput(sex="male", birth_year=2000, birth_month=2, height_cm=175,
                        weight_kg=82, activity_level="active", training_days=6, goal="bulk")


@pytest.mark.parametrize("question", [
    "ใช้โปรไฟล์ที่บันทึกปัจจุบัน ช่วยทวนเป้าหมาย พลังงานและโปรตีน คาร์บ ไขมันต่อวันตามระบบ",
    "ตามโปรไฟล์ฉัน ช่วยทวนระดับกิจกรรม จำนวนวันเล่นเวท เป้าหมาย พลังงาน โปรตีน คาร์บและไขมัน",
    "ช่วยสรุปพลังงานกับเป้าหมายปัจจุบัน",
    "ช่วยทวนสารอาหารตามโปรไฟล์",
])
def test_summary_always_includes_goal_and_all_actual_numbers(question):
    p=profile()
    targets=calc_nutrition_targets(p)
    reply=explicit_profile_summary_reply(question,p,targets)
    assert reply and "เพิ่มกล้ามเนื้อ" in reply and "6 วัน/สัปดาห์" in reply
    assert targets["inputs"]["activity_label_th"] in reply
    for number in [targets["energy_target_kcal"],*[targets["macros"][k] for k in
                                                ("protein_g","carb_g","fat_g")]]:
        assert str(number) in reply
    assert all(w in reply for w in targets["warnings"])
    assert "[S" not in reply


@pytest.mark.parametrize("question", [
    "สรุปงานวิจัยเรื่องโปรตีน", "ช่วยทวนพลังงานแล้วจัดเมนูตามโปรไฟล์",
    "โปรไฟล์นี้คำนวณพลังงานอย่างไร", "ช่วยสรุปโปรไฟล์กับงบอาหาร",
    "ตามโปรไฟล์วันนี้กินถึงเป้าหมายโปรตีนหรือยัง", "ช่วยสรุปหลักฐานโปรตีนตามโปรไฟล์",
    "ช่วยทวนโปรตีนตามโปรไฟล์แบ่ง 3 มื้อ", "สรุปพลังงานตามโปรไฟล์ถ้าฉันหนัก 90 กก",
    "ทวนโปรไฟล์กับสัดส่วนพลังงานจากโปรตีน", "ช่วยทวนโปรไฟล์เปรียบเทียบโปรตีนกับงานวิจัย",
])
def test_complex_and_research_questions_keep_normal_chat_route(question):
    p=profile()
    assert explicit_profile_summary_reply(question,p,calc_nutrition_targets(p)) is None


def test_reset_summary_uses_saved_goal_even_with_old_assistant_values(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError("An exact profile summary must not call the model")
    monkeypatch.setattr(chat,"get_client",forbidden)
    monkeypatch.setattr(chat.retrieval,"search",lambda *args:[])
    p=profile()
    answer=chat.collect_answer(SimpleNamespace(commit=lambda:None),profile=p,
        history=[{"role":"user","content":"สมมติเปลี่ยนเป็นรักษาน้ำหนัก"},
                 {"role":"assistant","content":"พลังงาน 3086 รักษาน้ำหนัก"}],
        user_message="เลิกใช้เป้าหมายชั่วคราว กลับไปใช้โปรไฟล์ที่บันทึกจริง ช่วยทวนพลังงานและโปรตีน")
    assert answer["model"]=="rule:profile_summary"
    assert "เพิ่มกล้ามเนื้อ" in answer["text"] and "3471" in answer["text"]
    assert "ไม่ได้แก้ไขโปรไฟล์" in answer["text"]


def test_temporary_goal_is_preserved_in_exact_summary(monkeypatch):
    monkeypatch.setattr(chat.retrieval,"search",lambda *args:[])
    answer=chat.collect_answer(SimpleNamespace(commit=lambda:None),profile=profile(),
        history=[{"role":"user","content":"สมมติเปลี่ยนเป็นรักษาน้ำหนัก"}],
        user_message="ช่วยทวนพลังงานตามโปรไฟล์ตอนนี้")
    assert answer["model"]=="rule:profile_summary" and "รักษาน้ำหนัก" in answer["text"]
    assert "3086" in answer["text"] and "ชั่วคราว" in answer["text"]


def test_constraint_summary_does_not_add_unasked_macros():
    p=profile()
    reply=explicit_profile_summary_reply(
        "กลับไปใช้ข้อจำกัดอาหารตามโปรไฟล์ที่บันทึกจริงทั้งหมด แล้วช่วยทวนเป้าหมายกับข้อจำกัดอาหาร",
        p,calc_nutrition_targets(p),"กลับไปใช้โปรไฟล์ที่บันทึกล่าสุด",
    )
    assert "ไม่มีข้อจำกัดอาหาร" in reply and "เพิ่มกล้ามเนื้อ" in reply
    assert "พลังงาน" not in reply and "โปรตีน" not in reply


def test_constraint_summary_keeps_actual_allergy():
    from dataclasses import replace
    p=replace(profile(),restrictions=["แพ้นมวัว"])
    reply=explicit_profile_summary_reply("ช่วยทวนข้อจำกัดอาหารตามโปรไฟล์",p,calc_nutrition_targets(p))
    assert "แพ้นมวัว" in reply and "ไม่มีข้อจำกัดอาหาร" not in reply
