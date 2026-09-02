"""Pure CRUD + aggregation for the food diary.

Kept free of `app.api` imports - services never import from api in this
codebase (see chat.py/retrieval.py/guardrails.py) - so `daily_totals` stays
unit-testable without a DB, the same way nutrition.py's calculators are.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Food, FoodLogEntry, User

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


def create_entry(
    db: Session,
    user: User,
    food_id: uuid.UUID,
    quantity_servings: float,
    meal_type: str,
    logged_date: date,
) -> FoodLogEntry | None:
    """Snapshot the food's current macros onto a new entry.

    Returns None if food_id doesn't exist - the caller turns that into a 404.
    """
    food = db.get(Food, food_id)
    if food is None:
        return None
    entry = FoodLogEntry(
        user_id=user.id,
        food_id=food.id,
        food_name_th=food.name_th,
        serving_desc=food.serving_desc,
        serving_g=food.serving_g,
        serving_kcal=food.kcal,
        serving_protein_g=food.protein_g,
        serving_carb_g=food.carb_g,
        serving_fat_g=food.fat_g,
        quantity_servings=quantity_servings,
        meal_type=meal_type,
        logged_date=logged_date,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_entries(db: Session, user: User, logged_date: date) -> list[FoodLogEntry]:
    stmt = (
        select(FoodLogEntry)
        .where(FoodLogEntry.user_id == user.id, FoodLogEntry.logged_date == logged_date)
        .order_by(FoodLogEntry.created_at)
    )
    return list(db.execute(stmt).scalars())


def get_owned_entry(db: Session, user: User, entry_id: uuid.UUID) -> FoodLogEntry | None:
    entry = db.get(FoodLogEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        return None
    return entry


def daily_totals(entries: list[FoodLogEntry]) -> dict:
    """Sum kcal/macros overall and per meal_type. Pure - no DB access."""
    empty = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    totals = dict(empty)
    by_meal = {m: dict(empty) for m in MEAL_TYPES}
    for entry in entries:
        bucket = by_meal[entry.meal_type]
        for key, value in (
            ("kcal", entry.total_kcal),
            ("protein_g", entry.total_protein_g),
            ("carb_g", entry.total_carb_g),
            ("fat_g", entry.total_fat_g),
        ):
            totals[key] += value
            bucket[key] += value
    return {
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "by_meal": {m: {k: round(v, 1) for k, v in d.items()} for m, d in by_meal.items()},
    }
