"""Wilcoxon signed-rank test: RAG vs no-RAG, paired by question.

The plan promised this exact test ("RAG vs no-RAG: same model/prompt, only
the context differs -> paired comparison, report the mean +/- Wilcoxon
signed-rank") but it was never actually run - run_eval.py's summary only
ever reported the paired table and the raw mean difference, not a
significance test over it. This script reads an existing run's
``<run_id>_answers.csv`` (no LLM calls, no quota spent) and runs the test
scipy provides, on every judge metric that was scored (correctness,
completeness, groundedness).

Run:
    backend/.venv/Scripts/python.exe eval/wilcoxon.py --run-id baseline-v5
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from scipy.stats import wilcoxon

REPORTS_DIR = Path(__file__).parent / "reports"

METRICS = ["correctness", "completeness", "groundedness"]


def load_pairs(run_id: str, metric: str) -> tuple[list[int], list[int]]:
    """Paired (rag, norag) scores for `metric`, one pair per question that
    was scored in both modes. Rows with a missing/errored judge score in
    either mode are dropped from the pair - Wilcoxon needs complete pairs.
    """
    path = REPORTS_DIR / f"{run_id}_answers.csv"
    if not path.exists():
        raise FileNotFoundError(f"no such report: {path}")

    by_id: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            by_id.setdefault(row["id"], {})[row["mode"]] = row.get(metric, "")

    rag_scores: list[int] = []
    norag_scores: list[int] = []
    for pair in by_id.values():
        rag_raw, norag_raw = pair.get("rag", ""), pair.get("norag", "")
        if rag_raw == "" or norag_raw == "":
            continue
        rag_scores.append(int(rag_raw))
        norag_scores.append(int(norag_raw))
    return rag_scores, norag_scores


def main() -> int:
    parser = argparse.ArgumentParser(description="Wilcoxon signed-rank test: RAG vs no-RAG")
    parser.add_argument("--run-id", required=True, help="e.g. baseline-v5")
    args = parser.parse_args()

    lines = [f"# Wilcoxon signed-rank: RAG vs no-RAG ({args.run_id})", ""]
    lines.append(
        "H0: ไม่มีความต่างอย่างมีนัยสำคัญระหว่างคะแนน RAG กับ no-RAG แบบจับคู่รายข้อ "
        "(same generator/prompt, ต่างแค่มี context หรือไม่)"
    )
    lines.append("")
    lines.append("| ตัวชี้วัด | n คู่ | ค่าเฉลี่ย RAG | ค่าเฉลี่ย no-RAG | W statistic | p-value | นัยสำคัญที่ 0.05 |")
    lines.append("|---|---|---|---|---|---|---|")

    any_data = False
    for metric in METRICS:
        try:
            rag, norag = load_pairs(args.run_id, metric)
        except FileNotFoundError as exc:
            print(f"! {exc}", file=sys.stderr)
            return 1

        if len(rag) < 2:
            lines.append(f"| {metric} | {len(rag)} | - | - | - | - | ข้อมูลไม่พอ |")
            continue

        # strict=True on purpose: this is a *paired* test, so a length mismatch
        # is not something to silently truncate past - it would hand the thesis
        # a p-value computed over the wrong pairs.
        diffs = [r - n for r, n in zip(rag, norag, strict=True)]
        if all(d == 0 for d in diffs):
            lines.append(
                f"| {metric} | {len(rag)} | {sum(rag) / len(rag):.3f} | "
                f"{sum(norag) / len(norag):.3f} | - | - | คะแนนเท่ากันทุกคู่ ทดสอบไม่ได้ |"
            )
            continue

        any_data = True
        result = wilcoxon(rag, norag, zero_method="wilcox", method="auto")
        significant = "ใช่" if result.pvalue < 0.05 else "ไม่"
        lines.append(
            f"| {metric} | {len(rag)} | {sum(rag) / len(rag):.3f} | "
            f"{sum(norag) / len(norag):.3f} | {result.statistic:.2f} | "
            f"{result.pvalue:.4f} | {significant} |"
        )

    if not any_data:
        lines.append("")
        lines.append("⚠️ ไม่มีตัวชี้วัดไหนทดสอบได้ (ข้อมูลไม่พอ หรือคะแนนเท่ากันทุกคู่ทุกตัวชี้วัด)")

    lines.append("")
    lines.append(
        "หมายเหตุ: `zero_method=\"wilcox\"` ตัดคู่ที่คะแนนเท่ากันทิ้งก่อนจัดอันดับ (พฤติกรรมมาตรฐานของ "
        "Wilcoxon signed-rank) `method=\"auto\"` ให้ scipy เลือกวิธีคำนวณ p-value เอง (exact เมื่อ n เล็กและ"
        "ไม่มี tie, normal approximation เมื่อ n ใหญ่หรือมี tie) ตรงกับจำนวนคำถามที่คะแนนเท่ากันเยอะในชุดนี้"
    )

    output = "\n".join(lines) + "\n"
    report_path = REPORTS_DIR / f"{args.run_id}_wilcoxon.md"
    report_path.write_text(output, encoding="utf-8")
    print(output)
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
