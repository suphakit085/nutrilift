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
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import guardrails, prompts, retrieval
from app.services.answer_review import has_answer_content, review_answer, trim_unverified
from app.services.answer_validation import (
    answer_issues,
    repair_instruction,
    without_food_citations,
    without_target_citations,
)
from app.services.calculation_methods import methods_note, target_methods_note
from app.services.creatine_facts import creatine_necessity_reply
from app.services.dietary_preferences import CLARIFY_TOOL, DIETARY_VALUES, nut_clarification
from app.services.food_portions import verified_food_portion_reply
from app.services.food_preparation import food_preparation
from app.services.food_suggestions import suggest_foods, suggestion_reply
from app.services.foods import all_foods, explicit_food_names, lookup_food
from app.services.llm import get_client, retry_delay_seconds
from app.services.macro_math import explicit_macro_energy_reply
from app.services.meal_plan import MealPlanError, plan_day_menu
from app.services.menu_changes import (
    apply_menu_change,
    main_meal_change_note,
    previous_menu_call,
    shown_in,
)
from app.services.menu_context import (
    conversation_profile,
    conversation_restrictions,
    menu_planning_options,
)
from app.services.menu_request import (
    next_menu_variant,
    requests_menu,
    requests_multiple_days,
    requests_single_meal,
    unverified_menu_table,
)
from app.services.nutrition import (
    ACTIVITY_LABELS_TH,
    GOAL_LABELS_TH,
    NutritionInputError,
    ProfileInput,
    calc_nutrition_targets,
    summarize_targets_th,
)
from app.services.personal_context import missing_personal_context_reply
from app.services.profile_reply import explicit_profile_summary_reply
from app.services.protein_facts import explicit_single_meal_absorption_reply
from app.services.protein_split import equal_protein_split_reply, target_split_reply
from app.services.request_understanding import (
    UNDERSTANDING_VERSION,
    RequestUnderstanding,
    interpret_request,
)
from app.services.target_explanation import (
    explicit_target_explanation_reply,
    requests_target_explanation,
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
            "จัดอาหาร 3 มื้อหลักและเสนอหรือเลือกมื้อเสริมตามสารอาหารที่ต้องการ พร้อมปริมาณและ"
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
                },
                "meal_count": {
                    "type": "integer", "minimum": 3, "maximum": 6,
                    "description": "จำนวนรวมที่ผู้ใช้ระบุเท่านั้น ถ้าไม่ระบุให้ระบบเลือกมื้อเสริมเอง",
                },
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
            "message": "ยังจัดเมนูเฉพาะบุคคลในบริบทสุขภาพนี้ไม่ได้ครับ กรุณาปรึกษาแพทย์หรือนักกำหนดอาหารผู้ดูแล",
        }
    if profile is None:
        return {
            "error": "no_profile",
            "message": (
                "ยังไม่มีโปรไฟล์ จึงยังจัดเมนูตามเป้าหมายให้ไม่ได้ครับ "
                "กรุณากรอกโปรไฟล์ก่อนเพื่อคำนวณพลังงานและสารอาหาร"
            ),
        }
    unknown = [r for r in profile.restrictions if r not in DIETARY_VALUES]
    if unknown:
        labels = [r.removeprefix("ข้อจำกัดที่ยังไม่รองรับ:").strip() for r in unknown]
        return {
            "error": "unsupported_menu_constraint",
            "message": (
                "ระบบยังไม่มีตัวกรองที่ตรวจข้อจำกัดนี้ได้: " + ", ".join(labels) + " "
                "ระบบจึงไม่เสนอเมนูที่อาจมีอาหารที่คุณงดหรือแพ้ "
                "ข้อจำกัดที่แจ้งยังคงอยู่ กรุณาให้นักกำหนดอาหารช่วยเลือกอาหารที่เหมาะสมครับ"
            ),
        }
    clarify = nut_clarification(profile.restrictions)
    if clarify:
        return {"error": "ambiguous_allergy", "message": clarify}
    try:
        targets = calc_nutrition_targets(profile)
    except NutritionInputError as exc:
        return {"error": "invalid_profile", "message": str(exc)}

    try:
        variant = int(args.get("variant") or 0)
    except (TypeError, ValueError):
        variant = 0

    try:
        plan = plan_day_menu(
            all_foods(db),
            {
                "kcal": targets["energy_target_kcal"],
                **{k: targets["macros"][k] for k in ("protein_g", "carb_g", "fat_g")},
            },
            profile.restrictions,
            variant=max(variant, 0),
            meal_count=args.get("meal_count"),
            allow_extra_meals=args.get("allow_extra_meals"),
            suggest_extra_meals=args.get("suggest_extra_meals", True),
        )
        plan["target_warnings"] = targets.get("warnings") or []
        plan["calculation_methods"] = targets.get("calculation_methods") or []
        return plan
    except MealPlanError as exc:
        return {"error": "cannot_build_menu", "message": str(exc)}


TRIMMED_NOTE = "ตัดข้อความบางส่วนที่ยังยืนยันกับแหล่งข้อมูลไม่ได้ออกจากคำตอบนี้แล้วครับ"


def _keep_verified_part(
    client, model, question, answer, verdict, passages, understanding, use_rag, usage_total,
    user_context,
):
    """Keep the verified part of an answer whose only defects are unbacked sentences.

    The trimmed text goes through the same deterministic validation and the
    same review again; only a version that passes both, and still says
    something beyond framing or a coverage note, is shown, with a note that
    part of the answer was removed. Anything else keeps the old outcome.
    """
    if verdict is None:
        return None
    trimmed = trim_unverified(answer, verdict)
    if trimmed is None:
        return None
    text, removed = trimmed
    source = [p.as_dict() for p in passages]
    if answer_issues(question, text, source, use_rag=use_rag, understanding=understanding):
        return None
    try:
        recheck, more = review_answer(
            client, model=model, question=question, draft=text, passages=source,
            understanding=understanding, user_context=user_context,
        )
    except Exception as exc:
        logger.warning("trimmed answer review failed: %s", type(exc).__name__)
        return None
    for key, value in more.items():
        usage_total[key] += value
    if recheck.issues or not has_answer_content(recheck):
        return None
    for raw, edited in recheck.label_edits:
        if text.count(raw) == 1:
            text = text.replace(raw, edited)
    return f"{text}\n\n{TRIMMED_NOTE}", removed


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


def _tool_status(name: str, result: dict) -> str | None:
    """Outcome belongs to the application, never to the model or stream state."""
    if name == "suggest_day_menu" and result.get("error") == "ambiguous_allergy":
        return "confirmation_required"
    if result.get("error"):
        return "error"
    if name == "suggest_day_menu":
        if not result.get("meals"):
            return "error"
        return "success" if (result.get("within_tolerance")
                             and result.get("budget_status") != "not_calculated") else "partial"
    if name == "lookup_food":
        if result.get("found"):
            return "success"
        if result.get("match") in {"partial", "confirmation_required"}:
            return "confirmation_required"
        return "not_found"
    if name == "calc_nutrition_targets":
        return "success"
    return None


