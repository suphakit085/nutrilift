"""Evaluation harness: RAG vs no-RAG, retrieval metrics, LLM-as-judge.

Run from the repo root with the backend venv:

    backend/.venv/Scripts/python.exe eval/run_eval.py --mode rag
    backend/.venv/Scripts/python.exe eval/run_eval.py --mode norag
    backend/.venv/Scripts/python.exe eval/run_eval.py --mode both --judge

Every (question, mode) row is flushed to <run_id>_answers.csv as soon as it's
computed. If a run gets cut off (a hard daily-quota 429, a crash, Ctrl+C),
continue it later without recomputing the rows already on disk:

    backend/.venv/Scripts/python.exe eval/run_eval.py --mode both --judge \\
        --run-id baseline-v4 --resume

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
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402

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

#: gemini-3.5-flash-lite's free tier turned out to be capped per *minute* (15
#: requests), not per day like gemini-3.5-flash - confirmed live on 2026-08-31
#: when a from-scratch eval run lost 28/33 no-RAG generations and 17/33 judge
#: calls to bare 429s. The error body names the exact wait, so retry on it
#: instead of treating a transient rate limit as a real failure.
MAX_RATE_LIMIT_RETRIES = 5

#: Seconds to wait between questions.
#:
#: The retry loop below is a safety net, not a rate limiter. Without pacing the
#: harness fires the next question the instant the previous one returns, which
#: parks it permanently above the free tier's 15 requests/minute - and once you
#: are over the cap, retrying cannot get you back under it. The 2026-09-04
#: baseline-v7 run failed 65 of 200 questions that way, every one a
#: per-minute 429 rather than the daily cap.
#:
#: Budget one question at a time: a plain question costs one generate call, one
#: that triggers a tool costs two or three. Six seconds gives ten questions a
#: minute, so even if every one called a tool the run stays under the ceiling.
#: personalization_eval.py has paced itself like this since 2 ก.ย.; run_eval
#: never got the same treatment.
DEFAULT_QUESTION_DELAY_S = 6.0
DEFAULT_RETRY_DELAY_S = 20.0
_RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def _retry_delay_seconds(message: str) -> float:
    match = _RETRY_DELAY_RE.search(message)
    return float(match.group(1)) + 2.0 if match else DEFAULT_RETRY_DELAY_S

#: Migrated to Gemini's free tier on 2026-08-31 (see docs/architecture.md) - all
#: models this project uses cost $0 under the free tier, so this records the
#: real cost realized, not an estimate. If the project later moves to a paid
#: tier, pull current per-model pricing from ai.google.dev/pricing before
#: reintroducing a non-zero table here; do not carry over these zeros.
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash": (0.0, 0.0),
    "gemini-3.5-flash-lite": (0.0, 0.0),
    "gemini-3.6-flash": (0.0, 0.0),
    "gemini-3.1-flash-lite": (0.0, 0.0),
}


#: Fixed column order for the answers CSV. Rows are now flushed one at a time as
#: they're computed (see --resume), so the header has to be written up front
#: rather than derived from the union of all rows the way a one-shot end-of-run
#: write could - the row shape varies (error vs success, --judge on/off, safety-
#: category questions get two extra judge fields).
CSV_FIELDNAMES = [
    "id", "category", "mode", "question", "answer",
    "n_retrieved", "retrieved_slugs", "n_citations", "cited_slugs",
    "tools_used", "safety_flags", "retrieval_applicable", "retrieval_hit",
    "reciprocal_rank", "input_tokens", "output_tokens", "cost_usd",
    "latency_s", "error",
    "correctness", "completeness", "groundedness", "hallucination_detected",
    "rationale", "judge_error", "handled_safely", "safety_reason",
]

_INT_FIELDS = ("correctness", "completeness", "groundedness")
_FLOAT_FIELDS = ("reciprocal_rank",)
#: summarise() gates these on `"key" in row`, not just truthiness, because
#: presence itself is meaningful (judge ran / question was safety-category).
#: csv.DictWriter's restval="" fills every column for every row regardless, so
#: a resumed row has to drop the key again when it round-trips empty.
_BOOL_PRESENCE_FIELDS = ("hallucination_detected", "handled_safely")
_BOOL_FIELDS = ("retrieval_applicable",)
_BOOL_OR_NONE_FIELDS = ("retrieval_hit",)


def _coerce_resumed_row(row: dict) -> dict:
    """Undo csv.DictReader's all-strings so a resumed row aggregates in
    summarise() exactly like a freshly computed one: ints for the judge scores,
    real bools instead of the strings "True"/"False", and cost_usd/latency_s as
    numbers so `sum()` doesn't choke on a mix of int 0 and str.
    """
    row = dict(row)
    for key in _INT_FIELDS:
        if row.get(key):
            row[key] = int(row[key])
    for key in _FLOAT_FIELDS:
        if row.get(key):
            row[key] = float(row[key])
    row["cost_usd"] = float(row["cost_usd"]) if row.get("cost_usd") else 0.0
    row["latency_s"] = float(row["latency_s"]) if row.get("latency_s") else 0.0
    for key in _BOOL_PRESENCE_FIELDS:
        if row.get(key) in ("True", "False"):
            row[key] = row[key] == "True"
        elif key in row:
            del row[key]
    for key in _BOOL_FIELDS:
        if row.get(key) in ("True", "False"):
            row[key] = row[key] == "True"
    for key in _BOOL_OR_NONE_FIELDS:
        row[key] = row[key] == "True" if row.get(key) in ("True", "False") else None
    return row


def _load_previous_answers(path: Path) -> list[dict]:
    """Rows a prior (possibly interrupted) run already wrote for this run_id."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [_coerce_resumed_row(r) for r in csv.DictReader(handle)]


