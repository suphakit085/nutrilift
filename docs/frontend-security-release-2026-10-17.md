# Frontend security release — 2026-10-17

Base: `origin/main` at `78b015c6e42040911da55f39492318fb9296d20f`.
Branch: `security/frontend-dependencies-20261017`.

This release updates frontend dependencies and adds a frontend-only CI check.
Next.js and eslint-config-next move from 16.3.3 to 16.3.8. The lockfile updates
sharp to 0.35.5, source-map-js to 1.2.2, and brace-expansion to 1.1.21 / 5.0.12.
The previous audit reported one critical and eight high affected packages;
five high entries were the same braces issue propagated through its lint parents.

## Next ESLint dependency replacement

Upstream braces 3.0.3 has no published security fix. A scoped npm override
replaces only Next ESLint's fast-glob dependency with the private local package
`frontend/tools/next-eslint-glob`, using tinyglobby 0.2.17. This supplies the
plugin's `globSync` API with `expandDirectories: false`, preserving literal
directory and brace-list behavior. The local package and its manifest must be
included with the root frontend manifest and lockfile.

The override's relative path is evaluated from
`node_modules/@next/eslint-plugin-next`; the lockfile resolves it to
`tools/next-eslint-glob` in the frontend root. Review this narrow compatibility
layer whenever upgrading Next ESLint. Three tests verify directory discovery
and enforcement of the internal-link rule. No lint rule is disabled for
application code.

## Release boundary

Application files under `frontend/src`, all backend code, database migrations
and email configuration match the base commit. No domain or mail provider
setup is required for this dependency update. The unfinished account rollout
remains in its separate development workspace.

CI runs installation, a high/critical dependency audit, lint, Next route type
generation, TypeScript, tests and build. Type generation creates the ignored
`next-env.d.ts` and route types before checking a fresh checkout. The CI build
uses a dummy API origin and is not an artifact for production deployment.

## Before production deployment

GitHub's latest recorded Vercel `Production` deployment, ID `6870721579`, reports
success for the base SHA above. Its latest recorded Railway production deployment,
ID `6870736250`, reports success for the same SHA. The live frontend homepage
returned HTTP 200 during review. These records support using this base but do not
replace checking the current provider alias, production branch and environment
settings before publication.

Review these changes as a frontend-only release, run its GitHub checks, and use
the existing production `NEXT_PUBLIC_API_BASE` when Vercel builds it. A production
release must not use CI's `https://api.example.invalid` value.

This branch does not deploy automatically through Actions and contains no Railway
code changes or migrations. The GitHub deployment history includes both providers
for the same commits: inspect **both Vercel and Railway Git integration settings**
before pushing or merging. Even a frontend-only commit may trigger a backend rebuild
if Railway's branch/watch settings include it. Choose a frontend-only deployment
path or adjust the provider trigger deliberately before publishing. No push, merge,
provider settings change or deployment was performed while preparing this release.

## Local validation

On 2026-10-17, a fresh install of this isolated release passed the full npm audit
with **0 vulnerabilities**, ESLint, route type generation, TypeScript, **78 tests**
and the Next.js 16.3.8 production build. Both the frontend application source and
the entire backend match the base commit. The workflow passed actionlint 1.7.12.
The wider development workspace has one additional retrieval warning regression;
its 79-test result is separate from this release's 78-test result.

Deployment records: [Vercel status](https://api.github.com/repos/suphakit085/nutrilift/deployments/6870721579/statuses),
[Railway status](https://api.github.com/repos/suphakit085/nutrilift/deployments/6870736250/statuses).

References: [Next advisory](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j),
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[tinyglobby migration guide](https://superchupu.dev/tinyglobby/migration).
