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

import re
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


#: Characters that render as nothing: zero-width space/joiner/non-joiner, the
#: byte-order mark, soft hyphen, word joiner, and the rest of Unicode's Cf
#: (format) category. Thai copied from LINE or a web page often carries U+200B
#: between words, and it can also be inserted on purpose - "สเตีย​รอยด์"
#: walked straight past the PED rule before these were stripped.
_INVISIBLE_RE = re.compile(r"[­͏؜᠎​-‏‪-‮⁠-⁯﻿]")

#: สระอำ written as นิคหิต + สระอา, with an optional tone mark between them
#: ("นํ้า" for "น้ำ", "ดํา" for "ดำ"). The ASEAN food table is spelled this way
#: in 30 rows. Matching-side folding (below) handles it, but the *display* side
#: - what the food table stores and what a user types - wants the composed
#: character, so the two forms meet in an ILIKE.
_SPLIT_SARA_AM_RE = re.compile("ํ([่-๋]?)า")


def compose_sara_am(text: str) -> str:
    """Rewrite นิคหิต+สระอา (with any tone mark between) as สระอำ.

    Order-preserving and lossless for real words: the tone mark is moved in
    front of the composed vowel, which is where a keyboard puts it.
    """
    if not text:
        return ""
    return _SPLIT_SARA_AM_RE.sub(lambda m: m.group(1) + _SARA_AM, text)


def strip_invisible(text: str) -> str:
    """Remove zero-width and other format characters."""
    return _INVISIBLE_RE.sub("", text) if text else ""


def normalize_thai(text: str) -> str:
    """Fold Thai spelling variants so substring tests are reliable.

    Invisible characters removed, NFKC, สระอำ expanded, each run of combining
    marks sorted, lower-cased.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", strip_invisible(text)).replace(
        _SARA_AM, _NIKHAHIT + _SARA_AA
    )
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
