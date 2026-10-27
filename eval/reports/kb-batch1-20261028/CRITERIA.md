# Knowledge-base batch 1: frozen criteria

Frozen 2026-10-27T16:47Z, before any new card was written. The owner asked on 27 Oct 2026 to expand the
knowledge base for maximum coverage (reversing the 24 Oct "no new cards" decision). Batch 1 has 11 cards
on topics where real questions failed or hedged in the c0201c3 run.

Assessment: preliminary AI review (Claude). This is not human review. The cards were chosen from failure
topics in the 61 real questions, so the real-question result is in-sample. The held-out set (H) was written
by AI, not taken from users, so it is a secondary measure only.

## Method

- Retrieval: production chunks (read-only) plus the new card chunks, embedded with the same `embed_texts`
  and scored by the same code path as `retrieval.search` (cosine, domain gate, relative window, BM25 fusion).
  This runs in memory; production is not written.
- **Validity gate (must pass before anything else):** with the new cards excluded, the simulator must
  reproduce the frozen c0201c3 passages (same slugs, headings and order) for all 61 questions. If it does
  not, stop and report.
- Answer generation: same runner as c0201c3 (`stream_understood_chat`, sample profile, same model,
  pacing, keyring), with retrieval swapped for the simulator.

## A. Real questions (61 questions, 101 results), primary

- Items whose branch retrieval equals the frozen context are carried over unchanged from c0201c3.
- Items whose retrieval changes are rerun on the branch with the same repeats as c0201c3 (core 3, others 1).
- Baseline: c0201c3 verdicts (same code and contexts, 2 days earlier), verdict rules unchanged
  (condition.json, amendment 12.3).
- Merge requires all of:
  1. A1: pass count over the changed items ≥ baseline pass count over the same items.
  2. A2: no new `factual_error` traceable to a new card.
  3. A3: all medical-policy items (TH43–TH46, YT08, YT09) stay "pass by policy" if their retrieval changes.
  4. A4: every pass→fail flip is listed with its cause. A flip caused by a new card's content blocks
     merge until the card is fixed and the item rerun.

## B. Held-out questions (22, AI-written), secondary

- Run once on main (current production retrieval) and once on the branch.
- A result passes if it covers the key points and avoids the forbidden content below.
- Target: branch passes ≥ 16/22 and more than main; no factual error traceable to a card.

## C. Retrieval safety (embedding only, no generation)

- C1: off-topic leak. The off-topic queries in `eval/calibrate_threshold.py` and the out-of-scope items in
  `eval/questions.jsonl` must not pass the domain gate more often on the branch than on main.
- C2: no displacement. On the 143 on-topic items of `eval/questions.jsonl`, hit@k for `relevant_doc_slugs`
  must not fall by more than 2 items.

## Held-out questions and expectations

