"""Shared Gemini client and embedding helper.

Migrated from OpenAI (31 Aug 2026) - see docs/architecture.md for why and what
changed. The Responses/Chat Completions equivalent here is
``client.models.generate_content`` / ``generate_content_stream``; the manual
tool-calling loop lives in services/chat.py exactly as it did for OpenAI.
"""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from typing import Literal

from google import genai
from google.genai import errors as genai_errors

from app.core.config import settings

logger = logging.getLogger(__name__)

#: gemini-embedding-001's free tier has its own per-minute cap, hit live on
#: 2026-09-01 during an eval run - every retrieval.search() call embeds the
#: query, so a bare 429 here silently degrades a "with RAG" turn into an
#: unsourced answer (chat.py's broad except just logs and falls back to
#: use_rag=False). That's the right fallback for a real user's live turn, but
#: it corrupted 12/33 rows of an eval baseline before this retry existed -
#: retrying first, so the fallback only fires when the quota is genuinely
#: unavailable rather than every time a burst of calls crosses the per-minute
#: line.
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_DELAY_S = 20.0
_RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def retry_delay_seconds(message: str) -> float:
    """Seconds Google asks us to wait, +2 s of slack; the default when unstated."""
    match = _RETRY_DELAY_RE.search(message)
    return float(match.group(1)) + 2.0 if match else DEFAULT_RETRY_DELAY_S


#: Longest silence tolerated on a Gemini connection. The SDK's default is no
#: timeout at all, and the chat endpoint's SSE pings every 15 s keep the
#: browser from ever giving up either, so a stalled model call used to leave
#: the user on a spinner forever and pin a worker thread for good. Measured on
#: production 2026-09-24: 2 of ~110 turns stalled past 150 s, while a healthy
#: first token arrives in 1-3 s and the slowest real one seen was 33 s on a bad
#: day. httpx applies this per read, so a long answer that keeps streaming is
#: never cut; only silence is.
MODEL_READ_TIMEOUT_S = 45


@lru_cache
def get_client() -> genai.Client:
    from google.genai import types

    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(MODEL_READ_TIMEOUT_S * 1000)),
    )


def embed_texts(
    texts: list[str],
    *,
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"] = "RETRIEVAL_DOCUMENT",
    max_retries: int = MAX_RATE_LIMIT_RETRIES,
    max_delay_s: float | None = None,
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

    ``max_retries`` / ``max_delay_s`` bound the 429 back-off. The defaults
    (5 retries, sleep as long as Google asks - ~20 s each) are right for ingest
    and eval runs that must eventually succeed. They are wrong inside a live
    chat turn, where the retry loop blocks a worker thread while the user
    stares at a spinner; retrieval.py passes a short budget and lets the turn
    fall back to an unsourced answer instead.
    """
    if not texts:
        return []
    from google.genai import types

    config = types.EmbedContentConfig(output_dimensionality=settings.embed_dim, task_type=task_type)
    for attempt in range(max_retries + 1):
        try:
            response = get_client().models.embed_content(
                model=settings.embed_model, contents=texts, config=config
            )
            break
        except genai_errors.ClientError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            delay = retry_delay_seconds(str(exc))
            if max_delay_s is not None:
                delay = min(delay, max_delay_s)
            logger.warning(
                "embed_content 429, retrying in %.0fs (%d/%d)",
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)
    # The batch endpoint has no per-item index to sort by; order is positional
    # and matches the input list (verified against the live API - see
    # docs/architecture.md's migration notes for the check that confirmed this).
    return [item.values for item in response.embeddings]


def embed_text(
    text: str,
    *,
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"] = "RETRIEVAL_QUERY",
    max_retries: int = MAX_RATE_LIMIT_RETRIES,
    max_delay_s: float | None = None,
) -> list[float]:
    return embed_texts(
        [text], task_type=task_type, max_retries=max_retries, max_delay_s=max_delay_s
    )[0]
