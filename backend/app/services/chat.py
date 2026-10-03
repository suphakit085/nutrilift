"""Chat orchestrator.

One pass over a user message:

    guard-in -> retrieve -> build prompt -> LLM + tool loop (streamed) -> events

The orchestrator is written directly against the Gemini API (``client.models``,
no agent framework) so every step is inspectable and can be described in the
thesis.

``stream_chat`` is a generator of plain dicts. The API layer turns them into SSE;
the evaluation harness consumes the same generator with ``collect_answer``.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from typing import Any

import httpx
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import guardrails, prompts, retrieval
from app.services.foods import all_foods, lookup_food
from app.services.llm import get_client, retry_delay_seconds
from app.services.meal_plan import MealPlanError, build_day_plan
from app.services.nutrition import (
    GOAL_LABELS_TH,
    NutritionInputError,
    ProfileInput,
    calc_nutrition_targets,
    summarize_targets_th,
)
from app.services.thai_text import normalize_thai

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4

#: Per-minute 429s on the generator. gemini-3.5-flash-lite's free tier allows
#: 15 requests/minute across *everyone* using this deployment, so two people
#: sending at once already brushes it - and until 2026-09-15 a single 429 here
#: ended the turn with "โควตาของวันนี้เต็มแล้ว", which was both wrong (the day's
#: quota was fine) and unrecoverable for the user. Retry a couple of times with
#: the delay Google names, capped so a person watching a spinner never waits
#: long; embedding calls in retrieval.py already do the same. A per-*day* 429
#: looks identical on the wire, so the cap is also the bound on wasted waiting
#: when that is what actually happened: at most 2 x 12 s before the daily
#: message shows.
GENERATE_MAX_RETRIES = 2
GENERATE_MAX_DELAY_S = 12.0
#: Google's daily-cap messages sometimes name the window; when they do, do not
#: bother retrying. Best effort only - see the note above.
_PER_DAY_TOKENS = ("per_day", "perday", "per day", "daily")


def rate_limit_retry_delay(exc: Exception) -> float | None:
    """Seconds to wait before retrying ``exc``, or ``None`` if it is not worth it."""
    if getattr(exc, "code", None) != 429:
        return None
    text = str(exc).lower()
    if any(token in text for token in _PER_DAY_TOKENS):
        return None
    return min(retry_delay_seconds(str(exc)), GENERATE_MAX_DELAY_S)


#: Pause before retrying a 503 "model overloaded" - seen live on production
#: and in eval runs, and it usually clears within seconds.
OVERLOADED_RETRY_DELAY_S = 3.0


def transient_retry(exc: Exception, attempt: int) -> tuple[float, str] | None:
    """(delay, message for the user) if ``exc`` is worth one more try, else None.

    Covers the three failures seen on the live system that a second attempt
    fixes: a per-minute 429, a 503 overload, and a stalled connection (the
    read timeout in llm.get_client). A stall only gets one retry - two more
    silent 45 s waits would be worse than the "took too long" message.
    """
    delay = rate_limit_retry_delay(exc)
    if delay is not None:
        return delay, f"โมเดลกำลังคิวแน่น ระบบจะลองใหม่ให้อัตโนมัติใน {delay:.0f} วินาที"
    if isinstance(exc, genai_errors.ServerError) and getattr(exc, "code", None) in (500, 503):
        return OVERLOADED_RETRY_DELAY_S, "ผู้ให้บริการโมเดลขัดข้องชั่วคราว ระบบกำลังลองใหม่ให้อัตโนมัติ"
    if isinstance(exc, httpx.TimeoutException) and attempt == 0:
        return 0.0, "โมเดลตอบช้ากว่าปกติ ระบบกำลังลองใหม่ให้อัตโนมัติ"
    return None


#: Raw JSON schema per tool. Passed to Gemini via ``FunctionDeclaration(
#: parameters_json_schema=...)``, which accepts standard JSON schema directly -
#: no translation needed from the shape used for the previous OpenAI Responses
#: API integration.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "calc_nutrition_targets",
        "description": (
            "คำนวณ BMR, TDEE, พลังงานเป้าหมายต่อวัน และสารอาหารหลัก (โปรตีน/คาร์บ/ไขมัน) "
            "จากโปรไฟล์ของผู้ใช้ ใช้เครื่องมือนี้ทุกครั้งที่ต้องให้ตัวเลขเฉพาะบุคคล ห้ามคำนวณเอง\n"
            "สำคัญมาก: พารามิเตอร์ทุกตัวเป็นค่า 'แทนที่' และเป็นตัวเลือกทั้งหมด "
            "ส่งเฉพาะค่าที่ผู้ใช้ระบุมาในข้อความเท่านั้น (เช่น ผู้ใช้พิมพ์ว่า 'ถ้าผมหนัก 85 กก.' "
            "ให้ส่งเฉพาะ weight_kg=85) ค่าที่ไม่ได้ส่งจะถูกดึงจากโปรไฟล์ให้อัตโนมัติ "
            "ห้ามเดา สมมติ หรือเติมค่าที่ผู้ใช้ไม่ได้บอกโดยเด็ดขาด เพราะจะทำให้ผลลัพธ์ผิด"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "weight_kg": {
                    "type": "number",
                    "description": "ส่งเฉพาะเมื่อผู้ใช้ระบุน้ำหนักอื่นในข้อความ (กก.)",
                },
                "height_cm": {
                    "type": "number",
                    "description": "ส่งเฉพาะเมื่อผู้ใช้ระบุส่วนสูงอื่นในข้อความ (ซม.)",
                },
                "body_fat_pct": {
                    "type": "number",
                    "description": (
                        "ส่งเฉพาะเมื่อผู้ใช้บอกเปอร์เซ็นต์ไขมันมาในข้อความนี้เท่านั้น "
                        "ห้ามเดาหรือใส่ค่าสมมติเด็ดขาด ถ้าผู้ใช้ไม่ได้บอก ให้ละพารามิเตอร์นี้ไป "
                        "ระบบจะใช้สูตร Mifflin-St Jeor ซึ่งไม่ต้องใช้ค่านี้"
                    ),
                },
                "goal": {
                    "type": "string",
                    "enum": ["cut", "bulk", "maintain"],
                    "description": "ส่งเฉพาะเมื่อผู้ใช้ระบุเป้าหมายอื่นในข้อความ",
                },
                "activity_level": {
                    "type": "string",
                    "enum": ["sedentary", "light", "moderate", "active", "very_active"],
                    "description": "ส่งเฉพาะเมื่อผู้ใช้ระบุระดับกิจกรรมอื่นในข้อความ",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "suggest_day_menu",
        "description": (
            "จัดเมนูอาหาร 1 วัน (เช้า/กลางวัน/เย็น/ว่าง) พร้อมปริมาณที่รวมแล้วเข้าใกล้เป้าหมายพลังงานและ"
            "มาโครของผู้ใช้ ใช้เครื่องมือนี้ทุกครั้งที่ผู้ใช้ขอตัวอย่างเมนู ตารางอาหาร หรือ 'ควรกินอะไรบ้าง' "
            "ห้ามแต่งเมนูหรือกะปริมาณเอง เพราะเมนูคือผลรวม ถ้าเดาปริมาณเองตัวเลขรวมจะไม่ตรงกับเป้าหมายที่บอกผู้ใช้ไป "
            "ระบบจะดึงเป้าหมายและข้อจำกัดอาหารจากโปรไฟล์ให้เอง ไม่ต้องส่งมา "
            "ถ้าผู้ใช้ขอเมนูแบบอื่นหรือไม่ชอบเมนูที่ได้ ให้เรียกซ้ำโดยเพิ่ม variant ทีละ 1"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "variant": {
                    "type": "integer",
                    "description": "0 = เมนูชุดแรก เพิ่มทีละ 1 เมื่อผู้ใช้ขอเมนูอื่น",
                    "minimum": 0,
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_food",
        "description": (
            "ค้นหาพลังงานและสารอาหารของเมนูอาหารไทยจากฐานข้อมูล "
            "ใช้ทุกครั้งที่ต้องระบุแคลอรี่หรือมาโครของอาหาร ห้ามตอบจากความจำ "
            "ถ้าผลเป็น partial ให้บอกชื่อที่เสนอและรอผู้ใช้พิมพ์ยืนยันชื่อนั้นในข้อความถัดไป "
            "ห้ามเรียกค้นซ้ำด้วยชื่อที่ระบบเสนอเอง"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "ชื่อเมนูภาษาไทยหรืออังกฤษ เช่น 'ข้าวมันไก่'"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]

_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters_json_schema=schema["parameters"],
            )
            for schema in TOOL_SCHEMAS
        ]
    )
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


#: Numeric override fields where a non-positive value cannot be a real
#: measurement, so it can only mean "the model had nothing to put here".
_POSITIVE_ONLY_FIELDS = ("weight_kg", "height_cm", "body_fat_pct")


def _clean_overrides(args: dict) -> dict:
    """Drop placeholder values the model fills in for optional parameters.

    Models routinely send ``body_fat_pct: 0`` rather than omitting the field.
    Passing that through makes the calculators raise "must be 3-60%", and the
    model then wrongly concludes body fat is required and refuses to answer -
    even though Mifflin-St Jeor needs no such value. Treating a non-positive
    number as absent keeps the fallback path working.
    """
    cleaned = {}
    for key, value in args.items():
        if value is None:
            continue
        if key in _POSITIVE_ONLY_FIELDS and isinstance(value, (int, float)) and value <= 0:
            logger.info("dropping placeholder override %s=%s", key, value)
            continue
        cleaned[key] = value
    return cleaned


def _run_calc_tool(
    profile: ProfileInput | None, args: dict, guard: guardrails.GuardResult | None = None
) -> dict:
    if guard is not None and not guardrails.personalization_allowed(guard):
        return {
            "error": "safety_boundary",
            "message": "ไม่อนุญาตให้คำนวณเป้าหมายเฉพาะบุคคลในบริบทสุขภาพนี้ ให้ส่งต่อผู้ดูแล",
        }
    if profile is None:
        return {
            "error": "no_profile",
            "message": (
                "ผู้ใช้ยังไม่ได้กรอกโปรไฟล์ จึงคำนวณค่าเฉพาะบุคคลไม่ได้ ให้ตอบเป็นหลักการทั่วไปและชวนผู้ใช้ไปกรอกโปรไฟล์"
            ),
        }
    overrides = _clean_overrides(args)
    merged = ProfileInput(
        sex=overrides.get("sex", profile.sex),
        birth_year=profile.birth_year,
        birth_month=profile.birth_month,
        height_cm=overrides.get("height_cm", profile.height_cm),
        weight_kg=overrides.get("weight_kg", profile.weight_kg),
        activity_level=overrides.get("activity_level", profile.activity_level),
        goal=overrides.get("goal", profile.goal),
        body_fat_pct=overrides.get("body_fat_pct", profile.body_fat_pct),
        training_days=profile.training_days,
        restrictions=profile.restrictions,
    )
    try:
        result = calc_nutrition_targets(merged)
    except NutritionInputError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    result["used_overrides"] = overrides or None
    if overrides:
        # Defence in depth: the schema tells the model not to invent inputs, but
        # if it does anyway, force the assumption into the visible answer so the
        # user can catch it instead of trusting a number built on a guess.
        stated = ", ".join(f"{k}={v}" for k, v in sorted(overrides.items()))
        result["disclosure_required"] = (
            f"ตัวเลขนี้คำนวณโดยแทนที่ค่าในโปรไฟล์ด้วย: {stated} "
            "ต้องระบุข้อนี้ให้ผู้ใช้เห็นชัดเจนในคำตอบ และถ้าผู้ใช้ไม่ได้เป็นคนบอกค่าเหล่านี้ "
            "ให้บอกตรง ๆ ว่าเป็นค่าสมมติและถามผู้ใช้เพื่อยืนยัน"
        )
    return result


def _run_menu_tool(
    db: Session,
    profile: ProfileInput | None,
    args: dict,
    guard: guardrails.GuardResult | None = None,
) -> dict:
    """Build a day's menu for the stored profile.

    Targets come from ``calc_nutrition_targets`` rather than from the model, so
    a menu can never be built against numbers the model made up - and a profile
    the calculator rejects (under 18, out-of-range measurements) yields no menu
    at all, the same as it yields no targets.
    """
    if guard is not None and not guardrails.personalization_allowed(guard):
        return {
            "error": "safety_boundary",
            "message": "ไม่อนุญาตให้จัดเมนูเฉพาะบุคคลในบริบทสุขภาพนี้ ให้ส่งต่อผู้ดูแล",
        }
    if profile is None:
        return {
            "error": "no_profile",
            "message": (
                "ยังไม่มีโปรไฟล์ จัดเมนูให้ไม่ได้เพราะไม่รู้เป้าหมายพลังงานและมาโคร ให้ชวนผู้ใช้ไปกรอกโปรไฟล์ก่อน"
            ),
        }
    try:
        targets = calc_nutrition_targets(profile)
    except NutritionInputError as exc:
        return {"error": "invalid_profile", "message": str(exc)}

    try:
        variant = int(args.get("variant") or 0)
    except (TypeError, ValueError):
        variant = 0

    try:
        return build_day_plan(
            all_foods(db),
            {
                "kcal": targets["energy_target_kcal"],
                **{k: targets["macros"][k] for k in ("protein_g", "carb_g", "fat_g")},
            },
            profile.restrictions,
            variant=max(variant, 0),
        )
    except MealPlanError as exc:
        return {"error": "cannot_build_menu", "message": str(exc)}


def _release_connection(db: Session) -> None:
    """End the read-only transaction so the pooled connection goes back.

    Everything this module reads (chunks, foods) is done in autobegun
    transactions that would otherwise stay open - "idle in transaction" - for
    the whole model stream. Measured on the production image: two such
    connections per in-flight chat, against a pool of 15. Nothing here has
    pending writes; the router commits its own rows on its own session.
    """
    try:
        db.commit()
    except Exception:  # pragma: no cover - a failed release must not kill the turn
        logger.exception("could not release DB connection mid-stream")
        db.rollback()


def _execute_tool(
    db: Session,
    profile: ProfileInput | None,
    name: str,
    args: dict,
    guard: guardrails.GuardResult | None = None,
) -> dict:
    if name == "calc_nutrition_targets":
        return _run_calc_tool(profile, args, guard)
    if name == "suggest_day_menu":
        return _run_menu_tool(db, profile, args, guard)
    if name == "lookup_food":
        return lookup_food(db, args.get("query", ""))
    return {"error": "unknown_tool", "message": f"ไม่รู้จักเครื่องมือ {name}"}


def _confirmation_required(query: str, candidates: list[str]) -> dict:
    return {
        "query": query,
        "found": False,
        "match": "confirmation_required",
        "confirmation_required": True,
        "results": [],
        "candidates": candidates,
        "note": (
            "ผู้ใช้ยังไม่ได้ยืนยันชื่ออาหารในข้อความล่าสุด ห้ามค้นชื่อรายการที่เสนอซ้ำหรือรายงานตัวเลข "
            "ให้บอกผู้ใช้ว่าต้องพิมพ์ชื่อรายการที่ต้องการตามตัวเลือกให้ชัดเจนก่อน"
        ),
    }


def _unverified_food_reply(candidates: list[str]) -> str:
    """Fixed no-number reply when the food lookup did not verify a row."""
    if candidates:
        options = "\n".join(f"- {name}" for name in candidates)
        return (
            "ผมยังยืนยันตัวเลขโภชนาการให้ไม่ได้ครับ เพราะชื่อที่พิมพ์มายังไม่ตรงกับรายการในฐานข้อมูล\n\n"
            f"ชื่อที่ใกล้เคียงและพบในฐานข้อมูล:\n{options}\n\n"
            "รายการเหล่านี้อาจเป็นคนละอาหาร กรุณาพิมพ์ชื่อรายการที่ต้องการตามตัวเลือกเพื่อยืนยันก่อนครับ"
        )
    return "ยังไม่พบรายการนี้ในฐานข้อมูลอาหาร จึงยืนยันค่าแคลอรี่หรือสารอาหารให้ไม่ได้ครับ"


def _run_food_lookup(
    db: Session,
    query: str,
    *,
    user_message: str,
    pending_confirmations: list[str],
    partial_candidates_this_turn: list[str],
) -> dict:
    """Only return macros after the user names a suggested row in a later turn.

    A model can call a tool again with its own previous suggestion, so a
    ``found=false`` payload alone is not a confirmation gate. Block all further
    food lookups after a partial match in this turn. Across turns, unlock only
    a candidate that also appears in the current user message.
    """
    candidates = partial_candidates_this_turn or pending_confirmations
    if partial_candidates_this_turn:
        return _confirmation_required(query, candidates)

    normalized_query = normalize_thai(query)
    normalized_user = normalize_thai(user_message)
    for candidate in pending_confirmations:
        normalized_candidate = normalize_thai(candidate)
        if normalized_candidate and normalized_candidate in normalized_query:
            if normalized_candidate not in normalized_user:
                return _confirmation_required(query, pending_confirmations)
            # Use the canonical database name after the user has explicitly
            # repeated it, even if the model included a serving amount as well.
            result = lookup_food(db, candidate)
            if result.get("found"):
                result["confirmation_for"] = candidate
            return result
    result = lookup_food(db, query)
    if result.get("found"):
        # The model can normalize a user's reordered phrase into a canonical
        # database name before its first lookup. Require that canonical name in
        # the actual user message too, or the model has effectively confirmed
        # its own guess without ever returning a partial result.
        normalized_user = normalize_thai(user_message)
        unseen = [
            row["name_th"]
            for row in result.get("results", [])
            if normalize_thai(row.get("name_th") or "") not in normalized_user
        ]
        if unseen:
            return _confirmation_required(query, unseen)
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


#: Matches the contents of any [...] bracket; individual Sn markers are pulled
#: out of that content below. The model sometimes packs several markers into
#: one bracket (e.g. "[S2, S6]") rather than writing "[S2][S6]", so matching
#: a single "S\d{1,2}" per bracket would silently drop every marker after the
#: first.
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_LABEL_TOKEN_RE = re.compile(r"^S\d{1,2}$")

_INTERNAL_REFERENCE_RE = re.compile(
    r"\[(?:ข้อควรระวังเพิ่มเติมสำหรับข้อความนี้|ข้อจำกัดด้านความปลอดภัย)[^\]]*\]"
)


def clean_answer(text: str) -> str:
    """Remove internal labels and scope recency claims to the supplied corpus.

    Retrieval has no live literature search, so it cannot establish that a
    cited study is the latest as of today. Keep the study/date/citation intact.
    """
    cleaned = _INTERNAL_REFERENCE_RE.sub("", text)
    return re.sub(r"(งานวิจัย|งานศึกษา|งานทดลอง|หลักฐาน|บททบทวน)ล่าสุด", r"\1ในชุดข้อมูลนี้", cleaned)


def _food_timeout_reply(results: list[dict]) -> str:
    """Report verified database servings without guessing the requested portion."""
    lines = [
        "โมเดลตอบช้ากว่าปกติ จึงแสดงข้อมูลอาหารจากฐานข้อมูลของระบบให้ก่อนครับ",
        "ค่าด้านล่างเป็นค่าต่อหน่วยเสิร์ฟที่ระบุ ยังไม่ได้ปรับตามปริมาณอื่นที่คุณถาม",
    ]
    for result in results:
        for row in result["results"]:
            lines.append(
                f"- {row['name_th']} — {row['serving_desc']} ({row['serving_g']:g} กรัม): "
                f"พลังงาน {row['kcal']:g} kcal, โปรตีน {row['protein_g']:g} กรัม, "
                f"คาร์โบไฮเดรต {row['carb_g']:g} กรัม, ไขมัน {row['fat_g']:g} กรัม"
            )
            if row.get("estimated"):
                lines.append("รายการนี้เป็นค่าประมาณที่ยังไม่ได้ยืนยัน ไม่ควรใช้ในการนับแคลอรี่อย่างจริงจัง")
            lines.extend(row.get("warnings") or [])
    return "\n\n".join(lines)


def _append_food_data_notes(answer: str, results: list[dict]) -> str:
    """Keep database limitations visible even when the model omits them."""
    notes: dict[str, list[str]] = {}
    for result in results:
        for row in result.get("results") or []:
            warnings = list(row.get("warnings") or [])
            if (row.get("nutrition_meta") or {}).get("carb_definition") == "available":
                warnings.append(
                    "คาร์โบไฮเดรตของรายการนี้เป็นคาร์โบไฮเดรตที่ใช้ได้ แยกจากใยอาหาร ไม่รวมใยอาหารในค่านี้"
                )
            for warning in warnings:
                if warning not in answer:
                    names = notes.setdefault(warning, [])
                    if row["name_th"] not in names:
                        names.append(row["name_th"])
    if not notes:
        return answer
    lines = [answer, "ข้อจำกัดข้อมูลอาหาร"]
    for warning, names in notes.items():
        lines.append("- " + warning + " (รายการ: " + ", ".join(names) + ")")
    return "\n\n".join(lines)


def _menu_reply(plan: dict) -> str:
    """Render calculated portions and totals without model transcription."""
    target = plan["targets"]
    lines = [
        f"ตัวอย่างเมนูอาหาร 1 วัน ชุดที่ {plan.get('variant', 0) + 1} จากฐานข้อมูลอาหารของระบบ",
        (
            f"เป้าหมาย: พลังงาน {target['kcal']:g} kcal, โปรตีน {target['protein_g']:g} กรัม, "
            f"คาร์โบไฮเดรต {target['carb_g']:g} กรัม, ไขมัน {target['fat_g']:g} กรัม"
        ),
        "| มื้ออาหาร | รายการอาหารและปริมาณ | พลังงาน (kcal) | โปรตีน (g) | คาร์บ (g) | ไขมัน (g) |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for meal in plan["meals"]:
        foods = "<br>".join(
            (item["name_th"] + ": " + item["portion_desc_th"]).replace("|", "/")
            for item in meal["items"]
        )
        macros = " | ".join(f"{meal[key]:.1f}" for key in ("kcal", "protein_g", "carb_g", "fat_g"))
        lines.append(f"| {meal['label_th']} | {foods} | {macros} |")
    total = " | ".join(
        f"{plan['totals'][key]:.1f}" for key in ("kcal", "protein_g", "carb_g", "fat_g")
    )
    lines.append(f"| รวมทั้งวัน | | {total} |")
    lines.append("")
    lines.append(
        "สารอาหารรวมอยู่ในเกณฑ์เป้าหมายของระบบ"
        if plan["within_tolerance"]
        else "เมนูนี้ยังเข้าเป้าหมายไม่ครบทุกตัว ดูส่วนต่างด้านล่าง"
    )
    lines.append(
        "รายการนี้เป็นวัตถุดิบและปริมาณ ปรับวิธีปรุงได้ แต่การเพิ่มน้ำมันหรือเครื่องปรุงจะเปลี่ยนตัวเลขจากที่คำนวณไว้"
    )
    return "\n".join(lines)


def _append_menu_data_notes(answer: str, plans: list[dict]) -> str:
    """Report menu limitations independently of the model's wording."""
    warnings: list[str] = []
    for plan in plans:
        rows = [item for meal in plan.get("meals") or [] for item in meal["items"]]
        answer = _append_food_data_notes(answer, [{"results": rows}])
        if any("ใยอาหาร" in warning for warning in plan.get("warnings") or []):
            warnings.append("เมนูนี้มีอาหารที่ยังไม่มีข้อมูลใยอาหารครบ จึงยังยืนยันใยอาหารรวมทั้งวันไม่ได้")
        if not plan.get("within_tolerance", True):
            labels = {
                "kcal": "พลังงาน",
                "protein_g": "โปรตีน",
                "carb_g": "คาร์โบไฮเดรต",
                "fat_g": "ไขมัน",
            }
            for key, delta in (plan.get("deviation_pct") or {}).items():
                tolerance = (plan.get("tolerance_pct") or {}).get(key, 0)
                if key in labels and abs(delta) > tolerance:
                    direction = "เกิน" if delta > 0 else "ขาด"
                    warnings.append(
                        f"เมนูนี้ยังเข้าเป้าไม่ครบ: {labels[key]}{direction} {abs(delta):.1f}%"
                    )
        if plan.get("restrictions_unknown"):
            warnings.append(
                "ระบบยังไม่รองรับข้อจำกัดอาหาร: "
                + ", ".join(plan["restrictions_unknown"])
                + " กรุณาตรวจรายการอาหารก่อนใช้เมนูนี้"
            )
        if any("ขาดองค์ประกอบ" in warning for warning in plan.get("warnings") or []):
            warnings.append("ข้อจำกัดอาหารทำให้บางมื้อมีอาหารไม่ครบกลุ่มที่ใช้จัดเมนู")
        if any("แพ้" in restriction for restriction in plan.get("restrictions_applied") or []):
            warnings.append(
                "การกรองอาหารใช้ชื่อและประเภทในฐานข้อมูล กรุณาตรวจฉลาก ส่วนผสม และการปนเปื้อนของอาหารจริงด้วย"
            )
        if plan.get("disclaimer"):
            warnings.append(plan["disclaimer"])
    missing = [warning for warning in dict.fromkeys(warnings) if warning not in answer]
    if missing:
        answer += "\n\nข้อจำกัดของเมนู\n" + "\n".join("- " + warning for warning in missing)
    return answer


