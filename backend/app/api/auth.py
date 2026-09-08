"""Registration and login."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_current_user, rate_limit_auth, rate_limit_login
from app.api.schemas import (
    CONSENT_VERSION,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_TAKEN = "อีเมลนี้ถูกใช้สมัครแล้ว"


def normalise_email(email: str) -> str:
    """One account per mailbox: ``Foo@Example.com`` and ``foo@example.com``
    must hit the same row, both at registration and at login."""
    return email.strip().lower()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
)
def register(payload: RegisterRequest, db: Session = DB_SESSION) -> TokenResponse:
    return register_user(db, payload)


def register_user(db: Session, payload: RegisterRequest) -> TokenResponse:
    email = normalise_email(payload.email)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN)

    # The consent is stamped in the same transaction that creates the row, so
    # an account can never exist without the record of what its owner agreed
    # to. RegisterRequest has already rejected anything but an explicit true.
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        consented_at=datetime.now(UTC),
        consent_version=CONSENT_VERSION,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two registrations for the same email raced past the SELECT above;
        # the unique index is the real guard, this just turns it into the
        # same 409 the pre-check produces instead of a 500.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN) from exc
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = DB_SESSION) -> TokenResponse:
    email = normalise_email(payload.email)
    # Needs the body's email, so it cannot be a route dependency like register.
    rate_limit_login(request, email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/consent", response_model=UserOut)
def accept_consent(user: User = Depends(get_current_user), db: Session = DB_SESSION) -> User:
    """Record agreement to the notice currently in force.

    Deliberately re-stamps instead of returning early when a consent already
    exists: someone who agreed to an older wording is agreeing again, to
    different text, and the row should say when that happened.

    Guarded by get_current_user rather than get_consented_user - a user who owes
    consent is exactly who needs to call this.
    """
    user.consented_at = datetime.now(UTC)
    user.consent_version = CONSENT_VERSION
    db.commit()
    db.refresh(user)
    return user
