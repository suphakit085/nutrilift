"""Tests for citation filtering.

The answer shown to the user must only credit passages it actually referenced.
Attaching every retrieved passage would display misleading sources and inflate
the groundedness score in the evaluation.
"""

import pytest

from app.services.chat import cited_only, clean_answer

PASSAGES = [
    {"label": "S1", "title": "โปรตีน", "document_slug": "protein-requirement"},
    {"label": "S2", "title": "พลังงาน", "document_slug": "energy-balance-cut-bulk"},
    {"label": "S3", "title": "ครีเอทีน", "document_slug": "creatine"},
]


def labels(result):
    return [c["label"] for c in result]


def test_keeps_only_referenced_passages():
    answer = "ควรกินโปรตีน 1.6-2.2 g/kg [S1] และคุมพลังงานตามเป้า [S3]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_returns_empty_when_answer_cites_nothing():
    answer = "ข้าวมันไก่ 1 จานมีประมาณ 596 กิโลแคลอรี่ โปรตีน 26 กรัม"
    assert cited_only(answer, PASSAGES) == []


def test_preserves_retrieval_order_not_mention_order():
    answer = "อ้างอิงหลัง [S3] แล้วค่อยอ้างอิงแรก [S1]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_ignores_invented_labels():
    """The model sometimes writes a marker for a passage that was never sent."""
    answer = "ตามงานวิจัย [S9] และ [S1]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1"]


def test_deduplicates_repeated_markers():
    answer = "[S1] ย่อหน้าแรก ... [S1] ย่อหน้าสอง ... [S1] สรุป"
    assert labels(cited_only(answer, PASSAGES)) == ["S1"]


def test_tolerates_spacing_inside_brackets():
    assert labels(cited_only("ข้อความ [ S2 ]", PASSAGES)) == ["S2"]


def test_lowercase_marker_still_matches():
    assert labels(cited_only("ข้อความ [s2]", PASSAGES)) == ["S2"]


def test_no_passages_returns_empty():
    assert cited_only("อะไรก็ตาม [S1]", []) == []


def test_empty_answer_returns_empty():
    assert cited_only("", PASSAGES) == []


def test_does_not_match_other_bracketed_text():
    """Markdown links and bracketed notes must not be read as citations."""
    answer = "ดูเพิ่มเติม [ฐานข้อมูลอาหาร] และ [S2]"
    assert labels(cited_only(answer, PASSAGES)) == ["S2"]


def test_multiple_markers_in_one_bracket_comma_separated():
    """The model sometimes writes "[S1, S3]" instead of "[S1][S3]"."""
    answer = "ตามข้อมูล [S1, S3]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_multiple_markers_in_one_bracket_no_space():
    answer = "ตามข้อมูล [S1,S3]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_multiple_markers_in_one_bracket_space_separated():
    answer = "ตามข้อมูล [S1 S3]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_markdown_link_is_not_a_retrieved_citation():
    assert cited_only("[S1](https://example.com)", PASSAGES) == []


def test_mixed_note_is_not_a_citation():
    assert cited_only("[S1 ข้อมูลจากระบบ]", PASSAGES) == []


def test_cleanup_removes_unknown_markers_from_displayed_answer():
    assert clean_answer("ข้อความ [S9] [S1, S8; s3]", PASSAGES) == "ข้อความ  [S1, S3]"


def test_cleanup_without_retrieval_cannot_claim_a_source():
    assert clean_answer("ข้อความ [S1]", []) == "ข้อความ "


def test_cleanup_keeps_ordinary_markdown_links():
    assert clean_answer("[ข้อมูล](https://example.com) [S1]", []) == "[ข้อมูล](https://example.com) "


def test_cleanup_supports_semicolon_citations_and_deduplicates():
    assert clean_answer("ข้อความ [s2; S1; S2]", PASSAGES) == "ข้อความ [S2, S1]"


