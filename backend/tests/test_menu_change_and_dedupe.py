# ruff: noqa: E501
"""25 Oct live test: a snack request read as 'another set', and rice listed twice."""

from types import SimpleNamespace

from app.services import chat
from app.services.food_suggestions import suggest_foods
from app.services.menu_changes import apply_menu_change
from app.services.request_understanding import MenuChange, _checked
from tests.test_food_suggestions import foods
from tests.test_functional_prompt_fixes import adult, client_for, understood

SNACK = "อยากได้มื้อว่างตอนบ่ายเพิ่มอีกมื้อ"
HISTORY = [
    {"role": "user", "content": "จัดเมนูกินทั้งวันให้ผมหน่อย"},
    {"role": "assistant", "content": "เมนู",
     "tool_calls": [{"name": "suggest_day_menu", "status": "success",
                     "arguments": {"variant": 0, "meal_count": None}}]},
]


def reading(change, **changes):
    return understood(menu_change=change, **changes).model_dump_json()


def test_snack_without_a_number_is_grounded():
    change = {"kind": "add_meals", "added_meals": None, "quote": "มื้อว่างตอนบ่ายเพิ่มอีกมื้อ"}
    assert _checked(reading(change), ["จัดเมนู", SNACK]).menu_change.kind == "add_meals"


def test_ungrounded_menu_change_is_dropped():
    for bad in ({"kind": "add_meals", "added_meals": 2, "quote": "เพิ่มอีกมื้อ"},
                {"kind": "another_set", "added_meals": None, "quote": "ขอเมนูอีกชุด"}):
        assert _checked(reading(bad), ["จัดเมนู", SNACK]).menu_change is None


def test_add_meals_keeps_the_set_and_adds_to_the_count():
    args = {"variant": 1, "meal_count": None, "allow_extra_meals": None, "suggest_extra_meals": True}
    added = apply_menu_change(args, MenuChange(kind="add_meals", quote=SNACK), HISTORY)
    assert added["variant"] == 0 and added["meal_count"] == 4 and added["allow_extra_meals"] is False
    two = apply_menu_change(args, MenuChange(kind="add_meals", added_meals=2, quote="2 มื้อ"), HISTORY)
    assert two["meal_count"] == 5


def test_another_set_moves_to_the_next_variant():
    args = {"variant": 0, "meal_count": None}
    other = apply_menu_change(args, MenuChange(kind="another_set", quote="อีกชุด"), HISTORY)
    assert other["variant"] == 1


def test_snack_follow_up_plans_the_same_set_with_one_more_meal(monkeypatch):
    seen = []

    def fake_tool(db, profile, args, guard=None):
        seen.append(dict(args))
        return {"error": "x", "message": "เมนู"}

    change = {"kind": "add_meals", "added_meals": None, "quote": "มื้อว่างตอนบ่ายเพิ่มอีกมื้อ"}
    client, _ = client_for(reading(change, task="knowledge"))
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat, "_run_menu_tool", fake_tool)
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message=SNACK, history=HISTORY, profile=adult(),
    )
    assert result["model"] == "rule:verified_menu"
    assert seen[0]["variant"] == 0 and seen[0]["meal_count"] == 4


def test_one_composition_record_fills_one_place():
    for focus in ("carbohydrate", "protein"):
        items = suggest_foods(foods(), focus, [], 6)
        sources = [f["source"] for f in items]
        assert len(sources) == len(set(sources))
    names = [f["name_th"] for f in suggest_foods(foods(), "carbohydrate", [], 4)]
    assert not {"ข้าวเจ้า, สุก", "ข้าวสวย"} <= set(names)