def cited_only(answer_text: str, citations: list[dict]) -> list[dict]:
    """Keep just the passages whose ``[Sn]`` label appears in the answer.

    Labels the model invents that were never retrieved are ignored. Order
    follows the original retrieval ranking, not the order of first mention.
    """
    used: set[str] = set()
    for bracket in _BRACKET_RE.findall(answer_text.upper()):
        for token in re.split(r"[,\s;]+", bracket.strip()):
            if _LABEL_TOKEN_RE.match(token):
                used.add(token)
    return [c for c in citations if c["label"].upper() in used]


OUT_OF_SCOPE_REPLY = """\
ขอโทษครับ คำถามนี้อยู่นอกขอบเขตของระบบ ผมตอบได้เฉพาะเรื่องโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง

เรื่องที่ผมช่วยได้ เช่น
- คำนวณพลังงานและสารอาหารที่ควรได้รับต่อวันจากโปรไฟล์ของคุณ
- ปริมาณโปรตีน คาร์โบไฮเดรต และไขมัน สำหรับช่วงลดไขมันหรือเพิ่มกล้ามเนื้อ
- ช่วงเวลาการกินรอบการฝึก
- อาหารเสริมที่มีหลักฐานรองรับ เช่น เวย์โปรตีน ครีเอทีน คาเฟอีน
- คุณค่าทางโภชนาการของเมนูอาหารไทย
"""


