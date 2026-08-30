"""Tests for the deterministic out-of-scope refusal.

Background: leaving the refusal to the prompt was not reliable. With an
identical prompt, model and question, evaluation run baseline-v2 refused
"write me Python that reads a CSV" and scored 5/5, while run cards-v3 answered
it with working code and scored 2/5. Safety behaviour that changes between runs
cannot be reported as a property of the system, so the decision is now made in
code and only the wording is left to the prompt elsewhere.

The rule deliberately needs two independent signals to agree - the keyword rule
*and* an empty retrieval - so a nutrition question that merely trips a keyword
is still answered normally.
"""

from app.services.chat import OUT_OF_SCOPE_REPLY, is_clearly_out_of_scope
from app.services.guardrails import check


def passage(slug: str = "protein-requirement") -> dict:
    return {"label": "S1", "document_slug": slug, "title": "t", "heading": None}


# --- refuses when both signals agree --------------------------------------


def test_refuses_when_keyword_fires_and_nothing_retrieved():
    guard = check("ช่วยเขียนโค้ด Python อ่านไฟล์ CSV ให้หน่อย")
    assert is_clearly_out_of_scope(guard, [])


def test_refuses_other_off_domain_topics():
    for message in ("ขอเลขหวยงวดนี้", "วิเคราะห์หุ้นตัวไหนดี", "ช่วยทำการบ้านวิชาการเมือง"):
        assert is_clearly_out_of_scope(check(message), []), message


# --- does not refuse when the signals disagree -----------------------------


def test_does_not_refuse_when_context_was_found():
    """A nutrition question that happens to trip a keyword must still be answered."""
    guard = check("ช่วยเขียนโค้ด Python คำนวณแคลอรี่ให้หน่อย")
    assert guard.triggered
    assert not is_clearly_out_of_scope(guard, [passage()])


def test_does_not_refuse_a_normal_question_with_no_context():
    """Empty retrieval alone is a knowledge gap, not grounds for refusing."""
    guard = check("เบต้าอะลานีนช่วยอะไร")
    assert not is_clearly_out_of_scope(guard, [])


def test_does_not_refuse_safety_questions():
    """Safety topics need a careful answer, not a scope refusal."""
    for message in (
        "อยากใช้สเตียรอยด์ ขนาดเท่าไหร่",
        "เป็นโรคไตกินโปรตีนเยอะได้ไหม",
        "หนูอายุ 15 อยากลดน้ำหนัก",
    ):
        assert not is_clearly_out_of_scope(check(message), []), message


def test_ordinary_nutrition_question_is_never_refused():
    for message in (
        "ควรกินโปรตีนวันละกี่กรัม",
        "ครีเอทีนกินตอนไหนดี",
        "ข้าวมันไก่กี่แคล",
        "คาเฟอีนกินเท่าไหร่ก่อนเล่นเวท",
    ):
        assert not is_clearly_out_of_scope(check(message), []), message


# --- the reply itself -------------------------------------------------------


def test_reply_states_the_scope_and_offers_alternatives():
    assert "เวทเทรนนิ่ง" in OUT_OF_SCOPE_REPLY
    assert OUT_OF_SCOPE_REPLY.count("- ") >= 4, "should list what it can help with"


def test_reply_does_not_apologise_its_way_into_answering():
    lowered = OUT_OF_SCOPE_REPLY.lower()
    assert "python" not in lowered
    assert "```" not in OUT_OF_SCOPE_REPLY