def _run_food_lookup(
    db: Session,
    query: str,
    *,
    user_message: str,
    pending_confirmations: list[str],
    partial_candidates_this_turn: list[str],
    earlier_user_messages: Sequence[str] = (),
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
    if result.get("match") == "partial" and any(
        normalize_thai(name) in normalized_user for name in result.get("candidates", [])
    ):
        # The user may already have supplied the full table name while the
        # model removed its comma. Only one explicit, non-negated food may
        # resolve this; names proposed by the assistant cannot do so.
        explicit = explicit_food_names(db, user_message)
        if len(explicit) == 1 and explicit[0] in result.get("candidates", []):
            confirmed = lookup_food(db, explicit[0])
            if confirmed.get("found") and len(confirmed.get("results", [])) == 1:
                result = confirmed
    if result.get("found"):
        # The model can normalize a user's reordered phrase into a canonical
        # database name before its first lookup. Require that canonical name in
        # the actual user message too, or the model has effectively confirmed
        # its own guess without ever returning a partial result.
        normalized_user = normalize_thai(user_message)
        # A name the user typed in an earlier turn of this chat is the user's
        # own food, so a follow-up such as "ถ้ากินครึ่งจานล่ะ" needs no second
        # confirmation (23 Oct retest). Only user turns count: an assistant
        # suggestion still has to be repeated by the user.
        normalized_user += "".join(" " + normalize_thai(m) for m in earlier_user_messages)
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
_CITATION_MARKER_RE = re.compile(r"\[S\d{1,2}(?:[\s,;]+S\d{1,2})*\](?!\()", re.I)
_APP_INSTRUCTION_RE = re.compile(
    r"(?:ไป|เข้า|เปิด|กลับ).{0,25}(?:หน้า|เมนู).{0,15}โปรไฟล์|"
    r"หน้า\s*[\s*\"“”]*โปรไฟล์ของฉัน|"
    r"(?:กด|คลิก|แตะ|เลือก).{0,30}บันทึกและคำนวณ|"
    r"(?:กรอก|บันทึก|แก้ไข|อัปเดต).{0,25}(?:ข้อมูลใน)?โปรไฟล์|"
    r"กรอกข้อมูลส่วนตัว|"
    r"(?:ยัง)?(?:ไม่ได้|ยังไม่|ไม่มี|ยังไม่มี).{0,30}(?:กรอก|บันทึก).{0,25}(?:ข้อมูล|โปรไฟล์)|"
    r"(?:เมื่อ|หลังจาก).{0,30}(?:บันทึก|กรอก).{0,30}(?:ระบบ|แอป).{0,30}(?:คำนวณ|จัดเมนู)|"
    r"กลับ.{0,20}(?:แชต|พิมพ์|ถามใหม่|ขอ(?:ตัวอย่าง)?เมนู)|"
    r"(?:go to|open|visit).{0,25}(?:profile page|my profile)|"
    r"(?:click|press|tap).{0,25}save and calculate",
    re.I,
)


def _without_navigation_citations(text: str) -> str:
    """Publications cannot substantiate UI instructions.

    Inspect each cited claim rather than deleting every citation in a mixed
    paragraph. Earlier cited nutrition claims and Markdown links stay intact.
    """
    previous_end = 0
    navigation = False

    def keep_claim(match: re.Match) -> str:
        nonlocal previous_end, navigation
        claim = text[previous_end:match.start()]
        previous_end = match.end()
        # A new sentence/line can return to a research claim after instructions.
        if claim.strip():
            claim = claim.split("\n\n")[-1]
            # Numbered steps share their trailing citation. A step's "4. "
            # is not a sentence boundary, and a final "return to chat" step
            # does not turn the preceding UI list into a research claim.
            if not re.search(r"(?m)^\s*\d+[.)]\s", claim):
                claim = re.split(r"\n|(?<=[.!?])\s+", claim)[-1]
            navigation = bool(_APP_INSTRUCTION_RE.search(claim))
        return "" if navigation else match.group(0)

    return _CITATION_MARKER_RE.sub(keep_claim, text)


def clean_answer(text: str, citations: list[dict] | None = None) -> str:
    """Remove internal labels and scope recency claims to the supplied corpus.

    Retrieval has no live literature search, so it cannot establish that a
    cited study is the latest as of today. Keep the study/date/citation intact.
    """
    cleaned = _INTERNAL_REFERENCE_RE.sub("", text)
    # Translate the observed unit contamination, preserving its number/source.
    cleaned = cleaned.replace("किलोग्राम", "กิโลกรัม").replace("ग्राम", "กรัม")
    # Oxidation is not excretion. Correct the observed mistranslation without
    # changing the study's dose, endpoint, or citation.
    cleaned = cleaned.replace(
        "การเผาผลาญกรดอะมิโนเพื่อเป็นพลังงานหรือขับออก", "การออกซิไดซ์กรดอะมิโน"
    )
    allowed = None if citations is None else {c["label"].upper() for c in citations}

    def keep_citation_or_link(match: re.Match) -> str:
        if cleaned[match.end():].startswith("("):
            return match.group(0)  # Ordinary Markdown links remain readable.
        tokens = re.split(r"[\s,;]+", match.group(1).strip().upper())
        if not all(_LABEL_TOKEN_RE.fullmatch(t) for t in tokens):
            return ""
        if allowed is None:
            return match.group(0)
        supported = list(dict.fromkeys(t for t in tokens if t in allowed))
        return "[" + ", ".join(supported) + "]" if supported else ""

    cleaned = _BRACKET_RE.sub(keep_citation_or_link, cleaned)
    cleaned = _without_navigation_citations(cleaned)
    # Publication labels cannot establish application state or calculator policy.
    # Inspect the claim immediately before each marker. A calculator result and
    # a supported research claim can share a paragraph or Markdown bullet list.
    # Removing all markers in that paragraph erased the research claim's source.
    operational = re.compile(
        r"กติกาของ(?:เครื่องคำนวณ)?(?:ระบบ|โครงการ)|โครงการมีกติกา|"
        r"กติกา.{0,35}(?:ระบบ|โครงการ)|"
        r"ข้อกำหนดของเครื่องคำนวณ|"
        r"ติดตาม.{0,35}2[-\u2013]4\s*สัปดาห์|"
        r"(?:ไม่ได้|ไม่มีการ|ไม่)เปลี่ยน(?:แปลง)?(?:ข้อมูลใน)?โปรไฟล์|"
        r"ฐานข้อมูล.{0,45}(?:ยังไม่มี|ไม่มีข้อมูล|ไม่พบ)"
    )
    calculated_energy = re.compile(
        r"^\s*(?:[-•]\s*|\d+[.)]\s*)?พลังงานเป้าหมาย"
        r"(?:จากโปรไฟล์|ของคุณ|ที่ระบบคำนวณได้)?\s*(?::|คือ|เท่ากับ|อยู่ที่)?\s*\d"
    )
    previous_end = 0
    is_operational = False

    def keep_claim(match: re.Match) -> str:
        nonlocal previous_end, is_operational
        claim = cleaned[previous_end:match.start()]
        previous_end = match.end()
        if claim.strip():
            claims = [part for part in re.split(r"\n|(?<=[.!?;])\s+", claim) if part.strip()]
            claim = (claims[-1] if claims else claim).replace("*", "")
            is_operational = bool(operational.search(claim) or calculated_energy.search(claim))
        return "" if is_operational else match.group(0)

    cleaned = _CITATION_MARKER_RE.sub(keep_claim, cleaned)
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
    if plan.get("conversation_note"):
        lines.insert(1, plan["conversation_note"])
    if plan.get("budget_note"):
        lines.insert(1, plan["budget_note"])
    if "main_meal_count" in plan:
        extras = plan.get("supplemental_meal_count", 0)
        structure = f"{plan['main_meal_count']} มื้อหลัก"
        if extras:
            structure += f" + {extras} มื้อเสริม"
        lines.insert(1, structure)
    if plan.get("target_warnings"):
        lines = [
            "### ข้อควรทราบก่อนใช้เมนู",
            *["- " + warning for warning in dict.fromkeys(plan["target_warnings"])],
            "", *lines,
        ]
    for meal in plan["meals"]:
        foods = "<br>".join(
            (item["name_th"] + ": " + item["portion_desc_th"] + " — "
             + (item.get("preparation") or food_preparation(item))["label_th"]).replace("|", "/")
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
    lines.append(
        "ชั่งส่วนที่กินได้ตามสถานะที่ระบุในแต่ละรายการ ไม่เทียบน้ำหนักดิบกับสุกโดยตรง "
        "รายการที่ข้อมูลไม่ระบุดิบ/สุกยังแปลงน้ำหนักหลังปรุงให้ไม่ได้"
    )
    for option in plan.get("extra_meal_options") or []:
        lines.extend([
            "",
            (f"ทางเลือกที่คำนวณแล้วเข้าเกณฑ์: 3 มื้อหลัก + {option['supplemental_meal_count']} มื้อเสริม "
             f"รวมประมาณ {option['totals']['kcal']:.0f} kcal ต่อวัน"),
            ("หากต้องการลองแผนนี้ พิมพ์ว่า เพิ่มมื้อเสริมได้ ระบบจะจัดปริมาณทั้งแผนใหม่ "
             "ตัวเลือกนี้ยังไม่ได้รวมอยู่ในตารางและยอดรวมด้านบน"),
        ])
    return "\n".join(lines) + methods_note(plan.get("calculation_methods"))


def _append_menu_data_notes(answer: str, plans: list[dict]) -> str:
    """Report menu limitations independently of the model's wording."""
    warnings: list[str] = []
    for plan in plans:
        warnings.extend(plan.get("target_warnings") or [])
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
                if key in labels and (key in plan.get("out_of_tolerance", [])
                                      or abs(delta) > tolerance):
                    direction = "เกิน" if delta > 0 else "ขาด"
                    warnings.append(
                        f"เมนูนี้ยังเข้าเป้าไม่ครบ: {labels[key]}{direction} {abs(delta):.1f}%"
                    )
        practicality = plan.get("practicality") or {}
        if practicality and not plan.get("within_tolerance", True):
            warnings.append("ยังไม่พบแผนที่เข้าเป้าครบภายใต้รายการอาหารและปริมาณนี้ ลองขอเมนูอีกแบบได้")
        if practicality.get("meal_weights_within_preference") is False:
            warnings.append("บางมื้อมีน้ำหนักอาหารรวมมากกว่าช่วงตัวอย่างของระบบ ควรกระจายไปมื้ออื่น")
        if practicality.get("meal_balance_within_preference") is False:
            warnings.append("พลังงานหรือโปรตีนยังกระจายระหว่างมื้อไม่สม่ำเสมอตามเกณฑ์ตัวอย่างของระบบ")
        if practicality.get("review_status") == "pending_dietitian_review":
            warnings.append("ช่วงปริมาณอาหารเป็นเกณฑ์ตัวอย่างของระบบ ยังไม่ได้รับการทบทวนโดยนักกำหนดอาหาร")
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
    for match in _BRACKET_RE.finditer(answer_text.upper()):
        if answer_text[match.end():].startswith("("):
            continue
        tokens = re.split(r"[,\s;]+", match.group(1).strip())
        if all(_LABEL_TOKEN_RE.fullmatch(token) for token in tokens):
            used.update(tokens)
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


def _reference_question(message: str) -> bool:
    """Keep study interpretation separate from a requested personal plan."""
    text = normalize_thai(message)
    reference = re.search(
        r"งานวิจัย|งานศึกษา|งานทดลอง|งานทบทวน|บททบทวน|หลักฐาน|พิสูจน์|"
        r"meta.analysis|helms|issn|dri|ธงโภชนาการ|crude\s*fib|"
        r"ทุกแบบ|ทุกกรณี|ข้อสรุป|พอสรุป|\beaa\b", text, re.I,
    )
    personal = re.search(
        normalize_thai(
            r"(?:ของ|สำหรับ)(?:ผม|ฉัน|ดิฉัน|ตัวเอง)|(?:จาก|ตาม)โปรไฟล์|"
            r"(?:จัด|ขอ|ช่วย).{0,12}เมนู|คำนวณ(?:เป้า|แคล|พลังงาน|รักษาน้ำหนัก)"
        ), text,
    )
    return bool(reference and not personal)


def _database_food_request(message: str) -> bool:
    """An explicit portion lookup must consult foods before reporting absence."""
    text = normalize_thai(message)
    return bool(
        "ฐานข้อมูล" in text
        and re.search(r"\d+(?:\.\d+)?\s*(?:กรัม|มล\.?|ml\b|g\b)", text, re.I)
        and re.search(r"แคล|พลังงาน|โปรตีน|สารอาหาร", text)
        and not _reference_question(message)
        and not re.search(r"เมนู.{0,12}(?:วัน|ชุด)|ตารางอาหาร", text)
    )


def _personal_context_requested(message: str) -> bool:
    """Only expose personal targets when the current question needs them."""
    return bool(re.search(normalize_thai(
        r"ผม|ฉัน|ดิฉัน|ตัวเอง|โปรไฟล์|เป้า(?:หมาย)?|เมนู|ตารางอาหาร|"
        r"(?:ควร|ต้อง|ให้)(?:กิน|ทาน)|กี่(?:แคล|กรัม)|my\b"
    ), normalize_thai(message), re.I))


def _profile_summary_th(profile: ProfileInput | None) -> str | None:
    if profile is None:
        return None
    bf = f", ไขมัน {profile.body_fat_pct}%" if profile.body_fat_pct is not None else ""
    return (
        f"เพศ {'ชาย' if profile.sex == 'male' else 'หญิง'}, อายุ {profile.age()} ปี, "
        f"สูง {profile.height_cm} ซม., หนัก {profile.weight_kg} กก.{bf}, "
        f"ระดับกิจกรรม: {ACTIVITY_LABELS_TH.get(profile.activity_level, profile.activity_level)}, "
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


def _dietary_question_events(
    restrictions: list[str], guard: guardrails.GuardResult, use_rag: bool,
    *, include_sources: bool = True,
) -> Iterator[dict]:
    answer = nut_clarification(restrictions)
    if include_sources:
        yield {"type": "sources", "sources": [], "retrieval_status": "not_required"}
    yield {"type": "tool", "name": CLARIFY_TOOL, "status": "confirmation_required"}
    yield {"type": "delta", "text": answer}
    yield {
        "type": "done", "text": answer, "citations": [], "retrieved": [],
        "tool_calls": [{"name": CLARIFY_TOOL, "status": "confirmation_required"}],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "safety_flags": guard.as_json(), "model": "rule:dietary_clarification",
        "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
    }


def _main_meal_change(
    db: Session, profile: ProfileInput | None, history: list[dict],
    guard: guardrails.GuardResult, current: dict, current_args: dict,
) -> str | None:
    """Compare with the previous menu of this chat, rebuilt from its own arguments."""
    previous = previous_menu_call(history)
    if previous is None:
        return None
    args, shown = previous
    if args.get("variant", 0) != current_args.get("variant", 0):
        return None  # A different set was asked for; its items are meant to differ.
    try:
        rebuilt = _run_menu_tool(db, profile, args, guard)
    except Exception:
        logger.warning("previous menu could not be rebuilt for comparison")
        return None
    if not rebuilt.get("meals") or not shown_in(rebuilt, shown):
        # Profile or restrictions changed since: the rebuilt plan is not the
        # one the user saw, so no item-level claim is made.
        return None
    return main_meal_change_note(rebuilt, current)


def _food_suggestion_events(
    db: Session, suggestion, profile: ProfileInput | None, history: list[dict],
    message: str, guard: guardrails.GuardResult, use_rag: bool,
) -> Iterator[dict]:
    """List foods from the food database; values are never model-written."""
    saved = conversation_restrictions(
        profile, [*history, {"role": "user", "content": message}],
    ) if profile is not None else []
    if nut_clarification(saved):
        yield from _dietary_question_events(saved, guard, use_rag)
        return
    request_only = [r for r in suggestion.exclude if r not in saved]
    restrictions = [*saved, *request_only]
    unknown = [r for r in restrictions if r not in DIETARY_VALUES]
    if unknown:
        answer = ("ยังคัดอาหารตามข้อจำกัดนี้จากฐานข้อมูลไม่ได้ครับ: "
                  + ", ".join(r.removeprefix("ข้อจำกัดที่ยังไม่รองรับ:").strip() for r in unknown))
        items = []
    else:
        items = suggest_foods(all_foods(db), suggestion.focus, restrictions, suggestion.count)
        answer = suggestion_reply(items, suggestion.focus, suggestion.count, restrictions,
                                  request_only)
    _release_connection(db)
    args = {"focus": suggestion.focus, "count": suggestion.count, "restrictions": restrictions}
    status = "success" if items else "error"
    yield {"type": "sources", "sources": [], "retrieval_status": "not_required"}
    yield {"type": "tool", "name": "suggest_foods", "args": args, "status": status}
    yield {"type": "delta", "text": answer}
    yield {
        "type": "done", "text": answer, "citations": [], "retrieved": [],
        "tool_calls": [{"name": "suggest_foods", "arguments": args, "status": status}],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "safety_flags": guard.as_json(), "model": "rule:food_suggestion",
        "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
    }


def _verified_menu_events(
    db: Session, message: str, profile: ProfileInput | None,
    history: list[dict], guard: guardrails.GuardResult, use_rag: bool,
    understanding: RequestUnderstanding | None = None,
) -> Iterator[dict]:
    """Execute a requested operation on the server; no model transcription."""
    yield {"type": "sources", "sources": [], "retrieval_status": "not_required"}
    clarification = missing_personal_context_reply(
        message, history, has_profile=profile is not None,
    )
    calls = []
    try:
        if clarification:
            answer = clarification
        else:
            effective, note = conversation_profile(profile, history, message, understanding)
            if effective is not None and nut_clarification(effective.restrictions):
                yield from _dietary_question_events(
                    effective.restrictions, guard, use_rag, include_sources=False,
                )
                return
            if effective is not None:
                try:
                    targets = calc_nutrition_targets(effective)
                except NutritionInputError:
                    targets = None  # The menu tool returns the validation message.
                guard = guardrails.combine(guard, guardrails.check_profile(effective, targets))
            args = {"variant": next_menu_variant(message, history),
                    **menu_planning_options(history, message)}
            if understanding is not None and understanding.menu_change is not None:
                args = apply_menu_change(args, understanding.menu_change, history)
            if requests_multiple_days(message):
                result = {"error": "unsupported_period", "message": (
                    "ตอนนี้ระบบจัดเมนูได้ครั้งละ 1 วันครับ ยังไม่จัดแผนหลายวันให้ครบ "
                    "กรุณาขอเมนูสำหรับหนึ่งวันก่อน แล้วขออีกชุดสำหรับวันถัดไปได้ครับ"
                )}
            elif requests_single_meal(message):
                result = {"error": "unsupported_single_meal", "message": (
                    "ตอนนี้ระบบคำนวณเป็นแผนอาหารหนึ่งวัน ยังไม่จัดเฉพาะมื้อเดี่ยวครับ "
                    "กรุณาขอแผนหนึ่งวัน 3 ถึง 6 มื้อ เพื่อดูปริมาณและสารอาหารแยกรายมื้อ"
                )}
            else:
                result = _run_menu_tool(db, effective, args, guard)
            if result.get("meals"):
                change = _main_meal_change(db, effective, history, guard, result, args)
                note = "\n".join(n for n in [change, note] if n)
                if note:
                    result["conversation_note"] = note
                if re.search("งบ|ราคา|บาท", "\n".join([
                    *(t.get("content", "") for t in history if t.get("role") == "user"),
                    message,
                ])):
                    result["budget_note"] = (
                        "เมนูนี้คำนวณเฉพาะพลังงานและสารอาหาร ยังไม่ได้คำนวณราคา"
                        "หรือยืนยันว่าอยู่ในงบที่แจ้ง กรุณาตรวจราคาจริงก่อนเลือกซื้อ"
                    )
                    result["budget_status"] = "not_calculated"
                answer = _append_menu_data_notes(_menu_reply(result), [result])
            else:
                answer = result.get("message") or "ยังจัดเมนูตามข้อจำกัดนี้ไม่ได้ครับ"
            status = _tool_status("suggest_day_menu", result)
            calls = [{"name": "suggest_day_menu", "arguments": args, "status": status}]
            _release_connection(db)
            yield {"type": "tool", "name": "suggest_day_menu", "args": args, "status": status}
    except Exception as exc:
        logger.exception("verified menu execution failed")
        _release_connection(db)
        yield {"type": "error", "message": user_facing_error(exc)}
        return
    _release_connection(db)
    yield {"type": "delta", "text": answer}
    yield {
        "type": "done", "text": answer, "citations": [], "retrieved": [],
        "tool_calls": calls, "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "safety_flags": guard.as_json(),
        "model": "rule:missing_personal_context" if clarification else "rule:verified_menu",
        "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
    }


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
    menu_history: list[dict] | None = None,
    understanding: RequestUnderstanding | None = None,
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
    if understanding and understanding.medical_self_context:
        guard = guardrails.combine(guard, guardrails.GuardResult(
            flags=[guardrails.Flag.MEDICAL], matched={"medical_condition": ["semantic_context"]},
        ))
    if understanding and profile is not None:
        interpreted_profile, _ = conversation_profile(
            profile, menu_history if menu_history is not None else (history or []),
            user_message, understanding,
        )
        guard = guardrails.combine(guard, guardrails.check_profile(interpreted_profile))
    elif understanding:
        guard = guardrails.combine(guard, guardrails.check_stated_measurements(
            understanding.weight_kg.value if understanding.weight_kg else None,
            understanding.height_cm.value if understanding.height_cm else None,
            understanding.goal,
        ))

    # Safety precedes retrieval and all model/tool calls, including outages.
    safety = guardrails.safety_reply(guard)
    if safety is None:
        refusal = guardrails.refusal_reply(guard)
        if refusal:
            safety = ("medical_scope", refusal)
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

    operation_history = menu_history if menu_history is not None else (history or [])
    if understanding:
        if understanding.task == "clarify":
            reply = {
                "pair_partner": PAIR_CLARIFICATION,
                "profile": ("กรุณากรอกและบันทึกข้อมูลในหน้าโปรไฟล์ก่อนครับ "
                            "ระบบจึงจะใช้ข้อมูลครบสำหรับคำนวณเป้าหมายเฉพาะบุคคลได้"),
                "food_quantity": "เป็นอาหารหรือผลิตภัณฑ์ใด และปริมาณที่กินกี่กรัมหรือกี่หน่วยครับ",
                "training_schedule": "คุณเริ่มและเลิกฝึกกี่โมง และกินมื้อก่อนฝึกเวลาใดครับ",
                "budget": ("งบอาหารกี่บาทต่อวันหรือต่อมื้อครับ ฐานข้อมูลยังไม่มีราคาอาหาร "
                           "จึงต้องตรวจราคาจริงก่อนยืนยันว่าอยู่ในงบ"),
                "goal": "ตอนนี้ต้องการลดไขมัน เพิ่มกล้ามเนื้อ หรือรักษาน้ำหนักครับ",
                "allergy_type": "แพ้อาหารหรือส่วนประกอบชนิดใดบ้างครับ กรุณาระบุให้ครบก่อนจัดเมนู",
                "other": "ช่วยระบุสิ่งที่ต้องการทราบหรือรายละเอียดที่ยังไม่ได้แจ้งเพิ่มเติมครับ",
            }[understanding.missing_information]
            yield from _understanding_reply(reply, guard, use_rag, "missing_information")
            return
        if understanding.task == "calculate_targets" and profile is None:
            reply = ("ยังไม่มีข้อมูลเพียงพอสำหรับคำนวณเป้าหมายของคุณครับ "
                     "กรุณากรอกและบันทึกเพศ ปีและเดือนเกิด ส่วนสูง น้ำหนัก ระดับกิจกรรม "
                     "และเป้าหมายในหน้าโปรไฟล์ก่อน เปอร์เซ็นต์ไขมันเป็นข้อมูลเสริม")
            yield from _understanding_reply(reply, guard, use_rag, "missing_personal_context")
            return
    if re.search(r"แพ้ถั่ว(?!ลิสง|เหลือง|เปลือกแข็ง)", normalize_thai(user_message)):
        restrictions = conversation_restrictions(
            profile, [*operation_history, {"role": "user", "content": user_message}],
        )
        if nut_clarification(restrictions):
            yield from _dietary_question_events(restrictions, guard, use_rag)
            return
    suggestion = understanding.food_suggestion if understanding else None
    if suggestion is not None and suggestion.listable:
        yield from _food_suggestion_events(
            db, suggestion, profile, operation_history, user_message, guard, use_rag,
        )
        return
    menu_requested = (understanding.task == "plan_menu" if understanding
                      else requests_menu(user_message, operation_history))
    if (understanding is not None and understanding.menu_change is not None
            and previous_menu_call(operation_history) is not None):
        menu_requested = True  # A change to the menu shown is a menu operation.
    if menu_requested:
        yield from _verified_menu_events(
            db, user_message, profile, operation_history, guard, use_rag, understanding,
        )
        return

    # Formula/provenance questions use the actual calculator payload. Primary
    # links are scoped in the reply, not fabricated as retrieved S passages.
    target_requested = (understanding.task == "calculate_targets" if understanding
                        else requests_target_explanation(user_message))
    meal_split = understanding.meal_split if understanding else None
    if meal_split is not None:
        # "แล้วถ้ากิน 4 มื้อ มื้อละกี่กรัม" after a target answer was read as
        # calculate_targets in 2 of 3 runs and got the whole-day block again
        # (24 Oct). A grounded per-meal reading takes the division route below.
        target_requested = False
    if target_requested and guardrails.personalization_allowed(guard):
        effective_profile, context_note = conversation_profile(
            profile, operation_history, user_message, understanding,
        )
        if effective_profile is not None:
            try:
                explanation_targets = calc_nutrition_targets(effective_profile)
                explanation = explicit_target_explanation_reply(
                    user_message, explanation_targets, context_note, requested=target_requested,
                )
            except NutritionInputError:
                explanation = None
            if explanation:
                guard = guardrails.combine(
                    guard, guardrails.check_profile(effective_profile, explanation_targets),
                )
                _release_connection(db)
                yield {"type": "sources", "sources": [], "retrieval_status": "not_required"}
                yield {"type": "delta", "text": explanation}
                yield {
                    "type": "done", "text": explanation, "citations": [], "retrieved": [],
                    "tool_calls": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    "safety_flags": guard.as_json(), "model": "rule:target_explanation",
                    "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
                }
                return

    # Retrieval failure (embedding API down, DB unreachable) must not kill the
    # turn - fall back to answering without context and say so in the prompt.
    passages = []
    retrieval_status = "disabled"
    if use_rag:
        try:
            passages = retrieval.search(db, user_message)
            previous = next((t.get("content", "") for t in reversed(history or [])
                             if t.get("role") == "user"), "")
            if not passages and previous:
                # A short follow-up ("แล้วต้องโหลดไหมครับ") names no topic of
                # its own; searching it alone found nothing and the prompt then
                # said the knowledge base did not cover a topic it does cover
                # (23 Oct production test). The domain gate still applies.
                passages = retrieval.search(db, f"{previous}\n{user_message}")
            retrieval_status = "ready" if passages else "empty"
        except Exception:
            logger.exception("retrieval failed; answering without context")
            use_rag = False
            retrieval_status = "unavailable"
    citations = [p.as_citation() for p in passages]
    _release_connection(db)
    yield {"type": "sources", "sources": citations, "retrieval_status": retrieval_status}

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

    clarification = None if understanding else missing_personal_context_reply(
        user_message, menu_history or history or [], has_profile=profile is not None,
    )
    if clarification:
        yield {"type": "delta", "text": clarification}
        yield {
            "type": "done", "text": clarification, "citations": [], "retrieved": citations,
            "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(), "model": "rule:missing_personal_context",
            "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
        }
        return

    necessity = creatine_necessity_reply(
        user_message, [p.as_dict() for p in passages], understanding,
    )
    if necessity:
        yield {"type": "delta", "text": necessity}
        yield {
            "type": "done", "text": necessity,
            "citations": cited_only(necessity, citations), "retrieved": citations,
            "tool_calls": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(), "model": "rule:creatine_necessity",
            "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
        }
        return

    absorption_reply = explicit_single_meal_absorption_reply(user_message)
    if absorption_reply:
        yield {"type": "delta", "text": absorption_reply}
        yield {
            "type": "done", "text": absorption_reply, "citations": [], "retrieved": citations,
            "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(), "model": "rule:protein_absorption",
            "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
        }
        return

    profile, menu_context_note = conversation_profile(
        profile, menu_history if menu_history is not None else (history or []),
        user_message, understanding,
    )
    macro_reply = explicit_macro_energy_reply(user_message)
    if macro_reply:
        yield {"type": "delta", "text": macro_reply}
        yield {
            "type": "done", "text": macro_reply, "citations": [], "retrieved": citations,
            "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "safety_flags": guard.as_json(), "model": "rule:macro_energy",
            "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
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

    # Formula notes already shown in this chat are not appended again.
    shown_notes = [t.get("content", "") for t in history or [] if t.get("role") == "assistant"]
    if guardrails.personalization_allowed(guard) and not guard.flags:
        profile_reply = (
            explicit_profile_summary_reply(user_message, profile, targets, menu_context_note)
            if profile is not None and targets is not None else None
        )
        if profile_reply:
            profile_reply += target_methods_note(profile_reply, targets, shown_notes)
            yield {"type": "delta", "text": profile_reply}
            yield {
                "type": "done", "text": profile_reply, "citations": [], "retrieved": citations,
                "tool_calls": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "safety_flags": guard.as_json(), "model": "rule:profile_summary",
                "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
            }
            return
        split_reply = equal_protein_split_reply(
            user_message, daily_protein_g=(targets or {}).get("macros", {}).get("protein_g"),
            history=history,
        )
        split_model = "rule:protein_split"
        meal_split = understanding.meal_split if understanding else None
        if split_reply is None and meal_split is not None:
            split_reply = target_split_reply(
                targets, meal_split.meal_count, meal_split.nutrient, meal_split.stated_total,
            )
            split_model = "rule:target_split"
        if split_reply:
            split_reply += target_methods_note(split_reply, targets, shown_notes)
            yield {"type": "delta", "text": split_reply}
            yield {
                "type": "done", "text": split_reply, "citations": [], "retrieved": citations,
                "tool_calls": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "safety_flags": guard.as_json(), "model": split_model,
                "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag,
            }
            return

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
        reference_only=(
            (not understanding.personal_context or "calculate" in understanding.blocked_actions)
            if understanding else
            _reference_question(user_message) or not _personal_context_requested(user_message)
        ),
    )

    if menu_context_note:
        system_prompt += "\n\n" + menu_context_note + " ต้องแจ้งข้อนี้เมื่อรายงานเป้าหมายหรือเมนู"
    focus = "" if understanding else prompts.answer_focus_th(user_message)
    if understanding:
        # Never promote user-provided quotes into system instructions.
        state = understanding.model_dump(exclude={
            "weight_kg", "height_cm", "goal_quote", "goal_user_turn", "missing_information",
        })
        focus += "\nข้อมูลความต้องการที่ผ่านการตรวจโครงสร้างแล้ว:\n" + str(state)
        focus += ("\nเคารพ blocked_actions ห้ามทำกิจกรรมที่ระบุไว้ "
                  "ไม่สร้างชื่อผู้ใช้หรือข้อมูลส่วนตัวเพิ่ม ไม่อ้างการไม่มีข้อมูลว่าเป็นผลจากบทความ")
        if understanding.topic == "progress_tracking":
            focus += ("\nใช้เป้าหมายล่าสุด ถ้าหลักฐานไม่มีวิธีติดตามโดยตรงให้แจ้งช่องว่างก่อน "
                      "แล้วสรุปเฉพาะปัจจัยที่มีหลักฐาน ไม่เพิ่มอัตราหรือช่วงเวลาตายตัวจากความจำ")
    if focus:
        system_prompt += "\n\n" + focus
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
        tool_config=(types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode="ANY", allowed_function_names=["lookup_food"],
        )) if (understanding.task == "lookup_food" if understanding
               else _database_food_request(user_message)) else None),
    )

    text_parts: list[str] = []
    tool_calls_log: list[dict] = []
    partial_candidates_this_turn: list[str] = []
    food_lookup_unverified = False
    food_lookup_candidates: list[str] = []
    tool_chain_active = False
    verified_food_results: list[dict] = []
    food_portion_reply: str | None = None
    verified_menu_results: list[dict] = []
    menu_errors: list[str] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    finish_reasons: list[str] = []
    answer_repair_used = False
    answer_validation_issues: list[str] = []
    evidence_ledger: list[dict] = []

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
                            partial = clean_answer("".join(turn_text_parts), citations)
                            if not unverified_menu_table(partial):
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
                    answer = without_target_citations(
                        clean_answer("".join(turn_text_parts), citations),
                        targets,
                    )
                    if unverified_menu_table(answer):
                        yield {"type": "error", "code": "unverified_menu", "message": (
                            "ยังยืนยันเมนูนี้กับฐานข้อมูลอาหารไม่ได้ครับ "
                            "กรุณาขอให้จัดเมนูจากโปรไฟล์อีกครั้ง"
                        )}
                        return
                    issues = answer_issues(
                        user_message, answer, [p.as_dict() for p in passages], use_rag=use_rag,
                        understanding=understanding,
                    )
                    last_review = None
                    if understanding and not issues:
                        try:
                            verdict, review_usage = review_answer(
                                client, model=chosen_model, question=user_message,
                                draft=answer, passages=[p.as_dict() for p in passages],
                                understanding=understanding,
                                user_context={
                                    "user_profile": _profile_summary_th(profile),
                                    "calculated_targets": targets_summary,
                                },
                            )
                        except Exception as exc:
                            logger.warning("semantic answer review failed: %s", type(exc).__name__)
                            yield {"type": "error", "code": "answer_review_unavailable",
                                   "message": "ยังตรวจยืนยันคำตอบกับหลักฐานไม่ได้ครับ กรุณาลองใหม่อีกครั้ง"}
                            return
                        for key, value in review_usage.items():
                            usage_total[key] += value
                        evidence_ledger = verdict.ledger
                        last_review = verdict
                        issues = [f"{i.category}: {i.reason} (ข้อความ: {i.fragment})"
                                  for i in verdict.issues]
                        if not issues:
                            # Labels the review found on non-claim sentences
                            # (instructions, coverage notes) that their sources
                            # do not state are removed rather than shown.
                            for raw, edited in verdict.label_edits:
                                # Only an unambiguous position is edited; an
                                # untouched label is safer than a wrong one.
                                if answer.count(raw) == 1:
                                    answer = answer.replace(raw, edited)
                    if issues:
                        answer_validation_issues.extend(issues)
                        kept = None
                        if answer_repair_used or _ == MAX_TOOL_ITERATIONS - 1:
                            kept = _keep_verified_part(
                                client, chosen_model, user_message, answer, last_review,
                                passages, understanding, use_rag, usage_total,
                                {"user_profile": _profile_summary_th(profile),
                                 "calculated_targets": targets_summary},
                            )
                        if kept is not None:
                            answer, removed = kept
                            answer_validation_issues.append(
                                "trimmed: " + " | ".join(r[:80] for r in removed)
                            )
                        elif answer_repair_used or _ == MAX_TOOL_ITERATIONS - 1:
                            yield {
                                "type": "error", "code": "answer_validation_failed",
                                "message": "ยังตรวจยืนยันคำตอบให้ตรงเงื่อนไขที่ขอไม่ได้ครับ กรุณาลองใหม่อีกครั้ง",
                                "usage": usage_total, "safety_flags": guard.as_json(),
                                "answer_validation": {
                                    "repairs": int(answer_repair_used),
                                    "issues": answer_validation_issues,
                                },
                            }
                            return
                        if kept is None:
                            answer_repair_used = True
                            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                                text=repair_instruction(issues),
                            )]))
                            yield {"type": "retry", "message": "กำลังปรับคำตอบให้ตรงคำถามครับ",
                                   "wait_s": 0}
                            continue
                    answer += target_methods_note(answer, targets, shown_notes)
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
                if call.name == "suggest_day_menu":
                    args = {
                        **args,
                        **menu_planning_options(menu_history or history or [], user_message),
                    }
                blocked_action = {
                    "calc_nutrition_targets": "calculate", "suggest_day_menu": "menu",
                }.get(call.name)
                if understanding and blocked_action in understanding.blocked_actions:
                    result = {"error": "action_excluded",
                              "message": "ผู้ใช้ไม่ต้องการกิจกรรมนี้ ห้ามดำเนินการ"}
                elif call.name == "lookup_food":
                    result = _run_food_lookup(
                        db,
                        str(args.get("query") or ""),
                        user_message=user_message,
                        pending_confirmations=pending_food_confirmations or [],
                        partial_candidates_this_turn=partial_candidates_this_turn,
                        earlier_user_messages=[
                            t.get("content", "") for t in history or [] if t.get("role") == "user"
                        ],
                    )
                else:
                    result = _execute_tool(db, profile, call.name, args, guard)
                if call.name == "lookup_food" and result.get("found"):
                    verified_food_results.append(result)
                if call.name == "suggest_day_menu" and result.get("meals"):
                    if menu_context_note:
                        result["conversation_note"] = menu_context_note
                    budget_turns = [
                        t.get("content", "") for t in (menu_history or history or [])
                        if t.get("role") == "user"
                    ]
                    if re.search("งบ|ราคา|บาท", "\n".join([*budget_turns, user_message])):
                        result["budget_note"] = (
                            "เมนูนี้คำนวณเฉพาะพลังงานและสารอาหาร ยังไม่ได้คำนวณราคา"
                            "หรือยืนยันว่าอยู่ในงบที่แจ้ง กรุณาตรวจราคาจริงก่อนเลือกซื้อ"
                        )
                        result["budget_status"] = "not_calculated"
                    verified_menu_results.append(result)
                elif call.name == "suggest_day_menu" and result.get("error"):
                    menu_errors.append(result.get("message") or "ยังจัดเมนูตามข้อจำกัดนี้ไม่ได้ครับ")
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
                status = _tool_status(call.name, result)
                call_log = {"name": call.name, "arguments": args, "status": status}
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
                yield {"type": "tool", "name": call.name, "args": args, "status": status}
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=response_parts))
            # Only the first provider turn is forced to consult foods. Any
            # subsequent explanation uses the normal automatic tool policy.
            config.tool_config = None
            if (
                verified_food_results
                and not food_lookup_unverified
                and all(call["name"] == "lookup_food" for call in tool_calls_log)
            ):
                food_portion_reply = verified_food_portion_reply(
                    verified_food_results, user_message
                )
                if food_portion_reply:
                    break
            # The planner supplies a complete displayable answer. Another model
            # turn can alter portion numbers while keeping the original totals.
            if (verified_menu_results or menu_errors) and not food_lookup_unverified:
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
            else "\n\n".join(dict.fromkeys(menu_errors))
            if menu_errors
            else "\n\n".join(_menu_reply(plan) for plan in verified_menu_results)
            if verified_menu_results
            else food_portion_reply
            if food_portion_reply
            else clean_answer("".join(text_parts), citations)
        )
        if not food_lookup_unverified:
            answer_text = without_food_citations(answer_text, verified_food_results)
            answer_text = _append_food_data_notes(answer_text, verified_food_results)
            answer_text = _append_menu_data_notes(answer_text, verified_menu_results)
        if not verified_menu_results and unverified_menu_table(answer_text):
            yield {"type": "error", "code": "unverified_menu", "message": (
                "ยังยืนยันเมนูนี้กับฐานข้อมูลอาหารไม่ได้ครับ กรุณาขอให้จัดเมนูจากโปรไฟล์อีกครั้ง"
            )}
            return
        if answer_text and not verified_menu_results:
            answer_text = without_target_citations(answer_text, targets)
            answer_text += target_methods_note(answer_text, targets, shown_notes)
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
        "answer_validation": {
            "repairs": int(answer_repair_used), "issues": answer_validation_issues,
            "evidence_ledger": evidence_ledger,
        },
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
            "ตอนนี้ผู้ให้บริการจำกัดโควตาการตอบ กรุณาลองใหม่ในภายหลังนะครับ "
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