def is_clearly_out_of_scope(guard: guardrails.GuardResult, passages: list) -> bool:
    """True when two independent signals agree the question is off-domain.

    Relying on the prompt alone proved unreliable: with an identical prompt and
    model, the same "write me some Python" question was refused in one
    evaluation run and answered in full in the next. Safety behaviour that
    varies between runs cannot be reported as a property of the system.

    Requiring *both* the keyword rule and weak retrieval keeps this precise. A
    nutrition question that merely trips a keyword still retrieves confident
    context and is answered normally; only a question that is off-domain by
    both measures is refused outright.

    "Weak retrieval" used to mean *empty* retrieval. That stopped working as the
    knowledge base grew: with 26 cards, "วันนี้อากาศเป็นยังไงบ้าง เดี๋ยวจะไปเล่นเวท"
    still pulls the hydration card above the 0.63 gate, so the empty-retrieval
    test could never fire for it (4 of the eval set's 7 off-domain questions
    were in that position on 2026-09-15). The best dense score is now compared
    with ``settings.retrieval_out_of_scope_score`` instead; the retrieval gate
    keeps its own, lower, threshold because it answers a different question.
    """
    if guardrails.Flag.OUT_OF_SCOPE not in guard.flags:
        return False
    if not passages:
        return True
    best = _best_score(passages)
    return best is not None and best < settings.retrieval_out_of_scope_score


