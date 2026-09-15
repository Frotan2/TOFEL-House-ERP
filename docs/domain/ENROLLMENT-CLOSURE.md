# Enrollment — IMPLEMENTED (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Admission predecessor: [ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md) (CLOSED / QUALIFIED, `4da6f1b`, hosted run `34941341845`). Admission was not reopened.
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, `4571e6c`, hosted run `34932512626`). Placement was not reopened.

**Status: IMPLEMENTED — hosted qualification not yet executed.** Synthetic-data
implementation only, authorized for the bounded isolated build. Production
remains **REJECT**. Do not deploy. Do not reopen Placement or Admission. Do
not start the next domain. B07 billing values are not invented.

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

## 3. Limitations (do not implement in this close)

- Student Group / Course Schedule / attendance / assessment
- Tuition Sales Invoice (A08 / B07)
- Same-term repeats (A05 BLOCKED)
- Cancel/amend history (A11 BLOCKED)
- Returning-student re-enrollment
- Candidate portal

Production remains **REJECT**. Do not deploy. Do not start the next domain.
