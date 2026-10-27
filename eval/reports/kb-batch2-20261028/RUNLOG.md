# Batch 2 run log

## 2026-10-28: validity gate
The simulator over live production (37 cards, 84 chunks) reproduced the batch-1 final retrieval for 61/61
real questions, with score difference 0. Gate passed.

## 2026-10-28: cards v1, retrieval only (before any generation)
- 8 cards, 16 chunks (2 sections each). Retrieval changed for 43/61 real questions.
- **C1 failed on the first check:** "เล่นเวทแล้วปวดข้อเข่ามาก ควรทำยังไง" passed the 0.63 gate through
  pre-workout-meal (branch 3/15, main 2/15). No query crossed the 0.66 out-of-scope score.
- **Fix:** retitled pre-workout-meal and its headings to name food and meals explicitly. Recheck: C1 branch
  2/15, main 2/15, so **C1 passes**. The knee query's best score is 0.629 (protein-requirement), the same
  as main.
- **C2 (raw labels):** main 112, branch 110. Lost: Q080 and Q139 (Q087 recovered after the retitle).
  - **Relabelling, recorded before generation:** Q080 was already relabelled in batch 1 to accept
    pre-sleep-protein-casein, which the branch still retrieves at rank 1, so it is not lost. Q139
    ("refeed หรือ diet break…") now retrieves diet-breaks-refeeds, which covers it, and is relabelled.
  - After relabelling: 0 lost. **C2 passes.**
- **Watch item:** alcohol-training appears at the bottom of a few protein questions (TH08, TH45, Q087).
  Check the answers for this.

## 2026-10-28: round 1 review (AI preliminary)
- **B (held-out):** branch 16/16, main 4/16. **B passes.** Notes: K03 slightly overstates the refeed
  finding (Campbell correction); K15 calls DIAAS < 75 "low quality" where FAO says "no quality claim".
- **A (75 rerun results vs live):** branch 61, live 65. **A1 fails.**
  - 8 pass→fail: TH02-r3, TH13-r1, TH15-r1, TH19-r2, TH20-r1, TH20-r2, TH25-r1, YT02-r1.
  - 4 fail→pass: TH02-r2, TH14-r2, TH27-r1, TH38-r1 (borderline). Policy 5/5 unchanged.
- **A4 triggered.** Weight-loss plateau questions (TH15, TH19, TH20, TH25) now retrieve
  diet-breaks-refeeds, meal-frequency and sleep-body-composition chunks. These push
  metabolic-adaptation and energy-balance-cut-bulk down, and the answers lose the "why the weight is
  not dropping" explanation (estimation error, adaptation, water). TH13 lost its brand-free criteria with
  protein-quality chunks retrieved twice. TH02-r3 and YT02-r1 have no batch-2 card in retrieval
  (variance).
- **Plan (recorded before any rerun):**
  1. Reword diet-breaks-refeeds, meal-frequency and sleep-body-composition so their titles and openings
     name their own topic, not weight-loss plateaus.
  2. Recheck retrieval for the plateau questions, C1 and C2.
  3. Rerun every real question whose retrieval changes against round 1, plus any held-out item whose
     retrieval changes.

## 2026-10-28: card edits for round 2 (before any round-2 generation)
- Condensed four cards to one section each: diet-breaks-refeeds, meal-frequency, sleep-body-composition and
  protein-quality. Titles and headings now name their own topic. No number was changed; the text is
  shortened from the same sources.
- **Plateau retrieval after the edit:** each of TH14, TH15, TH16, TH19, TH20 and TH25 has at most one batch-2
  chunk. metabolic-adaptation is back in TH16 and TH19.
- **C1:** 2/15 on both arms. No query crosses 0.66.
- **C2 (raw):** 109/125 vs 112. Lost: Q080, Q087, Q139.
  - Relabelling (recorded now): Q080 keeps pre-sleep-protein-casein at rank 1 (batch-1 relabel). Q139
    retrieves diet-breaks-refeeds. Q087 ("ระหว่างวันกินไม่ครบมื้อ…") retrieves meal-frequency, which
    covers meal count.
  - After relabelling: 0 lost. **C2 passes.**

