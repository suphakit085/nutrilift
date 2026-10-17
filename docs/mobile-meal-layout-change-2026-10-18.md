# Mobile meal layout — 2026-10-18

## Problem and resulting behaviour

Production persona UAT found a meal table about 689 px wide inside a 270 px phone message. Reading a food and its nutrient amounts required horizontal scrolling. Repeated canonical food names also made data-limit warnings difficult to scan.

Below 768 px, known meal tables now render as one card per source row. Every food, portion, nutrient column and daily total remains present. A zero remains zero; an unfinished streamed cell displays an em dash rather than an invented number. At 768 px and above, and in print, the original table remains available. Other comparison tables retain their existing scrollable layout.

The full warning message remains visible. Only the trailing food-name list in the explicitly labelled food-data-limit section uses a native keyboard-operable disclosure. Allergy precautions, unknown fibre, target deficits and menu limitations remain visible. The raw answer, stored history and API contract are unchanged.

## Scope and verification

- Presentation only: no dependency, database, menu calculation, portion policy, safety detection or auth rollout.
- 89 frontend tests passed, including streamed prefixes, unmodified food names containing commas/parentheses, supplemental rows, totals and zeroes.
- Lint, Next type generation, TypeScript and production build passed locally.
- Chrome recorded-answer replay: 48/48 checks passed at widths 320, 390, 430, 767, 768 and 1280, covering three-meal partial plans, six-meal successful plans and vegan plans with unknown fibre. All food portions and numeric cells were compared against the recorded answer. Keyboard disclosure, print, generic-table fallback and literal HTML safety passed.
- The recorded-answer replay intercepts API requests and creates no accounts or database data; it does not claim fresh live API coverage.
- CI runs both the existing diary browser regression and the new meal-layout regression, retaining screenshots and JSON results.
- Live production validation must follow a successful Vercel deployment. Its results belong in the production UAT report.

## Remaining release boundary

This patch does not enable the pending account-security changes. On 2026-10-18 the owner confirmed that nutrilift.xyz DNS is not configured and Resend is not Verified. Real verification/reset email delivery, staging migration and integrated production auth UAT remain required before that work can be closed.
