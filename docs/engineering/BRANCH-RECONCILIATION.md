# Branch and evidence reconciliation

Date: 2026-09-16 UTC · Rotation record: 2026-09-17 UTC (two rotations)

## Active engineering branch

The Arena session branch for current engineering work and hosted qualification is
`arena/01a0b5c4-tofel-house-erp`. The executable branch boundary is defined once
in `tools/session_branch.py`; workflow filters, hosted guards, and their tests
must remain aligned with it. `tests/foundation/test_branch_boundary.py` now
enforces that mechanically instead of leaving it to review.

### Rotation of 2026-09-18 (third): `arena/01a0b3a7-tofel-house-erp` → historical provenance

The Arena session branch changed again, so the boundary was rotated to
`arena/01a0b5c4-tofel-house-erp` using the recorded procedure: the canonical
value in `tools/session_branch.py`, all eleven workflow branch filters and their
`github.ref` guards, the ten current-status document headers, the D8
matrix/contract/owner records, the acceptance ledger and the qualification tests
were updated in the same change. `arena/01a0b3a7-tofel-house-erp` moved from
**active** to **historical provenance**; `arena/01a0aef4-tofel-house-erp` moved
to `earlier_active_branch_provenance`; `arena/01a0aafe-tofel-house-erp` moved to
`older_active_branch_provenance`; and `arena/01a0a9f7-tofel-house-erp` moved to
`oldest_active_branch_provenance`. Every run, check, commit and SHA-256 identity
in those blocks is unchanged — a rotation moves the boundary, never the evidence.

**A stale claim was corrected by this rotation.** The block that previously
occupied `active_branch_qualification` recorded
`hosted_execution_state: NOT_EXECUTED_ON_THIS_BRANCH` for
`arena/01a0b3a7-tofel-house-erp`. That was not true. The GitHub Actions API
shows `Foundation runtime validation` genuinely executed on that branch and
rejected:

| Run | Head SHA | Conclusion | Created |
| --- | --- | --- | --- |
| `35361065542` | `82275fd4fd917dbe175f7bd67a0b5380ab169017` | `failure` | 2026-09-18T15:13:11Z |
| `35356041559` | `53aae309dfd668c66ac30dc6072237f525a5dce0` | `failure` | 2026-09-18T14:24:34Z |

Run `35361065542` is now pinned as `PRIOR_ACTIVE_RUNTIME_RUN` with status
`fail_reject`. Its job steps show checkout, setup-node, owned qualification
policies, pinned Yarn CLI and Python/service setup all succeeding, then
`Install and validate the pinned foundation` failing with exit code 1 — the
SEC-DEPS-01 position. Check-run ids and report digests are deliberately **not**
recorded for it: the check-runs endpoint returns 404 for that run and the
artifact/log blobs are unreachable from the recording sandbox, so nothing is
asserted that was not independently read.

Because no hosted workflow has run on `arena/01a0b5c4-tofel-house-erp` yet,
`hosted_execution_state` is the explicit, fail-closed
`NOT_EXECUTED_ON_THIS_BRANCH` carrying **no** run, check, commit or report
identifier. `tools/foundation/d8_validate.py` enforces that absence. Production
remains **REJECT** and D8 remains **BLOCKED**; no gate changed state.

### Rotation of 2026-09-17 (second): `arena/01a0aef4-tofel-house-erp` → historical provenance

When the Arena session branch changed again, the boundary was rotated to
`arena/01a0b3a7-tofel-house-erp` using the recorded procedure: the canonical
value in `tools/session_branch.py`, the workflow branch filters, the hosted
guards, the current-status document headers, the D8 matrix/contract/owner
records and the qualification tests were updated in the same change. The
immediately previous branch `arena/01a0aef4-tofel-house-erp` moved from
**active** to **historical provenance**, keeping its own executed evidence
(Foundation runtime run `35218007937`, REJECT on SEC-DEPS-01, at commit
`e8da889`) under `prior_active_branch_provenance`. The previous prior branch
`arena/01a0aafe-tofel-house-erp` moved to `earlier_active_branch_provenance`,
and `arena/01a0a9f7-tofel-house-erp` is preserved verbatim under
`older_active_branch_provenance`.

Because no hosted workflow has run on `arena/01a0b3a7-tofel-house-erp` yet,
`hosted_execution_state` is again recorded as the explicit, fail-closed
`NOT_EXECUTED_ON_THIS_BRANCH` state carrying **no** run, check, commit or
report identifier. `tools/foundation/d8_validate.py` enforces that absence: any
execution identity attached to the active block fails the contract, so no
earlier branch's run can be re-labelled as this branch's execution. The
`ActiveBranchEvidenceTests` guards keep driving both directions of the state
machine (absence populated with identity, and execution claimed while the
boundary records an absence), so the state cannot drift in either direction.
Production remains **REJECT** and D8 remains **BLOCKED**.

