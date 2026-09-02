"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- auth ---------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


# --- profile ------------------------------------------------------------


class ProfileIn(BaseModel):
    sex: Literal["male", "female"]
    birth_year: int = Field(ge=1900, le=2100)
    height_cm: float = Field(gt=0, le=250)
    weight_kg: float = Field(gt=0, le=400)
    body_fat_pct: float | None = Field(default=None, ge=3, le=60)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    training_days: int = Field(default=3, ge=0, le=7)
    goal: Literal["cut", "bulk", "maintain"]
    restrictions: list[str] = Field(default_factory=list)


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


class TargetsOut(BaseModel):
    """Whatever calc_nutrition_targets returns, passed through untouched."""

    model_config = ConfigDict(extra="allow")


# --- conversations / chat ----------------------------------------------


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    citations: list | None = None
    tool_calls: list | None = None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    use_rag: bool = True


# --- food log -------------------------------------------------------------


class FoodSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_th: str
    name_en: str | None
    category: str | None
    serving_desc: str
    serving_g: float
    kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float | None


class FoodLogEntryIn(BaseModel):
    food_id: uuid.UUID
    quantity_servings: float = Field(default=1.0, gt=0, le=50)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    logged_date: date


class FoodLogEntryUpdate(BaseModel):
    quantity_servings: float | None = Field(default=None, gt=0, le=50)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None


class FoodLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_id: uuid.UUID | None
    food_name_th: str
    serving_desc: str
    serving_g: float
    serving_kcal: float
    serving_protein_g: float
    serving_carb_g: float
    serving_fat_g: float
    quantity_servings: float
    meal_type: str
    logged_date: date
    total_kcal: float
    total_protein_g: float
    total_carb_g: float
    total_fat_g: float
    created_at: datetime


class DailySummaryOut(BaseModel):
    """Whatever the /food-log/summary route builds, passed through untouched -
    same trick as TargetsOut."""

    model_config = ConfigDict(extra="allow")