def _understanding_reply(reply: str, guard, use_rag: bool, route: str) -> Iterator[dict]:
    yield {"type": "sources", "sources": [], "retrieval_status": "not_required"}
    yield {"type": "delta", "text": reply}
    yield {"type": "done", "text": reply, "citations": [], "retrieved": [], "tool_calls": [],
           "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
           "safety_flags": guard.as_json(), "model": "rule:" + route,
           "prompt_version": prompts.PROMPT_VERSION, "use_rag": use_rag}


PAIR_CLARIFICATION = "ต้องการกินหรือผสมอะไรคู่กับอะไรครับ กรุณาระบุทั้งสองอย่างก่อนครับ"
#: Clarification slots the answering model resolves first. The fixed "name
#: both items" reply was wrong on complete questions in every recorded run -
#: comparisons, substitutions and stated pairs (TH11, TH22, TH42, VX03; the
#: 23 Oct production test "กินเวย์ผสมนมได้ไหม"); checking quoted items moved
#: the model to other slots instead (named_items trial, not adopted). The
#: answer model sees the question with evidence and can answer or ask. If its
#: answer cannot be verified, the user gets the clarification instead of an
#: error, so the turn is never worse than the fixed reply.
MODEL_FIRST_CLARIFICATIONS = {"pair_partner": PAIR_CLARIFICATION}
_UNVERIFIED_ANSWER_CODES = {"answer_validation_failed", "answer_review_unavailable"}


