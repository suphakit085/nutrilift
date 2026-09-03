"""Do goal and sex change the *advice*, not just the numbers?

`personalization_eval.py` proves the chat layer reports profile-specific
numbers (kcal/protein) faithfully. `safety_personalization_eval.py` proves the
safety layer sees profile-level risk. Neither asks the question a real user
would: two people with the same body but a different *goal* (cut / bulk /
maintain), or the same body but a different *sex*, should not get the same
guidance with one number swapped.

Two matrices, each holding everything else in the profile constant:

  goal  - one male profile x {cut, bulk, maintain}, same messages. The energy
          target itself moves the right way by construction (checked here from
          `calc_nutrition_targets()` without an LLM), so the interesting part is
          the prose: does a cut answer talk about a deficit, a sensible rate of
          loss and keeping muscle, does a bulk answer talk about a surplus and
          warn about dirty bulking, does a maintain answer say "eat at TDEE,
          recomposition" rather than pushing a deficit anyway.
  sex   - one body (168 cm / 62 kg / 30 y / cut) as male and as female. The
          knowledge base carries two sex-specific facts the answer *should*
          reach for when relevant: iron RDA is 20 mg/day for women of
          reproductive age vs 11.5 for men (card `calcium-iron-vitd`), and
          menstrual disruption is a hallmark sign of low energy availability
          (card `energy-balance-cut-bulk`). A woman's answer about "what to
          watch while cutting" should mention iron; a man's answer must not
          tell him to watch his periods.

Checks are plain substring/regex against the answer text - no LLM judge. Each
check is either *hard* (a mismatch is a failure and the script exits 1) or
*soft* (reported for the reader, never fails). Hard checks are deliberately
few and grounded in a specific knowledge card or a computed number; the full
transcripts at the end of the report are what the thesis should quote.

Run:
    backend/.venv/Scripts/python.exe eval/goal_sex_personalization_eval.py
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from google.genai import errors as genai_errors  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.chat import collect_answer  # noqa: E402
from app.services.nutrition import ProfileInput, calc_nutrition_targets  # noqa: E402
from app.services.prompts import PROMPT_VERSION  # noqa: E402

REPORTS_DIR = Path(__file__).parent / "reports"
#: v1 = prompt v1.5.0 (goal guidance only): goal matrix clean, but both male
#: "watch out for" answers mentioned menstrual disruption. v2 = prompt v1.6.0,
#: after prompts.sex_guidance_th. Bump when the checks or the prompt change.
REPORT_PATH = REPORTS_DIR / "goal_sex_personalization_v2.md"
THIS_YEAR = datetime.now(UTC).year

MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_DELAY_S = 20.0
_RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def _retry_delay_seconds(message: str) -> float:
    match = _RETRY_DELAY_RE.search(message)
    return float(match.group(1)) + 2.0 if match else DEFAULT_RETRY_DELAY_S


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
            print(
                f"    429, retrying in {delay:.0f}s ({attempt + 1}/{MAX_RATE_LIMIT_RETRIES})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------

def _goal_profile(goal: str) -> ProfileInput:
    return ProfileInput(
        sex="male", birth_year=THIS_YEAR - 30, height_cm=175, weight_kg=75,
        activity_level="moderate", goal=goal, training_days=4,  # type: ignore[arg-type]
    )


def _sex_profile(sex: str) -> ProfileInput:
    return ProfileInput(
        sex=sex, birth_year=THIS_YEAR - 30, height_cm=168, weight_kg=62,  # type: ignore[arg-type]
        activity_level="moderate", goal="cut", training_days=4,
    )


GOAL_PROFILES: dict[str, ProfileInput] = {g: _goal_profile(g) for g in ("cut", "bulk", "maintain")}
SEX_PROFILES: dict[str, ProfileInput] = {s: _sex_profile(s) for s in ("male", "female")}

GOAL_LABEL = {"cut": "ลดไขมัน (cut)", "bulk": "เพิ่มกล้ามเนื้อ (bulk)", "maintain": "รักษาน้ำหนัก (maintain)"}
SEX_LABEL = {"male": "ชาย", "female": "หญิง"}


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Check:
    name: str
    #: substrings, any one of which satisfies the check (or must be absent when
    #: ``absent`` is set)
    markers: tuple[str, ...]
    absent: bool = False
    hard: bool = True

    def evaluate(self, text: str) -> tuple[bool, list[str]]:
        hits = [m for m in self.markers if m.lower() in text.lower()]
        ok = (not hits) if self.absent else bool(hits)
        return ok, hits


#: Phrases that belong to one goal's framing. They paraphrase the
#: energy-balance-cut-bulk card and prompts.GOAL_GUIDANCE_TH, so an answer
#: built from either source should contain at least one.
GOAL_OWN_MARKERS: dict[str, tuple[str, ...]] = {
    "cut": ("ขาดดุล", "0.5-1%", "0.5–1%", "0.5 - 1%", "รักษามวลกล้ามเนื้อ", "คงมวลกล้ามเนื้อ", "เสียกล้ามเนื้อ"),
    "bulk": ("เกินดุล", "0.25-0.5%", "0.25–0.5%", "dirty bulk", "กินเกินมาก", "ไขมันส่วนเกิน", "ไขมันสะสม"),
    "maintain": ("รักษาน้ำหนัก", "เท่ากับ TDEE", "recomposition", "องค์ประกอบร่างกาย", "ไม่ต้องขาดดุล", "ไม่ต้องเกินดุล"),
}

#: Recommendation phrases that would be *wrong* for the goal. Soft: a cut answer
#: may legitimately mention a surplus while explaining why not to, so this is a
#: flag for the reader, not a failure.
GOAL_FOREIGN_MARKERS: dict[str, tuple[str, ...]] = {
    "cut": ("ควรเกินดุล", "กินเกิน TDEE", "เพิ่มพลังงานให้เกิน"),
    "bulk": ("ควรขาดดุล", "ลดพลังงานลง", "กินต่ำกว่า TDEE"),
    "maintain": ("ควรขาดดุล", "ควรเกินดุล", "ลดพลังงานลง"),
}

GOAL_MESSAGES: list[str] = [
    "ช่วยแนะนำแนวทางการกินสำหรับเป้าหมายของฉันหน่อย ควรกินยังไง แล้วคาดหวังผลได้ประมาณไหน",
    "ถ้าอยากเห็นผลเร็วขึ้นกว่านี้ ควรปรับพลังงานที่กินต่อวันยังไง",
]


@dataclass(frozen=True)
class SexMessage:
    text: str
    note: str
    checks: dict[str, tuple[Check, ...]] = field(default_factory=dict)
    #: The "energy target present" check is hard only where the message asks
    #: for a number. On a "what should I watch out for" question the model is
    #: free to answer without restating the target (v2 run: it did so twice and
    #: the answers were correct), so there it is reported, not required.
    require_number: bool = False


SEX_MESSAGES: list[SexMessage] = [
    SexMessage(
        text="ฉันควรกินกี่แคลอรี่ต่อวัน",
        note="ตัวเลขล้วน: BMR ต่างกัน 166 kcal จากค่าคงที่เพศในสูตร Mifflin-St Jeor คำตอบต้องรายงานเลขของเพศตัวเอง",
        require_number=True,
    ),
    SexMessage(
        text="กำลัง cut อยู่ ควรระวังวิตามินหรือแร่ธาตุอะไรเป็นพิเศษไหม",
        note=(
            "การ์ด calcium-iron-vitd: RDA ธาตุเหล็กหญิง 19-50 ปี = 20 มก./วัน (ชาย 11.5) และระบุว่า "
            "\"ผู้หญิงที่ฝึกหนัก กินน้อย\" เป็นกลุ่มเสี่ยงเหล็กต่ำ — คำตอบของผู้ใช้หญิงควรหยิบเรื่องนี้ขึ้นมา"
        ),
        checks={
            "female": (
                Check("พูดถึงธาตุเหล็ก", ("ธาตุเหล็ก", "เหล็ก")),
                Check("อ้างตัวเลข 20 มก.", ("20 มก", "20 มิลลิกรัม", "20 mg"), hard=False),
            ),
            "male": (
                Check("ไม่บอกผู้ใช้ชายให้สังเกตประจำเดือน", ("ประจำเดือน",), absent=True),
                Check("ไม่ยกค่าเหล็กของหญิง (20 มก.) ให้ผู้ใช้ชาย", ("20 มก", "20 มิลลิกรัม", "20 mg"), absent=True, hard=False),
            ),
        },
    ),
    SexMessage(
        text="จะรู้ได้ยังไงว่าฉันกินน้อยเกินไประหว่าง cut มีสัญญาณอะไรบ้าง",
        note=(
            "การ์ด energy-balance-cut-bulk ยก \"ประจำเดือนขาด/ไม่ปกติ\" เป็นสัญญาณแรกของ EA ต่ำ/RED-S "
            "— สัญญาณนี้ใช้ได้กับผู้ใช้หญิงเท่านั้น"
        ),
        checks={
            "female": (
                Check("ยกสัญญาณประจำเดือน", ("ประจำเดือน",)),
            ),
            "male": (
                Check("ไม่บอกผู้ใช้ชายให้สังเกตประจำเดือน", ("ประจำเดือน",), absent=True),
            ),
        },
    ),
]


def _number_present(text: str, value: int) -> bool:
    stripped = re.sub(r"(?<=\d),(?=\d)", "", text)
    return re.search(rf"(?<!\d){value}(?!\d)", stripped) is not None


_KCAL_RE = re.compile(r"(?<![\d.,])(\d{1,2},?\d{3}|\d{3,4})\s*(?:kcal|แคล|กิโลแคลอรี)", re.IGNORECASE)


def _kcal_mentions(text: str) -> list[int]:
    """Every kcal figure the answer names - lets the reader see at a glance
    whether a 'go faster' answer floated a number below/above the target."""
    return sorted({int(v.replace(",", "")) for v in _KCAL_RE.findall(text)})


def _trigram_jaccard(a: str, b: str) -> float:
    """Character-trigram Jaccard. Thai has no word boundaries, so this is the
    cheapest honest 'how similar are these two answers' number."""
    def grams(s: str) -> set[str]:
        s = re.sub(r"\s+", " ", s)
        return {s[i : i + 3] for i in range(max(len(s) - 2, 0))}
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga | gb) if ga | gb else 1.0


def _run(session, label: str, message: str, profile: ProfileInput) -> dict:
    print(f"  [{label}] {message}", flush=True)
    result = _collect_with_retry(session, user_message=message, profile=profile)
    time.sleep(4.5)  # free-tier 15 req/min (see personalization_eval.py)
    if result.get("type") == "error":
        return {"error": result.get("message", ""), "text": ""}
    return {"text": result.get("text", ""), "safety_flags": result.get("safety_flags") or []}


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    hard_total = 0
    hard_ok = 0
    failures: list[str] = []

    def record(ok: bool, hard: bool, where: str) -> None:
        nonlocal hard_total, hard_ok
        if not hard:
            return
        hard_total += 1
        if ok:
            hard_ok += 1
        else:
            failures.append(where)

    # ---- ground truth (no LLM) --------------------------------------------
    goal_truth = {g: calc_nutrition_targets(p) for g, p in GOAL_PROFILES.items()}
    sex_truth = {s: calc_nutrition_targets(p) for s, p in SEX_PROFILES.items()}

    lines = [
        "# เป้าหมายและเพศเปลี่ยน \"คำแนะนำ\" ไหม ไม่ใช่แค่ตัวเลข (goal × sex personalization eval)",
        "",
        f"prompt `{PROMPT_VERSION}` · รัน {datetime.now(UTC).strftime('%Y-%m-%d')} · "
        "ตรวจด้วย substring/regex กับคำตอบจริง ไม่ใช้ LLM judge · "
        "**hard** = ไม่ผ่านแล้วสคริปต์คืนค่า 1, **soft** = รายงานให้อ่านเท่านั้น",
        "",
        "## 1. ตัวเลขจากตัวคำนวณ (ground truth, ไม่ผ่าน LLM)",
        "",
        "| โปรไฟล์ | BMR | TDEE | พลังงานเป้าหมาย | โปรตีน (g) | คาร์บ (g) | ไขมัน (g) |",
        "|---|---|---|---|---|---|---|",
    ]
    for g, t in goal_truth.items():
        m = t["macros"]
        lines.append(
            f"| ชาย 30 ปี 175/75 · {GOAL_LABEL[g]} | {t['bmr_kcal']} | {t['tdee_kcal']} | "
            f"**{t['energy_target_kcal']}** | {m['protein_g']} | {m['carb_g']} | {m['fat_g']} |"
        )
    for s, t in sex_truth.items():
        m = t["macros"]
        lines.append(
            f"| {SEX_LABEL[s]} 30 ปี 168/62 · cut | {t['bmr_kcal']} | {t['tdee_kcal']} | "
            f"**{t['energy_target_kcal']}** | {m['protein_g']} | {m['carb_g']} | {m['fat_g']} |"
        )
    cut_t, bulk_t, maint_t = (goal_truth[g] for g in ("cut", "bulk", "maintain"))
    direction_ok = (
        cut_t["energy_target_kcal"] < maint_t["energy_target_kcal"] < bulk_t["energy_target_kcal"]
        and maint_t["energy_target_kcal"] == maint_t["tdee_kcal"]
    )
    record(direction_ok, True, "ground truth: cut < maintain == TDEE < bulk")
    bmr_gap = sex_truth["male"]["bmr_kcal"] - sex_truth["female"]["bmr_kcal"]
    record(bmr_gap == 166, True, f"ground truth: male-female BMR gap {bmr_gap} != 166")
    lines += [
        "",
        f"- ทิศทางพลังงานตามเป้าหมาย: cut {cut_t['energy_target_kcal']} < maintain {maint_t['energy_target_kcal']} "
        f"(= TDEE) < bulk {bulk_t['energy_target_kcal']} — {'✅' if direction_ok else '❌'} (hard)",
        f"- ช่องว่าง BMR ชาย−หญิง ร่างกายเดียวกัน: {bmr_gap} kcal (ค่าคงที่เพศของ Mifflin-St Jeor: +5 vs −161) "
        f"— {'✅' if bmr_gap == 166 else '❌'} (hard)",
        f"- โปรตีนต่อวันชาย/หญิงเท่ากัน ({sex_truth['male']['macros']['protein_g']} g) เพราะคิดต่อกก. "
        "น้ำหนักตัว ไม่ใช่ต่อเพศ — คำตอบที่ต่างกันตามเพศจึงต้องมาจากเนื้อหา ไม่ใช่ตัวเลขโปรตีน",
        "",
    ]

    session = SessionLocal()
    goal_answers: dict[str, dict[str, dict]] = {}   # message -> goal -> result
    sex_answers: dict[str, dict[str, dict]] = {}    # message -> sex -> result
    try:
        print("\n=== goal matrix ===", flush=True)
        for message in GOAL_MESSAGES:
            goal_answers[message] = {}
            for g, p in GOAL_PROFILES.items():
                goal_answers[message][g] = _run(session, GOAL_LABEL[g], message, p)
        print("\n=== sex matrix ===", flush=True)
        for sm in SEX_MESSAGES:
            sex_answers[sm.text] = {}
            for s, p in SEX_PROFILES.items():
                sex_answers[sm.text][s] = _run(session, SEX_LABEL[s], sm.text, p)
    finally:
        session.close()

    # ---- goal matrix ------------------------------------------------------
    lines += [
        "## 2. เป้าหมายต่างกัน → คำแนะนำต่างกันไหม (ร่างกายเดียวกัน ชาย 30 ปี 175 ซม. 75 กก.)",
        "",
        "| ข้อความ | เป้าหมาย | พบเลขเป้าหมาย (hard) | พบถ้อยคำของเป้าหมายตัวเอง (hard) | ถ้อยคำที่ผิดเป้าหมาย (soft) | kcal ที่เอ่ยถึงในคำตอบ |",
        "|---|---|---|---|---|---|",
    ]
    for message, per_goal in goal_answers.items():
        for g, r in per_goal.items():
            text = r["text"]
            target = goal_truth[g]["energy_target_kcal"]
            if "error" in r:
                lines.append(f"| {message} | {GOAL_LABEL[g]} | ⚠️ error | - | - | - |")
                record(False, True, f"goal/{g}: error {r['error'][:60]}")
                continue
            num_ok = _number_present(text, target)
            record(num_ok, True, f"goal/{g} «{message[:20]}…»: เลขเป้าหมาย {target} ไม่อยู่ในคำตอบ")
            own_ok, own_hits = Check("own", GOAL_OWN_MARKERS[g]).evaluate(text)
            record(own_ok, True, f"goal/{g} «{message[:20]}…»: ไม่พบถ้อยคำของเป้าหมาย {g}")
            _, foreign_hits = Check("foreign", GOAL_FOREIGN_MARKERS[g]).evaluate(text)
            lines.append(
                f"| {message} | {GOAL_LABEL[g]} | {'✅' if num_ok else '❌'} {target} "
                f"| {'✅' if own_ok else '❌'} {', '.join(own_hits) or '(ไม่พบ)'} "
                f"| {', '.join(foreign_hits) or '-'} "
                f"| {', '.join(str(k) for k in _kcal_mentions(text)) or '-'} |"
            )
    lines += ["", "ความคล้ายของคำตอบระหว่างเป้าหมาย (character-trigram Jaccard, 1.0 = เหมือนกันทุกตัวอักษร; soft):", ""]
    lines.append("| ข้อความ | cut↔bulk | cut↔maintain | bulk↔maintain |")
    lines.append("|---|---|---|---|")
    for message, per_goal in goal_answers.items():
        t = {g: per_goal[g]["text"] for g in per_goal}
        lines.append(
            f"| {message} | {_trigram_jaccard(t['cut'], t['bulk']):.2f} "
            f"| {_trigram_jaccard(t['cut'], t['maintain']):.2f} "
            f"| {_trigram_jaccard(t['bulk'], t['maintain']):.2f} |"
        )
    lines.append("")

    # ---- sex matrix -------------------------------------------------------
    lines += [
        "## 3. เพศต่างกัน → คำแนะนำต่างกันไหม (ร่างกายเดียวกัน 30 ปี 168 ซม. 62 กก. เป้าหมาย cut)",
        "",
        "| ข้อความ | เพศ | พบเลขเป้าหมาย | การตรวจเฉพาะเพศ | ผล |",
        "|---|---|---|---|---|",
    ]
    for sm in SEX_MESSAGES:
        for s, r in sex_answers[sm.text].items():
            text = r["text"]
            target = sex_truth[s]["energy_target_kcal"]
            if "error" in r:
                lines.append(f"| {sm.text} | {SEX_LABEL[s]} | ⚠️ error | - | - |")
                record(False, True, f"sex/{s}: error {r['error'][:60]}")
                continue
            num_ok = _number_present(text, target)
            record(num_ok, sm.require_number, f"sex/{s} «{sm.text[:20]}…»: เลขเป้าหมาย {target} ไม่อยู่ในคำตอบ")
            num_cell = f"{'✅' if num_ok else '➖'} {target} ({'hard' if sm.require_number else 'soft'})"
            checks = sm.checks.get(s, ())
            if not checks:
                lines.append(f"| {sm.text} | {SEX_LABEL[s]} | {num_cell} | - | - |")
                continue
            for c in checks:
                ok, hits = c.evaluate(text)
                record(ok, c.hard, f"sex/{s} «{sm.text[:20]}…»: {c.name}")
                kind = "hard" if c.hard else "soft"
                detail = ("พบ: " + ", ".join(hits)) if hits else "ไม่พบ"
                lines.append(
                    f"| {sm.text} | {SEX_LABEL[s]} | {num_cell} "
                    f"| {c.name} ({kind}) | {'✅' if ok else '❌'} {detail} |"
                )
    lines += ["", "ความคล้ายของคำตอบชาย↔หญิง (soft):", "", "| ข้อความ | ชาย↔หญิง |", "|---|---|"]
    for sm in SEX_MESSAGES:
        a = sex_answers[sm.text]
        lines.append(f"| {sm.text} | {_trigram_jaccard(a['male']['text'], a['female']['text']):.2f} |")
    lines.append("")

    # ---- verdict ----------------------------------------------------------
    lines += [
        "## สรุป",
        "",
        f"**hard checks ผ่าน {hard_ok}/{hard_total}**",
        "",
    ]
    if failures:
        lines.append("ที่ไม่ผ่าน:")
        lines += [f"- {f}" for f in failures]
        lines.append("")

    # ---- transcripts ------------------------------------------------------
    lines += ["## คำตอบเต็ม", ""]
    lines.append("### เป้าหมาย")
    for message, per_goal in goal_answers.items():
        lines += ["", f"**ข้อความ:** {message}"]
        for g, r in per_goal.items():
            lines += ["", f"#### {GOAL_LABEL[g]}", ""]
            lines.append(f"⚠️ error: {r['error']}" if "error" in r else "> " + r["text"].replace("\n", "\n> "))
    lines += ["", "### เพศ"]
    for sm in SEX_MESSAGES:
        lines += ["", f"**ข้อความ:** {sm.text}", "", f"_{sm.note}_"]
        for s, r in sex_answers[sm.text].items():
            lines += ["", f"#### {SEX_LABEL[s]}", ""]
            lines.append(f"⚠️ error: {r['error']}" if "error" in r else "> " + r["text"].replace("\n", "\n> "))

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {REPORT_PATH}")
    print(f"hard checks: {hard_ok}/{hard_total}")
    for f in failures:
        print(f"  FAIL {f}")
    return 0 if hard_ok == hard_total else 1


if __name__ == "__main__":
    sys.exit(main())