def _best_score(passages: list) -> float | None:
    """Highest dense score among retrieved passages (objects or dicts).

    ``None`` when no passage carries a score - callers treat that as confident
    context, so a caller that only knows *whether* something was retrieved
    keeps the pre-2026-09-15 behaviour.
    """
    scores = []
    for p in passages:
        value = p.get("score") if isinstance(p, dict) else getattr(p, "score", None)
        if value is not None:
            scores.append(float(value))
    return max(scores) if scores else None


def _profile_summary_th(profile: ProfileInput | None) -> str | None:
    if profile is None:
        return None
    bf = f", ไขมัน {profile.body_fat_pct}%" if profile.body_fat_pct is not None else ""
    return (
        f"เพศ {'ชาย' if profile.sex == 'male' else 'หญิง'}, อายุ {profile.age()} ปี, "
        f"สูง {profile.height_cm} ซม., หนัก {profile.weight_kg} กก.{bf}, "
        f"เล่นเวท {profile.training_days} วัน/สัปดาห์, "
        f"เป้าหมายที่ตั้งไว้: {GOAL_LABELS_TH.get(profile.goal, profile.goal)}"
        + (f", ข้อจำกัดอาหาร: {', '.join(profile.restrictions)}" if profile.restrictions else "")
    )


def _history_to_contents(history: list[dict]) -> list[types.Content]:
    """Translate the DB's plain ``{role, content}`` history into Gemini turns.

    Only user-visible text round-trips between turns (no replayed tool calls) -
    this is the same simplification the previous OpenAI integration made, since
    the DB only ever stores the final answer text per message, not the
    intermediate tool-call items. Gemini has no "assistant" role, so it maps to
    "model" here.
    """
    contents = []
    for turn in history:
        # An empty part is rejected by the API ("empty text parameter"), and one
        # empty assistant row - a safety-blocked or tool-only final turn - would
        # otherwise poison every later request in that conversation.
        if not (turn.get("content") or "").strip():
            continue
        role = "model" if turn["role"] == "assistant" else "user"
        part = types.Part.from_text(text=turn["content"])
        contents.append(types.Content(role=role, parts=[part]))
    return contents


