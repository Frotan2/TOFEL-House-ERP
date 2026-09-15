# Admission — CLOSED / QUALIFIED (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Qualifying product commit: `4da6f1b02dc07e9dbbe939b417b95939540dc8eb`
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, `4571e6c`, hosted run `34932512626`). Placement was not reopened.

**Status: CLOSED / QUALIFIED — bounded thin Admission slice implemented and
qualified on the hosted synthetic runner (see Evidence). Synthetic-data
implementation only, authorized for the bounded isolated build. Production
remains REJECT. Do not deploy. Do not reopen Placement. Do not start
Enrollment. B06 eligibility/offer/scholarship values are not invented.**

This records the **thin Admission slice**: **Applicant → released Placement
Decision → TH Admission Decision → native Student conversion**. Native Program
Enrollment, invoices, payments, attendance and payroll remain later authorities.

## 1. What was implemented

- **Owned record:** `TH Admission Decision` only. No TH Student, TH Applicant,
  TH Enrollment, TH Course/Program/Class, custom ledger, custom attendance,
  custom payroll, or replacement portal.
- **Reuse:** native `Student Applicant`, `Student`, `Program`, `Academic Year`.
  Synthetic catalog (`SYN-PROGRAM-GENERAL`, `SYN-AY-2026`, Customer Group
  `Student`, `Education Settings.user_creation_skip=1`) is Administrator native
  configuration, not an admission RPC. Placement Case `subject` (User email)
  is bound to Applicant `student_email_id` for this isolated build only — not a
  CRM person master.
- **Commands** (`toefl_house.admission`): `record_applicant`, `create_admission`,
  `review_admission`, `decide_admission` (Approved | Conditional | Deferred |
  Rejected), `accept_offer`, `withdraw_admission`, `revoke_admission`,
  `expire_admission`, `convert_applicant`.
- **Lifecycle:** Draft → Review → Approved/Conditional/Deferred/Rejected, with
  withdraw from Draft/Review, revoke/expire from Approved/Conditional. Convert
  only **Approved + accepted + unexpired**. Conditional is not convert.
  Native `application_status` stays Applied until Student save sets Admitted.
  Admission never sets `paid`.
- **SoD:** reviewer ≠ drafted_by; decide ≠ drafted_by and ≠ reviewed_by;
  accept ≠ decided_by; convert ≠ drafted_by/reviewed_by; withdraw = drafted_by
  only. Roles: Admission Officer / Reviewer / Approver / Auditor.
- **Containment:** `override_whitelisted_methods` maps
  `education.education.api.enroll_student` to `deny_enroll_student`. Program
  Enrollment / Course Enrollment / premature Sales Invoice validate hooks deny
  in this synthetic domain. Direct Python import of `enroll_student` is **not**
  overridden; HTTP whitelist + hooks are the containment. Honest side effect:
  native Student save may create a Customer (via `Student.create_customer` with
  `ignore_permissions` on that nested insert only; the Approver HTTP session is
  never switched to Administrator). Website User is skipped when
  `user_creation_skip` is set or the email User already exists.
- **Idempotency / CAS / audit:** shared `TH Placement Operation` receipts and
  `TH Placement Audit Event`. Applicant row `FOR UPDATE`. One active
  (Draft/Review/Approved/Conditional) decision per applicant and per placement
  decision.

## 2. Native / custom boundary

| Authority | Owner |
|---|---|
| Person application | Education Student Applicant |
| Learner master | Education Student |
| Intake catalog | Education Student Admission (unused in this slice) |
| Program / Academic Year | Education |
| Internal English-level recommendation | Closed Placement (`TH Placement Decision`) |
| Institutional offer / conditions / acceptance | **TH Admission Decision** |
| Program Enrollment / Course Enrollment | Native — **not this slice** |
| Invoice / payment / GL / payroll / attendance | Native — **not this slice** |

