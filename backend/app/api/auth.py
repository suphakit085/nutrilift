"""Registration and login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_current_user, rate_limit_auth, rate_limit_login
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
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

    user = User(email=email, password_hash=hash_password(payload.password))
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
