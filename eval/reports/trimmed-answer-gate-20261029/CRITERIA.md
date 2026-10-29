# Trimmed answers that no longer answer the question: criteria (frozen 29 Oct 2026, before any code change)

## Problem

When a reviewed answer still has unbacked sentences after one repair, `_keep_verified_part` removes them,
re-reviews the rest and shows it if it has no issues and at least one content unit. Nothing checks that what
is left still answers the question. Live 29 Oct: "ต้องกินเวย์ไหม หรือกินไข่แทน" kept one line about eggs and
lost "you do not need whey". In the deployed run c0201c3, 12/101 answers were trimmed and the owner marked 4
of them fail for a missing key point (TH29-r1, YT01-r1, YT01-r2, YT06-r3).

Reproduction on main `9921154` (W1, 4 repeats, `repro-main/`): 4/4 kept the direct answer; r2 shows the
mechanism (the reviewer flagged "คุณไม่จำเป็นต้องกินเวย์ครับ ... [S2]" as an unsupported permission).

## Planned fix

Only on the trim path: after the trimmed text passes re-review, one small typed call asks whether the trimmed
text still directly answers the user's main question. If not, the trimmed text is not shown; the model gets
one more repair with the removed sentences and the instruction to answer the main question only from what
the sources state, or to say plainly that they do not settle it. The main review prompt is not changed, so
untrimmed answers are unaffected.

## Probe set (frozen)

The 11 distinct real questions whose c0201c3 answer was trimmed (TH01, TH16, TH19, TH20, TH27, TH29, TH37,
TH39, TH50, YT01, YT06) plus W1 (the whey-or-eggs question after the fixed food list, from the food-suggestion
probe). 3 repeats each, main `9921154` and branch, same entry (`chat.stream_understood_chat`), same sample
profile as c0201c3, production retrieval read-only. `cases-trim.json`.

## Measures and criteria

Reviewed against the frozen c0201c3 expectations (`expected` / `must_not`); W1 must say whether whey is
needed. Preliminary AI review (Claude), blind to arm where practical (answers reviewed from a merged sheet).

- M1 lost answer: the shown answer was trimmed and misses the key point.
- M2 pass: the answer meets the expectation (pass or pass_by_policy).
- M3 errors: no answer shown (`answer_validation_failed`, `answer_review_unavailable`, other error),
  excluding provider failures (429/503), which are rerun and reported separately.
- M4 time: median seconds per result.

- **C1:** branch M1 < main M1, and branch M1 ≤ 1 of 36.
- **C2:** branch M2 ≥ main M2.
- **C3:** branch M3 ≤ main M3 + 1.
- **C4:** branch median time ≤ main median + 10 s.
- **C5:** backend tests and ruff pass.

If main M1 is 0 in this sample (the failure is intermittent), C1 cannot show an improvement; the decision
then rests on C2-C4 plus unit tests of the new gate, and that will be stated.
