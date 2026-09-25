# SEC-DEPS-01 — evidence index (current)

**Register item:** dependency security — disposition `EXTERNAL/UPSTREAM BLOCKED`
(docs/engineering/final-closure-register.json). The owner standing decision to
keep **REJECT** until findings are readable was satisfied on 2026-09-23 by the
full triage below; the block persists because no official upstream release
clears the pinned tree and no pin override will ever be invented. This directory
is the canonical evidence root for the item.

## Start here

1. [`feed-delta-reverification-2026-09-25.md`](feed-delta-reverification-2026-09-25.md)
   — **current posture**: 2026-09-25 feed sweep (357 advisories across the
   pinned surface, zero new applicable findings; no newer Frappe v16 or Bench
   release). Dispositions unchanged.
2. [`per-finding-remediation-analysis-2026-09-23.json`](per-finding-remediation-analysis-2026-09-23.json)
   — the 2026-09-23 per-finding triage the delta is measured against
   (FIXABLE/MITIGATED/NOT_REACHABLE/BLOCKED classifications with tests).
3. [`triage-integrity-verification-2026-09-25.md`](triage-integrity-verification-2026-09-25.md)
   — proof the triage input was complete and untampered.

## Supporting evidence chains (date-labelled, immutable)

- [`readable-register-2026-09-19.json`](readable-register-2026-09-19.json) +
  [`pdf-reachability-trace-2026-09-19.md`](pdf-reachability-trace-2026-09-19.md)
  — the readability register and reachability analysis that made the findings
  reviewable, per the 2026-09-19 owner decision.
- [`runtime-exposure-triage-2026-09-24.md`](runtime-exposure-triage-2026-09-24.md)
  — per-finding runtime exposure classification.
- [`realtime-callback-origin-root-cause-2026-09-25.md`](realtime-callback-origin-root-cause-2026-09-25.md)
  — the socket.io Origin callback root cause established while verifying
  reachability claims.
- [`feed-delta-2026-09-25/`](feed-delta-2026-09-25/) — raw feed rows plus the
  re-runnable collector/comparator scripts used for the 2026-09-25 sweep.

Every mitigation or reachability claim has a regression or negative test under
`tests/security/` or `tests/foundation/test_sec_deps_*.py`. Nothing in this
directory waives, softens, or reinterprets the gate; it only explains and
re-verifies it.
