# Diary request ordering and recovery — 2026-10-17

Rapid date changes could display an earlier day's food entries under the newly
selected date. Rapid food searches could similarly display results for an older
query. Search failures were indistinguishable from a successful empty response.

The diary now invalidates outstanding reads as soon as the date changes and
applies responses only when both the date and request sequence still match.
Changing dates clears the previous day's data, closes the picker and disables
food actions until loading finishes. The date controls remain available during
loading. Completion or failure of an older day's mutation cannot refresh or
display errors on the current day. Failed loads have a retry button.

The food picker invalidates requests on input changes, effect cleanup and
unmount. It clears obsolete results immediately and distinguishes loading,
successful empty results and failure. Search failures offer a retry button.

## Scope

This frontend patch is based on the deployed dependency security release
`f102d8ddf669b69fd9125747b79b5418751dfce1`. It requires no API changes,
database migrations or email configuration. The wider account rollout and
historical target calculation are separate work.

## Verification before release

- ESLint, Next route generation, TypeScript and the production build passed.
- Frontend unit tests: 78 passed, 0 failed.
- npm audit: 0 known vulnerabilities at the time checked.
- Chrome against the production build locally: 23 checks passed, 0 failed.
- The same browser script against the previous live frontend reproduced stale
  dates, stale searches and missing recovery UI: 13 failed observations and
  7 passed. Some steps stop after an earlier failure, so these counts are not
  directly comparable with the 23 successful checks.
- Viewports 390, 768 and 1280 px had no horizontal overflow in this run.

The browser fixture controls only its own API requests. It uses conspicuous
synthetic data and a placeholder browser token; no real users, database writes
or outgoing email are involved. It covers late successful and failed responses,
cleared searches, picker unmount/remount, old-day writes, HTTP 503, network
failure, retries, genuine empty results and JavaScript exceptions.

Run after `npm ci` and `npm run build` from `frontend/`:

```powershell
$env:NEXT_PUBLIC_API_BASE = 'https://api.example.invalid'
npm run build
npm run test:diary-ui
```

For a deployed frontend, set `DIARY_UAT_ORIGIN` and `DIARY_UAT_API_BASE` to its
frontend and API origins before running the script. API requests are intercepted
inside this isolated browser session. `DIARY_UAT_ARTIFACT_DIR` can select the
evidence directory. The default is `output/playwright/diary-regressions/`.
GitHub Actions runs the fixture after the production build and uploads evidence.

Local evidence:

- Before: `output/playwright/diary-fix-20261017/before/results.json` in the main workspace.
- Fixed: `output/ci-cd/diary-release/output/playwright/diary-regressions/2026-10-17T10-42-35-436Z/results.json` in the main workspace.

These checks establish the specified behavior in Chrome. They do not establish
that the entire application is defect free or certify other browser engines.
