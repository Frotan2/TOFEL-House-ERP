# Admission — thin extension (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a13b-tofel-house-erp`
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, `4571e6c`, hosted run `34932512626`).

**Status: IMPLEMENTED — hosted qualification not yet executed.** Synthetic-data
implementation only, authorized for the bounded isolated build. Production
remains **REJECT**. Do not deploy. Do not reopen Placement. Do not start
Enrollment. B06 eligibility/offer/scholarship values are not invented.

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
  native Student save may create a Customer; Website User is skipped when
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
sets Admitted). It is **not** enrollment and **not** billing. The capability map
line “does not create Student” is refined here: Admission does not create a
parallel TH Student; it may create the **native** Student after an accepted
Approved decision.

## 3. Files

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/admission/` | Commands + `TH Admission Decision` |
| `apps/toefl_house/toefl_house/policy.py` | Statuses, transitions, reason bounds, read boundary |
| `apps/toefl_house/toefl_house/security.py` / `permissions.py` / `hooks.py` / `install.py` / `controllers.py` | Roles, query, enroll_student containment, indexes, controller |
| `apps/toefl_house/toefl_house/fixtures/role.json` | Admission Officer/Reviewer/Approver/Auditor |
| `tests/admission/test_policy.py` | Local transition/read-boundary checks |
| `tools/placement/native_checks.py` | In-process + HTTP Admission; Placement increment regression retained |
| `.github/workflows/placement-content.yml` | Discover `tests/admission` |

## 4. Evidence

<!-- Hosted numbers are filled only from actual runner output. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (not native Frappe qualification):
  - `python3 -m unittest discover -s tests/placement -v`: **143/143 OK**
  - `python3 -m unittest discover -s tests/admission -v`: **5/5 OK**
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**
- Hosted qualification (`.github/workflows/placement-content.yml`):
  - **Not executed at document write.** Do not treat this slice as QUALIFIED
    until a hosted run on this branch reports pass with `production: REJECT`.
  - Required hosted proof includes: applicant/admission lifecycle;
    placement-to-admission linkage; approve/reject/withdraw/conditional/expire;
    duplicate protection; authorization/SoD; native Student creation without
    Program Enrollment/invoice/GL/payroll; idempotency/concurrency; audit;
    tenant isolation; HTTP/CSRF/CRUD/revocation; Placement increment regression.

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
- Physical/Hybrid placement, official TOEFL/CEFR, production deployment.

**Do not start Enrollment.** After hosted qualification, mark this document
QUALIFIED with the run id and stop. Production remains REJECT. Do not deploy.
