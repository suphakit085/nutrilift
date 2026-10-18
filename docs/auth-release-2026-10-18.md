# Account security release — 2026-10-18

## Resulting behaviour

Registration creates a pending account. The mailbox owner opens a single-use link and chooses the final password before profile, chat or diary access. Password recovery and email changes use expiring, hashed action tokens. Logout revokes the server session; reset/password changes revoke existing sessions. Account export, consent withdrawal and deletion remain available through explicit ownership/password checks.

Resend HTTPS is the delivery provider for Railway. The owner verified `nutrilift.xyz`, configured the backend variables and supplied a sending key privately for testing. Both real verification and password-reset emails from `noreply@nutrilift.xyz` reached the owner's Inbox, as confirmed by the owner. The key and recipient are outside Git and never included in reports or CI.

## Compatibility and migration

- Base main: `5d6b761`; the released meal, diary, intent, safety-copy and mobile-card patches are retained.
- Alembic upgrade: current production `f16c6106a002` → `f16c6106a001`. New columns are nullable; no existing mailbox is marked verified without proof.
- Old JWTs have no server session and require a fresh login. Existing accounts retain their password/data, then confirm mailbox ownership and the current consent notice. Mailbox verification chooses a replacement password to prevent an attacker keeping a password from pre-registration.
- The frontend accepts the old API's missing verification flag during a frontend-first deployment. Local logout is retained only when a 404 logout response is followed by a confirmed legacy `/auth/me` contract. New-API, network and service failures remain errors. No legacy JWT bypass is added to the new backend.
- Before production migration, the application public schema/data was exported with PostgreSQL 17 in read-only SSL session mode and encrypted. The recovery key is protected with Windows DPAPI for the current local user. The backup excludes Supabase platform schemas and storage objects.
- Restore drill: decrypted in memory, restored into an owned loopback PostgreSQL 17 container in tmpfs, then upgraded with the actual candidate Alembic code. Original columns and rows across nine application tables were unchanged. Legacy accounts remained unverified and no sessions were invented. The clone was destroyed afterwards.
- Rollback should use a reviewed restore/roll-forward plan. Do not automatically downgrade production: downgrade drops the new sessions/action-token tables.

## Validation before merge

- Backend: 1,252 regression tests; account/config targeted suite 93; Ruff passed.
- PostgreSQL: 43 tests including exact current production revision, previous legacy revision, row preservation, schema checks, one-use links under contention, concurrent password changes and profile/history regression.
- Frontend: 93 unit tests, lint, type generation/TypeScript and production build passed. Dependency audit reported zero vulnerabilities.
- Chrome account suite: 26/26 checks, using the actual isolated API and SMTP capture; the final frontend/old-API compatibility check uses a recorded contract fixture. Confirm dialogs for disposable withdrawal/deletion are explicitly accepted by the harness. This does not claim native-dialog coverage.
- Real Resend/browser suite: 13/13 checks on a disposable local account. Verification/reset links worked, were single use, cleared URL fragments and revoked old sessions; login with the resulting password worked. The owner separately confirmed both messages reached Inbox.
- The first broad regression had four failures because a profile stand-in still emitted legacy JWTs. Updating that stand-in to supply a verified user and actual session shape resolved all four. The first browser attempts exposed harness modal/async-readiness issues; those observations remain separate from passing runs. No auth guard was relaxed to make these tests pass.
- CI now runs account browser checks and PostgreSQL account migrations in addition to existing meal/diary checks. CI and production UAT results must be recorded after those runs finish.

## Evidence and remaining boundary

Local evidence: `output/auth-release-20261018/`; PostgreSQL reports: candidate `output/postgres-auth/`. Backup, local sending key, recipient, test passwords and action links are ignored by Git. Hosted artifacts contain only disposable test accounts.

At the time of preparing this record, the release has not yet been deployed. Production must be checked for `/auth/email-status`, verification gate, single-use recovery, logout revocation, existing account consent and normal profile/chat/diary access after deployment. Durable email retry and a shared rate limiter remain separate hardening work; this release does not claim independent clinical validation.
