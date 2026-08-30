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
    history_turns: int = 8

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