| id | card | question | key points | forbidden |
|---|---|---|---|---|
| H01 | whey types | เวย์ไอโซเลตกับคอนเซนเทรตต่างกันยังไง คุ้มไหมที่จ่ายแพงกว่า | isolate ≥90% protein; concentrate 29–80% (sport products ~70–80%); isolate has less lactose and fat; choose by protein per serving, tolerance and price | brand names; claiming isolate builds clearly more muscle |
| H02 | whey types | เวย์ไฮโดรไลซ์ดีกว่าเวย์ธรรมดาไหม | pre-digested, faster amino-acid rise; some studies on recovery; evidence for more muscle gain is limited or mixed | claiming clear superiority |
| H03 | pre-sleep | กินโปรตีนก่อนนอนจะทำให้อ้วนไหม | total daily energy decides fat gain; studies of 30–40 g casein before sleep raised overnight MPS without blunting fat oxidation; optional | "eating before bed definitely makes you fat" |
| H04 | pre-sleep | เคซีนคืออะไร ต่างจากเวย์ยังไง ควรกินตอนไหน | casein digests slowly, whey quickly; pre-sleep casein 30–40 g studied; daily total matters more | saying timing matters more than daily total |
| H05 | whey vs meals | ดื่มเวย์แทนข้าวเที่ยงทุกวันได้ไหม | whey supplies protein but not the carbohydrate, fibre and micronutrients of a meal; food first, powder for convenience | calling whey a complete meal |
| H06 | whey vs meals | เวย์ผสมนมกับผสมน้ำต่างกันไหม | milk adds energy, protein, carbohydrate and fat (useful when gaining); water keeps energy lower (useful when cutting); choose by goal | invented nutrition numbers |
| H07 | BCAA | ต้องกิน BCAA ระหว่างเล่นเวทไหม | not needed when total protein is adequate; BCAA alone lacks the other EAAs; acute MPS rise smaller than whole protein | "BCAA is necessary" |
| H08 | BCAA | BCAA กับเวย์อันไหนคุ้มกว่าสำหรับสร้างกล้าม | whey contains BCAA plus all EAAs; complete protein preferred | recommending BCAA over whey |
| H09 | protein, high weight | หนัก 120 กิโล ไขมันเยอะ ต้องกินโปรตีน 240 กรัมจริงเหรอ | per-kg ranges come mostly from lean or athletic people; multiplying a high actual weight overestimates; alternatives: per-LBM ranges or weight-loss studies at 1.2–1.6 g/kg; professional advice at high BMI | insisting on 2 g/kg of actual weight |
| H10 | protein, high weight | คิดโปรตีนจากมวลไร้ไขมัน (LBM) ยังไง | LBM = weight × (1 − body-fat fraction); apply a per-LBM range; body-fat estimates carry error | wrong formula |
| H11 | keto | กินคีโตแล้วเล่นเวทหนักได้ไหม แรงจะตกไหม | short studies mostly show no strength or power difference; higher-intensity work may suffer; some studies show lean-mass loss or blunted hypertrophy; fat loss follows the energy deficit | "keto is best for lifting" |
| H12 | keto | คีโตกินคาร์บได้วันละเท่าไหร่ | about 50 g or ~10% of energy; protein moderate (1.2–1.5 g/kg); fat ~60–80% | wrong thresholds |
| H13 | carbs | คนเล่นเวทควรกินคาร์บวันละกี่กรัม | no single number; ≥3–5 g/kg suggested for bodybuilders off-season; strength-sport proposals 4–7 g/kg; set protein and fat first | one fixed number for everyone |
| H14 | carbs | ไม่กินแป้งเลยจะสร้างกล้ามได้ไหม | carbohydrate is not essential, but it supports training and glycogen; very low carb may hurt training; gaining is possible with enough energy and protein | "impossible" |
| H15 | BMR history | สูตร Harris-Benedict กับ Mifflin ต่างกันยังไง อันไหนแม่นกว่า | Harris and Benedict 1918/1919; Mifflin, St Jeor et al. 1990 (498 adults; Harris-Benedict overestimated by 5% there); in athletes no equation is guaranteed best; all are estimates | wrong names or years |
| H16 | BMR history | TDEE คำนวณยังไง ตัวคูณกิจกรรมมาจากไหน | BMR × activity factor (PAL); FAO/WHO/UNU 2004 PAL bands 1.40–1.69 / 1.70–1.99 / 2.00–2.40; an estimate, adjust by weight trend | presenting TDEE as measured |
| H17 | budget protein | อยากกินโปรตีนให้ถึงแต่เงินน้อย ควรเลือกอะไร | low-cost protein foods (eggs, tofu, soy milk, chicken, canned fish, milk); compare protein per serving; the system has no price data | invented prices |
| H18 | budget protein | เต้าหู้กับไข่ อะไรให้โปรตีนมากกว่า | per-100 g values from the food database; depends on tofu type | invented values |
| H19 | weight gain | กินเท่าไหร่ก็ไม่อ้วน อยากเพิ่มน้ำหนัก ทำยังไง | a sustained surplus; energy-dense foods; snacks with protein and carbohydrate between meals; resistance training; track the weekly weight trend | junk food as the main approach |
| H20 | weight gain | เกนเนอร์จำเป็นไหมสำหรับคนผอม | not necessary; food first; a supplement can be a convenience | "gainer is necessary" |
| H21 | sports drinks | เล่นเวทชั่วโมงเดียวต้องกินเกลือแร่ไหม | water is enough for most people; carbohydrate-electrolyte drinks help in long or endurance sessions; sugar counts toward energy | "always necessary" |
| H22 | sports drinks | หลังออกกำลังกายดื่มนมดีไหม | milk after exercise supports recovery, rehydration and protein balance in studies | medical claims |
