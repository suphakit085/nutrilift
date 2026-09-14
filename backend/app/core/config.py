"""Application settings, loaded from environment / .env."""

import logging
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

#: backend/.env - resolved from this file, not the working directory, so the
#: ingest CLI and eval/ scripts load the same settings no matter where they run.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

#: JWT secrets that appear in this repo's own defaults / .env.example. Any of
#: them in production means every token is forgeable by anyone who read GitHub.
PLACEHOLDER_JWT_SECRETS = frozenset({"change-me", "change-me-to-a-long-random-string"})
MIN_JWT_SECRET_LENGTH = 32
#: The literal value .env.example ships for GEMINI_API_KEY.
PLACEHOLDER_GEMINI_KEY_PREFIX = "AIza..."


def _normalise_origin(raw: str) -> str:
    """Canonical form of one CORS origin.

    Browsers send ``Origin: https://x.vercel.app`` - lowercase scheme and host,
    no trailing slash - and Starlette compares the string exactly, so a value
    pasted into Render as ``https://X.vercel.app/`` silently never matches.
    """
    origin = raw.strip().rstrip("/")
    parts = urlsplit(origin)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path}"
    return origin


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # "production" turns the startup secret check in ``check_production_settings``
    # from a warning into a refusal to boot. Render/Railway are detected even
    # when this is left unset - see ``is_production``.
    environment: str = "development"

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
    # live on 2026-08-31, not just a stale training-data name. Tried Google's
    # stated replacement gemini-3.6-flash next, but its free tier caps at only
    # 20 requests/*day* (confirmed via the aistudio.google.com/rate-limit
    # dashboard on 2026-09-01, showing 21/20 used) - a single eval run's judge
    # calls exhausted it, and unlike a per-minute cap there is no retry-and-wait
    # that fixes a per-day one same-day. Switched to gemini-3.1-flash-lite,
    # which the same dashboard showed essentially untouched (1/500 daily,
    # 1/15 per-minute) and which still sits in its own quota bucket separate
    # from llm_model, keeping the judge from sharing a quota with the
    # generator it is judging.
    judge_model: str = "gemini-3.1-flash-lite"
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
    # Used by chat.is_clearly_out_of_scope together with the keyword rule. The
    # retrieval gate above cannot do this job on its own any more: measured on
    # 2026-09-15 with 26 cards, the eval set's off-domain questions scored
    # 0.520-0.644 and in-domain ones 0.622-0.850, so no single value separates
    # them and 4 of 7 off-domain questions passed the 0.63 gate. A keyword hit
    # plus a best dense score under this value refuses without a model call; a
    # keyword hit on a question retrieval is confident about (>= this) is still
    # answered. See eval/calibrate_threshold.py --verbose for the current spread.
    retrieval_out_of_scope_score: float = 0.66
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
    # Login/register attempts per IP. Deliberately loose: a whole classroom
    # sits behind one NAT during the SUS study, and at 10 the third student to
    # mistype a password locked everyone out. Password guessing is blunted by
    # the per-email login limit below instead.
    rate_limit_auth_per_15min: int = 60
    # Login attempts per email address (any IP), the actual brute-force guard.
    rate_limit_login_per_email_per_15min: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        origins = (_normalise_origin(o) for o in self.cors_origins.split(","))
        return [o for o in origins if o]


def is_production(environ: Mapping[str, str] | None = None) -> bool:
    """Whether this process is a deployed instance rather than a dev machine.

    ``ENVIRONMENT=production`` is the explicit switch, but Render sets ``RENDER``
    and Railway sets ``RAILWAY_*`` on every service automatically, so forgetting
    to set ENVIRONMENT on the host does not quietly disable the secret check.
    """
    env = os.environ if environ is None else environ
    if env.get("ENVIRONMENT", "").strip().lower() == "production":
        return True
    if env.get("RENDER"):
        return True
    return any(key.startswith("RAILWAY_") for key in env)


def production_config_problems(cfg: "Settings") -> list[str]:
    """Settings that must never reach production, as human-readable findings."""
    problems: list[str] = []
    secret = cfg.jwt_secret
    if secret in PLACEHOLDER_JWT_SECRETS:
        problems.append(
            f"JWT_SECRET is the placeholder value {secret!r}; anyone can mint tokens"
        )
    elif len(secret) < MIN_JWT_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is only {len(secret)} characters; use at least "
            f"{MIN_JWT_SECRET_LENGTH} random characters"
        )
    key = cfg.gemini_api_key
    if not key.strip():
        problems.append("GEMINI_API_KEY is empty; every chat turn will fail")
    elif key.startswith(PLACEHOLDER_GEMINI_KEY_PREFIX):
        problems.append("GEMINI_API_KEY is the .env.example placeholder ('AIza...')")
    return problems


def check_production_settings(
    cfg: "Settings", *, environ: Mapping[str, str] | None = None
) -> None:
    """Refuse to boot a production deployment on placeholder secrets.

    Called from the FastAPI lifespan. Outside production the same findings are
    logged as a WARNING so a local checkout with the default ``.env`` keeps
    working.
    """
    problems = production_config_problems(cfg)
    if not problems:
        return
    if is_production(environ):
        raise RuntimeError(
            "Refusing to start in production with unsafe settings:\n  - "
            + "\n  - ".join(problems)
            + "\nSet the variables above on the host (Render/Railway dashboard) and redeploy."
        )
    for problem in problems:
        logger.warning("INSECURE DEV SETTING (fatal in production): %s", problem)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
