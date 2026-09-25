"""Conversations and the streaming chat endpoint (SSE)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import DB_SESSION, get_consented_user, profile_to_input, rate_limit_chat
from app.api.schemas import ChatRequest, ConversationDetail, ConversationOut
from app.core.config import settings
from app.db.models import Conversation, Message, Profile, User
from app.db.session import SessionLocal
from app.services.chat import stream_chat
from app.services.nutrition import ProfileInput

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

#: Shown when the turn dies *outside* stream_chat's own error handling (a
#: commit failing, the Gemini client refusing to build on an empty key, ...).
#: Once SSE headers are out, an uncaught exception just drops the chunked
#: body and the frontend hangs with the composer disabled; a terminal error
#: event is the only way to tell it the turn is over.
INTERNAL_ERROR_MESSAGE = "เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่อีกครั้ง"


# --- conversations ------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: User = Depends(get_consented_user), db: Session = DB_SESSION
) -> list[Conversation]:
    return list(
        db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.created_at.desc())
        ).scalars()
    )


@router.post(
    "/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    user: User = Depends(get_consented_user), db: Session = DB_SESSION
) -> Conversation:
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> Conversation:
    return _owned_conversation(db, user, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_consented_user),
    db: Session = DB_SESSION,
) -> None:
    db.delete(_owned_conversation(db, user, conversation_id))
    db.commit()


def _owned_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบห้องแชตนี้")
    return conversation


def _pending_food_confirmations(messages: list[Message]) -> list[str]:
    """Replay food-lookup outcomes to find candidates the user has not named yet."""
    pending: dict[str, None] = {}
    for message in messages:
        if message.role != "assistant":
            continue
        for call in message.tool_calls or []:
            if call.get("name") != "lookup_food":
                continue
            outcome = call.get("lookup_result") or {}
            if outcome.get("confirmation_for"):
                pending.pop(outcome["confirmation_for"], None)
            if outcome.get("match") in {"partial", "confirmation_required"}:
                for candidate in outcome.get("candidates") or []:
                    pending[candidate] = None
    return list(pending)


# --- chat ---------------------------------------------------------------


def _sse(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def turn_events(
    session_factory: Callable[[], Session],
    *,
    conversation_id: uuid.UUID,
    user_message: str,
    profile: ProfileInput | None,
    history: list[dict],
    use_rag: bool,
    is_first_message: bool,
    pending_food_confirmations: list[str] | None = None,
    stream: Callable[..., Iterator[dict]] = stream_chat,
) -> Iterator[dict]:
    """Persist the user turn, stream the assistant turn, persist the result.

    Module-level (rather than a closure in the endpoint) so the persistence and
    error paths are unit-testable with a fake session and a fake ``stream``.

    Connection hygiene matters here because this generator runs for the whole
    LLM stream on a pooled Supabase connection:

    - ``session.commit()`` ends the transaction and returns the connection to
      the pool; SQLAlchemy only re-acquires one on the next query.
    - ``stream_chat`` only *reads* through the session (retrieval, food and
      menu tool lookups) and each read begins a transaction that would
      otherwise sit "idle in transaction" until the ``done`` commit. So after
      every event handed back to the client, an open read transaction is
      released; the next read simply starts a fresh one.
    """
    session = session_factory()
    try:
        conv = session.get(Conversation, conversation_id)
        if conv is None:
            yield _sse("error", {"message": "ไม่พบห้องแชต"})
            return

        session.add(Message(conversation_id=conversation_id, role="user", content=user_message))
        if is_first_message:
            conv.title = user_message[:60]
        session.commit()

        for event in stream(
            session,
            user_message=user_message,
            profile=profile,
            history=history,
            use_rag=use_rag,
            pending_food_confirmations=pending_food_confirmations or [],
        ):
            event_type = event.pop("type")
            if event_type == "done":
                text = event.get("text") or ""
                if text.strip():
                    session.add(
                        Message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=text,
                            citations=event.get("citations"),
                            tool_calls=event.get("tool_calls"),
                            usage=event.get("usage"),
                            safety_flags=event.get("safety_flags"),
                        )
                    )
                    session.commit()
                else:
                    # An empty assistant turn replayed as history is rejected
                    # by Gemini ("empty text parameter", 400) on every later
                    # turn, bricking the conversation. Keep the user's message
                    # (already committed) and just skip this row.
                    logger.warning(
                        "assistant turn for conversation %s produced no text; not persisted",
                        conversation_id,
                    )
                    session.rollback()
            elif session.in_transaction():
                session.rollback()
            yield _sse(event_type, event)
    except Exception:
        logger.exception("chat turn failed for conversation %s", conversation_id)
        yield _sse("error", {"message": INTERNAL_ERROR_MESSAGE})
    finally:
        session.close()


@router.post("/conversations/{conversation_id}/chat")
def chat(
    conversation_id: uuid.UUID,
    payload: ChatRequest,
    user: User = Depends(rate_limit_chat),
    db: Session = DB_SESSION,
) -> EventSourceResponse:
    """Stream one assistant turn as Server-Sent Events.

    Event names: ``sources``, ``delta``, ``tool``, ``done``, ``error``.
    """
    conversation = _owned_conversation(db, user, conversation_id)
    profile = profile_to_input(db.get(Profile, user.id))

    history = [
        {"role": m.role, "content": m.content}
        for m in conversation.messages[-(settings.history_turns * 2) :]
    ]
    is_first_message = not conversation.messages

    # ``db`` is function-scoped (see DB_SESSION), so it is closed before the
    # response starts streaming; everything the generator needs is copied out
    # above and it opens its own short-lived session for the stream.
    return EventSourceResponse(
        turn_events(
            SessionLocal,
            conversation_id=conversation.id,
            user_message=payload.message,
            profile=profile,
            history=history,
            # Always on for the web app; the no-RAG arm exists only inside
            # eval/run_eval.py, which calls collect_answer() directly.
            use_rag=True,
            is_first_message=is_first_message,
            pending_food_confirmations=_pending_food_confirmations(conversation.messages),
        )
    )
