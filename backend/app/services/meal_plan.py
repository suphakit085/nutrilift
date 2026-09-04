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
3. fill a fixed meal template, refusing to reuse a food and preferring an unused
   food *category* per role, so the day is not four servings of the same fish;
4. solve the portion multipliers by bounded coordinate descent on the weighted
   relative error against the protein/carb/fat/kcal targets.

Portions are expressed as multiples of each row's own ``serving_desc`` and
snapped to ``PORTION_STEP``, so the output is something a person can actually
measure ("ข้าวสวย 3 ทัพพี"), not 1.37 servings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.thai_text import normalize_thai

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

#: Portions are rounded to this fraction of a serving. A quarter of a serving is
#: about as fine as "half a ladle of rice" can be followed in a real kitchen.
PORTION_STEP = 0.25

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
    "protein": frozenset({
        "เนื้อสัตว์", "ปลาและอาหารทะเล", "ไข่", "ไข่-นม", "นมและผลิตภัณฑ์",
        "ถั่วและเมล็ด", "โปรตีนพืช", "กับข้าว",
    }),
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
    "ผงชูรส", "เกลือ", "น้ำปลา", "ซีอิ๊ว", "กะปิ", "น้ำตาล", "ซอส", "น้ำเชื่อม",
    "น้ำสลัด", "กะทิ", "ผงปรุงรส", "แป้ง",
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
    if category in _ROLE_CATEGORIES["protein"] and kcal >= _MIN_KCAL_FOR_ANCHOR:
        if (
            protein >= _MIN_PROTEIN_G_FOR_ANCHOR
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
    if category in _ROLE_CATEGORIES["fat"]:
        if _energy_share(fat, KCAL_PER_G_FAT, kcal) >= _MIN_FAT_ENERGY_SHARE:
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
    "หมู", "ไก่", "เนื้อ", "วัว", "เป็ด", "ปลา", "กุ้ง", "หอย", "ปู", "ปลาหมึก", "แฮม",
    "เบคอน", "ไส้กรอก", "ลูกชิ้น", "ตับ", "เลือด", "กระเพาะ", "ขาหมู", "น้ำปลา", "กะปิ",
)
_MEAT_CATEGORIES = frozenset({"เนื้อสัตว์", "ปลาและอาหารทะเล"})
#: Thai writes compounds without spaces, so a short token matches inside
#: unrelated words: a bare "นม" hits ขนมปัง (bread) and แหนม (fermented pork).
#: Dairy is caught by the category gate; these spell out the forms that appear
#: as free-standing names, none shorter than three characters.
_DAIRY_TOKENS = (
    "นมวัว", "นมสด", "นมจืด", "นมข้น", "นมผง", "นมเปรี้ยว", "นมพร่อง", "นมถั่ว",
    "ชีส", "เนย", "โยเกิร์ต", "เวย์", "ครีม",
)

#: The same no-spaces problem in the other direction: "ไข่ไก่" contains "ไก่"
#: and "ไข่เป็ด" contains "เป็ด", so the meat tokens excluded every egg from a
#: lacto-ovo vegetarian's menu - which is what made มังสวิรัติ come out with
#: *less* protein than วีแกน in the sweep. Before matching, these compounds are
#: collapsed to plain "ไข่" for the restrictions that permit eggs. "ไข่ปลา"
#: (roe) is deliberately absent: it really is fish.
_EGG_COMPOUNDS = ("ไข่ไก่", "ไข่เป็ด", "ไข่นกกระทา", "ไข่ห่าน")
_RESTRICTIONS_EXCLUDING_EGGS = frozenset({"วีแกน"})