The boundary was rotated from `arena/01a0aafe-tofel-house-erp` on 2026-09-17 when
the Arena session branch changed, using the procedure recorded in
`tools/session_branch.py`: the canonical value, the workflow branch filters, the
hosted guards, the current-status document headers, the D8 matrix/contract/owner
records and the qualification tests were updated in the same change.
`arena/01a0aafe-tofel-house-erp` therefore moved from **active** to **historical
provenance**. Runs and checks recorded against it keep their original branch,
commit, run and check identities and are not re-executed or re-labelled by the
rotation.

An earlier rotation moved `arena/01a0a9f7-tofel-house-erp` to historical
provenance on 2026-09-16. The acceptance ledger keeps both in an ordered chain:
`active_branch_qualification` (current branch), `prior_active_branch_provenance`
(`arena/01a0aafe-tofel-house-erp`) and `earlier_active_branch_provenance`
(`arena/01a0a9f7-tofel-house-erp`).

### The active branch now carries its own hosted evidence — and it is a REJECT

A rotation moves the boundary, not the evidence. Immediately after the 2026-09-17
rotation no hosted workflow had run on `arena/01a0aef4-tofel-house-erp`, so
`hosted_execution_state` was recorded as `NOT_EXECUTED_ON_THIS_BRANCH`, carrying
**no** run, check, commit or report identifier.

That absence has since been closed by execution rather than by re-labelling. All
five named workflows — `foundation-runtime.yml`, `foundation-runner.yml`,
`placement-content.yml`, `foundation-frontend-review.yml` and
`d8-operations-contract.yml` — were genuinely re-executed on this branch at commit
`e8da889b22589a5d64f7843ecaf5d11d9260424c`, together with the operational-
boundaries, durability, key-custody, independent-recovery and owned-suite gates.
The state is now:

| Field | Value |
| --- | --- |
| `hosted_execution_state` | `EXECUTED` |
| `session_branch.ACTIVE_RUNTIME_STATE` | `EXECUTED` |
| `session_branch.ACTIVE_RUNTIME_RUN` | `35218007937` |
| `foundation_runtime.status` | `fail_reject` (SEC-DEPS-01) |
| `production_state` | `REJECT` |

`tools/foundation/d8_validate.py` asserts **both** the `fail_reject` status and
that exact run id, so the pin cannot be silently swapped for a different or
passing run while SEC-DEPS-01 is open. **The Foundation runtime rejected exactly
as predicted**: 119 of 121 restricted checks pass, with
`hosted-full-stack-dependency-audit` and `hosted-frontend-advisory-audit` failing.
Re-execution moved the evidence onto this branch; it changed no outcome.

Before the rotation this was a latent trap: the validator required
`active_branch_qualification.foundation_runtime.run` to equal a pinned run id, so
a rotation could only be recorded by asserting a run that never happened on the
new branch. The explicit-absence state was the honest fix for that, and it was
exercised for real rather than being theoretical. **Its guards were not deleted**
— `ActiveBranchEvidenceTests` still drives them by forcing `NOT_EXECUTED`, so a
future rotation back to that state remains fail-closed. A mirror-image test now
also rejects a ledger that claims the absence while the boundary records an
execution.

The D8 report surfaces the state as `active_branch_hosted_execution`.

The branch is not a production approval. Production remains **REJECT** and D8
remains **BLOCKED**.

## Historical evidence boundary

The repository contains immutable evidence from earlier Arena sessions. Those
records retain the exact branch, commit, run, and check identities under which
they were produced. They must not be rewritten to the active branch or treated
as a new execution on this branch. In particular, hosted placement/domain and
foundation evidence may name `arena/01a0aafe-tofel-house-erp`, `arena/01a0a9f7-tofel-house-erp`,
`arena/01a0a942-tofel-house-erp`, `arena/01a0a496-tofel-house-erp`,
`arena/01a0a13b-tofel-house-erp`, `arena/01a0a055-tofel-house-erp`, or
`arena/01a09bf3-tofel-house-erp` because those are provenance fields, not current
execution authorization. `tools/session_branch.HISTORICAL_BRANCHES` is the
executable list of exactly those branches.

The evidence-recovery workflow runs on the active branch but accepts only its
explicitly identified historical source run and source branch. Recovery copies
sanitized evidence; it does not re-execute or re-label the original result. It
is manual-only, not a qualification gate: the migration push's recovery run
`35090760612` failed before publication while retrieving the historical artifact
(the artifact/results host returned `EOF`). No recovered evidence was claimed.
The failure is retained as an infrastructure/evidence-retrieval limitation.

## Required review rule

A branch reference in a document or report must be classified as one of:

- **active** — current executable work and automation; use the canonical active
  branch above;
- **historical provenance** — the exact source of an already-recorded run; keep
  unchanged for evidence integrity; or
- **example/text fixture** — not an execution claim.

An unclassified old branch in an active workflow, hosted guard, current status
header, or qualification test is documentation or release-control drift and
must be corrected before relying on that workflow.
