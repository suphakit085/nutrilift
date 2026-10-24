# ruff: noqa: E501
"""A follow-up menu says how it changed the main meals the user already saw."""

from copy import deepcopy
from types import SimpleNamespace

from app.services import chat
from app.services.menu_changes import main_meal_change_note, previous_menu_call, shown_in
from tests.test_functional_prompt_fixes import adult


def item(name, portion):
    return {"name_th": name, "portion_desc_th": portion, "preparation": {"label_th": "สุก"}}


def meal(label, kind, items, kcal):
    return {"label_th": label, "kind": kind, "items": items, "kcal": kcal,
            "protein_g": 30.0, "carb_g": 80.0, "fat_g": 15.0}


def plan(meals, total_kcal, extras=0):
    return {"meals": meals, "totals": {"kcal": total_kcal, "protein_g": 120.0, "carb_g": 320.0,
                                       "fat_g": 59.0},
            "targets": {"kcal": 2391.0, "protein_g": 118.0, "carb_g": 348.0, "fat_g": 59.0},
            "within_tolerance": True, "main_meal_count": 3, "supplemental_meal_count": extras,
            "variant": 0}


BEFORE = plan([
    meal("มื้อเช้า", "main",
         [item("ขนมปังโฮลวีท", "150 กรัม"), item("ไข่ไก่ต้ม", "2 ฟอง (รวม 100 กรัม)")], 855.0),
    meal("มื้อกลางวัน", "main", [item("ข้าวสวย", "300 กรัม")], 692.0),
    meal("มื้อเย็น", "main", [item("ปลาแซลมอน, อบ", "100 กรัม")], 827.6),
], 2374.7)
AFTER = plan([
    meal("มื้อเช้า", "main",
         [item("ขนมปังโฮลวีท", "100 กรัม"), item("ไข่ไก่ต้ม", "1 ฟอง (รวม 50 กรัม)")], 600.0),
    meal("มื้อกลางวัน", "main", [item("ข้าวสวย", "300 กรัม")], 692.0),
    meal("มื้อเย็น", "main", [item("ปลาแซลมอน, อบ", "50 กรัม")], 600.0),
    meal("มื้อเสริมที่ 1", "supplemental", [item("มะละกอสุก", "75 กรัม")], 533.0),
], 2425.2, extras=1)
SHOWN = "\n".join(f"{i['name_th']}: {i['portion_desc_th']} — สุก" for m in BEFORE["meals"] for i in m["items"])
HISTORY = [
    {"role": "user", "content": "ช่วยจัดเมนูอาหาร 1 วันให้หน่อย"},
    {"role": "assistant", "content": SHOWN,
     "tool_calls": [{"name": "suggest_day_menu", "status": "success", "arguments": {"variant": 0}}]},
]


def test_previous_call_is_the_last_successful_menu():
    failed = {"role": "assistant", "content": "x",
              "tool_calls": [{"name": "suggest_day_menu", "status": "error", "arguments": {"variant": 5}}]}
    args, text = previous_menu_call([*HISTORY, failed])
    assert args == {"variant": 0} and text == SHOWN
    assert previous_menu_call([{"role": "user", "content": "x"}]) is None


def test_rebuilt_plan_must_match_what_the_user_saw():
    assert shown_in(BEFORE, SHOWN)
    assert not shown_in(AFTER, SHOWN)


def test_note_lists_each_changed_main_item_and_the_cost_of_keeping_them():
    note = main_meal_change_note(BEFORE, AFTER)
    assert "มื้อเช้า: ขนมปังโฮลวีท 150 กรัม → 100 กรัม" in note
    assert "มื้อเช้า: ไข่ไก่ต้ม 2 ฟอง (รวม 100 กรัม) → 1 ฟอง (รวม 50 กรัม)" in note
    assert "มื้อเย็น: ปลาแซลมอน, อบ 100 กรัม → 50 กรัม" in note
    assert "ข้าวสวย" not in note  # unchanged items are not listed
    # 2374.7 + 533 = 2907.7 kcal, 516.7 over the 2391 kcal target
    assert "ประมาณ 2908 kcal เกินเป้า 517 kcal" in note


def test_unchanged_main_meals_give_no_note():
    same = plan([*BEFORE["meals"], meal("มื้อเสริมที่ 1", "supplemental", [item("กล้วย", "100 กรัม")], 90.0)],
                2464.7, extras=1)
    assert main_meal_change_note(BEFORE, same) is None


def test_menu_follow_up_shows_the_note(monkeypatch):
    plans = iter([deepcopy(AFTER), deepcopy(BEFORE)])  # current request first, then the rebuild
    monkeypatch.setattr(chat, "_run_menu_tool", lambda *a, **k: next(plans))
    monkeypatch.setattr(chat, "_append_menu_data_notes", lambda text, results: text)
    events = list(chat._verified_menu_events(
        SimpleNamespace(commit=lambda: None), "ขอเพิ่มเฉพาะมื้อเสริม 1 มื้อ มื้อหลักขอเหมือนเดิม",
        adult(), HISTORY, chat.guardrails.GuardResult(flags=[], matched={}), True,
    ))
    done = next(e for e in events if e["type"] == "done")
    assert "มื้อหลักเปลี่ยนจากเมนูก่อนหน้า" in done["text"]
    assert "ขนมปังโฮลวีท 150 กรัม → 100 กรัม" in done["text"]


def test_no_note_when_the_rebuilt_menu_is_not_the_one_shown(monkeypatch):
    other = plan([meal("มื้อเช้า", "main", [item("ข้าวโอ๊ต", "80 กรัม")], 300.0)], 2300.0)
    plans = iter([deepcopy(AFTER), other])
    monkeypatch.setattr(chat, "_run_menu_tool", lambda *a, **k: next(plans))
    monkeypatch.setattr(chat, "_append_menu_data_notes", lambda text, results: text)
    events = list(chat._verified_menu_events(
        SimpleNamespace(commit=lambda: None), "ขอเพิ่มมื้อเสริม", adult(), HISTORY,
        chat.guardrails.GuardResult(flags=[], matched={}), True,
    ))
    done = next(e for e in events if e["type"] == "done")
    assert "มื้อหลักเปลี่ยน" not in done["text"]


def test_another_menu_set_gives_no_note(monkeypatch):
    plans = iter([deepcopy(AFTER), deepcopy(BEFORE)])
    monkeypatch.setattr(chat, "_run_menu_tool", lambda *a, **k: next(plans))
    monkeypatch.setattr(chat, "_append_menu_data_notes", lambda text, results: text)
    events = list(chat._verified_menu_events(
        SimpleNamespace(commit=lambda: None), "ขอเมนูอีกชุด", adult(), HISTORY,
        chat.guardrails.GuardResult(flags=[], matched={}), True,
    ))
    done = next(e for e in events if e["type"] == "done")
    assert "มื้อหลักเปลี่ยน" not in done["text"]
