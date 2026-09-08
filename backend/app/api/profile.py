"""Profile CRUD and the derived nutrition targets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_consented_user, profile_to_input
from app.api.schemas import ProfileIn, ProfileOut
from app.db.models import Profile, User
from app.services.nutrition import NutritionInputError, calc_nutrition_targets

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(
    user: User = Depends(get_consented_user), db: Session = DB_SESSION
) -> Profile:
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
    profile = db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id, **payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)

    # Reject profiles the calculators cannot handle, before persisting.
    try:
        calc_nutrition_targets(profile_to_input(profile))  # type: ignore[arg-type]
    except NutritionInputError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
