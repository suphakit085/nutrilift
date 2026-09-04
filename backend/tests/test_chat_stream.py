"""The SSE turn generator must always end the stream cleanly.

Once SSE headers are sent, an exception escaping the generator just drops the
chunked body; the browser sees a truncated stream and the composer stays
disabled. And an assistant row with empty text, replayed as history, makes
Gemini reject every later turn with 400 "empty text parameter".

Everything here runs against a fake session and a fake ``stream`` - no DB, no
Gemini.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.api.chat import INTERNAL_ERROR_MESSAGE, turn_events
from app.db.models import Message

CONV_ID = uuid.uuid4()


class FakeSession:
    def __init__(self, *, conversation=True, fail_commit_on: int | None = None) -> None:
        self.conv = SimpleNamespace(id=CONV_ID, title="") if conversation else None
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.transaction_open = False
        self._fail_commit_on = fail_commit_on

    def get(self, model, key):
        return self.conv

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1
        if self._fail_commit_on == self.commits:
            raise RuntimeError("connection lost")
        self.transaction_open = False

    def rollback(self):
        self.rollbacks += 1
        self.transaction_open = False

    def in_transaction(self):
        return self.transaction_open

    def close(self):
        self.closed = True


def run(session, stream, *, is_first_message=False):
    events = list(
        turn_events(
            lambda: session,
            conversation_id=CONV_ID,
            user_message="โปรตีนวันละเท่าไหร่",
            profile=None,
            history=[],
            use_rag=True,
            is_first_message=is_first_message,
            stream=stream,
        )
    )
    return [(e["event"], json.loads(e["data"])) for e in events]


def messages(session, role):
    return [m for m in session.added if isinstance(m, Message) and m.role == role]


# --- happy path ---------------------------------------------------------


def test_persists_user_then_assistant_and_forwards_events():
    def stream(session, **kwargs):
        yield {"type": "sources", "sources": []}
        yield {"type": "delta", "text": "กิน"}
        yield {"type": "done", "text": "กินโปรตีน 1.6 g/kg", "citations": [{"label": "S1"}]}

    session = FakeSession()
    events = run(session, stream, is_first_message=True)

    assert [e for e, _ in events] == ["sources", "delta", "done"]
    assert events[-1][1]["text"] == "กินโปรตีน 1.6 g/kg"
    assert messages(session, "user")[0].content == "โปรตีนวันละเท่าไหร่"
    (assistant,) = messages(session, "assistant")
    assert assistant.content == "กินโปรตีน 1.6 g/kg"
    assert assistant.citations == [{"label": "S1"}]
    assert session.conv.title == "โปรตีนวันละเท่าไหร่"
    assert session.commits == 2
    assert session.closed


def test_read_transactions_are_released_between_events():
    """stream_chat only reads; an open read transaction must not sit idle on a
    pooled connection for the whole generation."""

    def stream(session, **kwargs):
        session.transaction_open = True  # retrieval ran a query
        yield {"type": "sources", "sources": []}
        yield {"type": "delta", "text": "..."}
        yield {"type": "done", "text": "ok"}

    session = FakeSession()
    run(session, stream)
    assert session.rollbacks == 1
    assert not session.transaction_open


# --- empty assistant turn -------------------------------------------------


@pytest.mark.parametrize("text", ["", "   \n", None])
def test_empty_assistant_turn_is_not_persisted(text):
    def stream(session, **kwargs):
        yield {"type": "done", "text": text}

    session = FakeSession()
    events = run(session, stream)

    assert [e for e, _ in events] == ["done"], "the client still needs its terminal event"
    assert messages(session, "assistant") == []
    assert len(messages(session, "user")) == 1
    assert session.commits == 1


# --- failure paths ----------------------------------------------------------


def test_missing_conversation_yields_error_and_closes():
    session = FakeSession(conversation=False)
    events = run(session, lambda *a, **k: iter(()))
    assert events == [("error", {"message": "ไม่พบห้องแชต"})]
    assert session.closed


def test_exception_from_stream_becomes_a_terminal_error_event():
    def stream(session, **kwargs):
        yield {"type": "delta", "text": "กำลัง"}
        raise ValueError("GEMINI_API_KEY is empty")

    session = FakeSession()
    events = run(session, stream)
    assert events[0][0] == "delta"
    assert events[-1] == ("error", {"message": INTERNAL_ERROR_MESSAGE})
    assert session.closed


def test_commit_failure_becomes_a_terminal_error_event():
    """The first commit (the user's message) happens before stream_chat's own
    try/except can help; it used to escape after headers were sent."""
    session = FakeSession(fail_commit_on=1)
    events = run(session, lambda *a, **k: iter(()))
    assert events == [("error", {"message": INTERNAL_ERROR_MESSAGE})]
    assert session.closed


def test_error_payload_never_leaks_the_exception_text():
    def stream(session, **kwargs):
        raise RuntimeError("psycopg.OperationalError: server closed the connection")
        yield  # pragma: no cover - makes this a generator

    session = FakeSession()
    events = run(session, stream)
    assert "psycopg" not in json.dumps(events, ensure_ascii=False)
