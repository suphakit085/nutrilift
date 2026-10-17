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