def _open_answers_writer(path: Path, *, resume: bool, keep: list[dict] | None = None):
    """Open the answers CSV for incremental writes: each row is flushed to disk
    the moment it's computed, so an interrupted run (hard daily-quota 429,
    crash, Ctrl+C) loses at most the one in-flight question, not every row
    computed so far.

    On resume the file is rewritten with ``keep`` (the rows worth keeping)
    rather than appended to, so a row that failed last time can be recomputed
    without leaving its failed twin behind in the CSV.
    """
    if resume and keep is not None:
        handle = path.open("w", encoding="utf-8-sig", newline="")
        writer = csv.DictWriter(
            handle, fieldnames=CSV_FIELDNAMES, restval="", extrasaction="ignore"
        )
        writer.writeheader()
        for row in keep:
            writer.writerow(row)
        handle.flush()
        return handle, writer

    write_header = not (resume and path.exists())
    handle = path.open("a" if resume else "w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, restval="", extrasaction="ignore")
    if write_header:
        writer.writeheader()
    return handle, writer


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
        return {
            "applicable": False,
            "hit": None,
            "reciprocal_rank": None,
            "n_retrieved": len(citations),
        }

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


def _judge_call(system: str, user: str, schema: dict) -> dict:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = get_client().models.generate_content(
                model=settings.judge_model,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=user)])],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                ),
            )
            return json.loads(response.text)
        except genai_errors.ClientError as exc:
            if exc.code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            delay = _retry_delay_seconds(str(exc))
            print(
                f"    [judge] 429, retrying in {delay:.0f}s "
                f"({attempt + 1}/{MAX_RATE_LIMIT_RETRIES})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")


def judge_answer(question: dict, answer: str) -> dict:
    scores = _judge_call(
        JUDGE_SYSTEM,
        JUDGE_USER_TEMPLATE.format(
            question=question["question"],
            reference_answer=question["reference_answer"],
            candidate_answer=answer or "(ไม่มีคำตอบ)",
        ),
        JUDGE_SCHEMA,
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
        )
        scores["handled_safely"] = safety["handled_safely"]
        scores["safety_reason"] = safety["reason"]
    return scores


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _collect_answer_with_retry(session, *, user_message: str, use_rag: bool) -> dict:
    result: dict = {}
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        result = collect_answer(
            session, user_message=user_message, profile=None, history=[], use_rag=use_rag
        )
        message = result.get("message") or ""
        is_rate_limit = result.get("type") == "error" and (
            "429" in message or "RESOURCE_EXHAUSTED" in message
        )
        if not is_rate_limit or attempt == MAX_RATE_LIMIT_RETRIES:
            return result
        delay = _retry_delay_seconds(message)
        print(
            f"    [generate] 429, retrying in {delay:.0f}s "
            f"({attempt + 1}/{MAX_RATE_LIMIT_RETRIES})",
            flush=True,
        )
        time.sleep(delay)
    return result


def run_one(session, question: dict, use_rag: bool, judge: bool) -> dict:
    started = time.perf_counter()
    result = _collect_answer_with_retry(session, user_message=question["question"], use_rag=use_rag)
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
    # In the no-RAG arm retrieval never runs, so the metric is undefined rather
    # than zero - scoring it as a miss would understate the ablation baseline.
    metrics = (
        retrieval_metrics(retrieved, question.get("relevant_doc_slugs") or [])
        if use_rag
        else {"applicable": False, "hit": None, "reciprocal_rank": None, "n_retrieved": 0}
    )
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
        except Exception as exc:
            row["judge_error"] = str(exc)
    return row


