# Enrollment — CLOSED / QUALIFIED (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Qualifying product commit: `756614e6826b7029d26e117b281a3b5aef1ad5bd`
· Admission predecessor: [ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md) (CLOSED / QUALIFIED, `4da6f1b`, hosted run `34941341845`). Admission was not reopened.
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, `4571e6c`, hosted run `34932512626`). Placement was not reopened.

**Status: CLOSED / QUALIFIED — bounded thin Enrollment slice implemented and
qualified on the hosted synthetic runner (see Evidence). Synthetic-data
implementation only, authorized for the bounded isolated build. Production
remains REJECT. Do not deploy. Do not reopen Placement or Admission. Do
not start the next domain. B07 billing values are not invented.**

This records the **thin Enrollment slice**: **converted native Student +
accepted Approved TH Admission Decision → native Program Enrollment** (and
native Course Enrollment as PE submit side effects). No TH Enrollment
Request. Invoices, payments, attendance, payroll and Student Group remain
later authorities.

## 1. What was implemented

- **Authority:** Education **Program Enrollment** (submitted). Native Course
  Enrollment is created only as PE `on_submit` from required Program Course
  rows. No TH Enrollment / TH Enrollment Request / TH Course / TH Class.
- **Command:** `toefl_house.enrollment.enroll_in_program` (Enrollment Officer).
  Idempotent via `TH Placement Operation` receipts. Duplicate student /
  program / year / term fails closed on native uniqueness.
- **Preconditions:** Approved + accepted + converted + unexpired placement;
  returning-student and Conditional paths denied. SoD: actor ≠ drafted_by,
  reviewed_by, decided_by.
- **Containment:** HTTP `enroll_student` remains denied (Admission A13). PE/CE
  validate hooks allow writes only inside the enrollment command context.
  Sales Invoice for converted students remains denied (B07 / A08 not this
  slice). Direct PE insert with `ignore_permissions` is still denied.
- **Honest native side effect:** PE submit may create Course Enrollment. Nested
  CE `save()` is wrapped with `ignore_permissions` on that worker only; the
  Enrollment Officer HTTP session is never switched to Administrator.

## 2. Native / custom boundary

| Authority | Owner |
|---|---|
| Institutional offer / conversion | Closed Admission (`TH Admission Decision`) |
| Learner master | Education Student |
| Program / Course / Academic Year | Education catalog |
| **Registration ledger** | **Education Program Enrollment** |
| Course registration | Education Course Enrollment (PE submit) |
| Invoice / payment / GL / payroll / attendance / roster | Native — **not this slice** |

## 3. Files

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/enrollment/__init__.py` | `enroll_in_program`, PE/CE guards, CE.save wrap |
| `apps/toefl_house/toefl_house/policy.py` | `enrollment_is_eligible`; Enrollment Auditor on operation/audit |
| `apps/toefl_house/toefl_house/security.py` / `permissions.py` / `hooks.py` | KIND_ROLES, command context, PE/CE/invoice hooks |
| `apps/toefl_house/toefl_house/fixtures/role.json` | Enrollment Officer / Enrollment Auditor |
| `tests/enrollment/test_policy.py` | Local eligibility / read-boundary / scoping checks |
| `tools/placement/native_checks.py` | In-process + HTTP Enrollment; Placement and Admission retained |
| `.github/workflows/placement-content.yml` | Discover `tests/enrollment` |

## 4. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (qualifying commit `756614e`; not native Frappe qualification):
  - `python3 -m unittest discover -s tests/placement -v`: **146/146 OK**
  - `python3 -m unittest discover -s tests/admission -v`: **6/6 OK**
  - `python3 -m unittest discover -s tests/enrollment -v`: **10/10 OK**
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**
- Hosted qualification (`.github/workflows/placement-content.yml`):
  - Run `34946981784` (commit `756614e6826b7029d26e117b281a3b5aef1ad5bd` on
    `arena/01a0a13b-tofel-house-erp`): **PASSED**.
    Check-run JSON: `Placement native checks` conclusion `success`
    (id `104311070370`); `Placement runner result` conclusion `success`
    (id `104311072959`); workflow job `content` conclusion `success`
    (id `104308613944`). Head SHA matches the product commit.
    - Pinned runner probe, pinned installs, both synthetic site installations
      and migrations: **all 86 runner steps exit 0** (`runtime_complete: true`,
      `production: REJECT`; runner report SHA-256
      `6ae1bef30f11706dc99f23d25454f4632cc54a9d5ce6b6bc5ac6096a62f0119b`).
      `native-acceptance` exit 0, 19.676 s.
    - Native qualification: **425/425 checks pass** (`runtime_kind`
      Frappe/MariaDB/Redis/HTTP; `status: pass`; `failure: null`). Placement
      increments 1–7, Placement closure, and Admission remain green.
      Enrollment in-process happy path, SoD, uniqueness, rollback, HTTP
      CSRF/races/revocation (`http-enrollment-concurrent-idempotency`),
      two-site isolation, and `no-academic-finance-payroll-writes` pass.
      Native report SHA-256
      `a11baba0dd539ad71324ffadfdcd3e86de2c630bda571478f2ad5c422e273ed7`.
    Unique literal `check(` names in `tools/placement/native_checks.py` are
    **423**; hosted **425** includes the extra fixture-site checks.
    Placement remains independently qualified by run `34932512626`
    (332/332, commit `4571e6c`). Admission remains independently qualified
    by run `34941341845` (397/397, commit `4da6f1b`).

Production remains **REJECT**.

## 5. Limitations and deferred (do not implement in this close)

- Student Group / Course Schedule / attendance / assessment
- Tuition Sales Invoice (A08 / B07) — values not invented
- Same-term repeats (A05 BLOCKED)
- Cancel/amend history (A11 BLOCKED)
- Returning-student re-enrollment
- Candidate portal
- Direct in-process `education.education.api.enroll_student` import remains a
  native function; HTTP whitelist + PE/CE hooks are the containment

**Do not start the next domain.** Enrollment is CLOSED / QUALIFIED. Stop.
Production remains REJECT. Do not deploy.
