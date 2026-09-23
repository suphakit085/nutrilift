"""Score the SUS + satisfaction questionnaire exported from Google Forms.

    backend/.venv/Scripts/python.exe eval/sus_score.py eval/sus/responses.csv
    backend/.venv/Scripts/python.exe eval/sus_score.py --self-test

Columns are found by the code each question title starts with ("Q1 ...",
"S3 ...", "T2 ..."), so the Thai wording can change without touching this file.
See eval/sus/questionnaire.md for the instrument and how to report the result.

SUS scoring (Brooke, 1996): odd items contribute (answer - 1), even items
(5 - answer); the sum x 2.5 gives 0-100. It is not a percentage. Grades follow
Bangor, Kortum & Miller (2009).
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import sys
from pathlib import Path

SUS_ITEMS = [f"Q{i}" for i in range(1, 11)]
SAT_ITEMS = [f"S{i}" for i in range(1, 11)]
TASKS = [f"T{i}" for i in range(1, 7)]

#: (lower bound, adjective, acceptability) - Bangor, Kortum & Miller 2009.
GRADES = [
    (85.5, "Excellent", "Acceptable"),
    (72.6, "Good", "Acceptable"),
    (70.0, "OK", "Acceptable"),
    (52.0, "OK", "Marginal"),
    (39.2, "Poor", "Not acceptable"),
    (0.0, "Worst imaginable", "Not acceptable"),
]
BENCHMARK = 68.0


def sus_score(answers: list[int]) -> float:
    if len(answers) != 10 or any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise ValueError(f"SUS needs ten answers in 1-5, got {answers}")
    total = sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers))
    return total * 2.5


def grade(score: float) -> tuple[str, str]:
    for lower, adjective, acceptability in GRADES:
        if score >= lower:
            return adjective, acceptability
    return GRADES[-1][1:]


def cronbach_alpha(rows: list[list[float]]) -> float | None:
    """Alpha over item columns; rows are respondents."""
    if len(rows) < 2:
        return None
    k = len(rows[0])
    item_vars = [statistics.variance([r[j] for r in rows]) for j in range(k)]
    total_var = statistics.variance([sum(r) for r in rows])
    if total_var == 0:
        return None
    return k / (k - 1) * (1 - sum(item_vars) / total_var)


def t_critical_95(df: int) -> float:
    try:
        from scipy import stats

        return float(stats.t.ppf(0.975, df))
    except ImportError:  # pragma: no cover - scipy is in the eval deps
        return 1.96


def find_columns(header: list[str], codes: list[str]) -> dict[str, int]:
    found = {}
    for idx, title in enumerate(header):
        m = re.match(r"^\s*\[?([QST]\d{1,2})\b", title.strip())
        if m and m.group(1) in codes:
            found[m.group(1)] = idx
    return found


def _num(value: str) -> int | None:
    m = re.search(r"[1-5]", value or "")
    return int(m.group()) if m else None


def analyse(rows: list[list[str]], header: list[str]) -> str:
    sus_cols = find_columns(header, SUS_ITEMS)
    missing = [c for c in SUS_ITEMS if c not in sus_cols]
    if missing:
        raise SystemExit(f"! CSV has no column starting with {missing} - put the code first in each title")
    sat_cols = find_columns(header, SAT_ITEMS)
    task_cols = find_columns(header, TASKS)

    scores, item_rows, skipped = [], [], 0
    for row in rows:
        answers = [_num(row[sus_cols[c]]) for c in SUS_ITEMS]
        if None in answers:
            skipped += 1
            continue
        scores.append(sus_score(answers))
        item_rows.append([(a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers)])

    out = []
    n = len(scores)
    out.append(f"ผู้ตอบ SUS ครบ 10 ข้อ: n = {n}" + (f" (ตัดทิ้ง {skipped} แถวที่ตอบไม่ครบ)" if skipped else ""))
    if n == 0:
        return "\n".join(out)
    mean = statistics.fmean(scores)
    sd = statistics.stdev(scores) if n > 1 else 0.0
    half = t_critical_95(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    adjective, acceptability = grade(mean)
    alpha = cronbach_alpha(item_rows)
    out += [
        "",
        "| สถิติ | ค่า |",
        "|---|---|",
        f"| ค่าเฉลี่ย SUS | {mean:.1f} |",
        f"| SD | {sd:.1f} |",
        f"| มัธยฐาน | {statistics.median(scores):.1f} |",
        f"| ต่ำสุด–สูงสุด | {min(scores):.1f}–{max(scores):.1f} |",
        f"| 95% CI ของค่าเฉลี่ย | {mean - half:.1f}–{mean + half:.1f} |",
        f"| ระดับ (Bangor et al. 2009) | {adjective} · {acceptability} |",
        f"| เทียบค่ากลาง {BENCHMARK:.0f} | {mean - BENCHMARK:+.1f} |",
        f"| Cronbach's alpha (10 ข้อ) | {'n/a' if alpha is None else f'{alpha:.2f}'} |",
    ]

    if sat_cols:
        out += ["", "ความพึงพอใจรายข้อ (1–5)", "", "| ข้อ | ค่าเฉลี่ย | SD | n |", "|---|---|---|---|"]
        for code in SAT_ITEMS:
            if code in sat_cols:
                vals = [v for v in (_num(r[sat_cols[code]]) for r in rows) if v is not None]
                if vals:
                    sd_i = statistics.stdev(vals) if len(vals) > 1 else 0.0
                    out.append(f"| {code} | {statistics.fmean(vals):.2f} | {sd_i:.2f} | {len(vals)} |")

    if task_cols:
        out += ["", "อัตราทำงานสำเร็จ", "", "| งาน | สำเร็จ | ติดขัด | ไม่สำเร็จ |", "|---|---|---|---|"]
        for code in TASKS:
            if code in task_cols:
                vals = [(r[task_cols[code]] or "").strip() for r in rows]
                vals = [v for v in vals if v]
                stuck = sum("ติดขัด" in v for v in vals)
                fail = sum("ไม่สำเร็จ" in v for v in vals)
                ok = len(vals) - stuck - fail
                out.append(f"| {code} | {ok}/{len(vals)} | {stuck} | {fail} |")
    return "\n".join(out)


def _self_test() -> int:
    # Brooke's worked extremes and a known midpoint.
    assert sus_score([5, 1] * 5) == 100.0
    assert sus_score([1, 5] * 5) == 0.0
    assert sus_score([3] * 10) == 50.0
    assert sus_score([4, 2, 4, 2, 4, 2, 4, 2, 4, 2]) == 75.0
    assert grade(90)[0] == "Excellent" and grade(75)[0] == "Good"
    assert grade(71)[1] == "Acceptable" and grade(60)[1] == "Marginal" and grade(45)[0] == "Poor"
    header = ["Timestamp"] + [f"{c} ข้อความ" for c in SUS_ITEMS] + ["S1 เข้าใจง่าย", "T1 สมัคร"]
    rows = [["x"] + ["4", "2"] * 5 + ["5", "สำเร็จ"], ["y"] + ["5", "1"] * 5 + ["4", "สำเร็จแต่ติดขัด"]]
    report = analyse(rows, header)
    assert "n = 2" in report and "87.5" in report, report
    try:
        sus_score([0] * 10)
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range answers must be rejected")
    print("self-test ok")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not args.csv:
        parser.error("give the exported CSV path")
    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [r for r in reader if any(cell.strip() for cell in r)]
    print(analyse(rows, header))
    return 0


if __name__ == "__main__":
    sys.exit(main())
