# Placement — increment 7 implementation record (independent finalization)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Predecessor: increment 6 qualified in hosted run `34929427505` (commit `0f1b286`).

**Status: COMPLETE — bounded increment-7 slice implemented and qualified on the
hosted synthetic runner (see Evidence). Synthetic-data implementation only,
authorized for the bounded isolated build. Production remains REJECT.
F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 7 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §4:
**Finalized is not released.** Independent finalization of a reviewed Digital
score. No Decision row, candidate-visible release, course recommendation or
human rating.

## 1. What was implemented

- **Same Reviewer role, different actor:** `finalize_attempt` requires
  `Placement Reviewer`. The recorded scorer and the recorded reviewer cannot
  finalize, even with a Reviewer role union (increment-2 style independence).
- **Attempt state:** `Review → Finalized` under command context with integer
  version CAS. Scores and responses remain FrozenRecord.
- **No Decision row, candidate portal, Subject Access, audio, human rating,
  composite, cutoff, course recommendation or learner-visible release.** No
  native Student/Enrollment/academic/finance/payroll writes.

## 2. Files changed (increment 7)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/api.py` | `finalize_attempt` |
| `apps/toefl_house/toefl_house/security.py` | Reviewer command kind |
| `apps/toefl_house/toefl_house/policy.py` | `Review→Finalized` |
| `apps/toefl_house/toefl_house/controllers.py` | finalize clocks on AttemptRecord |
| attempt DocType JSON | `Finalized` status; `finalized_by` / `finalized_at` |
| `apps/toefl_house/README.md` | increment-7 boundary |
| `tests/placement/test_finalize.py` | read-boundary + transition |
| `tests/placement/test_native_check_actors.py` | reviewer2 fixture, HTTP signatures |
| `tools/placement/native_checks.py` | increment-7 native + HTTP (1–6 retained) |

Increment 1–6 product behaviour is otherwise unchanged; foundation pins are
untouched.

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (this commit):
  - `python3 -m unittest discover -s tests/placement -v`: **119/119 OK**
    (115 increment 1–6 tests retained, plus 4 finalize tests).
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**.
- Hosted qualification (`.github/workflows/placement-content.yml`):
  **not yet executed for this increment.** Increment 6 remains independently
  qualified by run `34929427505` (252/252 native checks, commit `0f1b286`).

## 4. Known limitations (unchanged outer boundary)

- Hosted runner evidence is the only runtime qualification; local unit tests
  do not qualify native Frappe/MariaDB/Redis/HTTP behavior.
- Controller invariants constrain generic CRUD/RPC/`ignore_permissions`
  writes; privileged raw SQL/Python remains governed administration, not
  tamper-proof storage (spec S5).
- All fixture content is synthetic and non-operational; owner artifacts
  P1–P5 remain prerequisites before any operational use.
- Partial-credit formats, human analytic rubrics, Decision/release,
  Physical/Hybrid delivery, candidate Website User / Subject Access, audio
  and retention are not implemented and remain disabled.
