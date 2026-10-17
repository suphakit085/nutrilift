"""Build one day's menu that hits the user's macro targets.

Same principle as ``nutrition.py``: the numbers come from Python, not from the
model. The LLM is told to call ``suggest_day_menu`` and report what comes back,
because a menu is a *sum* - a model that invents portions produces a plan whose
totals do not add up to the targets it just quoted, and nothing in the answer
would show that. Here the totals are computed from ``foods`` rows (the same
table ``lookup_food`` reads, every row carrying its ``source``), the deviation
from target is reported alongside them, and a plan that cannot reach the target
says so instead of being presented as if it had.

Pipeline, all deterministic - the same profile and ``variant`` always give the
same menu:

1. filter the food table by the profile's restrictions (conservative: a rule
   that might apply excludes the food) and drop rows whose macros are still
   estimates (``source`` starting with ``TOVERIFY``), since every number here
   is summed into a total compared against a target;
2. rank each role's candidates by how cleanly they serve that role, then rotate
   by ``variant`` so "ขออีกแบบ" gives a different menu without any randomness;
3. fill main meals and optional supplemental meals, preferring an unused
   food *category* per role, so the day is not four servings of the same fish;
4. solve bounded portions, prioritising meal size and daily feasibility before meal balance
   and preferred portions; independently validate the final reported numbers.

Food composition references stay unchanged. Planning uses a gram grid per food
kind, or whole units for countable foods, rather than treating a per-100-g
nutrient reference as a customary serving.
"""

from __future__ import annotations

import json
import math
import re
from copy import copy
from dataclasses import dataclass, field

from app.services.meal_portions import PORTION_POLICY_VERSION, PortionPolicy, portion_policy
from app.services.thai_text import normalize_thai

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

#: How far the finished plan may sit from each target before it is reported as
#: not meeting it. Protein is the tightest because it is the target the training
#: population actually cares about hitting; fat and carb are allowed to trade
#: against each other as long as energy lands close.
TOLERANCE: dict[str, float] = {
    "protein_g": 0.10,
    "carb_g": 0.15,
    "fat_g": 0.15,
    "kcal": 0.07,
}

#: Relative weights in the objective, mirroring the tolerances above.
_ERROR_WEIGHTS: dict[str, float] = {"protein_g": 2.0, "kcal": 1.5, "carb_g": 1.0, "fat_g": 1.0}

_OPTIMIZER_PASSES = 12


class MealPlanError(ValueError):
    """Raised when no menu can be built at all (e.g. restrictions leave no
    protein source). Distinct from a menu that was built but missed a target -
    that comes back as a plan with ``within_tolerance`` False."""


# ---------------------------------------------------------------------------
# Thai text normalisation
# ---------------------------------------------------------------------------

#: foods.csv spells "น้ำ" two ways because its rows come from three source
#: documents, and a plain substring test for "น้ำปลา" misses whichever spelling
#: it was not written with. Folding lives in app/services/thai_text.py because
#: guardrails.py had the same class of bug on the safety keywords.


def _contains(haystack: str, needle: str) -> bool:
    return normalize_thai(needle) in haystack


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

#: A role needs both gates: the food must come from the right *food group*, and
#: its own macro profile must actually deliver that macro. The category gate
#: alone would let ketchup anchor a carb slot; the macro gate alone ranked
#: chicken-essence drink (32 kcal, 8 g protein) as the best protein in the
#: table, because nothing else in it contributes any energy.
_ROLE_CATEGORIES: dict[str, frozenset[str]] = {
    "protein": frozenset(
        {
            "เนื้อสัตว์",
            "ปลาและอาหารทะเล",
            "ไข่",
            "ไข่-นม",
            "นมและผลิตภัณฑ์",
            "ถั่วและเมล็ด",
            "โปรตีนพืช",
            "กับข้าว",
            # whey is the one row here (USDA 173180); a post-training shake is what
            # this app's users actually drink, and the macro gates below still apply
            "อาหารเสริม",
        }
    ),
    "carb": frozenset({"ข้าว-แป้ง", "หัวและมันต่าง ๆ"}),
    "fat": frozenset({"ถั่วและเมล็ด", "น้ำมันและไขมัน", "ไข่", "ไข่-นม"}),
    "vegetable": frozenset({"ผัก"}),
    "fruit": frozenset({"ผลไม้"}),
}

_MIN_PROTEIN_ENERGY_SHARE = 0.35
_MIN_CARB_ENERGY_SHARE = 0.55
_MIN_FAT_ENERGY_SHARE = 0.55

#: Anchors have to be worth building a meal around; these keep out rows that
#: pass the share test only because they are nearly calorie-free.
_MIN_PROTEIN_G_FOR_ANCHOR = 8.0
_MIN_CARB_G_FOR_ANCHOR = 15.0
_MIN_KCAL_FOR_ANCHOR = 50.0

#: Composition tables list grains and noodles by *dry* weight, and those rows
#: cannot be served as a portion - "ข้าวเจ้า, พันธุ์ต่างๆ 100 กรัม" is a cup of
#: raw rice, not a meal. Within ข้าว-แป้ง the split is clean and wide: cooked
#: staples run 77-150 kcal per 100 g, dry ones 345-374, while bread (273) and
#: other ready-to-eat items stay below the line.
_MAX_COOKED_STAPLE_KCAL_PER_100G = 300.0
_DRY_STAPLE_CATEGORIES = frozenset({"ข้าว-แป้ง"})


def _kcal_per_100g(food: dict) -> float:
    serving_g = float(food.get("serving_g") or 0)
    return float(food["kcal"]) / serving_g * 100.0 if serving_g > 0 else float(food["kcal"])


#: Names that disqualify a row from every role: condiments, sweetened packing
#: liquid, and preparations nobody serves as a portion.
_NAME_EXCLUSIONS: tuple[str, ...] = (
    "ผงชูรส",
    "เกลือ",
    "น้ำปลา",
    "ซีอิ๊ว",
    "กะปิ",
    "น้ำตาล",
    "ซอส",
    "น้ำเชื่อม",
    "น้ำสลัด",
    "กะทิ",
    "ผงปรุงรส",
    "แป้ง",
)

#: Deprioritised, not excluded: still real food, but a menu should reach for the
#: cooked/fresh form first. Applied as a multiplier on the role score.
_LOW_PRIORITY_TOKENS: tuple[str, ...] = ("ดิบ", "แห้ง", "รมควัน", "เค็ม", "หวาน", "ทอด", "กระป๋อง")
_LOW_PRIORITY_FACTOR = 0.75


def _energy_share(grams: float, kcal_per_g: float, kcal: float) -> float:
    return (grams * kcal_per_g) / kcal if kcal > 0 else 0.0


def roles_of(food: dict) -> frozenset[str]:
    """Which meal roles this food can fill."""
    category = (food.get("category") or "").strip()
    name = normalize_thai(food.get("name_th") or "")
    if any(_contains(name, bad) for bad in _NAME_EXCLUSIONS):
        return frozenset()

    kcal = float(food["kcal"])
    if kcal <= 0:
        return frozenset()
    protein = float(food["protein_g"])
    carb = float(food["carb_g"])
    fat = float(food["fat_g"])

    roles: set[str] = set()
    if (
        category in _ROLE_CATEGORIES["protein"]
        and kcal >= _MIN_KCAL_FOR_ANCHOR
        and protein >= _MIN_PROTEIN_G_FOR_ANCHOR
        and _energy_share(protein, KCAL_PER_G_PROTEIN, kcal) >= _MIN_PROTEIN_ENERGY_SHARE
    ):
        roles.add("protein")
    if category in _ROLE_CATEGORIES["carb"] and kcal >= _MIN_KCAL_FOR_ANCHOR:
        dry = (
            category in _DRY_STAPLE_CATEGORIES
            and _kcal_per_100g(food) >= _MAX_COOKED_STAPLE_KCAL_PER_100G
        )
        if (
            not dry
            and carb >= _MIN_CARB_G_FOR_ANCHOR
            and _energy_share(carb, KCAL_PER_G_CARB, kcal) >= _MIN_CARB_ENERGY_SHARE
        ):
            roles.add("carb")
    if (
        category in _ROLE_CATEGORIES["fat"]
        and _energy_share(fat, KCAL_PER_G_FAT, kcal) >= _MIN_FAT_ENERGY_SHARE
    ):
        roles.add("fat")
    if category in _ROLE_CATEGORIES["vegetable"]:
        roles.add("vegetable")
    if category in _ROLE_CATEGORIES["fruit"]:
        roles.add("fruit")
    return frozenset(roles)


