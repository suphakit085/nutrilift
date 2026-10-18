# Email OTP signup — 18 October 2026

Owner-selected flow: **email → one-time email code → set the first password once**. Normal password login, password recovery, profile, chat and diary contracts remain in place.

## Behaviour

- `/auth/registration/start` accepts the email, adult assertion and consent. It creates a temporary challenge and sends a six-digit code through the configured Resend/SMTP transport. It creates no user or bearer session.
- `/auth/registration/verify` consumes the code and returns a short-lived setup grant. Only `/auth/registration/finish` can exchange that grant plus a valid password for a verified account/session. The frontend keeps the grant in component memory, never in local/session storage or the URL.
- New passwords are requested only after mailbox proof. The normal email/password login is unchanged.
- A previously verified account cannot have its password replaced through signup. After proving email ownership the user is directed to login/recovery. A legacy pending account can prove ownership and choose the final password; its previous sessions and email actions are revoked.
- Pending legacy email links remain valid until their existing expiration. Their endpoints are retained for compatibility; newly built signup screens use OTP.

## Limits and storage

- Six numeric digits generated with a cryptographic random generator, expires in ten minutes, one use, five persisted failed attempts maximum per challenge.
- Resend requires sixty seconds; each request generates a new challenge/code and invalidates the previous code/setup grant. Existing per-email and per-IP request limits also apply. PostgreSQL advisory/row locks serialize issuance and consumption across requests.
- Codes use a challenge-bound HMAC with the server secret rather than an unsalted hash of a small numeric space. Setup grants have high entropy and only their SHA-256 digest is stored.
- Migration `f16c6106a001` → `f16c6106a003` adds `registration_challenges`; existing user/password/session tables are not rewritten. Confirmed account deletion also removes matching registration challenges. Expired challenges older than a day are deleted opportunistically on subsequent starts; no background scheduler is claimed.
- No API key, actual recipient, OTP, password or link token is committed/logged. Email-status remains a configuration check, not an Inbox placement guarantee. The existing in-process background mail transport still has no durable retry queue.

## Validation

Local checks: 1,271 backend regression tests passed, followed by 21 OTP-specific tests after adding delivery/redaction coverage; 67 PostgreSQL tests passed before those two additional cases; 93 frontend unit tests, lint and build passed; 35 Chrome account checks passed against the actual disposable API/SMTP transport. Hosted CI reruns the final source including the additional cases.

Real Resend OTP: seven browser checks passed with a disposable local database and the authorized spare inbox. The real provider acknowledged the OTP message; the test read its code from the local delivery harness, not the owner inbox. The owner separately confirmed receipt in Inbox. The disposable local account was deleted and the server stopped. This is not a production OTP UAT claim.

Tests cover wrong/expired/replayed codes, consent/adult gates, resend invalidation/cooldown, setup expiry/replay/purpose, verified-account protection, legacy pending accounts, password limits, deletion, actual SMTP/browser flow and PostgreSQL concurrency/migration.

## Operational follow-up

Actual production verification emails were previously observed in Spam. OTP changes the signup interaction and does not guarantee Inbox placement. Continue inspecting delivered message authentication and Resend Insights. Deployment order and a real Resend OTP round trip must be recorded separately from isolated tests; do not claim production OTP passed before that run.