def stream_understood_chat(db: Session, **kwargs) -> Iterator[dict]:
    """Production entry: semantic interpretation -> validated state -> execution.

    Existing deterministic safety rules can refuse before any provider call.
    The semantic stage can add a medical concern, never clear a safety flag.
    """
    history = kwargs.get("menu_history")
    if history is None:
        history = kwargs.get("history") or []
    pre_guard = guardrails.combine(
        guardrails.check(kwargs["user_message"]), guardrails.check_history(history, lookback=None),
        guardrails.from_stored_flags(kwargs.get("persistent_safety_flags")),
        guardrails.check_profile(kwargs.get("profile")),
    )
    if guardrails.safety_reply(pre_guard) or guardrails.refusal_reply(pre_guard):
        yield from stream_chat(db, **kwargs)
        return
    _release_connection(db)
    for attempt in range(2):
        try:
            understanding, usage = interpret_request(
                get_client(), model=kwargs.get("model") or settings.llm_model,
                message=kwargs["user_message"], history=history, profile=kwargs.get("profile"),
            )
            break
        except Exception as exc:
            code = getattr(exc, "code", None)
            empty_generation = getattr(exc, "transient", False)
            network_failure = isinstance(exc, httpx.HTTPError)
            unavailable = empty_generation or network_failure
            # A timeout already used its request budget; do not add another
            # long wait or tell the user their data was incomplete.
            if attempt == 0 and (empty_generation or code in {429, 500, 502, 503, 504}):
                delay = 12 if code == 429 else 1
                yield {"type": "retry", "wait_s": delay,
                       "message": "กำลังลองเชื่อมต่อผู้ให้บริการอีกครั้งครับ"}
                time.sleep(delay)
                continue
            logger.warning("request interpretation failed: %s", type(exc).__name__)
            if code is not None or unavailable:
                yield {"type": "error", "code": "request_understanding_unavailable",
                       "message": (user_facing_error(exc)
                                   if code is not None or network_failure else
                                   "ยังอ่านผลจากผู้ให้บริการโมเดลไม่ได้ครับ กรุณาลองใหม่อีกครั้ง")}
            else:
                yield {"type": "error", "code": "request_understanding_failed",
                       "message": ("ยังยืนยันความต้องการหรือข้อมูลที่แก้ไขไม่ได้ครับ "
                                   "กรุณาระบุคำถามและข้อมูลที่ต้องการใช้ให้ชัดเจนอีกครั้ง")}
            return
    fallback = None
    executed = understanding
    slot = understanding.missing_information
    if understanding.task == "clarify" and slot in MODEL_FIRST_CLARIFICATIONS:
        fallback = MODEL_FIRST_CLARIFICATIONS[slot]
        executed = understanding.model_copy(
            update={"task": "knowledge", "missing_information": None}
        )
    for event in stream_chat(db, **kwargs, understanding=executed):
        unverified = event["type"] == "error" and event.get("code") in _UNVERIFIED_ANSWER_CODES
        if fallback and unverified:
            guard = guardrails.combine(
                guardrails.check(kwargs["user_message"]),
                guardrails.check_history(history, lookback=None),
            )
            event = {"type": "done", "text": fallback, "citations": [], "retrieved": [],
                     "tool_calls": [], "usage": event.get("usage") or {},
                     "safety_flags": guard.as_json(), "model": "rule:missing_information",
                     "prompt_version": prompts.PROMPT_VERSION,
                     "use_rag": kwargs.get("use_rag", True),
                     "answer_validation": event.get("answer_validation")}
            yield {"type": "delta", "text": fallback}
        if event["type"] in ("done", "error"):
            event["request_understanding"] = {
                "version": UNDERSTANDING_VERSION, **understanding.model_dump(mode="json"),
            }
            total = dict(event.get("usage") or {})
            for key, count in usage.items():
                total[key] = (total.get(key) or 0) + count
            event["usage"] = total
        yield event


def collect_understood_answer(db: Session, **kwargs) -> dict:
    last = {"type": "error", "message": "no events produced"}
    for event in stream_understood_chat(db, **kwargs):
        if event["type"] in ("done", "error"):
            last = event
    return last


def collect_answer(db: Session, **kwargs) -> dict:
    """Run a turn to completion and return the final ``done`` (or ``error``) event.

    Low-level executor helper for deterministic unit tests. Full production
    evaluation uses collect_understood_answer, including semantic interpretation.
    """
    last: dict = {"type": "error", "message": "no events produced"}
    for event in stream_chat(db, **kwargs):
        if event["type"] in ("done", "error"):
            last = event
    return last