def summarise(rows: list[dict], modes: list[str]) -> str:
    lines = ["# ผลการประเมิน", ""]
    lines.append(f"- วันที่รัน: {datetime.now(UTC).isoformat(timespec='seconds')}")
    lines.append(f"- generator model: `{settings.llm_model}`")
    lines.append(f"- judge model: `{settings.judge_model}`")
    lines.append(f"- embedding model: `{settings.embed_model}`")
    lines.append(f"- prompt version: `{PROMPT_VERSION}`")
    lines.append(
        f"- retrieval: top_k={settings.retrieval_top_k}, "
        f"min_score={settings.retrieval_min_score}"
    )
    lines.append(f"- จำนวนคำถาม: {len(rows) // max(len(modes), 1)}")

    # A run that dies partway (a hard daily quota 429, a crash) still writes a
    # report, and the scores below are means over the rows that *have* scores.
    # Without this banner the table reads as a clean full run: a 40-question
    # run where 34 rows hit 429 and one was scored still printed "n=40" beside
    # a perfect 5.0/5.0/5.0. Say so at the top, before any number is read.
    failed = [r for r in rows if r.get("error")]
    if failed:
        lines.append("")
        lines.append(
            f"> ⚠️ **ผลชุดนี้ไม่สมบูรณ์ — {len(failed)} จาก {len(rows)} แถวรันไม่สำเร็จ** "
            "(ดูคอลัมน์ `error` ในไฟล์ `_answers.csv`) "
            "ตัวเลขด้านล่างคิดจากเฉพาะแถวที่ให้คะแนนได้ ห้ามนำไปใช้สรุปผลจนกว่าจะรันครบ"
        )
    lines.append("")

    def mean(values: list) -> float | None:
        clean = [v for v in values if isinstance(v, (int, float))]
        return round(statistics.mean(clean), 3) if clean else None

    lines.append("## สรุปรวมต่อโหมด")
    lines.append("")
    lines.append(
        "| โหมด | ให้คะแนนได้ / ทั้งหมด | correctness | completeness | groundedness "
        "| hallucination | hit@k | MRR | cost (USD) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for mode in modes:
        subset = [r for r in rows if r["mode"] == mode]
        applicable = [r for r in subset if r.get("retrieval_applicable")]
        hits = [1 if r.get("retrieval_hit") else 0 for r in applicable]
        halluc = [r["hallucination_detected"] for r in subset if "hallucination_detected" in r]
        # n is the number of rows the scores actually come from, not the number
        # attempted - reporting the latter beside a mean of the former is what
        # made a 1-row result look like a 40-question one.
        scored = [r for r in subset if isinstance(r.get("correctness"), (int, float))]
        lines.append(
            f"| {mode} | {len(scored)} / {len(subset)} "
            f"| {mean([r.get('correctness') for r in subset])} "
            f"| {mean([r.get('completeness') for r in subset])} "
            f"| {mean([r.get('groundedness') for r in subset])} "
            f"| {round(sum(halluc) / len(halluc), 3) if halluc else '-'} "
            f"| {round(sum(hits) / len(hits), 3) if hits else '-'} "
            f"| {mean([r.get('reciprocal_rank') for r in applicable]) or '-'} "
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
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_QUESTION_DELAY_S,
        help=(
            "seconds to wait between questions so the run stays under the free "
            f"tier's 15 requests/minute (default {DEFAULT_QUESTION_DELAY_S})"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue a previous --run-id: skip (id, mode) pairs already in "
        "<run_id>_answers.csv instead of recomputing them. Use the same --mode "
        "and --judge as the interrupted run.",
    )
    args = parser.parse_args()
    if args.resume and not args.run_id:
        parser.error("--resume requires --run-id (the run to continue)")

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]

    modes = ["rag", "norag"] if args.mode == "both" else [args.mode]
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    answers_path = REPORTS_DIR / f"{run_id}_answers.csv"

    previous: list[dict] = _load_previous_answers(answers_path) if args.resume else []
    # A row that errored is not done. Treating it as done was how the
    # 2026-09-04 baseline-v7 run kept its 65 rate-limited failures across a
    # resume: they sat in the CSV, --resume skipped them, and the summary was
    # computed from a set that could never fill in. The same applies one level
    # down: the same run answered Q027 fine but the judge hit a 503, so the row
    # carried judge_error and no score. It is not done either - "ให้คะแนนได้
    # 99/100" in the summary was that row.
    def _is_done(row: dict) -> bool:
        # _coerce_resumed_row turns the numeric columns back into ints, so these
        # values are int | str | None depending on the column and the row.
        if str(row.get("error") or "").strip():
            return False  # generation failed
        if args.judge and str(row.get("correctness") or "").strip() == "":
            return False  # answered, but the judge never scored it (503, quota)
        return True

    rows: list[dict] = [r for r in previous if _is_done(r)]
    retryable = len(previous) - len(rows)
    done = {(r["id"], r["mode"]) for r in rows}
    if previous:
        print(
            f"resuming {run_id}: {len(done)} pair(s) already answered"
            + (f", {retryable} failed pair(s) will be retried" if retryable else ""),
            flush=True,
        )

    handle, writer = _open_answers_writer(
        answers_path, resume=args.resume, keep=rows if args.resume else None
    )
    session = SessionLocal()
    try:
        for mode in modes:
            for index, question in enumerate(questions, start=1):
                if (question["id"], mode) in done:
                    continue
                print(f"[{mode}] {index}/{len(questions)} {question['id']}", flush=True)
                row = run_one(session, question, mode == "rag", args.judge)
                rows.append(row)
                writer.writerow(row)
                handle.flush()
                # Pace the next question rather than relying on the retry loop;
                # see DEFAULT_QUESTION_DELAY_S. Skipped after a question that
                # already failed, since it burned its own backoff waiting.
                if args.delay > 0 and not row.get("error"):
                    time.sleep(args.delay)
    finally:
        session.close()
        handle.close()

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
