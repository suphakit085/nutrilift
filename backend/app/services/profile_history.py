"""Saved nutrition targets, effective on a Bangkok calendar date.

Past targets come only from an actual saved snapshot. The first current-day
diary read also captures a legacy profile, without inventing its earlier history.
"""

import uuid
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Profile, ProfileRevision, User
from app.services.nutrition import NutritionInputError, ProfileInput, calc_nutrition_targets

BANGKOK = timezone(timedelta(hours=7))


def utc_now() -> datetime:
    return datetime.now(UTC)


def today_bangkok() -> date:
    return utc_now().astimezone(BANGKOK).date()


def latest_revision(db: Session, user_id: uuid.UUID, for_date: date) -> ProfileRevision | None:
    return db.execute(
        select(ProfileRevision)
        .where(ProfileRevision.user_id == user_id, ProfileRevision.effective_date <= for_date)
        .order_by(
            ProfileRevision.effective_date.desc(),
            ProfileRevision.created_at.desc(),
            ProfileRevision.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def add_revision(db: Session, user_id: uuid.UUID, profile: dict, targets: dict) -> None:
    # The caller holds the user's row lock until profile + revision commit.
    now = utc_now()
    effective_date = now.astimezone(BANGKOK).date()
    previous = latest_revision(db, user_id, effective_date)
    created_at = now
    if previous is not None:
        previous_time = previous.created_at
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=UTC)
        # Equal clock ticks or different worker clocks must not make an older
        # save win. The row lock makes this ordering safe across workers.
        created_at = max(now, previous_time + timedelta(microseconds=1))
    db.add(
        ProfileRevision(
            user_id=user_id,
            effective_date=effective_date,
            profile_snapshot=profile,
            targets=targets,
            created_at=created_at,
        )
    )


def targets_for_date(db: Session, user_id: uuid.UUID, for_date: date) -> tuple:
    revision = latest_revision(db, user_id, for_date)
    if revision is not None:
        return revision.targets, "saved_profile", revision.effective_date
    if for_date < today_bangkok():
        return None, "unavailable_for_date", None

    # Serialize a legacy baseline with both other first reads and profile saves.
    # Re-read after acquiring the lock; another request may have created it.
    db.get(User, user_id, with_for_update=True)
    revision = latest_revision(db, user_id, for_date)
    if revision is not None:
        db.commit()
        return revision.targets, "saved_profile", revision.effective_date
    profile = db.get(Profile, user_id, populate_existing=True)
    if profile is None:
        db.commit()
        return None, "no_profile", None
    snapshot = {field.name: getattr(profile, field.name) for field in fields(ProfileInput)}
    snapshot["restrictions"] = list(snapshot["restrictions"] or [])
    try:
        targets = calc_nutrition_targets(ProfileInput(**snapshot))
    except NutritionInputError:
        db.rollback()
        return None, "unavailable_for_date", None
    add_revision(db, user_id, snapshot, targets)
    db.commit()
    revision = latest_revision(db, user_id, for_date)
    if revision is None:
        # A request spanning Thai midnight must not attach tomorrow's snapshot
        # to the previous day.
        return None, "unavailable_for_date", None
    return revision.targets, "saved_profile", revision.effective_date
