"""Profile CRUD and the derived nutrition targets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_consented_user, profile_to_input
from app.api.schemas import ProfileIn, ProfileOut
from app.db.models import Profile, ProfileRevision, User
from app.services import profile_history
from app.services.nutrition import NutritionInputError, calc_nutrition_targets

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(get_consented_user), db: Session = DB_SESSION) -> Profile:
    profile = db.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ยังไม่ได้กรอกโปรไฟล์")
    return profile


@router.put("", response_model=ProfileOut)
def upsert_profile(
    payload: ProfileIn,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> Profile:
    db.get(User, user.id, with_for_update=True)
    profile = db.get(Profile, user.id, populate_existing=True)
    if profile is None:
        profile = Profile(user_id=user.id, **payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)

    # Reject profiles the calculators cannot handle, before persisting.
    try:
        targets = calc_nutrition_targets(profile_to_input(profile))  # type: ignore[arg-type]
    except NutritionInputError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    profile_history.add_revision(db, user.id, payload.model_dump(), targets)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/targets")
def get_targets(user: User = Depends(get_consented_user), db: Session = DB_SESSION) -> dict:
    """BMR / TDEE / macro targets computed from the stored profile."""
    profile = db.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ยังไม่ได้กรอกโปรไฟล์")
    try:
        return calc_nutrition_targets(profile_to_input(profile))  # type: ignore[arg-type]
    except NutritionInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/history")
def history(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> list[dict]:
    rows = db.execute(
        select(ProfileRevision)
        .where(ProfileRevision.user_id == user.id)
        .order_by(ProfileRevision.created_at.desc(), ProfileRevision.id.desc())
        .limit(limit)
    ).scalars()
    return [
        {
            "id": str(row.id),
            "effective_date": row.effective_date.isoformat(),
            "created_at": row.created_at,
            "profile": row.profile_snapshot,
            "targets": row.targets,
        }
        for row in rows
    ]
