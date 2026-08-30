"""BM25 lexical scoring over Thai text, and rank fusion with dense retrieval.

Why this exists: dense retrieval alone degraded measurably as the knowledge
base grew. Across evaluation runs, hit@k fell 1.00 (3 cards) -> 0.889 (5) ->
0.875 (8) -> 0.833 (12), and the failures shared a shape - a broad card
outranking a specific one because the question's *words* appear in both. The
question "ช่วง bulk ควรกินเกินไปเท่าไหร่" was answered from the nutrient-timing
card while the energy-balance card, which literally contains "bulk", ranked
lower. Embeddings capture topic; they blur the exact term. BM25 restores it.

Postgres has no Thai text-search configuration, so full-text search in the
database is not an option. The corpus here is small (tens to low hundreds of
chunks) so BM25 is computed in memory, which keeps the whole thing dependency-
light and unit-testable. If the base ever outgrows that, the same scores can be
precomputed into a table without changing the interface.

Fusion uses Reciprocal Rank Fusion: it needs no score normalisation between two
scales that are not comparable, and no weight to tune - which matters when
there is not enough labelled data to tune one honestly.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

#: BM25 parameters. k1 controls term-frequency saturation, b the length
#: normalisation; these are the standard defaults and are not tuned here
#: because the question set is far too small to tune them without overfitting.
K1 = 1.5
B = 0.75

#: Rank-fusion constant. 60 is the value from the original RRF paper; it damps
#: the influence of any single retriever's top hit.
RRF_K = 60

_LATIN_OR_DIGIT = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """Split Thai text into words, keeping Latin words and numbers intact.

    Thai is written without spaces, so a whitespace split would make the whole
    sentence one token. pythainlp's newmm engine is a dictionary-based maximum
    matching segmenter - fast, deterministic, and good enough here.
    """
    from pythainlp.tokenize import word_tokenize

    tokens: list[str] = []
    for raw in word_tokenize(text.lower(), engine="newmm"):
        token = raw.strip()
        if not token:
            continue
        # Keep terms like "bulk", "tdee", "1.6", "g/kg" as single units.
        if _LATIN_OR_DIGIT.fullmatch(token) or len(token) > 1:
            tokens.append(token)
    return tokens


@dataclass
class BM25Index:
    """An in-memory BM25 index over a fixed list of documents."""

    doc_tokens: list[list[str]]
    doc_freq: Counter = field(default_factory=Counter)
    avg_len: float = 0.0

    @classmethod
    def build(cls, documents: list[str]) -> BM25Index:
        doc_tokens = [tokenize(d) for d in documents]
        index = cls(doc_tokens=doc_tokens)
        for tokens in doc_tokens:
            for term in set(tokens):
                index.doc_freq[term] += 1
        index.avg_len = (
            sum(len(t) for t in doc_tokens) / len(doc_tokens) if doc_tokens else 0.0
        )
        return index

    def _idf(self, term: str) -> float:
        """Robertson-Sparck Jones IDF with the +0.5 smoothing.

        Clamped at zero: without the clamp, a term appearing in more than half
        the documents gets a negative weight, so a chunk could be *penalised*
        for containing the query word.
        """
        n = len(self.doc_tokens)
        df = self.doc_freq.get(term, 0)
        return max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))

    def score(self, query: str) -> list[float]:
        """BM25 score of every document against ``query``."""
        query_terms = tokenize(query)
        scores = [0.0] * len(self.doc_tokens)
        if not query_terms or not self.doc_tokens:
            return scores

        for i, tokens in enumerate(self.doc_tokens):
            if not tokens:
                continue
            counts = Counter(tokens)
            length = len(tokens)
            total = 0.0
            for term in query_terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                denom = tf + K1 * (1 - B + B * length / (self.avg_len or 1))
                total += self._idf(term) * (tf * (K1 + 1)) / denom
            scores[i] = total
        return scores


def reciprocal_rank_fusion(
    rankings: list[list[int]], *, k: int = RRF_K
) -> dict[int, float]:
    """Fuse several rankings of the same items into one score per item.

    ``rankings`` holds one list of item indices per retriever, each ordered
    best-first. An item's fused score is the sum of 1/(k + rank) over the
    retrievers that ranked it, so agreement between retrievers is what lifts an
    item rather than the magnitude of either score.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


def rank_desc(scores: list[float], *, limit: int | None = None) -> list[int]:
    """Indices of ``scores``, best first, dropping anything scoring zero."""
    order = sorted(
        (i for i, s in enumerate(scores) if s > 0),
        key=lambda i: scores[i],
        reverse=True,
    )
    return order[:limit] if limit is not None else order
