"""New credentials require fresh mailbox proof; SQLite HTTP and real PostgreSQL."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.models import AuthSession, RegistrationChallenge, User
from app.services import account_email, registration
from tests.test_account_lifecycle import PASSWORD, signup
from tests.test_account_lifecycle import account_app as account_app

EMAIL = "otp-owner@example.com"
PASSWORD_NEW = "OnlySetAfterEmail_123!"
REAL_SEND_CODE = account_email.send_registration_code


@pytest.fixture
def otp_app(account_app, monkeypatch):
    account_app.codes = []
    monkeypatch.setattr(
        account_email,
        "send_registration_code",
        lambda email, code, challenge: account_app.codes.append((email, code, challenge)),
    )
    return account_app


def start(state, email=EMAIL, status=200):
    r = state.client.post(
        "/auth/registration/start", json={"email": email, "accepted_terms": True, "is_adult": True}
    )
    assert r.status_code == status, r.text
    return r


def verify(state, challenge=None, code=None):
    return state.client.post(
        "/auth/registration/verify",
        json={"challenge_id": challenge or state.codes[-1][2], "code": code or state.codes[-1][1]},
    )


def finish(state, grant, challenge=None, password=PASSWORD_NEW):
    return state.client.post(
        "/auth/registration/finish",
        json={
            "challenge_id": challenge or state.codes[-1][2],
            "setup_token": grant,
            "password": password,
        },
    )


def test_account_and_session_exist_only_after_email_proof_and_password(otp_app):
    s = otp_app
    r = start(s)
    assert "access_token" not in r.json()
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        row = db.get(RegistrationChallenge, UUID(r.json()["challenge_id"]))
        assert len(s.codes[-1][1]) == 6 and row.code_hash != s.codes[-1][1]
        assert row.code_hash != hashlib.sha256(s.codes[-1][1].encode()).hexdigest()
    proven = verify(s)
    assert proven.status_code == 200 and not proven.json()["already_registered"]
    grant = proven.json()["setup_token"]
    assert finish(s, "x" * 43).status_code == 400
    completed = finish(s, grant)
    assert completed.status_code == 200
    headers = {"Authorization": "Bearer " + completed.json()["access_token"]}
    me = s.client.get("/auth/me", headers=headers).json()
    assert me["email_verified"] and not me["needs_consent"]
    assert s.client.get("/profile", headers=headers).status_code == 404
    assert (
        s.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD_NEW}).status_code
        == 200
    )
    assert verify(s).status_code == 400
    assert finish(s, grant).status_code == 400


def test_cannot_finish_without_otp_or_using_code_as_setup_grant(otp_app):
    s = otp_app
    start(s)
    assert finish(s, "x" * 43).status_code == 400
    assert finish(s, s.codes[-1][1]).status_code == 422
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_five_wrong_attempts_survive_requests_and_lock_correct_code(otp_app):
    s = otp_app
    start(s)
    correct = s.codes[-1][1]
    wrong = "000000" if correct != "000000" else "000001"
    for _ in range(5):
        assert verify(s, code=wrong).status_code == 400
    assert verify(s).status_code == 400
    with Session(s.engine) as db:
        assert db.get(RegistrationChallenge, UUID(s.codes[-1][2])).attempts == 5


def test_expired_code_rejected(otp_app, monkeypatch):
    s = otp_app
    start(s)
    monkeypatch.setattr(registration, "now", lambda: datetime.now(UTC) + timedelta(minutes=11))
    assert verify(s).status_code == 400


def test_resend_cooldown_and_new_code_invalidates_previous_challenge(otp_app, monkeypatch):
    s = otp_app
    start(s)
    old = s.codes[-1]
    r = start(s, status=429)
    assert int(r.headers["retry-after"]) > 0 and len(s.codes) == 1
    later = datetime.now(UTC) + timedelta(seconds=61)
    monkeypatch.setattr(registration, "now", lambda: later)
    start(s)
    assert len(s.codes) == 2 and old[2] != s.codes[-1][2]
    assert verify(s, challenge=old[2], code=old[1]).status_code == 400
    assert verify(s).status_code == 200


def test_otp_cannot_be_used_for_another_challenge(otp_app):
    s = otp_app
    start(s)
    first = s.codes[-1]
    start(s, email="other@example.com")
    # Equal randomly generated numeric codes are allowed; the HMAC remains challenge-bound.
    if s.codes[-1][1] == first[1]:
        wrong = "999999" if first[1] != "999999" else "999998"
    else:
        wrong = first[1]
    assert verify(s, code=wrong).status_code == 400


def test_setup_grant_expiry_and_purpose(otp_app, monkeypatch):
    s = otp_app
    start(s)
    grant = verify(s).json()["setup_token"]
    assert (
        s.client.post(
            "/auth/reset-password", json={"token": grant, "new_password": PASSWORD_NEW}
        ).status_code
        == 400
    )
    monkeypatch.setattr(registration, "now", lambda: datetime.now(UTC) + timedelta(minutes=11))
    assert finish(s, grant).status_code == 400


def test_resend_invalidates_a_previously_verified_setup_grant(otp_app, monkeypatch):
    s = otp_app
    start(s)
    old = s.codes[-1]
    grant = verify(s).json()["setup_token"]
    later = datetime.now(UTC) + timedelta(seconds=61)
    monkeypatch.setattr(registration, "now", lambda: later)
    start(s)
    assert finish(s, grant, challenge=old[2]).status_code == 400


@pytest.mark.parametrize("field", ["accepted_terms", "is_adult"])
def test_otp_request_requires_adult_and_consent(otp_app, field):
    data = {"email": EMAIL, "accepted_terms": True, "is_adult": True}
    data[field] = False
    assert otp_app.client.post("/auth/registration/start", json=data).status_code == 422
    assert not otp_app.codes


@pytest.mark.parametrize(
    "code", ["12345", "1234567", "abcdef", "\uff11\uff12\uff13\uff14\uff15\uff16", "123 45"]
)
def test_malformed_codes(otp_app, code):
    s = otp_app
    start(s)
    assert verify(s, code=code).status_code == 422


def test_verified_account_signup_cannot_change_its_password(otp_app):
    s = otp_app
    headers = signup(s, email=EMAIL)
    start(s)
    result = verify(s)
    assert (
        result.status_code == 200
        and result.json()["already_registered"]
        and result.json()["setup_token"] is None
    )
    assert finish(s, "x" * 43).status_code == 400
    assert s.client.get("/auth/me", headers=headers).status_code == 200
    assert (
        s.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    )
    with Session(s.engine) as db:
        assert verify_password(
            PASSWORD, db.scalar(select(User).where(User.email == EMAIL)).password_hash
        )


def test_pending_legacy_account_can_prove_email_without_retaining_attacker_password(otp_app):
    s = otp_app
    old = signup(s, email=EMAIL, verified=False)
    start(s)
    grant = verify(s).json()["setup_token"]
    new = finish(s, grant)
    assert new.status_code == 200
    assert s.client.get("/auth/me", headers=old).status_code == 401
    assert (
        s.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    )
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_password_validation_does_not_consume_setup_grant(otp_app):
    s = otp_app
    start(s)
    grant = verify(s).json()["setup_token"]
    assert finish(s, grant, password="short").status_code == 422
    assert finish(s, grant, password="ก" * 25).status_code == 422
    assert finish(s, grant).status_code == 200


def test_delete_account_removes_its_registration_email(otp_app):
    s = otp_app
    start(s)
    grant = verify(s).json()["setup_token"]
    access = finish(s, grant).json()["access_token"]
    assert (
        s.client.request(
            "DELETE",
            "/auth/account",
            headers={"Authorization": "Bearer " + access},
            json={"password": PASSWORD_NEW},
        ).status_code
        == 204
    )
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(RegistrationChallenge)) == 0


def test_otp_message_contains_code_and_no_password_or_action_link(otp_app, monkeypatch):
    sent = []
    monkeypatch.setattr(account_email, "_send_message", lambda *args: sent.append(args))
    REAL_SEND_CODE(EMAIL, "012345", "random-challenge-id")
    _sender, _recipient, subject, body, idempotency = sent[0]
    assert "012345" in body and "10 นาที" in body and "http" not in body
    assert subject == "รหัสยืนยันอีเมล NutriLift"
    assert "012345" not in idempotency and EMAIL not in idempotency


def test_otp_failure_logs_no_code_or_recipient(otp_app, monkeypatch, caplog):
    # Alembic's fileConfig disables pre-existing application loggers in this
    # isolated migration process. Re-enable this logger for log capture only.
    monkeypatch.setattr(account_email.logger, "disabled", False)
    def fail(*args):
        raise RuntimeError(EMAIL + " secret-code-012345")

    monkeypatch.setattr(account_email, "send_registration_code", fail)
    account_email.deliver_registration_code(EMAIL, "012345", "challenge")
    assert "Registration email delivery failed" in caplog.text
    assert EMAIL not in caplog.text and "012345" not in caplog.text
