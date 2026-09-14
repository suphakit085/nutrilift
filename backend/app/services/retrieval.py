"""Retrieval over the knowledge-card chunks stored in pgvector.

Dense (embedding) ranking, optionally fused with BM25 - see services/bm25.py
for why the lexical half was added.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.services.llm import embed_text

logger = logging.getLogger(__name__)


@dataclass
class Passage:
    """One retrieved chunk, already labelled [S1], [S2], ... for the prompt."""

    label: str
    score: float
    chunk_id: str
    document_id: str
    document_slug: str
    title: str
    heading: str | None
    content: str
    source_refs: list | None

    def as_dict(self) -> dict:
        return asdict(self)

    def as_citation(self) -> dict:
        """The trimmed form persisted on the message row and shown in the UI."""
        return {
            "label": self.label,
            "title": self.title,
            "heading": self.heading,
            "document_slug": self.document_slug,
            "score": round(self.score, 4),
            "source_refs": self.source_refs,
        }


def _fuse_with_bm25(query: str, kept: list[tuple]) -> list[tuple]:
    """Re-order accepted candidates by fusing dense rank with a BM25 rank.

    The index is built over just these candidates rather than the whole corpus.
    That is deliberate: the dense stage has already decided what is in scope, and
    BM25's job here is only to settle the order among them - which is exactly
    where dense retrieval was failing as the base grew.
    """
    from app.services.bm25 import BM25Index, rank_desc, reciprocal_rank_fusion

    texts = [chunk.content for chunk, _, _ in kept]
    try:
        lexical = BM25Index.build(texts).score(query)
    except Exception:
        logger.exception("BM25 scoring failed; falling back to dense order")
        return kept

    dense_rank = rank_desc([score for _, _, score in kept])
    lexical_rank = rank_desc(lexical)
    if not lexical_rank:
        # No query term appears in any candidate; dense order is all we have.
        return kept

    fused = reciprocal_rank_fusion([dense_rank, lexical_rank])
    order = sorted(range(len(kept)), key=lambda i: fused.get(i, 0.0), reverse=True)
    return [kept[i] for i in order]


def score_cutoff(best_score: float, threshold: float, window: float) -> float | None:
    """The minimum score a chunk needs to be kept, or ``None`` to keep nothing.

    Split out as a pure function so the two-stage filtering rule is unit-tested
    rather than only observable through a live database and embedding calls.
    """
    if best_score < threshold:
        return None
    return best_score - window


def search(
    db: Session,
    query: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    relative_window: float | None = None,
) -> list[Passage]:
    """Return the chunks most similar to ``query``.

    Score is cosine similarity in [-1, 1]; pgvector's ``cosine_distance`` returns
    ``1 - similarity``, so we convert back for readability in the UI and reports.

    Filtering happens in two stages, because "is this question in our domain?"
    and "which chunks are relevant to it?" are different questions and a single
    flat cutoff answers them badly:

    1. **Domain gate** - if even the best chunk scores below ``min_score``, the
       question is outside the knowledge base and nothing is returned.
    2. **Relative window** - otherwise, keep every chunk within
       ``relative_window`` of the best score, so a strong match brings the rest
       of its card along.

    A single flat cutoff at 0.32 measurably hurt: for "ครีเอทีนกินยังไง ต้องโหลดไหม"
    it kept only the myth-busting chunk (0.361) and discarded the section holding
    the actual dosage (0.306), so the bot answered that it had no dosage data
    while the card plainly did.

    Ranking is hybrid when ``settings.retrieval_hybrid`` is on: the dense
    candidates are re-ordered by fusing them with a BM25 ranking of the same
    candidates. The gate above still runs on the *dense* score, so the
    calibration in eval/calibrate_threshold.py keeps its meaning; only the order
    within an accepted set changes.
    """
    k = top_k if top_k is not None else settings.retrieval_top_k
    threshold = min_score if min_score is not None else settings.retrieval_min_score
    window = (
        relative_window if relative_window is not None else settings.retrieval_relative_window
    )

    # Short retry budget: this runs inside a live chat turn on a worker thread.
    # One quick retry catches a burst crossing the per-minute line; anything
    # longer and the caller's fallback (answer without sources) is the better
    # experience than a 20 s+ stall. Ingest/eval keep the long defaults.
    query_vector = embed_text(query, max_retries=1, max_delay_s=5.0)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    # Over-fetch so BM25 has candidates the dense ranking placed just outside
    # top-k; without this, fusion can only reorder what dense already liked.
    fetch = k * settings.retrieval_candidate_multiplier if settings.retrieval_hybrid else k
    rows = db.execute(
        select(Chunk, Document, distance)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance)
        .limit(fetch)
    ).all()
    if not rows:
        return []

    scored = [(chunk, document, 1.0 - float(dist)) for chunk, document, dist in rows]
    cutoff = score_cutoff(scored[0][2], threshold, window)
    if cutoff is None:
        return []

    if settings.retrieval_hybrid and len(scored) > 1:
        # Fuse over *all* candidates first, then window the fused order. Fusing
        # first matters: the chunk BM25 is meant to rescue is usually the one
        # dense ranked just too low to make top-k on its own (measured on the
        # five questions dense was failing: windowing before fusion rescued
        # 1 of 5, fusing first rescued 4 of 5).
        #
        # The window still has to be applied afterwards. Until 2026-09-15 it
        # was not - this branch took the fused top-k unfiltered - so any
        # candidate BM25 happened to like reached the model regardless of its
        # dense score. Over the 150-question eval set that put 164 of 876
        # passages (19%) below the documented cutoff into the prompt; applying
        # the cutoff changed hit@k and MRR by nothing.
        ranked = _fuse_with_bm25(query, scored)
    else:
        ranked = scored
    kept = [item for item in ranked if item[2] >= cutoff][:k]

    passages: list[Passage] = []
    for chunk, document, score in kept:
        passages.append(
            Passage(
                label=f"S{len(passages) + 1}",
                score=score,
                chunk_id=str(chunk.id),
                document_id=str(document.id),
                document_slug=document.slug,
                title=document.title,
                heading=chunk.heading,
                content=chunk.content,
                source_refs=document.source_refs,
            )
        )
    return passages
