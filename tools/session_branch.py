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
#
# 2026-09-25 observation — the pin is unchanged, and the reason matters.
#
# The first push-triggered Foundation runtime run on this branch completed:
# run 36114770663 at commit 8918403, conclusion success. Its evidence report
# records status "pass" with security_gate_passed False (runtime_install.py
# sets that flag unconditionally: broader roles, advisories and the remaining
# security gates are still required). The stack dependency audit in the same
# report lists real OSV findings and reports its own status "pass", meaning
# the audit completed; the advisory verdict is carried by security_gate_passed
# and the frontend advisory block, both of which remain failing.
#
# The 2026-09-24 note above says the state holds "until the first
# post-rotation push runs the runtime to completion". Read literally that
# condition is now met, but it is not the operative one. The enforced rule is
# d8_validate.validate_active_branch_qualification, which requires the pinned
# run's status to be exactly "fail_reject" as well as the run id to match.
# Advancing the pin on completion alone would make that check raise
# "acceptance ledger latest runtime evidence drifted".
#
# No tool writes "fail_reject"; it is a classification recorded by hand from
# an observed rejection, as it was for the two prior branches. Since the
# advisory-triage work the runtime reports "pass" while keeping
# security_gate_passed False, so the observed outcome no longer has the shape
# the rule expects. That is a decision for the release-contract owner, not a
# bookkeeping correction: see
# docs/engineering/evidence/active-runtime-state-2026-09-25.md.

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
