"""Thai text folding, shared by every substring rule in the app.

Thai writes several things two ways that look identical on screen, and plain
``in`` tests do not see through any of them. Both places that match Thai
substrings hit this, and in both the failure was silent:

* ``guardrails`` normalised the *message* with NFKC but left its patterns raw.
  NFKC expands สระอำ (U+0E33) into นิคหิต + สระอา (U+0E4D U+0E32), so every
  pattern containing "ำ" could never match anything - nine of them across four
  flags, including "ยาขับน้ำ", "อดน้ำ", "ทำให้อ้วก" and "โรคประจำตัว". Found by
  eval/adversarial_scope_eval.py on 2026-09-04; it had been that way since the
  rules were written.
* ``meal_plan`` matched restriction keywords against ``foods.csv``, whose rows
  come from three source documents and spell "น้ำ" both ways: 28 rows use
  นํ้า (นิคหิต then ไม้โท) and 2 use น้ำ (ไม้โท then สระอำ). Unicode NFC does not
  unify those - นิคหิต has combining class 0, so nothing reorders it - and the
  "น้ำปลา" keyword silently skipped every row spelled the other way.

One function fixes both: expand สระอำ, then sort each run of combining marks so
the two orderings collapse to one. Case is folded at the same time because the
patterns mix Thai and English.

Anything comparing user text (or food names) against a Thai keyword must fold
*both sides* through this. Folding only one side is what caused both bugs.
"""

from __future__ import annotations

import unicodedata

#: สระอำ decomposes to นิคหิต + สระอา. NFKC already does this, but it is spelled
#: out so the function does not depend on that behaviour staying put.
_SARA_AM = "ำ"
_NIKHAHIT = "ํ"
_SARA_AA = "า"

#: Marks that sit above or below a consonant. Within one run they may be typed
#: in either order, so they are sorted to a canonical order.
_THAI_COMBINING = frozenset(
    "ั"  # ไม้หันอากาศ
    "ิีึืฺุู"  # สระบน/ล่าง
    "็่้๊๋์ํ๎"  # ไม้ไต่คู้ วรรณยุกต์ ทัณฑฆาต นิคหิต
)


def normalize_thai(text: str) -> str:
    """Fold Thai spelling variants so substring tests are reliable.

    NFKC, สระอำ expanded, each run of combining marks sorted, lower-cased.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).replace(_SARA_AM, _NIKHAHIT + _SARA_AA)
    out: list[str] = []
    run: list[str] = []
    for char in folded:
        if char in _THAI_COMBINING:
            run.append(char)
            continue
        if run:
            out.extend(sorted(run))
            run = []
        out.append(char)
    out.extend(sorted(run))
    return "".join(out).lower()
