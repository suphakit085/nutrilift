# Historical nutrition targets — 2026-10-17

The diary previously recalculated every selected date from the current profile.
Editing today's weight or goal could therefore change yesterday's target, and
dates before a user had any known target showed invented historical values.

Profile saves now commit an immutable profile/target snapshot in the same
transaction. Diary summaries select the latest saved snapshot effective on or
before the selected Bangkok calendar date. Later saves cannot rewrite earlier
days. Multiple saves in one day use the latest completed save for that day.
User row locks serialize concurrent saves and first reads. Snapshot timestamps
increase even with equal or slightly backwards worker clocks.

Dates with no known snapshot return `target: null`, `remaining: null` and
`target_basis: unavailable_for_date`; food entries and consumed totals remain
available. The UI explains the missing historical data and shows the effective
date when a target is available. A user without a profile today sees the profile
setup link. A legacy user's first current-day diary read records a baseline so
the target remains available after that day ends; it does not fabricate earlier
history.

## Release scope

The isolated branch starts from the deployed diary/dependency fixes. Migration
`f16c6106a002` now follows `e43c6103b001` directly and adds only the history
table/index. The pending account migration depends on this history migration in
the development workspace. This release does not include the new auth rollout.

Production preflight found revision `e43c6103b001` and no history table. The
existing Docker startup runs Alembic before starting the API. The migration is
additive: existing users, profiles, food entries and authentication fields are
preserved. There is no backfill of targets for dates without evidence.

The runtime image installs `uv.lock` with `uv sync --locked`, matching the
dependency set used in CI. Its build, runtime imports and non-root user are
checked separately in CI.

## Verification before deployment

- 15 PostgreSQL history integration cases passed, including actual fresh
  migrations, upgrade/downgrade/re-upgrade preserving a legacy profile, ORM
  schema comparison, concurrent requests and Bangkok midnight.
- Those cases plus existing profile/food tests: 59 passed.
- The wider development account/history compatibility suite passed 91 tests on
  SQLite and real migrated PostgreSQL, with no skips.
- Frontend unit tests: 78 passed; lint, TypeScript and production build passed.
- Chrome: 26 browser checks passed, including the previous diary request-order
  regressions, unknown historical targets, saved-date labels and profile setup.
- The broad backend run passed 1,069 checks and exposed one pre-existing
  Windows/Git line-ending mismatch in the knowledge-card hash test. The fix
  retains the original recorded evidence hashes and checks canonical UTF-8/LF
  text against hashes derived from the verified original files; the three
  affected claim-release tests passed after correction. The complete backend
  suite also runs in Linux CI before deployment.

## Completed release checks

- Linux CI passed **15 PostgreSQL history cases and 1,070 backend regressions**.
  Backend image build/import/non-root checks also passed:
  [backend CI](https://github.com/suphakit085/nutrilift/actions/runs/39041581415).
- [Frontend CI](https://github.com/suphakit085/nutrilift/actions/runs/39041581314)
  passed, including 78 unit tests, dependency audit, lint/types/build and 26
  Chrome fixture checks.
- [PR #3](https://github.com/suphakit085/nutrilift/pull/3) merged as
  `798b7f55300c9173449bca9ee98d51156221b406`. CI also passed after the merge.
- Vercel production deployment `dpl_D3e8Z9A359b5tYMhoXweFNQWGTGX` is READY
  for that merge SHA. All 26 browser fixture checks passed against the live
  frontend. Those checks intercept API requests and do not prove backend rollout.
- The locked backend image built and booted locally, ran migrations from an
  empty PostgreSQL database and returned HTTP 200 health plus the new endpoint.
  A separate real-browser run against that image and PostgreSQL passed **15
  history checks with zero intercepted requests**. The controlled past snapshot
  belonged only to its disposable account; no application clock was changed.
  Changing its target from 2,579 kcal to 3,215 kcal and then changing profile
  again preserved past energy and all three macro targets, consumption and
  remaining energy. Reloads and 390/768/1280 px layouts passed.

## Verified production rollout

The owner triggered Railway's Deploy Latest Commit after the initial automatic
rollout did not happen. Railway deployment `7141400089` now records merge commit
`798b7f55300c9173449bca9ee98d51156221b406`. The live API exposes
`/profile/history`, the database is at `f16c6106a002`, and the history table is
present. The new auth/session tables remain absent, as intended for this release.
`/health` returned HTTP 200. A real UI chat question also received a completed
reply with no intercepted requests after the runtime/dependency update.

Before rollout, a disposable production account reproduced the bug: its diary
date before any known historical target incorrectly reported 2,579 kcal while
its actual saved food total was 232.5 kcal. After rollout, **7 real-account
migration checks passed**: its old token still worked, its profile was identical,
the 232.5 kcal food entry remained, today's target stayed correct and the past
date correctly became unavailable without losing its food data. These checks
ran before any synthetic historical snapshot was inserted.

Then one controlled past snapshot was inserted for that exact disposable UUID
and matching campaign email, copied from its real baseline. This enables testing
past-date behavior without waiting days or changing the application clock. It
does not represent verified historical data for a real user. Against that
fixture, **15 more production UI/API checks passed with zero intercepted
requests**, including two profile changes, unchanged historical energy and all
macros, correct remaining energy, reload persistence, same-day latest-save
ordering, missing-history messaging and responsive layouts. Total: **22/22
production history/migration checks** plus the separate chat smoke check.

After testing, the exact disposable user and matching email were checked before
deletion. Cascade cleanup removed its 1 profile, 4 revisions, 1 food entry,
1 conversation and 2 messages; all scoped counts were zero afterward. Its token
returned 401, browser credentials were cleared and test browsers/containers were
closed. No real user's history was edited or backfilled by the test.

Additional evidence in the main workspace:
`output/playwright/history-fix-20261017/before.json`, `merge.json`,
`production-frontend/results.json`, `local-flow-results.json`, and
`output/ci-cd/history-checks/ci-results.txt`.

Final production evidence: `after-deploy.json`, `production-api/results.json`,
`production-migration.json`, `railway-deployments.json`, `chat-smoke.json`,
`cleanup.json` and `cleanup-browser.json` under
`output/playwright/history-fix-20261017/`.

The browser-only fixture uses intercepted synthetic API responses. PostgreSQL
tests use disposable local databases with a loopback-only URL and no external
email or model calls. Production behavior is recorded separately after release.

## Reproducing checks

Use a disposable local PostgreSQL + pgvector database ending in `_test` and set
`DATABASE_URL` and `NUTRILIFT_PG_TEST_URL` to its loopback URL. From `backend/`:

```text
uv sync --locked --extra dev
uv run --locked --extra dev pytest tests/test_profile_history.py -q
uv run --locked --extra dev pytest tests -m "not postgres and not evidence" --ignore=tests/test_food_audit_fixes.py -q
```

From `frontend/`, build with `NEXT_PUBLIC_API_BASE=https://api.example.invalid`
and run `npm run test:diary-ui`. The GitHub workflows run these checks and retain
their test results/screenshots.

Local artifacts in the main workspace:
`output/ci-cd/history-release/output/history-pytest.xml`,
`output/ci-cd/history-checks/root-compatibility.xml`, and
`output/ci-cd/history-release/output/playwright/diary-regressions/`.

These are scoped functional and regression checks, not a claim that the whole
application is defect free or that nutrition advice has expert certification.
