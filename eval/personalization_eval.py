"""Measure how much personalized chat answers actually vary across profiles.

`test_nutrition.py` already proves the deterministic calculator itself
produces correct, varying numbers per profile (21 unit tests over BMR/TDEE/
macros). What has never been tested is the layer above it: when a profile is
attached to a chat turn, `stream_chat()` pre-computes
`summarize_targets_th(calc_nutrition_targets(profile))` and injects it into
the system prompt with an instruction to use those numbers directly (see
`app/services/prompts.py` and `app/services/chat.py:333-343`). Nothing has
ever checked that the model's *prose answer* actually reports that number
faithfully across a range of real profiles, rather than drifting, averaging,
or ignoring the profile.

This script is deliberately NOT an LLM-as-judge eval: the correct answer for
each (profile, question) pair is computable exactly from
`calc_nutrition_targets()`, so faithfulness is checked with a plain
substring match against that ground truth - no judge model, no quota spent
on scoring, no subjectivity.

Run:
    backend/.venv/Scripts/python.exe eval/personalization_eval.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from google.genai import errors as genai_errors  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.chat import collect_answer  # noqa: E402
from app.services.nutrition import ProfileInput, calc_nutrition_targets  # noqa: E402

REPORTS_DIR = Path(__file__).parent / "reports"

MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_DELAY_S = 20.0
_RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def _retry_delay_seconds(message: str) -> float:
    match = _RETRY_DELAY_RE.search(message)
    return float(match.group(1)) + 2.0 if match else DEFAULT_RETRY_DELAY_S


#: Four profiles chosen to vary every dimension the calculator branches on:
#: sex, goal (cut/bulk/maintain), activity level, and Mifflin vs Katch-McArdle
#: (only "male_athletic_bf" supplies body_fat_pct).
PROFILES: dict[str, ProfileInput] = {
    "male_cut_heavy": ProfileInput(
        sex="male", birth_year=1999, height_cm=178, weight_kg=95,
        activity_level="moderate", goal="cut", training_days=5,
    ),
    "female_bulk_light": ProfileInput(
        sex="female", birth_year=2003, height_cm=160, weight_kg=48,
        activity_level="active", goal="bulk", training_days=4,
    ),
    "male_athletic_bf": ProfileInput(
        sex="male", birth_year=1990, height_cm=180, weight_kg=82,
        activity_level="light", goal="maintain", body_fat_pct=14,
        training_days=3,
    ),
    "female_sedentary_cut": ProfileInput(
        sex="female", birth_year=1978, height_cm=165, weight_kg=72,
        activity_level="sedentary", goal="cut", training_days=2,
    ),
}

#: (question, field path into calc_nutrition_targets()'s return dict).
#: These are exactly the numbers summarize_targets_th() injects into the
#: system prompt, so a faithful answer must contain the same integer.
QUESTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("ฉันควรกินโปรตีนวันละกี่กรัม", ("macros", "protein_g")),
    ("แคลอรี่ที่ฉันควรกินต่อวันคือเท่าไหร่", ("energy_target_kcal",)),
    ("ฉันควรกินไขมันวันละกี่กรัม", ("macros", "fat_g")),
    ("ฉันควรกินคาร์โบไฮเดรตวันละกี่กรัม", ("macros", "carb_g")),
    ("TDEE ของฉันเท่าไหร่", ("tdee_kcal",)),
]


def _get_field(targets: dict, path: tuple[str, ...]) -> int:
    value = targets
    for key in path:
        value = value[key]
    return int(value)


def _number_present(text: str, value: int) -> bool:
    """True if `value` appears in `text` as a whole number, tolerating Thai
    thousands separators ("2,594" -> "2594") so the check isn't fooled by a
    comma the model inserted purely for readability."""
    stripped = re.sub(r"(?<=\d),(?=\d)", "", text)
    return re.search(rf"(?<!\d){value}(?!\d)", stripped) is not None


def _collect_with_retry(session, *, user_message: str, profile: ProfileInput) -> dict:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return collect_answer(
                session, user_message=user_message, profile=profile,
                history=[], use_rag=True,
            )
        except genai_errors.ClientError as exc:
            if exc.code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            delay = _retry_delay_seconds(str(exc))
            print(f"    429, retrying in {delay:.0f}s ({attempt + 1}/{MAX_RATE_LIMIT_RETRIES})", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- ground truth: how much do the numbers themselves vary by profile? ---
    # Pure calculator calls, no LLM - this table alone answers "how different
    # are the answers for different people" quantitatively and exactly.
    ground_truth: dict[str, dict] = {
        name: calc_nutrition_targets(profile) for name, profile in PROFILES.items()
    }

    lines = ["# ความแตกต่างของคำตอบเชิงบุคคลตามโปรไฟล์ (personalization eval)", ""]
    lines.append(
        "ตรวจสอบว่าคำตอบแชตจริง (ผ่าน LLM + system prompt ที่ฝังตัวเลขจากโปรไฟล์) "
        "รายงานตัวเลขตรงกับที่คำนวณได้จาก `calc_nutrition_targets()` หรือไม่ "
        "- เทียบ substring ตรง ๆ กับค่าความจริง ไม่ใช้ LLM-as-judge เพราะคำตอบที่ถูกมีค่าเดียวที่คำนวณได้แน่นอน"
    )
    lines.append("")
    lines.append("## 1. ตัวเลขเป้าหมายต่างกันแค่ไหนตามโปรไฟล์ (ground truth, ไม่ผ่าน LLM)")
    lines.append("")
    lines.append("| โปรไฟล์ | BMR | TDEE | พลังงานเป้าหมาย | โปรตีน (g) | คาร์บ (g) | ไขมัน (g) |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, targets in ground_truth.items():
        m = targets["macros"]
        lines.append(
            f"| {name} | {targets['bmr_kcal']} | {targets['tdee_kcal']} | "
            f"{targets['energy_target_kcal']} | {m['protein_g']} | {m['carb_g']} | {m['fat_g']} |"
        )
    energy_values = [t["energy_target_kcal"] for t in ground_truth.values()]
    protein_values = [t["macros"]["protein_g"] for t in ground_truth.values()]
    lines.append("")
    lines.append(
        f"ช่วงพลังงานเป้าหมายระหว่างโปรไฟล์: {min(energy_values)}-{max(energy_values)} kcal "
        f"(ต่าง {max(energy_values) - min(energy_values)} kcal) · "
        f"ช่วงโปรตีน: {min(protein_values)}-{max(protein_values)} g "
        f"(ต่าง {max(protein_values) - min(protein_values)} g)"
    )
    lines.append("")

    # --- faithfulness: does the chat layer report those numbers correctly? ---
    lines.append("## 2. คำตอบแชตจริงรายงานตัวเลขตรงกับ ground truth หรือไม่")
    lines.append("")
    lines.append("| โปรไฟล์ | คำถาม | ค่าที่ถูกต้อง | เรียก calc_nutrition_targets | พบตัวเลขในคำตอบ |")
    lines.append("|---|---|---|---|---|")

    session = SessionLocal()
    total = 0
    matched = 0
    mismatches: list[dict] = []
    try:
        for profile_name, profile in PROFILES.items():
            targets = ground_truth[profile_name]
            for question, field_path in QUESTIONS:
                total += 1
                print(f"[{profile_name}] {question}", flush=True)
                expected = _get_field(targets, field_path)
                result = _collect_with_retry(session, user_message=question, profile=profile)
                # gemini-3.5-flash-lite's free tier caps at 15 requests/minute
                # (see docs/architecture.md); pacing calls here keeps this run
                # under that ceiling instead of leaning entirely on the 429
                # retry loop, which stacks badly against chat.py's own
                # internal tenacity retry on the same call.
                time.sleep(4.5)

                if result.get("type") == "error":
                    lines.append(
                        f"| {profile_name} | {question} | {expected} | - | "
                        f"⚠️ error: {result.get('message', '')[:80]} |"
                    )
                    mismatches.append(
                        {"profile": profile_name, "question": question, "expected": expected,
                         "answer": f"(error: {result.get('message', '')})"}
                    )
                    continue

                answer = result.get("text", "")
                tool_called = "calc_nutrition_targets" in [
                    t["name"] for t in (result.get("tool_calls") or [])
                ]
                found = _number_present(answer, expected)
                if found:
                    matched += 1
                else:
                    mismatches.append(
                        {"profile": profile_name, "question": question,
                         "expected": expected, "answer": answer}
                    )
                lines.append(
                    f"| {profile_name} | {question} | {expected} | "
                    f"{'ใช่' if tool_called else 'ไม่ (ใช้ตัวเลขจาก prompt โดยตรง)'} | "
                    f"{'✅' if found else '❌'} |"
                )
    finally:
        session.close()

    lines.append("")
    lines.append(f"**อัตราความถูกต้อง: {matched}/{total} ({matched / total:.1%})**")

    if mismatches:
        lines.append("")
        lines.append("### รายละเอียดข้อที่ไม่พบตัวเลขที่ถูกต้อง")
        lines.append("")
        for m in mismatches:
            lines.append(f"- **{m['profile']} / {m['question']}** (ควรมี {m['expected']}):")
            lines.append(f"  > {m['answer'][:300]}")

    report_path = REPORTS_DIR / "personalization_v1.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {report_path}")
    print(f"match rate: {matched}/{total} ({matched / total:.1%})")
    return 0 if matched == total else 1


if __name__ == "__main__":
    sys.exit(main())
