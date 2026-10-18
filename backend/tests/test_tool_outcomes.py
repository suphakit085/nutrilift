"""Outcome travels with the result; completion alone must not claim success."""
from types import SimpleNamespace

import pytest
from google.genai import types

from app.services import chat
from app.services.nutrition import ProfileInput
from tests import test_meal_practicality

real_foods = test_meal_practicality.real_foods


@pytest.mark.parametrize("count,weight,height,restrictions,expected", [
    (3, 55, 160, [], "success"),
    (3, 110, 195, [], "partial"),
    (7, 55, 160, [], "error"),
    (3, 55, 160, ["วีแกน", "แพ้ถั่วเหลือง"], "error"),
])
def test_real_menu_result_has_same_outcome_in_stream_and_saved_log(
    real_foods, monkeypatch, count, weight, height, restrictions, expected
):
    profile = ProfileInput(sex="male" if weight == 110 else "female", birth_year=1998,
        birth_month=1, weight_kg=weight, height_cm=height,
        activity_level="active" if weight == 110 else "moderate",
        goal="bulk" if weight == 110 else "maintain", restrictions=restrictions)
    monkeypatch.setattr(chat, "all_foods", lambda _: real_foods)
    chunk = SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(parts=[
        types.Part(function_call=types.FunctionCall(
            name="suggest_day_menu", args={"meal_count": count}))
    ]), finish_reason="STOP")], text="", usage_metadata=None)
    monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=lambda **_: iter([chunk]))))
    events = list(chat.stream_chat(SimpleNamespace(commit=lambda: None, rollback=lambda: None),
        user_message=f"จัดเมนู {count} มื้อ ไม่เพิ่มมื้อเสริม", profile=profile, use_rag=False))
    tools = [e for e in events if e["type"] == "tool"]
    final = events[-1]
    assert final["type"] == "done"
    assert tools[0]["status"] == final["tool_calls"][0]["status"] == expected
    for leaked in ("ให้บอกผู้ใช้", "cannot_build_menu", "Traceback"):
        assert leaked not in final["text"]
    if restrictions:
        assert "ไม่พบแหล่งโปรตีน" in final["text"]
        assert "| มื้อเช้า |" not in final["text"]


@pytest.mark.parametrize("result,expected", [
    ({"found": True}, "success"),
    ({"found": False, "match": "partial"}, "confirmation_required"),
    ({"found": False, "match": "confirmation_required"}, "confirmation_required"),
    ({"found": False}, "not_found"),
    ({"error": "failed"}, "error"),
])
def test_lookup_outcome_is_based_on_verified_result(result, expected):
    assert chat._tool_status("lookup_food", result) == expected