def _role_score(food: dict, role: str) -> float:
    """How cleanly a food serves a role - higher sorts first."""
    kcal = float(food["kcal"])
    if role == "protein":
        base = _energy_share(float(food["protein_g"]), KCAL_PER_G_PROTEIN, kcal)
    elif role == "carb":
        base = _energy_share(float(food["carb_g"]), KCAL_PER_G_CARB, kcal)
    elif role == "fat":
        base = _energy_share(float(food["fat_g"]), KCAL_PER_G_FAT, kcal)
    else:
        # Vegetables and fruit are picked for fibre per calorie, not for a macro.
        fiber = float(food.get("fiber_g") or 0.0)
        base = fiber / kcal if kcal > 0 else 0.0
    name = normalize_thai(food.get("name_th") or "")
    if any(_contains(name, token) for token in _LOW_PRIORITY_TOKENS):
        base *= _LOW_PRIORITY_FACTOR
    return base


# ---------------------------------------------------------------------------
# Dietary restrictions
# ---------------------------------------------------------------------------

#: Restriction -> (name substrings, categories) that must be excluded.
#:
#: Deliberately over-broad: these come from a user who ticked "แพ้ถั่ว" on their
#: profile, so a false exclusion costs them one food option while a missed one
#: hands an allergic person a menu they cannot eat. Anything a rule *might*
#: cover is excluded, and `excluded_counts` in the result reports how much each
#: rule removed so the answer can explain why the menu looks narrow.
_MEAT_TOKENS = (
    "หมู",
    "ไก่",
    "เนื้อ",
    "วัว",
    "เป็ด",
    "ปลา",
    "กุ้ง",
    "หอย",
    "ปู",
    "ปลาหมึก",
    "แฮม",
    "เบคอน",
    "ไส้กรอก",
    "ลูกชิ้น",
    "ตับ",
    "เลือด",
    "กระเพาะ",
    "ขาหมู",
    "น้ำปลา",
    "กะปิ",
)
_MEAT_CATEGORIES = frozenset({"เนื้อสัตว์", "ปลาและอาหารทะเล"})
#: Thai writes compounds without spaces, so a short token matches inside
#: unrelated words: a bare "นม" hits ขนมปัง (bread) and แหนม (fermented pork).
#: Dairy is caught by the category gate; these spell out the forms that appear
#: as free-standing names, none shorter than three characters.
_DAIRY_TOKENS = (
    "นมวัว",
    "นมสด",
    "นมจืด",
    "นมข้น",
    "นมผง",
    "นมเปรี้ยว",
    "นมพร่อง",
    "นมถั่ว",
    "ชีส",
    "เนย",
    "โยเกิร์ต",
    "เวย์",
    "ครีม",
)

#: The same no-spaces problem in the other direction: "ไข่ไก่" contains "ไก่"
#: and "ไข่เป็ด" contains "เป็ด", so the meat tokens excluded every egg from a
#: lacto-ovo vegetarian's menu - which is what made มังสวิรัติ come out with
#: *less* protein than วีแกน in the sweep. Before matching, these compounds are
#: collapsed to plain "ไข่" for the restrictions that permit eggs. "ไข่ปลา"
#: (roe) is deliberately absent: it really is fish.
_EGG_COMPOUNDS = ("ไข่ไก่", "ไข่เป็ด", "ไข่นกกระทา", "ไข่ห่าน")
_RESTRICTIONS_EXCLUDING_EGGS = frozenset({"วีแกน", "ไม่กินไข่"})

_RESTRICTION_RULES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "ไม่กินไก่": (("ไก่", "chicken"), frozenset()),
    "ไม่กินไข่": (("ไข่", "egg"), frozenset({"ไข่", "ไข่-นม"})),
    "แพ้ถั่วเหลือง": (
        ("ถั่วเหลือง", "เต้าหู้", "เต้าเจี้ยว", "เทมเป้", "โปรตีนเกษตร", "soy"),
        frozenset(),
    ),
    "ฮาลาล": (
        # blood and amphibians are haram alongside pork and alcohol; the ASEAN
        # table has boiled chicken/duck blood and frog as plain "เนื้อสัตว์" rows
        (
            "หมู",
            "แฮม",
            "เบคอน",
            "ไส้กรอก",
            "ขาหมู",
            "เลือด",
            "กบ",
            "เขียด",
            "สุรา",
            "เบียร์",
            "ไวน์",
            "เหล้า",
            "แอลกอฮอล์",
        ),
        frozenset(),
    ),
    "มังสวิรัติ": (_MEAT_TOKENS, _MEAT_CATEGORIES),
    "วีแกน": (
        _MEAT_TOKENS + _DAIRY_TOKENS + ("ไข่", "น้ำผึ้ง"),
        _MEAT_CATEGORIES | frozenset({"ไข่", "นมและผลิตภัณฑ์", "ไข่-นม"}),
    ),
    "แพ้นมวัว": (
        tuple(t for t in _DAIRY_TOKENS if t != "นมถั่ว"),  # soy milk is not cow's milk
        frozenset({"นมและผลิตภัณฑ์"}),
    ),
    "แพ้ถั่ว": (
        (
            "ถั่ว",
            "เต้าหู้",
            "เต้าเจี้ยว",
            "นัต",
            "อัลมอนด์",
            "แมคคาเดเมีย",
            "พิสตาชิโอ",
            "งา",
            "เม็ดมะม่วงหิมพานต์",
            "มะม่วงหิมพานต์",
            "โปรตีนเกษตร",
        ),
        frozenset({"ถั่วและเมล็ด", "โปรตีนพืช"}),
    ),
    "แพ้อาหารทะเล": (
        ("ปลา", "กุ้ง", "หอย", "ปู", "ปลาหมึก", "กะปิ", "น้ำปลา", "ทะเล", "สาหร่าย"),
        frozenset({"ปลาและอาหารทะเล"}),
    ),
    "ไม่กินเนื้อวัว": (("เนื้อวัว", "วัว", "เนื้อโค", "beef"), frozenset()),
}


def _collapse_egg_compounds(name: str) -> str:
    for compound in _EGG_COMPOUNDS:
        name = name.replace(normalize_thai(compound), normalize_thai("ไข่"))
    return name


def excluded_by(food: dict, restrictions: list[str] | tuple[str, ...]) -> str | None:
    """The first restriction that rules this food out, or None."""
    raw = normalize_thai((food.get("name_th") or "") + " " + (food.get("name_en") or ""))
    egg_safe = _collapse_egg_compounds(raw)
    category = (food.get("category") or "").strip()
    for restriction in restrictions:
        key = restriction.strip()
        rule = _RESTRICTION_RULES.get(key)
        if rule is None:
            continue  # unknown restriction: reported separately, never silently applied
        names, categories = rule
        name = raw if key in _RESTRICTIONS_EXCLUDING_EGGS else egg_safe
        if category in categories or any(_contains(name, token) for token in names):
            return restriction
    return None


