"""Calibrate RETRIEVAL_MIN_SCORE against the current knowledge base.

Cosine similarities from an embedding model are not comparable across corpora -
the usable range shifts as the knowledge base grows. This script measures where
on-topic and off-topic queries actually land, then reports the threshold that
separates them, so the value in ``.env`` is an evidence-based number rather than
a guess.

Re-run it whenever the knowledge base changes substantially (e.g. after adding a
batch of cards), and record the output in the thesis alongside the chosen value.

    backend/.venv/Scripts/python.exe eval/calibrate_threshold.py
    backend/.venv/Scripts/python.exe eval/calibrate_threshold.py --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import retrieval  # noqa: E402

QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"

#: Queries that must NOT retrieve anything - used to find the noise ceiling.
#: Deliberately varied: everyday chatter, other domains, and near-miss health
#: topics the knowledge base does not cover.
OFF_TOPIC_QUERIES = [
    "วันนี้อากาศเป็นยังไง",
    "ราคาหุ้นวันนี้เท่าไหร่",
    "ช่วยเขียนโค้ด Python อ่านไฟล์ CSV",
    "หนังเรื่องไหนน่าดู",
    "รถติดไหมวันนี้",
    "แปลประโยคนี้เป็นภาษาอังกฤษให้หน่อย",
    "เลขเด็ดงวดนี้",
    "จองตั๋วเครื่องบินยังไง",
]


def load_on_topic() -> list[str]:
    """On-topic queries = eval questions that have a known relevant document."""
    if not QUESTIONS_PATH.exists():
        return []
    questions = []
    with QUESTIONS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("relevant_doc_slugs"):
                questions.append(item["question"])
    return questions


def top_score(db, query: str) -> tuple[float, str, str | None]:
    passages = retrieval.search(db, query, top_k=1, min_score=-1.0)
    if not passages:
        return (float("nan"), "(ฐานความรู้ว่าง)", None)
    top = passages[0]
    return (top.score, top.document_slug, top.heading)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate the retrieval threshold")
    parser.add_argument("--verbose", action="store_true", help="show every query's top hit")
    args = parser.parse_args()

    on_topic = load_on_topic()
    if not on_topic:
        print("! ไม่พบคำถามที่มี relevant_doc_slugs ใน eval/questions.jsonl")
        return 1

    db = SessionLocal()
    try:
        on_scores: list[tuple[float, str]] = []
        off_scores: list[tuple[float, str]] = []

        for query in on_topic:
            score, slug, _ = top_score(db, query)
            on_scores.append((score, query))
            if args.verbose:
                print(f"  on  {score:6.3f}  {slug:<26} {query}")

        for query in OFF_TOPIC_QUERIES:
            score, slug, _ = top_score(db, query)
            off_scores.append((score, query))
            if args.verbose:
                print(f"  off {score:6.3f}  {slug:<26} {query}")
    finally:
        db.close()

    if args.verbose:
        print()

    on_min = min(s for s, _ in on_scores)
    on_max = max(s for s, _ in on_scores)
    off_min = min(s for s, _ in off_scores)
    off_max = max(s for s, _ in off_scores)
    gap = on_min - off_max

    print(f"คำถามตรงประเด็น ({len(on_scores)} ข้อ) : {on_min:.3f} - {on_max:.3f}")
    print(f"คำถามนอกเรื่อง  ({len(off_scores)} ข้อ) : {off_min:.3f} - {off_max:.3f}")
    print(f"ช่องว่างระหว่างสองกลุ่ม            : {gap:+.3f}")
    print()

    print("ผลของแต่ละ threshold:")
    print(f"  {'threshold':>9}  {'เก็บที่ตรงประเด็น':>18}  {'ปล่อยนอกเรื่องผ่าน':>20}")
    # Gemini-embedding-001 similarities sit far above the OpenAI-era range this
    # list used to cover (0.20-0.40); with those candidates the current value
    # never even appeared in the table.
    candidates = sorted(
        {round(v, 2) for v in [0.55, 0.58, 0.60, 0.62, 0.63, 0.64, 0.65, 0.66, 0.68, 0.70]}
        | {round(settings.retrieval_min_score, 2)}
    )
    for threshold in candidates:
        kept = sum(1 for s, _ in on_scores if s >= threshold)
        leaked = sum(1 for s, _ in off_scores if s >= threshold)
        marker = "  <-- ค่าปัจจุบัน" if abs(threshold - settings.retrieval_min_score) < 1e-9 else ""
        print(
            f"  {threshold:>9.2f}  {kept:>10}/{len(on_scores):<7}  "
            f"{leaked:>12}/{len(off_scores):<7}{marker}"
        )
    print()

    if gap > 0:
        suggested = round((on_min + off_max) / 2, 2)
        print(f"แนะนำ: RETRIEVAL_MIN_SCORE={suggested:.2f}  (กึ่งกลางของช่องว่าง)")
        if abs(suggested - settings.retrieval_min_score) >= 0.02:
            print(f"  ค่าปัจจุบันคือ {settings.retrieval_min_score:.2f} - ควรพิจารณาปรับ")
        else:
            print(f"  ค่าปัจจุบัน {settings.retrieval_min_score:.2f} เหมาะสมอยู่แล้ว")
    else:
        print("! คะแนนสองกลุ่มทับซ้อนกัน - ไม่มี threshold ที่แยกได้สะอาด")
        print("  แปลว่า retrieval ยังอ่อน ควรเพิ่มการ์ดความรู้ หรือพิจารณา hybrid search")

    weakest = sorted(on_scores)[:3]
    print()
    print("คำถามตรงประเด็นที่ได้คะแนนต่ำสุด (ช่องว่างของฐานความรู้):")
    for score, query in weakest:
        print(f"  {score:.3f}  {query}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
