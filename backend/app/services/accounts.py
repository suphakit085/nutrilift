"""Revocable sessions and single-use account actions; transactions belong to callers."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import AuthActionToken, AuthSession, User

INVALID_LINK = "ลิงก์ไม่ถูกต้อง หมดอายุ หรือถูกใช้แล้ว กรุณาขอลิงก์ใหม่"


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def issue_session(db: Session, user: User) -> str:
    now = datetime.now(UTC)
    session = AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.access_token_expire_minutes),
    )
    db.add(session)
    return create_access_token(str(user.id), session_id=str(session.id))


def revoke_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def invalidate_actions(db: Session, user_id: uuid.UUID, purpose: str | None = None) -> None:
    statement = update(AuthActionToken).where(
        AuthActionToken.user_id == user_id, AuthActionToken.used_at.is_(None)
    )
    if purpose:
        statement = statement.where(AuthActionToken.purpose == purpose)
    db.execute(statement.values(used_at=datetime.now(UTC)))


def new_action(db: Session, user: User, purpose: str, *, email: str | None = None) -> str:
    invalidate_actions(db, user.id, purpose)
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    minutes = (
        settings.password_reset_expire_minutes
        if purpose == "reset_password"
        else settings.email_verification_expire_minutes
    )
    db.add(
        AuthActionToken(
            id=uuid.uuid4(),
            user_id=user.id,
            purpose=purpose,
            email=email or user.email,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            created_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
    )
    return raw


def consume_action(db: Session, raw: str, purpose: str) -> tuple[User, AuthActionToken]:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    candidate = db.execute(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == digest, AuthActionToken.purpose == purpose
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(400, INVALID_LINK)
    # Uniform lock order (user -> action) also serializes password changes and link issuance.
    user = db.execute(
        select(User).where(User.id == candidate.user_id).with_for_update()
    ).scalar_one_or_none()
    action = db.execute(
        select(AuthActionToken)
        .where(AuthActionToken.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if (
        user is None
        or action is None
        or action.used_at is not None
        or utc(action.expires_at) <= datetime.now(UTC)
    ):
        raise HTTPException(400, INVALID_LINK)
    if purpose != "change_email" and action.email != user.email:
        raise HTTPException(400, INVALID_LINK)
    action.used_at = datetime.now(UTC)
    return user, action
