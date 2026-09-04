"""SQLAlchemy engine / session factory."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def connect_args_for(database_url: str) -> dict[str, Any]:
    """Driver-level connect args for ``database_url``.

    In production ``DATABASE_URL`` points at Supabase's *pooled* endpoint
    (port 6543), which pools in **transaction mode**: consecutive transactions
    from the same client can land on different server connections. psycopg3
    promotes a query to a server-side prepared statement once it has seen the
    same text 5 times (``prepare_threshold=5`` by default), and that statement
    lives on whichever server connection happened to be borrowed - so a later
    transaction routed elsewhere fails with `prepared statement "_pg3_0" does
    not exist`. It surfaces only after warm-up, which makes it look like a
    random production flake rather than a config problem.

    ``prepare_threshold=None`` turns the promotion off. The cost is re-parsing
    small queries; at this service's ceiling (the Gemini free tier caps us at
    15 requests/minute) that is not measurable, and it is correct against a
    direct connection too, so the same setting is safe locally.
    """
    if make_url(database_url).get_driver_name() != "psycopg":
        return {}
    return {"prepare_threshold": None}


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args_for(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
