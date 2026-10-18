"""Database contention and additive OTP migration on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import RegistrationChallenge, User
from app.services import account_email
from tests.postgres_support import migrate, migrated_database, migration_config
from tests.test_account_lifecycle import account_client
from tests.test_registration_otp import EMAIL, finish, start, verify

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_otp(monkeypatch):
    with migrated_database() as engine, account_client(engine, monkeypatch) as state:
        state.codes = []
        monkeypatch.setattr(
            account_email,
            "send_registration_code",
            lambda email, code, challenge: state.codes.append((email, code, challenge)),
        )
        yield state


def race(*functions):
    barrier = Barrier(len(functions))

    def run(fn):
        barrier.wait(timeout=5)
        return fn()

    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return [f.result(timeout=20) for f in [pool.submit(run, fn) for fn in functions]]


def test_only_one_concurrent_otp_verification_succeeds(pg_otp):
    s = pg_otp
    start(s)
    results = race(lambda: verify(s), lambda: verify(s))
    assert sorted(r.status_code for r in results) == [200, 400]


def test_only_one_concurrent_password_setup_succeeds(pg_otp):
    s = pg_otp
    start(s)
    grant = verify(s).json()["setup_token"]
    results = race(lambda: finish(s, grant), lambda: finish(s, grant))
    assert sorted(r.status_code for r in results) == [200, 400]
    with Session(s.engine) as db:
        assert len(list(db.scalars(select(User).where(User.email == EMAIL)))) == 1


def test_concurrent_wrong_attempts_cannot_exceed_persistent_limit(pg_otp):
    s = pg_otp
    start(s)
    wrong = "000000" if s.codes[-1][1] != "000000" else "000001"
    results = race(*[lambda: verify(s, code=wrong) for _ in range(7)])
    assert all(r.status_code == 400 for r in results)
    with Session(s.engine) as db:
        assert db.get(RegistrationChallenge, UUID(s.codes[-1][2])).attempts == 5
    assert verify(s).status_code == 400


def test_first_concurrent_start_is_serialized_by_email(pg_otp):
    s = pg_otp

    def request():
        return s.client.post(
            "/auth/registration/start",
            json={"email": EMAIL, "accepted_terms": True, "is_adult": True},
        )

    results = race(request, request)
    assert sorted(r.status_code for r in results) == [200, 429]
    assert len(s.codes) == 1


def test_otp_migration_preserves_existing_verified_credentials():
    with migrated_database("f16c6106a001") as engine:
        identifier = uuid4()
        digest = hash_password("ExistingPassword_123!")
        timestamp = datetime.now(UTC)
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO users (id,email,password_hash,created_at,email_verified_at) "
                    "VALUES (:id,:email,:hash,:at,:at)"
                ),
                {"id": identifier, "email": EMAIL, "hash": digest, "at": timestamp},
            )
        migrate(engine)
        with Session(engine) as db:
            user = db.get(User, identifier)
            assert (
                user.email == EMAIL
                and user.password_hash == digest
                and user.email_verified_at == timestamp
            )
        with migration_config(engine) as cfg:
            command.check(cfg)
