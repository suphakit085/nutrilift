"""Latest stored profiles and explicit withdrawal of temporary choices."""
from dataclasses import replace

import pytest

from app.services.menu_context import conversation_profile, requested_meal_count
from app.services.nutrition import ProfileInput, calc_nutrition_targets


def saved(**changes):
    return ProfileInput(**{
        "sex": "male", "birth_year": 2000, "birth_month": 2, "height_cm": 175,
        "weight_kg": 82, "activity_level": "active", "training_days": 6,
        "goal": "bulk", "restrictions": [], **changes,
    })


@pytest.mark.parametrize("message", [
    "เลิกใช้เป้าหมายชั่วคราวแล้ว กลับไปใช้โปรไฟล์ที่บันทึกจริง",
    "ฉันอัปเดตโปรไฟล์แล้ว ใช้โปรไฟล์ที่บันทึกใหม่คำนวณให้หน่อย",
    "กลับไปใช้ข้อมูลในโปรไฟล์ล่าสุดทั้งหมด",
    "reset to my saved profile",
])
def test_explicit_saved_profile_request_withdraws_temporary_goal(message):
    profile = saved()
    history = [{"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนักเฉพาะในห้องนี้"}]
    effective, _ = conversation_profile(profile, history, message)
    assert effective == profile


def test_old_assistant_profile_and_numbers_cannot_override_new_profile():
    profile = saved(weight_kg=82, goal="bulk")
    old = replace(profile, weight_kg=75, goal="cut")
    history = [{"role": "user", "content": "ตามโปรไฟล์ฉันควรกินเท่าไร"},
               {"role": "assistant", "content": (
                   f"ลดไขมัน {calc_nutrition_targets(old)['energy_target_kcal']} kcal")}]
    effective, _ = conversation_profile(profile, history, "ใช้โปรไฟล์ที่บันทึกใหม่")
    assert effective == profile


def test_reset_diet_retains_real_saved_restrictions_and_never_mutates_them():
    profile = saved(restrictions=["วีแกน"])
    history = [{"role": "user", "content": "ฉันไม่กินไข่และไม่กินไก่"}]
    effective, _ = conversation_profile(
        profile, history,
        "กลับไปใช้ข้อจำกัดอาหารตามโปรไฟล์ที่บันทึกจริงทั้งหมด ยกเลิกข้อจำกัดชั่วคราวในห้องนี้",
    )
    assert effective.restrictions == ["วีแกน"]
    assert profile.restrictions == ["วีแกน"]


def test_normal_followup_keeps_temporary_goal_and_exclusions():
    effective, _ = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ไม่กินไข่"},
    ], "จัดเมนูอีกแบบตามโปรไฟล์")
    assert effective.goal == "maintain"
    assert "ไม่กินไข่" in effective.restrictions


def test_new_constraints_in_same_reset_message_are_applied():
    profile = saved()
    history = [{"role": "user", "content": "ฉันไม่กินไข่ สมมติเปลี่ยนเป็นรักษาน้ำหนัก"}]
    effective, _ = conversation_profile(profile, history, "กลับไปใช้โปรไฟล์ที่บันทึกจริง แต่ไม่กินไก่")
    assert effective.goal == profile.goal
    assert effective.restrictions == ["ไม่กินไก่"]


def test_assistant_cannot_reset_explicit_user_choices():
    effective, _ = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ไม่กินไข่"},
        {"role": "assistant", "content": "กลับไปใช้โปรไฟล์ที่บันทึกจริง"},
    ], "ขออีกเมนู")
    assert effective.goal == "maintain"
    assert "ไม่กินไข่" in effective.restrictions


def test_saved_profile_reset_cannot_erase_declared_food_allergy():
    effective, _ = conversation_profile(saved(), [
        {"role": "user", "content": "ฉันแพ้นมวัว และไม่กินไก่"},
    ], "กลับไปใช้ข้อจำกัดอาหารตามโปรไฟล์ที่บันทึกจริงทั้งหมด")
    assert "แพ้นมวัว" in effective.restrictions
    assert "ไม่กินไก่" not in effective.restrictions


def test_saved_profile_reset_cannot_erase_unknown_allergy():
    effective, _ = conversation_profile(saved(), [
        {"role": "user", "content": "ฉันแพ้ผลไม้ทุกชนิด"},
    ], "กลับไปใช้โปรไฟล์ที่บันทึกจริงทั้งหมด")
    assert any(item.startswith("ข้อจำกัดที่ยังไม่รองรับ:") for item in effective.restrictions)


def test_negated_allergy_is_not_retained_during_reset():
    effective, _ = conversation_profile(saved(), [
        {"role": "user", "content": "ฉันไม่แพ้นมวัว แต่ไม่กินไก่"},
    ], "กลับไปใช้ข้อจำกัดอาหารตามโปรไฟล์ที่บันทึกจริงทั้งหมด")
    assert effective.restrictions == []


def test_diet_reset_keeps_temporary_goal():
    p, _ = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ไม่กินไข่"},
    ], "กลับไปใช้ข้อจำกัดอาหารตามโปรไฟล์ที่บันทึกจริงทั้งหมด")
    assert p.goal == "maintain" and p.restrictions == []


def test_goal_reset_keeps_temporary_food_choices():
    p, note = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ไม่กินไข่"},
    ], "เลิกใช้เป้าหมายชั่วคราว กลับไปใช้โปรไฟล์ที่บันทึกจริง")
    assert p.goal == "bulk" and p.restrictions == ["ไม่กินไข่"]
    assert note and "เป้าหมาย" in note


def test_negated_reset_keeps_choices():
    p, _ = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก ไม่กินไข่"},
    ], "ไม่ต้องกลับไปใช้โปรไฟล์ที่บันทึกจริง จัดตามที่คุยไว้")
    assert p.goal == "maintain" and p.restrictions == ["ไม่กินไข่"]


@pytest.mark.parametrize("message,count", [("จัดเมนู 3 มื้อ", 3), ("จัดสามมื้อ", 3),
                                          ("กิน 4 มื้อ", 4), ("ขอ 6 มื้อ", 6), ("ขอเมนู", 4)])
def test_only_explicit_meal_counts_are_used(message, count):
    assert requested_meal_count([], message) == count


def test_followup_meal_count_ignores_assistant_suggestion():
    history = [{"role": "user", "content": "ขอ 3 มื้อ"},
               {"role": "assistant", "content": "จัด 4 มื้อให้ครับ"}]
    assert requested_meal_count(history, "ขอเมนูอีกแบบ") == 3
    assert requested_meal_count(history, "เปลี่ยนเป็น 4 มื้อ") == 4


def test_named_withdrawn_goal_is_not_reapplied():
    p, _ = conversation_profile(saved(), [
        {"role": "user", "content": "สมมติเปลี่ยนเป็นรักษาน้ำหนัก"},
    ], "ยกเลิกเป้ารักษาน้ำหนัก กลับไปใช้โปรไฟล์ที่บันทึกจริง")
    assert p.goal == "bulk"


def test_named_withdrawn_preference_is_not_reapplied():
    p, _ = conversation_profile(saved(), [
        {"role": "user", "content": "ไม่กินไข่"},
    ], "ยกเลิกข้อจำกัดอาหารไม่กินไข่ กลับไปใช้โปรไฟล์ที่บันทึกจริง")
    assert p.restrictions == []
