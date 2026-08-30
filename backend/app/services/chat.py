"""Chat orchestrator.

One pass over a user message:

    guard-in -> retrieve -> build prompt -> LLM + tool loop (streamed) -> events

The orchestrator is written directly against the OpenAI Responses API (no agent
framework) so every step is inspectable and can be described in the thesis.

``stream_chat`` is a generator of plain dicts. The API layer turns them into SSE;
the evaluation harness consumes the same generator with ``collect_answer``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import guardrails, prompts, retrieval
from app.services.foods import lookup_food
from app.services.llm import get_client
from app.services.nutrition import (
    NutritionInputError,
    ProfileInput,
    calc_nutrition_targets,
    summarize_targets_th,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
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
        "type": "function",
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


def _execute_tool(db: Session, profile: ProfileInput | None, name: str, args: dict) -> dict:
    if name == "calc_nutrition_targets":
        return _run_calc_tool(profile, args)
    if name == "lookup_food":
        return lookup_food(db, args.get("query", ""))
    return {"error": "unknown_tool", "message": f"ไม่รู้จักเครื่องมือ {name}"}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


#: Matches the [S1] / [S2] markers the model is instructed to write.
_CITATION_RE = re.compile(r"\[\s*(S\d{1,2})\s*\]")


def cited_only(answer_text: str, citations: list[dict]) -> list[dict]:
    """Keep just the passages whose ``[Sn]`` label appears in the answer.

    Labels the model invents that were never retrieved are ignored. Order
    follows the original retrieval ranking, not the order of first mention.
    """
    used = {label.upper() for label in _CITATION_RE.findall(answer_text.upper())}
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
        f"เล่นเวท {profile.training_days} วัน/สัปดาห์"
        + (f", ข้อจำกัดอาหาร: {', '.join(profile.restrictions)}" if profile.restrictions else "")
    )


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
    guard = guardrails.check(user_message)

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

    targets_summary = None
    if profile is not None:
        try:
            targets_summary = summarize_targets_th(calc_nutrition_targets(profile))
        except NutritionInputError:
            logger.warning("stored profile fails validation; skipping targets summary")
            targets_summary = None

    system_prompt = prompts.build_system_prompt(
        profile_summary=_profile_summary_th(profile),
        targets_summary=targets_summary,
        passages=[p.as_dict() for p in passages],
        guard_instructions=guardrails.instructions_for(guard),
        use_rag=use_rag,
    )

    input_list: list[Any] = list(history or [])
    input_list.append({"role": "user", "content": user_message})

    client = get_client()
    chosen_model = model or settings.llm_model

    text_parts: list[str] = []
    tool_calls_log: list[dict] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            with client.responses.stream(
                model=chosen_model,
                instructions=system_prompt,
                input=input_list,
                tools=TOOL_DEFINITIONS,
                store=False,
            ) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        text_parts.append(event.delta)
                        yield {"type": "delta", "text": event.delta}
                final = stream.get_final_response()

            if final.usage is not None:
                usage_total["input_tokens"] += final.usage.input_tokens or 0
                usage_total["output_tokens"] += final.usage.output_tokens or 0
                usage_total["total_tokens"] += final.usage.total_tokens or 0

            input_list += final.output

            function_calls = [item for item in final.output if item.type == "function_call"]
            if not function_calls:
                break

            for call in function_calls:
                try:
                    args = json.loads(call.arguments) if call.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                result = _execute_tool(db, profile, call.name, args)
                tool_calls_log.append({"name": call.name, "arguments": args})
                yield {"type": "tool", "name": call.name, "args": args}
                input_list.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
        else:
            logger.warning("tool loop hit MAX_TOOL_ITERATIONS=%s", MAX_TOOL_ITERATIONS)

    except Exception as exc:
        logger.exception("chat generation failed")
        yield {"type": "error", "message": f"เกิดข้อผิดพลาดในการสร้างคำตอบ: {exc}"}
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
