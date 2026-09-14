"""The out-of-scope refusal's second signal is a score, not "nothing retrieved".

Measured 2026-09-15 with 26 cards: the eval set's off-domain questions scored
0.520-0.644 against the knowledge base, in-domain ones 0.622-0.850. Four of the
seven off-domain questions therefore cleared the 0.63 retrieval gate, and since
``is_clearly_out_of_scope`` demanded an *empty* retrieval, the deterministic
refusal fired for two of seven. The other five were left to the model, which
answered a weather question with hydration advice and offered to translate a
menu. The keyword list also covered none of those five request types.
"""

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.chat import is_clearly_out_of_scope
from app.services.guardrails import Flag, check


def passage(score: float | None = None, slug: str = "protein-requirement"):
    if score is None:
        return {"label": "S1", "document_slug": slug, "title": "t", "heading": None}
    return SimpleNamespace(label="S1", document_slug=slug, score=score)


@pytest.fixture(autouse=True)
def _threshold(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_out_of_scope_score", 0.66)


# --- the request types from the eval set now trip the keyword rule ----------


@pytest.mark.parametrize(
    "message",
    [
        "วันนี้อากาศเป็นยังไงบ้าง เดี๋ยวจะไปเล่นเวท",
        "ช่วยแปลเมนูอาหารนี้เป็นภาษาอังกฤษให้หน่อย",
        "ช่วยหาคลิปสอนท่าสควอทที่ถูกต้องให้หน่อย",
        "แนะนำเทรนเนอร์ฟิตเนสแถวบ้านให้หน่อย",
        "แนะนำยิมใกล้บ้านหน่อย",
        "ช่วยแต่งกลอนเกี่ยวกับการออกกำลังกายให้หน่อย",
        "ช่วยเขียนโค้ด Python อ่านไฟล์ CSV ให้หน่อย",
    ],
)
def test_eval_set_off_domain_requests_trip_the_keyword_rule(message):
    assert Flag.OUT_OF_SCOPE in check(message).flags


def test_knee_pain_is_a_medical_refusal_not_a_nutrition_question():
    guard = check("เล่นเวทแล้วปวดข้อเข่ามาก ควรทำยังไง")
    assert Flag.MEDICAL in guard.flags


def test_muscle_soreness_after_training_is_not_medical():
    """The squashed-space match must not turn "เจ็บ หลังเล่นเวท" into back pain."""
    assert Flag.MEDICAL not in check("กล้ามเนื้อเจ็บ หลังเล่นเวท กินอะไรช่วยฟื้นตัว").flags


# --- keyword + weak retrieval refuses; keyword + confident retrieval answers --


def test_refuses_when_keyword_fires_and_retrieval_is_weak():
    guard = check("วันนี้อากาศเป็นยังไงบ้าง เดี๋ยวจะไปเล่นเวท")
    assert is_clearly_out_of_scope(guard, [passage(0.644), passage(0.61)])


def test_answers_when_keyword_fires_but_retrieval_is_confident():
    """The sentence scored 0.777 against the real base on 2026-09-15."""
    guard = check("วันนี้อากาศร้อนมาก เล่นเวทควรดื่มน้ำเท่าไหร่")
    assert Flag.OUT_OF_SCOPE in guard.flags
    assert not is_clearly_out_of_scope(guard, [passage(0.777)])


def test_threshold_is_inclusive_on_the_confident_side():
    guard = check("แปลให้หน่อย")
    assert not is_clearly_out_of_scope(guard, [passage(0.66)])
    assert is_clearly_out_of_scope(guard, [passage(0.6599)])


def test_best_score_decides_not_the_first_passage():
    guard = check("แปลให้หน่อย")
    assert not is_clearly_out_of_scope(guard, [passage(0.60), passage(0.70)])


def test_passages_without_scores_count_as_confident():
    """Callers that only know *whether* something was retrieved keep the old rule."""
    guard = check("ช่วยเขียนโค้ด Python คำนวณแคลอรี่ให้หน่อย")
    assert not is_clearly_out_of_scope(guard, [passage()])


def test_empty_retrieval_still_refuses():
    assert is_clearly_out_of_scope(check("ขอเลขหวยงวดนี้"), [])


def test_no_keyword_means_no_refusal_however_weak_retrieval_is():
    assert not is_clearly_out_of_scope(check("เบต้าอะลานีนช่วยอะไร"), [passage(0.50)])
