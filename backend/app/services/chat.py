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
from collections.abc import Iterator
from typing import Any

from google.genai import types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import guardrails, prompts, retrieval
from app.services.foods import all_foods, lookup_food
from app.services.llm import get_client
from app.services.meal_plan import MealPlanError, build_day_plan
from app.services.nutrition import (
    GOAL_LABELS_TH,
    NutritionInputError,
    ProfileInput,
    calc_nutrition_targets,
    summarize_targets_th,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4

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
            "ใช้ทุกครั้งที่ต้องระบุแคลอรี่หรือมาโครของอาหาร ห้ามตอบจากความจำ"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "ชื่อเมนูภาษาไทยหรืออังกฤษ เช่น 'ข้าวผัดกุ้ง'"}
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


def _run_calc_tool(profile: ProfileInput | None, args: dict) -> dict:
    if profile is None:
        return {
            "error": "no_profile",
            "message": (
                "ผู้ใช้ยังไม่ได้กรอกโปรไฟล์ จึงคำนวณค่าเฉพาะบุคคลไม่ได้ "
                "ให้ตอบเป็นหลักการทั่วไปและชวนผู้ใช้ไปกรอกโปรไฟล์"
            ),
        }
    overrides = _clean_overrides(args)
    merged = ProfileInput(
        sex=overrides.get("sex", profile.sex),
        birth_year=profile.birth_year,
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


def _run_menu_tool(db: Session, profile: ProfileInput | None, args: dict) -> dict:
    """Build a day's menu for the stored profile.

    Targets come from ``calc_nutrition_targets`` rather than from the model, so
    a menu can never be built against numbers the model made up - and a profile
    the calculator rejects (under 18, out-of-range measurements) yields no menu
    at all, the same as it yields no targets.
    """
    if profile is None:
        return {
            "error": "no_profile",
            "message": (
                "ยังไม่มีโปรไฟล์ จัดเมนูให้ไม่ได้เพราะไม่รู้เป้าหมายพลังงานและมาโคร "
                "ให้ชวนผู้ใช้ไปกรอกโปรไฟล์ก่อน"
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


def _execute_tool(db: Session, profile: ProfileInput | None, name: str, args: dict) -> dict:
    if name == "calc_nutrition_targets":
        return _run_calc_tool(profile, args)
    if name == "suggest_day_menu":
        return _run_menu_tool(db, profile, args)
    if name == "lookup_food":
        return lookup_food(db, args.get("query", ""))
    return {"error": "unknown_tool", "message": f"ไม่รู้จักเครื่องมือ {name}"}


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

    Requiring *both* the keyword rule and an empty retrieval keeps this precise.
    A nutrition question that merely trips a keyword still retrieves context and
    is answered normally; only a question that is off-domain by both measures is
    refused outright.
    """
    return guardrails.Flag.OUT_OF_SCOPE in guard.flags and not passages


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
        role = "model" if turn["role"] == "assistant" else "user"
        part = types.Part.from_text(text=turn["content"])
        contents.append(types.Content(role=role, parts=[part]))
    return contents


def stream_chat(
    db: Session,
    *,
    user_message: str,
    profile: ProfileInput | None = None,
    history: list[dict] | None = None,
    use_rag: bool = True,
    model: str | None = None,
) -> Iterator[dict]:
    """Run one turn. Yields event dicts:

    ``{"type": "sources", "sources": [...]}``   once, before generation
    ``{"type": "delta", "text": "..."}``        many
    ``{"type": "tool", "name": ..., "args": ...}``  when a tool runs
    ``{"type": "done", ...}``                   once, with citations/usage/flags
    ``{"type": "error", "message": ...}``       on failure
    """
    # History is merged straight away so the refusal below sees a risk the user
    # disclosed in an earlier turn - "เป็นโรคไตอยู่" in turn 1 then "กินโปรตีน
    # 200 กรัมได้ไหม" in turn 2 is exactly the case the medical scope rule exists
    # for, and the second message names nothing.
    guard = guardrails.combine(
        guardrails.check(user_message), guardrails.check_history(history or [])
    )

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
    if profile is not None:
        try:
            targets = calc_nutrition_targets(profile)
            targets_summary = summarize_targets_th(targets)
        except NutritionInputError:
            logger.warning("stored profile fails validation; skipping targets summary")
        # Profile-derived risk (age, BMI, computed target). The text rules above
        # cannot see any of this - a logged-in minor rarely retypes their age -
        # so it is merged here, after targets exist, and lands in the same
        # guard_instructions / safety_flags as the text rules.
        guard = guardrails.combine(guard, guardrails.check_profile(profile, targets))


    effective_goal = (targets or {}).get("effective_goal") or (profile.goal if profile else None)
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
    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            # function_call and text parts arrive in separate stream chunks (a
            # chunk carries a delta, not a full turn); accumulating every
            # chunk's parts is the only way to reconstruct the full model turn
            # for the next iteration's history, since the terminal chunk's
            # parts are near-empty (it only carries finish_reason/usage).
            turn_parts: list[types.Part] = []
            usage_meta = None
            for chunk in client.models.generate_content_stream(
                model=chosen_model, contents=contents, config=config
            ):
                if chunk.candidates:
                    candidate_content = chunk.candidates[0].content
                    if candidate_content and candidate_content.parts:
                        turn_parts.extend(candidate_content.parts)
                if chunk.text:
                    text_parts.append(chunk.text)
                    yield {"type": "delta", "text": chunk.text}
                if chunk.usage_metadata:
                    usage_meta = chunk.usage_metadata

            if usage_meta is not None:
                usage_total["input_tokens"] += usage_meta.prompt_token_count or 0
                usage_total["output_tokens"] += usage_meta.candidates_token_count or 0
                usage_total["total_tokens"] += usage_meta.total_token_count or 0

            if turn_parts:
                contents.append(types.Content(role="model", parts=turn_parts))

            function_calls = [p.function_call for p in turn_parts if p.function_call is not None]
            if not function_calls:
                break

            response_parts = []
            for call in function_calls:
                args = call.args or {}
                result = _execute_tool(db, profile, call.name, args)
                tool_calls_log.append({"name": call.name, "arguments": args})
                yield {"type": "tool", "name": call.name, "args": args}
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=response_parts))
        else:
            logger.warning("tool loop hit MAX_TOOL_ITERATIONS=%s", MAX_TOOL_ITERATIONS)

    except Exception as exc:
        logger.exception("chat generation failed")
        yield {"type": "error", "message": user_facing_error(exc)}
        return

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
    (("resource_exhausted", "429", "quota"),
     "ตอนนี้ระบบใช้โควตาการตอบของวันนี้เต็มแล้ว ลองใหม่อีกครั้งในภายหลังนะครับ "
     "(คำถามของคุณยังอยู่ ไม่ได้หายไปไหน)"),
    (("deadline_exceeded", "timeout", "timed out"),
     "ระบบใช้เวลาตอบนานเกินไป ลองส่งคำถามอีกครั้งนะครับ"),
    (("unauthenticated", "api key", "permission_denied", "401", "403"),
     "ระบบเชื่อมต่อกับผู้ให้บริการโมเดลไม่ได้ กรุณาแจ้งผู้ดูแลระบบครับ"),
    (("unavailable", "503", "500", "internal"),
     "ผู้ให้บริการโมเดลขัดข้องชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่นะครับ"),
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
