# Foundation failure on f59836b: cause check (2026-10-17)

Foundation run `39034054581` on `f59836b` failed in `Install and validate the pinned foundation`, as on `07117ea4`
(run `38904598642`). This record establishes why, from evidence that can be reproduced here.

## Result

- **Frontend audit (`hosted-frontend-advisory-audit`) reproduced:** 279 packages from the pinned
  `frappe/education` lockfile (`93bc7075`, v16.1.0), queried against the live npm bulk endpoint
  today. 66 advisory entries: 65 closed, **1 open, 0 untriaged**. The open entry is
  `@tiptap/extension-link` (GHSA-vhrc-hgrq-x75r), disposition **BLOCKED**. That accounts for the
  audit's exit 1 (`status` is `fail` when any finding is open or untriaged). Script:
  `repro_frontend.py` (reproduces the inventory approximately; the bench tree is not rebuilt).
- **Full-stack audit (`hosted-full-stack-dependency-audit`):** the CI annotations are capped
  (`... +12 packages not shown`). 145 distinct package/ID pairs are visible. All 145 are closed by the register
  (0 untriaged, 0 open); GHSA-vhrc is not among the visible annotations. The Python OSV query (`api.osv.dev`) is
  not on the sandbox allow-list, so the Python side was checked only for the visible IDs, not the full set.
- **Critical findings:** `loader-utils` GHSA-76p3-8jx3-jpfq (critical) is BUILD_ONLY; `shell-quote`
  GHSA-w7jw-789q-3m8p and GHSA-395f-4hp3-45gv are DEV_ONLY. These are the register's existing decisions, which
  I re-checked against the triage function. They are not newly triaged here.

## No new untriaged finding

The inventory of both trees is unchanged since `07117ea4`: `git diff 07117ea4 f59836b` touches no
`package.json`, lockfile, or Python manifest. The only dependency-file change is the test-only
`tests/security/requirements-ci.txt`. A changed audit outcome could therefore only come from a
new advisory published after `07117ea4`. The reproduction above shows none.

## Limits (not verified here)

- The full audit JSON artifact (`foundation-runtime-39034054581-1`) cannot be downloaded from the sandbox: its
  blob host is not on the allow-list. The full-stack annotation set is incomplete (12 packages not shown).
- OSV Python findings were not queried directly.
- The repro inventory is the upstream lockfile, not the rebuilt bench `node_modules`. In this reproduction
  the two agree on every triaged ID that appears in the annotations.

## What stays open

GHSA-vhrc remains **BLOCKED**. The Foundation red status on `f59836b` is the expected result of that blocker.
It is not a regression. Foundation will stay red until GHSA-vhrc has a hosted runtime containment check and a
reinstatement is recorded, or until the owner records an explicit decision on the blocker.

## Re-run

    python3 docs/engineering/evidence/sec-deps-01/foundation-replay-f59836b-2026-10-17/repro_frontend.py
    # exits 0 when there are no untriaged findings; prints the open GHSA-vhrc entry.
