# Placement — increment 6 implementation record (independent review)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Predecessor: increment 5 qualified in hosted run `34927594996` (commit `4ef4488`).

**Status: IMPLEMENTED — bounded increment-6 slice coded and covered by local
unit tests; hosted synthetic qualification is the remaining runtime gate.
Synthetic-data implementation only. Production remains REJECT.
F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 6 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §4:
**Mark / rate / moderate** — independent review of a marked Digital score.
Human rubric rating, Finalized/Decision, candidate-visible release, course
recommendation and candidate portal remain out of scope.

## 1. What was implemented

- **Reviewer role:** `Placement Reviewer` (Desk staff). Command `review_attempt`
  requires that role. Authors, outsiders, Publishers, Invigilators and
  Assessors have no review path. The original scorer cannot review even with
  a Reviewer role union.
- **Attempt state:** `Marking → Review` under command context with integer
  version CAS. Scores and responses remain FrozenRecord. Review does not
  unseal, rescore or invent a composite.
- **No Decision row, Finalized state, candidate portal, Subject Access, audio,
  human rating, moderation sample or release.** No native Student/Enrollment/
  academic/finance/payroll writes.

## 2. Files changed (increment 6)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/api.py` | `review_attempt` |
| `apps/toefl_house/toefl_house/security.py` | Reviewer command kind |
| `apps/toefl_house/toefl_house/policy.py` | `Marking→Review`; Reviewer `can_read` |
| `apps/toefl_house/toefl_house/controllers.py` | review clocks on AttemptRecord |
| `apps/toefl_house/toefl_house/permissions.py` / `hooks.py` / `fixtures/role.json` | Reviewer role + query |
| attempt/case/response/score DocType JSON | `Review` status; Reviewer read |
| `apps/toefl_house/README.md` | increment-6 boundary |
| `tests/placement/test_review.py` | read-boundary + transition |
| `tests/placement/test_native_check_actors.py` | Reviewer grants, HTTP signatures |
| `tools/placement/native_checks.py` | increment-6 native + HTTP (1–5 retained) |

Increment 1–5 product behaviour is otherwise unchanged; foundation pins are
untouched.

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (this commit):
  - `python3 -m unittest discover -s tests/placement -v`: **115/115 OK**
    (110 increment 1–5 tests retained, plus 5 review tests).
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**.
- Hosted qualification (`.github/workflows/placement-content.yml`):
  **not yet executed for this increment.** Increment 5 remains independently
  qualified by run `34927594996` (221/221 native checks, commit `4ef4488`).

## 4. Known limitations (unchanged outer boundary)

- Hosted runner evidence is the only runtime qualification; local unit tests
  do not qualify native Frappe/MariaDB/Redis/HTTP behavior.
- Controller invariants constrain generic CRUD/RPC/`ignore_permissions`
  writes; privileged raw SQL/Python remains governed administration, not
  tamper-proof storage (spec S5).
- All fixture content is synthetic and non-operational; owner artifacts
  P1–P5 remain prerequisites before any operational use.
- Partial-credit formats, human analytic rubrics, independent release,
  Physical/Hybrid delivery, candidate Website User / Subject Access, audio
  and retention are not implemented and remain disabled.
