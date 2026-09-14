"""``retrieval.search`` end to end, with the database and embedding call faked.

test_retrieval_filter.py covers the pure ``score_cutoff`` rule. Nothing covered
the code that *applies* it, and in hybrid mode nothing did: the fused top-k was
returned unfiltered, so a candidate BM25 liked reached the model however low
its dense score (found 2026-09-15: 164 of 876 passages across the 150-question
set sat below the documented window). These tests pin the window to the code
path that is actually on in production.
"""

from types import SimpleNamespace

import pytest

from app.services import retrieval


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Returns the pre-ranked candidate list whatever the query is."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, _stmt):
        return _Rows(self.rows)


def _candidate(slug: str, score: float, text: str):
    chunk = SimpleNamespace(id=f"c-{slug}-{score}", heading="h", content=text, embedding=None)
    doc = SimpleNamespace(id=f"d-{slug}", slug=slug, title=slug, source_refs=[])
    return (chunk, doc, 1.0 - score)  # pgvector hands back cosine *distance*


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(retrieval, "embed_text", lambda q, **kw: [0.0])
    monkeypatch.setattr(retrieval.settings, "retrieval_top_k", 6)
    monkeypatch.setattr(retrieval.settings, "retrieval_min_score", 0.63)
    monkeypatch.setattr(retrieval.settings, "retrieval_relative_window", 0.10)
    monkeypatch.setattr(retrieval.settings, "retrieval_candidate_multiplier", 3)
    monkeypatch.setattr(retrieval.settings, "retrieval_hybrid", True)
    # Make BM25 adore the weakest candidate, which is the failure mode.
    monkeypatch.setattr(retrieval, "_fuse_with_bm25", lambda q, kept: list(reversed(kept)))
    return monkeypatch


ROWS = [
    _candidate("protein-requirement", 0.85, "โปรตีน 1.6 g/kg"),
    _candidate("protein-requirement", 0.80, "โปรตีนต่อมื้อ"),
    _candidate("nutrient-timing", 0.77, "หลังฝึก"),
    _candidate("caffeine", 0.70, "คาเฟอีน"),  # below 0.85 - 0.10
    _candidate("fiber", 0.66, "ใยอาหาร"),  # below the window too
]


def test_hybrid_mode_still_applies_the_relative_window(stub):
    got = retrieval.search(_FakeDB(ROWS), "โปรตีนวันละเท่าไหร่")
    slugs = {p.document_slug for p in got}
    assert "caffeine" not in slugs and "fiber" not in slugs
    assert all(p.score >= 0.85 - 0.10 for p in got)
    assert len(got) == 3


def test_window_is_applied_after_fusion_not_before(stub):
    """Fused order decides the labels; the window only trims the tail."""
    got = retrieval.search(_FakeDB(ROWS), "q")
    # our fake fusion reversed the list, so the survivors come back reversed
    assert [p.document_slug for p in got] == [
        "nutrient-timing",
        "protein-requirement",
        "protein-requirement",
    ]
    assert [p.label for p in got] == ["S1", "S2", "S3"]


def test_dense_mode_unchanged(stub):
    stub.setattr(retrieval.settings, "retrieval_hybrid", False)
    got = retrieval.search(_FakeDB(ROWS), "q")
    assert [round(p.score, 2) for p in got] == [0.85, 0.80, 0.77]


def test_domain_gate_still_returns_nothing_off_domain(stub):
    rows = [_candidate("fiber", 0.60, "x"), _candidate("caffeine", 0.55, "y")]
    assert retrieval.search(_FakeDB(rows), "วันนี้อากาศเป็นยังไง") == []


def test_top_k_caps_the_windowed_list(stub):
    rows = [_candidate("protein-requirement", 0.90 - i * 0.01, f"t{i}") for i in range(10)]
    got = retrieval.search(_FakeDB(rows), "q")
    assert len(got) == 6
