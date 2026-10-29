# Run log

## Round 1 (branch commit: working tree of fix/food-suggestion-conditions, first version)

Interpretation only, 3 repeats, main `3d3c53d` (key start 2) vs branch (key start 4). Results kept in
`probe-main.json` and `round1/probe-branch.json`.

- C1 target: main 15/21 list routes, branch 0/21. **Pass.**
- C2 keep: main 18/18, branch 16/18. **Fail** (needs ≥ 17).
  - K1-r2 "แนะนำอาหารโปรตีนสูงที่หาง่ายหน่อย": "หาง่าย" recorded as shop_or_place.
  - K4-r2 "ขออาหารโปรตีนสูง 5 อย่าง ไม่เอาหมู": "ไม่เอาหมู" recorded as other instead of exclude
    (I assumed pork was a supported exclusion value; round 2 found it is not).
- Conditions recorded on the branch: budget 9, shop_or_place 7, dishes_to_order 3, yes_no_or_comparison 3, other 1.

Change before round 2 (recorded before rerunning): the field description and the system line now say that
food exclusions always go in `exclude`, never in `unsupported_conditions`, and that a general wish for
common or easy-to-find foods is not a condition (the database list is common foods). Same probe set and
criteria; branch rerun with 3 repeats; main results reused.

## Round 2

Branch rerun after the description change (results in `probe-branch.json`, log `probe-branch.log`).

- C1 target: main 15/21, branch 0/21. **Pass.**
- K1 is back to 3/3. K4 is 1/3 on the branch.
- **K4's frozen expectation was wrong.** `DIETARY_VALUES` has no pork value, so on main "ไม่เอาหมู"
  never reaches `exclude` (main recorded `exclude: []` in 3/3) and the list it returns is the default one,
  whose second item is "หมู, สันใน, ต้ม". Main's 3/3 "list routes" for K4 are wrong answers. The branch
  records "ไม่เอาหมู" as an unsupported condition in 2/3 and sends the turn to the normal answer, which is
  the intended behaviour for a condition the list cannot honour. K4 is therefore left out of C2. This is a
  correction of my own expectation, not a criteria change made to pass.
- C2 without K4: main 15/15, branch 15/15, no K question at 0/3. **Pass.**

## Round 2: real questions and full answers

- C3 routing: interpretation of the 61 real questions, main twice (`real-main.json`, `real-main2.json`) and
  branch once (`real-branch.json`). Main against itself differs in 12 questions on other routing fields, the
  branch against main in 15-20, so those fields are already noisy at one run each. List-route change: TH32
  only (main r1 listed, branch not, branch recorded "เล่นเวท" as `other`).
- Full answers on the branch (`gen-branch/`, 5 items first hit `request_understanding_unavailable`; kept in
  `gen-branch-service-fail/` and rerun after checking the keys):
  - C4: T1-T7 all address the stated condition (shop dishes, 7-Eleven items, no price data, whey not
    required if eggs cover protein, eggs vs chicken numbers). 7/7, preliminary AI review.
  - TH42: branch answers the supplement question (main c0201c3 r2/r3 failed).
  - **TH32 regresses:** main c0201c3 passed with a vegetarian protein list; the branch answers that the
    system does not cover vegetarian menus. **C3 fails.** Cause: "เล่นเวท" (who the foods are for) was read
    as a condition.

Change before round 3 (recorded before rerunning): the description says who the foods are for (lifters,
vegetarians, beginners) is not a condition; diets go in `exclude`. Branch reruns: probe set 3 repeats,
61 real questions once, TH32 end to end.

## Round 3 (final)

Branch after the round-3 description change. Main results reused.

- C1 target: main 15/21, branch 0/21. **Pass.**
- C2 keep: main 18/18, branch 17/18 even counting K4 (K4 1 miss, see round 2). **Pass.**
- C3 real questions (`real-branch.json`): against main run 2 no list-route change; against main run 1 only
  TH42 (branch lists, main run 1 did not, main run 2 did: main's own variance). Other routing fields differ in
  15-16 questions against 12 between the two main runs. TH32 end to end on the branch returns the vegetarian
  list (`rule:food_suggestion`, ไข่ขาว / เต้าหู้ / เทมเป้), as main c0201c3. **Pass.**
- C4: the full answers are from round 2 (`round2/gen-branch/`). Round 3 changed only the field description;
  T1-T7 stay off the list route in 21/21, so they take the same answer path. 7/7. **Pass** (not regenerated).
- C5: see the PR (backend tests and ruff).
