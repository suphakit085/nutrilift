"""A per-minute 429 on the generator is retried, not shown as "quota for today".

The free tier allows 15 generate requests a minute for the whole deployment.
Before 2026-09-15 the first 429 ended the turn with the daily-quota message,
which was untrue and left the user to retype. Everything here runs with a fake
Gemini client and a no-op sleep.
"""

from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.services import chat

RATE_LIMIT = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota. Please retry in 4.2s.'}}"
)
DAILY = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded for "
    "metric: generate_content_free_tier_requests_per_day, limit: 500'}}"
)


def _err(message: str, code: int = 429):
    return genai_errors.ClientError(code, {"error": {"code": code, "message": message}})


def _chunk(text: str):
    part = types.Part.from_text(text=text)
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        text=text,
        usage_metadata=None,
    )


class FakeModels:
    """Each entry in ``script`` is either an exception or an iterable of chunks."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def generate_content_stream(self, **_kwargs):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        yield from step


class FakeDB:
    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def harness(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(chat.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(chat.retrieval, "search", lambda db, q, **kw: [])

    def run(script):
        models = FakeModels(script)
        monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(models=models))
        events = list(chat.stream_chat(FakeDB(), user_message="โปรตีนวันละเท่าไหร่"))
        return events, models, sleeps

    return run


def test_rate_limit_before_any_output_is_retried_and_announced(harness):
    events, models, sleeps = harness([_err(RATE_LIMIT), [_chunk("1.6 g/kg")]])
    kinds = [e["type"] for e in events]
    assert kinds == ["sources", "retry", "delta", "done"]
    assert "ลองใหม่" in events[1]["message"] and events[1]["wait_s"] == pytest.approx(6.2)
    assert sleeps == [pytest.approx(6.2)]
    assert models.calls == 2
    assert events[-1]["text"] == "1.6 g/kg"


def test_gives_up_after_the_retry_budget(harness):
    events, models, _ = harness([_err(RATE_LIMIT)] * 3)
    kinds = [e["type"] for e in events]
    assert kinds == ["sources", "retry", "retry", "error"]
    assert models.calls == chat.GENERATE_MAX_RETRIES + 1
    assert "โควตา" in events[-1]["message"]


def test_delay_is_capped_for_a_live_user(harness):
    slow = _err("429 RESOURCE_EXHAUSTED. Please retry in 55s.")
    events, _, sleeps = harness([slow, [_chunk("ok")]])
    assert sleeps == [chat.GENERATE_MAX_DELAY_S]
    assert events[1]["wait_s"] == chat.GENERATE_MAX_DELAY_S


def test_incomplete_buffered_text_is_discarded_before_retry(harness):
    def cut_stream():
        yield _chunk("ครึ่ง")
        raise _err(RATE_LIMIT)

    events, models, sleeps = harness([cut_stream(), [_chunk("คำตอบครบ")]])
    assert [e["type"] for e in events] == ["sources", "retry", "delta", "done"]
    assert models.calls == 2 and len(sleeps) == 1
    assert events[-1]["text"] == "คำตอบครบ"


def test_daily_cap_is_not_retried(harness):
    events, models, sleeps = harness([_err(DAILY)])
    assert [e["type"] for e in events] == ["sources", "error"]
    assert models.calls == 1 and sleeps == []


def test_other_client_errors_are_not_retried(harness):
    events, models, _ = harness([_err("400 INVALID_ARGUMENT", code=400)])
    assert [e["type"] for e in events] == ["sources", "error"]
    assert models.calls == 1


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_err(RATE_LIMIT), 6.2),
        (_err("429 RESOURCE_EXHAUSTED with no hint"), chat.GENERATE_MAX_DELAY_S),
        (_err(DAILY), None),
        (_err("400 bad", code=400), None),
        (RuntimeError("429 in a plain exception"), None),
    ],
)
def test_rate_limit_retry_delay(exc, expected):
    got = chat.rate_limit_retry_delay(exc)
    assert got == (pytest.approx(expected) if expected is not None else None)


# --- stalls and overloads (production_review_2026-09-24.md, B1) --------------
# 2 of ~110 live turns stalled past 150 s: the SDK had no timeout and SSE pings
# kept the browser waiting forever. The client now times out on silence and the
# turn gets one more try, or a Thai "took too long" message.


def _overloaded():
    body = {"error": {"code": 503, "message": "The model is overloaded."}}
    return genai_errors.ServerError(503, body)


def test_client_has_a_read_timeout(monkeypatch):
    from app.services import llm

    # Constructing the SDK client should not depend on a developer's real key.
    monkeypatch.setattr(llm.settings, "gemini_api_key", "test-api-key")
    llm.get_client.cache_clear()
    try:
        client = llm.get_client()
        assert client._api_client._http_options.timeout == llm.MODEL_READ_TIMEOUT_S * 1000
    finally:
        llm.get_client.cache_clear()


def test_a_stall_before_output_is_retried_once(harness):
    events, models, sleeps = harness([httpx.ReadTimeout("read timed out"), [_chunk("ตอบแล้ว")]])
    assert [e["type"] for e in events] == ["sources", "retry", "delta", "done"]
    assert "ช้ากว่าปกติ" in events[1]["message"]
    assert models.calls == 2 and sleeps == []


def test_a_second_stall_ends_with_the_took_too_long_message(harness):
    events, models, _ = harness([httpx.ReadTimeout("read timed out")] * 3)
    assert [e["type"] for e in events] == ["sources", "retry", "error"]
    assert models.calls == 2
    assert "นานเกินไป" in events[-1]["message"]


def test_a_stall_mid_buffered_answer_is_retried(harness):
    def cut_stream():
        yield _chunk("ครึ่ง")
        raise httpx.ReadTimeout("read timed out")

    events, models, _ = harness([cut_stream(), [_chunk("ครบ")]])
    assert [e["type"] for e in events] == ["sources", "retry", "delta", "done"]
    assert models.calls == 2
    assert events[-1]["text"] == "ครบ"


def test_internal_heading_split_across_chunks_never_reaches_client(harness):
    events, _, _ = harness([[_chunk("ปรึกษาแพทย์ [ข้อจำกัดด้าน"),
                            _chunk("ความปลอดภัย] [S1]")]])
    assert events[-1]["text"] == "ปรึกษาแพทย์  [S1]"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == events[-1]["text"]


def test_timed_out_tool_turn_is_discarded_without_executing_it(harness, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "_execute_tool", lambda *args: calls.append(args))

    def cut_stream():
        yield SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            types.Part(function_call=types.FunctionCall(name="calc_nutrition_targets", args={}))
        ]))], text=None, usage_metadata=None)
        raise httpx.ReadTimeout("read timed out")

    events, models, _ = harness([cut_stream(), [_chunk("กรุณากรอกโปรไฟล์")]])
    assert events[-1]["type"] == "done"
    assert models.calls == 2 and calls == []


def test_verified_food_survives_timeout_after_lookup(harness, monkeypatch):
    row = {"name_th": "ข้าวสวย", "serving_desc": "1 หน่วย", "serving_g": 120,
           "kcal": 155, "protein_g": 2.6, "carb_g": 35.3, "fat_g": 0.1, "estimated": True}
    monkeypatch.setattr(chat, "_run_food_lookup", lambda *a, **kw:
                        {"found": True, "match": "exact", "results": [row]})
    tool = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
        types.Part(function_call=types.FunctionCall(name="lookup_food", args={"query": "ข้าวสวย"}))
    ]))], text=None, usage_metadata=None)
    events, models, _ = harness([
        [tool], httpx.ReadTimeout("timeout"), httpx.ReadTimeout("timeout")
    ])
    assert events[-1]["type"] == "done"
    assert models.calls == 3
    assert "155 kcal" in events[-1]["text"]
    assert "120 กรัม" in events[-1]["text"]
    assert "ค่าประมาณที่ยังไม่ได้ยืนยัน" in events[-1]["text"]
    assert "ยังไม่ได้ปรับ" in events[-1]["text"]


def test_overload_503_is_retried(harness):
    events, models, sleeps = harness([_overloaded(), [_chunk("ok")]])
    assert [e["type"] for e in events] == ["sources", "retry", "delta", "done"]
    assert models.calls == 2
    assert "ขัดข้องชั่วคราว" in events[1]["message"]
    assert sleeps == [chat.OVERLOADED_RETRY_DELAY_S]