## 2026-10-28: round 2 review (AI preliminary)
- **B:** all 9 rerun held-out items pass. Final branch 16/16, main 4/16.
- **A (final over 75: round 2 where rerun, round 1 elsewhere):** branch 63, live 65. **A1 still fails.**
  - Round-2 subset: 27/34 vs live 29/34.
  - pass→fail: TH02-r3 and TH05-r3 (variance, no batch-2 card), TH26-r3 (validation block), TH15-r1,
    TH20-r1 and TH20-r2.
  - fail→pass: TH02-r2, TH14-r2, TH20-r3, TH27-r1. Policy unchanged.
- **Remaining crowding:** in TH20 the single diet-breaks chunk (rank 5) pushes metabolic-adaptation to
  rank 7. The answers again lack causes.
- **Plan (owner said "ช่วยลองอีกครั้ง"):**
  1. Reword diet-breaks-refeeds until TH15 and TH20 retrieve metabolic-adaptation as on live.
  2. Recheck C1 and C2.
  3. Rerun items whose retrieval changes against round 2.

## 2026-10-28: card edit for round 3 (before any round-3 generation)
- **Cause:** on dense similarity alone, diet-breaks-refeeds ranks low for the plateau questions (TH20: 12th).
  It entered the top 6 through BM25 fusion, because its text contained the questions' own words
  "คุมอาหาร" and "ลดน้ำหนัก".
- **Fix:** replaced those words in diet-breaks-refeeds with equivalent phrasing ("น้ำหนักลง", "เสียไขมัน",
  "เมื่อต้องขาดดุลพลังงานเป็นเวลานาน"). No number changed.
- **Result:**
  - TH14, TH15 and TH20 no longer retrieve the card, and TH20 has metabolic-adaptation back.
  - C1: 2/15 on both arms; nothing crosses 0.66.
  - C2: unchanged (Q080, Q087, Q139 lost raw; all relabelled; 0 lost).
- **Round 3 rerun set** (retrieval changed against the latest results): real TH14, TH15, TH16, TH19, TH20,
  TH25, TH47; held K03, K04.

## 2026-10-28: round 3 review (AI preliminary)
- **Held-out K03, K04:** pass. B final: branch 16/16, main 4/16.
- **Real questions:** all 13 rerun results pass. The plateau answers again give causes (estimation error,
  adaptation, water) from metabolic-adaptation and energy-balance-cut-bulk.
- **Final over the 75 changed results** (latest round per item): branch 67, live 65. **A1 passes.**
  - 5 fail→pass: TH02-r2, TH14-r2, TH19-r1, TH20-r3, TH27-r1.
  - 3 pass→fail: TH02-r3 and TH05-r3 (no batch-2 card in retrieval; variance), and TH26-r3 (validation
    block for wrong citation labels S4/S5; none of the claimed content comes from a batch-2 card).
  - **A4:** none of the 3 flips is caused by card content. **A4 passes.**
  - **A2:** no factual error. TH17-r1 mislabels the DIAAS ≥ 75 class as "PDCAAS" (minor, noted).
  - **A3:** policy results 5/5 unchanged.
  - Service: TH02-r1 (identical to live, provider 503 on both).
- **C1, C2:** pass (C2 with the relabelling recorded before generation).
- **Decision:** all frozen criteria pass after round 3. Proceed to PR and merge, per the owner's request to
  measure before merge.

## Live check (28 Oct)

- Ingested from `c865467` to production: 45 documents, 97 chunks, no null embeddings.
- Five questions on www.nutrilift.xyz in fresh chats with the owner's account (K05, K13, TH20, K11, TH45):
  four pass and TH45 is refused by the medical policy as before. Details in README.md.
