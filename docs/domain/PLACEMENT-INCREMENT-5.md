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
  (qualifying commit `4ef4488`):
  - `python3 -m unittest discover -s tests/placement -v`: **110/110 OK**
    (99 increment 1–4 tests retained, plus 11 scoring tests).
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**.
  - `node tests/foundation/test_realtime_guard.cjs`: **PASS**.
- Hosted qualification (`.github/workflows/placement-content.yml`):
  - Run `34927008961` (commit `7e51160a73b8df452b035a1683fbd3365cee0f54` on
    `arena/01a0a13b-tofel-house-erp`): **FAILED** at
    `score-role-and-list-parity` with
    `PermissionError: Insufficient Permission for TH Placement Case`.
    **150/151 executed native checks passed.** Root cause: Assessor had no
    DocType grant on Case/Attempt/Response (score listing would have failed
    next: `query_score` was mapped in hooks but not defined). Classification:
    **product** (Assessor read grants). Native report SHA-256
    `3d131ec6350b044aa1cc236a72f0c4eac7d31d8ac7b1ed66d2de7c7d94274582`.
    Remaining increment-5 native and HTTP checks did not run.
  - Run `34927594996` (commit `4ef44885a4e80eb0ff19ee74fd9e9dc101511d5c` on
    `arena/01a0a13b-tofel-house-erp`): **PASSED**.
    - Pinned runner probe, pinned installs (Frappe/ERPNext/Education/
      Payments/HRMS + foundation_security + toefl_house at pinned refs), both
      synthetic site installations and migrations: **all 86 runner steps exit
      0** (`runtime_complete: true`, `production: REJECT`; runner report
      SHA-256 `1c77df6c02c69d5ff169bd620a9d3e5f1215eb70317388502f89dddf682fcc07`).
    - Native qualification: **221/221 checks pass** — increment 1–4
      item/key, blueprint/policy, allocation and staff-supervised Digital
      delivery plus increment 5 objective scoring of sealed Digital attempts
      (Assessor-only `score_attempt`, Sealed→Marking CAS, missing≠zero,
      key-free projection, no composite/cutoff/recommendation, Publisher/
      Auditor/Assessor score reads, Author/Invigilator denied, rollback,
      transient retry, HTTP CSRF/races/revocation, two-site isolation, no
      student/enrollment/academic/finance/payroll writes; native report
      SHA-256
      `472c9c243d9819133cfc9859768a6d6410a1c9366a97cac1d44159f4a9478af1`).
    `native-acceptance` 11.544 s. Unique `check(` names in
    `tools/placement/native_checks.py` are **219**; hosted **221** includes
    the two fixture-site checks. Increments 1–2 remain independently
    qualified by run `34865327509` (85/85 native checks, commit `c0048dc`).
    Increment 3 remains independently qualified by run `34888352524`
    (135/135 native checks, commit `c7277a4`). Increment 4 remains
    independently qualified by run `34923752045` (188/188 native checks,
    commit `8b66bcb`).

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