_RESTRICTION_RULES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "ฮาลาล": (
        # blood and amphibians are haram alongside pork and alcohol; the ASEAN
        # table has boiled chicken/duck blood and frog as plain "เนื้อสัตว์" rows
        ("หมู", "แฮม", "เบคอน", "ไส้กรอก", "ขาหมู", "เลือด", "กบ", "เขียด",
         "สุรา", "เบียร์", "ไวน์", "เหล้า", "แอลกอฮอล์"),
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
        ("ถั่ว", "เต้าหู้", "เต้าเจี้ยว", "นัต", "อัลมอนด์", "แมคคาเดเมีย", "พิสตาชิโอ",
         "งา", "เม็ดมะม่วงหิมพานต์", "มะม่วงหิมพานต์", "โปรตีนเกษตร"),
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
    Meal("breakfast", "มื้อเช้า", (
        Slot("protein", 0.5, 3.0, 300),
        Slot("carb", 0.5, 5.0, 350),
        Slot("fruit", 0.5, 2.0, 300),
        Slot("fat", 0.25, 2.0, 50),
    )),
    Meal("lunch", "มื้อกลางวัน", (
        Slot("protein", 0.5, 3.0, 300),
        Slot("carb", 0.5, 8.0, 500),
        Slot("vegetable", 0.5, 2.0, 250),
        Slot("fat", 0.25, 2.0, 80),
    )),
    Meal("dinner", "มื้อเย็น", (
        Slot("protein", 0.5, 3.0, 300),
        Slot("carb", 0.5, 8.0, 500),
        Slot("vegetable", 0.5, 2.0, 250),
        Slot("fat", 0.25, 2.0, 80),
    )),
    Meal("snack", "มื้อว่าง / หลังฝึก", (
        Slot("protein", 0.5, 2.5, 250),
        Slot("carb", 0.5, 4.0, 300),
        Slot("fruit", 0.5, 2.0, 300),
    )),
)


# ---------------------------------------------------------------------------
# Portion solving
# ---------------------------------------------------------------------------

@dataclass
class _Item:
    food: dict
    meal: Meal
    slot: Slot
    mult: float
    lo: float = field(init=False)
    hi: float = field(init=False)
    choices: list[float] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        serving_g = float(self.food.get("serving_g") or 0) or 100.0
        gram_cap = self.slot.max_grams / serving_g
        self.lo = self.slot.min_mult
        self.hi = max(self.lo, min(self.slot.max_mult, gram_cap))
        # Snap onto the allowed grid straight away. Clamping alone could leave a
        # multiplier the optimizer never proposes (a 60 g cap on a 100 g serving
        # clamps 1.0 to 0.6, which is not a multiple of PORTION_STEP), and that
        # value then survives to the answer as "0.6 x 100 กรัม".
        self.choices = _grid(self.lo, self.hi)
        self.mult = min(self.choices, key=lambda c: abs(c - self.mult))

    def macros(self) -> dict[str, float]:
        f = self.food
        return {
            "kcal": float(f["kcal"]) * self.mult,
            "protein_g": float(f["protein_g"]) * self.mult,
            "carb_g": float(f["carb_g"]) * self.mult,
            "fat_g": float(f["fat_g"]) * self.mult,
        }


def _totals(items: list[_Item]) -> dict[str, float]:
    out = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    for item in items:
        for key, value in item.macros().items():
            out[key] += value
    return out


def _error(items: list[_Item], targets: dict[str, float]) -> float:
    totals = _totals(items)
    score = 0.0
    for key, weight in _ERROR_WEIGHTS.items():
        target = targets.get(key, 0.0)
        if target <= 0:
            continue
        score += weight * ((totals[key] - target) / target) ** 2
    return score


def _snap(value: float) -> float:
    return round(value / PORTION_STEP) * PORTION_STEP


def _grid(lo: float, hi: float) -> list[float]:
    """Allowed multipliers in [lo, hi] at PORTION_STEP resolution.

    ``hi`` is often a gram cap rather than a grid point; when the range holds no
    grid point at all (a cap tighter than one step above ``lo``) the cap itself
    is the only choice, so the plan stays inside the gram limit.
    """
    values: list[float] = []
    value = _snap(lo)
    if value < lo - 1e-9:
        value += PORTION_STEP
    while value <= hi + 1e-9:
        values.append(round(value, 4))
        value += PORTION_STEP
    return values or [round(hi, 4)]


