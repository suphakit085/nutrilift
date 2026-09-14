"""Audit retrieval over the whole eval set without one embedding call per question.

What it measures, against the live database and the real ``retrieval.search``:

- hit@k / MRR for the shipped configuration and for dense-only, so the claim
  "hybrid improves retrieval" is re-checked every time the knowledge base
  changes rather than carried forward from the run that introduced it;
- the domain gate: which off-domain questions still pass ``RETRIEVAL_MIN_SCORE``
  and how the two score populations overlap;
- what the deterministic out-of-scope layer (keyword rule + score) decides for
  every question, and whether any in-scope question is refused by it;
- window compliance: passages sent to the model below ``best - window``.

Questions are embedded in batches (``RETRIEVAL_QUERY``, the same task type the
chat path uses) and cached next to this file, so a re-run costs no quota.

    backend/.venv/Scripts/python.exe eval/retrieval_audit.py
    backend/.venv/Scripts/python.exe eval/retrieval_audit.py --no-cache

First written 2026-09-15, when it found that hybrid mode never applied the
relative window and that 4 of the 7 off-domain questions cleared the gate.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import chat, guardrails, retrieval  # noqa: E402
from app.services.llm import embed_texts  # noqa: E402

QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"
CACHE_PATH = Path(__file__).parent / "reports" / ".question_vectors.pkl"
EMBED_BATCH = 64


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def question_vectors(questions: list[dict], *, use_cache: bool) -> dict[str, list[float]]:
    texts = [q["question"] for q in questions]
    cached: dict[str, list[float]] = {}
    if use_cache and CACHE_PATH.exists():
        cached = pickle.load(CACHE_PATH.open("rb"))
    missing = [t for t in texts if t not in cached]
    for start in range(0, len(missing), EMBED_BATCH):
        batch = missing[start : start + EMBED_BATCH]
        cached.update(zip(batch, embed_texts(batch, task_type="RETRIEVAL_QUERY"), strict=True))
        print(f"  embedded {min(start + EMBED_BATCH, len(missing))}/{len(missing)}", file=sys.stderr)
    if missing:
        CACHE_PATH.parent.mkdir(exist_ok=True)
        pickle.dump(cached, CACHE_PATH.open("wb"))
    return cached


def rank_metrics(rows: list[dict], key: str) -> tuple[float, float, list[str]]:
    scored = [r for r in rows if r["gold"]]
    hit = mrr = 0.0
    misses = []
    for r in scored:
        slugs = [s for s, _ in r[key]]
        rank = next((i for i, s in enumerate(slugs, 1) if s in r["gold"]), None)
        if rank is None:
            misses.append(r["id"])
        else:
            hit += 1
            mrr += 1 / rank
    return hit / len(scored), mrr / len(scored), misses


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit retrieval over eval/questions.jsonl")
    parser.add_argument("--no-cache", action="store_true", help="re-embed every question")
    args = parser.parse_args()

    questions = load_questions()
    vectors = question_vectors(questions, use_cache=not args.no_cache)
    retrieval.embed_text = lambda text, **_: vectors[text]  # type: ignore[assignment]

    gate_seen: dict[str, float] = {}
    real_cutoff = retrieval.score_cutoff

    def spy(best: float, threshold: float, window: float):
        gate_seen["best"] = best
        return real_cutoff(best, threshold, window)

    retrieval.score_cutoff = spy  # type: ignore[assignment]

    shipped_hybrid = settings.retrieval_hybrid
    rows: list[dict] = []
    db = SessionLocal()
    try:
        for q in questions:
            gate_seen.clear()
            hybrid = retrieval.search(db, q["question"])
            best = gate_seen.get("best", float("nan"))
            settings.retrieval_hybrid = False
            dense = retrieval.search(db, q["question"])
            settings.retrieval_hybrid = shipped_hybrid
            guard = guardrails.check(q["question"])
            rows.append(
                {
                    "id": q["id"],
                    "cat": q["category"],
                    "q": q["question"],
                    "gold": q.get("relevant_doc_slugs") or [],
                    "best": best,
                    "hybrid": [(p.document_slug, p.score) for p in hybrid],
                    "dense": [(p.document_slug, p.score) for p in dense],
                    "oos_rule": chat.is_clearly_out_of_scope(guard, hybrid),
                    "medical_rule": bool(guardrails.refusal_reply(guard)),
                }
            )
    finally:
        db.close()

    labelled = sum(1 for r in rows if r["gold"])
    print(f"คำถาม {len(rows)} ข้อ (มีการ์ดเฉลย {labelled} ข้อ)  hybrid={shipped_hybrid} "
          f"top_k={settings.retrieval_top_k} min_score={settings.retrieval_min_score} "
          f"window={settings.retrieval_relative_window} "
          f"oos_score={settings.retrieval_out_of_scope_score}")
    print()
    print("=== hit@k / MRR ===")
    for label, key in (("hybrid (shipped)" if shipped_hybrid else "dense (shipped)", "hybrid"),
                       ("dense only", "dense")):
        h, m, misses = rank_metrics(rows, key)
        print(f"  {label:<18} hit@{settings.retrieval_top_k}={h:.3f}  MRR={m:.3f}  misses={misses}")

    print()
    print("=== domain gate ===")
    on = sorted(r["best"] for r in rows if r["cat"] != "out-of-scope")
    off = sorted(r["best"] for r in rows if r["cat"] == "out-of-scope")
    passing = [r for r in rows if r["cat"] == "out-of-scope" and r["hybrid"]]
    print(f"  ในขอบเขต  best score {on[0]:.3f} - {on[-1]:.3f}")
    if off:
        print(f"  นอกขอบเขต best score {off[0]:.3f} - {off[-1]:.3f}  ผ่าน gate {len(passing)}/{len(off)}")
        overlap = sum(1 for s in on if s <= off[-1])
        print(f"  คำถามในขอบเขตที่ได้คะแนนไม่เกินคำถามนอกขอบเขตสูงสุด: {overlap}")

    print()
    print("=== ชั้น deterministic ===")
    for r in rows:
        if r["cat"] == "out-of-scope":
            verdict = "refuse:oos" if r["oos_rule"] else ("refuse:medical" if r["medical_rule"] else "-> model")
            print(f"  {r['id']} best={r['best']:.3f} {verdict:<15} {r['q'][:50]}")
    wrong = [r["id"] for r in rows if r["cat"] != "out-of-scope" and r["oos_rule"]]
    print(f"  คำถามในขอบเขตที่ถูกกฎ out-of-scope ปฏิเสธผิด: {len(wrong)} {wrong}")

    print()
    print("=== relative window ===")
    sent = sum(len(r["hybrid"]) for r in rows)
    low = sum(
        1 for r in rows for _, s in r["hybrid"]
        if s < r["best"] - settings.retrieval_relative_window
    )
    print(f"  passages ที่ส่งเข้าโมเดล {sent}  ต่ำกว่า best-window {low}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
