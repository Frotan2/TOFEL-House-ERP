"""Canonical branch boundary for hosted qualification tooling.

This value is deliberately explicit rather than derived from the checkout. A
qualification script must not become runnable on an arbitrary branch merely
because it was copied there. Rotate it only when the Arena session branch is
intentionally changed, and update the workflow branch filters and tests in the
same change.
"""

ACTIVE_BRANCH = "arena/01a0aafe-tofel-house-erp"
ACTIVE_REF = "refs/heads/" + ACTIVE_BRANCH

# Latest Foundation runtime run actually executed on the active branch. While
# SEC-DEPS-01 is open this run must be a REJECT, and tools/foundation/d8_validate.py
# pins the exact identifier so active-branch runtime evidence can neither be
# silently swapped nor flipped to a pass. Rotate it together with ACTIVE_BRANCH
# when the Arena session branch is intentionally changed.
ACTIVE_RUNTIME_RUN = "35122242581"
