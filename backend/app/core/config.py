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

    # OpenAI
    openai_api_key: str = ""
    llm_model: str = "gpt-5.6-luna"
    judge_model: str = "gpt-5.6-terra"
    embed_model: str = "text-embedding-3-small"
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
    # Calibrated on 2026-08-31 with eval/calibrate_threshold.py (14 chunks, 3 cards):
    # on-topic queries scored 0.377-0.474, off-topic 0.135-0.257 -> 0.32 sits in the
    # gap. Re-run that script whenever the knowledge base grows substantially.
    retrieval_min_score: float = 0.32
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
