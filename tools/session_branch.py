"""Canonical branch boundary for hosted qualification tooling.

This value is deliberately explicit rather than derived from the checkout. A
qualification script must not become runnable on an arbitrary branch merely
because it was copied there. Rotate it only when the Arena session branch is
intentionally changed, and update the workflow branch filters and tests in the
same change.
"""

ACTIVE_BRANCH = "arena/01a0ba0d-tofel-house-erp"
ACTIVE_REF = "refs/heads/" + ACTIVE_BRANCH

# Hosted-execution identity for the ACTIVE branch.
#
# A rotation moves the previous session branch and its runs into historical
# provenance; it does not move the runs with it. At the 2026-09-19 rotation
# the active branch had NO hosted runtime evidence, recorded as the explicit
# NOT_EXECUTED_ON_THIS_BRANCH state. That absence was then closed by genuine
# push-triggered execution on this branch (all ten hosted workflows ran;
# Foundation runtime validation rejected on SEC-DEPS-01 exactly as predicted),
# so the state below is now EXECUTED with the real run pinned.
# tools/foundation/d8_validate.py fails closed on this state: it asserts both
# the fail_reject status and this exact run id, so the pin cannot be silently
# swapped for a different or passing run while SEC-DEPS-01 is open.
ACTIVE_RUNTIME_STATE = "EXECUTED"
ACTIVE_RUNTIME_RUN = "35451785714"

# Historical provenance pins: the last two Arena session branches that produced
# a recorded Foundation runtime REJECT. These are evidence identity, never
# current execution authority. Newest first.
#
# arena/01a0b084-tofel-house-erp never executed hosted workflows (its
# active_branch_qualification was NOT_EXECUTED_ON_THIS_BRANCH with empty run),
# so it falls into the general HISTORICAL_BRANCHES list without a pinned run,
# and the two evidence-bearing provenance pins stay pinned to their executed runs.
# The 2026-09-19 rotation advances both pins: arena/01a0b5c4-tofel-house-erp
# (run 35384078097, fail_reject) becomes prior, arena/01a0b3a7-tofel-house-erp
# (run 35361065542, fail_reject) becomes earlier, and arena/01a0aef4-tofel-house-erp
# falls into the general HISTORICAL_BRANCHES list with its run kept in the ledger.
PRIOR_ACTIVE_BRANCH = "arena/01a0b5c4-tofel-house-erp"
PRIOR_ACTIVE_RUNTIME_RUN = "35384078097"

EARLIER_ACTIVE_BRANCH = "arena/01a0b3a7-tofel-house-erp"
EARLIER_ACTIVE_RUNTIME_RUN = "35361065542"

# Every Arena session branch this repository has ever recorded hosted evidence
# against. A branch reference anywhere in an active surface (workflow filter,
# hosted guard, qualification test, current-status header) must be either
# ACTIVE_BRANCH or one of these explicitly classified as historical provenance.
# The executable enforcement of that rule is tests/foundation/test_branch_boundary.py;
# the classification policy is docs/engineering/BRANCH-RECONCILIATION.md.
HISTORICAL_BRANCHES = (
    "arena/01a0b568-tofel-house-erp",
    "arena/01a0aafe-tofel-house-erp",
    "arena/01a0b084-tofel-house-erp",
    PRIOR_ACTIVE_BRANCH,
    EARLIER_ACTIVE_BRANCH,
    "arena/01a0aef4-tofel-house-erp",
    "arena/01a0a9f7-tofel-house-erp",
    "arena/01a0a942-tofel-house-erp",
    "arena/01a0a496-tofel-house-erp",
    "arena/01a0a13b-tofel-house-erp",
    "arena/01a0a055-tofel-house-erp",
    "arena/01a09bf3-tofel-house-erp",
)
