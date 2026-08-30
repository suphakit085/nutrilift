"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ratelimit import Limit, RateLimiter, RateLimitExceeded, enforce
from app.core.security import decode_access_token
from app.db.models import Profile, User
from app.db.session import get_db
from app.services.nutrition import ProfileInput

bearer_scheme = HTTPBearer(auto_error=False)

#: One process-wide limiter. See app/core/ratelimit.py for what that implies.
limiter = RateLimiter()

GLOBAL_CHAT_KEY = "chat:all-users"

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


def _client_ip(request: Request) -> str:
    """Best-effort client address.

    Behind a proxy (Render, Vercel, Cloudflare Tunnel) the socket address is the
    proxy's, so the first hop in X-Forwarded-For is used when present. That
    header is client-controllable, which is acceptable here: it gates login
    attempts, not authorisation, and the per-user chat limits do not rely on it.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=exc.message,
        headers={"Retry-After": str(exc.retry_after)},
    )


def rate_limit_auth(request: Request) -> None:
    """Throttle login/register attempts per IP."""
    limit = Limit(settings.rate_limit_auth_per_15min, 15 * 60)
    try:
        enforce(
            limiter,
            f"auth:{_client_ip(request)}",
            limit,
            f"พยายามเข้าสู่ระบบบ่อยเกินไป (จำกัด {limit.describe_th()}) กรุณารอสักครู่แล้วลองใหม่",
        )
    except RateLimitExceeded as exc:
        raise _too_many(exc) from exc


def chat_limits(user_id) -> list[tuple[str, Limit]]:
    """Per-user chat limits as (key, limit) pairs.

    Each window needs its own key: the limiter prunes a key's history using the
    window it is given, so sharing one key between the hourly and daily limits
    would record two events per turn and halve both allowances.
    """
    return [
        (f"chat:hour:{user_id}", Limit(settings.rate_limit_chat_per_hour, 3600)),
        (f"chat:day:{user_id}", Limit(settings.rate_limit_chat_per_day, 24 * 3600)),
    ]


def global_chat_limit() -> Limit:
    return Limit(settings.rate_limit_chat_global_per_day, 24 * 3600)


def rate_limit_chat(user: User = Depends(get_current_user)) -> User:
    """Throttle chat turns per user, and cap total spend across all users.

    The global cap is checked first so one heavy user cannot exhaust it and
    leave everyone else with a confusing per-user message.
    """
    if limiter.retry_after(GLOBAL_CHAT_KEY, global_chat_limit()) is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ระบบใช้งานครบโควตาประจำวันแล้ว (เป็นการจำกัดค่าใช้จ่ายของโปรเจก) "
                "กรุณาลองใหม่ในวันถัดไป"
            ),
        )

    pairs = chat_limits(user.id)
    for key, limit in pairs:
        wait = limiter.retry_after(key, limit)
        if wait is not None:
            raise _too_many(
                RateLimitExceeded(
                    f"คุณถามบ่อยเกินไป (จำกัด {limit.describe_th()}) กรุณารอสักครู่แล้วลองใหม่",
                    wait,
                )
            )

    # Count the turn only once every limit has passed, so a rejected request
    # does not eat into the caller's remaining allowance.
    for key, limit in pairs:
        limiter.hit(key, limit)
    limiter.hit(GLOBAL_CHAT_KEY, global_chat_limit())
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
