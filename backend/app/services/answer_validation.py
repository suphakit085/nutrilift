"""Bounded checks on model prose before it becomes a displayed answer.

These checks enforce explicit constraints and detect unsupported percentages.
They do not prove semantic entailment or replace a human evidence review.
"""

import json
import re
from decimal import Decimal

from app.services.request_constraints import excludes_dose
from app.services.thai_text import normalize_thai

_CITATION = re.compile(r"\[S\d+(?:[\s,;]+S\d+)*\]", re.I)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.]\d+)?")


def normalize_answer_terms(answer: str) -> str:
    """Normalize known mixed-script spellings, not arbitrary foreign words.

    This is a terminology correction, not replacement of a generated answer.
    Localize known week units only after a number; evidence validation still
    rejects a fixed interval not supported by the supplied passages.
    """
    answer = answer.replace("เซ\u05d8\u05d9\u05dd", "เซต")
    return re.sub(
        r"(?<=\d)\s*(?:semaines?|minggu|wochen|semanas)\b",
        " สัปดาห์",
        answer,
        flags=re.I,
    )


def without_target_citations(answer: str, targets: dict | None) -> str:
    """Keep calculator provenance separate from adjacent research citations."""
    if not targets:
        return answer
    previous_end = 0
    calculated = False

    def keep(match: re.Match) -> str:
        nonlocal previous_end, calculated
        clause = answer[previous_end : match.start()]
        previous_end = match.end()
        if clause.strip():
            clause = re.split(r"\n|;|(?<=[!?])\s+", clause)[-1].replace("*", "").replace(",", "")
            folded = normalize_thai(clause)
            research = re.search(
                normalize_thai(r"งานวิจัย|บททบทวน|การทดลอง|งานศึกษา|หลักฐานทั่วไป"), folded
            )
            calculated = False
            for method in targets.get("calculation_methods", []):
                name = {
                    "energy": "พลังงาน|แคล",
                    "protein": "โปรตีน",
                    "fat": "ไขมัน",
                    "carb": "คาร์บ|คาร์โบไฮเดรต",
                    "bmi": "bmi",
                    "bmr": "bmr",
                    "tdee": "tdee",
                }[method["key"]]
                if (
                    not research
                    and re.search(name, folded, re.I)
                    and re.search(
                        r"(?<![\d.])" + re.escape(str(method["result"])) + r"(?![\d.])", clause
                    )
                ):
                    calculated = True
                    break
        return "" if calculated else match.group()

    return _CITATION.sub(keep, answer)


def requested_format(message: str) -> tuple[str, int | None] | None:
    text = normalize_thai(message)
    only = re.search(normalize_thai(r"เท่านั้น|ไม่มีบทนำ|ไม่มีข้อความนอก|only"), text)
    if re.search(r"\bjson\b", text) and only:
        return ("json", None)
    if re.search(normalize_thai(r"ตาราง|table"), text) and only:
        return ("table", None)
    count = re.search(normalize_thai(r"(?:จำนวน|แค่|เพียง)?\s*(\d{1,2})\s*(?:ข้อ|bullets?)"), text)
    if count and re.search(r"bullet", text) and only:
        return ("bullets", int(count.group(1)))
    return None


def format_issue(answer: str, spec: tuple[str, int | None] | None) -> str | None:
    if not spec:
        return None
    kind, count = spec
    lines = [line for line in answer.splitlines() if line.strip()]
    if kind == "json":
        try:
            value = json.loads(answer)
            if isinstance(value, dict):
                return None
        except ValueError:
            pass
        return "ต้องตอบเป็น JSON object ที่ parse ได้ ไม่มี code fence หรือข้อความนอก JSON"
    if kind == "table":
        cells = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
        if (
            len(lines) >= 3
            and all(line.strip().startswith("|") and line.strip().endswith("|") for line in lines)
            and len(cells[0]) >= 2
            and all(len(row) == len(cells[0]) for row in cells)
            and all(re.fullmatch(r":?-+:?", c) for c in cells[1])
        ):
            return None
        return "ตอบเป็นตาราง Markdown เท่านั้น ไม่มีบทนำหรือข้อความท้าย ใส่ข้อจำกัดไว้ในเซลล์"
    if kind == "bullets":
        if (
            lines
            and lines[0].startswith("- ")
            and sum(line.startswith("- ") for line in lines) == count
            and all(line.startswith(("- ", " ", "\t")) for line in lines)
        ):
            return None
        return f"ตอบด้วย bullet ที่ขึ้นต้น - จำนวน {count} ข้อเท่านั้น ไม่มีบทนำหรือบทสรุป"
    return None


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(n.group()) for n in _NUMBER.finditer(text)}


