"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

# --- auth ---------------------------------------------------------------

#: bcrypt hashes only the first 72 *bytes* of a password. A Thai character is
#: 3 bytes in UTF-8, so a 25-character Thai password would be silently
#: truncated (bcrypt < 4.1) or rejected with a 500 (>= 4.1). Refuse it up
#: front with a message that explains the byte/character difference.
PASSWORD_MAX_BYTES = 72
PASSWORD_TOO_LONG = "รหัสผ่านยาวเกินไป (ไม่เกิน 72 ไบต์ หรือประมาณ 24 ตัวอักษรไทย)"


#: Bumped whenever the wording of the consent notice changes, so a stored
#: consent can be traced back to the exact text that was agreed to.
CONSENT_VERSION = "2026-09-11"

CONSENT_REQUIRED = "ต้องยอมรับการเก็บและใช้ข้อมูลก่อนจึงจะสมัครได้"
ADULT_REQUIRED = "บริการนี้สำหรับผู้ที่มีอายุ 18 ปีขึ้นไป"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    #: Required with no default, and rejected unless true. A default of False
    #: would still reject, but a default of any kind lets a client register by
    #: simply omitting the field - which is the exact failure a consent record
    #: exists to rule out. The age gate is asserted here as well as enforced in
    #: nutrition._validate, so a minor's email is never stored in the first
    #: place rather than being turned away one screen later.
    accepted_terms: bool
    is_adult: bool

    @field_validator("password")
    @classmethod
    def _fits_in_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError(PASSWORD_TOO_LONG)
        return value

    @field_validator("accepted_terms")
    @classmethod
    def _consent_given(cls, value: bool) -> bool:
        if not value:
            raise ValueError(CONSENT_REQUIRED)
        return value

    @field_validator("is_adult")
    @classmethod
    def _is_adult(cls, value: bool) -> bool:
        if not value:
            raise ValueError(ADULT_REQUIRED)
        return value


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
    consent_version: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_consent(self) -> bool:
        """Whether this account still owes agreement to the live notice.

        A NULL (registered before consent was recorded) and a superseded
        version are the same situation to a caller: there is no agreement
        on file for the text currently in force, so it has to be asked for
        again. Collapsing both into one flag keeps that decision in one
        place instead of in every client that reads this."""
        return self.consent_version != CONSENT_VERSION


# --- profile ------------------------------------------------------------


#: Thai users think in พ.ศ.; a year above this is taken as Buddhist Era and
#: converted, so "2547" becomes 2004 instead of a 422 about the year 2100.
_BE_THRESHOLD = 2400
_BE_OFFSET = 543


class ProfileIn(BaseModel):
    sex: Literal["male", "female"]
    birth_year: int
    birth_month: int = Field(ge=1, le=12)
    height_cm: float = Field(gt=0, le=250)
    weight_kg: float = Field(gt=0, le=400)
    body_fat_pct: float | None = Field(default=None, ge=3, le=60)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    training_days: int = Field(default=3, ge=0, le=7)
    goal: Literal["cut", "bulk", "maintain"]
    restrictions: list[str] = Field(default_factory=list)


    @field_validator("birth_year", mode="before")
    @classmethod
    def _birth_year_ce(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            return value
        if value >= _BE_THRESHOLD:
            value -= _BE_OFFSET
        if not 1900 <= value <= 2100:
            raise ValueError("ปีเกิดต้องอยู่ระหว่าง ค.ศ. 1900-2100 (หรือ พ.ศ. 2443-2643)")
        return value


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)

    # Rows saved before the column existed have no month; the API still
    # requires it on write, so a client re-saving such a row must supply it.
    birth_month: int | None = Field(default=None, ge=1, le=12)
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
    """``use_rag`` used to be a field here (default True). Nothing in the UI
    ever sent False, and the evaluation harness drives ``collect_answer``
    directly, so the only thing the field did was let any client turn off
    retrieval, citations and the out-of-scope refusal (chat.py gates that on
    use_rag) by flipping one JSON key. Removed 2026-09-15; an old client that
    still sends it is ignored (pydantic's default is extra="ignore")."""

    message: str = Field(min_length=1, max_length=4000)


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


#: A diary entry may be dated at most this far past the server's UTC date.
#: Thailand is UTC+7, so a user logging breakfast at 01:00 local time is
#: already on "tomorrow" by the server clock; one day of slack covers every
#: timezone without letting someone pre-fill next week.
FOOD_LOG_MAX_DAYS_AHEAD = 1


class FoodLogEntryIn(BaseModel):
    food_id: uuid.UUID
    quantity_servings: float = Field(default=1.0, gt=0, le=50)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    logged_date: date

    @field_validator("logged_date")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        limit = datetime.now(UTC).date() + timedelta(days=FOOD_LOG_MAX_DAYS_AHEAD)
        if value > limit:
            raise ValueError("บันทึกล่วงหน้าได้ไม่เกิน 1 วัน")
        return value


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
