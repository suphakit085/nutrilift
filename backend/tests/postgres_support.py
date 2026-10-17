"""Disposable local databases only. Never falls back to application DATABASE_URL."""

import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

BACKEND = Path(__file__).resolve().parents[1]


def admin_url():
    raw = os.environ.get("NUTRILIFT_PG_TEST_URL")
    if not raw:
        pytest.skip("Set NUTRILIFT_PG_TEST_URL for disposable local PostgreSQL tests")
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or not (url.database or "").endswith("_test")
    ):
        raise RuntimeError(
            "PostgreSQL tests require a loopback URL with a database ending in _test"
        )
    return url


@contextmanager
def migration_config(engine):
    # Existing env.py intentionally reads application settings. Patch only for
    # this synchronous migration and restore immediately, before any HTTP work.
    config = Config(str(BACKEND / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "database_url", engine.url.render_as_string(hide_password=False))
        yield config


def migrate(engine, revision="head", *, downgrade=False):
    with migration_config(engine) as config:
        operation = command.downgrade if downgrade else command.upgrade
        operation(config, revision)


@contextmanager
def migrated_database(revision="head"):
    admin = create_engine(admin_url(), isolation_level="AUTOCOMMIT", hide_parameters=True)
    name = "nl_test_" + uuid.uuid4().hex
    # name is generated here, never supplied by a caller or derived from a URL.
    quoted = admin.dialect.identifier_preparer.quote(name)
    created = False
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {quoted}"))
            created = True
        engine = create_engine(
            admin.url.set(database=name),
            hide_parameters=True,
            connect_args={
                "prepare_threshold": None,
                "options": "-c lock_timeout=8000 -c statement_timeout=15000",
            },
        )
        migrate(engine, revision)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f"DROP DATABASE {quoted} WITH (FORCE)"))
        admin.dispose()
