from copy import deepcopy
from types import SimpleNamespace

import pytest
from google.genai import types

from app.services import chat
from app.services.food_portions import verified_food_portion_reply

RICE = {
    "found": True,
    "match": "exact",
    "results": [{
        "name_th": "ข้าวสวย", "serving_g": 120, "kcal": 155,
        "protein_g": 2.6, "carb_g": 35.3, "fat_g": 0.2, "fiber_g": 0.7,
        "nutrition_meta": {"carb_definition": "available"},
    }],
}


def test_requested_weight_is_scaled_even_when_tool_has_only_food_name():
    answer = verified_food_portion_reply([RICE], "ข้าวสวย 180 กรัม มีสารอาหารเท่าไร")
    for expected in ["180 กรัม", "232.5 kcal", "3.9 กรัม", "52.95 กรัม", "1.05 กรัม"]:
        assert expected in answer


def test_tiny_known_nutrients_do_not_become_displayed_zero():
    answer = verified_food_portion_reply([RICE], "ข้าวสวย 2.5 กรัม")
    assert "3.229 kcal" in answer
    assert "0.004 กรัม" in answer and "0.015 กรัม" in answer


@pytest.mark.parametrize("fiber", [None, "unknown", "crude"])
def test_unknown_and_crude_fiber_are_not_treated_as_total_fiber(fiber):
    result = deepcopy(RICE)
    if fiber is None:
        result["results"][0]["fiber_g"] = None
    else:
        result["results"][0]["nutrition_meta"]["fiber_definition"] = fiber
    answer = verified_food_portion_reply([result], "ข้าวสวย 180 กรัม")
    assert "ยังไม่มีข้อมูลที่ยืนยันได้ ไม่ใช่ศูนย์กรัม" in answer


@pytest.mark.parametrize("question", ["ข้าวสวย", "ข้าวสวย -180 กรัม", "100 กรัม กับ 180 กรัม"])
def test_missing_invalid_or_ambiguous_weight_is_not_guessed(question):
    assert verified_food_portion_reply([RICE], question) is None


def test_multiple_foods_are_not_scaled_as_one_food():
    assert verified_food_portion_reply([RICE, RICE], "ข้าวสวย 180 กรัม") is None


def test_verified_portion_bypasses_model_rewriting_and_keeps_data_notes(monkeypatch):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        assert len(calls) == 1, "A second model response can ignore the requested 180 grams"
        part = types.Part(function_call=types.FunctionCall(
            id="rice", name="lookup_food", args={"query": "ข้าวสวย"},
        ))
        yield SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
            text=None, usage_metadata=None,
        )

    monkeypatch.setattr(chat, "lookup_food", lambda *_: deepcopy(RICE))
    monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=generate),
    ))
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    result = list(chat.stream_chat(
        db, user_message="ข้าวสวย 180 กรัม มีสารอาหารเท่าไร", use_rag=False,
    ))[-1]
    assert result["type"] == "done"
    assert "232.5 kcal" in result["text"]
    assert "ไม่รวมใยอาหาร" in result["text"]
    assert len(result["tool_calls"]) == 1
