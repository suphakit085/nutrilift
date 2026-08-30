"""Conversations and the streaming chat endpoint (SSE)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, profile_to_input
from app.api.schemas import ChatRequest, ConversationDetail, ConversationOut
from app.core.config import settings
from app.db.models import Conversation, Message, Profile, User
from app.db.session import SessionLocal, get_db
from app.services.chat import stream_chat

router = APIRouter(tags=["chat"])


# --- conversations ------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Conversation:
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    return _owned_conversation(db, user, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.delete(_owned_conversation(db, user, conversation_id))
    db.commit()


def _owned_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบห้องแชตนี้")
    return conversation


# --- chat ---------------------------------------------------------------


@router.post("/conversations/{conversation_id}/chat")
def chat(
    conversation_id: uuid.UUID,
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    conversation_id_value = conversation.id
    user_message = payload.message
    use_rag = payload.use_rag

    def event_generator() -> Iterator[dict]:
        # A dedicated session: the request-scoped one is closed once the
        # response starts streaming.
        session = SessionLocal()
        try:
            conv = session.get(Conversation, conversation_id_value)
            if conv is None:
                yield {"event": "error", "data": json.dumps({"message": "ไม่พบห้องแชต"})}
                return

            session.add(Message(conversation_id=conv.id, role="user", content=user_message))
            if is_first_message:
                conv.title = user_message[:60]
            session.commit()

            for event in stream_chat(
                session,
                user_message=user_message,
                profile=profile,
                history=history,
                use_rag=use_rag,
            ):
                event_type = event.pop("type")
                if event_type == "done":
                    session.add(
                        Message(
                            conversation_id=conv.id,
                            role="assistant",
                            content=event.get("text", ""),
                            citations=event.get("citations"),
                            tool_calls=event.get("tool_calls"),
                            usage=event.get("usage"),
                            safety_flags=event.get("safety_flags"),
                        )
                    )
                    session.commit()
                yield {"event": event_type, "data": json.dumps(event, ensure_ascii=False)}
        finally:
            session.close()

    return EventSourceResponse(event_generator())