# ---------------------------------------------------------------------------
# Meal template
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One role to fill within a meal, with the portion range allowed for it."""

    role: str
    min_mult: float
    max_mult: float
    #: Cap in grams of the food itself, so "3 servings" of a 100 g row cannot
    #: turn into 600 g of chicken breast.
    max_grams: float = 400.0
    optional: bool = False


@dataclass(frozen=True)
class Meal:
    key: str
    label_th: str
    slots: tuple[Slot, ...]


#: Four eating occasions. Two of them carry an explicit fat slot: without one,
#: the ranking picks the leanest protein and the purest starch for every slot,
#: and the finished day lands ~90% short of the fat target while every other
#: macro is on. The post-training slot is protein + fruit because that is the
#: pairing the nutrient-timing card describes; nothing here depends on training
#: time, which the profile does not record.
MEAL_TEMPLATE: tuple[Meal, ...] = (
    Meal(
        "breakfast",
        "มื้อเช้า",
        (
            Slot("protein", 0.25, 3.0, 300),
            Slot("carb", 0.5, 5.0, 350),
            Slot("fruit", 0.5, 2.0, 300),
            # 110 g = two whole eggs, the breakfast fat of choice now that eggs
            # are portioned whole (a 50 g cap allowed exactly one)
            Slot("fat", 0.25, 2.0, 110),
        ),
    ),
    Meal(
        "lunch",
        "มื้อกลางวัน",
        (
            Slot("protein", 0.25, 3.0, 300),
            Slot("carb", 0.5, 8.0, 500),
            Slot("vegetable", 0.5, 2.0, 250),
            Slot("fat", 0.25, 2.0, 110),
        ),
    ),
    Meal(
        "dinner",
        "มื้อเย็น",
        (
            Slot("protein", 0.25, 3.0, 300),
            Slot("carb", 0.5, 8.0, 500),
            Slot("vegetable", 0.5, 2.0, 250),
            Slot("fat", 0.25, 2.0, 110),
        ),
    ),
    Meal(
        "snack",
        "มื้อว่าง / หลังฝึก",
        (
            Slot("protein", 0.5, 2.5, 250, optional=True),
            Slot("carb", 0.5, 4.0, 300),
            Slot("fruit", 0.5, 2.0, 300),
        ),
    ),
)

# Three meals are solved directly. Fruit can accompany dinner; there is no
# post-solve movement of a fourth meal's protein into breakfast.
THREE_MEAL_TEMPLATE: tuple[Meal, ...] = (
    Meal("breakfast", "มื้อเช้า", (
        MEAL_TEMPLATE[0].slots[0], Slot("carb", 0.5, 8.0, 400),
        *MEAL_TEMPLATE[0].slots[2:],
    )),
    MEAL_TEMPLATE[1],
    Meal(
        "dinner", "มื้อเย็น",
        (*MEAL_TEMPLATE[2].slots, Slot("fruit", 0.5, 3.0, 300)),
    ),
)

_MEAL_SHARES = {
    3: {"breakfast": 0.30, "lunch": 0.35, "dinner": 0.35},
    4: {"breakfast": 0.25, "lunch": 0.30, "dinner": 0.30, "snack": 0.15},
}

# Computational search bounds, not a recommendation that everyone eat six times.
MAX_SUPPLEMENTAL_MEALS = 3
MAIN_MEAL_WEIGHT_G = 750.0
SUPPLEMENTAL_MEAL_WEIGHT_G = 350.0


def meal_template(count: int, practical: bool = False) -> tuple[Meal, ...]:
    if type(count) is not int or not 3 <= count <= 3 + MAX_SUPPLEMENTAL_MEALS:
        raise MealPlanError("ระบบจัด 3 มื้อหลักและมื้อเสริมได้ 0–3 มื้อ กรุณาระบุจำนวนรวม 3–6 มื้อ")
    if not practical and count == 4:
        return MEAL_TEMPLATE
    extras = tuple(
        Meal("snack" if n == 1 else f"snack_{n}", f"มื้อเสริมที่ {n}", (
            Slot("protein", 0.25, 2, 150, optional=True),
            Slot("carb", 0.5, 4, 200),
            Slot("fruit", 0.5, 2, 150, optional=True),
            Slot("fat", 0.25, 2, 30, optional=True),
        )) for n in range(1, count - 2)
    )
    return (*THREE_MEAL_TEMPLATE, *extras)


def _meal_shares(count: int) -> dict[str, float]:
    if count in _MEAL_SHARES:
        return _MEAL_SHARES[count]
    extra_share = 0.12 * (count - 3)
    return {
        **{key: value * (1 - extra_share) for key, value in _MEAL_SHARES[3].items()},
        **{("snack" if n == 1 else f"snack_{n}"): 0.12 for n in range(1, count - 2)},
    }


def _upper_grams(food: dict, slot: Slot, practical: bool) -> float:
    policy = portion_policy(food, slot.role)
    cap = min(slot.max_grams, policy.max_g)
    if practical:
        preferred = policy.preferred_max_g
        if _is_countable(food):
            # Two ordinary eggs should not fail a gram preference designed for
            # generic fats. Unit counts still intersect the source/slot caps.
            preferred = max(preferred, 2 * float(food["serving_g"]))
        cap = min(cap, preferred)
    return cap


# ---------------------------------------------------------------------------
# Portion solving
# ---------------------------------------------------------------------------


@dataclass
class _Item:
    food: dict
    meal: Meal
    slot: Slot
    mult: float
    practical: bool = False
    lo: float = field(init=False)
    hi: float = field(init=False)
    choices: list[float] = field(init=False, default_factory=list)
    policy: PortionPolicy = field(init=False)

    def __post_init__(self) -> None:
        serving_g = float(self.food.get("serving_g") or 0)
        if not math.isfinite(serving_g) or serving_g <= 0:
            raise MealPlanError("น้ำหนักอ้างอิงของอาหารไม่ถูกต้อง")
        self.policy = portion_policy(self.food, self.slot.role)
        self.lo = self.policy.min_g / serving_g
        if self.policy.key == "role-fallback":
            self.lo = max(self.lo, self.slot.min_mult)
        self.hi = _upper_grams(self.food, self.slot, self.practical) / serving_g
        if _is_countable(self.food):
            self.hi = min(self.hi, self.slot.max_mult)
        if self.lo > self.hi:
            raise MealPlanError("ขอบเขตปริมาณอาหารไม่มีช่วงที่ใช้ได้")
        self.choices = [g / serving_g for g in _grid(
            self.lo * serving_g, self.hi * serving_g, self.policy.step_g
        )]
        if _is_countable(self.food):
            whole = [float(n) for n in range(max(1, math.ceil(self.lo - 1e-9)),
                                             math.floor(self.hi + 1e-9) + 1)]
            if not whole:
                raise MealPlanError("ไม่มีจำนวนเต็มของอาหารที่อยู่ในขอบเขตปริมาณ")
            self.choices = whole
            self.lo, self.hi = self.choices[0], self.choices[-1]
        if self.slot.optional:
            self.choices.insert(0, 0.0)
            self.lo = 0.0
        self.mult = min(self.choices, key=lambda c: abs(c - self.mult))

    def macros(self) -> dict[str, float]:
        f = self.food
        return {
            "kcal": float(f["kcal"]) * self.mult,
            "protein_g": float(f["protein_g"]) * self.mult,
            "carb_g": float(f["carb_g"]) * self.mult,
            "fat_g": float(f["fat_g"]) * self.mult,
        }


def _is_countable(food: dict) -> bool:
    serving = str(food.get("serving_desc") or "")
    return serving.strip().startswith("1 ") and any(unit in serving for unit in _COUNTABLE_UNITS)


def _totals(items: list[_Item]) -> dict[str, float]:
    out = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    for item in items:
        for key, value in item.macros().items():
            out[key] += value
    return out


def _quality(items: list[_Item], totals: dict[str, float], meal_count: int) -> float:
    """Soft application preferences, not medical limits or equal-meal mandates."""
    score = 0.0
    by_meal = {meal: {"kcal": 0.0, "protein_g": 0.0} for meal in _meal_shares(meal_count)}
    for item in items:
        for key in ("kcal", "protein_g"):
            by_meal[item.meal.key][key] += float(item.food[key]) * item.mult
    for meal, share in _meal_shares(meal_count).items():
        for key in ("kcal", "protein_g"):
            if totals[key] <= 0:
                continue
            fraction = by_meal[meal][key] / totals[key]
            # A 25% band around each desired share allows different meal sizes.
            distance = max(0.0, abs(fraction - share) - share * 0.25)
            score += 0.20 * (distance / share) ** 2
    for item in items:
        if item.mult == 0:
            continue
        grams = item.mult * float(item.food["serving_g"])
        low, high = item.policy.preferred_min_g, item.policy.preferred_max_g
        distance = max(0.0, low - grams) / max(low, 1) + max(0.0, grams - high) / high
        score += 0.15 * distance ** 2 / len(items)
    return score


def _score(
    items: list[_Item], targets: dict[str, float], meal_count: int
) -> tuple[float, float, float]:
    totals = _totals(items)
    excess = sum(
        max(0.0, abs(totals[k] - targets[k]) / targets[k] - tolerance - 1e-9) ** 2
        for k, tolerance in TOLERANCE.items()
    )
    # Within meal-weight budgets, daily feasibility outranks soft preferences.
    nutrition_error = sum(_ERROR_WEIGHTS[k] * ((totals[k] - t) / t) ** 2
                          for k, t in targets.items())
    weight_excess = 0.0
    if items and items[0].practical:
        weights: dict[str, float] = {}
        for item in items:
            weights[item.meal.key] = weights.get(item.meal.key, 0) + (
                item.mult * float(item.food["serving_g"])
            )
        weight_excess = sum(
            max(0, grams / (SUPPLEMENTAL_MEAL_WEIGHT_G if key.startswith("snack")
                           else MAIN_MEAL_WEIGHT_G) - 1) ** 2
            for key, grams in weights.items()
        )
    return weight_excess, excess, nutrition_error + _quality(items, totals, meal_count)


def _improve_pair(items: list[_Item], targets: dict[str, float], meal_count: int) -> bool:
    """Escape a one-variable local minimum with a bounded two-food exchange.

    Adjacent choices refine daily-feasible plans; an infeasible plan can try
    all choices for a pair. Both use a fixed order and bounded pass count.
    This remains a heuristic, not a claim of global optimality.
    """
    best = _score(items, targets, meal_count)
    move = None
    for index, first in enumerate(items):
        original_first = first.mult
        first_at = first.choices.index(original_first)
        for second in items[index + 1:]:
            original_second = second.mult
            second_at = second.choices.index(original_second)
            pair_score = (_pair_scorer(items, first, second, targets, meal_count)
                          if first.practical else lambda: _score(items, targets, meal_count))
            if first.practical:
                # Adaptive planning tries up to four templates. Bound pair
                # search to neighbours and endpoints, rather than multiplying
                # exhaustive pair grids by every extra meal and food repair.
                first_moves = sorted({0, first_at - 1, first_at + 1, len(first.choices) - 1})
                second_moves = sorted({0, second_at - 1, second_at + 1, len(second.choices) - 1})
            else:
                first_moves = (range(len(first.choices)) if max(best[:2]) > 0
                               else (first_at - 1, first_at + 1))
                second_moves = (range(len(second.choices)) if max(best[:2]) > 0
                                else (second_at - 1, second_at + 1))
            for a in first_moves:
                if not 0 <= a < len(first.choices):
                    continue
                first.mult = first.choices[a]
                for b in second_moves:
                    if not 0 <= b < len(second.choices):
                        continue
                    second.mult = second.choices[b]
                    if first.mult == original_first and second.mult == original_second:
                        continue
                    score = pair_score()
                    if score < best:
                        best = score
                        move = first, first.mult, second, second.mult
                second.mult = original_second
            first.mult = original_first
    if move is None:
        return False
    first, first.mult, second, second.mult = move
    return True


def _pair_scorer(items: list[_Item], first: _Item, second: _Item,
                 targets: dict[str, float], meal_count: int):
    """Cache unchanged contributions during a pair search, without rounding.

    The reference score still drives coordinate descent. Only the two changing
    foods are added here; repeated whole-menu summation is unnecessary.
    """
    shares = _meal_shares(meal_count)
    keys = tuple(TOLERANCE)
    fixed = dict.fromkeys(keys, 0.0)
    fixed_meals = {key: [0.0, 0.0, 0.0] for key in shares}  # kcal, protein, grams

    def portion_cost(item):
        if item.mult == 0:
            return 0.0
        grams = item.mult * float(item.food["serving_g"])
        low, high = item.policy.preferred_min_g, item.policy.preferred_max_g
        distance = max(0, low - grams) / max(low, 1) + max(0, grams - high) / high
        return 0.15 * distance ** 2 / len(items)

    fixed_cost = 0.0
    for item in items:
        if item is first or item is second:
            continue
        for key in keys:
            fixed[key] += float(item.food[key]) * item.mult
        values = fixed_meals[item.meal.key]
        values[0] += float(item.food["kcal"]) * item.mult
        values[1] += float(item.food["protein_g"]) * item.mult
        values[2] += float(item.food["serving_g"]) * item.mult
        fixed_cost += portion_cost(item)

    def score():
        totals = fixed.copy()
        meals = {key: values.copy() for key, values in fixed_meals.items()}
        quality = fixed_cost
        for item in (first, second):
            for key in keys:
                totals[key] += float(item.food[key]) * item.mult
            values = meals[item.meal.key]
            values[0] += float(item.food["kcal"]) * item.mult
            values[1] += float(item.food["protein_g"]) * item.mult
            values[2] += float(item.food["serving_g"]) * item.mult
            quality += portion_cost(item)
        weight_excess = 0.0
        for key, share in shares.items():
            values = meals[key]
            budget = SUPPLEMENTAL_MEAL_WEIGHT_G if key.startswith("snack") else MAIN_MEAL_WEIGHT_G
            weight_excess += max(0, values[2] / budget - 1) ** 2
            for index, nutrient in enumerate(("kcal", "protein_g")):
                if totals[nutrient] > 0:
                    distance = max(0, abs(values[index] / totals[nutrient] - share) - share * 0.25)
                    quality += 0.20 * (distance / share) ** 2
        excess = sum(max(0, abs(totals[k] - targets[k]) / targets[k] - tol - 1e-9) ** 2
                     for k, tol in TOLERANCE.items())
        error = sum(_ERROR_WEIGHTS[k] * ((totals[k] - t) / t) ** 2 for k, t in targets.items())
        return weight_excess, excess, error + quality

    return score


def _grid(lo: float, hi: float, step: float) -> list[float]:
    """Allowed quantities in [lo, hi] at the requested resolution.

    ``hi`` is often a gram cap rather than a grid point; when the range holds no
    grid point at all (a cap tighter than one step above ``lo``) the cap itself
    is the only choice, so the plan stays inside the gram limit.
    """
    values: list[float] = []
    value = round(lo / step) * step
    if value < lo - 1e-9:
        value += step
    while value <= hi + 1e-9:
        values.append(round(value, 4))
        value += step
    return values or [round(hi, 4)]


def _optimize(items: list[_Item], targets: dict[str, float], meal_count: int = 4) -> None:
    """Bounded coordinate descent over the snapped portion grid.

    Enumerates the finite gram/unit choices without a solver dependency or
    randomness. If a single-variable sweep stalls, try a two-food exchange.
    """
    for _ in range(_OPTIMIZER_PASSES):
        improved = False
        for item in items:
            best_mult = item.mult
            best_error = _score(items, targets, meal_count)
            for candidate in item.choices:
                if candidate == best_mult:
                    continue
                item.mult = candidate
                error = _score(items, targets, meal_count)
                if error < best_error:
                    best_error, best_mult, improved = error, candidate, True
            item.mult = best_mult
        if not improved and not _improve_pair(items, targets, meal_count):
            return


def _repair_food_choices(
    items: list[_Item], pool: list[dict], targets: dict[str, float], meal_count: int, variant: int
) -> list[_Item]:
    """At most eight deterministic alternatives when the first food set misses.

    Restrictions have already filtered pool. Bounds are never relaxed to make
    a plan pass. Search remains deliberately bounded; failure is reported.
    """
    remaining = 8
    for _ in range(2):
        best_score = _score(items, targets, meal_count)
        if max(best_score[:2]) <= 1e-18:
            return items
        totals = _totals(items)
        roles = sorted(("carb", "fat", "protein"), key=lambda role: (
            -abs(totals[f"{role}_g"] / targets[f"{role}_g"] - 1)
        ))
        best_items = items
        for role in roles:
            nutrient = f"{role}_g"
            indices = sorted(
                (n for n, i in enumerate(items) if i.slot.role == role),
                key=lambda n: float(items[n].food[nutrient]) / float(items[n].food["serving_g"]),
                reverse=totals[nutrient] > targets[nutrient],
            )
            for index in indices:
                item = items[index]
                candidates = [f for f in pool if f["name_th"] != item.food["name_th"]]
                others = items[:index] + items[index + 1:]
                for _candidate in range(2):
                    food = _pick(candidates, role, {i.food["name_th"] for i in others},
                                 {i.food.get("category") or "" for i in others
                                  if i.slot.role == role}, variant, item.meal.key, item.practical)
                    if remaining == 0:
                        return best_items
                    if food is None:
                        break
                    candidates = [f for f in candidates if f is not food]
                    try:
                        replacement = _Item(food, item.meal, item.slot, 1.0, item.practical)
                    except MealPlanError:
                        continue
                    remaining -= 1
                    trial = [copy(i) for i in items]
                    trial[index] = replacement
                    _optimize(trial, targets, meal_count)
                    score = _score(trial, targets, meal_count)
                    if score < best_score:
                        best_score, best_items = score, trial
                        if max(score[:2]) <= 1e-18:
                            return trial
                        break
                if best_items is not items:
                    break
            if best_items is not items:
                break
        if best_items is items:
            break
        items = best_items
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: Foods a Thai lifter actually eats, per role, in order of preference. They
#: are tried before the rest of the table, which is still there as a fallback
#: (for restrictions that remove most of these). Ranking the whole 383-row
#: table by macro purity alone put tuna in mineral water, cassava, sapodilla and
#: 25 g of unsalted butter on the same breakfast plate, 300 g of egg white and
#: duck-egg yolk in one day, and gave every profile that same set of rows
#: (production_review_2026-09-24.md B6). Every name below is a row in
#: knowledge/foods.csv; tests/test_meal_plan.py checks that they still are.
EVERYDAY_FOODS: dict[str, tuple[str, ...]] = {
    "protein": (
        "อกไก่ไม่มีหนัง, ต้ม",
        "ปลานิล, ต้ม",
        "หมู, สันใน, ต้ม",
        "เต้าหู้ขาวแข็ง",
        "โปรตีนเกษตรถั่วเหลืองต้ม ไม่ใส่เกลือ",
        "เทมเป้สุก",
        "อกไก่ไม่มีหนัง, ย่าง",
        "ปลาแซลมอนแอตแลนติก (เลี้ยง), อบ",
        "กุ้งต้ม",
        "เนื้อวัวสะโพกต้ม",
        "สะโพกไก่ไม่มีหนัง, อบ",
        "ปลาทู, นึ่ง, ต้ม",
        "ปลาทูน่า, ในน้ำ, บรรจุกระป๋อง, เฉพาะเนื้อ",
        "ปลากะพงขาว, นึ่ง",
        "หมู, สับ, ต้ม",
        "ถั่วเหลือง, เมล็ดแห้ง",
        "ผงโปรตีนถั่วเหลืองไอโซเลท (ทั่วไป)",
    ),
    "carb": ("ข้าวสวย", "ขนมปังโฮลวีท", "ข้าวเจ้า, สุก", "มันฝรั่ง", "ก๋วยเตี๋ยวเส้นใหญ่, สด"),
    "fat": (
        "ไข่ไก่ต้ม",
        "ไข่ดาว",
        "ไข่ไก่, ทั้งฟอง",
        "ถั่วลิสง, เมล็ดแห้ง",
        "มะม่วงหิมพานต์, เมล็ดสด",
        "เมล็ดฟักทอง, พันธุ์ต่างๆ, แกะเปลือก, คั่ว",
    ),
    "vegetable": (
        "บร็อคโคลี่",
        "ผักกวางตุ้ง",
        "ผักบุ้งไทย",
        "กระหล่ำปลี",
        "แครอท",
        "ถั่วฝักยาว",
        "ผักกาดขาว/ ผักกาดขาวใบห่อ",
        "ปวยเล้ง",
        "แตงกวา",
        "มะเขือเทศ",
    ),
    "fruit": (
        "กล้วยหอม",
        "ฝรั่ง",
        "มะละกอสุก",
        "กล้วยน้ำว้าสุก",
        "แตงโม",
        "มังคุด",
    ),
}

#: Per-meal order that goes in front of ``EVERYDAY_FOODS`` for that meal, so
#: breakfast gets bread and a boiled egg, lunch and dinner get rice, and the
#: post-training snack gets a whey shake - rather than whichever row happened
#: to be next in line.
MEAL_PREFERENCES: dict[tuple[str, str], tuple[str, ...]] = {
    # Lean staples need a deliberate fat source, so dinner leans on fattier fish
    # and thigh, while a measured cooking-oil portion can support restricted diets.
    ("breakfast", "protein"): (
        "อกไก่ไม่มีหนัง, ต้ม",
        "ปลาทูน่า, ในน้ำ, บรรจุกระป๋อง, เฉพาะเนื้อ",
        "หมู, สับ, ต้ม",
    ),
    ("lunch", "protein"): ("อกไก่ไม่มีหนัง, ย่าง", "ปลานิล, ต้ม", "เนื้อวัวสะโพกต้ม", "กุ้งต้ม"),
    ("dinner", "protein"): (
        "ปลาแซลมอนแอตแลนติก (เลี้ยง), อบ",
        "สะโพกไก่ไม่มีหนัง, อบ",
        "ปลาทู, นึ่ง, ต้ม",
    ),
    ("breakfast", "carb"): ("ขนมปังโฮลวีท", "ข้าวสวย"),
    ("breakfast", "fat"): ("ไข่ไก่ต้ม", "ไข่ดาว"),
    ("breakfast", "fruit"): ("กล้วยหอม", "มะละกอสุก"),
    ("lunch", "carb"): ("ข้าวสวย", "ข้าวเจ้า, สุก", "ก๋วยเตี๋ยวเส้นใหญ่, สด"),
    ("lunch", "fat"): (
        "ถั่วลิสง, เมล็ดแห้ง",
        "มะม่วงหิมพานต์, เมล็ดสด",
        "น้ำมันมะกอก",
    ),
    ("dinner", "carb"): ("ข้าวเจ้า, สุก", "ข้าวสวย", "มันฝรั่ง"),
    ("dinner", "fat"): (
        "มะม่วงหิมพานต์, เมล็ดสด",
        "ถั่วลิสง, เมล็ดแห้ง",
        "น้ำมันมะกอก",
    ),
    ("snack", "protein"): (
        "เวย์โปรตีน (ผงชงดื่ม)",
        "ผงโปรตีนถั่วเหลืองไอโซเลท (ทั่วไป)",
    ),
    ("snack", "carb"): ("มันฝรั่ง", "ขนมปังโฮลวีท"),
    ("snack", "fruit"): ("กล้วยหอม", "ฝรั่ง"),
}

#: Serving units that only make sense whole - nobody boils a quarter of an egg
#: or scoops a quarter of a scoop. Rows served in these units are portioned in
#: whole numbers, at least one.
_COUNTABLE_UNITS: tuple[str, ...] = ("ฟอง", "สกู๊ป", "ลูก", "ผล", "ชิ้น", "แผ่น", "ไม้")

_SNACK_ONLY_PROTEINS = frozenset(
    {
        "เวย์โปรตีน (ผงชงดื่ม)",
        "ผงโปรตีนถั่วเหลืองไอโซเลท (ทั่วไป)",
    }
)


def _pick(
    pool: list[dict],
    role: str,
    used_names: set[str],
    used_categories: set[str],
    variant: int,
    meal: str = "",
    practical: bool = False,
) -> dict | None:
    """Best remaining candidate for a role, rotated by ``variant``.

    Everyday foods come first - this meal's ``MEAL_PREFERENCES``, then the
    role's ``EVERYDAY_FOODS`` - taking the first one not already on the menu.
    Only when none is left (usually a restriction removed them) does the rest
    of the table come in, ranked by how cleanly each serves the role. Rotation
    (rather than random choice) is what makes "ขออีกแบบ" reproducible: variant 0
    and variant 1 each always give the same menu. Among the fallback rows a
    category already used for this role is skipped on the first pass - the food
    table holds 85 seafood rows against 28 meat rows, so ranking alone would
    serve four different fish in one day.
    """
    if meal.startswith("snack"):
        meal = "snack"
    ranked = [
        f
        for f in pool
        if role in roles_of(f) and (meal == "snack" or f["name_th"] not in _SNACK_ONLY_PROTEINS)
        and not (meal == "snack" and role == "fat"
                 and f.get("category") == "น้ำมันและไขมัน")
    ]
    if not ranked:
        return None
    by_name = {normalize_thai(f["name_th"]): f for f in ranked}
    # Keep the existing whey shake on ordinary profiles; the soy powder is a
    # fallback for vegan users, not a rotation that changes other profiles.
    if meal == "snack" and role == "protein":
        whey = by_name.get(normalize_thai("เวย์โปรตีน (ผงชงดื่ม)"))
        if whey and (practical or whey["name_th"] not in used_names):
            return whey

    def available(names: tuple[str, ...]) -> list[dict]:
        return [by_name[normalize_thai(n)] for n in names if normalize_thai(n) in by_name]

    # the meal's own list and the role's list rotate separately, so "ขออีกแบบ"
    # moves lunch from chicken to fish rather than lunch's fat slot onto eggs
    meal_first = available(MEAL_PREFERENCES.get((meal, role), ()))
    general = [f for f in available(EVERYDAY_FOODS.get(role, ())) if f not in meal_first]
    everyday: list[dict] = []
    for group in (meal_first, general):
        if group:
            offset = variant % len(group)
            everyday += group[offset:] + group[:offset]
    for food in everyday:
        if food["name_th"] not in used_names:
            return food
    if practical and everyday:
        # Extra occasions may reuse ordinary foods. Exhausting the familiar
        # list must not force raw egg yolks or unusual foods into a snack.
        return everyday[0]
    position = {normalize_thai(f["name_th"]) for f in everyday}
    rest = sorted(
        (f for f in ranked if normalize_thai(f["name_th"]) not in position),
        key=lambda f: (-_role_score(f, role), f["name_th"]),
    )
    ordered = []
    if rest:
        offset = variant % len(rest)
        ordered = rest[offset:] + rest[:offset]
    ordered += everyday
    for food in ordered:
        category = food.get("category") or ""
        if food["name_th"] not in used_names and category not in used_categories:
            return food
    for food in ordered:
        if food["name_th"] not in used_names:
            return food
    return ordered[0]


#: Rows that are legitimately in the food table (they come from the ASEAN
#: composition data, with a source id) but must never be *recommended*: the
#: table's egg category includes sea-turtle eggs, and the vegetarian sweep
#: served them as a lunch protein because they rank as a clean egg row.
_NEVER_SUGGEST_TOKENS = ("เต่า", "จะละเม็ด(ไข่")


def _never_suggest(food: dict) -> bool:
    name = normalize_thai(food.get("name_th") or "")
    return any(_contains(name, normalize_thai(t)) for t in _NEVER_SUGGEST_TOKENS)


def plan_day_menu(
    foods: list[dict], targets: dict[str, float],
    restrictions: list[str] | tuple[str, ...] = (), variant: int = 0,
    meal_count: int | None = None, allow_extra_meals: bool | None = None,
    suggest_extra_meals: bool = True,
) -> dict:
    """Plan usable portions, preserving explicit counts and offering alternatives.

    No count means choose the smallest working number of supplemental meals.
    An explicit count stays fixed unless the user allows additional meals.
    Unaccepted alternatives never enter the displayed plan's totals.
    """
    count = 3 if meal_count is None else meal_count
    meal_template(count, True)  # Validate before doing any work.
    allow = meal_count is None if allow_extra_meals is None else allow_extra_meals
    base = build_day_plan(foods, targets, restrictions, variant, count, practical_portions=True)
    base["selection"] = "automatic" if meal_count is None else "requested"
    base["extra_meal_options"] = []
    if base["within_tolerance"] and base["practicality"]["meal_weights_within_preference"]:
        return base
    if not allow and not suggest_extra_meals:
        return base
    for candidate_count in range(count + 1, 4 + MAX_SUPPLEMENTAL_MEALS):
        try:
            candidate = build_day_plan(foods, targets, restrictions, variant, candidate_count,
                                       practical_portions=True)
        except MealPlanError:
            continue
        if (not candidate["within_tolerance"]
                or not candidate["practicality"]["meal_weights_within_preference"]):
            continue
        if allow:
            candidate["selection"] = "automatic" if meal_count is None else "extras_allowed"
            candidate["extra_meal_options"] = []
            return candidate
        base["extra_meal_options"] = [{
            "meal_count": candidate_count, "main_meal_count": 3,
            "supplemental_meal_count": candidate_count - 3,
            "totals": candidate["totals"], "within_tolerance": True,
            "requires_replanning": True,
        }]
        return base
    return base


def build_day_plan(
    foods: list[dict],
    targets: dict[str, float],
    restrictions: list[str] | tuple[str, ...] = (),
    variant: int = 0,
    meal_count: int = 4,
    *,
    practical_portions: bool = False,
) -> dict:
    """Assemble one day's menu for ``targets`` out of ``foods``.

    ``foods`` are rows shaped like ``foods.csv`` / the ``foods`` table, passed in
    rather than queried here so this stays a pure function the unit tests can
    drive without a database.
    """
    output_template = meal_template(meal_count, practical_portions)
    for key in ("kcal", "protein_g", "carb_g", "fat_g"):
        value = float(targets.get(key, 0) or 0)
        if not math.isfinite(value) or value <= 0:
            raise MealPlanError(f"เป้าหมาย {key} ต้องมากกว่า 0")
    targets = {key: float(targets[key]) for key in TOLERANCE}

    restrictions = [r for r in restrictions if r and r.strip()]
    unknown = [r for r in restrictions if r.strip() not in _RESTRICTION_RULES]

    pool: list[dict] = []
    excluded_counts: dict[str, int] = {}
    estimated_dropped = 0
    for food in foods:
        # Public callers may pass CSV rows; database callers supply dictionaries.
        if isinstance(food.get("nutrition_meta"), str):
            food = {
                **food,
                "nutrition_meta": json.loads(food["nutrition_meta"])
                if food["nutrition_meta"]
                else None,
            }
        if (
            food.get("estimated")
            or str(food.get("source") or "").startswith("TOVERIFY")
            or (food.get("nutrition_meta") or {}).get("verification_status")
            in {"unverified", "proxy_unverified"}
        ):
            estimated_dropped += 1
            continue
        # This powder fixes a documented vegan gap. Other profiles already have
        # whole-food or whey options and should keep their established menus.
        if food.get("name_th") == "ผงโปรตีนถั่วเหลืองไอโซเลท (ทั่วไป)" and "วีแกน" not in restrictions:
            continue
        if _never_suggest(food):
            continue
        if practical_portions:
            # Do not present dry legumes as if their source grams were cooked
            # eating portions. Verified cooked alternatives are already present.
            name = normalize_thai(food.get("name_th") or "")
            if "แห้ง" in name and any(token in name for token in
                                      ("ถั่วเหลือง", "ถั่วเขียว", "ถั่วแดง", "ถั่วดำ")):
                continue
            if (food.get("category") == "ไข่" and "ไข่ขาว" not in name
                    and not _is_countable(food)):
                continue  # Source-only 100-g egg rows do not define whole eggs.
        blocked_by = excluded_by(food, restrictions)
        if blocked_by:
            excluded_counts[blocked_by] = excluded_counts.get(blocked_by, 0) + 1
            continue
        if roles_of(food):
            pool.append(food)

    items: list[_Item] = []
    used_names: set[str] = set()
    used_categories: dict[str, set[str]] = {}
    missing_roles: list[str] = []
    for meal in output_template:
        for slot in meal.slots:
            seen = used_categories.setdefault(slot.role, set())
            # An impossible whole unit or empty portion range must not be
            # forced past its cap. Try another eligible food in the same slot.
            candidates = list(pool)
            item = None
            while candidates:
                food = _pick(candidates, slot.role, used_names, seen, variant, meal.key,
                             practical_portions)
                if food is None:
                    break
                try:
                    item = _Item(food=food, meal=meal, slot=slot, mult=1.0,
                                 practical=practical_portions)
                    break
                except MealPlanError:
                    candidates = [f for f in candidates if f is not food]
            if item is None:
                if not slot.optional:
                    missing_roles.append(f"{meal.label_th}:{slot.role}")
                continue
            used_names.add(item.food["name_th"])
            seen.add(item.food.get("category") or "")
            items.append(item)

    if not any(item.slot.role == "protein" for item in items):
        raise MealPlanError(
            "ไม่พบแหล่งโปรตีนที่ผ่านข้อจำกัดอาหารของผู้ใช้ในฐานข้อมูล จัดเมนูให้ไม่ได้ "
            "ให้บอกผู้ใช้ตรง ๆ และแนะนำให้ปรึกษานักกำหนดอาหาร"
        )

    _optimize(items, targets, meal_count)
    items = _repair_food_choices(items, pool, targets, meal_count, variant)
    items = [item for item in items if item.mult > 0]
    totals = _totals(items)

    deviations: dict[str, float] = {}
    within_tolerance = True
    for key, tol in TOLERANCE.items():
        target = float(targets[key])
        pct = (totals[key] - target) / target
        deviations[key] = round(pct * 100, 1)
        if abs(pct) > tol + 1e-9:
            within_tolerance = False

    meals_out = []
    for meal in output_template:
        meal_items = [i for i in items if i.meal.key == meal.key]
        if not meal_items:
            continue
        meals_out.append(
            {
                "key": meal.key,
                "label_th": meal.label_th,
                "kind": "supplemental" if meal.key.startswith("snack") else "main",
                "food_weight_g": round(sum(i.mult * float(i.food["serving_g"])
                                           for i in meal_items), 1),
                "items": [
                    {
                        "name_th": i.food["name_th"],
                        "role": i.slot.role,
                        "portion": i.mult,
                        "portion_desc_th": portion_text(i.mult, i.food),
                        "grams": round(i.mult * float(i.food.get("serving_g") or 0), 1),
                        **{k: round(v, 1) for k, v in i.macros().items()},
                        "source": i.food.get("source"),
                        "nutrition_meta": i.food.get("nutrition_meta"),
                        "warnings": i.food.get("warnings", []),
                        "portion_policy": {
                            "key": i.policy.key,
                            "min_grams": i.policy.min_g,
                            "max_grams": min(i.policy.max_g, i.slot.max_grams),
                            "planning_max_grams": _upper_grams(i.food, i.slot, practical_portions),
                        },
                    }
                    for i in meal_items
                ],
                **{
                    k: round(sum(i.macros()[k] for i in meal_items), 1)
                    for k in ("kcal", "protein_g", "carb_g", "fat_g")
                },
            }
        )

    warnings: list[str] = []
    if any(i.food.get("fiber_g") is None for i in items):
        warnings.append(
            "เมนูนี้มีอาหารที่ไม่มีค่าใยอาหารรวมครบ จึงยืนยันใยอาหารรวมทั้งวันไม่ได้ ห้ามนับค่าที่ไม่ทราบเป็นศูนย์"
        )
    if not within_tolerance:
        off = [
            f"{k} {deviations[k]:+.1f}%"
            for k, tol in TOLERANCE.items()
            if abs(totals[k] / targets[k] - 1) > tol + 1e-9
        ]
        warnings.append(
            "เมนูนี้ยังเข้าเป้าไม่ครบทุกตัว (" + ", ".join(off) + ") "
            "ต้องบอกผู้ใช้ตามตรงว่าตัวไหนเกิน/ขาดกี่ % ห้ามนำเสนอว่าตรงเป้าแล้ว"
        )
    if missing_roles:
        warnings.append("ข้อจำกัดอาหารทำให้บางมื้อขาดองค์ประกอบที่ตั้งใจไว้: " + ", ".join(missing_roles))
    if unknown:
        warnings.append(
            "ระบบไม่รู้จักข้อจำกัดอาหารนี้จึงไม่ได้กรองให้: "
            + ", ".join(unknown)
            + " ต้องเตือนผู้ใช้ให้ตรวจเมนูเองด้วย"
        )

    meal_balance = all(
        abs(sum(i.macros()[key] for i in items if i.meal.key == meal) / totals[key] - share)
        <= share * 0.25 + 1e-9
        for meal, share in _meal_shares(meal_count).items()
        for key in ("kcal", "protein_g")
        if totals[key] > 0
    )
    if not meal_balance:
        warnings.append("พลังงานหรือโปรตีนยังกระจายระหว่างมื้อไม่สม่ำเสมอตามเกณฑ์ตัวอย่างของระบบ")
    plan = {
        "variant": variant,
        "meal_count": meal_count,
        "main_meal_count": 3,
        "supplemental_meal_count": meal_count - 3,
        "restrictions_applied": restrictions,
        "restrictions_unknown": unknown,
        "excluded_counts": excluded_counts,
        "estimated_rows_dropped": estimated_dropped,
        "pool_size": len(pool),
        "targets": {
            k: float(targets[k]) for k in ("kcal", "protein_g", "carb_g", "fat_g")
        },
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "deviation_pct": deviations,
        "out_of_tolerance": [k for k, tol in TOLERANCE.items()
                             if abs(totals[k] / targets[k] - 1) > tol + 1e-9],
        "within_tolerance": within_tolerance,
        "tolerance_pct": {k: round(v * 100) for k, v in TOLERANCE.items()},
        "meals": meals_out,
        "warnings": warnings,
        "practicality": {
            "policy_version": PORTION_POLICY_VERSION,
            "review_status": "pending_dietitian_review",
            "meal_balance_within_preference": meal_balance,
            "portion_mode": "preferred" if practical_portions else "bounded",
            "meal_weights_within_preference": all(
                m["food_weight_g"] <= (SUPPLEMENTAL_MEAL_WEIGHT_G if m["kind"] == "supplemental"
                                       else MAIN_MEAL_WEIGHT_G) + 1e-6
                for m in meals_out
            ),
        },
        "note": (
            "เมนูนี้คำนวณด้วยโปรแกรม ไม่ใช่การประมาณของโมเดล และไม่ใช่การสุ่ม "
            "ตัวเลขทุกตัวมาจากฐานข้อมูลอาหารของระบบ "
            "ห้ามบอกผู้ใช้ว่าเมนูนี้สุ่มมา โปรไฟล์เดิมกับ variant เดิมจะได้เมนูเดิมเสมอ "
            "ให้รายงานหน่วยเสิร์ฟตามข้อความปริมาณที่แนบมากับแต่ละรายการ และแจ้งส่วนต่างจากเป้าหมายตามจริง "
            "ห้ามพิมพ์ชื่อคีย์หรือชื่อฟิลด์จากข้อมูลนี้ให้ผู้ใช้เห็น ให้เขียนเป็นภาษาคนเสมอ "
            "ห้ามเพิ่ม ลด หรือแทนที่รายการอาหารเอง ถ้าผู้ใช้อยากได้เมนูอื่นให้เรียกเครื่องมือใหม่ด้วย variant ถัดไป "
            "เมนูนี้เป็นวัตถุดิบ/รายการอาหารพร้อมปริมาณ ไม่ได้ระบุวิธีปรุง ให้บอกผู้ใช้ว่าปรับวิธีปรุงได้ "
            "แต่ถ้าเพิ่มน้ำมันหรือเครื่องปรุงจะทำให้ตัวเลขเปลี่ยนจากที่คำนวณไว้"
        ),
        "disclaimer": "เป็นตัวอย่างการจัดมื้อเพื่อการศึกษา ไม่ใช่การกำหนดอาหารเฉพาะบุคคลโดยนักกำหนดอาหาร",
    }
    validate_day_plan(plan, pool)
    return plan


def validate_day_plan(plan: dict, foods: list[dict]) -> None:
    """Recompute from source rows, independent of optimizer totals and flags.

    Fail closed: a malformed result must never become a verified chat table.
    Reference portions remain untouched; no cooked/raw conversion is inferred.
    """
    def close(reported: float, expected: float) -> bool:
        return math.isfinite(reported) and abs(reported - expected) <= 0.051

    practical = (plan.get("practicality") or {}).get("portion_mode") == "preferred"
    by_food = {(f["name_th"], f.get("source")): f for f in foods}
    template = meal_template(plan["meal_count"], practical)
    if (plan.get("main_meal_count") != 3
            or plan.get("supplemental_meal_count") != plan["meal_count"] - 3):
        raise MealPlanError("ตรวจสอบจำนวนมื้อหลักและมื้อเสริมไม่ผ่าน")
    slots = {(m.key, s.role): s for m in template for s in m.slots}
    totals = dict.fromkeys(TOLERANCE, 0.0)
    seen_slots: set[tuple[str, str]] = set()
    seen_meals: set[str] = set()
    weights_within_preference = True
    for meal in plan["meals"]:
        if meal["key"] in seen_meals or not meal["items"]:
            raise MealPlanError("ตรวจสอบโครงสร้างมื้ออาหารไม่ผ่าน")
        seen_meals.add(meal["key"])
        supplemental = meal["key"].startswith("snack")
        if meal.get("kind") != ("supplemental" if supplemental else "main"):
            raise MealPlanError("ตรวจสอบประเภทมื้ออาหารไม่ผ่าน")
        weight = 0.0
        meal_totals = dict.fromkeys(TOLERANCE, 0.0)
        for item in meal["items"]:
            slot_key = (meal["key"], item["role"])
            food = by_food.get((item["name_th"], item.get("source")))
            if food is None or slot_key not in slots or slot_key in seen_slots:
                raise MealPlanError("ตรวจสอบรายการอาหารในเมนูไม่ผ่าน")
            seen_slots.add(slot_key)
            meta = food.get("nutrition_meta") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            if (excluded_by(food, plan["restrictions_applied"]) or _never_suggest(food)
                    or food.get("estimated") or str(food.get("source") or "").startswith("TOVERIFY")
                    or meta.get("verification_status") in {"unverified", "proxy_unverified"}
                    or item["role"] not in roles_of(food)):
                raise MealPlanError("ตรวจสอบข้อจำกัดอาหารในเมนูไม่ผ่าน")
            multiplier = item["portion"]
            grams = multiplier * float(food["serving_g"])
            weight += grams
            policy = portion_policy(food, item["role"])
            slot = slots[slot_key]
            if (not math.isfinite(grams) or grams < policy.min_g - 1e-4
                    or grams > _upper_grams(food, slot, practical) + 1e-4
                    or (_is_countable(food) and multiplier > slot.max_mult + 1e-6)
                    or not close(item["grams"], grams)):
                raise MealPlanError("ตรวจสอบขอบเขตปริมาณอาหารในเมนูไม่ผ่าน")
            if _is_countable(food) and (multiplier < 1 or not float(multiplier).is_integer()):
                raise MealPlanError("ตรวจสอบจำนวนเต็มของอาหารในเมนูไม่ผ่าน")
            for key in TOLERANCE:
                value = float(food[key]) * multiplier
                if not math.isfinite(value) or value < 0 or not close(item[key], value):
                    raise MealPlanError("ตรวจสอบสารอาหารของรายการอาหารไม่ผ่าน")
                meal_totals[key] += value
        for key, value in meal_totals.items():
            if not close(meal[key], value):
                raise MealPlanError("ตรวจสอบผลรวมสารอาหารรายมื้อไม่ผ่าน")
            totals[key] += value
        if "food_weight_g" in meal and not close(meal["food_weight_g"], weight):
            raise MealPlanError("ตรวจสอบน้ำหนักอาหารรวมในมื้อไม่ผ่าน")
        budget = SUPPLEMENTAL_MEAL_WEIGHT_G if supplemental else MAIN_MEAL_WEIGHT_G
        weights_within_preference &= weight <= budget + 1e-6
    for key, value in totals.items():
        if not close(plan["totals"][key], value):
            raise MealPlanError("ตรวจสอบผลรวมสารอาหารรายวันไม่ผ่าน")
        target = plan["targets"][key]
        if not math.isfinite(target) or target <= 0:
            raise MealPlanError("ตรวจสอบเป้าหมายสารอาหารไม่ผ่าน")
        deviation = (value - target) / target * 100
        if not close(plan["deviation_pct"][key], deviation):
            raise MealPlanError("ตรวจสอบส่วนต่างจากเป้าหมายสารอาหารไม่ผ่าน")
    if seen_meals != {meal.key for meal in template}:
        raise MealPlanError("ตรวจสอบจำนวนมื้อที่จัดได้ไม่ผ่าน")
    within = all(abs(totals[k] / plan["targets"][k] - 1) <= tol + 1e-9
                 for k, tol in TOLERANCE.items())
    if plan["within_tolerance"] != within:
        raise MealPlanError("ตรวจสอบสถานะเข้าเป้าหมายสารอาหารไม่ผ่าน")
    if plan["practicality"]["meal_weights_within_preference"] != weights_within_preference:
        raise MealPlanError("ตรวจสอบสถานะน้ำหนักอาหารรวมไม่ผ่าน")


def _format_portion(mult: float) -> str:
    """1.0 -> "1", 1.5 -> "1.5" - avoids "1.0 × 1 ทัพพี" in the Thai output."""
    return str(int(mult)) if abs(mult - round(mult)) < 1e-9 else f"{mult:g}"


_GRAM_SERVING_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(กรัม|ก\.|g)\s*$")
_UNIT_SERVING_RE = re.compile(r"^\s*1\s+([^(]+?)\s*(\(.*\))?\s*$")


def portion_text(mult: float, food: dict) -> str:
    """A portion a person can measure, in the table's own unit.

    "0.5 × 100 กรัม" and "0.25 × 100 กรัม" were what users read before
    2026-09-24 (production_review_2026-09-24.md B6). Rows served per 100 g now
    read as grams ("50 กรัม"); rows served per piece read as pieces with the
    total weight ("2 ฟอง (รวม 92 กรัม)"). Anything else keeps the old form.
    """
    serving = str(food.get("serving_desc") or "").strip()
    grams = mult * float(food.get("serving_g") or 0)
    grams_txt = f"{round(grams, 1):g}"
    if _GRAM_SERVING_RE.match(serving) and grams > 0:
        return f"{grams_txt} กรัม"
    unit = _UNIT_SERVING_RE.match(serving)
    if unit and grams > 0:
        if not _is_countable(food) and abs(mult * 4 - round(mult * 4)) > 1e-6:
            return f"{grams_txt} กรัม"
        return f"{_format_portion(mult)} {unit.group(1)} (รวม {grams_txt} กรัม)"
    return f"{_format_portion(mult)} × {serving}"


def summarize_plan_th(plan: dict) -> str:
    """One-line-per-meal Thai summary, used in tests and for logging."""
    lines = []
    for meal in plan["meals"]:
        names = ", ".join(f"{i['name_th']} {i['portion_desc_th']}" for i in meal["items"])
        lines.append(f"{meal['label_th']}: {names} ({meal['kcal']:.0f} kcal)")
    t = plan["totals"]
    lines.append(
        f"รวม {t['kcal']:.0f} kcal | โปรตีน {t['protein_g']:.0f} g | "
        f"คาร์บ {t['carb_g']:.0f} g | ไขมัน {t['fat_g']:.0f} g"
    )
    return "\n".join(lines)
