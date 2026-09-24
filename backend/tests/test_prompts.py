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


# --- brackets are reserved for real citations (prompt v1.10.0) ---------------
# baseline-v9 stored "[อ้างอิงจากระบบ]" (Q097, nothing retrieved) and
# "[รายงานจากฐานข้อมูลอาหารของระบบ]" x5 (Q098, tool data); a live run on
# 2026-09-15 produced "[S-NONE]". The chat bubble renders answer text verbatim,
# so every one of these reached the screen. cited_only() ignores them, which is
# exactly why nothing noticed.

from app.services.prompts import BASE_SYSTEM_PROMPT, NO_CONTEXT_NOTE, PROMPT_VERSION  # noqa: E402


def test_prompt_version_bumped_with_the_bracket_rule():
    assert PROMPT_VERSION == "v1.12.0"


def test_base_prompt_reserves_square_brackets_for_citations():
    assert "วงเล็บเหลี่ยม" in BASE_SYSTEM_PROMPT
    assert "[S-NONE]" in BASE_SYSTEM_PROMPT  # named as a thing not to write


def test_no_context_note_forbids_any_marker():
    """With nothing retrieved there is no S-number to cite, and the base rule 1
    still says "ใส่หมายเลขกำกับ" - the note must cancel it explicitly, as the
    use_rag=False branch already did."""
    assert "ห้ามใส่ [S1]" in NO_CONTEXT_NOTE
    prompt = build_system_prompt(passages=[], use_rag=True)
    assert NO_CONTEXT_NOTE.strip() in prompt


def test_food_tool_attribution_is_prose_not_a_bracket_label():
    assert "ไม่ใช่ป้ายในวงเล็บเหลี่ยม" in BASE_SYSTEM_PROMPT


# --- the chat cannot see or write the diary (production_review_2026-09-24, B5)
# Live answer to "ช่วยบันทึกลงไดอารี่ว่ามื้อเที่ยงกินข้าวมันไก่": "บันทึกมื้อเที่ยงของคุณ
# เรียบร้อยแล้วครับ" - no tool writes the diary, so nothing was saved.


def test_prompt_says_the_chat_cannot_touch_the_diary():
    assert "ห้ามพูดว่าบันทึกให้แล้ว" in BASE_SYSTEM_PROMPT
    assert "หน้า \"บันทึกอาหาร\"" in BASE_SYSTEM_PROMPT


def test_prompt_forbids_estimates_for_foods_not_in_the_table():
    """B9: americano "5-15 kcal" and iced green tea "200-400 kcal" came from
    general knowledge although lookup_food said not found."""
    assert "ห้ามให้ตัวเลขหรือช่วงตัวเลข" in BASE_SYSTEM_PROMPT
    assert "match เป็น partial" in BASE_SYSTEM_PROMPT


def test_post_menopause_note_asks_for_the_10mg_figure():
    assert "ต้องระบุตัวเลข 10 มก./วัน" in sex_guidance_th("female", 56)
