"""Account ownership, recovery and revocable sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import (
    DB_SESSION,
    get_current_user,
    get_verified_user,
    rate_limit_auth,
    rate_limit_login,
)
from app.api.schemas import (
    CONSENT_VERSION,
    EmailActionRequest,
    EmailChangeRequest,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordRequest,
    PasswordResetRequest,
    RegisterRequest,
    RegistrationCodeRequest,
    RegistrationFinishRequest,
    RegistrationStartRequest,
    SessionOut,
    TokenResponse,
    UserOut,
)
from app.core.config import settings
from app.core.ratelimit import Limit, RateLimitExceeded, enforce
from app.core.security import hash_password, verify_password
from app.db.models import (
    AuthSession,
    Conversation,
    FoodLogEntry,
    Message,
    Profile,
    ProfileRevision,
    RegistrationChallenge,
    User,
)
from app.services import account_email, accounts, registration

router = APIRouter(prefix="/auth", tags=["auth"])
_EMAIL_TAKEN = "อีเมลนี้ถูกใช้สมัครแล้ว"
_MAIL_MESSAGE = "หากมีบัญชีที่ตรงกับอีเมลนี้และต้องดำเนินการ คุณจะได้รับลิงก์ทางอีเมล กรุณาตรวจสอบกล่องจดหมายและสแปม"


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _email_limit(request: Request, email: str) -> None:
    rate_limit_auth(request)
    try:
        enforce(
            deps.limiter,
            f"account-mail:{email}",
            Limit(5, 3600),
            "ขอลิงก์บ่อยเกินไป กรุณารอสักครู่แล้วลองใหม่",
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            429, exc.message, headers={"Retry-After": str(exc.retry_after)}
        ) from exc


def _locked_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(401, "กรุณาเข้าสู่ระบบใหม่")
    return user


def _check_password(request: Request, user: User, password: str) -> None:
    rate_limit_auth(request)
    try:
        enforce(
            deps.limiter,
            f"account-password:{user.id}",
            Limit(10, 900),
            "ยืนยันรหัสผ่านบ่อยเกินไป กรุณารอสักครู่แล้วลองใหม่",
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            429, exc.message, headers={"Retry-After": str(exc.retry_after)}
        ) from exc
    if not verify_password(password, user.password_hash):
        raise HTTPException(400, "รหัสผ่านปัจจุบันไม่ถูกต้อง")


@router.get("/email-status")
def email_status() -> dict:
    return {"available": settings.email_delivery_configured}


@router.post("/registration/start")
def start_registration(
    payload: RegistrationStartRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = DB_SESSION,
):
    account_email.require_email_delivery()
    email = normalise_email(payload.email)
    _email_limit(request, email)
    challenge_id, code = registration.start(db, email)
    background.add_task(account_email.deliver_registration_code, email, code, str(challenge_id))
    return {
        "challenge_id": str(challenge_id),
        "expires_in": 600,
        "resend_after": 60,
        "message": "ส่งรหัสยืนยันไปยังอีเมลแล้ว กรุณาตรวจสอบกล่องจดหมายและสแปม",
    }


@router.post("/registration/verify", dependencies=[Depends(rate_limit_auth)])
def verify_registration(payload: RegistrationCodeRequest, db: Session = DB_SESSION):
    grant = registration.verify(db, payload.challenge_id, payload.code)
    return {
        "setup_token": grant,
        "already_registered": grant is None,
        "message": "บัญชีนี้มีอยู่แล้ว กรุณาเข้าสู่ระบบหรือลืมรหัสผ่าน"
        if grant is None
        else "ยืนยันอีเมลแล้ว ตั้งรหัสผ่านเพื่อสมัครให้เสร็จ",
    }


@router.post(
    "/registration/finish", response_model=TokenResponse, dependencies=[Depends(rate_limit_auth)]
)
def finish_registration(payload: RegistrationFinishRequest, db: Session = DB_SESSION):
    try:
        return TokenResponse(
            access_token=registration.finish(
                db, payload.challenge_id, payload.setup_token, payload.password
            )
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "บัญชีนี้มีอยู่แล้ว กรุณาเข้าสู่ระบบหรือลืมรหัสผ่าน") from exc


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
)
def register(
    payload: RegisterRequest, background: BackgroundTasks, db: Session = DB_SESSION
) -> TokenResponse:
    return register_user(db, payload, background)


def register_user(
    db: Session, payload: RegisterRequest, background: BackgroundTasks | None = None
) -> TokenResponse:
    account_email.require_email_delivery()
    email = normalise_email(payload.email)
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is not None:
        raise HTTPException(409, _EMAIL_TAKEN)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        consented_at=datetime.now(UTC),
        consent_version=CONSENT_VERSION,
    )
    db.add(user)
    try:
        db.flush()
        raw = accounts.new_action(db, user, "verify_email")
        access = accounts.issue_session(db, user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, _EMAIL_TAKEN) from exc
    if background is not None:
        background.add_task(account_email.deliver_action_email, email, "verify_email", raw)
    else:
        account_email.deliver_action_email(email, "verify_email", raw)
    return TokenResponse(access_token=access, email_verification_required=True)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = DB_SESSION) -> TokenResponse:
    email = normalise_email(payload.email)
    rate_limit_login(request, email)
    user = db.execute(
        select(User).where(User.email == email).with_for_update()
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    token = accounts.issue_session(db, user)
    db.commit()
    return TokenResponse(
        access_token=token, email_verification_required=user.email_verified_at is None
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: EmailRequest, request: Request, background: BackgroundTasks, db: Session = DB_SESSION
):
    account_email.require_email_delivery()
    email = normalise_email(payload.email)
    _email_limit(request, email)
    user = db.execute(
        select(User).where(User.email == email).with_for_update()
    ).scalar_one_or_none()
    if user is not None and user.email_verified_at is None:
        raw = accounts.new_action(db, user, "verify_email")
        db.commit()
        background.add_task(account_email.deliver_action_email, email, "verify_email", raw)
    return {"message": _MAIL_MESSAGE}


@router.post(
    "/verify-email", response_model=MessageResponse, dependencies=[Depends(rate_limit_auth)]
)
def verify_email(payload: PasswordResetRequest, db: Session = DB_SESSION):
    user, _ = accounts.consume_action(db, payload.token, "verify_email")
    # The mailbox owner chooses the final password, preventing pre-registration
    # by somebody else from leaving a known password or an active session behind.
    user.password_hash = hash_password(payload.new_password)
    user.email_verified_at = datetime.now(UTC)
    accounts.revoke_sessions(db, user.id)
    accounts.invalidate_actions(db, user.id)
    db.commit()
    return {"message": "ยืนยันอีเมลและตั้งรหัสผ่านแล้ว กรุณาเข้าสู่ระบบด้วยรหัสผ่านที่ตั้งในหน้านี้"}


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: EmailRequest, request: Request, background: BackgroundTasks, db: Session = DB_SESSION
):
    account_email.require_email_delivery()
    email = normalise_email(payload.email)
    _email_limit(request, email)
    user = db.execute(
        select(User).where(User.email == email).with_for_update()
    ).scalar_one_or_none()
    if user is not None:
        raw = accounts.new_action(db, user, "reset_password")
        db.commit()
        background.add_task(account_email.deliver_action_email, email, "reset_password", raw)
    return {"message": _MAIL_MESSAGE}


@router.post(
    "/reset-password", response_model=MessageResponse, dependencies=[Depends(rate_limit_auth)]
)
def reset_password(payload: PasswordResetRequest, db: Session = DB_SESSION):
    user, _ = accounts.consume_action(db, payload.token, "reset_password")
    user.password_hash = hash_password(payload.new_password)
    user.email_verified_at = datetime.now(UTC)
    accounts.revoke_sessions(db, user.id)
    accounts.invalidate_actions(db, user.id)
    db.commit()
    return {"message": "ตั้งรหัสผ่านใหม่แล้ว กรุณาเข้าสู่ระบบอีกครั้ง"}


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = DB_SESSION,
):
    user = _locked_user(db, user.id)
    _check_password(request, user, payload.password)
    user.password_hash = hash_password(payload.new_password)
    accounts.revoke_sessions(db, user.id)
    accounts.invalidate_actions(db, user.id)
    token = accounts.issue_session(db, user)
    db.commit()
    return TokenResponse(
        access_token=token, email_verification_required=user.email_verified_at is None
    )


@router.post("/change-email", response_model=MessageResponse)
def change_email(
    payload: EmailChangeRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_verified_user),
    db: Session = DB_SESSION,
):
    account_email.require_email_delivery()
    user = _locked_user(db, user.id)
    _check_password(request, user, payload.password)
    email = normalise_email(payload.email)
    if email == user.email:
        raise HTTPException(400, "กรุณาระบุอีเมลใหม่")
    _email_limit(request, email)
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is not None:
        raise HTTPException(409, _EMAIL_TAKEN)
    raw = accounts.new_action(db, user, "change_email", email=email)
    db.commit()
    background.add_task(account_email.deliver_action_email, email, "change_email", raw)
    return {"message": "ส่งลิงก์ไปยังอีเมลใหม่แล้ว อีเมลเดิมยังใช้ได้จนกว่าจะยืนยันอีเมลใหม่"}


@router.post(
    "/confirm-email", response_model=MessageResponse, dependencies=[Depends(rate_limit_auth)]
)
def confirm_email(payload: EmailActionRequest, db: Session = DB_SESSION):
    user, action = accounts.consume_action(db, payload.token, "change_email")
    user.email = action.email
    user.email_verified_at = datetime.now(UTC)
    accounts.revoke_sessions(db, user.id)
    accounts.invalidate_actions(db, user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, _EMAIL_TAKEN) from exc
    return {"message": "เปลี่ยนอีเมลแล้ว กรุณาเข้าสู่ระบบด้วยอีเมลใหม่"}


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = DB_SESSION):
    session = db.get(AuthSession, request.state.auth_session_id)
    session.revoked_at = datetime.now(UTC)
    db.commit()


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user), db: Session = DB_SESSION):
    _locked_user(db, user.id)
    accounts.revoke_sessions(db, user.id)
    db.commit()


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request, user: User = Depends(get_current_user), db: Session = DB_SESSION
):
    rows = db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
        .order_by(AuthSession.created_at.desc())
    ).scalars()
    return [
        SessionOut(
            id=row.id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            is_current=row.id == request.state.auth_session_id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = DB_SESSION
):
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "ไม่พบการเข้าสู่ระบบนี้")
    row.revoked_at = datetime.now(UTC)
    db.commit()


@router.post("/consent", response_model=UserOut)
def accept_consent(user: User = Depends(get_verified_user), db: Session = DB_SESSION):
    user.consented_at = datetime.now(UTC)
    user.consent_version = CONSENT_VERSION
    user.consent_withdrawn_at = None
    db.commit()
    db.refresh(user)
    return user


@router.post("/withdraw-consent", response_model=MessageResponse)
def withdraw_consent(
    payload: PasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = DB_SESSION,
):
    user = _locked_user(db, user.id)
    _check_password(request, user, payload.password)
    user.consent_withdrawn_at = datetime.now(UTC)
    accounts.revoke_sessions(db, user.id)
    db.commit()
    return {
        "message": (
            "ถอนความยินยอมแล้วและออกจากระบบทุกเครื่อง ข้อมูลยังเก็บอยู่จนกว่าจะขอลบบัญชี "
            "หากกลับมาใช้ต้องให้ความยินยอมใหม่"
        )
    }


@router.get("/export")
def export_account(user: User = Depends(get_verified_user), db: Session = DB_SESSION):
    def row_dict(row):
        return {column.name: getattr(row, column.key) for column in row.__table__.columns}

    profile = db.get(Profile, user.id)
    conversations = list(
        db.execute(select(Conversation).where(Conversation.user_id == user.id)).scalars()
    )
    messages = list(
        db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user.id)
        ).scalars()
    )
    entries = list(
        db.execute(select(FoodLogEntry).where(FoodLogEntry.user_id == user.id)).scalars()
    )
    revisions = list(
        db.execute(select(ProfileRevision).where(ProfileRevision.user_id == user.id)).scalars()
    )
    data = {
        "exported_at": datetime.now(UTC),
        "account": UserOut.model_validate(user).model_dump(),
        "consented_at": user.consented_at,
        "profile": row_dict(profile) if profile else None,
        "profile_history": [row_dict(row) for row in revisions],
        "conversations": [row_dict(row) for row in conversations],
        "messages": [row_dict(row) for row in messages],
        "food_log": [row_dict(row) for row in entries],
    }
    return JSONResponse(
        jsonable_encoder(data),
        headers={
            "Content-Disposition": 'attachment; filename="nutrilift-data.json"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/account", status_code=204)
def delete_account(
    payload: PasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = DB_SESSION,
):
    user = _locked_user(db, user.id)
    _check_password(request, user, payload.password)
    # Database foreign keys cascade personal data, action tokens and sessions.
    db.execute(delete(RegistrationChallenge).where(RegistrationChallenge.email == user.email))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
