# Food-suggestion routing fix: criteria (frozen 29 Oct 2026, before any code change)

## Problem

A turn read as `food_suggestion` goes to a rule that lists the top-5 foods by protein share. Only focus,
count and exclusions reach that rule; every other condition in the question (budget, a shop such as
7-Eleven or a made-to-order stall, which dishes to order, a whey-or-eggs question) is dropped silently.
The answer is then the same 5 foods every time.

Reproduced on main `3d3c53d`, interpretation only, 2 repeats (`repro-main.json`): P1, P2 and P5 were routed
to the list in 2/2 repeats; P4 (whey or eggs, asked after a list) in 1/2.

## Planned fix (structural, no wording regex)

`FoodSuggestion` gets a typed field listing request conditions the list cannot honour (budget/price, a shop
or place, dishes or menu items to order, a yes/no or comparison question, other), each with an exact quote
from the current turn. When it is non-empty the turn does not take the rule path and goes to the normal
answer path (knowledge cards + tools). Ungrounded quotes drop the suggestion, as today.

## Probe questions (frozen)

Target: must not be answered by the fixed list.

| ID | History | Question |
|---|---|---|
| T1 | none | งบผมวันละ 150 บาท ส่วนใหญ่กินร้านตามสั่งกับเซเว่น กินอะไรได้บ้างครับ |
| T2 | none | ร้านตามสั่งสั่งเมนูไหนดีครับ ได้โปรตีนเยอะๆ งบมื้อละ 50 บาท |
| T3 | after a list | ต้องกินเวย์ไหมครับ หรือกินไข่วันละ 5-6 ฟองแทนได้ |
| T4 | after a list | ร้านตามสั่งสั่งเมนูไหนดีครับ ได้โปรตีนเยอะๆ |
| T5 | none | เซเว่นมีอะไรกินแล้วได้โปรตีนเยอะบ้างครับ |
| T6 | none | อยากได้โปรตีนเยอะแต่ประหยัด กินอะไรดีครับ |
| T7 | none | ไข่กับอกไก่ อันไหนดีกว่ากันสำหรับสร้างกล้าม |

Keep: must still get the food list (behaviour from #52 / #55).

| ID | Question |
|---|---|
| K1 | แนะนำอาหารโปรตีนสูงที่หาง่ายหน่อย |
| K2 | ขออาหารไม่มีนม 3 อย่าง |
| K3 | อาหารคาร์บสูงมีอะไรบ้าง |
| K4 | ขออาหารโปรตีนสูง 5 อย่าง ไม่เอาหมู |
| K5 | แนะนำอาหารที่มีโปรตีนเยอะๆ หน่อยครับ |
| K6 | อยากได้รายชื่ออาหารคาร์บดีๆ 4 อย่าง |

"After a list" = history of the T1 question followed by the fixed-list answer (`cases-probe.json`).

## Criteria

Interpretation stage, model `gemini-3.5-flash-lite`, 3 repeats per question per arm (main `3d3c53d`, branch).
"List route" = `food_suggestion` non-null after grounding and, on the branch, with no unsupported condition.

- **C1 (target):** branch list routes over T1–T7 ≤ 2 of 21, and fewer than main.
- **C2 (keep):** branch list routes over K1–K6 ≥ main − 1, and no K question at 0/3 on the branch.
- **C3 (real questions):** interpret the 61 real questions (`real-questions-c0201c3`, round 1) on both arms.
  Any question whose list route differs between arms is generated end to end on the branch and reviewed;
  it must not turn a pass into a fail. Changes in other routing fields are listed and, if more than 3,
  investigated before merge.
- **C4 (answers):** full answers on the branch for T1–T7 (1 repeat). AI review: the answer addresses the
  stated condition (budget, shop, dishes, whey vs eggs, eggs vs chicken) and has no factual error.
  At least 6 of 7.
- **C5:** backend tests and ruff pass.

All reviews are preliminary AI reviews (Claude). Every run is kept; service failures (429/503) are
retried and reported separately.
