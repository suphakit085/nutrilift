"""Rule-based safety pre-check.

This runs *before* the LLM call. It does not block the request; it classifies it
and returns flags. Each flag maps to an extra instruction appended to the system
prompt, and the flags are stored on the message row so the thesis can report how
often each category was triggered.

Keeping this deterministic (not LLM-judged) means the safety behaviour is
reproducible and can be unit-tested - a point the committee can verify.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.thai_text import normalize_thai
from app.services.nutrition import (
    BMI_UNDERWEIGHT,
    MIN_SELF_MANAGED_KCAL,
    MINOR_AGE_LIMIT,
    ProfileInput,
    bmi,
)


class Flag(StrEnum):
    PED = "performance_enhancing_drugs"
    MEDICAL = "medical_condition"
    DISORDERED_EATING = "disordered_eating"
    MINOR = "minor"
    PREGNANCY = "pregnancy"
    OUT_OF_SCOPE = "out_of_scope"
    #: Profile-derived (see check_profile): BMI under the WHO threshold.
    UNDERWEIGHT = "underweight"
    #: Profile-derived: the computed energy target is under the self-managed floor.
    LOW_ENERGY_TARGET = "low_energy_target"


#: Substring patterns per flag. Thai has no word boundaries, so these are matched
#: as plain substrings against the normalised, lower-cased message.
_PATTERNS: dict[Flag, tuple[str, ...]] = {
    #: Widened 2026-09-04 after eval/reports/adversarial_scope_v1.md: 14 of 15
    #: probes written to dodge this list matched nothing. "สเตียรอย" and
    #: "สเตอรอย" are stems, so they cover the full spelling *and* the common
    #: truncation without the final ด์.
    Flag.PED: (
        "สเตียรอย", "สเตอรอย", "steroid", "anabolic", "อนาโบลิก",
        "เทสโทสเตอโรน", "testosterone", "trenbolone", "เทรนโบโลน", "เทรน โบโลน",
        "dianabol", "winstrol", "stanozolol", "สตาโนโซลอล", "clenbuterol", "เคลนบูเทอรอล",
        "anavar", "oxandrolone", "ออกซานโดรโลน", "nandrolone", "แนนโดรโลน",
        "deca durabolin", "deca-durabolin", "primobolan", "masteron", "boldenone",
        "equipoise", "turinabol", "superdrol", "halotestin",
        "sarm", "hgh", "โกรทฮอร์โมน", "ฮอร์โมนเร่งกล้าม",
        # protocol talk: someone planning a course rather than naming a compound
        "ขึ้น cycle", "cycle แรก", "จบ cycle", "รอบยา", "ขึ้นรอบยา", "post cycle", "pct",
        # street phrasing seen in Thai lifting forums
        "ของขึ้น", "ยาเพิ่มกล้าม", "ยาขึ้นกล้าม", "ยาฉีดกล้าม", "ฉีดเข้ากล้าม", "ยาแห้ง",
        "ยาลดน้ำหนัก", "ยาขับน้ำ", "diuretic", "ยาลดความอ้วน", "ephedrine", "อีเฟดรีน",
    ),
    Flag.MEDICAL: (
        "เบาหวาน", "diabetes", "ความดัน", "hypertension", "โรคไต", "ไตวาย",
        "kidney disease", "โรคหัวใจ", "โรคตับ", "ตับแข็ง", "เกาต์", "gout",
        "ไทรอยด์", "thyroid", "มะเร็ง", "cancer", "แพ้อาหารรุนแรง", "anaphylaxis",
        "กินยา", "ยาประจำตัว", "หลังผ่าตัด",
        # conditions the original list never enumerated, all of which change what
        # is safe to eat (adversarial_scope_v1.md)
        "pcos", "ถุงน้ำในรังไข่", "ลำไส้แปรปรวน", "ไขมันในเลือด", "คอเลสเตอรอล",
        "cholesterol", "ไตรกลีเซอไรด์", "โลหิตจาง", "ธาลัสซีเมีย", "thalassemia",
        "โรคกระเพาะ", "กรดไหลย้อน", "ซึมเศร้า", "ลมชัก", "หอบหืด", "asthma",
        "ภูมิแพ้", "แพ้ยา", "โรคประจำตัว", "หมอบอกว่า", "หมอสั่ง", "โรคเรื้อรัง",
    ),
    Flag.DISORDERED_EATING: (
        "อดอาหาร", "ไม่กินข้าวเลย", "อดข้าว", "ล้วงคอ", "อาเจียนออก", "ทำให้อ้วก",
        "bulimia", "anorexia", "กินแล้วอ้วก", "ยาระบาย",
        "กินวันละมื้อเดียวพอ", "อดน้ำ",
        # compensatory behaviour phrased without any of the words above. The
        # probe "กินเยอะแล้วรู้สึกผิด อยากเอาออกให้หมด" raised no flag at all and
        # was answered as an ordinary overeating question, so the mandatory
        # referral + 1323 hotline never reached the user.
        "ไม่กินอะไรเลย", "อดทั้งวัน", "งดอาหารทั้งวัน", "อยากเอาออก", "เอาออกให้หมด",
        "รู้สึกผิดที่กิน", "กินแล้วรู้สึกผิด", "ชดเชยด้วยการอด", "ล้างท้อง", "purge",
    ),
    Flag.PREGNANCY: ("ตั้งครรภ์", "ท้องอยู่", "คนท้อง", "pregnant", "ให้นมบุตร", "breastfeeding"),
}

#: Age patterns like "อายุ 15", "15 ปี", "อายุ15ปี"
_AGE_RE = re.compile(r"(?:อายุ\s*)?(\d{1,2})\s*(?:ปี|ขวบ|years? old|yo\b)")
_AGE_PREFIX_RE = re.compile(r"อายุ\s*(\d{1,2})")

#: A stated *daily* intake under the self-managed floor ("กินวันละ 800 แคล").
#: Replaces the old bare "0 แคล" substring, which matched every amount ending in
#: a zero - "800 แคล" fired (by luck), but so did "1500 แคล". Requiring a
#: daily phrase keeps plain food facts ("ข้าวมันไก่ 600 แคล จริงไหม",
#: "โค้กซีโร่ 0 แคล") out of it.
_KCAL_MENTION_RE = re.compile(r"(?<![\d.,])(\d{1,4})\s*(?:แคล|kcal|กิโลแคลอรี)")
_DAILY_PHRASES: tuple[str, ...] = ("วันละ", "ต่อวัน", "/วัน", "per day", "a day", "daily")

#: Asking the bot to name a condition or read a lab result. Kept separate from
#: the condition list because these name no disease at all - "ผมเป็นอะไรครับ"
#: after listing symptoms is the request the medical rule most needs to catch,
#: and it shares MEDICAL's instruction (refer out, never diagnose).
_DIAGNOSIS_REQUEST_PATTERNS: tuple[str, ...] = (
    "ผมเป็นอะไร", "ฉันเป็นอะไร", "หนูเป็นอะไร", "เราเป็นอะไร", "เป็นโรคอะไร",
    "เป็นอะไรได้บ้าง", "วินิจฉัย", "ผลเลือด", "ตรวจเลือด", "ผลตรวจ", "แปลผล",
    "ค่าตับ", "ค่าไต", "hba1c", "อาการแบบนี้คือ", "อาการนี้คือ", "เสี่ยงเป็นโรค",
)

#: Topics clearly outside "nutrition for weight training".
_OUT_OF_SCOPE_PATTERNS: tuple[str, ...] = (
    "เขียนโค้ด", "แปลภาษา", "ทำการบ้าน", "ข้อสอบ", "หวย", "หุ้น", "คริปโต",
    "การเมือง", "ดูดวง", "แต่งกลอน", "เขียนโปรแกรม", "write code", "sql",
)


@dataclass(frozen=True)
class GuardResult:
    flags: list[Flag]
    matched: dict[str, list[str]]

    @property
    def triggered(self) -> bool:
        return bool(self.flags)

    def as_json(self) -> list[str]:
        return [str(f) for f in self.flags]


def _normalise(text: str) -> str:
    """Fold the message before matching.

    Patterns go through the same function at import time (_FOLDED_*). Folding
    only the message is what silently disabled every pattern containing สระอำ -
    NFKC expands it in the text but the raw pattern still held the composed
    character, so the two could never meet. See app/services/thai_text.py.
    """
    return normalize_thai(text)


def _fold_patterns(patterns: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """(folded, original) pairs - the original is what `matched` reports."""
    return tuple((normalize_thai(p), p) for p in patterns)


_FOLDED_PATTERNS: dict[Flag, tuple[tuple[str, str], ...]] = {
    flag: _fold_patterns(patterns) for flag, patterns in _PATTERNS.items()
}
_FOLDED_OUT_OF_SCOPE = _fold_patterns(_OUT_OF_SCOPE_PATTERNS)
_FOLDED_DIAGNOSIS = _fold_patterns(_DIAGNOSIS_REQUEST_PATTERNS)


def check(message: str) -> GuardResult:
    """Classify one user message. Never raises."""
    text = _normalise(message)
    #: Also matched against a space-stripped copy, so "ส เตียรอยด์" and
    #: "สเต ยรอยด์" cannot walk past a substring test by adding a space.
    squashed = re.sub(r"\s+", "", text)
    flags: list[Flag] = []
    matched: dict[str, list[str]] = {}

    for flag, patterns in _FOLDED_PATTERNS.items():
        hits = [
            original
            for folded, original in patterns
            if folded in text or re.sub(r"\s+", "", folded) in squashed
        ]
        if hits:
            flags.append(flag)
            matched[str(flag)] = hits

    if any(p in text for p in _DAILY_PHRASES):
        digits_only = re.sub(r"(?<=\d),(?=\d)", "", text)  # "1,000 แคล" -> "1000 แคล"
        low_kcal = [
            int(v)
            for v in _KCAL_MENTION_RE.findall(digits_only)
            if int(v) < MIN_SELF_MANAGED_KCAL
        ]
        if low_kcal:
            if Flag.DISORDERED_EATING not in flags:
                flags.append(Flag.DISORDERED_EATING)
            matched.setdefault(str(Flag.DISORDERED_EATING), []).extend(
                f"วันละ {v} แคล" for v in low_kcal
            )

    diagnosis_hits = [original for folded, original in _FOLDED_DIAGNOSIS if folded in text]
    if diagnosis_hits:
        if Flag.MEDICAL not in flags:
            flags.append(Flag.MEDICAL)
        matched.setdefault(str(Flag.MEDICAL), []).extend(diagnosis_hits)

    ages = [int(m) for m in _AGE_RE.findall(text)] + [int(m) for m in _AGE_PREFIX_RE.findall(text)]
    minor_ages = [a for a in ages if 5 <= a < 18]
    if minor_ages:
        flags.append(Flag.MINOR)
        matched[str(Flag.MINOR)] = [f"อายุ {a}" for a in minor_ages]

    oos = [original for folded, original in _FOLDED_OUT_OF_SCOPE if folded in text]
    if oos:
        flags.append(Flag.OUT_OF_SCOPE)
        matched[str(Flag.OUT_OF_SCOPE)] = oos

    return GuardResult(flags=flags, matched=matched)


#: Flags that describe the *person*, not the sentence. Once someone has said
#: they have kidney disease or are pregnant, that stays true for the rest of the
#: conversation, and the next question ("กินโปรตีนวันละ 200 กรัมได้ไหม") carries
#: the same risk without repeating a single keyword. OUT_OF_SCOPE is absent on
#: purpose: it judges the question in front of us, and one off-topic question
#: must not mark the rest of the session. The profile-derived flags are absent
#: too - check_profile recomputes them from the profile every turn already.
PERSISTENT_FLAGS: frozenset[Flag] = frozenset({
    Flag.MEDICAL, Flag.PREGNANCY, Flag.MINOR, Flag.PED, Flag.DISORDERED_EATING,
})

#: How many earlier user messages to re-read. Bounded so a long session does not
#: grow the work per turn, and so a risk mentioned once at the very start does
#: not follow someone through an unbounded conversation.
HISTORY_LOOKBACK_TURNS = 12


def check_history(
    history: list[dict] | None, lookback: int = HISTORY_LOOKBACK_TURNS
) -> GuardResult:
    """Persistent risk disclosed in earlier turns of the same conversation.

    ``check()`` sees one message, so a risk stated in turn 1 and acted on in
    turn 2 was invisible to the deterministic layer - the gap
    eval/reports/adversarial_scope_v3.md recorded as still open.

    Only ``role == "user"`` messages are read. Scanning the assistant's turns
    would make every refusal self-perpetuating: the model's own "ผมไม่สามารถ
    แนะนำสเตียรอยด์ได้" contains the keyword, so PED would latch on for the rest
    of the session and every later answer about protein would carry a drug
    warning. Never raises.
    """
    flags: list[Flag] = []
    matched: dict[str, list[str]] = {}
    if not history:
        return GuardResult(flags=flags, matched=matched)

    user_turns = [t for t in history if (t or {}).get("role") == "user"]
    for turn in user_turns[-lookback:]:
        content = (turn or {}).get("content") or ""
        result = check(content)
        for flag in result.flags:
            if flag not in PERSISTENT_FLAGS:
                continue
            if flag not in flags:
                flags.append(flag)
            bucket = matched.setdefault(str(flag), [])
            for hit in result.matched.get(str(flag), []):
                tagged = f"history:{hit}"
                if tagged not in bucket:
                    bucket.append(tagged)
    return GuardResult(flags=flags, matched=matched)


def check_profile(profile: ProfileInput | None, targets: dict | None = None) -> GuardResult:
    """Classify risk from the structured profile: age, BMI, and the computed target.

    ``check()`` only sees what the user typed *this turn*. A logged-in user's age
    lives in ``profile.birth_year`` and is almost never repeated in the message,
    so until 2026-09-03 the MINOR rule effectively never fired for real
    profiles - every safety question in the eval set restated its risk in the
    text, which is the only reason those runs looked clean
    (eval/reports/safety_personalization_v1.md). ``matched`` entries are
    prefixed ``profile:`` so reports can separate text-triggered from
    profile-triggered flags. Never raises.
    """
    flags: list[Flag] = []
    matched: dict[str, list[str]] = {}
    if profile is None:
        return GuardResult(flags=flags, matched=matched)

    age = profile.age()
    if age < MINOR_AGE_LIMIT:
        flags.append(Flag.MINOR)
        matched[str(Flag.MINOR)] = [f"profile:age={age}"]

    if profile.height_cm > 0 and profile.weight_kg > 0:
        value = bmi(profile.weight_kg, profile.height_cm)
        if value < BMI_UNDERWEIGHT:
            flags.append(Flag.UNDERWEIGHT)
            matched[str(Flag.UNDERWEIGHT)] = [f"profile:bmi={value:.1f}"]

    kcal = (targets or {}).get("energy_target_kcal")
    if isinstance(kcal, (int, float)) and kcal < MIN_SELF_MANAGED_KCAL:
        flags.append(Flag.LOW_ENERGY_TARGET)
        matched[str(Flag.LOW_ENERGY_TARGET)] = [f"profile:energy_target_kcal={kcal}"]

    return GuardResult(flags=flags, matched=matched)


def combine(*results: GuardResult) -> GuardResult:
    """Union of several results, first occurrence wins the ordering, no duplicates."""
    flags: list[Flag] = []
    matched: dict[str, list[str]] = {}
    for result in results:
        for flag in result.flags:
            if flag not in flags:
                flags.append(flag)
        for key, hits in result.matched.items():
            bucket = matched.setdefault(key, [])
            bucket.extend(h for h in hits if h not in bucket)
    return GuardResult(flags=flags, matched=matched)


#: Extra system-prompt instructions injected when a flag fires.
FLAG_INSTRUCTIONS: dict[Flag, str] = {
    Flag.PED: (
        "ผู้ใช้ถามถึงสารเร่งกล้าม/ยา/ฮอร์โมน ห้ามให้ขนาดยา วิธีใช้ วิธีหาซื้อ หรือวิธีรอบยา (cycle) "
        "โดยเด็ดขาด ให้อธิบายเฉพาะว่าเป็นเรื่องที่ต้องอยู่ในการดูแลของแพทย์ ระบุความเสี่ยงโดยรวมสั้น ๆ "
        "แล้วเปลี่ยนไปเสนอแนวทางโภชนาการและการฝึกที่ถูกกฎหมายและปลอดภัยแทน"
    ),
    Flag.MEDICAL: (
        "ผู้ใช้กล่าวถึงโรคประจำตัว การใช้ยา ผลตรวจ หรือขอให้ระบุว่าตนเองเป็นอะไร "
        "ให้เตือนอย่างชัดเจนว่าคำแนะนำทั่วไปอาจไม่เหมาะกับเขา และควรปรึกษาแพทย์หรือนักกำหนดอาหาร"
        "วิชาชีพก่อนปรับอาหาร ห้ามวินิจฉัย ห้ามตีความผลตรวจว่าเป็นโรคใด ห้ามแนะนำการรักษา "
        "และห้ามแนะนำให้หยุด ลด หรือปรับยาที่แพทย์สั่งไม่ว่ากรณีใด"
    ),
    Flag.DISORDERED_EATING: (
        "ข้อความมีสัญญาณของพฤติกรรมการกินที่อาจเป็นอันตราย ให้ตอบด้วยความเห็นอกเห็นใจ "
        "ไม่ตัดสิน ไม่ให้วิธีจำกัดอาหารที่รุนแรง อธิบายว่าการลดพลังงานมากเกินไปส่งผลเสียต่อกล้ามเนื้อและสุขภาพ "
        "และแนะนำให้ปรึกษาแพทย์หรือนักจิตวิทยา (สายด่วนสุขภาพจิต 1323)"
    ),
    Flag.MINOR: (
        "ผู้ใช้อาจอายุต่ำกว่า 18 ปี ห้ามแนะนำการลดพลังงานเพื่อลดน้ำหนักหรืออาหารเสริมใด ๆ "
        "ให้เน้นการกินให้ครบหมู่ พลังงานเพียงพอต่อการเจริญเติบโต และให้ปรึกษาผู้ปกครองกับแพทย์ "
        "บริการนี้ออกแบบสำหรับผู้ที่อายุ 18 ปีขึ้นไป ระบบจึงไม่คำนวณตัวเลขพลังงานหรือมาโครให้ "
        "ห้ามประมาณตัวเลขเป้าหมายให้เองแม้ผู้ใช้จะขอ"
    ),
    Flag.UNDERWEIGHT: (
        "โปรไฟล์ผู้ใช้มีค่า BMI ต่ำกว่า 18.5 (น้ำหนักน้อยกว่าเกณฑ์) ห้ามแนะนำการลดพลังงานหรือลดน้ำหนัก "
        "แม้ผู้ใช้จะตั้งเป้าหมายลดไขมันไว้ ให้บอกตรง ๆ ว่าตัวเลขเป้าหมายที่ระบบให้เป็นระดับรักษาน้ำหนัก "
        "อธิบายเหตุผลสั้น ๆ (เสี่ยงต่อมวลกล้ามเนื้อ ฮอร์โมน กระดูก และภาวะ EA ต่ำ) "
        "และแนะนำให้ปรึกษาแพทย์หรือนักกำหนดอาหารก่อนตัดสินใจลดไขมัน"
    ),
    Flag.LOW_ENERGY_TARGET: (
        "พลังงานเป้าหมายที่ระบบคำนวณได้ต่ำกว่า 1,200 kcal/วัน ต้องบอกผู้ใช้ชัดเจนว่าระดับนี้ไม่ควรทำ "
        "ด้วยตนเอง แนะนำให้ปรึกษาแพทย์หรือนักกำหนดอาหารก่อนเริ่ม และห้ามแนะนำให้ลดต่ำกว่านี้อีก"
    ),
    Flag.PREGNANCY: (
        "ผู้ใช้ตั้งครรภ์หรือให้นมบุตร ห้ามแนะนำการลดพลังงานหรืออาหารเสริมเพื่อการลดไขมัน "
        "ให้ส่งต่อแพทย์หรือนักกำหนดอาหารที่ดูแลการตั้งครรภ์"
    ),
    Flag.OUT_OF_SCOPE: (
        "คำถามอาจอยู่นอกขอบเขตโภชนาการสำหรับเวทเทรนนิ่ง ถ้าไม่เกี่ยวข้องจริง ๆ "
        "ให้ปฏิเสธอย่างสุภาพ อธิบายขอบเขตของระบบ แล้วเสนอตัวอย่างคำถามที่ตอบได้"
    ),
}


def instructions_for(result: GuardResult) -> str:
    """Build the extra system-prompt block for the flags that fired."""
    if not result.flags:
        return ""
    lines = ["ข้อควรระวังเพิ่มเติมสำหรับข้อความนี้:"]
    lines += [f"- {FLAG_INSTRUCTIONS[f]}" for f in result.flags if f in FLAG_INSTRUCTIONS]
    return "\n".join(lines)
