"""Food suggestions come from the food database (24 Oct live test, item 2)."""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from app.services import chat
from app.services.food_suggestions import suggest_foods, suggestion_reply
from app.services.meal_plan import excluded_by
from app.services.request_understanding import _checked
from tests.test_functional_prompt_fixes import adult, client_for, understood

FOODS_CSV = Path(__file__).resolve().parents[2] / "knowledge" / "foods.csv"


def foods():
    rows = list(csv.DictReader(FOODS_CSV.open(encoding="utf-8-sig")))
    for row in rows:
        row["nutrition_meta"] = json.loads(row["nutrition_meta"]) if row["nutrition_meta"] else None
    return rows


def suggestion(**changes):
    return {"focus": "protein", "count": None, "count_quote": None, "exclude": [],
            "exclude_quotes": []} | changes


def reading(value, **changes):
    return understood(food_suggestion=value, **changes).model_dump_json()


NO_MILK = "ขออาหารไม่มีนม 3 อย่าง"


def test_grounded_suggestion_is_kept():
    value = _checked(reading(suggestion(count=3, count_quote="3 อย่าง", exclude=["แพ้นมวัว"],
                                        exclude_quotes=["ไม่มีนม"])), [NO_MILK])
    assert value.food_suggestion.count == 3 and value.food_suggestion.exclude == ["แพ้นมวัว"]


def test_ungrounded_suggestion_is_dropped_whole():
    for bad in (
        suggestion(count=4, count_quote="3 อย่าง"),
        suggestion(count=3, count_quote=None),
        suggestion(exclude=["แพ้นมวัว"], exclude_quotes=["ไม่มีไข่"]),
        suggestion(exclude=["แพ้นมวัว"], exclude_quotes=[]),
    ):
        assert _checked(reading(bad), [NO_MILK]).food_suggestion is None


def test_medical_reading_drops_the_suggestion():
    value = _checked(reading(suggestion(), medical_self_context=True), [NO_MILK])
    assert value.food_suggestion is None


def test_suggestions_respect_restrictions_and_skip_supplements():
    rows = foods()
    for restrictions in ([], ["แพ้นมวัว"], ["วีแกน"], ["แพ้อาหารทะเล", "ไม่กินไข่"]):
        items = suggest_foods(rows, "protein", restrictions)
        assert items and len(items) <= 5
        assert not any(excluded_by(food, restrictions) for food in items)
        assert all(food["category"] != "อาหารเสริม" for food in items)
    assert len(suggest_foods(rows, "protein", ["แพ้นมวัว"], 3)) == 3


def test_default_list_spans_several_categories():
    items = suggest_foods(foods(), "protein", [])
    assert len({food["category"] for food in items}) >= 3


def test_reply_shows_database_values_and_the_request_only_filter():
    rows = foods()
    items = suggest_foods(rows, "protein", ["แพ้นมวัว"], 3)
    reply = suggestion_reply(items, "protein", 3, ["แพ้นมวัว"], ["แพ้นมวัว"])
    first = items[0]
    assert f"1. {first['name_th']} ({first['serving_desc']})" in reply
    assert "ใช้เฉพาะคำตอบนี้" in reply and "[S" not in reply


def _answer(monkeypatch, state, message=NO_MILK):
    client, calls = client_for(state)
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat, "all_foods", lambda db: foods())
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message=message, profile=adult(),
    )
    return result, calls


def test_suggestion_beats_a_menu_reading(monkeypatch):
    # The live site answered "3 foods without milk" with a whole-day menu.
    state = reading(suggestion(count=3, count_quote="3 อย่าง", exclude=["แพ้นมวัว"],
                               exclude_quotes=["ไม่มีนม"]), task="plan_menu")
    result, calls = _answer(monkeypatch, state)
    assert result["model"] == "rule:food_suggestion"
    assert "\n3. " in result["text"] and "\n4. " not in result["text"]
    assert len(calls) == 1  # interpreter only


def test_without_suggestion_the_menu_route_is_unchanged(monkeypatch):
    monkeypatch.setattr(chat, "_run_menu_tool", lambda *a, **k: {"error": "x", "message": "เมนู"})
    result, _ = _answer(monkeypatch, reading(None, task="plan_menu"), "ช่วยจัดเมนู 1 วัน")
    assert result["model"] == "rule:verified_menu"
