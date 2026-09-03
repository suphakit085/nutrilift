"""Thai folding shared by the guardrail and the meal planner.

Both had the same class of bug: a substring rule comparing text that had been
folded one way against a pattern that had not been folded at all.
"""

from app.services.thai_text import normalize_thai


def test_the_two_spellings_of_nam_fold_together():
    # น + ไม้โท + สระอำ  vs  น + นิคหิต + ไม้โท + สระอา - identical on screen.
    assert normalize_thai("น้ำ") == normalize_thai("นํ้า")
    assert normalize_thai("อดน้ำ") == normalize_thai("อดนํ้า")


def test_sara_am_is_expanded_so_nfkc_text_and_raw_patterns_meet():
    assert normalize_thai("ทำ") == normalize_thai("ทํา")


def test_case_is_folded_for_mixed_scripts():
    assert normalize_thai("SARM") == normalize_thai("sarm")


def test_distinct_words_stay_distinct():
    assert normalize_thai("ข้าว") != normalize_thai("ขาว")
    assert normalize_thai("น้ำ") != normalize_thai("นา")


def test_empty_and_plain_text_are_safe():
    assert normalize_thai("") == ""
    assert normalize_thai("protein") == "protein"
