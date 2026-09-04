"""Registration edge cases that do not need a database.

- Emails are one account per mailbox regardless of case.
- A duplicate that races past the pre-check (unique-index violation) is a 409,
  not a 500.
- bcrypt only hashes 72 bytes; Thai is 3 bytes/char, so a 25-character Thai
  password must be rejected up front rather than silently truncated.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.auth import normalise_email, register_user
from app.api.schemas import PASSWORD_TOO_LONG, RegisterRequest
from app.db.models import User

THAI_24 = "รหัสผ่านภาษาไทยยาวมากๆนะ"  # 24 chars = 72 bytes
assert len(THAI_24) == 24 and len(THAI_24.encode()) == 72


# --- password byte limit ---------------------------------------------------


def test_72_bytes_of_thai_is_accepted():
    assert RegisterRequest(email="a@example.com", password=THAI_24).password == THAI_24


def test_73_bytes_is_rejected_with_a_thai_explanation():
    with pytest.raises(ValidationError) as excinfo:
        RegisterRequest(email="a@example.com", password=THAI_24 + "ก")
    assert PASSWORD_TOO_LONG in str(excinfo.value)


def test_long_ascii_is_rejected_too():
    """128 ASCII chars passes max_length but bcrypt would drop 56 of them."""
    with pytest.raises(ValidationError, match="72"):
        RegisterRequest(email="a@example.com", password="a" * 100)


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
    token = register_user(db, RegisterRequest(email="New.User@Example.com", password="hunter22"))
    (user,) = db.added
    assert isinstance(user, User)
    assert user.email == "new.user@example.com"
    assert user.password_hash != "hunter22"
    assert token.access_token


def test_duplicate_email_is_409_before_hashing():
    db = FakeSession(existing=User(email="taken@example.com", password_hash="x"))
    with pytest.raises(HTTPException) as excinfo:
        register_user(db, RegisterRequest(email="Taken@example.com", password="hunter22"))
    assert excinfo.value.status_code == 409
    assert db.added == []


def test_unique_violation_on_commit_is_409_after_rollback():
    """Two registrations for the same email racing past the SELECT: the unique
    index fires on commit. That must roll back and answer like the pre-check."""
    boom = IntegrityError("INSERT INTO users", {}, Exception("duplicate key"))
    db = FakeSession(commit_raises=boom)
    with pytest.raises(HTTPException) as excinfo:
        register_user(db, RegisterRequest(email="race@example.com", password="hunter22"))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "อีเมลนี้ถูกใช้สมัครแล้ว"
    assert db.rolled_back
