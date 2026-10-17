"""Food diary CRUD: search results turn into logged entries grouped by day/meal."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_consented_user
from app.api.schemas import DailySummaryOut, FoodLogEntryIn, FoodLogEntryOut, FoodLogEntryUpdate
from app.db.models import User
from app.services import food_log, profile_history

router = APIRouter(prefix="/food-log", tags=["food-log"])


@router.post("", response_model=FoodLogEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: FoodLogEntryIn,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
):
    entry = food_log.create_entry(
        db,
        user,
        payload.food_id,
        payload.quantity_servings,
        payload.meal_type,
        payload.logged_date,
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเมนูอาหารนี้")
    return entry


@router.get("", response_model=list[FoodLogEntryOut])
def list_entries(
    date_: date = Query(alias="date"),
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
):
    return food_log.list_entries(db, user, date_)


@router.get("/summary", response_model=DailySummaryOut)
def summary(
    date_: date = Query(alias="date"),
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
):
    entries = food_log.list_entries(db, user, date_)
    agg = food_log.daily_totals(entries)

    target = None
    targets, basis, effective_date = profile_history.targets_for_date(db, user.id, date_)
    if targets is not None:
        target = {
            "kcal": targets["energy_target_kcal"],
            "protein_g": targets["macros"]["protein_g"],
            "carb_g": targets["macros"]["carb_g"],
            "fat_g": targets["macros"]["fat_g"],
        }

    remaining = (
        {k: round(target[k] - agg["totals"][k], 1) for k in target} if target else None
    )

    return {
        "date": date_.isoformat(),
        "entries_count": len(entries),
        "consumed": agg["totals"],
        "target": target,
        "target_basis": basis,
        "target_effective_date": effective_date.isoformat() if effective_date else None,
        "remaining": remaining,
        "by_meal": agg["by_meal"],
    }


@router.patch("/{entry_id}", response_model=FoodLogEntryOut)
def update_entry(
    entry_id: uuid.UUID,
    payload: FoodLogEntryUpdate,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
):
    entry = food_log.get_owned_entry(db, user, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการนี้")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(entry, key, value)
    if changes:
        db.commit()
        db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> None:
    entry = food_log.get_owned_entry(db, user, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการนี้")
    db.delete(entry)
    db.commit()
