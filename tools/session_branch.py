"""Canonical branch boundary for hosted qualification tooling.

This value is deliberately explicit rather than derived from the checkout. A
qualification script must not become runnable on an arbitrary branch merely
because it was copied there. Rotate it only when the Arena session branch is
intentionally changed, and update the workflow branch filters and tests in the
same change.
"""

ACTIVE_BRANCH = "arena/01a0cd90-tofel-house-erp"
ACTIVE_REF = "refs/heads/" + ACTIVE_BRANCH

# Hosted-execution identity for the ACTIVE branch.
#
# 2026-09-24 (sixth rotation): arena/01a0c987-tofel-house-erp produced
# multiple fail_reject runtime runs (latest 35984767187) and moves to
# historical provenance. The new active branch arena/01a0cd90 has not yet
# recorded a genuine push-triggered runtime run on its own workflow
# configuration, so the state is NOT_EXECUTED_ON_THIS_BRANCH until the
# first post-rotation push runs the runtime to completion. d8_validate
# pins NOT_EXECUTED state explicitly (no run id populated) and rejects
# any relabelling of older runs as executions on this branch.
ACTIVE_RUNTIME_STATE = "NOT_EXECUTED_ON_THIS_BRANCH"
ACTIVE_RUNTIME_RUN = None

# Historical provenance pins: the last two Arena session branches that produced
# a recorded Foundation runtime REJECT. These are evidence identity, never
# current execution authority. Newest first.
#
# The 2026-09-24 rotation advances both pins: arena/01a0c987-tofel-house-erp
# (run 35984767187, fail_reject) becomes prior, arena/01a0ba0d-tofel-house-erp
# (run 35451785714, fail_reject) becomes earlier.
PRIOR_ACTIVE_BRANCH = "arena/01a0c987-tofel-house-erp"
PRIOR_ACTIVE_RUNTIME_RUN = "35984767187"

EARLIER_ACTIVE_BRANCH = "arena/01a0ba0d-tofel-house-erp"
EARLIER_ACTIVE_RUNTIME_RUN = "35451785714"

# Every Arena session branch this repository has ever recorded hosted evidence
# against. A branch reference anywhere in an active surface (workflow filter,
# hosted guard, qualification test, current-status header) must be either
# ACTIVE_BRANCH or one of these explicitly classified as historical provenance.
# The executable enforcement of that rule is tests/foundation/test_branch_boundary.py;
# the classification policy is docs/engineering/BRANCH-RECONCILIATION.md.
HISTORICAL_BRANCHES = (
    PRIOR_ACTIVE_BRANCH,
    EARLIER_ACTIVE_BRANCH,
    "arena/01a0b5c4-tofel-house-erp",
    "arena/01a0b568-tofel-house-erp",
    "arena/01a0aafe-tofel-house-erp",
    "arena/01a0b084-tofel-house-erp",
    "arena/01a0b3a7-tofel-house-erp",
    "arena/01a0aef4-tofel-house-erp",
    "arena/01a0a9f7-tofel-house-erp",
    "arena/01a0a942-tofel-house-erp",
    "arena/01a0a496-tofel-house-erp",
    "arena/01a0a13b-tofel-house-erp",
    "arena/01a0a055-tofel-house-erp",
    "arena/01a09bf3-tofel-house-erp",
)
