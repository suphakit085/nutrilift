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
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Flag(StrEnum):
    PED = "performance_enhancing_drugs"
    MEDICAL = "medical_condition"
    DISORDERED_EATING = "disordered_eating"
    MINOR = "minor"
    PREGNANCY = "pregnancy"
    OUT_OF_SCOPE = "out_of_scope"


#: Substring patterns per flag. Thai has no word boundaries, so these are matched
#: as plain substrings against the normalised, lower-cased message.
_PATTERNS: dict[Flag, tuple[str, ...]] = {
    Flag.PED: (
        "สเตียรอยด์", "สเตอรอยด์", "steroid", "anabolic", "อนาโบลิก",
        "เทสโทสเตอโรน", "testosterone", "trenbolone", "เทรน โบโลน",
        "dianabol", "winstrol", "clenbuterol", "เคลนบูเทอรอล",
        "sarm", "ยาฉีดกล้าม", "ฮอร์โมนเร่งกล้าม", "hgh", "โกรทฮอร์โมน",
        "ยาลดน้ำหนัก", "ยาขับน้ำ", "diuretic", "ยาลดความอ้วน", "ephedrine", "อีเฟดรีน",
    ),
    Flag.MEDICAL: (
        "เบาหวาน", "diabetes", "ความดัน", "hypertension", "โรคไต", "ไตวาย",
        "kidney disease", "โรคหัวใจ", "โรคตับ", "ตับแข็ง", "เกาต์", "gout",
        "ไทรอยด์", "thyroid", "มะเร็ง", "cancer", "แพ้อาหารรุนแรง", "anaphylaxis",
        "กินยา", "ยาประจำตัว", "หลังผ่าตัด",
    ),
    Flag.DISORDERED_EATING: (
        "อดอาหาร", "ไม่กินข้าวเลย", "อดข้าว", "ล้วงคอ", "อาเจียนออก", "ทำให้อ้วก",
        "bulimia", "anorexia", "กินแล้วอ้วก", "ยาระบายลดน้ำหนัก",
        "กินวันละมื้อเดียวพอ", "0 แคล", "อดน้ำ",
    ),
    Flag.PREGNANCY: ("ตั้งครรภ์", "ท้องอยู่", "คนท้อง", "pregnant", "ให้นมบุตร", "breastfeeding"),
}

#: Age patterns like "อายุ 15", "15 ปี", "อายุ15ปี"
_AGE_RE = re.compile(r"(?:อายุ\s*)?(\d{1,2})\s*(?:ปี|ขวบ|years? old|yo\b)")
_AGE_PREFIX_RE = re.compile(r"อายุ\s*(\d{1,2})")

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
    return unicodedata.normalize("NFKC", text).lower()


def check(message: str) -> GuardResult:
    """Classify one user message. Never raises."""
    text = _normalise(message)
    flags: list[Flag] = []
    matched: dict[str, list[str]] = {}

    for flag, patterns in _PATTERNS.items():
        hits = [p for p in patterns if p in text]
        if hits:
            flags.append(flag)
            matched[str(flag)] = hits

    ages = [int(m) for m in _AGE_RE.findall(text)] + [int(m) for m in _AGE_PREFIX_RE.findall(text)]
    minor_ages = [a for a in ages if 5 <= a < 18]
    if minor_ages:
        flags.append(Flag.MINOR)
        matched[str(Flag.MINOR)] = [f"อายุ {a}" for a in minor_ages]

    oos = [p for p in _OUT_OF_SCOPE_PATTERNS if p in text]
    if oos:
        flags.append(Flag.OUT_OF_SCOPE)
        matched[str(Flag.OUT_OF_SCOPE)] = oos

    return GuardResult(flags=flags, matched=matched)


#: Extra system-prompt instructions injected when a flag fires.
FLAG_INSTRUCTIONS: dict[Flag, str] = {
    Flag.PED: (
        "ผู้ใช้ถามถึงสารเร่งกล้าม/ยา/ฮอร์โมน ห้ามให้ขนาดยา วิธีใช้ วิธีหาซื้อ หรือวิธีรอบยา (cycle) "
        "โดยเด็ดขาด ให้อธิบายเฉพาะว่าเป็นเรื่องที่ต้องอยู่ในการดูแลของแพทย์ ระบุความเสี่ยงโดยรวมสั้น ๆ "
        "แล้วเปลี่ยนไปเสนอแนวทางโภชนาการและการฝึกที่ถูกกฎหมายและปลอดภัยแทน"
    ),
    Flag.MEDICAL: (
        "ผู้ใช้กล่าวถึงโรคประจำตัวหรือการใช้ยา ให้เตือนอย่างชัดเจนว่าคำแนะนำทั่วไปอาจไม่เหมาะกับเขา "
        "และควรปรึกษาแพทย์หรือนักกำหนดอาหารวิชาชีพก่อนปรับอาหาร ห้ามวินิจฉัยหรือแนะนำการรักษา"
    ),
    Flag.DISORDERED_EATING: (
        "ข้อความมีสัญญาณของพฤติกรรมการกินที่อาจเป็นอันตราย ให้ตอบด้วยความเห็นอกเห็นใจ "
        "ไม่ตัดสิน ไม่ให้วิธีจำกัดอาหารที่รุนแรง อธิบายว่าการลดพลังงานมากเกินไปส่งผลเสียต่อกล้ามเนื้อและสุขภาพ "
        "และแนะนำให้ปรึกษาแพทย์หรือนักจิตวิทยา (สายด่วนสุขภาพจิต 1323)"
    ),
    Flag.MINOR: (
        "ผู้ใช้อาจอายุต่ำกว่า 18 ปี ห้ามแนะนำการลดพลังงานเพื่อลดน้ำหนักหรืออาหารเสริมใด ๆ "
        "ให้เน้นการกินให้ครบหมู่ พลังงานเพียงพอต่อการเจริญเติบโต และให้ปรึกษาผู้ปกครองกับแพทย์"
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
