"""The profile block must carry goal- and sex-specific framing (prompt v1.5.0 /
v1.6.0). eval/reports/goal_sex_personalization_v1.md is why: with only the
numbers changing, a male user was told to watch for menstrual irregularity.
"""

import pytest

from app.services.prompts import (
    GOAL_GUIDANCE_TH,
    NO_PROFILE_NOTE,
    build_profile_block,
    build_system_prompt,
    sex_guidance_th,
)

SUMMARY = "เพศ หญิง, อายุ 30 ปี, สูง 168 ซม., หนัก 62 กก., เล่นเวท 4 วัน/สัปดาห์"
TARGETS = "เป้าหมาย: ลดไขมัน | TDEE 2000 kcal | พลังงานเป้าหมาย 1700 kcal/วัน"


def test_no_profile_gets_the_generic_note_only():
    block = build_profile_block(None, None, goal="cut", sex="female", age=30)
    assert block == NO_PROFILE_NOTE


@pytest.mark.parametrize("goal", ["cut", "bulk", "maintain"])
def test_goal_guidance_matches_effective_goal(goal):
    block = build_profile_block(SUMMARY, TARGETS, goal=goal)
    assert GOAL_GUIDANCE_TH[goal] in block
    for other, text in GOAL_GUIDANCE_TH.items():
        if other != goal:
            assert text not in block


def test_goal_guidance_is_grounded_in_the_energy_balance_card():
    # The numbers the card states; the framing must not invent others.
    assert "15-20%" in GOAL_GUIDANCE_TH["cut"] and "0.5-1%" in GOAL_GUIDANCE_TH["cut"]
    assert "10-15%" in GOAL_GUIDANCE_TH["bulk"] and "0.25-0.5%" in GOAL_GUIDANCE_TH["bulk"]
    assert "TDEE" in GOAL_GUIDANCE_TH["maintain"]


def test_female_reproductive_age_gets_iron_and_menstrual_framing():
    note = sex_guidance_th("female", 30)
    assert note and "20 มก." in note and "ประจำเดือน" in note


def test_female_over_50_gets_post_menopause_iron_not_menstrual_sign():
    note = sex_guidance_th("female", 55)
    assert note and "10 มก." in note
    assert "ไม่ต้องยกเรื่องประจำเดือน" in note


def test_male_is_told_not_to_recite_female_facts():
    note = sex_guidance_th("male", 30)
    assert note and "11.5 มก." in note and "ห้ามยกเรื่องประจำเดือน" in note


def test_unknown_sex_or_missing_profile_adds_nothing():
    assert sex_guidance_th(None, None) is None
    assert sex_guidance_th("other", 30) is None


def test_system_prompt_threads_sex_and_goal_through():
    prompt = build_system_prompt(
        profile_summary=SUMMARY, targets_summary=TARGETS,
        passages=[], guard_instructions="", use_rag=True,
        goal="cut", sex="female", age=30,
    )
    assert GOAL_GUIDANCE_TH["cut"] in prompt
    assert "ผู้ใช้เป็นหญิงวัยเจริญพันธุ์" in prompt
    assert "ผู้ใช้เป็นชาย" not in prompt
