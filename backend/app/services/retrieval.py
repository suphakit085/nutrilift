"""Dense retrieval over the knowledge-card chunks stored in pgvector."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.services.llm import embed_text


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
    """
    k = top_k if top_k is not None else settings.retrieval_top_k
    threshold = min_score if min_score is not None else settings.retrieval_min_score
    window = (
        relative_window if relative_window is not None else settings.retrieval_relative_window
    )

    query_vector = embed_text(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    rows = db.execute(
        select(Chunk, Document, distance)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance)
        .limit(k)
    ).all()
    if not rows:
        return []

    scored = [(chunk, document, 1.0 - float(dist)) for chunk, document, dist in rows]
    cutoff = score_cutoff(scored[0][2], threshold, window)
    if cutoff is None:
        return []

    passages: list[Passage] = []
    for chunk, document, score in scored:
        if score < cutoff:
            continue
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
