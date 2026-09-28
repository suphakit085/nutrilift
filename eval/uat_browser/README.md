# Browser UAT snippets

These are Playwright CLI snippets used for the 2026-09-28 production UAT.
They are stateful steps, not independent Playwright Test specifications.
Results and raw answers are recorded in `docs/UAT-system-report-2026-09-28.md`
and the adjacent evidence JSON files.

Use disposable accounts only. `eval/uat_system.py api` creates A/B, and `chat`
creates the history expected by the browser snippets. Credentials are in the
ignored `output/playwright/uat-system/session.env`; never commit that file or
print tokens. Choose a fresh `--evidence` path for a new campaign and use that
same path for every phase. Do not append a new campaign to the accepted report.

Run a snippet with an already open browser session:

```text
npx --yes --package @playwright/cli playwright-cli -s=default snapshot
npx --yes --package @playwright/cli playwright-cli -s=default run-code --filename eval/uat_browser/profile.cjs
```

Execution order and prerequisites:

1. `signup.cjs`: visit `/profile` while logged out, verify redirect, then select the signup tab.
2. Run the API `expire-consent` phase for B. Log in as B using the UI.
3. `consent.cjs`: decline consent; log in again, check consent, and accept through the UI.
4. Visit `/profile`; `profile.cjs` saves and reloads the synthetic profile.
5. Visit `/log`; `diary.cjs` needs an empty diary on the selected date. The CLI may yield during native dialogs; final results are also stored temporarily under `uat-diary-results` in session storage.
6. Visit `/chat`; `chat.cjs` opens the history created by AI-01 and starts a new conversation.
7. `mobile.cjs` checks the open chat's citation disclosure and mobile menu.
8. `recovery.cjs` injects failures only into the test browser, removes each route afterward, and ends logged out with an invalid-token check.
9. Log in as B again; `recovery-retest.cjs` repeats the failed recovery sequence and captures the visible error.
10. Log out, remove the test session-storage key, and always run the API `cleanup` phase with the database env file, including after a failed test.

The CLI returns per-case result objects. Save them without the CLI's echoed
credential-entry commands. Screenshots are generated under `output/playwright/uat-system/`.
The `review` phase detects internal-heading markers; full answer quality still
requires inspecting the actual responses. A PASS from a transport/flag assertion
alone is not expert approval of nutritional content.