def _optimize(items: list[_Item], targets: dict[str, float]) -> None:
    """Bounded coordinate descent over the snapped portion grid.

    Every variable has at most (max_mult - min_mult) / PORTION_STEP + 1 values -
    a dozen or so - and there are at most a dozen variables, so an exhaustive
    sweep per pass is cheap and needs no gradient, no solver dependency, and no
    randomness. It stops as soon as a full pass improves nothing.
    """
    for _ in range(_OPTIMIZER_PASSES):
        improved = False
        for item in items:
            best_mult = item.mult
            best_error = _error(items, targets)
            for candidate in item.choices:
                if candidate == best_mult:
                    continue
                item.mult = candidate
                error = _error(items, targets)
                if error < best_error - 1e-9:
                    best_error, best_mult, improved = error, candidate, True
            item.mult = best_mult
        if not improved:
            return


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _pick(
    pool: list[dict],
    role: str,
    used_names: set[str],
    used_categories: set[str],
    variant: int,
) -> dict | None:
    """Best remaining candidate for a role, rotated by ``variant``.

    Rotation (rather than random choice) is what makes "ขออีกแบบ" reproducible:
    variant 0 and variant 1 each always give the same menu. A food is never
    repeated, and a category already used for this role is skipped on the first
    pass - the food table holds 85 seafood rows against 28 meat rows, so ranking
    alone would serve four different fish in one day.
    """
    ranked = [f for f in pool if role in roles_of(f)]
    ranked.sort(key=lambda f: (-_role_score(f, role), f["name_th"]))
    if not ranked:
        return None
    offset = variant % len(ranked)
    ordered = ranked[offset:] + ranked[:offset]
    for food in ordered:
        if food["name_th"] not in used_names and (food.get("category") or "") not in used_categories:
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


