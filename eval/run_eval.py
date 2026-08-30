"""Evaluation harness: RAG vs no-RAG, retrieval metrics, LLM-as-judge.

Run from the repo root with the backend venv:

    backend/.venv/Scripts/python.exe eval/run_eval.py --mode rag
    backend/.venv/Scripts/python.exe eval/run_eval.py --mode norag
    backend/.venv/Scripts/python.exe eval/run_eval.py --mode both --judge

Outputs (in eval/reports/):
    <run_id>_answers.csv   one row per (question, mode) with scores
    <run_id>_summary.md    aggregate table, ready to paste into the thesis
    <run_id>_expert.csv    blinded sheet for human expert scoring

Every run also records the model, prompt version, retrieval settings and cost so
results are traceable to the configuration that produced them.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.chat import collect_answer  # noqa: E402
from app.services.llm import get_client  # noqa: E402
from app.services.prompts import PROMPT_VERSION  # noqa: E402

from judge_prompts import (  # noqa: E402
    JUDGE_SCHEMA,
    JUDGE_SYSTEM,
    JUDGE_USER_TEMPLATE,
    SAFETY_SCHEMA,
    SAFETY_SYSTEM,
)

QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"
REPORTS_DIR = Path(__file__).parent / "reports"

SAFETY_CATEGORIES = {"safety", "out-of-scope"}

#: USD per 1M tokens, fetched from developers.openai.com on 2026-08-30.
#: Update alongside settings.llm_model / settings.judge_model.
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def estimate_cost_usd(model: str, usage: dict) -> float:
    prices = PRICE_PER_MTOK.get(model)
    if not prices:
        return 0.0
    inp, out = prices
    return (usage.get("input_tokens", 0) * inp + usage.get("output_tokens", 0) * out) / 1_000_000


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------


def retrieval_metrics(citations: list[dict], relevant: list[str]) -> dict:
    """hit@k and reciprocal rank over the retrieved document slugs.

    Questions with no ``relevant_doc_slugs`` (e.g. safety refusals, food lookups)
    are excluded from the aggregate - they are marked ``applicable=False``.
    """
    if not relevant:
        return {"applicable": False, "hit": None, "reciprocal_rank": None, "n_retrieved": len(citations)}

    retrieved = [c.get("document_slug") for c in citations]
    rank = next((i + 1 for i, slug in enumerate(retrieved) if slug in relevant), None)
    return {
        "applicable": True,
        "hit": rank is not None,
        "reciprocal_rank": 1.0 / rank if rank else 0.0,
        "n_retrieved": len(retrieved),
    }


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------


def _judge_call(system: str, user: str, schema: dict, schema_name: str) -> dict:
    response = get_client().responses.create(
        model=settings.judge_model,
        instructions=system,
        input=[{"role": "user", "content": user}],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
        store=False,
    )
    return json.loads(response.output_text)


def judge_answer(question: dict, answer: str) -> dict:
    scores = _judge_call(
        JUDGE_SYSTEM,
        JUDGE_USER_TEMPLATE.format(
            question=question["question"],
            reference_answer=question["reference_answer"],
            candidate_answer=answer or "(ไม่มีคำตอบ)",
        ),
        JUDGE_SCHEMA,
        "answer_scores",
    )
    if question.get("category") in SAFETY_CATEGORIES:
        safety = _judge_call(
            SAFETY_SYSTEM,
            JUDGE_USER_TEMPLATE.format(
                question=question["question"],
                reference_answer=question["reference_answer"],
                candidate_answer=answer or "(ไม่มีคำตอบ)",
            ),
            SAFETY_SCHEMA,
            "safety_check",
        )
        scores["handled_safely"] = safety["handled_safely"]
        scores["safety_reason"] = safety["reason"]
    return scores


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_one(session, question: dict, use_rag: bool, judge: bool) -> dict:
    started = time.perf_counter()
    result = collect_answer(
        session,
        user_message=question["question"],
        profile=None,
        history=[],
        use_rag=use_rag,
    )
    latency = time.perf_counter() - started

    if result.get("type") == "error":
        return {
            "id": question["id"],
            "category": question.get("category"),
            "mode": "rag" if use_rag else "norag",
            "question": question["question"],
            "answer": "",
            "error": result.get("message"),
            "latency_s": round(latency, 2),
        }

    citations = result.get("citations") or []
    retrieved = result.get("retrieved") or []
    # hit-rate/MRR measure the retriever, so they score everything it returned;
    # `citations` is the narrower set the answer actually referenced.
    metrics = retrieval_metrics(retrieved, question.get("relevant_doc_slugs") or [])
    usage = result.get("usage") or {}

    row = {
        "id": question["id"],
        "category": question.get("category"),
        "mode": "rag" if use_rag else "norag",
        "question": question["question"],
        "answer": result.get("text", ""),
        "n_retrieved": len(retrieved),
        "retrieved_slugs": "|".join(c.get("document_slug", "") for c in retrieved),
        "n_citations": len(citations),
        "cited_slugs": "|".join(c.get("document_slug", "") for c in citations),
        "tools_used": "|".join(t["name"] for t in (result.get("tool_calls") or [])),
        "safety_flags": "|".join(result.get("safety_flags") or []),
        "retrieval_applicable": metrics["applicable"],
        "retrieval_hit": metrics["hit"],
        "reciprocal_rank": metrics["reciprocal_rank"],
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": round(estimate_cost_usd(result.get("model", ""), usage), 6),
        "latency_s": round(latency, 2),
        "error": "",
    }

    if judge:
        try:
            row.update(judge_answer(question, row["answer"]))
        except Exception as exc:  # noqa: BLE001
            row["judge_error"] = str(exc)
    return row


def summarise(rows: list[dict], modes: list[str]) -> str:
    lines = ["# ผลการประเมิน", ""]
    lines.append(f"- วันที่รัน: {datetime.now(UTC).isoformat(timespec='seconds')}")
    lines.append(f"- generator model: `{settings.llm_model}`")
    lines.append(f"- judge model: `{settings.judge_model}`")
    lines.append(f"- embedding model: `{settings.embed_model}`")
    lines.append(f"- prompt version: `{PROMPT_VERSION}`")
    lines.append(f"- retrieval: top_k={settings.retrieval_top_k}, min_score={settings.retrieval_min_score}")
    lines.append(f"- จำนวนคำถาม: {len(rows) // max(len(modes), 1)}")
    lines.append("")

    def mean(values: list) -> float | None:
        clean = [v for v in values if isinstance(v, (int, float))]
        return round(statistics.mean(clean), 3) if clean else None

    lines.append("## สรุปรวมต่อโหมด")
    lines.append("")
    lines.append(
        "| โหมด | n | correctness | completeness | groundedness | hallucination | hit@k | MRR | cost (USD) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for mode in modes:
        subset = [r for r in rows if r["mode"] == mode]
        applicable = [r for r in subset if r.get("retrieval_applicable")]
        hits = [1 if r.get("retrieval_hit") else 0 for r in applicable]
        halluc = [r["hallucination_detected"] for r in subset if "hallucination_detected" in r]
        lines.append(
            f"| {mode} | {len(subset)} "
            f"| {mean([r.get('correctness') for r in subset])} "
            f"| {mean([r.get('completeness') for r in subset])} "
            f"| {mean([r.get('groundedness') for r in subset])} "
            f"| {round(sum(halluc) / len(halluc), 3) if halluc else '-'} "
            f"| {round(sum(hits) / len(hits), 3) if hits else '-'} "
            f"| {mean([r.get('reciprocal_rank') for r in applicable])} "
            f"| {round(sum(r.get('cost_usd', 0) for r in subset), 4)} |"
        )

    lines.append("")
    lines.append("## แยกตามหมวดคำถาม (correctness เฉลี่ย)")
    lines.append("")
    categories = sorted({r["category"] for r in rows if r.get("category")})
    lines.append("| หมวด | " + " | ".join(modes) + " |")
    lines.append("|---" * (len(modes) + 1) + "|")
    for category in categories:
        cells = []
        for mode in modes:
            subset = [r for r in rows if r["mode"] == mode and r["category"] == category]
            cells.append(str(mean([r.get("correctness") for r in subset])))
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    safety_rows = [r for r in rows if r.get("category") in SAFETY_CATEGORIES]
    if any("handled_safely" in r for r in safety_rows):
        lines.append("")
        lines.append("## ความปลอดภัย (สัดส่วนที่ปฏิเสธ/ส่งต่อได้เหมาะสม)")
        lines.append("")
        for mode in modes:
            subset = [r for r in safety_rows if r["mode"] == mode and "handled_safely" in r]
            if subset:
                rate = sum(1 for r in subset if r["handled_safely"]) / len(subset)
                lines.append(f"- {mode}: {rate:.1%} ({len(subset)} ข้อ)")

    if len(modes) == 2:
        lines.append("")
        lines.append("## เปรียบเทียบรายข้อ (สำหรับ Wilcoxon signed-rank)")
        lines.append("")
        lines.append("| id | correctness rag | correctness norag | ผลต่าง |")
        lines.append("|---|---|---|---|")
        by_id: dict[str, dict[str, dict]] = {}
        for row in rows:
            by_id.setdefault(row["id"], {})[row["mode"]] = row
        for qid in sorted(by_id):
            pair = by_id[qid]
            rag = pair.get("rag", {}).get("correctness")
            norag = pair.get("norag", {}).get("correctness")
            diff = rag - norag if isinstance(rag, int) and isinstance(norag, int) else "-"
            lines.append(f"| {qid} | {rag} | {norag} | {diff} |")

    return "\n".join(lines) + "\n"


def write_expert_sheet(path: Path, rows: list[dict]) -> None:
    """Blinded sheet: answers shuffled between arms, arm label hidden.

    The mapping is written to a separate ``*_key.csv`` so scoring stays blind but
    results can be un-blinded afterwards.
    """
    import random

    by_id: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_id.setdefault(row["id"], {})[row["mode"]] = row

    rng = random.Random(20260831)
    sheet: list[dict] = []
    key: list[dict] = []
    for qid in sorted(by_id):
        pair = by_id[qid]
        if len(pair) < 2:
            continue
        modes = ["rag", "norag"]
        rng.shuffle(modes)
        sheet.append(
            {
                "id": qid,
                "question": pair[modes[0]]["question"],
                "answer_A": pair[modes[0]]["answer"],
                "answer_B": pair[modes[1]]["answer"],
                "score_A_correctness_1_5": "",
                "score_B_correctness_1_5": "",
                "score_A_usefulness_1_5": "",
                "score_B_usefulness_1_5": "",
                "comment": "",
            }
        )
        key.append({"id": qid, "answer_A_mode": modes[0], "answer_B_mode": modes[1]})

    _write_csv(path, sheet)
    _write_csv(path.with_name(path.name.replace("_expert", "_expert_key")), key)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for column in row:
            if column not in fieldnames:
                fieldnames.append(column)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RAG evaluation")
    parser.add_argument("--mode", choices=["rag", "norag", "both"], default="both")
    parser.add_argument("--judge", action="store_true", help="score answers with the judge model")
    parser.add_argument("--limit", type=int, help="only run the first N questions")
    parser.add_argument("--run-id", help="override the report file prefix")
    args = parser.parse_args()

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]

    modes = ["rag", "norag"] if args.mode == "both" else [args.mode]
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    rows: list[dict] = []
    try:
        for mode in modes:
            for index, question in enumerate(questions, start=1):
                print(f"[{mode}] {index}/{len(questions)} {question['id']}", flush=True)
                rows.append(run_one(session, question, mode == "rag", args.judge))
    finally:
        session.close()

    answers_path = REPORTS_DIR / f"{run_id}_answers.csv"
    _write_csv(answers_path, rows)

    summary_path = REPORTS_DIR / f"{run_id}_summary.md"
    summary_path.write_text(summarise(rows, modes), encoding="utf-8")

    if len(modes) == 2:
        write_expert_sheet(REPORTS_DIR / f"{run_id}_expert.csv", rows)

    print(f"\nwrote {answers_path}")
    print(f"wrote {summary_path}")
    errors = [r for r in rows if r.get("error")]
    if errors:
        print(f"! {len(errors)} question(s) failed - see the error column")
    return 0


if __name__ == "__main__":
    sys.exit(main())
