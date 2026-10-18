"""Account lifecycle through HTTP and a real isolated SQL database; no external mail."""

from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import ARRAY, JSON, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import auth, chat, deps, food_log, profile
from app.api.schemas import CONSENT_VERSION
from app.core.config import settings
from app.core.ratelimit import RateLimiter
from app.core.security import create_access_token
from app.db.models import AuthActionToken, AuthSession, Base, User
from app.db.session import get_db
from app.services import account_email

PASSWORD = "OriginalPassword_123!"
NEW_PASSWORD = "ChangedPassword_456!"


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def account_app(monkeypatch, request):
    with ExitStack() as resources:
        if request.param == "postgres":
            from tests.postgres_support import migrated_database

            engine = resources.enter_context(migrated_database())
        else:
            for table in Base.metadata.tables.values():
                for column in table.columns:
                    if isinstance(column.type, (ARRAY, JSONB)):
                        monkeypatch.setattr(
                            column, "type", column.type.with_variant(JSON(), "sqlite")
                        )
            engine = create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )

            @event.listens_for(engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

            Base.metadata.create_all(engine)
            resources.callback(engine.dispose)
        with account_client(engine, monkeypatch) as state:
            yield state


@contextmanager
def account_client(engine, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_from", "")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from_email", "accounts@example.com")
    monkeypatch.setattr(deps, "limiter", RateLimiter())
    messages = []
    monkeypatch.setattr(
        account_email,
        "send_action_email",
        lambda email, purpose, token: messages.append(
            {"email": email, "purpose": purpose, "token": token}
        ),
    )
    app = FastAPI()
    for router in [auth.router, profile.router, food_log.router, chat.router]:
        app.include_router(router)

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, engine=engine, messages=messages)


def signup(state, email="owner@example.com", verified=True):
    response = state.client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "accepted_terms": True, "is_adult": True},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    if verified:
        verify = state.client.post(
            "/auth/verify-email",
            json={"token": state.messages[-1]["token"], "new_password": PASSWORD},
        )
        assert verify.status_code == 200, verify.text
        headers = {"Authorization": "Bearer " + login(state, email=email).json()["access_token"]}
    return headers


def login(state, email="owner@example.com", password=PASSWORD):
    return state.client.post("/auth/login", json={"email": email, "password": password})


