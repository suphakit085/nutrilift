# Run log

## Round 1 (only round)

Main `9921154` vs branch `fix/trim-keeps-answer` (`c334ea2`), 12 questions x 3 repeats each, full answers through
`chat.stream_understood_chat`, sample profile of c0201c3, production retrieval read-only.

Service failures (kept in `branch-service-fail/`, not counted): the branch run hit the daily quota on two keys
(`request_understanding_unavailable` / provider quota message, 10 results, then 4 more on rerun). Each was rerun
on a key with quota left until all 36 finished. Main had none.

Review: one merged sheet with arm hidden behind a code (`sheet.json`, `sheet-key.json`), judged against the frozen
c0201c3 expectations; preliminary AI review (Claude). Verdicts in `verdicts.json`.

| Measure | main | branch |
|---|---:|---:|
| answers trimmed | 4 | 4 |
| lost-answer gate fired | – | 1 (TH19-r2) |
| M1 trimmed and missing the key point | 2 (TH16-r2, TH19-r3) | 0 |
| M2 pass | 33/36 | 33/36 |
| M3 errors (excluding provider quota) | 0 | 0 |
| M4 median seconds | 30.3 | 31.7 |

- C1 pass (0 < 2, ≤ 1). C2 pass (33 ≥ 33). C3 pass. C4 pass (+1.4 s).
- Failures on main: TH16-r2 (trimmed to metabolic adaptation only), TH19-r3 (trimmed to targets and trend
  tracking, no causes), TH27-r2 (ranges only, does not say rest days keep the same protein).
- Failures on the branch: TH19-r2 (the gate fired; the extra draft states that the sources do not cover the
  causes and gives targets and tracking, still no causes), TH20-r1 and TH20-r3 (not trimmed; the known
  "sources do not cover" hedge, limitation 13 in the owner's decisions).
- So the gate removed every trimmed answer that missed the key point, but for TH19 the extra draft was an honest
  coverage statement rather than a passing answer. The pass count is unchanged in this sample.
