
## 2026-10-28: cards v2 (2-3 sections each, 25 new chunks), retrieval only
- A: retrieval changed for 59/61 real questions.
- C1: main 2/15, branch 2/15 (no change).
- C2 frozen: 112/125 (main 119), 7 lost. **Fails the frozen limit.**
- C2 amended (Q018, Q040, Q077, Q080, Q085 accept the new card): 3 lost (Q010, Q014, Q021). **Fails the limit of 2.**
  - Q010 vegetarian: carbs-for-lifting, bcaa and whey-vs-whole-food displace protein-requirement.
  - Q014 kidney + 200 g: weight-gain and protein-higher-body-weight displace protein-requirement. This
    item is refused by the medical guard before retrieval matters.
  - Q021 six meals: weight-gain displaces nutrient-timing.
- Two wording edits after the first v2 check: weight-gain referral sentence (removed "น้ำหนักลด… กินได้น้อย",
  which matched weight-loss questions) and the budget card's first heading. After the edits the weight-gain
  card is no longer rank 1 for TH19, but it still appears lower in several weight-loss questions.
- Decision: stop wording changes. Run generation (A, B) on these v2 cards, because answer quality is what
  the merge criteria measure. The C2 failure goes in the report and to the owner either way.

## 2026-10-28: out-of-scope refusal line (0.66), embedding only
None of the 15 off-topic queries crosses the 0.66 out-of-scope score with the v2 cards. The largest rise is
"ราคาหุ้นวันนี้เท่าไหร่", 0.559 → 0.575 (budget-protein-thai).

## 2026-10-28: generation started (held-out, then real)
- H09 ("หนัก 120 กิโล…") triggers the BMI ≥ 40 referral guard on both arms, by design: the sample profile
  is 170 cm tall and the message states 120 kg. It cannot test the card, so it is reported as "untestable
  (guard)" and excluded from the 22. The B denominator becomes 21; the B target scales to 15/21.
  Recorded before any H verdict.

## 2026-10-28: review of round 1 (cards v2), AI preliminary
- **B (held-out, 21 testable):**
  - Branch 19/21 pass, main 3/21.
  - The first branch attempts of H18 and H20 hit provider 503; both were rerun and passed. The 503 records are archived in `service-failures-held/`.
  - The 2 branch failures (H17 budget, H19 weight gain) are deterministic routes that never use retrieval. Main gives the identical answer for both.
  - **B passes.**
- **A (real questions, 99 changed results):**
  - Branch 85 pass, c0201c3 baseline 80. 2 branch results are provider 503s (TH02-r1, YT01-r1).
  - 15 fail→pass, 9 pass→fail. No factual error. All 9 policy results are unchanged.
  - **A1, A2 and A3 pass.**
- **A4: flips caused by a card:**
  - TH08 ("เวย์สร้างกล้ามได้จริงเหรอ") fails 3/3. whey-vs-whole-food leads retrieval and has no statement that muscle comes from resistance training. **This is a content flip, so it blocks merge until fixed.**
  - TH21-r1 and TH19-r1 may be crowding (carbs-for-lifting / weight-gain chunks). Other flips (TH02-r2, TH14-r2, TH20-r3, TH25-r1) look like trimming or variance. TH42-r1 is the interpreter, with no retrieval.
- **Note:** TH36-r1 passes, but the model added full first names (James Arthur Harris, Francis Gano Benedict) that are not in the card. They are historically correct, yet unsupported, and the claim checker did not catch them.
- **Fix (recorded before any rerun):** whey-vs-whole-food gets a first paragraph from ISSN 2017 (resistance exercise and protein both stimulate MPS and are synergistic; muscle comes from training plus total protein and energy), and the section heading names the question.
- **Rerun plan:**
  1. Rerun TH08 r1-r3, TH21-r1 and TH19-r1 on the edited card.
  2. Also rerun every real or held item whose retrieval changes because of the edit.
  3. Report round 1 and round 2 side by side, and keep all records.

## 2026-10-28: round 2 (whey-vs-whole-food with resistance-training paragraph)
- Rerun: 5 held-out items and 29 real questions (49 results) whose retrieval changed with the edit.
- **Held-out:** all 5 pass. B final: branch 19/21, main 3/21.
- **Real questions:**
  - TH08 passes 3/3 (was 0/3 in round 1). A4 is satisfied.
  - Round-2 subset: branch 45/49, baseline 37/49.
  - Final over the 99 changed results (round 2 where rerun, round 1 elsewhere): branch 90, baseline 80. Whole set: 91/101 (90.1%) vs c0201c3 81/101 (80.2%).
  - 17 fail→pass, 6 pass→fail: TH02-r2, TH14-r2, TH19-r1, TH20-r3, TH27-r1, TH42-r1. None is caused by card content; they come from trimming, variance, a validation block, or the interpreter.
  - 1 service failure (TH02-r1, provider 503). No factual errors. All 9 policy results are unchanged.
- **Retrieval with final cards:** C1 unchanged (2/15 both). C2 112/125 vs 119, so **C2 fails**, as recorded. Off-topic queries crossing 0.66: none.
- **Merge:** the owner approved merging on 28 Oct 2026 with C2 failing, after the C2 explanation.
