"""Tests for the two-stage retrieval filter.

Background: a single flat similarity cutoff conflates two different decisions -
"is this question inside our domain at all?" and "which chunks are relevant to
it?". Measured on the real knowledge base, a flat 0.32 answered the first well
and the second badly: for "ครีเอทีนกินยังไง ต้องโหลดไหม" it kept the myth-busting
chunk (0.361) and discarded the section that actually holds the dosage (0.306),
so the bot said it had no dosage information while the card plainly did.

The gate now uses the *best* score, and the remaining chunks are kept relative
to it.
"""

import pytest

from app.services.retrieval import score_cutoff

THRESHOLD = 0.32
WINDOW = 0.10


# --- stage 1: domain gate --------------------------------------------------


@pytest.mark.parametrize("best", [0.0, 0.124, 0.257, 0.3199])
def test_off_domain_question_keeps_nothing(best):
    """Off-topic queries measured on the real corpus top out at ~0.257."""
    assert score_cutoff(best, THRESHOLD, WINDOW) is None


@pytest.mark.parametrize("best", [0.32, 0.361, 0.444, 0.511])
def test_in_domain_question_returns_a_cutoff(best):
    assert score_cutoff(best, THRESHOLD, WINDOW) is not None


def test_gate_is_inclusive_at_the_threshold():
    assert score_cutoff(0.32, 0.32, WINDOW) == pytest.approx(0.22)


# --- stage 2: relative window ----------------------------------------------


def test_cutoff_is_relative_to_the_best_score():
    assert score_cutoff(0.44, THRESHOLD, WINDOW) == pytest.approx(0.34)
    assert score_cutoff(0.36, THRESHOLD, WINDOW) == pytest.approx(0.26)


def test_creatine_regression_dosage_chunk_survives():
    """The exact case that made RAG score worse than no-RAG on Q006.

    Chunk scores for "ครีเอทีนกินยังไง ต้องโหลดไหม", measured 2026-08-31.
    """
    chunk_scores = {
        "ความเชื่อผิด ๆ ที่พบบ่อย": 0.361,
        "ข้อควรระวัง": 0.319,
        "ครีเอทีนคืออะไรและช่วยอะไร": 0.309,
        "วิธีใช้และปริมาณ": 0.306,
        "แหล่งโปรตีนในอาหารไทยที่หาง่าย": 0.213,
    }
    cutoff = score_cutoff(max(chunk_scores.values()), THRESHOLD, WINDOW)
    kept = {name for name, score in chunk_scores.items() if score >= cutoff}

    assert "วิธีใช้และปริมาณ" in kept, "the dosage section must reach the model"
    assert "แหล่งโปรตีนในอาหารไทยที่หาง่าย" not in kept, "unrelated card must stay out"
    assert len(kept) == 4


def test_a_wider_window_admits_weaker_chunks():
    assert score_cutoff(0.40, THRESHOLD, 0.20) < score_cutoff(0.40, THRESHOLD, 0.05)


def test_zero_window_keeps_only_the_top_score():
    assert score_cutoff(0.40, THRESHOLD, 0.0) == pytest.approx(0.40)


def test_window_never_promotes_an_off_domain_query():
    """A generous window must not rescue a question the gate already rejected."""
    assert score_cutoff(0.257, THRESHOLD, 0.50) is None
