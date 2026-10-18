"""Actual Alembic schemas and PostgreSQL contention; no live mail or production DB."""

import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import (
    AuthActionToken,
    AuthSession,
    Conversation,
    Document,
    Food,
    FoodLogEntry,
    Message,
    Profile,
    ProfileRevision,
    User,
)
from app.services import accounts
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from tests.postgres_support import admin_url, migrate, migrated_database, migration_config
from tests.test_account_lifecycle import NEW_PASSWORD, PASSWORD, account_client, login, signup

pytestmark = pytest.mark.postgres

PROFILE = {
    "sex": "male",
    "birth_year": 2000,
    "birth_month": 1,
    "height_cm": 175,
    "weight_kg": 70,
    "body_fat_pct": None,
    "activity_level": "moderate",
    "training_days": 3,
    "goal": "cut",
    "restrictions": [],
}


@pytest.fixture
def pg_account(monkeypatch):
    with migrated_database() as engine, account_client(engine, monkeypatch) as state:
        yield state


def wait_for_lock_waiters(engine, minimum):
    """Prove requests reached PostgreSQL lock contention, rather than relying on sleeps."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
        if count >= minimum:
            return
        Event().wait(0.02)
    raise AssertionError(f"Expected at least {minimum} PostgreSQL lock waiters")


def user_id(state, headers):
    return uuid.UUID(state.client.get("/auth/me", headers=headers).json()["id"])


def test_fresh_migrations_match_current_orm_schema(pg_account):
    state = pg_account
    with state.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "f16c6106a001"
        assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    with migration_config(state.engine) as config:
        command.check(config)


@pytest.mark.parametrize("base_revision", ["e43c6103b001", "f16c6106a002"])
def test_upgrade_preserves_legacy_accounts_and_data_and_requires_real_verification(
    monkeypatch, base_revision
):
    identifier = uuid.uuid4()
    with migrated_database(base_revision) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,email,password_hash,created_at,consented_at,consent_version) "
                    "VALUES (:id,:email,:password,:created,:created,:version)"
                ),
                {
                    "id": identifier,
                    "email": "legacy@example.com",
                    "password": hash_password(PASSWORD),
                    "created": datetime.now(UTC),
                    "version": "2026-09-01",
                },
            )
        with Session(engine) as db:
            db.add(Profile(user_id=identifier, **PROFILE))
            if base_revision == "f16c6106a002":
                db.add(
                    ProfileRevision(
                        user_id=identifier,
                        effective_date=date(2026, 10, 17),
                        profile_snapshot=PROFILE,
                        targets=calc_nutrition_targets(ProfileInput(**PROFILE)),
                    )
                )
            db.commit()
        with engine.connect() as connection:
            preserved = connection.execute(
                text("SELECT row_to_json(p)::text FROM profiles p")
            ).all()
            saved_history = (
                connection.execute(
                    text("SELECT row_to_json(p)::text FROM profile_revisions p")
                ).all()
                if base_revision == "f16c6106a002"
                else []
            )
        migrate(engine)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT row_to_json(p)::text FROM profiles p")).all()
                == preserved
            )
            assert (
                connection.execute(
                    text("SELECT row_to_json(p)::text FROM profile_revisions p")
                ).all()
                == saved_history
            )
        with Session(engine) as db:
            legacy = db.get(User, identifier)
            assert legacy.email_verified_at is None and legacy.consent_withdrawn_at is None
            assert verify_password(PASSWORD, legacy.password_hash)
            assert db.get(Profile, identifier).weight_kg == 70
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
            assert db.scalar(select(func.count()).select_from(ProfileRevision)) == len(
                saved_history
            )
        with account_client(engine, monkeypatch) as state:
            old = {"Authorization": "Bearer " + create_access_token(str(identifier))}
            assert state.client.get("/auth/me", headers=old).status_code == 401
            result = login(state, email="legacy@example.com")
            assert result.status_code == 200 and result.json()["email_verification_required"]
            headers = {"Authorization": "Bearer " + result.json()["access_token"]}
            assert state.client.get("/profile", headers=headers).status_code == 403
            assert (
                state.client.post(
                    "/auth/resend-verification", json={"email": "legacy@example.com"}
                ).status_code
                == 200
            )
            assert (
                state.client.post(
                    "/auth/verify-email",
                    json={
                        "token": state.messages[-1]["token"],
                        "new_password": NEW_PASSWORD,
                    },
                ).status_code
                == 200
            )
            headers = {
                "Authorization": "Bearer "
                + login(state, email="legacy@example.com", password=NEW_PASSWORD).json()[
                    "access_token"
                ]
            }
            assert state.client.get("/auth/me", headers=headers).json()["needs_consent"] is True
            assert state.client.post("/auth/consent", headers=headers).status_code == 200
            assert state.client.get("/profile", headers=headers).json()["weight_kg"] == 70
        # Rollback is tested only on this disposable DB. It must preserve legacy
        # data; new auth/history tables are intentionally removed by downgrade.
        migrate(engine, "e43c6103b001", downgrade=True)
        assert "auth_sessions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert connection.scalar(text("SELECT weight_kg FROM profiles")) == 70
        migrate(engine)
        with Session(engine) as db:
            assert db.get(User, identifier).email_verified_at is None
            assert db.get(Profile, identifier).weight_kg == 70


@pytest.mark.parametrize(
    "purpose,path",
    [
        ("verify_email", "/auth/verify-email"),
        ("reset_password", "/auth/reset-password"),
        ("change_email", "/auth/confirm-email"),
    ],
)
def test_same_email_link_can_only_commit_once_under_contention(pg_account, purpose, path):
    state = pg_account
    headers = signup(state, verified=purpose != "verify_email")
    identifier = user_id(state, headers)
    if purpose == "reset_password":
        assert (
            state.client.post(
                "/auth/forgot-password", json={"email": "owner@example.com"}
            ).status_code
            == 200
        )
    elif purpose == "change_email":
        assert (
            state.client.post(
                "/auth/change-email",
                headers=headers,
                json={
                    "email": "renamed@example.com",
                    "password": PASSWORD,
                },
            ).status_code
            == 200
        )
    raw = state.messages[-1]["token"]
    payload = {"token": raw}
    if purpose != "change_email":
        payload["new_password"] = NEW_PASSWORD
    # A third transaction holds the user so both HTTP requests are demonstrably
    # waiting on the real database lock before we release them.
    with Session(state.engine) as blocker, ThreadPoolExecutor(max_workers=2) as workers:
        blocker.execute(select(User).where(User.id == identifier).with_for_update())
        pending = [workers.submit(state.client.post, path, json=payload) for _ in range(2)]
        try:
            wait_for_lock_waiters(state.engine, 2)
        finally:
            blocker.commit()
        results = [job.result(timeout=12) for job in pending]
    assert sorted(row.status_code for row in results) == [200, 400]
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    with Session(state.engine) as db:
        action = db.scalar(
            select(AuthActionToken).where(
                AuthActionToken.token_hash == hashlib.sha256(raw.encode()).hexdigest()
            )
        )
        assert action.used_at is not None
        account = db.get(User, identifier)
        assert account.email == (
            "renamed@example.com" if purpose == "change_email" else "owner@example.com"
        )


def test_login_waiting_for_password_reset_cannot_issue_a_session_using_old_password(
    pg_account, monkeypatch
):
    state = pg_account
    headers = signup(state)
    assert (
        state.client.post("/auth/forgot-password", json={"email": "owner@example.com"}).status_code
        == 200
    )
    raw = state.messages[-1]["token"]
    acquired, proceed = Event(), Event()
    consume = accounts.consume_action

    def hold_reset(*args, **kwargs):
        result = consume(*args, **kwargs)
        acquired.set()
        if not proceed.wait(7):
            raise AssertionError("Test did not release reset transaction")
        return result

    monkeypatch.setattr(accounts, "consume_action", hold_reset)
    with ThreadPoolExecutor(max_workers=2) as workers:
        reset = workers.submit(
            state.client.post,
            "/auth/reset-password",
            json={
                "token": raw,
                "new_password": NEW_PASSWORD,
            },
        )
        try:
            assert acquired.wait(5)
            old_login = workers.submit(login, state)
            wait_for_lock_waiters(state.engine, 1)
        finally:
            proceed.set()
        assert reset.result(timeout=12).status_code == 200
        assert old_login.result(timeout=12).status_code == 401
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    assert login(state, password=NEW_PASSWORD).status_code == 200


def test_two_password_changes_cannot_both_succeed_with_the_same_old_password(pg_account):
    state = pg_account
    headers = signup(state)
    identifier = user_id(state, headers)
    passwords = [NEW_PASSWORD, "AnotherChangedPassword_789!"]
    with Session(state.engine) as blocker, ThreadPoolExecutor(max_workers=2) as workers:
        blocker.execute(select(User).where(User.id == identifier).with_for_update())
        jobs = [
            workers.submit(
                state.client.post,
                "/auth/change-password",
                headers=headers,
                json={"password": PASSWORD, "new_password": password},
            )
            for password in passwords
        ]
        try:
            wait_for_lock_waiters(state.engine, 2)
        finally:
            blocker.commit()
        results = [job.result(timeout=12) for job in jobs]
    assert sorted(row.status_code for row in results) == [200, 400]
    winner = next(row for row in results if row.status_code == 200)
    rotated = {"Authorization": "Bearer " + winner.json()["access_token"]}
    assert state.client.get("/auth/me", headers=rotated).status_code == 200
    assert state.client.get("/auth/me", headers=headers).status_code == 401


def test_logout_all_revokes_a_login_issued_just_before_it(pg_account, monkeypatch):
    state = pg_account
    headers = signup(state)
    issued, proceed = Event(), Event()
    issue_session = accounts.issue_session

    def hold_login(*args, **kwargs):
        token = issue_session(*args, **kwargs)
        issued.set()
        if not proceed.wait(7):
            raise AssertionError("Test did not release login transaction")
        return token

    monkeypatch.setattr(accounts, "issue_session", hold_login)
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending_login = workers.submit(login, state)
        try:
            assert issued.wait(5)
            logout = workers.submit(state.client.post, "/auth/logout-all", headers=headers)
            wait_for_lock_waiters(state.engine, 1)
        finally:
            proceed.set()
        result = pending_login.result(timeout=12)
        assert result.status_code == 200
        assert logout.result(timeout=12).status_code == 204
    just_issued = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert state.client.get("/auth/me", headers=just_issued).status_code == 401
    assert state.client.get("/auth/me", headers=headers).status_code == 401


def test_resend_committing_first_prevents_pending_use_of_old_verification_link(
    pg_account, monkeypatch
):
    state = pg_account
    signup(state, verified=False)
    old_token = state.messages[-1]["token"]
    issued, proceed = Event(), Event()
    new_action = accounts.new_action

    def hold_resend(*args, **kwargs):
        token = new_action(*args, **kwargs)
        issued.set()
        if not proceed.wait(7):
            raise AssertionError("Test did not release resend transaction")
        return token

    monkeypatch.setattr(accounts, "new_action", hold_resend)
    with ThreadPoolExecutor(max_workers=2) as workers:
        resend = workers.submit(
            state.client.post, "/auth/resend-verification", json={"email": "owner@example.com"}
        )
        try:
            assert issued.wait(5)
            old_verification = workers.submit(
                state.client.post,
                "/auth/verify-email",
                json={"token": old_token, "new_password": NEW_PASSWORD},
            )
            wait_for_lock_waiters(state.engine, 1)
        finally:
            proceed.set()
        assert resend.result(timeout=12).status_code == 200
        assert old_verification.result(timeout=12).status_code == 400
    assert (
        state.client.post(
            "/auth/verify-email",
            json={
                "token": state.messages[-1]["token"],
                "new_password": NEW_PASSWORD,
            },
        ).status_code
        == 200
    )


def test_concurrent_first_profile_saves_keep_one_profile_and_both_revisions(pg_account):
    state = pg_account
    headers = signup(state)
    identifier = user_id(state, headers)
    with Session(state.engine) as blocker, ThreadPoolExecutor(max_workers=2) as workers:
        blocker.execute(select(User).where(User.id == identifier).with_for_update())
        jobs = [
            workers.submit(
                state.client.put, "/profile", headers=headers, json={**PROFILE, "weight_kg": weight}
            )
            for weight in (70, 80)
        ]
        try:
            wait_for_lock_waiters(state.engine, 2)
        finally:
            blocker.commit()
        assert [job.result(timeout=12).status_code for job in jobs] == [200, 200]
    with Session(state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Profile)) == 1
        assert db.scalar(select(func.count()).select_from(ProfileRevision)) == 2
    rows = state.client.get("/profile/history", headers=headers).json()
    current = state.client.get("/profile", headers=headers).json()
    assert rows[0]["profile"]["weight_kg"] == current["weight_kg"]


def test_database_cascades_all_owned_data_without_deleting_shared_food_or_other_users(pg_account):
    state = pg_account
    headers = signup(state)
    other = signup(state, "other@example.com")
    identifier = user_id(state, headers)
    assert state.client.put("/profile", headers=headers, json=PROFILE).status_code == 200
    conversation = state.client.post("/conversations", headers=headers).json()
    with Session(state.engine) as db:
        shared = Food(
            name_th="Test food",
            serving_desc="100 g",
            serving_g=100,
            kcal=100,
            protein_g=10,
            carb_g=10,
            fat_g=2,
        )
        db.add(shared)
        db.add(Document(slug="test-shared", title="Shared knowledge"))
        first = Message(
            id=uuid.uuid4(),
            conversation_id=uuid.UUID(conversation["id"]),
            role="user",
            content="Test message",
        )
        db.add(first)
        db.flush()
        db.add(
            Message(
                conversation_id=first.conversation_id,
                role="assistant",
                content="Test answer",
                reply_to_id=first.id,
            )
        )
        db.commit()
        food_identifier = str(shared.id)
    assert (
        state.client.post(
            "/food-log",
            headers=headers,
            json={
                "food_id": food_identifier,
                "quantity_servings": 1,
                "meal_type": "breakfast",
                "logged_date": date.today().isoformat(),
            },
        ).status_code
        == 201
    )
    assert (
        state.client.request(
            "DELETE", "/auth/account", headers=headers, json={"password": PASSWORD}
        ).status_code
        == 204
    )
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    assert state.client.get("/auth/me", headers=other).status_code == 200
    with Session(state.engine) as db:
        assert db.get(User, identifier) is None
        for model in [
            Profile,
            ProfileRevision,
            AuthSession,
            AuthActionToken,
            Conversation,
            FoodLogEntry,
        ]:
            assert (
                db.scalar(
                    select(func.count()).select_from(model).where(model.user_id == identifier)
                )
                == 0
            )
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(Food)) == 1
        assert db.scalar(select(func.count()).select_from(Document)) == 1


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://test:test@db.example.com/app_test",
        "postgresql+psycopg://test:test@127.0.0.1/production",
        "sqlite:///production.db",
    ],
)
def test_integration_guard_rejects_remote_or_non_test_databases(monkeypatch, url):
    monkeypatch.setenv("NUTRILIFT_PG_TEST_URL", url)
    with pytest.raises(RuntimeError, match="loopback"):
        admin_url()
