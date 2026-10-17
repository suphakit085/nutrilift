"""Historical targets through real HTTP handlers and migrated PostgreSQL."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event
from types import SimpleNamespace

import pytest
from alembic import command
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api import food_log, profile
from app.api.deps import get_consented_user
from app.api.schemas import CONSENT_VERSION
from app.db.models import FoodLogEntry, Profile, ProfileRevision, User
from app.db.session import get_db
from app.services import profile_history
from tests.postgres_support import migrate, migrated_database, migration_config

pytestmark = pytest.mark.postgres
DAY1 = date(2026, 10, 14)
DAY2 = date(2026, 10, 15)
DAY3 = date(2026, 10, 16)
PAYLOAD = {
    "sex": "male",
    "birth_year": 1995,
    "birth_month": 1,
    "height_cm": 175,
    "weight_kg": 70,
    "body_fat_pct": None,
    "activity_level": "moderate",
    "training_days": 3,
    "goal": "maintain",
    "restrictions": [],
}


@pytest.fixture
def state(monkeypatch):
    with migrated_database() as engine:
        owner, other = uuid.uuid4(), uuid.uuid4()
        with Session(engine) as db:
            db.add_all(
                [
                    User(
                        id=identifier,
                        email=str(identifier) + "@example.com",
                        password_hash="unused-history-fixture",
                        consented_at=datetime.now(UTC),
                        consent_version=CONSENT_VERSION,
                    )
                    for identifier in [owner, other]
                ]
            )
            db.commit()
        app = FastAPI()
        app.include_router(profile.router)
        app.include_router(food_log.router)

        def database():
            with Session(engine) as db:
                yield db

        def authenticated(x_test_user: uuid.UUID = Header(), db: Session = Depends(get_db)):
            return db.get(User, x_test_user)

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_consented_user] = authenticated
        with TestClient(app) as client:
            value = SimpleNamespace(
                engine=engine,
                client=client,
                owner=owner,
                other=other,
                headers={"x-test-user": str(owner)},
            )
            monkeypatch.setattr(
                profile_history, "utc_now", lambda: datetime(2026, 10, 14, 5, tzinfo=UTC)
            )
            yield value


def day(monkeypatch, day, hour=5):
    monkeypatch.setattr(
        profile_history,
        "utc_now",
        lambda: datetime.combine(day, datetime.min.time(), UTC).replace(hour=hour),
    )


def summary(state, day, headers=None):
    response = state.client.get(
        "/food-log/summary", params={"date": day.isoformat()}, headers=headers or state.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def save(state, **changes):
    response = state.client.put("/profile", json={**PAYLOAD, **changes}, headers=state.headers)
    assert response.status_code == 200, response.text
    return response.json()


def history(state, headers=None):
    response = state.client.get("/profile/history", headers=headers or state.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_migration_matches_orm(state):
    with migration_config(state.engine) as config:
        command.check(config)


def test_upgrade_preserves_legacy_profile_without_inventing_past(monkeypatch):
    identifier = uuid.uuid4()
    with migrated_database("e43c6103b001") as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id,email,password_hash,created_at) "
                    "VALUES (:id,:email,:hash,:now)"
                ),
                {
                    "id": identifier,
                    "email": "legacy-history@example.com",
                    "hash": "unchanged-hash",
                    "now": datetime.now(UTC),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO profiles (user_id,sex,birth_year,birth_month,height_cm,"
                    "weight_kg,activity_level,training_days,goal,restrictions,updated_at) "
                    "VALUES (:id,'male',1995,1,175,70,'moderate',3,'maintain','{}',:now)"
                ),
                {"id": identifier, "now": datetime.now(UTC)},
            )
        migrate(engine)
        with Session(engine) as db:
            assert db.get(User, identifier).password_hash == "unchanged-hash"
            assert db.get(Profile, identifier).weight_kg == 70
            assert db.scalar(select(func.count()).select_from(ProfileRevision)) == 0
        migrate(engine, "e43c6103b001", downgrade=True)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT weight_kg FROM profiles")) == 70
        migrate(engine)


def test_changes_today_leave_yesterday_and_gap_dates_unchanged(state, monkeypatch):
    save(state)
    original = summary(state, DAY1)
    day(monkeypatch, DAY3)
    save(state, weight_kg=85, goal="bulk")
    assert summary(state, DAY1)["target"] == original["target"]
    assert summary(state, DAY2)["target"] == original["target"]
    current = summary(state, DAY3)
    assert current["target"] != original["target"]
    assert original["target_effective_date"] == DAY1.isoformat()
    assert current["target_effective_date"] == DAY3.isoformat()
    assert current["target_basis"] == "saved_profile"


def test_no_snapshot_means_no_past_target_even_with_existing_food(state):
    yesterday = date(2026, 10, 13)
    with Session(state.engine) as db:
        db.add(
            FoodLogEntry(
                user_id=state.owner,
                food_id=None,
                food_name_th="History fixture",
                serving_desc="100 g",
                serving_g=100,
                serving_kcal=155,
                serving_protein_g=3,
                serving_carb_g=35,
                serving_fat_g=1,
                quantity_servings=2,
                meal_type="breakfast",
                logged_date=yesterday,
            )
        )
        db.commit()
    save(state)
    result = summary(state, yesterday)
    assert result["target"] is None and result["remaining"] is None
    assert result["target_basis"] == "unavailable_for_date"
    assert result["entries_count"] == 1 and result["consumed"]["kcal"] == 310
    assert len(history(state)) == 1


def test_multiple_saves_same_day_use_last_save_and_keep_earlier_days(state, monkeypatch):
    save(state)
    original = summary(state, DAY1)["target"]
    day(monkeypatch, DAY2)
    save(state, weight_kg=75)
    day(monkeypatch, DAY2, hour=6)
    save(state, weight_kg=90, goal="bulk")
    latest = state.client.get("/profile/targets", headers=state.headers).json()
    assert summary(state, DAY2)["target"]["kcal"] == latest["energy_target_kcal"]
    assert summary(state, DAY1)["target"] == original
    assert len(history(state)) == 3


def test_first_current_read_captures_legacy_profile_without_fabricated_backfill(state, monkeypatch):
    with Session(state.engine) as db:
        db.add(Profile(user_id=state.owner, **PAYLOAD))
        db.commit()
    assert summary(state, date(2026, 10, 13))["target"] is None
    assert history(state) == []
    original = summary(state, DAY1)["target"]
    assert original is not None and len(history(state)) == 1
    assert summary(state, DAY1)["target"] == original and len(history(state)) == 1
    day(monkeypatch, DAY2)
    save(state, weight_kg=90, goal="bulk")
    assert summary(state, DAY1)["target"] == original


def test_no_profile_today_requests_profile_setup(state):
    current = summary(state, DAY1)
    assert current["target"] is None and current["target_basis"] == "no_profile"
    assert history(state) == []


def test_invalid_legacy_profile_does_not_create_a_target(state):
    with Session(state.engine) as db:
        db.add(Profile(user_id=state.owner, **{**PAYLOAD, "weight_kg": 5, "goal": "cut"}))
        db.commit()
    current = summary(state, DAY1)
    assert current["target"] is None and history(state) == []


def test_invalid_save_keeps_profile_and_history_unchanged(state):
    original = save(state)
    snapshots = history(state)
    response = state.client.put(
        "/profile", json={**PAYLOAD, "weight_kg": 5, "goal": "cut"}, headers=state.headers
    )
    assert response.status_code == 422
    assert state.client.get("/profile", headers=state.headers).json() == original
    assert history(state) == snapshots


def test_snapshot_failure_rolls_back_profile_change(state, monkeypatch):
    original = save(state)
    snapshots = history(state)

    def failure(*_):
        raise RuntimeError("fixture: snapshot write failed")

    monkeypatch.setattr(profile_history, "add_revision", failure)
    with pytest.raises(RuntimeError, match="snapshot write failed"):
        state.client.put("/profile", json={**PAYLOAD, "weight_kg": 90}, headers=state.headers)
    assert state.client.get("/profile", headers=state.headers).json() == original
    assert history(state) == snapshots


def test_each_user_only_reads_their_own_targets_and_history(state):
    save(state)
    other = {"x-test-user": str(state.other)}
    assert history(state, other) == []
    assert summary(state, DAY1, other)["target"] is None
    response = state.client.put(
        "/profile", json={**PAYLOAD, "weight_kg": 90, "goal": "bulk"}, headers=other
    )
    assert response.status_code == 200
    assert summary(state, DAY1, other)["target"] != summary(state, DAY1)["target"]
    assert len(history(state, other)) == len(history(state)) == 1


def test_midnight_uses_bangkok_date_not_utc(state, monkeypatch):
    monkeypatch.setattr(
        profile_history, "utc_now", lambda: datetime(2026, 10, 14, 16, 59, 59, tzinfo=UTC)
    )
    save(state)
    original = summary(state, DAY1)["target"]
    monkeypatch.setattr(
        profile_history, "utc_now", lambda: datetime(2026, 10, 14, 17, 0, 0, tzinfo=UTC)
    )
    assert profile_history.today_bangkok() == DAY2
    save(state, weight_kg=90, goal="bulk")
    assert summary(state, DAY1)["target"] == original
    assert summary(state, DAY2)["target"] != original
    assert {row["effective_date"] for row in history(state)} == {DAY1.isoformat(), DAY2.isoformat()}


def wait_for_waiters(engine, minimum):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() AND wait_event_type='Lock'"
                )
            )
        if count >= minimum:
            return
        Event().wait(0.02)
    raise AssertionError("Requests did not contend on PostgreSQL row locks")


def test_concurrent_first_saves_keep_profile_and_latest_targets_consistent(state):
    with ThreadPoolExecutor(max_workers=2) as pool, state.engine.connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(select(User).where(User.id == state.owner).with_for_update())
        futures = [pool.submit(save, state, weight_kg=weight) for weight in [75, 90]]
        try:
            wait_for_waiters(state.engine, 2)
        finally:
            transaction.commit()
        for future in futures:
            future.result(timeout=10)
    current = state.client.get("/profile/targets", headers=state.headers).json()
    assert summary(state, DAY1)["target"]["kcal"] == current["energy_target_kcal"]
    assert len(history(state)) == 2
    with Session(state.engine) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Profile).where(Profile.user_id == state.owner)
            )
            == 1
        )


def test_equal_or_backwards_worker_clocks_do_not_restore_older_save(state, monkeypatch):
    save(state, weight_kg=70)
    save(state, weight_kg=80)
    day(monkeypatch, DAY1, hour=4)
    save(state, weight_kg=90)
    current = state.client.get("/profile/targets", headers=state.headers).json()
    assert summary(state, DAY1)["target"]["kcal"] == current["energy_target_kcal"]
    assert history(state)[0]["profile"]["weight_kg"] == 90


def test_concurrent_legacy_reads_capture_one_baseline(state):
    with Session(state.engine) as db:
        db.add(Profile(user_id=state.owner, **PAYLOAD))
        db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool, state.engine.connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(select(User).where(User.id == state.owner).with_for_update())
        futures = [pool.submit(summary, state, DAY1) for _ in range(2)]
        try:
            wait_for_waiters(state.engine, 2)
        finally:
            transaction.commit()
        values = [future.result(timeout=10) for future in futures]
    assert values[0]["target"] == values[1]["target"]
    assert len(history(state)) == 1
