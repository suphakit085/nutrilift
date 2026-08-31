"""Application settings, loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: backend/.env - resolved from this file, not the working directory, so the
#: ingest CLI and eval/ scripts load the same settings no matter where they run.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # Gemini
    # gemini-3.5-flash's free tier is capped at 20 requests/day *per project*,
    # verified live on 2026-08-31 (a 429 RESOURCE_EXHAUSTED names the exact
    # figure) - a single eval run or a few minutes of manual testing exhausts
    # it. Switched the default to the lite variant, which sits in its own
    # quota bucket (untouched by that cap) and is ~4-5x cheaper on the paid
    # tier if this ever moves off free. Google does not publish per-model
    # free-tier numbers; the authoritative current value for this project is
    # only in the dashboard: aistudio.google.com/rate-limit. See
    # docs/architecture.md for the full tradeoff and eval/SUS-pacing notes.
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    # gemini-2.5-flash/-lite were retired for this project (404 "no longer
    # available to new users") after this project's key was created - confirmed
    # live on 2026-08-31, not just a stale training-data name. gemini-3.6-flash
    # is Google's stated replacement and sits in its own quota bucket, separate
    # from llm_model - which also keeps the judge from sharing a quota with the
    # generator it is judging.
    judge_model: str = "gemini-3.6-flash"
    embed_model: str = "gemini-embedding-001"
    # 1536, not the model's 3072 default - matched to the existing pgvector
    # column so switching providers needed no schema migration or index rebuild.
    embed_dim: int = 1536

    # Database
    database_url: str = "postgresql+psycopg://nutrition:nutrition@localhost:5432/nutrition"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # App
    cors_origins: str = "http://localhost:3000"
    retrieval_top_k: int = 6
    # Cosine-similarity floor for a chunk to be used as context.
    # Re-calibrated on 2026-08-31 after the OpenAI -> Gemini migration (embedding
    # model changed, so the whole similarity scale shifted - a 1536-dim OpenAI
    # vector and a 1536-dim Gemini vector are not comparable). Measured with
    # eval/calibrate_threshold.py over 12 cards: on-topic queries scored
    # 0.662-0.846, off-topic 0.516-0.606 -> 0.63 sits in the gap. The previous
    # OpenAI-era value (0.32) would pass every off-topic query under Gemini's
    # embeddings, silently breaking the out-of-scope refusal. Re-run that script
    # whenever the knowledge base grows substantially or the embedding model
    # changes again.
    retrieval_min_score: float = 0.63
    # How far below the best-matching chunk a sibling chunk may score and
    # still be included. Only applies once the domain gate above has passed.
    retrieval_relative_window: float = 0.10
    # Fuse dense ranking with BM25 over the same candidates. Turned on after
    # hit@k fell to 0.833 at 12 cards; see services/bm25.py for the numbers.
    retrieval_hybrid: bool = True
    # How many extra candidates to fetch for BM25 to reorder.
    retrieval_candidate_multiplier: int = 3
    history_turns: int = 8

    # --- rate limiting -------------------------------------------------
    # Every chat turn costs money, so these are a spend ceiling as much as an
    # abuse control. Tuned for a class-sized SUS study (20-30 users).
    rate_limit_chat_per_hour: int = 20
    rate_limit_chat_per_day: int = 60
    # Hard cap across all users combined, so total daily spend is bounded even
    # if many accounts are created.
    rate_limit_chat_global_per_day: int = 1500
    # Login/register attempts per IP, to blunt password guessing.
    rate_limit_auth_per_15min: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
