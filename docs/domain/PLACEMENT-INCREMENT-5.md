# Placement — increment 5 implementation record (objective scoring)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Predecessor: increment 4 qualified in hosted run `34923752045` (commit `8b66bcb`).

**Status: IMPLEMENTED — bounded increment-5 slice coded and covered by local
unit tests; hosted synthetic qualification is the remaining runtime gate.
Synthetic-data implementation only. Production remains REJECT.
F01–F05 remain CLOSED/APPROVED; no policy value is invented or reopened.**

This records increment 5 of the vertical-increment sequence in
[PLACEMENT-TECHNICAL-SPEC.md](PLACEMENT-TECHNICAL-SPEC.md) §4/§6:
**Mark / rate / moderate** for the formats this bank already implements —
**Single Choice and True False exact match** on **sealed Digital** attempts.
Human rubric rating, partial-credit formats, release, course recommendation
and candidate portal remain out of scope.

## 1. What was implemented

- **Assessor role:** `Placement Assessor` (Desk staff). Command `score_attempt`
  requires that role. Author/outsider DocType grants are not added. Assessor
  reads case/attempt/response/score, not the seed-bearing manifest or keys
  (those load inside the command via `db.get_value` / `ignore_permissions`).
- **Attempt state:** `Sealed → Marking` under command context with integer
  version CAS. Responses remain FrozenRecord. Scoring does not unseal.
- **Closed registry:** `toefl_house.scoring` (`objective-v1`, no Frappe import).
  Exact match only. Unsupported types fail closed. **Missing is not zero** and
  is not dropped from the denominator. Incorrect is never a negative mark.
  No composite, percent, cutoff, CEFR or course recommendation.
- **Score row:** `TH Placement Score`, unique `(attempt, revision)`, FrozenRecord
  with a self-verifying result hash. Projection never includes answers, option
  ids, item identity, family or seed.
- **No candidate portal, Subject Access, audio, physical packets, human
  rating, moderation sample or release.** No native Student/Enrollment/
  academic/finance/payroll writes.

## 2. Files changed (increment 5)

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/scoring.py` | new pure exact-match scorer |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_score/*` | new append-once score DocType |
| `apps/toefl_house/toefl_house/placement/doctype/th_placement_attempt/th_placement_attempt.json` | `Marking` status |
| `apps/toefl_house/toefl_house/api.py` | `score_attempt` |
| `apps/toefl_house/toefl_house/security.py` | Assessor command kind; Score DocType |
| `apps/toefl_house/toefl_house/policy.py` | `Sealed→Marking`; Assessor/score `can_read` |
| `apps/toefl_house/toefl_house/controllers.py` | `ScoreRecord` |
| `apps/toefl_house/toefl_house/permissions.py` / `hooks.py` / `install.py` / `fixtures/role.json` | Assessor role + score hooks/unique index |
| `apps/toefl_house/README.md` | increment-5 boundary |
| `tests/placement/test_scoring.py` | scorer + read-boundary |
| `tests/placement/test_native_check_actors.py` | Assessor grants, HTTP signatures |
| `tools/placement/native_checks.py` | increment-5 native + HTTP (increments 1–4 retained) |

Increment 1–4 product behaviour is otherwise unchanged; foundation pins are
untouched.

## 3. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (this commit):
  - `python3 -m unittest discover -s tests/placement -v`: **110/110 OK**
    (99 increment 1–4 tests retained, plus 11 scoring tests).
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**.
  - `node tests/foundation/test_realtime_guard.cjs`: **PASS**.
- Hosted qualification (`.github/workflows/placement-content.yml`):
  **not yet executed for this increment.** Increment 4 remains independently
  qualified by run `34923752045` (188/188 native checks, commit `8b66bcb`).

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
