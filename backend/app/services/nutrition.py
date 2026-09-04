"""Deterministic nutrition calculators.

These are pure functions. The LLM never does arithmetic for the user - it calls
``calc_nutrition_targets`` as a tool and reports the numbers this module returns.
Every returned payload carries the formula name and its reference so the answer
can cite where the number came from.

References
----------
- Mifflin MD, St Jeor ST, et al. "A new predictive equation for resting energy
  expenditure in healthy individuals." Am J Clin Nutr. 1990;51(2):241-247.
- Katch FI, McArdle WD. "Nutrition, Weight Control, and Exercise." (LBM-based RMR)
- Jager R, et al. "ISSN Position Stand: Protein and Exercise." JISSN. 2017;14:20.
- Morton RW, et al. "A systematic review, meta-analysis... protein supplementation
  on resistance training-induced gains." Br J Sports Med. 2018;52(6):376-384.
- Helms ER, Aragon AA, Fitschen PJ. "Evidence-based recommendations for natural
  bodybuilding contest preparation: nutrition and supplementation." JISSN. 2014;11:20.
- Iraki J, et al. "Nutrition Recommendations for Bodybuilders in the Off-Season."
  Sports (Basel). 2019;7(7):154.
- Thomas DT, Erdman KA, Burke LM. "ACSM/AND/DC Joint Position Statement: Nutrition
  and Athletic Performance." Med Sci Sports Exerc. 2016;48(3):543-568.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Sex = Literal["male", "female"]
Goal = Literal["cut", "bulk", "maintain"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

#: Physical Activity Level multipliers applied to BMR.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

ACTIVITY_LABELS_TH: dict[str, str] = {
    "sedentary": "แทบไม่ออกกำลังกาย (นั่งทำงานเป็นหลัก)",
    "light": "ออกกำลังกายเบา 1-3 วัน/สัปดาห์",
    "moderate": "ออกกำลังกายปานกลาง 3-5 วัน/สัปดาห์",
    "active": "ออกกำลังกายหนัก 6-7 วัน/สัปดาห์",
    "very_active": "ออกกำลังกายหนักมาก / ใช้แรงงานหนัก",
}

#: Fractional change applied to TDEE per goal, as (low, high).
GOAL_ENERGY_ADJUSTMENT: dict[str, tuple[float, float]] = {
    "cut": (-0.20, -0.15),
    "maintain": (0.0, 0.0),
    "bulk": (0.10, 0.15),
}

GOAL_LABELS_TH: dict[str, str] = {
    "cut": "ลดไขมัน (cut)",
    "maintain": "รักษาน้ำหนัก (maintain)",
    "bulk": "เพิ่มกล้ามเนื้อ (bulk)",
}

#: Protein g per kg bodyweight, as (low, high), per goal.
PROTEIN_G_PER_KG: dict[str, tuple[float, float]] = {
    "cut": (1.8, 2.2),
    "maintain": (1.6, 2.0),
    "bulk": (1.6, 2.0),
}

#: Fat g per kg bodyweight, as (low, high).
FAT_G_PER_KG: tuple[float, float] = (0.8, 1.0)

#: Fat must supply at least this share of total energy (Helms 2014).
MIN_FAT_ENERGY_SHARE = 0.20

#: The service is for adults: below this age the calculator refuses to produce
#: any target (NutritionInputError), which the profile route turns into a 422,
#: so an under-18 profile cannot be saved in the first place. Until 2026-09-03
#: the floor was 15 and a 15-year-old whose profile said goal=cut got a full
#: ~17% deficit labelled "safe" (eval/reports/safety_personalization_v1.md),
#: because the MINOR guardrail only read the message text. For rows written
#: before the floor moved, guardrails.check_profile still raises MINOR from the
#: stored birth_year and the chat path simply shows no numbers.
MINOR_AGE_LIMIT = 18
MAX_AGE = 100

#: WHO underweight threshold. No cut target is issued below it: the
#: energy-balance-cut-bulk card already says the already-lean should cut slower,
#: and someone under the clinical threshold should not self-manage a cut at all.
#: Only the *low* side of BMI is used for advice - the high side cannot separate
#: muscle from fat and would mislabel exactly this app's users.
BMI_UNDERWEIGHT = 18.5

#: Self-managed intake floor (energy-balance-cut-bulk card, "ข้อควรระวัง").
MIN_SELF_MANAGED_KCAL = 1200

#: Below this the macro split is reported with a warning rather than as a plan.
#: A lifter training several times a week has no business at ketogenic carb
#: levels by accident; when the leftover falls this low the cause is the
#: per-kg protein/fat rule meeting a high body weight, not a choice.
MIN_CARB_G = 100


class NutritionInputError(ValueError):
    """Raised when profile input is outside the range these formulas are valid for."""


@dataclass(frozen=True)
class ProfileInput:
    """The subset of a user profile the calculators need."""

    sex: Sex
    birth_year: int
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: Goal
    body_fat_pct: float | None = None
    training_days: int = 3
    restrictions: list[str] = field(default_factory=list)
    #: Optional only for rows written before the column existed. With a year
    #: alone, someone born in December 2008 counted as 18 from 1 Jan 2026 - three
    #: months of a 17-year-old passing the adult gate, which is the one gate this
    #: service is not allowed to get wrong.
    birth_month: int | None = None

    def age(self, today: datetime | None = None) -> int:
        """Completed years, rounded *down* when the month is known.

        The day is never stored, so in the birth month itself the birthday is
        assumed not to have happened yet. That errs by at most one month, in
        the direction that keeps a minor out rather than lets one in.
        """
        now = today or datetime.now(UTC)
        years = now.year - self.birth_year
        if self.birth_month is not None and now.month <= self.birth_month:
            years -= 1
        return years


def _validate(p: ProfileInput) -> None:
    if p.sex not in ("male", "female"):
        raise NutritionInputError("sex ต้องเป็น 'male' หรือ 'female'")
    if p.goal not in GOAL_ENERGY_ADJUSTMENT:
        raise NutritionInputError("goal ต้องเป็น 'cut', 'bulk' หรือ 'maintain'")
    if p.activity_level not in ACTIVITY_FACTORS:
        raise NutritionInputError(f"activity_level ต้องเป็นหนึ่งใน {list(ACTIVITY_FACTORS)}")
    age = p.age()
    if not MINOR_AGE_LIMIT <= age <= MAX_AGE:
        raise NutritionInputError(
            f"บริการนี้สำหรับผู้ที่อายุ {MINOR_AGE_LIMIT}-{MAX_AGE} ปี "
            f"ผู้ที่อายุต่ำกว่า {MINOR_AGE_LIMIT} ปีควรปรึกษาแพทย์หรือนักกำหนดอาหารร่วมกับผู้ปกครอง"
        )
    if not 120 <= p.height_cm <= 230:
        raise NutritionInputError("ส่วนสูงต้องอยู่ระหว่าง 120-230 ซม.")
    if not 30 <= p.weight_kg <= 300:
        raise NutritionInputError("น้ำหนักต้องอยู่ระหว่าง 30-300 กก.")
    if p.body_fat_pct is not None and not 3 <= p.body_fat_pct <= 60:
        raise NutritionInputError("เปอร์เซ็นต์ไขมันต้องอยู่ระหว่าง 3-60%")


def lean_body_mass(weight_kg: float, body_fat_pct: float) -> float:
    """Fat-free mass in kg."""
    return weight_kg * (1.0 - body_fat_pct / 100.0)


def bmi(weight_kg: float, height_cm: float) -> float:
    """Body mass index, kg/m^2."""
    height_m = height_cm / 100.0
    return weight_kg / (height_m * height_m)


def is_underweight(weight_kg: float, height_cm: float) -> bool:
    return bmi(weight_kg, height_cm) < BMI_UNDERWEIGHT


def bmr_mifflin_st_jeor(sex: Sex, weight_kg: float, height_cm: float, age: int) -> float:
    """Resting energy expenditure, Mifflin-St Jeor (1990)."""
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + 5.0 if sex == "male" else base - 161.0


def bmr_katch_mcardle(weight_kg: float, body_fat_pct: float) -> float:
    """Resting energy expenditure from lean mass, Katch-McArdle."""
    return 370.0 + 21.6 * lean_body_mass(weight_kg, body_fat_pct)


def calc_nutrition_targets(profile: ProfileInput) -> dict:
    """Compute BMR, TDEE, an energy target and a macro split.

    Returns a JSON-serialisable dict. This is the payload handed back to the LLM
    as a ``function_call_output``; the model is instructed to quote these numbers
    verbatim rather than recompute them.
    """
    _validate(profile)
    age = profile.age()

    if profile.body_fat_pct is not None:
        bmr = bmr_katch_mcardle(profile.weight_kg, profile.body_fat_pct)
        bmr_formula = "Katch-McArdle"
        bmr_reference = "Katch & McArdle - ใช้เมื่อทราบเปอร์เซ็นต์ไขมัน (แม่นกว่าเมื่อข้อมูลถูกต้อง)"
    else:
        bmr = bmr_mifflin_st_jeor(profile.sex, profile.weight_kg, profile.height_cm, age)
        bmr_formula = "Mifflin-St Jeor"
        bmr_reference = "Mifflin MD, St Jeor ST, et al. Am J Clin Nutr. 1990;51(2):241-247"

    activity_factor = ACTIVITY_FACTORS[profile.activity_level]
    tdee = bmr * activity_factor

    # --- goal: a cut is downgraded to maintenance when the profile is under the
    # underweight threshold (age needs no branch here: _validate already refused
    # anyone under 18). inputs.goal keeps what the user asked for; effective_goal
    # is what the numbers were built from, and the warning below tells the model
    # (and so the user) why they differ.
    bmi_value = bmi(profile.weight_kg, profile.height_cm)
    effective_goal: str = profile.goal
    deficit_suppressed_reason: str | None = None
    if profile.goal == "cut" and bmi_value < BMI_UNDERWEIGHT:
        effective_goal = "maintain"
        deficit_suppressed_reason = "underweight"

    adj_low, adj_high = GOAL_ENERGY_ADJUSTMENT[effective_goal]
    kcal_low = tdee * (1 + adj_low)
    kcal_high = tdee * (1 + adj_high)
    kcal_target = (kcal_low + kcal_high) / 2

    # --- protein ---
    p_low_per_kg, p_high_per_kg = PROTEIN_G_PER_KG[effective_goal]
    protein_g = profile.weight_kg * ((p_low_per_kg + p_high_per_kg) / 2)
    protein_kcal = protein_g * KCAL_PER_G_PROTEIN

    # --- fat: g/kg, but never below MIN_FAT_ENERGY_SHARE of energy ---
    f_low_per_kg, f_high_per_kg = FAT_G_PER_KG
    fat_g = profile.weight_kg * ((f_low_per_kg + f_high_per_kg) / 2)
    min_fat_g = (kcal_target * MIN_FAT_ENERGY_SHARE) / KCAL_PER_G_FAT
    fat_floor_applied = fat_g < min_fat_g
    fat_g = max(fat_g, min_fat_g)
    fat_kcal = fat_g * KCAL_PER_G_FAT

    # --- carbohydrate: whatever energy is left ---
    carb_kcal = kcal_target - protein_kcal - fat_kcal
    carb_g = carb_kcal / KCAL_PER_G_CARB
    carb_floor_applied = carb_g < 0
    if carb_floor_applied:
        carb_g = 0.0
        carb_kcal = 0.0

    warnings: list[str] = []
    if fat_floor_applied:
        warnings.append(
            "ปรับไขมันขึ้นให้ถึงขั้นต่ำ 20% ของพลังงานรวม เพื่อรักษาระดับฮอร์โมนและการดูดซึมวิตามินที่ละลายในไขมัน"
        )
    if carb_floor_applied:
        warnings.append(
            "พลังงานเป้าหมายต่ำเกินกว่าจะรองรับโปรตีนและไขมันขั้นต่ำได้ "
            "ควรลดการขาดดุลพลังงานลง หรือปรึกษานักกำหนดอาหาร"
        )
    if deficit_suppressed_reason == "underweight":
        warnings.append(
            f"BMI {bmi_value:.1f} ต่ำกว่าเกณฑ์ {BMI_UNDERWEIGHT} (น้ำหนักน้อยกว่าเกณฑ์) "
            "ระบบไม่กำหนดพลังงานขาดดุลให้ จึงปรับเป้าหมายพลังงานจากลดไขมันเป็นระดับรักษาน้ำหนัก "
            "(เท่ากับ TDEE) ควรปรึกษาแพทย์หรือนักกำหนดอาหารก่อนตัดสินใจลดไขมัน"
        )
    if kcal_target < MIN_SELF_MANAGED_KCAL:
        warnings.append(
            f"พลังงานเป้าหมายต่ำกว่า {MIN_SELF_MANAGED_KCAL:,} kcal/วัน ซึ่งต่ำเกินกว่าจะดูแลด้วยตนเอง "
            "แนะนำให้ปรึกษาแพทย์หรือนักกำหนดอาหารก่อน"
        )
    # Protein and fat are set per kg of *total* body weight, so at a high BMI
    # on a cut they can eat the whole energy budget: a 100 kg / 150 cm sedentary
    # cut came out at 200 g protein, 90 g fat and 5 g carbohydrate, and the
    # model quoted it as a plan. The numbers are not changed here - the split
    # is still the documented method - but the model is told the result is
    # not something to hand over as-is.
    if not carb_floor_applied and carb_g < MIN_CARB_G:
        warnings.append(
            f"คาร์โบไฮเดรตที่เหลือหลังหักโปรตีนและไขมันต่ำมาก ({carb_g:.0f} g/วัน ต่ำกว่า "
            f"{MIN_CARB_G} g) เพราะโปรตีนและไขมันคิดต่อน้ำหนักตัวทั้งหมด ซึ่งไม่เหมาะกับผู้ที่มี BMI สูง "
            "ให้บอกผู้ใช้ตรง ๆ ว่าสัดส่วนนี้ยังไม่ควรใช้จริง และควรให้นักกำหนดอาหารปรับโปรตีน"
            "ตามน้ำหนักเป้าหมายหรือมวลกล้ามเนื้อแทน"
        )

    return {
        "inputs": {
            "sex": profile.sex,
            "age": age,
            "height_cm": round(profile.height_cm, 1),
            "weight_kg": round(profile.weight_kg, 1),
            "body_fat_pct": profile.body_fat_pct,
            "activity_level": profile.activity_level,
            "activity_label_th": ACTIVITY_LABELS_TH[profile.activity_level],
            "activity_factor": activity_factor,
            "training_days": profile.training_days,
            "goal": profile.goal,
            "goal_label_th": GOAL_LABELS_TH[profile.goal],
            "restrictions": list(profile.restrictions),
        },
        "bmi": round(bmi_value, 1),
        "underweight": bmi_value < BMI_UNDERWEIGHT,
        "effective_goal": effective_goal,
        "effective_goal_label_th": GOAL_LABELS_TH[effective_goal],
        "deficit_suppressed_reason": deficit_suppressed_reason,
        "bmr_kcal": round(bmr),
        "bmr_formula": bmr_formula,
        "bmr_reference": bmr_reference,
        "tdee_kcal": round(tdee),
        "energy_target_kcal": round(kcal_target),
        "energy_target_range_kcal": [
            round(min(kcal_low, kcal_high)),
            round(max(kcal_low, kcal_high)),
        ],
        "energy_adjustment_pct": [round(adj_low * 100), round(adj_high * 100)],
        "macros": {
            "protein_g": round(protein_g),
            "protein_g_per_kg_range": [p_low_per_kg, p_high_per_kg],
            "protein_kcal": round(protein_kcal),
            "fat_g": round(fat_g),
            "fat_g_per_kg_range": [f_low_per_kg, f_high_per_kg],
            "fat_kcal": round(fat_kcal),
            "carb_g": round(carb_g),
            "carb_kcal": round(carb_kcal),
        },
        "warnings": warnings,
        "references": [
            bmr_reference,
            (
                "Jager R, et al. ISSN Position Stand: Protein and Exercise. JISSN. 2017;14:20 "
                "(โปรตีน 1.4-2.0 g/kg สำหรับผู้ฝึกแรงต้าน)"
            ),
            (
                "Morton RW, et al. Br J Sports Med. 2018;52(6):376-384 "
                "(จุดอิ่มตัวของโปรตีนราว 1.6 g/kg/วัน)"
            ),
            "Helms ER, et al. JISSN. 2014;11:20 (ช่วง cut: โปรตีนสูงขึ้น, ไขมันไม่ต่ำกว่า 20% ของพลังงาน)",
            (
                "Thomas DT, et al. ACSM/AND/DC Joint Position Statement. "
                "Med Sci Sports Exerc. 2016;48(3):543-568"
            ),
        ],
        "disclaimer": (
            "ตัวเลขนี้เป็นค่าประมาณจากสมการมาตรฐาน ไม่ใช่คำแนะนำทางการแพทย์ "
            "ควรปรับตามน้ำหนักจริงที่เปลี่ยนแปลงใน 2-4 สัปดาห์ และปรึกษาแพทย์หรือนักกำหนดอาหาร "
            "หากมีโรคประจำตัว ตั้งครรภ์ หรืออายุต่ำกว่า 18 ปี"
        ),
    }


def summarize_targets_th(targets: dict) -> str:
    """Thai summary injected into the system prompt as user context.

    Carries the calculator's ``warnings`` too. Before 2026-09-03 they were
    dropped here, and since the prompt tells the model to use these numbers
    without re-calling the tool, the model never saw them on the main path.
    """
    m = targets["macros"]
    i = targets["inputs"]
    goal_text = i["goal_label_th"]
    effective = targets.get("effective_goal")
    if effective and effective != i["goal"]:
        goal_text += f" → ระบบปรับเป็น {targets['effective_goal_label_th']}"
    bmi_text = f" | BMI {targets['bmi']}" if "bmi" in targets else ""
    line = (
        f"เป้าหมาย: {goal_text}{bmi_text} | BMR {targets['bmr_kcal']} kcal "
        f"({targets['bmr_formula']}) | TDEE {targets['tdee_kcal']} kcal | "
        f"พลังงานเป้าหมาย {targets['energy_target_kcal']} kcal/วัน | "
        f"โปรตีน {m['protein_g']} g, คาร์บ {m['carb_g']} g, ไขมัน {m['fat_g']} g"
    )
    warnings = targets.get("warnings") or []
    if warnings:
        line += "\nคำเตือนจากระบบคำนวณ (ต้องแจ้งผู้ใช้ให้ชัดเจน): " + " / ".join(warnings)
    return line
