"""Say how a follow-up menu changed the main meals the user already saw.

The planner fits the whole day to the target, so adding a snack also resizes
the main meals. On 24 Oct "ขอเพิ่มเฉพาะมื้อเสริม 1 มื้อ มื้อหลักขอเหมือนเดิม"
changed bread 150 -> 100 g and eggs 2 -> 1 without a word. The previous menu is
rebuilt from its recorded tool arguments and compared item by item, so the
note states the real differences and the cost of keeping the old meals.
"""

from __future__ import annotations

MENU_TOOL = "suggest_day_menu"


def previous_menu_call(history: list[dict]) -> tuple[dict, str] | None:
    """Arguments and text of the last menu this chat showed successfully."""
    for turn in reversed(history):
        if turn.get("role") != "assistant":
            continue
        for call in reversed(turn.get("tool_calls") or []):
            if call.get("name") == MENU_TOOL and call.get("status") in {"success", "partial"}:
                return dict(call.get("arguments") or {}), str(turn.get("content") or "")
    return None


def _item_line(item: dict) -> str:
    return f"{item['name_th']}: {item['portion_desc_th']}"


def shown_in(plan: dict, text: str) -> bool:
    """The rebuilt plan is the one the user saw only if every item line matches."""
    lines = [_item_line(i) for m in plan.get("meals") or [] for i in m["items"]]
    return bool(lines) and all(line in text for line in lines)


def _main_meals(plan: dict) -> dict[str, list[dict]]:
    return {m["label_th"]: m["items"] for m in plan.get("meals") or [] if m.get("kind") == "main"}


def main_meal_change_note(previous: dict, current: dict) -> str | None:
    """None when the main meals are unchanged; otherwise list each change."""
    before, after = _main_meals(previous), _main_meals(current)
    changes = []
    for label, old_items in before.items():
        old = {i["name_th"]: i["portion_desc_th"] for i in old_items}
        new = {i["name_th"]: i["portion_desc_th"] for i in after.get(label, [])}
        for name, portion in old.items():
            if name not in new:
                changes.append(f"{label}: เอา{name} ({portion}) ออก")
            elif new[name] != portion:
                changes.append(f"{label}: {name} {portion} → {new[name]}")
        for name, portion in new.items():
            if name not in old:
                changes.append(f"{label}: เพิ่ม{name} {portion}")
    if not changes:
        return None
    added = [m for m in current.get("meals") or []
             if m.get("kind") == "supplemental"
             and m["label_th"] not in {p["label_th"] for p in previous.get("meals") or []}]
    lines = [
        "มื้อหลักเปลี่ยนจากเมนูก่อนหน้า"
        + (" เพราะระบบจัดปริมาณทั้งวันใหม่ให้รวมแล้วยังอยู่ในเป้า:" if added else ":"),
        *("- " + change for change in changes),
    ]
    if added:
        kept = previous["totals"]["kcal"] + sum(m["kcal"] for m in added)
        over = kept - current["targets"]["kcal"]
        lines.append(
            f"ถ้าเก็บมื้อหลักเดิมไว้ทั้งหมดแล้วเพิ่มมื้อเสริมนี้ พลังงานรวมจะประมาณ {kept:.0f} kcal"
            + (f" เกินเป้า {over:.0f} kcal" if over > 0 else "")
        )
    return "\n".join(lines)
