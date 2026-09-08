"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.schemas import CONSENT_VERSION
from app.core.config import settings
from app.core.ratelimit import Limit, RateLimiter, RateLimitExceeded, enforce
from app.core.security import decode_access_token
from app.db.models import Profile, User
from app.db.session import get_db
from app.services.nutrition import ProfileInput

#: The one way routes should ask for a database session: ``db: Session = DB_SESSION``.
#:
#: ``scope="function"`` closes the session as soon as the endpoint has returned
#: and its response is serialised - *before* the response body is sent. With
#: the default request scope, FastAPI (>= 0.106) tears yield-dependencies down
#: only after the body has finished, which for the SSE chat endpoint meant a
#: session with an open transaction (``db.get`` starts one; nothing commits)
#: sat "idle in transaction" on a pooled Supabase connection for the whole
#: LLM stream. Two connections per in-flight chat, verified empirically.
#:
#: Every route must use the *same* call and scope: FastAPI keys its per-request
#: dependency cache on ``(callable, scope)``, so mixing ``Depends(get_db)`` with
#: this alias in one request silently opens a second session.
DB_SESSION = Depends(get_db, scope="function")

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
    db: Session = DB_SESSION,
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


#: Sent as a header as well as a message, so a client can react to this one
#: 403 without string-matching a Thai sentence that may be reworded.
CONSENT_REQUIRED_HEADER = "X-Consent-Required"
CONSENT_REQUIRED_DETAIL = "ต้องยินยอมให้เก็บและใช้ข้อมูลฉบับล่าสุดก่อนใช้งานต่อ"


def consent_is_current(user: User) -> bool:
    """Whether this account has agreed to the notice in force right now.

    A NULL and a superseded version are one case: there is no agreement on
    file for the current text. Accounts created before consent was recorded
    fall in here, which is the point - they were never asked.
    """
    return user.consent_version == CONSENT_VERSION


def get_consented_user(user: User = Depends(get_current_user)) -> User:
    """Authentication *and* current consent - what data routes should ask for.

    Enforced here rather than in the frontend so that consent is a property
    of the API: a client that skips the screen, or calls the endpoints
    directly, still cannot read or write personal data. /auth/me and
    /auth/consent deliberately stay on get_current_user, or a user who owes
    consent could never load the screen that collects it."""
    if not consent_is_current(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=CONSENT_REQUIRED_DETAIL,
            headers={CONSENT_REQUIRED_HEADER: "1"},
        )
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


def auth_ip_limit() -> Limit:
    return Limit(settings.rate_limit_auth_per_15min, 15 * 60)


def login_email_limit() -> Limit:
    return Limit(settings.rate_limit_login_per_email_per_15min, 15 * 60)


def auth_ip_key(request: Request) -> str:
    return f"auth:{_client_ip(request)}"


def login_email_key(email: str) -> str:
    return f"auth:email:{email.strip().lower()}"


def rate_limit_auth(request: Request) -> None:
    """Throttle register attempts per IP (route dependency).

    The per-IP limit is loose on purpose - a classroom shares one NAT during the
    SUS study - so this is a flood control, not the password-guessing guard.
    """
    limit = auth_ip_limit()
    try:
        enforce(
            limiter,
            auth_ip_key(request),
            limit,
            f"พยายามเข้าสู่ระบบบ่อยเกินไป (จำกัด {limit.describe_th()}) กรุณารอสักครู่แล้วลองใหม่",
        )
    except RateLimitExceeded as exc:
        raise _too_many(exc) from exc


def rate_limit_login(request: Request, email: str) -> None:
    """Throttle login attempts per IP *and* per email address.

    The email comes from the request body, so this runs inside the endpoint
    rather than as a route dependency. Same rule as ``rate_limit_chat``: every
    limit is checked first and only then are both counted, so a rejected
    attempt does not shorten the caller's remaining allowance.
    """
    ip_limit = auth_ip_limit()
    email_limit = login_email_limit()
    ip_message = (
        f"พยายามเข้าสู่ระบบบ่อยเกินไป (จำกัด {ip_limit.describe_th()}) กรุณารอสักครู่แล้วลองใหม่"
    )
    email_message = (
        f"พยายามเข้าสู่ระบบด้วยอีเมลนี้บ่อยเกินไป (จำกัด {email_limit.describe_th()}) "
        "กรุณารอสักครู่แล้วลองใหม่"
    )
    checks = [
        (auth_ip_key(request), ip_limit, ip_message),
        (login_email_key(email), email_limit, email_message),
    ]
    for key, limit, message in checks:
        wait = limiter.retry_after(key, limit)
        if wait is not None:
            raise _too_many(RateLimitExceeded(message, wait))
    for key, limit, _ in checks:
        limiter.hit(key, limit)


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


def rate_limit_chat(user: User = Depends(get_consented_user)) -> User:
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
        birth_month=profile.birth_month,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,  # type: ignore[arg-type]
        goal=profile.goal,  # type: ignore[arg-type]
        body_fat_pct=profile.body_fat_pct,
        training_days=profile.training_days,
        restrictions=list(profile.restrictions or []),
    )
