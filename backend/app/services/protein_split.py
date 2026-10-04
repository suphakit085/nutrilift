"""Answer unambiguous equal protein division without adding nutrition advice."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_NUMBER = r"[+-]?\d+(?:\.\d+)?"
_GRAMS = re.compile(rf"({_NUMBER})\s*(?:grams?|g)(?![a-z])", re.I)
# Thai units do not have an ASCII word boundary before the following Thai text.
_GRAMS_TH = re.compile(rf"({_NUMBER})\s*กรัม")
_MEALS = re.compile(rf"({_NUMBER})\s*(?:มื้อ|meals?\b)", re.I)
_WORDS = (
    "โปรตีน", "แบ่ง", "กระจาย", "ออกเป็น", "เป็น", "ถ้า", "หาก", "ต้องการ",
    "ผม", "ฉัน", "เรา", "คุณ", "เท่าๆกัน", "เท่ากัน", "ตาม", "เป้าหมาย", "เป้า",
    "ข้างบน", "ข้างต้น", "ที่คำนวณ", "ที่ตั้งไว้", "รวม", "ทั้งหมด", "วันละ", "ต่อวัน",
    "ต่อ", "แต่ละมื้อ", "มื้อละ", "มื้อ", "กี่", "เท่าไร", "เท่าไหร่", "กรัม",
    "ครับผม", "ครับ", "ค่ะ", "คะ", "ช่วย", "คำนวณ", "ให้หน่อย", "จะได้", "ได้",
    "protein", "split", "divide", "into", "across", "daily", "equally", "equal",
    "permeal", "howmuch", "grams", "gram", "g", "please", "of", "in", "is", "it",
    "the", "total", "target", "above", "each", "meal", "meals",
)
_ALLOWED_WORDS = re.compile("|".join(re.escape(w) for w in sorted(_WORDS, key=len, reverse=True)))


def _amounts(question: str) -> tuple[Decimal | None, int] | None:
    """Only accept arithmetic requests whose entire text has a known meaning."""
    text = question.casefold()
    compact = re.sub(r"\s+", "", text)
    if not any(word in compact for word in ("โปรตีน", "protein")):
        return None
    if not any(word in compact for word in ("แบ่ง", "กระจาย", "split", "divide")):
        return None
    # A question asking the result can say "มื้อละกี่กรัม", but its input
    # must be a daily total, never an existing per-meal quantity.
    if re.search(rf"(?:มื้อละ|permeal){_NUMBER}|(?:กรัม|g)(?:ต่อมื้อ|permeal)", compact):
        return None
    gram_matches = list(_GRAMS_TH.finditer(text)) + list(_GRAMS.finditer(text))
    meals = list(_MEALS.finditer(text))
    if len(gram_matches) > 1 or len(meals) != 1:
        return None
    remainder = text
    for match in sorted(gram_matches + meals, key=lambda m: m.start(), reverse=True):
        remainder = remainder[:match.start()] + remainder[match.end():]
    remainder = re.sub(r"[\s?.,!ๆ*]", "", remainder)
    if _ALLOWED_WORDS.sub("", remainder):
        return None
    try:
        count = Decimal(meals[0].group(1))
        total = Decimal(gram_matches[0].group(1)) if gram_matches else None
        if count != count.to_integral_value() or not 1 <= count <= 20:
            return None
        if total is not None and not 0 < total <= 1000:
            return None
    except InvalidOperation:
        return None
    refers_to_target = any(w in compact for w in ("เป้า", "ข้างบน", "ข้างต้น", "target", "above"))
    if total is None and not refers_to_target:
        return None
    return total, int(count)


def _display(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def _prior_total(history: list[dict]) -> Decimal | None:
    """Resolve a clearly stated daily total, not incidental food/per-meal protein."""
    for message in reversed(history):
        text = message.get("content", "")
        parsed = _amounts(text)
        if parsed and parsed[0] is not None:
            return parsed[0]
        plain = text.replace("*", "")
        matches = re.findall(
            r"โปรตีน\s*(?:รวม\s*)?(?:วันละ\s*)?(\d+(?:\.\d+)?)\s*"
            r"(?:กรัม|g)\s*ต่อวัน", plain, re.I,
        )
        setting_daily_target = re.fullmatch(
            r"\s*(?:ผม|ฉัน)?\s*(?:ตั้ง|กำหนด)เป้า(?:หมาย)?\s*โปรตีน\s*"
            r"\d+(?:\.\d+)?\s*(?:กรัม|g)\s*ต่อวัน\s*(?:ครับ|ค่ะ)?\s*", plain, re.I,
        )
        known_split_answer = plain.startswith("แบ่งโปรตีนรวม ")
        daily_heading = (
            message.get("role") == "assistant" and "สารอาหารหลักที่แนะนำต่อวัน" in plain
        )
        if daily_heading:
            matches += re.findall(r"โปรตีน\s*:\s*(\d+(?:\.\d+)?)\s*(?:กรัม|g)", plain)
        if matches:
            values = {Decimal(value) for value in matches}
            if len(values) == 1 and (setting_daily_target or known_split_answer or daily_heading):
                return values.pop()
            # Do not turn a rejected, hypothetical or ambiguous total into the
            # saved profile's number when the user refers to the prior text.
            return Decimal("NaN")
    return None


def equal_protein_split_reply(
    question: str, *, daily_protein_g: float | None = None, history: list[dict] | None = None,
) -> str | None:
    parsed = _amounts(question)
    if parsed is None:
        return None
    total, meals = parsed
    if total is None:
        total = _prior_total(history or [])
        if total is None and daily_protein_g is None:
            return "เป้าโปรตีนรวมต่อวันของคุณกี่กรัมครับ เพื่อคำนวณแบ่งเท่า ๆ กันต่อมื้อได้ถูกต้อง"
        if total is None:
            try:
                total = Decimal(str(daily_protein_g))
            except InvalidOperation:
                return None
        if not total.is_finite() or not 0 < total <= 1000:
            return None
    exact = total / meals
    rounded = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    approximate = "ประมาณ " if rounded != exact else ""
    return (
        f"แบ่งโปรตีนรวม {_display(total)} กรัมต่อวันเป็น {meals} มื้อเท่า ๆ กัน: "
        f"{_display(total)} ÷ {meals} = **{approximate}{_display(rounded)} กรัมต่อมื้อ** ครับ"
    )
