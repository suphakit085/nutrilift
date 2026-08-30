"""Tests for Thai BM25 scoring and rank fusion.

The lexical half of retrieval exists because dense ranking degraded as the
knowledge base grew: hit@k fell 1.00 -> 0.889 -> 0.875 -> 0.833 across 3, 5, 8
and 12 cards, and the misses were always a broad card outranking a specific one
that contained the query's actual words. These tests pin the behaviour that
fixes that, without needing a database or the embedding API.
"""

import pytest

from app.services.bm25 import (
    BM25Index,
    rank_desc,
    reciprocal_rank_fusion,
    tokenize,
)

DOCS = [
    "ช่วงเพิ่มกล้ามเนื้อ bulk ควรเกินดุลพลังงาน 10-20% ของ TDEE",
    "ช่วงเวลาการกินโปรตีนรอบการฝึก ควรกระจายทุก 3-4 ชั่วโมง",
    "ครีเอทีนโมโนไฮเดรต 3-5 กรัมต่อวัน ไม่จำเป็นต้องโหลด",
]


# --- tokenisation ----------------------------------------------------------


def test_tokenizes_thai_without_spaces():
    tokens = tokenize("ควรกินโปรตีนวันละกี่กรัม")
    assert len(tokens) > 1, "Thai has no spaces; a whitespace split gives one token"
    assert any("โปรตีน" in t for t in tokens)


def test_keeps_latin_terms_intact():
    assert "bulk" in tokenize("ช่วง bulk ควรกินเท่าไหร่")
    assert "tdee" in tokenize("TDEE คืออะไร"), "should be lowercased, not split"


def test_drops_empty_and_whitespace_tokens():
    assert all(t.strip() for t in tokenize("ช่วง   bulk  "))


def test_empty_text_gives_no_tokens():
    assert tokenize("") == []


# --- BM25 scoring ----------------------------------------------------------


def test_ranks_the_document_containing_the_query_term_first():
    """The exact failure dense retrieval kept making."""
    index = BM25Index.build(DOCS)
    scores = index.score("ช่วง bulk ควรกินเกินไปเท่าไหร่")
    assert scores[0] == max(scores)
    assert scores[0] > 0


def test_unrelated_query_scores_zero_everywhere():
    index = BM25Index.build(DOCS)
    assert all(s == 0 for s in index.score("ราคาหุ้นวันนี้"))


def test_idf_is_never_negative():
    """A term in most documents must not penalise the ones containing it."""
    docs = ["โปรตีน ก", "โปรตีน ข", "โปรตีน ค"]
    index = BM25Index.build(docs)
    assert all(s >= 0 for s in index.score("โปรตีน"))


def test_empty_corpus_is_safe():
    index = BM25Index.build([])
    assert index.score("อะไรก็ได้") == []


def test_empty_query_scores_zero():
    index = BM25Index.build(DOCS)
    assert index.score("") == [0.0] * len(DOCS)


def test_longer_document_is_not_automatically_favoured():
    """Length normalisation: padding a document must not lift its score."""
    short = "ครีเอทีน 3-5 กรัมต่อวัน"
    padded = short + " " + "ข้อความอื่นที่ไม่เกี่ยวข้องเลย " * 30
    index = BM25Index.build([short, padded])
    scores = index.score("ครีเอทีน")
    assert scores[0] > scores[1]


# --- ranking helpers -------------------------------------------------------


def test_rank_desc_orders_best_first_and_drops_zeros():
    assert rank_desc([0.1, 0.9, 0.0, 0.5]) == [1, 3, 0]


def test_rank_desc_respects_limit():
    assert rank_desc([0.1, 0.9, 0.5], limit=2) == [1, 2]


def test_rank_desc_on_all_zeros_is_empty():
    assert rank_desc([0.0, 0.0]) == []


# --- reciprocal rank fusion ------------------------------------------------


def test_fusion_rewards_agreement_between_retrievers():
    """An item both retrievers rank second beats one only dense ranks first."""
    dense = [0, 1]
    lexical = [2, 1]
    fused = reciprocal_rank_fusion([dense, lexical])
    assert fused[1] > fused[0]
    assert fused[1] > fused[2]


def test_fusion_includes_items_only_one_retriever_found():
    fused = reciprocal_rank_fusion([[0], [1]])
    assert set(fused) == {0, 1}
    assert fused[0] == pytest.approx(fused[1])


def test_fusion_of_nothing_is_empty():
    assert reciprocal_rank_fusion([[], []]) == {}


def test_fusion_score_decreases_with_rank():
    fused = reciprocal_rank_fusion([[0, 1, 2]])
    assert fused[0] > fused[1] > fused[2]
