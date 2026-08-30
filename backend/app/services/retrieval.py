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


def search(
    db: Session,
    query: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[Passage]:
    """Return the top-k most similar chunks above ``min_score``.

    Score is cosine similarity in [-1, 1]; pgvector's ``cosine_distance`` returns
    ``1 - similarity``, so we convert back for readability in the UI and reports.
    """
    k = top_k if top_k is not None else settings.retrieval_top_k
    threshold = min_score if min_score is not None else settings.retrieval_min_score

    query_vector = embed_text(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    rows = db.execute(
        select(Chunk, Document, distance)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance)
        .limit(k)
    ).all()

    passages: list[Passage] = []
    for chunk, document, dist in rows:
        score = 1.0 - float(dist)
        if score < threshold:
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
