"""Shared Gemini client and embedding helper.

Migrated from OpenAI (31 Aug 2026) - see docs/architecture.md for why and what
changed. The Responses/Chat Completions equivalent here is
``client.models.generate_content`` / ``generate_content_stream``; the manual
tool-calling loop lives in services/chat.py exactly as it did for OpenAI.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from google import genai

from app.core.config import settings


@lru_cache
def get_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def embed_texts(
    texts: list[str],
    *,
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"] = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Embed a batch of texts. Order of the returned vectors matches ``texts``.

    ``output_dimensionality`` is pinned to ``settings.embed_dim`` (1536) rather
    than the model's 3072 default, so the pgvector column this project already
    had needed no migration when the provider changed.

    ``task_type`` asymmetry is specific to this embedding model: indexing a
    knowledge chunk and embedding a user's question are different jobs, and the
    model produces measurably better retrieval when told which one it is doing.
    Chunks being ingested should use the default; retrieval.py passes
    RETRIEVAL_QUERY for the user's question.
    """
    if not texts:
        return []
    from google.genai import types

    response = get_client().models.embed_content(
        model=settings.embed_model,
        contents=texts,
        config=types.EmbedContentConfig(
            output_dimensionality=settings.embed_dim, task_type=task_type
        ),
    )
    # The batch endpoint has no per-item index to sort by; order is positional
    # and matches the input list (verified against the live API - see
    # docs/architecture.md's migration notes for the check that confirmed this).
    return [item.values for item in response.embeddings]


def embed_text(
    text: str,
    *,
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"] = "RETRIEVAL_QUERY",
) -> list[float]:
    return embed_texts([text], task_type=task_type)[0]