`convert_applicant` is the native Applicant→Student conversion path (Education
sets Admitted). It is **not** enrollment and **not** billing. Admission does
not create a parallel TH Student; it may create the **native** Student after an
accepted Approved decision. Hosted `no-enrollment-academic-finance-payroll-writes`
recorded Program Enrollment, Course Enrollment, Assessment Result, Sales Invoice,
GL Entry and Salary Slip unchanged; `native_students: 2`, `native_applicants: 4`.
Reject does not convert. Conditional convert is denied. HTTP `enroll_student` is
403.

## 3. Files

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/admission/` | Commands + `TH Admission Decision` |
| `apps/toefl_house/toefl_house/policy.py` | Statuses, transitions, reason bounds, read boundary |
| `apps/toefl_house/toefl_house/security.py` / `permissions.py` / `hooks.py` / `install.py` / `controllers.py` | Roles, query, enroll_student containment, indexes, controller |
| `apps/toefl_house/toefl_house/fixtures/role.json` | Admission Officer/Reviewer/Approver/Auditor |
| `tests/admission/test_policy.py` | Local transition/read-boundary/scoping checks |
| `tools/placement/native_checks.py` | In-process + HTTP Admission; Placement increment regression retained |
| `.github/workflows/placement-content.yml` | Discover `tests/admission` |

## 4. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (qualifying commit `4da6f1b`; not native Frappe qualification):
  - `python3 -m unittest discover -s tests/placement -v`: **143/143 OK**
  - `python3 -m unittest discover -s tests/admission -v`: **6/6 OK**
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**
- Hosted qualification (`.github/workflows/placement-content.yml`):
  - Run `34941341845` (commit `4da6f1b02dc07e9dbbe939b417b95939540dc8eb` on
    `arena/01a0a13b-tofel-house-erp`): **PASSED**.
    - Pinned runner probe, pinned installs, both synthetic site installations
      and migrations: **all 86 runner steps exit 0** (`runtime_complete: true`,
      `production: REJECT`; runner report SHA-256
      `cd3a52dbcf136b5585052b285c2fa5f08f4e625eed65a3e646b2dfaedc471e7f`).
    - Native qualification: **397/397 checks pass** (`runtime_kind`
      Frappe/MariaDB/Redis/HTTP). Placement increments 1–7 and Placement
      closure remain green (`placement-closed-without-student-or-applicant`
      pass). Admission lifecycle, SoD, convert without Program Enrollment,
      HTTP CSRF/races/revocation (including
      `http-admission-concurrent-idempotency` `{http_statuses: [200, 200],
      one_student: true}`), two-site isolation, and
      `no-enrollment-academic-finance-payroll-writes` pass. Native report
      SHA-256
      `cd25ffa7ce600d1b2de6336801a461981df5d3ee2b9057a02fa88fead35613d0`.
    `native-acceptance` 18.891 s. Unique literal `check(` names in
    `tools/placement/native_checks.py` are **396**; hosted **397** includes
    the extra fixture-site check. Placement remains independently qualified
    by run `34932512626` (332/332 native checks, commit `4571e6c`).

Production remains **REJECT**.

## 5. Limitations and deferred (do not implement in this close)

- **B06** real eligibility, scholarships, offer windows, named institutional
  approvers — not invented. Synthetic reasons/conditions are fixture text.
- Returning-student conversion (`existing_student`) is recorded on the DocType
  and **denied** in this slice.
- Candidate/applicant portal, guardian proxy, Lead CRM, Student Admission
  intake windows as the person-case.
- **Enrollment** (native Program Enrollment as authority). Do not add
  `TH Enrollment Request` here.
- A13: HTTP `enroll_student` + PE/CE/invoice hooks are contained on synthetic
  sites. Direct in-process `education.education.api.enroll_student` import is
  still a native function; do not claim every Python import path is wrapped.
- Identity A02 remains CONDITIONAL. Synthetic subject is still a User email
  on Applicant. Operational CRM must use Lead/Applicant, not productize the
  test User.
- Native Student conversion may create a Customer; that is Education
  `Student.on_update`, not a TOEFL House ledger.
- Physical/Hybrid placement, official TOEFL/CEFR, production deployment.

**Do not start Enrollment.** Admission is CLOSED / QUALIFIED. Stop.
Production remains REJECT. Do not deploy.
