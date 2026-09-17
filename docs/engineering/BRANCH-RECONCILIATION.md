# Branch and evidence reconciliation

Date: 2026-09-16 UTC · Rotation record: 2026-09-17 UTC

## Active engineering branch

The Arena session branch for current engineering work and hosted qualification is
`arena/01a0aef4-tofel-house-erp`. The executable branch boundary is defined once
in `tools/session_branch.py`; workflow filters, hosted guards, and their tests
must remain aligned with it. `tests/foundation/test_branch_boundary.py` now
enforces that mechanically instead of leaving it to review.

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

### The active branch has no hosted evidence

A rotation moves the boundary, not the evidence. No hosted workflow has been
executed on `arena/01a0aef4-tofel-house-erp`, so
`active_branch_qualification.hosted_execution_state` is
`NOT_EXECUTED_ON_THIS_BRANCH` and that block deliberately carries **no** run,
check, commit or report identifier. `tools/foundation/d8_validate.py` fails
closed on this state: attaching any execution identity to it, or populating its
evidence sub-blocks, is a contract error, so an older branch's run cannot be
re-labelled as an execution here. The D8 report surfaces the state as
`active_branch_hosted_execution`.

Before the 2026-09-17 rotation this was a latent trap: the validator required
`active_branch_qualification.foundation_runtime.run` to equal a pinned run id, so
a rotation could only be recorded by asserting a run that never happened on the
new branch. Recording the absence explicitly is the honest alternative and it
changes no gate: production remains **REJECT** and D8 remains **BLOCKED**.

To close it, re-run `foundation-runtime.yml`, `foundation-runner.yml`,
`placement-content.yml`, `foundation-frontend-review.yml` and
`d8-operations-contract.yml` on the active branch, then set
`session_branch.ACTIVE_RUNTIME_STATE = "EXECUTED"`, pin the real run id in
`ACTIVE_RUNTIME_RUN`, and replace the active block with the observed results in
the same change.

The branch is not a production approval. Production remains **REJECT**.

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
