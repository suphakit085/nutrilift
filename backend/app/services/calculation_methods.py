# ruff: noqa: RUF001
"""Visible provenance built from actual calculator operands, never from an LLM."""

from __future__ import annotations

import re

#: Which calculator steps each step's equation takes as input.
STEP_INPUTS = {
    "tdee": ("bmr",),
    "energy": ("tdee",),
    "fat": ("energy",),
    "carb": ("energy", "protein", "fat"),
}


def target_methods_note(
    answer: str, targets: dict | None, shown: list[str] | tuple[str, ...] = (),
) -> str:
    """Attach provenance when an answer quotes a calculated profile value.

    ``shown`` holds earlier assistant messages of this chat. A note whose every
    formula line is already there is not repeated: the 23 Oct retest saw the
    whole-day formula block appended again to a per-meal protein answer.
    """
    if not targets or not targets.get("calculation_methods"):
        return ""
    plain = answer.replace(",", "")
    labels = {
        "bmr": r"BMR|เผาผลาญพื้นฐาน", "tdee": r"TDEE|พลังงาน",
        "energy": r"พลังงาน|แคล|kcal", "protein": r"โปรตีน",
        "fat": r"ไขมัน", "carb": r"คาร์บ|คาร์โบไฮเดรต", "bmi": r"BMI",
    }
    selected = set()
    for method in targets["calculation_methods"]:
        value = str(method["result"])
        if (re.search(labels[method["key"]], plain, re.I)
                and re.search(r"(?<![\d.])" + re.escape(value) + r"(?![\d.])", plain)):
            selected.add(method["key"])
    # Every shown step's inputs are shown too, so no line uses a number the
    # reader cannot trace (e.g. the energy step multiplies the TDEE).
    pending = list(selected)
    while pending:
        for needed in STEP_INPUTS.get(pending.pop(), ()):
            if needed not in selected:
                selected.add(needed)
                pending.append(needed)
    note = methods_note([m for m in targets["calculation_methods"] if m["key"] in selected])
    lines = [line for line in note.splitlines() if line.startswith("- ")]
    if lines and any(all(line in earlier for line in lines) for earlier in shown):
        return ""
    return note


def methods_for_targets(targets: dict) -> list[dict]:
    d = targets["calculation_details"]

    def f(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")

    weight, height = d["weight_kg"], d["height_cm"]
    if targets["bmr_formula"] == "Mifflin-St Jeor":
        equation = f"10 × {f(weight)} + 6.25 × {f(height)} − 5 × {d['age']} + ({d['sex_constant']})"
        url = "https://pubmed.ncbi.nlm.nih.gov/2305711/"
        why = "ไม่มีข้อมูลเปอร์เซ็นต์ไขมัน จึงใช้สมการที่อาศัยเพศ อายุ น้ำหนัก และส่วนสูง"
    else:
        equation = f"370 + 21.6 × ({f(weight)} × (1 − {f(d['body_fat_pct'])}/100))"
        url = (
            "https://www.frontiersin.org/journals/nutrition/articles/10.3389/fnut.2025.1543263/full"
        )
        why = "มีเปอร์เซ็นต์ไขมัน จึงใช้มวลกายไร้ไขมันที่ประมาณจากข้อมูลนี้ ไม่ใช่ค่าที่ตรวจวัดการเผาผลาญจริง"
    methods = [
        {
            "key": "bmr",
            "name": targets["bmr_formula"],
            "equation": equation,
            "result": targets["bmr_kcal"],
            "unit": "kcal/วัน",
            "basis": why,
            "source_url": url,
        },
        {
            "key": "tdee",
            "name": "BMR × ตัวคูณกิจกรรม",
            "equation": f"{f(d['bmr_unrounded_kcal'])} × {f(d['activity_factor'])}",
            "result": targets["tdee_kcal"],
            "unit": "kcal/วัน",
            "basis": "ตัวคูณกิจกรรมตามระดับที่เลือก เป็นค่าประมาณตามกติกาเครื่องคำนวณ ไม่ใช่ผลวัดการใช้พลังงาน",
            "source_url": None,
        },
        {
            "key": "energy",
            "name": "ปรับพลังงานตามเป้าหมายที่อนุญาต",
            "equation": (f"{f(d['tdee_unrounded_kcal'])} × "
                         f"(1 + {f(d['energy_adjustment_fraction'])})"),
            "result": targets["energy_target_kcal"],
            "unit": "kcal/วัน",
            "basis": "กติกาโครงการ: ใช้ค่ากลางช่วงปรับพลังงาน และใช้เป้าหมายที่ผ่านการคัดกรองแล้ว",
            "source_url": None,
        },
        {
            "key": "protein",
            "name": "น้ำหนักตัว × โปรตีนต่อกิโลกรัม",
            "equation": f"{f(weight)} × {f(d['protein_g_per_kg'])}",
            "result": targets["macros"]["protein_g"],
            "unit": "กรัม/วัน",
            "basis": "เลือกอัตราตามเป้าหมายด้วยกติกาโครงการ ช่วงหลักฐานทั่วไปไม่ใช่ใบสั่งเฉพาะบุคคล",
            "source_url": "https://doi.org/10.1186/s12970-017-0177-8",
        },
        {
            "key": "fat",
            "name": "ค่าสูงกว่าระหว่างไขมันต่อน้ำหนักกับ floor พลังงาน",
            "equation": (f"max({f(weight)} × 0.9, "
                         f"{f(d['energy_target_unrounded_kcal'])} × 0.20 ÷ 9)"),
            "result": targets["macros"]["fat_g"],
            "unit": "กรัม/วัน",
            "basis": "0.9 กรัม/กก. และ floor 20% เป็นกติกาโครงการ ไม่ใช่เกณฑ์ขั้นต่ำสากล",
            "source_url": None,
        },
        {
            "key": "carb",
            "name": "พลังงานที่เหลือหลังหักโปรตีนและไขมัน",
            "equation": (f"max(0, ({f(d['energy_target_unrounded_kcal'])} "
                         f"− 4 × {f(d['protein_unrounded_g'])} "
                         f"− 9 × {f(d['fat_unrounded_g'])}) ÷ 4)"),
            "result": targets["macros"]["carb_g"],
            "unit": "กรัม/วัน",
            "basis": "ใช้ 4 kcal/กรัมโปรตีนและคาร์บ และ 9 kcal/กรัมไขมัน คำนวณด้วยค่าก่อนปัด",
            "source_url": None,
        },
        {
            "key": "bmi",
            "name": "BMI",
            "equation": f"{f(weight)} ÷ ({f(height)} ÷ 100)²",
            "result": targets["bmi"],
            "unit": "kg/m²",
            "basis": "ใช้คัดกรองเบื้องต้น ไม่แยกมวลกล้ามเนื้อจากไขมันและไม่วินิจฉัยภาวะทุพโภชนาการ",
            "source_url": "https://www.who.int/data/nutrition/nlis/info/malnutrition-in-women",
        },
    ]
    return methods


def methods_note(methods: list[dict] | None) -> str:
    if not methods:
        return ""
    lines = ["", "", "### สูตรที่ใช้กับเป้าหมายนี้"]
    for item in methods:
        name = f"[{item['name']}]({item['source_url']})" if item.get("source_url") else item["name"]
        lines.append(
            f"- {name}: {item['equation']} ≈ {item['result']} {item['unit']} — {item['basis']}"
        )
    lines.append("ใช้ค่าก่อนปัดในการคำนวณ และปัดเฉพาะตัวเลขที่แสดง ผลเป็นค่าประมาณ ไม่ใช่แผนรักษาโรค")
    return "\n".join(lines)
