"""Things the public API must *not* let a client do (found 2026-09-15).

Run against the pydantic models and small pure helpers only - no DB, no Gemini.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import FOOD_LOG_MAX_DAYS_AHEAD, ChatRequest, FoodLogEntryIn
from app.services.prompts import BASE_SYSTEM_PROMPT
from ingest.__main__ import prune_removed_cards

# --- 7. use_rag is no longer a request field --------------------------------


def test_chat_request_ignores_use_rag():
    payload = ChatRequest.model_validate({"message": "โปรตีนวันละเท่าไหร่", "use_rag": False})
    assert not hasattr(payload, "use_rag")
    assert payload.model_dump() == {"message": "โปรตีนวันละเท่าไหร่"}


def test_chat_endpoint_source_hardwires_rag_on():
    import inspect

    from app.api import chat as chat_api

    src = inspect.getsource(chat_api.chat)
    assert "use_rag=True" in src and "payload.use_rag" not in src


# --- 8. no invented name for the user ---------------------------------------


def test_prompt_forbids_addressing_the_user_by_an_invented_name():
    assert "ห้ามแต่งชื่อให้ผู้ใช้" in BASE_SYSTEM_PROMPT
    assert "คุณผู้ชาย" in BASE_SYSTEM_PROMPT  # named as a thing not to say


# --- 9a. incremental ingest prunes cards that left the disk ----------------


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Session:
    """Answers the not_in() query with whatever is not in keep_slugs."""

    def __init__(self, slugs):
        self.docs = [SimpleNamespace(slug=s) for s in slugs]
        self.deleted: list = []
        self.commits = 0
        self.keep: set[str] = set()

    def execute(self, _stmt):
        return _Result([d for d in self.docs if d.slug not in self.keep])

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1


def test_prune_removes_only_documents_without_a_card_file():
    session = _Session(["creatine", "old-slug", "fiber"])
    session.keep = {"creatine", "fiber"}
    assert prune_removed_cards(session, session.keep) == ["old-slug"]
    assert [d.slug for d in session.deleted] == ["old-slug"]
    assert session.commits == 1


def test_prune_is_a_no_op_when_everything_is_current():
    session = _Session(["creatine", "fiber"])
    session.keep = {"creatine", "fiber"}
    assert prune_removed_cards(session, session.keep) == []
    assert session.deleted == [] and session.commits == 0


# --- 9b. diary entries cannot be dated in the future -------------------------


def _entry(day):
    return {
        "food_id": str(uuid4()),
        "meal_type": "lunch",
        "quantity_servings": 1,
        "logged_date": day,
    }


def test_food_log_rejects_dates_beyond_the_grace_day():
    too_far = datetime.now(UTC).date() + timedelta(days=FOOD_LOG_MAX_DAYS_AHEAD + 1)
    with pytest.raises(ValidationError, match="ล่วงหน้า"):
        FoodLogEntryIn.model_validate(_entry(too_far.isoformat()))


@pytest.mark.parametrize("offset", [0, -1, -30, FOOD_LOG_MAX_DAYS_AHEAD])
def test_food_log_accepts_today_past_and_the_timezone_grace_day(offset):
    day = datetime.now(UTC).date() + timedelta(days=offset)
    assert FoodLogEntryIn.model_validate(_entry(day.isoformat())).logged_date == day
