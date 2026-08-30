"""Shared OpenAI client and embedding helper."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.core.config import settings


@lru_cache
def get_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Order of the returned vectors matches ``texts``."""
    if not texts:
        return []
    response = get_client().embeddings.create(model=settings.embed_model, input=texts)
    # The API may return items out of order; sort by index to be safe.
    items = sorted(response.data, key=lambda d: d.index)
    return [item.embedding for item in items]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
