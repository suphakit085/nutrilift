"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.models import Profile, User
from app.db.session import get_db
from app.services.nutrition import ProfileInput

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="ไม่ได้เข้าสู่ระบบ หรือโทเคนหมดอายุ",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _CREDENTIALS_ERROR
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise _CREDENTIALS_ERROR
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise _CREDENTIALS_ERROR from exc
    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_ERROR
    return user


def profile_to_input(profile: Profile | None) -> ProfileInput | None:
    """Convert the ORM row into the calculators' input dataclass."""
    if profile is None:
        return None
    return ProfileInput(
        sex=profile.sex,  # type: ignore[arg-type]
        birth_year=profile.birth_year,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,  # type: ignore[arg-type]
        goal=profile.goal,  # type: ignore[arg-type]
        body_fat_pct=profile.body_fat_pct,
        training_days=profile.training_days,
        restrictions=list(profile.restrictions or []),
    )