def _incomplete_answer(text: str) -> bool:
    # A transport-complete stream can contain an unfinished fragment (X03).
    # Short, meaningful replies remain possible; this is not semantic grading.
    cleaned = clean_answer(text).strip()
    visible = re.sub(r"[\s*#`|]+", "", cleaned)
    return len(visible) < 2 or visible in {"ขอ", "ขออภัย", "ครับ", "ค่ะ", "ขอโทษ", "สำหรับ", "ดังนี้"}


def stream_chat(
    db: Session,
    *,
    user_message: str,
    profile: ProfileInput | None = None,
    history: list[dict] | None = None,
    use_rag: bool = True,
    model: str | None = None,
    pending_food_confirmations: list[str] | None = None,
    persistent_safety_flags: list[str] | None = None,
) -> Iterator[dict]:
    """Run one turn. Yields event dicts:

    ``{"type": "sources", "sources": [...]}``   once, before generation
    ``{"type": "delta", "text": "..."}``        many
    ``{"type": "tool", "name": ..., "args": ...}``  when a tool runs
    ``{"type": "retry", "message": ..., "wait_s": n}``  a per-minute 429, retrying
    ``{"type": "done", ...}``                   once, with citations/usage/flags
    ``{"type": "error", "message": ...}``       on failure
    """
    # History is merged straight away so the refusal below sees a risk the user
    # disclosed in an earlier turn - "เป็นโรคไตอยู่" in turn 1 then "กินโปรตีน
    # 200 กรัมได้ไหม" in turn 2 is exactly the case the medical scope rule exists
    # for, and the second message names nothing.
    guard = guardrails.combine(
        guardrails.check(user_message),
        guardrails.check_history(history or [], lookback=None),
        guardrails.from_stored_flags(persistent_safety_flags),
        guardrails.check_profile(profile),
    )

    # Safety precedes retrieval and all model/tool calls, including outages.
    safety = guardrails.safety_reply(guard)
    if safety:
        route, reply = safety
        _release_connection(db)
        yield {"type": "sources", "sources": []}
        yield {"type": "delta", "text": reply}
        yield {
            "type": "done",
            "text": reply,
            "citations": [],
            "retrieved": [],
            "tool_calls": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(),
            "model": "rule:" + route,
            "prompt_version": prompts.PROMPT_VERSION,
            "use_rag": use_rag,
        }
        return

    # Retrieval failure (embedding API down, DB unreachable) must not kill the
    # turn - fall back to answering without context and say so in the prompt.
    passages = []
    if use_rag:
        try:
            passages = retrieval.search(db, user_message)
        except Exception:
            logger.exception("retrieval failed; answering without context")
            use_rag = False
    citations = [p.as_citation() for p in passages]
    _release_connection(db)
    yield {"type": "sources", "sources": citations}

    # Refuse deterministically rather than asking the model to refuse. This also
    # skips the API call, so an off-domain question costs nothing.
    if use_rag and is_clearly_out_of_scope(guard, passages):
        logger.info("refusing out-of-scope question without calling the model")
        for piece in OUT_OF_SCOPE_REPLY.splitlines(keepends=True):
            yield {"type": "delta", "text": piece}
        yield {
            "type": "done",
            "text": OUT_OF_SCOPE_REPLY,
            "citations": [],
            "retrieved": citations,
            "tool_calls": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(),
            "model": "rule:out_of_scope",
            "prompt_version": prompts.PROMPT_VERSION,
            "use_rag": use_rag,
        }
        return

    # Disease, symptoms and medication are out of scope: refused by rule, not
    # left to the model. Deterministic for the same reason the out-of-scope
    # refusal is - a safety boundary that depends on what the model decides this
    # run is not a boundary. Also skips the API call.
    refusal = guardrails.refusal_reply(guard)
    if refusal:
        logger.info("refusing out-of-medical-scope question: %s", guard.as_json())
        for piece in refusal.splitlines(keepends=True):
            yield {"type": "delta", "text": piece}
        yield {
            "type": "done",
            "text": refusal,
            "citations": [],
            "retrieved": citations,
            "tool_calls": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(),
            "model": "rule:medical_scope",
            "prompt_version": prompts.PROMPT_VERSION,
            "use_rag": use_rag,
        }
        return

    targets: dict | None = None
    targets_summary = None
    if profile is not None and guardrails.personalization_allowed(guard):
        try:
            targets = calc_nutrition_targets(profile)
            targets_summary = summarize_targets_th(targets)
        except NutritionInputError:
            logger.warning("stored profile fails validation; skipping targets summary")
    if guardrails.Flag.MINOR in guard.flags:
        # The text said "หนูอายุ 15" but the profile says adult. The MINOR
        # instruction forbids quoting any target while the targets block says
        # "ใช้ตัวเลขนี้ได้เลย"; the model cannot obey both, so the block goes.
        targets_summary = None
    if profile is not None:
        # Profile-derived risk (age, BMI, computed target). The text rules above
        # cannot see any of this - a logged-in minor rarely retypes their age -
        # so it is merged here, after targets exist, and lands in the same
        # guard_instructions / safety_flags as the text rules.
        guard = guardrails.combine(guard, guardrails.check_profile(profile, targets))

    effective_goal = (
        ((targets or {}).get("effective_goal") or (profile.goal if profile else None))
        if guardrails.personalization_allowed(guard)
        else None
    )
    system_prompt = prompts.build_system_prompt(
        profile_summary=_profile_summary_th(profile),
        targets_summary=targets_summary,
        passages=[p.as_dict() for p in passages],
        guard_instructions=guardrails.instructions_for(guard),
        use_rag=use_rag,
        goal=effective_goal,
        sex=profile.sex if profile else None,
        age=profile.age() if profile else None,
    )

    contents = _history_to_contents(history or [])
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

    client = get_client()
    chosen_model = model or settings.llm_model
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=_TOOLS,
        # The SDK's own auto-invoke loop only knows how to call plain Python
        # functions with no access to `db`/`profile`; the manual loop below
        # keeps tool execution in this project's own code, as it did for the
        # previous OpenAI integration.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    text_parts: list[str] = []
    tool_calls_log: list[dict] = []
    partial_candidates_this_turn: list[str] = []
    food_lookup_unverified = False
    food_lookup_candidates: list[str] = []
    tool_chain_active = False
    verified_food_results: list[dict] = []
    verified_menu_results: list[dict] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    finish_reasons: list[str] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            # function_call and text parts arrive in separate stream chunks (a
            # chunk carries a delta, not a full turn); accumulating every
            # chunk's parts is the only way to reconstruct the full model turn
            # for the next iteration's history, since the terminal chunk's
            # parts are near-empty (it only carries finish_reason/usage).
            turn_parts: list[types.Part] = []
            turn_text_parts: list[str] = []
            usage_meta = None
            finish_reason = None
            for attempt in range(GENERATE_MAX_RETRIES + 1):
                streamed = False
                try:
                    for chunk in client.models.generate_content_stream(
                        model=chosen_model, contents=contents, config=config
                    ):
                        if chunk.candidates:
                            reason = getattr(chunk.candidates[0], "finish_reason", None)
                            if reason is not None:
                                finish_reason = getattr(reason, "value", str(reason))
                            candidate_content = chunk.candidates[0].content
                            if candidate_content and candidate_content.parts:
                                turn_parts.extend(candidate_content.parts)
                        if chunk.text:
                            streamed = True
                            turn_text_parts.append(chunk.text)
                        if chunk.usage_metadata:
                            usage_meta = chunk.usage_metadata
                    break
                except (genai_errors.APIError, httpx.TimeoutException) as exc:
                    retry = transient_retry(exc, attempt)
                    # This model turn is buffered: no text has been sent and
                    # no collected function call has executed yet. Discard the
                    # incomplete turn before retrying to avoid duplicate output.
                    if retry is None or attempt >= GENERATE_MAX_RETRIES:
                        if (
                            streamed
                            and turn_text_parts
                            and not any(part.function_call is not None for part in turn_parts)
                            and not tool_chain_active
                        ):
                            partial = clean_answer("".join(turn_text_parts))
                            text_parts.append(partial)
                            yield {"type": "delta", "text": partial}
                            turn_text_parts.clear()
                        raise
                    turn_parts.clear()
                    turn_text_parts.clear()
                    usage_meta = None
                    finish_reason = None
                    delay, notice = retry
                    logger.warning(
                        "generate_content %s, retrying in %.0fs (%d/%d)",
                        type(exc).__name__,
                        delay,
                        attempt + 1,
                        GENERATE_MAX_RETRIES,
                    )
                    yield {"type": "retry", "message": notice, "wait_s": delay}
                    if delay:
                        time.sleep(delay)

            if usage_meta is not None:
                usage_total["input_tokens"] += usage_meta.prompt_token_count or 0
                usage_total["output_tokens"] += usage_meta.candidates_token_count or 0
                usage_total["total_tokens"] += usage_meta.total_token_count or 0

            if turn_parts:
                contents.append(types.Content(role="model", parts=turn_parts))

            function_calls = [p.function_call for p in turn_parts if p.function_call is not None]
            if finish_reason:
                finish_reasons.append(finish_reason)
            if finish_reason not in (None, "STOP") or (
                not function_calls and _incomplete_answer("".join(turn_text_parts))
            ):
                yield {
                    "type": "error",
                    "code": "incomplete_answer",
                    "message": "คำตอบยังไม่สมบูรณ์ กรุณาลองใหม่อีกครั้ง",
                    "finish_reason": finish_reason,
                    "usage": usage_total,
                    "safety_flags": guard.as_json(),
                }
                return
            if not function_calls:
                if not tool_chain_active:
                    answer = clean_answer("".join(turn_text_parts))
                    text_parts.append(answer)
                    yield {"type": "delta", "text": answer}
                elif not food_lookup_unverified:
                    text_parts.extend(turn_text_parts)
                break

            # Buffer text once the model starts a tool chain. If a food lookup
            # cannot verify the row, replace any estimates before they reach
            # the client. Plain text-only answers still stream as they arrive.
            tool_chain_active = True
            response_parts = []
            for call in function_calls:
                args = call.args or {}
                if call.name == "lookup_food":
                    result = _run_food_lookup(
                        db,
                        str(args.get("query") or ""),
                        user_message=user_message,
                        pending_confirmations=pending_food_confirmations or [],
                        partial_candidates_this_turn=partial_candidates_this_turn,
                    )
                else:
                    result = _execute_tool(db, profile, call.name, args, guard)
                if call.name == "lookup_food" and result.get("found"):
                    verified_food_results.append(result)
                if call.name == "suggest_day_menu" and result.get("meals"):
                    verified_menu_results.append(result)
                if call.name == "lookup_food" and result.get("match") in {
                    "partial",
                    "confirmation_required",
                }:
                    for candidate in result.get("candidates") or []:
                        if candidate not in partial_candidates_this_turn:
                            partial_candidates_this_turn.append(candidate)
                if call.name == "lookup_food" and not result.get("found"):
                    food_lookup_unverified = True
                    for candidate in result.get("candidates") or []:
                        if candidate not in food_lookup_candidates:
                            food_lookup_candidates.append(candidate)
                _release_connection(db)
                call_log = {"name": call.name, "arguments": args}
                if call.name == "lookup_food":
                    call_log["lookup_result"] = {
                        "found": bool(result.get("found")),
                        "match": result.get("match"),
                        "confirmation_required": bool(result.get("confirmation_required")),
                        "candidates": result.get("candidates") or [],
                        "confirmation_for": result.get("confirmation_for"),
                    }
                    result.pop("confirmation_for", None)
                tool_calls_log.append(call_log)
                yield {"type": "tool", "name": call.name, "args": args}
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=response_parts))
            # The planner supplies a complete displayable answer. Another model
            # turn can alter portion numbers while keeping the original totals.
            if verified_menu_results and not food_lookup_unverified:
                break
            # This response is already deterministic. A further model call
            # cannot confirm the user's choice and only adds timeout risk.
            if food_lookup_unverified:
                break
            if not food_lookup_unverified:
                text_parts.extend(turn_text_parts)
        else:
            logger.warning("tool loop hit MAX_TOOL_ITERATIONS=%s", MAX_TOOL_ITERATIONS)

    except Exception as exc:
        logger.exception("chat generation failed")
        if (
            isinstance(exc, httpx.TimeoutException)
            and verified_food_results
            and not food_lookup_unverified
            and not guard.flags
            and all(call["name"] == "lookup_food" for call in tool_calls_log)
        ):
            text_parts = [_food_timeout_reply(verified_food_results)]
        else:
            yield {"type": "error", "message": user_facing_error(exc)}
            return

    if tool_chain_active:
        answer_text = (
            _unverified_food_reply(food_lookup_candidates)
            if food_lookup_unverified
            else "\n\n".join(_menu_reply(plan) for plan in verified_menu_results)
            if verified_menu_results
            else clean_answer("".join(text_parts))
        )
        if not food_lookup_unverified:
            answer_text = _append_food_data_notes(answer_text, verified_food_results)
            answer_text = _append_menu_data_notes(answer_text, verified_menu_results)
        if answer_text:
            yield {"type": "delta", "text": answer_text}
    else:
        answer_text = "".join(text_parts)

    yield {
        "type": "done",
        "text": answer_text,
        # Only the passages the answer actually referenced - this is what the UI
        # shows and what groundedness is scored against. Attaching every
        # retrieved passage would credit sources the model never used.
        "citations": cited_only(answer_text, citations),
        # Everything retrieval returned, for hit-rate/MRR in eval/run_eval.py.
        "retrieved": citations,
        "tool_calls": tool_calls_log,
        "usage": usage_total,
        "finish_reasons": finish_reasons,
        "safety_flags": guard.as_json(),
        "model": chosen_model,
        "prompt_version": prompts.PROMPT_VERSION,
        "use_rag": use_rag,
    }


