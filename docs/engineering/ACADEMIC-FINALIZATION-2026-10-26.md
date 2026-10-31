# Academic and student operations — acceptance report, 2026-10-26

**Status: partial; not production acceptance.** This is an academic-focused
change on `arena/62ec6c27-tofel-house-erp`, based on source commit `49484403`.
The requested branch name could not be used in this session. The primary work
branch and `main` were not changed; the PR is intended to remain unmerged.

## Scope and results

- Placement/admission/enrollment remain the existing reviewed, native-backed
  workflows; no financial posting, collection, payroll or release integration
  was changed. Branch-scoped first enrollments can be projected through a
  matching admission before class placement. Mixed, foreign, branchless and
  truncated scope evidence fails closed.
- A scheduler can split one submitted native intake by selecting Student IDs;
  no selection preserves the previous all-eligible-intake behavior and legacy
  receipt payload. Academic Term must match the year and contain the class.
  The Academic desk distinguishes an unrostered learner from an intake with no
  open class, and suppresses precise guidance on incomplete bounded reads.
- In the **mocked** journey, GE and EAP each configured for two Solar Hijri
  months run from 23 September to 21 November 2026; a later entrant retains
  the same class dates. A separately configured three-week Speaking class ends
  on 14 October. These tests do not prove the real Owner settings are correct.
- Weekly timetable expansion shares the single-session calendar rule: Friday
  closes unless an audited dated Working Day reopens it; Saturday can be a
  configured teaching day. Explicit dates are not inferred from religion or
  country holidays.
- The Instructor desk and attendance command require one current identity and
  an assignment covering today and the specific session. They do not grant
  class-wide assessment results from a one-session assignment. Attendance is
  withheld for future **dates**, non-Active classes and non-Scheduled sessions;
  receipt replay rechecks instructor and roster scope.
- Student and consent-gated guardian schedule/attendance projections now show
  labeled Afghan Solar Hijri and Gregorian dates and the actual session/mark
  status. Guardian child changes clear old panes immediately and ignore stale
  child and consent responses. The view tests are simulated DOM/promise tests,
  not a physical browser qualification.
- The parent work branch advanced with an operations-health permission check.
  Its existing tests failed because their fake login denied that read. This PR
  adjusts only the test fixture for the explicitly readable case; the separate
  denied/fallback tests remain. The combined parent/academic synthetic snapshot
  passed the **14 affected tests** locally. The parent branch itself is untouched.

## Evidence on this source snapshot

| Kind | Exact evidence | Meaning |
| --- | --- | --- |
| Local Python | `.venv/bin/python -m unittest discover -s tests -t . -q`: **2,609 run, 13 skipped, 0 failures**, 100.051 s | Offline suite; many Frappe/native/site dependencies are stubbed. |
| Local lint/dependencies | `.venv/bin/ruff check .` (Ruff 0.16.8), `.venv/bin/python -m pip check`, `git diff --check`: passed | Static and environment checks, not operational acceptance. |
| Local Node | Node 22.22.3: product ingress **6/6**, realtime guard, command pages **14**, design system, role desks **8 / 76 guided actions**, and portal DOM/promise contract: passed | Local HTTP/DOM stubs; not a real Frappe web session. |
| Real Frappe / hosted | Native qualification was extended with synthetic future-date and expired-assignment checks; the existing two-teacher matrix is adapted for branch-safe roster fixtures. **Not run locally**; inspect exact-head GitHub checks and artifacts on this PR. | Prior PR #87 checks apply only to its earlier revisions and cannot certify this change. |
| Real browser / Windows | **Not run for this change.** No local browser, Docker or Frappe site was available; the existing Windows acceptance installation was not touched. | Portal interaction, real role logins, rebuilt customer package and Windows acceptance remain unproved. |

Python was 3.11.2. The local isolated environment used
`tests/security/requirements-ci.txt` with `--only-binary=:all: --require-hashes`;
13 skipped tests remain skips, not passes. Hosted status is deliberately not
asserted in this source file: use the PR's live check results for the pushed
commit and distinguish push-head checks from any PR merge-ref checks.

## Remaining risks / required acceptance

1. Pinned native Education overlap validation ignores custom
   `Cancelled`/`Postponed` session status. A slot the owned precheck considers
   free can still fail native insertion. No global monkeypatch or destructive
   cancellation workaround is included; prove a native-safe resolution.
2. Current roster rows have no membership-effective date. The command and desk
   can offer/accept a late entrant for an earlier session; do not backfill those
   marks. Design an auditable effective-date/migration policy before relying on
   retrospective attendance. The future guard is date-level, not start-time
   level, so a same-day session can still be marked before it begins.
3. Configure **Asia/Kabul** on the Frappe site. Configure and verify **2 Solar
   Hijri Month** for every GE/EAP level; arbitrary owner-defined family codes
   are not automatically recognized and an incorrectly configured non-Solar
   duration can bypass that specific two-month expectation. Other programs
   need their own reviewed duration settings. No fee-proration decision is
   assumed.
4. The bounded branch chain intentionally fails rather than grant access or
   present a precise enrollment count when evidence reaches its safe limit.
   Larger sites need a qualified paginated/indexed projection and performance
   test. The roster-based Academic desk measure is not the separately defined
   D7 analytics measure of enrollments with no open cohort.
5. Rerun native Education integration, permission/receipt revocation, two-teacher
   isolation, realistic placement-to-late-enrollment and assessment journeys on
   the exact merged source. Exercise guardian child switching and statuses in a
   real browser, then the rebuilt package on a disposable Windows installation.
   Complete Owner signoff and the other release gates; the approved release
   posture remains **NO-GO** until that evidence exists.