def test_signup_does_not_grant_personal_data_access_before_email_ownership(account_app):
    state = account_app
    headers = signup(state, verified=False)
    assert state.client.get("/auth/me", headers=headers).json()["email_verified"] is False
    response = state.client.get("/profile", headers=headers)
    assert response.status_code == 403
    assert response.headers["X-Email-Verification-Required"] == "1"
    raw = state.messages[-1]["token"]
    with Session(state.engine) as db:
        row = db.scalar(select(AuthActionToken))
        assert row.token_hash != raw and len(row.token_hash) == 64
        assert raw not in str(state.client.get("/auth/me", headers=headers).json())
    assert (
        state.client.post(
            "/auth/verify-email", json={"token": raw, "new_password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    assert login(state).status_code == 401
    headers = {
        "Authorization": "Bearer " + login(state, password=NEW_PASSWORD).json()["access_token"]
    }
    assert state.client.get("/profile", headers=headers).status_code == 404
    assert state.client.get("/auth/me", headers=headers).json()["email_verified"] is True
    assert (
        state.client.post(
            "/auth/verify-email", json={"token": raw, "new_password": PASSWORD}
        ).status_code
        == 400
    )


def test_reissued_expired_and_wrong_purpose_links_are_rejected(account_app):
    state = account_app
    signup(state, verified=False)
    first = state.messages[-1]["token"]
    assert (
        state.client.post(
            "/auth/resend-verification", json={"email": "owner@example.com"}
        ).status_code
        == 200
    )
    second = state.messages[-1]["token"]
    assert second != first
    assert (
        state.client.post(
            "/auth/verify-email", json={"token": first, "new_password": PASSWORD}
        ).status_code
        == 400
    )
    assert (
        state.client.post(
            "/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )
    with Session(state.engine) as db:
        row = db.scalar(select(AuthActionToken).where(AuthActionToken.used_at.is_(None)))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (
        state.client.post(
            "/auth/verify-email", json={"token": second, "new_password": PASSWORD}
        ).status_code
        == 400
    )
    assert (
        state.client.post(
            "/auth/verify-email", json={"token": "x" * 43, "new_password": PASSWORD}
        ).status_code
        == 400
    )


def test_password_reset_is_generic_single_use_and_revokes_all_sessions(account_app):
    state = account_app
    first = signup(state)
    second = {"Authorization": "Bearer " + login(state).json()["access_token"]}
    unknown = state.client.post("/auth/forgot-password", json={"email": "not-a-user@example.com"})
    known = state.client.post("/auth/forgot-password", json={"email": "owner@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    token = state.messages[-1]["token"]
    result = state.client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert result.status_code == 200
    assert state.client.get("/auth/me", headers=first).status_code == 401
    assert state.client.get("/auth/me", headers=second).status_code == 401
    assert login(state).status_code == 401
    assert login(state, password=NEW_PASSWORD).status_code == 200
    assert (
        state.client.post(
            "/auth/reset-password", json={"token": token, "new_password": PASSWORD}
        ).status_code
        == 400
    )


def test_changing_password_checks_current_password_and_rotates_every_session(account_app):
    state = account_app
    old = signup(state)
    other = {"Authorization": "Bearer " + login(state).json()["access_token"]}
    bad = state.client.post(
        "/auth/change-password",
        headers=old,
        json={"password": "wrong", "new_password": NEW_PASSWORD},
    )
    assert bad.status_code == 400
    assert state.client.get("/auth/me", headers=old).status_code == 200
    changed = state.client.post(
        "/auth/change-password",
        headers=old,
        json={"password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    fresh = {"Authorization": "Bearer " + changed.json()["access_token"]}
    assert state.client.get("/auth/me", headers=fresh).status_code == 200
    for headers in [old, other]:
        assert state.client.get("/auth/me", headers=headers).status_code == 401
    assert login(state).status_code == 401
    assert login(state, password=NEW_PASSWORD).status_code == 200


def test_logout_revokes_server_side_but_does_not_end_other_sessions(account_app):
    state = account_app
    first = signup(state)
    second = {"Authorization": "Bearer " + login(state).json()["access_token"]}
    assert state.client.post("/auth/logout", headers=first).status_code == 204
    assert state.client.get("/auth/me", headers=first).status_code == 401
    assert state.client.get("/auth/me", headers=second).status_code == 200
    assert state.client.post("/auth/logout-all", headers=second).status_code == 204
    assert state.client.get("/auth/me", headers=second).status_code == 401


def test_sessions_belong_to_their_user_and_legacy_tokens_require_login(account_app):
    state = account_app
    first = signup(state)
    second = signup(state, "other@example.com")
    rows = state.client.get("/auth/sessions", headers=first).json()
    assert len(rows) == 1 and rows[0]["is_current"] is True
    assert "access_token" not in str(rows)
    assert state.client.delete("/auth/sessions/" + rows[0]["id"], headers=second).status_code == 404
    assert state.client.get("/auth/me", headers=first).status_code == 200
    uid = state.client.get("/auth/me", headers=first).json()["id"]
    legacy = {"Authorization": "Bearer " + create_access_token(uid)}
    assert state.client.get("/auth/me", headers=legacy).status_code == 401


def test_email_change_keeps_old_address_until_confirmation_then_revokes_sessions(account_app):
    state = account_app
    headers = signup(state)
    payload = {"email": "new-owner@example.com", "password": PASSWORD}
    assert (
        state.client.post(
            "/auth/change-email", headers=headers, json={**payload, "password": "bad"}
        ).status_code
        == 400
    )
    assert state.client.post("/auth/change-email", headers=headers, json=payload).status_code == 200
    assert state.client.get("/auth/me", headers=headers).json()["email"] == "owner@example.com"
    token = state.messages[-1]["token"]
    assert state.client.post("/auth/confirm-email", json={"token": token}).status_code == 200
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    assert login(state).status_code == 401
    result = login(state, email="new-owner@example.com")
    assert result.status_code == 200 and result.json()["email_verification_required"] is False
    assert state.client.post("/auth/confirm-email", json={"token": token}).status_code == 400


def test_missing_mail_delivery_fails_explicitly_without_creating_an_account(
    account_app, monkeypatch
):
    monkeypatch.setattr(settings, "smtp_host", "")
    state = account_app
    assert state.client.get("/auth/email-status").json() == {"available": False}
    response = state.client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": PASSWORD,
            "accepted_terms": True,
            "is_adult": True,
        },
    )
    assert response.status_code == 503
    with Session(state.engine) as db:
        assert db.scalar(select(User)) is None
    assert not state.messages


def test_withdrawal_preserves_evidence_and_requires_fresh_consent(account_app):
    state = account_app
    headers = signup(state)
    assert (
        state.client.post(
            "/auth/withdraw-consent", headers=headers, json={"password": PASSWORD}
        ).status_code
        == 200
    )
    assert state.client.get("/auth/me", headers=headers).status_code == 401
    headers = {"Authorization": "Bearer " + login(state).json()["access_token"]}
    me = state.client.get("/auth/me", headers=headers).json()
    assert me["needs_consent"] is True and me["consent_version"] == CONSENT_VERSION
    assert me["consent_withdrawn_at"] is not None
    assert state.client.get("/profile", headers=headers).status_code == 403
    assert state.client.post("/auth/consent", headers=headers).status_code == 200
    assert state.client.get("/auth/me", headers=headers).json()["needs_consent"] is False


def test_export_is_private_and_deletion_removes_owned_records_and_sessions(account_app):
    state = account_app
    owner = signup(state)
    other = signup(state, "other@example.com")
    first = state.client.post("/conversations", headers=owner).json()
    second = state.client.post("/conversations", headers=other).json()
    exported = state.client.get("/auth/export", headers=owner)
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    data = exported.json()
    assert data["account"]["email"] == "owner@example.com"
    assert [row["id"] for row in data["conversations"]] == [first["id"]]
    assert second["id"] not in exported.text
    assert "password_hash" not in exported.text and "token_hash" not in exported.text
    assert (
        state.client.request(
            "DELETE", "/auth/account", headers=owner, json={"password": "wrong"}
        ).status_code
        == 400
    )
    assert (
        state.client.request(
            "DELETE", "/auth/account", headers=owner, json={"password": PASSWORD}
        ).status_code
        == 204
    )
    assert state.client.get("/auth/me", headers=owner).status_code == 401
    assert state.client.get("/auth/me", headers=other).status_code == 200
    with Session(state.engine) as db:
        assert db.get(User, UUID(data["account"]["id"])) is None
        assert (
            db.scalar(select(AuthSession).where(AuthSession.user_id == UUID(data["account"]["id"])))
            is None
        )
        assert (
            db.scalar(
                select(AuthActionToken).where(
                    AuthActionToken.user_id == UUID(data["account"]["id"])
                )
            )
            is None
        )


def test_saved_targets_do_not_change_when_a_later_profile_is_saved(account_app, monkeypatch):
    from app.services import profile_history

    state = account_app
    headers = signup(state)
    payload = {
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
    monkeypatch.setattr(profile_history, "utc_now", lambda: datetime(2026, 10, 10, 5, tzinfo=UTC))
    assert state.client.put("/profile", headers=headers, json=payload).status_code == 200
    before = state.client.get("/food-log/summary?date=2026-10-10", headers=headers).json()
    monkeypatch.setattr(profile_history, "utc_now", lambda: datetime(2026, 10, 11, 5, tzinfo=UTC))
    assert (
        state.client.put("/profile", headers=headers, json={**payload, "weight_kg": 80}).status_code
        == 200
    )
    after = state.client.get("/food-log/summary?date=2026-10-10", headers=headers).json()
    current = state.client.get("/food-log/summary?date=2026-10-11", headers=headers).json()
    assert before["target"] == after["target"]
    assert current["target"] != after["target"]
    assert after["target_basis"] == "saved_profile"
    unknown = state.client.get("/food-log/summary?date=2026-10-09", headers=headers).json()
    assert unknown["target"] is None and unknown["target_basis"] == "unavailable_for_date"
    rows = state.client.get("/profile/history", headers=headers).json()
    assert [row["profile"]["weight_kg"] for row in rows] == [80, 70]
    other = signup(state, "second-owner@example.com")
    assert state.client.get("/profile/history", headers=other).json() == []


def test_login_does_not_accept_a_password_with_extra_bytes_after_bcrypt_limit(account_app):
    state = account_app
    response = state.client.post(
        "/auth/register",
        json={
            "email": "long-pass@example.com",
            "password": "x" * 72,
            "accepted_terms": True,
            "is_adult": True,
        },
    )
    assert response.status_code == 201
    assert login(state, email="long-pass@example.com", password="x" * 72).status_code == 200
    assert login(state, email="long-pass@example.com", password="x" * 72 + "y").status_code == 401


def test_current_password_checks_share_a_limit_across_sensitive_actions(account_app):
    state = account_app
    headers = signup(state)
    for _ in range(10):
        assert (
            state.client.post(
                "/auth/change-password",
                headers=headers,
                json={"password": "wrong", "new_password": NEW_PASSWORD},
            ).status_code
            == 400
        )
    response = state.client.request(
        "DELETE", "/auth/account", headers=headers, json={"password": PASSWORD}
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert state.client.get("/auth/me", headers=headers).status_code == 200
