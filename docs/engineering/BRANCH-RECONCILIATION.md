# Branch and evidence reconciliation

Date: 2026-09-16 UTC

## Active engineering branch

The Arena session branch for current engineering work and hosted qualification is
`arena/01a0a9f7-tofel-house-erp`. The executable branch boundary is defined once
in `tools/session_branch.py`; workflow filters, hosted guards, and their tests
must remain aligned with it.

The branch is not a production approval. Production remains **REJECT**.

## Historical evidence boundary

The repository contains immutable evidence from earlier Arena sessions. Those
records retain the exact branch, commit, run, and check identities under which
they were produced. They must not be rewritten to the active branch or treated
as a new execution on this branch. In particular, hosted placement/domain and
foundation evidence may name `arena/01a0a942-tofel-house-erp`,
`arena/01a0a496-tofel-house-erp`, `arena/01a0a13b-tofel-house-erp`,
`arena/01a0a055-tofel-house-erp`, or `arena/01a09bf3-tofel-house-erp` because
those are provenance fields, not current execution authorization.

The evidence-recovery workflow runs on the active branch but accepts only its
explicitly identified historical source run and source branch. Recovery copies
sanitized evidence; it does not re-execute or re-label the original result.

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
