"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
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
