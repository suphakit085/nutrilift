"""Frozen fresh-question evaluation against production reference data, read only.

Uses synthetic profile/history and the deployed service code; never writes
production user records or invokes authenticated HTTP endpoints. Mechanical
checks are separate from the required full-answer semantic review.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="eval/datasets/release_v7_fresh.jsonl")
    parser.add_argument("--output", default="output/fresh-eval/release-v7-20261005")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    questions = (ROOT / args.questions).resolve()
    out = (ROOT / args.output).resolve()
    assert questions.is_relative_to(ROOT) and out.is_relative_to(ROOT / "output")
    out.mkdir(parents=True, exist_ok=True)
    for file in [r"C:\project_1\chat-bot-nutrition\backend\.env", r"C:\project_1\chat-bot-nutrition\backend\railway.env"]:
        for key, value in dotenv_values(file).items():
            if value is not None:
                os.environ[key] = value
    url = dotenv_values(r"C:\project_1\chat-bot-nutrition\backend\supabase.env")["DATABASE_URL"]
    assert "lyvsvixmbjxrkvevuxoi" in url
    os.environ["DATABASE_URL"] = url
    from app.core.config import settings
    from app.services import chat, prompts
    from app.services.nutrition import ProfileInput
    from ingest.__main__ import card_paths, content_hash
    import frontmatter
    logging.getLogger().setLevel(logging.ERROR)
    cases = [json.loads(line) for line in questions.read_text(encoding="utf8").splitlines() if line.strip()]
    assert len({c["id"] for c in cases}) == len(cases)
    profile = ProfileInput(sex="male", birth_year=1991, birth_month=3, height_cm=171,
                           weight_kg=74, activity_level="moderate", goal="bulk", training_days=3)
    engine = create_engine(url, connect_args={"prepare_threshold": None, "connect_timeout": 20})
    @event.listens_for(engine, "begin")
    def read_only(conn):
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    expected = {frontmatter.load(p).get("slug", p.stem): content_hash(frontmatter.load(p)) for p in card_paths()}
    with engine.connect() as conn:
        actual = {r.slug: r.content_hash for r in conn.execute(text("SELECT slug,content_hash FROM documents"))}
        assert actual == expected, "Production corpus differs from evaluated files"
        count = conn.execute(text("SELECT count(*) FROM foods")).scalar_one()
        assert count == 386
    manifest = {"question_sha256": digest(questions), "cases": len(cases), "prompt_version": prompts.PROMPT_VERSION,
                "prompt_sha256": hashlib.sha256(prompts.BASE_SYSTEM_PROMPT.encode()).hexdigest(),
                "source_code_sha256": digest(Path(__file__)), "model": settings.llm_model,
                "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "food_csv_sha256": digest(ROOT / "knowledge/foods.csv"), "card_hashes": expected,
                "profile": profile.__dict__, "scope": "Direct service generator; real production reference DB with every transaction read only; synthetic history/profile; no production user or HTTP quota changes.",
                "semantic_review": "pending; mechanical checks do not establish scientific correctness"}
    path = out / "frozen-run.json"
    if path.exists():
        assert json.loads(path.read_text(encoding="utf8")) == manifest, "Version changed: use a new run"
    else:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    if args.freeze_only:
        print(json.dumps({"frozen": True, "cases": len(cases), "question_sha256": manifest["question_sha256"]})); return
    answer_path = out / "answers.jsonl"
    assert not answer_path.exists(), "Never rerun/overwrite a held-out evaluation"
    histories, persistent, rows = {}, {}, []
    for case in cases:
        room = case.get("conversation", case["id"])
        history = histories.setdefault(room, [])
        start = time.perf_counter()
        with Session(engine) as session:
            answer = chat.collect_answer(session, user_message=case["question"], profile=profile,
                                         history=history, menu_history=history,
                                         persistent_safety_flags=persistent.get(room, []))
        elapsed = round(time.perf_counter() - start, 3)
        text_answer = answer.get("text", "")
        checks = {"complete": answer.get("type") == "done", "prompt_version": answer.get("prompt_version") == prompts.PROMPT_VERSION}
        if case.get("expected_model"):
            checks["model"] = answer.get("model") == case["expected_model"]
        elif case.get("slug"):
            checks["allowed_nutrition"] = not answer.get("model", "").startswith("rule:")
        if case.get("expected_tool"):
            checks["tool"] = case["expected_tool"] in {t["name"] for t in answer.get("tool_calls", [])}
        if case.get("must_include"):
            numeric_text = re.sub(r"(?<=\d),(?=\d)", "", text_answer)
            checks["expected_values"] = all(re.sub(r"(?<=\d),(?=\d)", "", v) in numeric_text for v in case["must_include"])
        if case.get("must_not_include"):
            checks["forbidden_text_absent"] = all(v not in text_answer for v in case["must_not_include"])
        used = set()
        for bracket in re.findall(r"\[([^\]]+)\]", text_answer):
            used.update(re.findall(r"\bS\d+\b", bracket))
        attached = {c["label"] for c in answer.get("citations", [])}
        available = {c["label"] for c in answer.get("retrieved", [])}
        checks["citation_mapping"] = used == attached and attached <= available
        if case.get("expected_model", "").startswith("rule:") and case["expected_model"] not in {"rule:protein_split"}:
            checks["no_tools_on_refusal"] = not answer.get("tool_calls")
        row = {**case, **answer, "latency_s": elapsed, "mechanical_checks": checks}
        with answer_path.open("a", encoding="utf8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows.append(row)
        history.extend([{"role": "user", "content": case["question"]}, {"role": "assistant", "content": text_answer}])
        persistent[room] = list(dict.fromkeys(persistent.get(room, []) + answer.get("safety_flags", [])))
        print(json.dumps({"id": case["id"], "model": answer.get("model"), "latency_s": elapsed,
                          "mechanical_failures": [k for k, v in checks.items() if not v]}), flush=True)
        time.sleep(6)
    summary = {"completed_at": datetime.now(UTC).isoformat(), "cases": len(rows),
               "mechanical_passed": sum(all(r["mechanical_checks"].values()) for r in rows),
               "errors": sum(r["type"] != "done" for r in rows), "semantic_review": "pending",
               "answers_sha256": digest(answer_path), "run_sha256": digest(path)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