def answer_issues(message: str, answer: str, passages: list[dict], *, use_rag: bool) -> list[str]:
    issues = []
    # Technical Latin/Greek terms are valid; unrelated alphabets absent from
    # the question and evidence are output artifacts, not facts to guess at.
    if re.search(r"[ก-๙]", message):
        supplied = message + "\n".join(p.get("content", "") for p in passages)
        for alphabet in [
            r"[\u0400-\u04ff]",
            r"[\u0590-\u06ff]",
            r"[\u0900-\u097f]",
            r"[\u3040-\u30ff\u4e00-\u9fff]",
        ]:
            if re.search(alphabet, answer) and not re.search(alphabet, supplied):
                issues.append("มีตัวอักษรภาษาอื่นแทรกโดยไม่มีในคำถามหรือหลักฐาน ให้เขียนคำอธิบายไทยที่สมบูรณ์")
                break
    issue = format_issue(answer, requested_format(message))
    if issue:
        issues.append(issue)
    if excludes_dose(message) and re.search(
        r"\d+(?:[.]\d+)?(?:\s*[-\u2013]\s*\d+(?:[.]\d+)?)?\s*"
        r"(?:กรัม|มิลลิกรัม|mg|grams?|g)\s*(?:/|ต่อ|per)\s*(?:วัน|ครั้ง|day|dose)",
        answer,
        re.I,
    ):
        issues.append("ผู้ใช้ระบุว่าไม่ขอโดส ห้ามให้ขนาดใช้ ตารางโหลด หรือปริมาณต่อวัน/ต่อครั้ง")
    if use_rag and passages:
        # Match a numeric percentage/range against the specific cited context.
        # A cut percentage somewhere else in the corpus cannot substantiate bulk.
        by_label = {p.get("label", "").upper(): p.get("content", "") for p in passages}
        tracking = re.search(
            normalize_thai(r"ติดตาม|ความก้าวหน้า|track|progress"), normalize_thai(message)
        )
        for line in answer.splitlines():
            percentages = re.findall(
                r"\d+(?:[.]\d+)?(?:\s*[-\u2013]\s*\d+(?:[.]\d+)?)?\s*(?:%|เปอร์เซ็นต์)", line
            )
            intervals = (
                re.findall(
                    r"\d+(?:[.]\d+)?\s*[-\u2013]\s*\d+(?:[.]\d+)?\s*(?:วัน|สัปดาห์|เดือน)",
                    line,
                )
                if tracking
                else []
            )
            if not percentages and not intervals:
                continue
            labels = [
                label.upper()
                for group in _CITATION.findall(line)
                for label in re.findall(r"S\d+", group, re.I)
            ]
            # Uncited numerical prescriptions must also be supported by supplied
            # context. Personal calculator answers bypass model generation.
            evidence = (
                "\n".join(by_label.get(label, "") for label in labels)
                if labels
                else "\n".join(by_label.values())
            )
            available = _numbers(evidence)
            compact_evidence = re.sub(r"\s+", "", normalize_thai(evidence)).replace("\u2013", "-")
            if any(
                re.sub(r"\s+", "", normalize_thai(value)).replace("\u2013", "-")
                not in compact_evidence
                for value in intervals
            ):
                issues.append("ช่วงเวลาติดตามที่กำหนดไม่มีในข้อความหลักฐาน ห้ามตั้งช่วงตายตัวจากความจำ")
                break
            if any(not _numbers(value) <= available for value in percentages):
                issues.append(
                    "เปอร์เซ็นต์ที่ตอบไม่มีในข้อความหลักฐานที่ใช้อ้าง "
                    "ห้ามเติมอัตราหรือย้ายเกณฑ์ cut ไป bulk ถ้าหลักฐานไม่พอให้ระบุตรง ๆ"
                )
                break
    return issues


def repair_instruction(issues: list[str]) -> str:
    return (
        "ตรวจคำตอบร่างก่อนแสดง พบเงื่อนไขที่ต้องแก้:\n- "
        + "\n- ".join(issues)
        + "\nตอบคำถามเดิมใหม่ทั้งคำตอบ คงข้อจำกัดและที่มาที่ถูกต้อง ห้ามแต่งข้อมูลเพิ่ม "
        "ไม่กล่าวถึงขั้นตอนตรวจหรือคำตอบร่าง หากหลักฐานไม่พอให้บอกข้อจำกัดตามรูปแบบที่ผู้ใช้ขอ"
    )
