from __future__ import annotations

from types import SimpleNamespace

from google.genai import types

from app.api.chat import _pending_food_confirmations
from app.services import chat

CANDIDATE = "อกไก่ไม่มีหนัง, ย่าง"


def _function_chunk(query: str, call_id: str):
    part = types.Part(
        function_call=types.FunctionCall(
            id=call_id,
            name="lookup_food",
            args={"query": query},
        )
    )
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        text=None,
        usage_metadata=None,
    )


def _text_chunk(text: str):
    part = types.Part.from_text(text=text)
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        text=text,
        usage_metadata=None,
    )


class _FakeModels:
    def __init__(self, script):
        self.script = iter(script)

    def generate_content_stream(self, **_kwargs):
        yield next(self.script)


class _FakeDB:
    def commit(self):
        pass

    def rollback(self):
        pass


def test_model_cannot_confirm_its_own_partial_suggestion(monkeypatch):
    calls = []

    def lookup(_db, query):
        calls.append(query)
        return {
            "query": query,
            "found": False,
            "match": "partial",
            "results": [],
            "candidates": [CANDIDATE],
            "note": "รอผู้ใช้ยืนยัน",
        }

    models = _FakeModels([
        _function_chunk("อกไก่ย่างไม่มีหนัง", "partial"),
        _function_chunk(CANDIDATE, "self-confirm"),
        _text_chunk("กรุณายืนยันชื่อรายการก่อนครับ"),
    ])
    monkeypatch.setattr(chat, "lookup_food", lookup)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(models=models))

    events = list(chat.stream_chat(_FakeDB(), user_message="อกไก่ย่างไม่มีหนังมีโปรตีนเท่าไร"))
    done = events[-1]

    assert done["type"] == "done"
    assert calls == ["อกไก่ย่างไม่มีหนัง"]
    assert done["tool_calls"][1]["lookup_result"]["confirmation_required"] is True
    assert done["tool_calls"][1]["lookup_result"]["candidates"] == [CANDIDATE]


def test_pending_candidate_requires_user_to_repeat_the_name(monkeypatch):
    calls = []

    def lookup(_db, query):
        calls.append(query)
        return {"query": query, "found": True, "match": "exact", "results": [{"protein_g": 30.5}]}

    monkeypatch.setattr(chat, "lookup_food", lookup)
    blocked = chat._run_food_lookup(
        None,
        CANDIDATE,
        user_message="แล้วโปรตีนเท่าไร",
        pending_confirmations=[CANDIDATE],
        partial_candidates_this_turn=[],
    )
    assert blocked["found"] is False
    assert blocked["confirmation_required"] is True
    assert calls == []

    confirmed = chat._run_food_lookup(
        None,
        CANDIDATE + " 100 กรัม",
        user_message="ยืนยันรายการ " + CANDIDATE,
        pending_confirmations=[CANDIDATE],
        partial_candidates_this_turn=[],
    )
    assert confirmed["found"] is True
    assert confirmed["confirmation_for"] == CANDIDATE
    assert calls == [CANDIDATE]


def test_pending_confirmation_is_carried_until_user_confirms_a_candidate():
    partial_message = SimpleNamespace(
        role="assistant",
        tool_calls=[{
            "name": "lookup_food",
            "lookup_result": {"match": "partial", "candidates": [CANDIDATE]},
        }],
    )
    pending_message = SimpleNamespace(role="assistant", tool_calls=[])
    confirmed_message = SimpleNamespace(
        role="assistant",
        tool_calls=[{
            "name": "lookup_food",
            "lookup_result": {"match": "exact", "confirmation_for": CANDIDATE},
        }],
    )

    assert _pending_food_confirmations([partial_message, pending_message]) == [CANDIDATE]
    assert _pending_food_confirmations([partial_message, confirmed_message]) == []
