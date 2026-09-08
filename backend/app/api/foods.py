"""REST food search, used by the diary UI to find a food_id to log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DB_SESSION, get_consented_user
from app.api.schemas import FoodSearchResult
from app.db.models import User
from app.services.foods import search_foods

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search", response_model=list[FoodSearchResult])
def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> list:
    return search_foods(db, q, limit)
