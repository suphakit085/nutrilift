"""Cancellation excludes model context without removing safety disclosures."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.chat import (
    _active_history,
    _conversation_safety_flags,
    _pending_food_confirmations,
    cancel_turn,
)
from app.db.models import Conversation, Message


def test_cancelled_turn_and_late_reply_are_excluded_but_other_history_remains():
    kept = Message(id=uuid.uuid4(), role="user", content="โปรตีนคืออะไร")
    cancelled = Message(id=uuid.uuid4(), role="user", content="คำถามที่หยุด", cancelled=True)
    late = Message(
        id=uuid.uuid4(), role="assistant", content="คำตอบที่เสร็จทีหลัง", reply_to_id=cancelled.id
    )
    current = Message(id=uuid.uuid4(), role="user", content="ข้าวสวยกี่แคล")
    assert _active_history([kept, cancelled, current, late]) == [kept, current]


def test_cancelled_medical_disclosure_still_blocks_personalization():
    message = Message(id=uuid.uuid4(), role="user", content="ผมเป็นโรคไต", cancelled=True)
    assert _active_history([message]) == []
    assert "medical_condition" in _conversation_safety_flags([message])


def test_cancelled_lookup_does_not_create_pending_food_confirmation():
    message = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="ยืนยันชื่ออาหาร",
        cancelled=True,
        tool_calls=[
            {
                "name": "lookup_food",
                "lookup_result": {"match": "confirmation_required", "candidates": ["เต้าหู้"]},
            }
        ],
    )
    assert _pending_food_confirmations([message]) == []


@pytest.mark.parametrize(
    "bad_target", ["foreign_conversation", "foreign_message", "assistant", "missing"]
)
def test_cancel_endpoint_does_not_allow_unowned_or_invalid_turns(bad_target):
    user = SimpleNamespace(id=uuid.uuid4())
    cid = uuid.uuid4()
    message_id = uuid.uuid4()
    conversation = SimpleNamespace(
        user_id=uuid.uuid4() if bad_target == "foreign_conversation" else user.id
    )
    message = SimpleNamespace(
        conversation_id=uuid.uuid4() if bad_target == "foreign_message" else cid,
        role="assistant" if bad_target == "assistant" else "user",
    )

    class DB:
        def get(self, model, key):
            return (
                conversation
                if model is Conversation
                else None
                if bad_target == "missing"
                else message
            )

        def execute(self, query):
            pytest.fail("Invalid cancellation must not mutate data")

        def commit(self):
            pytest.fail("Invalid cancellation must not commit")

    with pytest.raises(HTTPException) as error:
        cancel_turn(cid, message_id, user, DB())
    assert error.value.status_code == 404
