"""Registration edge cases that do not need a database.

- Emails are one account per mailbox regardless of case.
- A duplicate that races past the pre-check (unique-index violation) is a 409,
  not a 500.
- bcrypt only hashes 72 bytes; Thai is 3 bytes/char, so a 25-character Thai
  password must be rejected up front rather than silently truncated.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.auth import normalise_email, register_user
from app.api.deps import (
    CONSENT_REQUIRED_HEADER,
    consent_is_current,
    get_consented_user,
)
from app.api.schemas import (
    ADULT_REQUIRED,
    CONSENT_REQUIRED,
    CONSENT_VERSION,
    PASSWORD_TOO_LONG,
    RegisterRequest,
    UserOut,
)
from app.db.models import User

THAI_24 = "รหัสผ่านภาษาไทยยาวมากๆนะ"  # 24 chars = 72 bytes
assert len(THAI_24) == 24 and len(THAI_24.encode()) == 72


def valid(**overrides):
    """A registration payload that differs from a good one only where stated."""
    return RegisterRequest(
        **{
            "email": "a@example.com",
            "password": "hunter22",
            "accepted_terms": True,
            "is_adult": True,
            **overrides,
        }
    )


# --- password byte limit ---------------------------------------------------


def test_72_bytes_of_thai_is_accepted():
    assert valid(password=THAI_24).password == THAI_24


def test_73_bytes_is_rejected_with_a_thai_explanation():
    with pytest.raises(ValidationError) as excinfo:
        valid(password=THAI_24 + "ก")
    assert PASSWORD_TOO_LONG in str(excinfo.value)


def test_long_ascii_is_rejected_too():
    """128 ASCII chars passes max_length but bcrypt would drop 56 of them."""
    with pytest.raises(ValidationError, match="72"):
        valid(password="a" * 100)


# --- email normalisation -----------------------------------------------------


@pytest.mark.parametrize("raw", ["Foo@Example.COM", "  foo@example.com ", "FOO@example.com"])
def test_emails_are_lowercased_and_stripped(raw):
    assert normalise_email(raw) == "foo@example.com"


# --- register_user against a fake session -------------------------------------


class Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeSession:
    def __init__(self, *, existing=None, commit_raises: Exception | None = None) -> None:
        self.existing = existing
        self.commit_raises = commit_raises
        self.added: list = []
        self.rolled_back = False
        self.committed = False

    def execute(self, statement):
        return Result(self.existing)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if self.commit_raises is not None:
            raise self.commit_raises
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        obj.id = obj.id or __import__("uuid").uuid4()


def test_register_stores_the_lowercased_email():
    db = FakeSession()
    token = register_user(db, valid(email="New.User@Example.com"))
    (user,) = db.added
    assert isinstance(user, User)
    assert user.email == "new.user@example.com"
    assert user.password_hash != "hunter22"
    assert token.access_token


def test_duplicate_email_is_409_before_hashing():
    db = FakeSession(existing=User(email="taken@example.com", password_hash="x"))
    with pytest.raises(HTTPException) as excinfo:
        register_user(db, valid(email="Taken@example.com"))
    assert excinfo.value.status_code == 409
    assert db.added == []


def test_unique_violation_on_commit_is_409_after_rollback():
    """Two registrations for the same email racing past the SELECT: the unique
    index fires on commit. That must roll back and answer like the pre-check."""
    boom = IntegrityError("INSERT INTO users", {}, Exception("duplicate key"))
    db = FakeSession(commit_raises=boom)
    with pytest.raises(HTTPException) as excinfo:
        register_user(db, valid(email="race@example.com"))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "อีเมลนี้ถูกใช้สมัครแล้ว"
    assert db.rolled_back


# --- consent and age gate -----------------------------------------------------


def test_consent_must_be_explicit():
    """Omitting the field entirely is the case a default would have allowed."""
    with pytest.raises(ValidationError, match="accepted_terms"):
        RegisterRequest(email="a@example.com", password="hunter22", is_adult=True)


def test_consent_false_is_rejected_with_a_thai_explanation():
    with pytest.raises(ValidationError) as excinfo:
        valid(accepted_terms=False)
    assert CONSENT_REQUIRED in str(excinfo.value)


def test_age_must_be_asserted():
    with pytest.raises(ValidationError, match="is_adult"):
        RegisterRequest(email="a@example.com", password="hunter22", accepted_terms=True)


def test_age_false_is_rejected_with_a_thai_explanation():
    with pytest.raises(ValidationError) as excinfo:
        valid(is_adult=False)
    assert ADULT_REQUIRED in str(excinfo.value)


def test_registering_stamps_the_consent_on_the_row():
    """The account and the evidence for it are created together or not at all."""
    db = FakeSession()
    register_user(db, valid(email="consent@example.com"))
    saved = db.added[0]
    assert saved.consent_version == CONSENT_VERSION
    assert saved.consented_at is not None
    assert saved.consented_at.tzinfo is not None


# --- the gate for accounts that never consented -------------------------------


class _Row:
    """Minimal stand-in for a User row; only the consent fields matter here."""

    def __init__(self, version):
        self.consent_version = version


def test_account_with_no_consent_record_is_not_current():
    """Rows created before consent existed carry NULL - they were never asked."""
    assert consent_is_current(_Row(None)) is False


def test_account_on_an_older_notice_is_not_current():
    assert consent_is_current(_Row("1999-01-01")) is False


def test_account_on_the_live_notice_is_current():
    assert consent_is_current(_Row(CONSENT_VERSION)) is True


def test_gate_refuses_and_flags_itself_in_a_header():
    """403 plus a header, so the client need not match a Thai sentence."""
    with pytest.raises(HTTPException) as excinfo:
        get_consented_user(_Row(None))
    assert excinfo.value.status_code == 403
    assert excinfo.value.headers == {CONSENT_REQUIRED_HEADER: "1"}


def test_gate_passes_a_consented_user_straight_through():
    row = _Row(CONSENT_VERSION)
    assert get_consented_user(row) is row


def test_userout_reports_whether_consent_is_owed():
    """/auth/me is how the client learns it must show the screen."""
    common = {"id": uuid.uuid4(), "email": "a@example.com", "created_at": datetime.now(UTC)}
    assert UserOut(**common, consent_version=None).needs_consent is True
    assert UserOut(**common, consent_version="1999-01-01").needs_consent is True
    assert UserOut(**common, consent_version=CONSENT_VERSION).needs_consent is False