@pytest.mark.parametrize("instruction", [
    ('ขอแนะนำให้ไปที่หน้า **"โปรไฟล์ของฉัน"** แล้วกรอกข้อมูลน้ำหนัก ส่วนสูง อายุ '
     'และระดับกิจกรรม จากนั้นกดปุ่ม **"บันทึกและคำนวณ"** ให้เรียบร้อยก่อน'),
    'เข้าเมนูโปรไฟล์เพื่อกรอกข้อมูล',
    'กดปุ่ม “บันทึกและคำนวณ” ก่อนกลับมาถามใหม่',
    'กรอกข้อมูลในโปรไฟล์ให้ครบ',
    'Go to My Profile and press Save and Calculate',
])
def test_app_instructions_do_not_credit_research(instruction):
    text = instruction + " [S1, S2]"
    cleaned = clean_answer(text, PASSAGES)
    assert instruction in cleaned
    assert cited_only(cleaned, PASSAGES) == []


@pytest.mark.parametrize("separator", [" ", "\n\n"])
def test_nutrition_citations_survive_before_navigation_in_same_paragraph(separator):
    study = "งานวิจัยพบว่าโปรตีนช่วยสนับสนุนการเพิ่มกล้ามเนื้อ [S1]"
    ui = 'ไปที่หน้า "โปรไฟล์ของฉัน" แล้วกด "บันทึกและคำนวณ" [S2, S3]'
    cleaned = clean_answer(study + separator + ui, PASSAGES)
    assert study in cleaned and "บันทึกและคำนวณ" in cleaned
    assert labels(cited_only(cleaned, PASSAGES)) == ["S1"]


def test_nutrition_after_instruction_sentence_and_markdown_links_survive():
    study = "งานวิจัยพบว่าโปรตีนช่วยสนับสนุนการเพิ่มกล้ามเนื้อ [S1]"
    text = 'เปิดหน้า [โปรไฟล์ของฉัน](/profile). ' + study
    assert clean_answer(text, PASSAGES) == text
    assert labels(cited_only(clean_answer(text, PASSAGES), PASSAGES)) == ["S1"]


def test_navigation_cleanup_is_idempotent_and_keeps_links():
    text = 'ไปที่หน้า [โปรไฟล์ของฉัน](/profile) [s1; S2] [S3]'
    once = clean_answer(text, PASSAGES)
    assert "[โปรไฟล์ของฉัน](/profile)" in once
    assert cited_only(once, PASSAGES) == []
    assert clean_answer(once, PASSAGES) == once


def test_numbered_onboarding_and_missing_profile_do_not_credit_research():
    nutrition = "หลักฐานสนับสนุนโปรตีนรวมที่เพียงพอสำหรับผู้ฝึกเวท [S1]"
    missing = "ตอนนี้คุณยังไม่ได้กรอกข้อมูลส่วนตัวในระบบ จึงไม่มีตัวเลขจัดเมนูครับ [S2]"
    steps = ('**สิ่งที่แนะนำให้ทำก่อน:**\n'
             '1. ไปที่หน้า **"โปรไฟล์ของฉัน"** ในระบบ\n'
             '2. กรอกข้อมูลส่วนตัว เช่น น้ำหนัก ส่วนสูง และระดับกิจกรรม\n'
             '3. กดปุ่ม **"บันทึกและคำนวณ"**\n'
             '4. กลับมาที่แชตนี้แล้วขอตัวอย่างเมนูได้เลยครับ [S2]')
    after = "เมื่อคุณบันทึกข้อมูลเรียบร้อยแล้ว ระบบจะสามารถคำนวณและจัดเมนูได้ครับ [S2]"
    text = "\n\n".join((nutrition, missing, steps, after))
    cleaned = clean_answer(text, PASSAGES)
    assert nutrition in cleaned
    assert "กลับมาที่แชตนี้" in cleaned
    assert "[S2]" not in cleaned
    assert labels(cited_only(cleaned, PASSAGES)) == ["S1"]


def test_numbered_research_statements_keep_their_sources():
    text = "1. โปรตีนรวมต่อวันเป็นปัจจัยสำคัญ [S1]\n2. พลังงานขึ้นอยู่กับเป้าหมาย [S2]"
    assert clean_answer(text, PASSAGES) == text
