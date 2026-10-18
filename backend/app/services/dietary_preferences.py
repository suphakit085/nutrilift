"""Explicit, user-confirmed dietary settings stored in existing message metadata."""

import hashlib
import json
from pathlib import Path

DIETARY_GROUPS = json.loads(
    Path(__file__).with_name("dietary-options.json").read_text(encoding="utf-8")
)
DIETARY_VALUES = {item["value"] for group in DIETARY_GROUPS for item in group["options"]}
SETTING_TOOL = "set_dietary_preferences"
CLARIFY_TOOL = "clarify_dietary_restrictions"


def confirmed_settings(turn: dict) -> dict | None:
    # Assistant/model output must never rewrite the user's restrictions.
    if turn.get("role") != "user":
        return None
    for call in turn.get("tool_calls") or []:
        if call.get("name") != SETTING_TOOL or call.get("status") != "success":
            continue
        args = call.get("arguments") or {}
        values, saved = args.get("restrictions"), args.get("saved_restrictions")
        if (
            args.get("version") == 1
            and args.get("scope") in {"conversation", "profile"}
            and isinstance(values, list)
            and isinstance(saved, list)
            and len(values) <= 20
            and len(saved) <= 20
            and all(isinstance(v, str) and v.strip() for v in [*values, *saved])
        ):
            return args
    return None


def context_version(saved: list[str], history: list[dict]) -> str:
    data = {"saved": saved, "history": history}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def nut_clarification(restrictions: list[str]) -> str | None:
    if "แพ้ถั่ว" not in restrictions:
        return None
    return (
        "ก่อนจัดเมนู ขอทราบว่าคุณแพ้ถั่วชนิดใดครับ: ถั่วลิสง ถั่วเปลือกแข็ง "
        "ถั่วเหลือง หรือหลายชนิด? ตัวเลือกเดิม “แพ้ถั่ว” ยังไม่แยกชนิด "
        "ระบบจึงยังคงหลีกเลี่ยงถั่วและแหล่งโปรตีนพืชที่ตัวเลือกนี้ครอบคลุม\n\n"
        "กด “ระบุข้อจำกัดอาหาร” เลือกข้อแพ้ที่ทราบทั้งหมด แล้วเลือกใช้เฉพาะห้องนี้ "
        "หรือบันทึกในโปรไฟล์ด้วย หากยังไม่ทราบชนิด ให้คง “แพ้ถั่ว — ยังไม่ระบุชนิด” ไว้ "
        "ระบบจะยังไม่จัดเมนูที่อาจขัดกับข้อแพ้นี้"
    )
