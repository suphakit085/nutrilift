# Knowledge-base batch 2: frozen criteria

Frozen 2026-10-28, before any batch-2 card was written. The owner asked on 28 Oct 2026 to start batch 2 and
to measure it the same way as batch 1 before merging.

**Cards:** 8, on common lifter topics the 37 live cards do not cover:

| Slug | Topic |
|---|---|
| `pre-workout-meal` | pre-workout meal |
| `diet-breaks-refeeds` | diet breaks, refeeds, cheat meals |
| `alcohol-training` | alcohol and training |
| `sleep-body-composition` | sleep and body composition |
| `dietary-fat` | dietary fat |
| `sugar-sweeteners` | sugar and sweeteners |
| `meal-frequency` | meal frequency and late eating |
| `protein-quality` | protein quality, PDCAAS/DIAAS |

Two planned topics were dropped because live cards already cover them: rate of weight change / lean vs
dirty bulk (energy-balance-cut-bulk, weight-gain-underweight) and carbs-at-night myths (fat-loss-myths).

Assessment: preliminary AI review (Claude), not human review. Unlike batch 1, these topics were not
chosen from real-question failures. The real questions therefore measure regression only, and the
held-out questions (AI-written, so secondary) measure coverage.

## Baseline ("main")

Production with 37 cards (commit 152cb71). Simulator validity gate: it reproduces the batch-1 final
retrieval for 61/61 real questions, with score difference 0.

## A. Real questions (61 questions / 101 results): regression only

- Rerun items whose retrieval changes, with the same repeats (core 3, others 1).
- Baseline verdicts: the batch-1 final verdicts. That is round 2 where it was rerun, round 1 for other
  changed items, and c0201c3 for unchanged items.
- Merge requires all of:
  1. **A1:** pass count over the rerun items ≥ baseline pass count over the same items.
  2. **A2:** no new factual_error traceable to a new card.
  3. **A3:** policy items stay pass-by-policy.
  4. **A4:** any pass→fail flip caused by new card content blocks merge until the card is fixed and rerun.

## B. Held-out questions (16, AI-written): coverage, secondary

- Run once on main and once on the branch.
- Target: branch ≥ 12/16 and more than main.
- No factual error traceable to a card.

## C. Retrieval safety (embedding only)

- **C1:** off-topic gate passes on the branch ≤ main. Also, no off-topic query may cross the 0.66
  out-of-scope score.
- **C2:** hit@k on the 125 labelled eval items, measured against the batch-1 C2 relabelling (Q018, Q040,
  Q077, Q080, Q085 accept the batch-1 card). It must not fall by more than 2 items versus main. Items
  that switch to a batch-2 card covering the question are listed and re-labelled explicitly in RUNLOG
  before any generation result is seen.

## Held-out questions

| id | card | question | key points | forbidden |
|---|---|---|---|---|
| K01 | pre-workout | ก่อนเล่นเวทควรกินอะไร กินก่อนกี่ชั่วโมง | a meal with carbohydrate and protein a few hours before, or a smaller snack closer; tolerance matters; daily totals first | "must eat X exactly 30 min before" |
| K02 | pre-workout | เล่นเวทตอนเช้าตอนท้องว่างได้ไหม หรือควรกินอะไรก่อน | possible; pre-exercise protein/carbs may help some; individual tolerance; daily totals | "fasted training burns more fat" as fact |
| K03 | diet breaks | cheat meal ช่วยให้ลดไขมันดีขึ้นจริงไหม | refeeds and diet breaks are planned returns to maintenance; evidence is limited or mixed; overall energy balance decides fat loss | "cheat meals speed up metabolism" as fact |
| K04 | diet breaks | diet break คืออะไร ควรทำไหมตอนลดไขมัน | 1-2 weeks at maintenance during a long cut; MATADOR-type study findings; may help adherence; not mandatory | invented protocols |
| K05 | alcohol | ดื่มเหล้าเบียร์หลังเล่นเวทมีผลกับกล้ามไหม | alcohol after exercise reduced myofibrillar protein synthesis in a study even with protein; adds energy; less is better | "a little alcohol helps recovery" |
| K06 | alcohol | ลดไขมันอยู่ กินเบียร์ได้ไหม | alcohol has 7 kcal/g, counts toward energy, can displace food; amount matters | medical claims about liver disease |
| K07 | sleep | นอนน้อยมีผลกับการลดไขมันไหม | a study with sleep restriction during a diet lost a smaller share of weight as fat and more lean mass; sleep matters for body composition | diagnosing sleep disorders |
| K08 | sleep | นอนกี่ชั่วโมงดีสำหรับคนเล่นเวท | recommendations of 7+ hours for adults (source needed); the system does not treat sleep disorders | inventing a number without a source |
| K09 | fat | ไขมันควรกินวันละเท่าไหร่ | ~20-35% of energy or ~0.5-1.5 g/kg (Iraki); 15-30% in contest prep (Helms); not too low | "fat must be cut to zero" |
| K10 | fat | ไขมันอิ่มตัวควรจำกัดไหม | WHO: saturated fat under 10% of energy; replace with unsaturated | disease treatment advice |
| K11 | sugar | น้ำตาลควรกินไม่เกินวันละเท่าไหร่ | WHO: free sugars <10% of energy, ideally <5%; example in grams or teaspoons | wrong thresholds |
| K12 | sweeteners | ใช้น้ำตาลเทียมแทนน้ำตาลช่วยลดน้ำหนักไหม | WHO 2023 suggests not using non-sugar sweeteners for weight control; long-term evidence limited | "sweeteners are proven to cause disease" |
| K13 | meal frequency | กินวันละ 6 มื้อช่วยเร่งเผาผลาญจริงไหม | meal frequency does not meaningfully change fat loss when energy is equal; choose by preference; protein spread | "6 meals boost metabolism" as fact |
| K14 | meal frequency | กินมื้อดึกแล้วอ้วนจริงไหม | total energy decides; timing is secondary; pre-sleep protein studies | "eating late definitely makes you fat" |
| K15 | protein quality | โปรตีนสมบูรณ์คืออะไร DIAAS คืออะไร | complete protein has all EAAs in adequate amounts; PDCAAS/DIAAS rate quality; animal and soy proteins score high; plant combinations help | wrong definitions |
| K16 | protein quality | โปรตีนพืชคุณภาพสู้โปรตีนสัตว์ได้ไหม | many plant proteins are lower in some EAAs or leucine; combining and adequate totals help; soy is complete | "plant protein cannot build muscle" |