#: Provider failures the user can do something about, mapped to what they should
#: do about it. Anything else falls through to a generic line.
#:
#: The raw exception used to be interpolated straight into the chat bubble, and a
#: 429 put Google's entire error JSON on screen - quota metric names, the model
#: id, rpc type urls, all in English inside a Thai UI (see the 4 ก.ย. 2569 UI
#: walkthrough). None of it is actionable for the person reading it, and the
#: model id and quota shape are ours, not theirs. The detail still goes to the
#: log via logger.exception above.
_ERROR_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("resource_exhausted", "429", "quota"),
        (
            "ตอนนี้ระบบใช้โควตาการตอบของวันนี้เต็มแล้ว ลองใหม่อีกครั้งในภายหลังนะครับ "
            "(คำถามของคุณยังอยู่ ไม่ได้หายไปไหน)"
        ),
    ),
    (("deadline_exceeded", "timeout", "timed out"), "ระบบใช้เวลาตอบนานเกินไป ลองส่งคำถามอีกครั้งนะครับ"),
    (
        ("unauthenticated", "api key", "permission_denied", "401", "403"),
        "ระบบเชื่อมต่อกับผู้ให้บริการโมเดลไม่ได้ กรุณาแจ้งผู้ดูแลระบบครับ",
    ),
    (
        ("unavailable", "503", "500", "internal"),
        "ผู้ให้บริการโมเดลขัดข้องชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่นะครับ",
    ),
)


def user_facing_error(exc: Exception) -> str:
    """A Thai sentence for the chat bubble. Never echoes the provider payload."""
    haystack = f"{type(exc).__name__} {exc}".lower()
    for needles, message in _ERROR_HINTS:
        if any(n in haystack for n in needles):
            return message
    return "เกิดข้อผิดพลาดในการสร้างคำตอบ ลองส่งคำถามอีกครั้งนะครับ หากยังไม่ได้กรุณาแจ้งผู้ดูแลระบบ"


def collect_answer(db: Session, **kwargs) -> dict:
    """Run a turn to completion and return the final ``done`` (or ``error``) event.

    Used by eval/run_eval.py so the harness exercises exactly the same code path
    as the web app.
    """
    last: dict = {"type": "error", "message": "no events produced"}
    for event in stream_chat(db, **kwargs):
        if event["type"] in ("done", "error"):
            last = event
    return last