def build_day_plan(
    foods: list[dict],
    targets: dict[str, float],
    restrictions: list[str] | tuple[str, ...] = (),
    variant: int = 0,
) -> dict:
    """Assemble one day's menu for ``targets`` out of ``foods``.

    ``foods`` are rows shaped like ``foods.csv`` / the ``foods`` table, passed in
    rather than queried here so this stays a pure function the unit tests can
    drive without a database.
    """
    for key in ("kcal", "protein_g", "carb_g", "fat_g"):
        if float(targets.get(key, 0) or 0) <= 0:
            raise MealPlanError(f"เป้าหมาย {key} ต้องมากกว่า 0")

    restrictions = [r for r in restrictions if r and r.strip()]
    unknown = [r for r in restrictions if r.strip() not in _RESTRICTION_RULES]

    pool: list[dict] = []
    excluded_counts: dict[str, int] = {}
    estimated_dropped = 0
    for food in foods:
        if str(food.get("source") or "").startswith("TOVERIFY"):
            estimated_dropped += 1
            continue
        if _never_suggest(food):
            continue
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
    for meal in MEAL_TEMPLATE:
        for slot in meal.slots:
            seen = used_categories.setdefault(slot.role, set())
            food = _pick(pool, slot.role, used_names, seen, variant)
            if food is None:
                missing_roles.append(f"{meal.label_th}:{slot.role}")
                continue
            used_names.add(food["name_th"])
            seen.add(food.get("category") or "")
            items.append(_Item(food=food, meal=meal, slot=slot, mult=1.0))

    if not any(item.slot.role == "protein" for item in items):
        raise MealPlanError(
            "ไม่พบแหล่งโปรตีนที่ผ่านข้อจำกัดอาหารของผู้ใช้ในฐานข้อมูล จัดเมนูให้ไม่ได้ "
            "ให้บอกผู้ใช้ตรง ๆ และแนะนำให้ปรึกษานักกำหนดอาหาร"
        )

    _optimize(items, targets)
    totals = _totals(items)

    deviations: dict[str, float] = {}
    within_tolerance = True
    for key, tol in TOLERANCE.items():
        target = float(targets[key])
        pct = (totals[key] - target) / target
        deviations[key] = round(pct * 100, 1)
        if abs(pct) > tol:
            within_tolerance = False

    meals_out = []
    for meal in MEAL_TEMPLATE:
        meal_items = [i for i in items if i.meal.key == meal.key]
        if not meal_items:
            continue
        meals_out.append({
            "key": meal.key,
            "label_th": meal.label_th,
            "items": [
                {
                    "name_th": i.food["name_th"],
                    "role": i.slot.role,
                    "portion": round(i.mult, 2),
                    "portion_desc_th": f"{_format_portion(i.mult)} × {i.food['serving_desc']}",
                    "grams": round(i.mult * float(i.food.get("serving_g") or 0), 1),
                    **{k: round(v, 1) for k, v in i.macros().items()},
                    "source": i.food.get("source"),
                }
                for i in meal_items
            ],
            **{
                k: round(sum(i.macros()[k] for i in meal_items), 1)
                for k in ("kcal", "protein_g", "carb_g", "fat_g")
            },
        })

    warnings: list[str] = []
    if not within_tolerance:
        off = [
            f"{k} {deviations[k]:+.1f}%"
            for k, tol in TOLERANCE.items()
            if abs(deviations[k]) > tol * 100
        ]
        warnings.append(
            "เมนูนี้ยังเข้าเป้าไม่ครบทุกตัว (" + ", ".join(off) + ") "
            "ต้องบอกผู้ใช้ตามตรงว่าตัวไหนเกิน/ขาดกี่ % ห้ามนำเสนอว่าตรงเป้าแล้ว"
        )
    if missing_roles:
        warnings.append(
            "ข้อจำกัดอาหารทำให้บางมื้อขาดองค์ประกอบที่ตั้งใจไว้: " + ", ".join(missing_roles)
        )
    if unknown:
        warnings.append(
            "ระบบไม่รู้จักข้อจำกัดอาหารนี้จึงไม่ได้กรองให้: "
            + ", ".join(unknown)
            + " ต้องเตือนผู้ใช้ให้ตรวจเมนูเองด้วย"
        )

    return {
        "variant": variant,
        "restrictions_applied": restrictions,
        "restrictions_unknown": unknown,
        "excluded_counts": excluded_counts,
        "estimated_rows_dropped": estimated_dropped,
        "pool_size": len(pool),
        "targets": {
            k: round(float(targets[k]), 1) for k in ("kcal", "protein_g", "carb_g", "fat_g")
        },
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "deviation_pct": deviations,
        "within_tolerance": within_tolerance,
        "tolerance_pct": {k: round(v * 100) for k, v in TOLERANCE.items()},
        "meals": meals_out,
        "warnings": warnings,
        "note": (
            "เมนูนี้คำนวณด้วยโปรแกรม ไม่ใช่การประมาณของโมเดล และไม่ใช่การสุ่ม ตัวเลขทุกตัวมาจากฐานข้อมูลอาหารของระบบ "
            "ห้ามบอกผู้ใช้ว่าเมนูนี้สุ่มมา โปรไฟล์เดิมกับ variant เดิมจะได้เมนูเดิมเสมอ "
            "ให้รายงานหน่วยเสิร์ฟตาม portion_desc_th และแจ้ง deviation_pct ตามจริง "
            "ห้ามเพิ่ม ลด หรือแทนที่รายการอาหารเอง ถ้าผู้ใช้อยากได้เมนูอื่นให้เรียกเครื่องมือใหม่ด้วย variant ถัดไป "
            "เมนูนี้เป็นวัตถุดิบ/รายการอาหารพร้อมปริมาณ ไม่ได้ระบุวิธีปรุง ให้บอกผู้ใช้ว่าปรับวิธีปรุงได้ "
            "แต่ถ้าเพิ่มน้ำมันหรือเครื่องปรุงจะทำให้ตัวเลขเปลี่ยนจากที่คำนวณไว้"
        ),
        "disclaimer": "เป็นตัวอย่างการจัดมื้อเพื่อการศึกษา ไม่ใช่การกำหนดอาหารเฉพาะบุคคลโดยนักกำหนดอาหาร",
    }


def _format_portion(mult: float) -> str:
    """1.0 -> "1", 1.5 -> "1.5" - avoids "1.0 × 1 ทัพพี" in the Thai output."""
    return str(int(mult)) if abs(mult - round(mult)) < 1e-9 else f"{mult:g}"


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
