"""SQLAlchemy ORM models.

Mirrors the data model in docs/architecture.md:
users, profiles, conversations, messages, documents, chunks, foods.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    food_log_entries: Mapped[list[FoodLogEntry]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base):
    """One row per user. Feeds the deterministic nutrition calculators."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    sex: Mapped[str] = mapped_column(String(10), nullable=False)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False)
    training_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    goal: Mapped[str] = mapped_column(String(20), nullable=False)
    restrictions: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="profile")

    __table_args__ = (
        CheckConstraint("sex IN ('male','female')", name="ck_profiles_sex"),
        CheckConstraint("goal IN ('cut','bulk','maintain')", name="ck_profiles_goal"),
        CheckConstraint("height_cm > 0 AND weight_kg > 0", name="ck_profiles_positive"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="แชตใหม่")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    safety_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Document(Base):
    """A knowledge card (or other source doc) that chunks are derived from."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="knowledge_card")
    source_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    lang: Mapped[str] = mapped_column(String(10), default="th")
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embed_dim), nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Food(Base):
    """Thai food nutrition table - the source of truth for lookup_food()."""

    __tablename__ = "foods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name_th: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serving_desc: Mapped[str] = mapped_column(String(100), nullable=False)
    serving_g: Mapped[float] = mapped_column(Float, nullable=False)
    kcal: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carb_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FoodLogEntry(Base):
    """One row per food item a user adds to a given day's diary.

    Macros are snapshotted from `foods` at creation time rather than joined
    live. This is required, not just defensive: `python -m ingest --only
    foods` runs `DELETE FROM foods` and re-inserts every row with a fresh
    UUID (see ingest/__main__.py::ingest_foods) - a live join would make every
    already-logged day's totals shift, or 404, the next time the food table
    is regenerated. `food_id` is kept only as an optional provenance link.
    """

    __tablename__ = "food_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    food_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("foods.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Snapshot of the food row at the moment it was logged (see docstring above).
    food_name_th: Mapped[str] = mapped_column(String(200), nullable=False)
    serving_desc: Mapped[str] = mapped_column(String(100), nullable=False)
    serving_g: Mapped[float] = mapped_column(Float, nullable=False)
    serving_kcal: Mapped[float] = mapped_column(Float, nullable=False)
    serving_protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    serving_carb_g: Mapped[float] = mapped_column(Float, nullable=False)
    serving_fat_g: Mapped[float] = mapped_column(Float, nullable=False)

    quantity_servings: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    logged_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="food_log_entries")

    __table_args__ = (
        CheckConstraint("quantity_servings > 0", name="ck_food_log_entries_quantity_positive"),
        CheckConstraint(
            "meal_type IN ('breakfast','lunch','dinner','snack')",
            name="ck_food_log_entries_meal_type",
        ),
        Index("ix_food_log_entries_user_date", "user_id", "logged_date"),
    )

    @property
    def total_kcal(self) -> float:
        return round(self.serving_kcal * self.quantity_servings, 1)

    @property
    def total_protein_g(self) -> float:
        return round(self.serving_protein_g * self.quantity_servings, 1)

    @property
    def total_carb_g(self) -> float:
        return round(self.serving_carb_g * self.quantity_servings, 1)

    @property
    def total_fat_g(self) -> float:
        return round(self.serving_fat_g * self.quantity_servings, 1)
