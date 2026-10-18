"""Email proof precedes credentials. No bearer session exists before completion."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.api.schemas import CONSENT_VERSION
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import RegistrationChallenge, User
from app.services import accounts

INVALID_CODE = "รหัสยืนยันไม่ถูกต้อง หมดอายุ หรือถูกใช้แล้ว กรุณาขอรหัสใหม่"
INVALID_SETUP = "สิทธิ์ตั้งรหัสผ่านหมดอายุหรือถูกใช้แล้ว กรุณายืนยันอีเมลใหม่"


def now():
    return datetime.now(UTC)


def code_digest(challenge_id, code):
    # A plain hash of six digits is trivial to brute-force after a DB leak.
    return hmac.new(
        settings.jwt_secret.encode(),
        f"registration:{challenge_id}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def start(db: Session, email: str):
    # Opportunistic retention cleanup; never retain expired signup PII indefinitely
    # while the signup service is in use. No passwords are stored here.
    db.execute(
        delete(RegistrationChallenge).where(
            RegistrationChallenge.expires_at < now() - timedelta(days=1)
        )
    )
    if db.bind.dialect.name == "postgresql":
        # Serialize issuance across workers, including the first request for an email.
        lock = int.from_bytes(hashlib.sha256(email.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    previous = db.execute(
        select(RegistrationChallenge)
        .where(RegistrationChallenge.email == email)
        .order_by(RegistrationChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    timestamp = now()
    if previous and accounts.utc(previous.created_at) + timedelta(seconds=60) > timestamp:
        retry = max(
            1,
            int(
                (
                    accounts.utc(previous.created_at) + timedelta(seconds=60) - timestamp
                ).total_seconds()
            )
            + 1,
        )
        raise HTTPException(429, "กรุณารอ 60 วินาทีก่อนขอรหัสใหม่", headers={"Retry-After": str(retry)})
    # Only the latest challenge remains usable, including its setup grant.
    for row in db.execute(
        select(RegistrationChallenge).where(
            RegistrationChallenge.email == email, RegistrationChallenge.used_at.is_(None)
        )
    ).scalars():
        row.used_at = timestamp
    code = f"{secrets.randbelow(1_000_000):06d}"
    row = RegistrationChallenge(
        id=uuid.uuid4(),
        email=email,
        created_at=timestamp,
        expires_at=timestamp + timedelta(minutes=10),
        attempts=0,
        consent_version=CONSENT_VERSION,
    )
    row.code_hash = code_digest(row.id, code)
    db.add(row)
    db.commit()
    return row.id, code


def verify(db: Session, challenge_id: uuid.UUID, code: str):
    row = db.execute(
        select(RegistrationChallenge)
        .where(RegistrationChallenge.id == challenge_id)
        .with_for_update()
    ).scalar_one_or_none()
    timestamp = now()
    if (
        row is None
        or row.used_at
        or row.verified_at
        or row.attempts >= 5
        or accounts.utc(row.expires_at) <= timestamp
    ):
        raise HTTPException(400, INVALID_CODE)
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, code_digest(row.id, code)):
        db.commit()  # Attempts must survive the HTTP error/transaction rollback.
        raise HTTPException(400, INVALID_CODE)
    row.verified_at = timestamp
    row.code_hash = ""  # No OTP remains usable after email proof.
    user = db.execute(select(User).where(User.email == row.email)).scalar_one_or_none()
    if user is not None and user.email_verified_at is not None:
        row.used_at = timestamp
        db.commit()
        return None
    raw = secrets.token_urlsafe(32)
    row.setup_token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row.setup_expires_at = timestamp + timedelta(minutes=10)
    db.commit()
    return raw


def finish(db: Session, challenge_id: uuid.UUID, raw: str, password: str):
    candidate = db.get(RegistrationChallenge, challenge_id)
    if candidate is None:
        raise HTTPException(400, INVALID_SETUP)
    user = db.execute(
        select(User).where(User.email == candidate.email).with_for_update()
    ).scalar_one_or_none()
    row = db.execute(
        select(RegistrationChallenge)
        .where(RegistrationChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    timestamp = now()
    if (
        row.used_at
        or row.verified_at is None
        or row.setup_token_hash is None
        or row.setup_expires_at is None
        or accounts.utc(row.setup_expires_at) <= timestamp
        or row.consent_version != CONSENT_VERSION
        or not hmac.compare_digest(row.setup_token_hash, hashlib.sha256(raw.encode()).hexdigest())
    ):
        raise HTTPException(400, INVALID_SETUP)
    if user is not None and user.email_verified_at is not None:
        raise HTTPException(409, "บัญชีนี้ยืนยันแล้ว กรุณาเข้าสู่ระบบหรือลืมรหัสผ่าน")
    if user is None:
        user = User(email=row.email, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    else:
        user.password_hash = hash_password(password)
        accounts.revoke_sessions(db, user.id)
        accounts.invalidate_actions(db, user.id)
    user.email_verified_at = timestamp
    user.consented_at = row.created_at
    user.consent_version = row.consent_version
    user.consent_withdrawn_at = None
    row.used_at = timestamp
    row.setup_token_hash = None
    access = accounts.issue_session(db, user)
    db.commit()
    return access
