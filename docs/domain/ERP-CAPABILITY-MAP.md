# TOEFL House ERP capability map

Date: 2026-09-16 · Active branch: `arena/01a0c987-tofel-house-erp`
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, hosted run `34932512626`).

**Purpose:** prevent TOEFL House from becoming a second ERP on top of ERPNext.
This is a product-capability review, not production approval. Thin Admission
is recorded in [ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md), thin Enrollment
in [ENROLLMENT-CLOSURE.md](ENROLLMENT-CLOSURE.md) and thin Teaching
Operations (Scheduling & Attendance) in
[TEACHING-CLOSURE.md](TEACHING-CLOSURE.md). Production remains **REJECT**.
Do not deploy. Do not reopen closed domains. Do not start a gated domain
without its business gate resolved.

**Owner-decision alignment (2026-09-16):** The canonical record is
[`../engineering/canonical-owner-decision-record.json`](../engineering/canonical-owner-decision-record.json).
It selects Course Owner as system/strategic final authority; General Manager for
routine administration/operations; Academic Manager for academic operations and
progress; Finance Manager for finance/payroll; Reception for intake; role-based
access, auditable important activity, and offboarding access revocation with
historical preservation; multi-branch architecture with branch-level operational
isolation; current local/server operation through Tailscale with local
database/files; automated multi-version encrypted backup and recovery onto
another system with data preservation prioritized; configurable fees, discounts,
courses, levels, skills, terms and fixed/skill-based compensation; and controlled
owner role/permission administration with high-level health/attention visibility.
Native ERPNext/Education/HRMS authorities remain authoritative. Branch isolation
is an authorization/data-scope concern, not an assumption that Company or Branch
alone supplies tenancy. Student/guardian portal and online payments are not launch
scope. Future internet hosting and future off-site backup are supported directions
without a selected provider, hostname, DNS, public edge, or destination.

**Foundation strategy (unchanged):** Frappe → ERPNext → Education → HRMS/Payments
are the systems of record for identity, CRM, students, catalog, enrollment,
timetable, academic results, receivables/GL, employees and payroll. Owned code
exists only where the foundation cannot express a proven TOEFL House invariant.
See [foundation-architecture-decision.md](../engineering/foundation-architecture-decision.md)
and [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md).

**Classification (exactly one primary label per domain):**

| Label | Meaning |
|---|---|
| **NATIVE** | Use the pinned Frappe / ERPNext / Education / HRMS documents and controllers as the authority. Do not add a parallel master or ledger. |
| **CONFIGURATION** | Achievable with native settings, fixtures, naming series, print formats, Role Permissions, Workflow, Custom Fields that only *link*, or Query Reports. No new transactional DocType. |
| **TOEFL HOUSE EXTENSION** | Proven gap: custom domain logic is required. Keep it the smallest record that does not own native side effects. |
| **DEFERRED** | Part of the product vision, intentionally later. Do not implement now; do not invent a custom platform “to get ready.” |

A domain classified **NATIVE** may still need configuration. A domain classified
**EXTENSION** must still *reuse* native masters. The label is the *treatment*,
not a claim that native objects are absent.

---

## 1. Verdict

The project is **still following the reuse-the-enterprise-foundation strategy**
if and only if the next slices stay thin. Placement is the one large justified
extension (pre-enrollment assessment is not Education Assessment Result). The
failure mode from here is to clone Student, Course, Enrollment, Invoice, Attendance
or Payroll inside `toefl_house`.

| Domain | Primary classification | Custom code now? |
|---|---|---|
| Applicants / CRM | **NATIVE** | No |
| Admission | **TOEFL HOUSE EXTENSION** (thin decision only) | **CLOSED / QUALIFIED** ([ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md)) |
| Students | **NATIVE** | No |
| Courses / Programs | **NATIVE** | No (placement course-map is mapping, not catalog) |
| Batches / Scheduling | **NATIVE** | No custom ledger; thin command containment CLOSED ([TEACHING-CLOSURE.md](TEACHING-CLOSURE.md)) |
| Attendance | **NATIVE** | No custom ledger; thin command containment CLOSED ([TEACHING-CLOSURE.md](TEACHING-CLOSURE.md)) |
| Academic assessment | **NATIVE** | No |
| Teachers | **NATIVE** | No |
| Finance / billing / payments | **NATIVE** | No |
| HR | **NATIVE** | No |
| Payroll | **NATIVE** | No (teaching-pay path **BLOCKED**, A09) |
| Reporting | **CONFIGURATION** | No warehouse |
| Portals | **DEFERRED** | No replacement SPA |
| Placement | **TOEFL HOUSE EXTENSION** | **CLOSED / QUALIFIED** (synthetic). Do not reopen |
| Integrations | **CONFIGURATION** / external adapters **DEFERRED** | No second bus |

**Closed thin slices:** Admission (`TH Admission Decision` on native **Student
Applicant**), Enrollment (native **Program Enrollment** authority) and Teaching
Operations — Scheduling & Attendance (native **Student Group / Course Schedule /
Student Attendance**, no new DocType). The remaining lifecycle domains
(finance/B07, academic assessment/B04-B05, payroll/A09) stay gated on their
business decisions; see §7. Not CRM. Not a second Student master. Not a
portal. Not finance.

---

## 2. What is actually installed today

### 2.1 Foundation (pinned, unchanged)

- Frappe site: User, Role, User Permission, File, Email Queue, Notification, RQ, Version.
- ERPNext: Lead, Customer, Item, Sales Invoice, Payment Entry, GL, Employee, Supplier.
- Education: Student Applicant, Student Admission, Student, Guardian, Program, Course,
  Program Enrollment, Course Enrollment, Student Group, Instructor, Course Schedule,
  Room, Student Attendance, Student Leave Application, Assessment Plan/Result,
  Fee Structure/Schedule (source-reviewed in [pinned-source-review.json](pinned-source-review.json)).
- HRMS: employee lifecycle, leave, Attendance, Salary Component/Structure/Assignment,
  Salary Slip, Payroll Entry, Additional Salary.
- `foundation_security`: generic Student/Guardian/File/realtime guards. **Not** a
  TOEFL product and **not** a second ERP.

### 2.2 Owned `toefl_house` (Placement closed; thin Admission)

Installed and synthetically qualified Placement: item/key bank, blueprint/policy/course-map
revisions, case/attempt/manifest/exposure/response/score, `TH Placement Decision`,
operation receipts, placement roles.

Thin Admission (CLOSED): `TH Admission Decision`
plus native Applicant/Student conversion commands. Thin Enrollment (CLOSED):
`enroll_in_program` over native Program Enrollment with PE/CE guards. Thin
Teaching Operations (CLOSED): scheduling/attendance commands over native
Student Group / Course Schedule / Student Attendance with deny-by-default
guards. **No** TH Student, TH Applicant,
TH Enrollment, Course catalog, Invoice, Attendance, HR or portal code.

Synthetic limitation (do not “fix” by reopening Placement): case `subject` is a
test User, not native Lead/Applicant/Student. This Admission slice binds Applicant
`student_email_id` to that subject for isolation only. Operational CRM must attach
to **Lead / Student Applicant / Student**, not treat the synthetic User as a
person master.

### 2.3 Explicitly withdrawn or never to be built

- `TH Applicant` / `TH Student` / `TH Course` / `TH Class` / `TH Course Offering`
- Custom invoice, outstanding-balance table, or second Fees producer
- Custom payroll engine or student-attendance-as-pay
- `TH External Result Evidence`; official/mock TOEFL; baseline CEFR certification
- Replacement portal / new SPA / Kafka / second workflow engine

---

## 3. Domain catalog

### 3.1 Applicants / CRM — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | ERPNext **Lead** (prospect); Contact/Address; Education **Student Applicant** (application for a real Program/Academic Year). |
| Reuse unchanged | Lead as pre-program person (A01 route P). Student Applicant when a real program is intended (A01 route K). Native application_status values; do not invent Select options. |
| Configuration only | Lead source/territory, naming series, required documents as native attachments, Student Admission intake windows. |
| Custom code | None for a person/CRM master. Optional **link field** `Student Applicant.th_lead` (entity-ownership §E) only if provenance cannot be stored natively. Placement Case already holds the testing subject — do not clone it into a CRM. |
| Must NOT rebuild | `TH Applicant`, `TH Prospect`, custom pipeline, duplicate contact directory, email-as-identity merge. |
| Status | Not implemented. Placement does not write Lead/Applicant. |
| Dependencies | A02 (identity/email/merge) still **CONDITIONAL**. Staff-assisted intake is the locked first path. |

**Challenge:** building an “Applicant module” inside `toefl_house` would be a second CRM. Education already owns the application document. TOEFL House must not.

### 3.2 Admission — **TOEFL HOUSE EXTENSION** (thin)

| Question | Answer |
|---|---|
| Foundation already provides | **Student Applicant** (person’s application; **not submittable**; status Applied/Approved/Rejected/Admitted). **Student Admission** (intake *publication/configuration*, not one person’s case). `enroll_student` mapper (S8) can create Student + Program Enrollment with `ignore_permissions=True` — this is a containment problem, not an admission authority. |
| Reuse unchanged | Applicant identity, Program/year required fields, Student Admission windows, native conversion to Student. |
| Configuration only | Intake programs/years on Student Admission; Desk Workflow *may* assist routing but cannot be the durable institutional decision (A10 option W rejected because Applicant “Admitted” is a Student-creation side effect). |
| Custom code | **`TH Admission Decision` only:** references native Applicant (or verified existing Student), released valid **TH Placement Decision**, target Program/year/term, conditions, approver, offer acceptance/expiry. Logical states Draft → Review → Conditional / Approved / Deferred / Rejected. `convert_applicant` creates a **native** Student after accepted Approved; it does **not** create Program Enrollment, invoice, payment or placement edits. Returning-student conversion is recorded and denied in this slice. |
| Must NOT rebuild | Application form platform, admissions CRM, auto-enrollment from recommendation, payment-as-admission, “Admitted” status as proof of registration, applicant portal as the first slice. |
| Status | **CLOSED / QUALIFIED** (hosted run `34941341845`; [ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md)). A10 boundary held. B06 (eligibility, scholarships, named offer rules) is still a business input and is not invented. A13 containment of HTTP `enroll_student` plus PE/CE/invoice hooks is in the synthetic suite — not a claim that every Python import path is wrapped. |
| Dependencies | Closed Placement (released decision). Native Program + Academic Year (Applicant requires them). Identity A02 for conversion. **Enrollment is a later native step, not part of this slice.** |

**Challenge:** native Student Admission looks like “admissions” but is an intake catalog. Native Applicant.Admitted looks like approval but is set when a Student is created (S2). That is why a small owned decision is justified — and why anything larger is a rebuild.

**Challenge:** proposed **TH Enrollment Request** (entity-ownership §C, plan P3.4) is *not* Admission. It is the highest-risk future custom: it will become a second enrollment ledger if it stores roster/course truth. Prefer native Program Enrollment plus A13 hooks. Do not implement it in the Admission slice.

### 3.3 Students — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | Education **Student** (email required; can provision User and Customer; can set Applicant to Admitted). Guardian / Student Guardian. `foundation_security` exact Student/Customer scope. |
| Reuse unchanged | One Student per verified person. Returning learners reuse Student. Customer is the accounting party. User is authentication, not the learner master. |
| Configuration only | `Education Settings.user_creation_skip` to prevent premature website users; naming series; User Permission patterns already qualified for Student/Guardian. |
| Custom code | None for the master. Provenance links from Admission/Placement only. |
| Must NOT rebuild | `TH Student`, fake Student for portal login (A03), relaxing required email. |
| Status | Guards exist. No TOEFL House Student DocType (correct). |
| Dependencies | A02/A03/A04 still CONDITIONAL for activation, guardians, mixed roles. |

### 3.4 Courses / Programs — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | Education **Program**, **Course**, Program Course, Academic Year/Term. |
| Reuse unchanged | Catalog and curriculum. Program Enrollment uniqueness is student/program/year/term (S3). |
| Configuration only | Real programs, years, terms, course lists — **operational prerequisite for Applicant**, not custom code. |
| Custom code | None for catalog. **TH Placement Course Map Revision** maps sealed placement evidence to synthetic internal codes (`SYN-COURSE-GENERAL` fixtures). It is **placement policy**, not a course master. Operational mapping must eventually **Link native Course/Program**, not grow a second catalog. |
| Must NOT rebuild | `TH Course`, `TH Program`, encoding live learner scores on Course masters, using course-map as the timetable. |
| Status | Native catalog unused in synthetic placement. Course-map is fixture-only and non-operational. |
| Dependencies | B03 calendars; B04 operational mappings (still conditional). Do not reopen Placement to invent cutoffs. |

### 3.5 Batches / Scheduling — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | **Student Group** (roster), Student Batch Name (label, not a class), **Course Schedule**, **Room**. |
| Reuse unchanged | Teaching roster and session authority. |
| Configuration only | Groups, rooms, instructor assignment on native schedules. |
| Custom code | None. Do not add `TH Class` / `TH Course Offering` unless a proven invariant cannot be expressed natively (domain-architecture §2). Proposed **TH Placement Sitting** (if ever) coordinates capacity with native Room/Schedule; it must not own a second timetable. |
| Must NOT rebuild | Custom calendar, duplicate roster, batch-as-enrollment. |
| Status | **CLOSED / QUALIFIED (synthetic)** as thin commands over native Student Group / Course Schedule with deny-by-default containment; no new DocType. See [TEACHING-CLOSURE.md](TEACHING-CLOSURE.md). Physical placement sitting **DEFERRED**. |
| Dependencies | Native catalog and groups; A05 BLOCKED for same-term repeat representation. |

### 3.6 Attendance — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | **Student Attendance**, **Student Leave Application**. Bulk attendance in pinned Education **commits internally** (S8). |
| Reuse unchanged | Student attendance semantics. |
| Configuration only | Leave types, naming, instructor roles. |
| Custom code | None for recording attendance. Typed **TH Academic Change Request** only later, if native amend/cancel cannot express approved corrections — coordination, not a second attendance table. |
| Must NOT rebuild | `TH Attendance`; using this as **Employee Attendance** or payroll input. |
| Status | **CLOSED / QUALIFIED (synthetic)** as `toefl_house.teaching.record_attendance` over submitted native Student Attendance; the committing bulk tool path (S8) is not used and single-transaction rollback is proven. See [TEACHING-CLOSURE.md](TEACHING-CLOSURE.md). |
| Dependencies | Native groups/schedules; A13 if using the committing bulk path. |

### 3.7 Academic assessment — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | **Assessment Plan / Criteria / Result**, Grading Scale. These are **enrolled learning** records (S4). |
| Reuse unchanged | Course grading, progress evidence. |
| Configuration only | Grading scales, plans, weights — after B04 academic (not placement) policy. |
| Custom code | None for enrolled exams. Optional later **TH Progression Decision** *reads* native results; it must not write Assessment Result or enroll. |
| Must NOT rebuild | Reuse Placement Score/Decision as academic grades; union placement and academic into one “test score”; official TOEFL/CEFR. |
| Status | Not implemented. **Placement is a different domain and is CLOSED.** |
| Dependencies | Enrollment + B04 academic policy. A07 DECIDED: no official/mock TOEFL. |

### 3.8 Teachers — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | Education **Instructor** with explicit **Employee** link (S5). Not identity-by-name. |
| Reuse unchanged | Teaching role vs employment identity. |
| Configuration only | Instructor records, schedule assignment, qualifications as native/small child fields if needed. |
| Custom code | None for the teacher master. |
| Must NOT rebuild | `TH Teacher`; granting payroll admin via teaching assignment. |
| Status | Not implemented. |
| Dependencies | Employee (HR); A04 mixed-role still CONDITIONAL. |

### 3.9 Finance / billing / payments — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | Education fee configuration; ERPNext **Sales Invoice**, Payment Entry, credit/refund, GL. Student maintains Customer (S2). Program Enrollment can generate invoice/order (S3). Payments app is in the pinned bundle, **not** a chosen gateway. |
| Reuse unchanged | **A08 lock:** one enrollment-generated tuition Sales Invoice chain per obligation. |
| Configuration only | Company, accounts, tax, currency, fee structures, payment terms — **blocked on B07**, not on missing software. |
| Custom code | None for money. Domain operations may store **native document names** only. |
| Must NOT rebuild | Custom cashbook/balance, parallel Fees producer, marking paid from a browser redirect, placement fee hidden as tuition. |
| Status | **CLOSED / QUALIFIED** (thin slice: receipted `issue_tuition_fees` over native Fees + `issue_placement_fee` over native Sales Invoice with configuration-driven chargeability; see [FINANCE-CLOSURE.md](FINANCE-CLOSURE.md)). Refund terms, tax configuration and payment gateways remain owner policy / deferred. |
| Dependencies | B07 resolved at framework level ([FINANCE-POLICY-APPROVAL.md](FINANCE-POLICY-APPROVAL.md)); A13 containment on fee writers in the synthetic suite. |

### 3.10 HR — **NATIVE**

| Question | Answer |
|---|---|
| Foundation already provides | ERPNext Employee; HRMS recruitment/onboarding/leave/shifts/check-in/Attendance/Expense Claim. |
| Reuse unchanged | Employment lifecycle. |
| Configuration only | Departments, leave policies, shifts. |
| Custom code | None. |
| Must NOT rebuild | HR inside `toefl_house`; classroom attendance as HR attendance. |
| Status | App installed on synthetic sites; no TOEFL House HR code. |
| Dependencies | B08 classification; A04 accounts. |

### 3.11 Payroll — **NATIVE** (configurable teaching-compensation framework; posting **BLOCKED**)

| Question | Answer |
|---|---|
| Foundation already provides | HRMS Salary Component/Structure/Assignment, Salary Slip, Payroll Entry, Additional Salary; native accounting/payment (S6). |
| Reuse unchanged | **HRMS is the sole payroll calculation authority.** |
| Configuration only | Structures, assignments, fixed/skill-based/combined compensation models and effective dates after employment terms exist; rates and statutory policy remain owner configuration. |
| Custom code | Existing thin compensation framework may carry approved teaching facts and calculate configurable inputs, but native HRMS/payroll remains the sole posting authority. Conditional **TH Teaching Work Approval** is allowed only after a documented native gap — evidence + native input reference, never a second salary amount. |
| Must NOT rebuild | Custom payslip, dual Timesheet + Additional Salary for the same basis, fee-to-salary offset. |
| Status | Compensation framework selected and bounded; full payroll posting/statutory policy remains an open foundation/domain gate. |
| Dependencies | B08 classification and native path proof. |

### 3.12 Reporting — **CONFIGURATION**

| Question | Answer |
|---|---|
| Foundation already provides | Desk Query/Script Reports, print, export, Version. |
| Reuse unchanged | **A12:** scoped queries over source documents first. Placement metrics from released TH Placement Decision; academic from Assessment Result; finance from Invoice/GL; HR from slips. Never mixed “test score.” |
| Configuration only | Report definitions, role restrictions, print formats, stewards’ denominators once B04/B07/B09/B10 exist. |
| Custom code | Rebuildable projections **only** after measured need (A12 option P). No independently editable warehouse. |
| Must NOT rebuild | Analytics platform, custom outstanding-balance cube, official TOEFL metric. |
| Status | No product reports. Placement qualification reports are evidence, not operational BI. |
| Dependencies | Source domains; named stewards. |

### 3.13 Portals — **DEFERRED**

| Question | Answer |
|---|---|
| Foundation already provides | Education student/guardian website; Frappe Desk. Frontend advisory gate is **failed** (57 baseline matches; experimental candidate not adopted). |
| Reuse unchanged | Desk for staff. `disable_website_cache` and no public signup as security settings. |
| Configuration only | Website settings when a portal slice is explicitly authorized. |
| Custom code | None now. Applicant self-service is A02 option U (not first). Guardian pre-admission proxy is A03 option P (not first). **Placement candidate portal remains out of scope.** |
| Must NOT rebuild | Replacement SPA, parallel auth provider, new frontend toolchain to “unblock” Education. |
| Status | Production portal **REJECT**. Placement has no candidate Website User path. |
| Dependencies | Phase 2 frontend/ops gates; B01/B02/B11. |

### 3.14 Placement — **TOEFL HOUSE EXTENSION** (closed)

| Question | Answer |
|---|---|
| Foundation already provides | **Nothing that is a pre-enrollment English-level assessment.** Education Assessment Result is enrolled academic evidence and must not be reused (A06/S4). |
| Reuse unchanged | Native User/Role/File/RQ only as platform. Future operational subjects: Lead/Applicant/Student references — without rewriting qualified synthetic history. |
| Configuration only | Published blueprint/policy/course-map revisions (already a governed config lifecycle). Operational cutoffs/P1–P5 are **owner artifacts**, not code. |
| Custom code | Already implemented: bank, allocation, Digital session, objective scoring, review, finalize, internal decision/release. **Do not start another Placement increment.** |
| Must NOT rebuild | Official/mock TOEFL, CEFR certificate, academic Assessment Result writes, candidate portal, Physical/Hybrid (still fail-closed), invented percent/cutoff. |
| Status | **CLOSED / QUALIFIED** synthetic isolated build (run `34932512626`, 332/332 native, 86/86 runner, production REJECT). |
| Dependencies | None for further Placement work. Admission *consumes* released decisions. |

### 3.15 Integrations — **CONFIGURATION** (external adapters **DEFERRED**)

| Question | Answer |
|---|---|
| Foundation already provides | Email Queue, Notification, RQ, Communication; Payments app present but **no gateway selected**. |
| Reuse unchanged | After-commit native queues; idempotent consumers. Placement already has `TH Placement Operation` receipts — do not invent a second global bus for the same need. |
| Configuration only | Email accounts, print, notification templates (minimize PII). |
| Custom code | `TH Domain Operation` / integration receipt **only** after B13 shows native queues lack uniqueness/retention. No Kafka, no custom workflow engine. |
| Must NOT rebuild | Parallel messaging platform; storing provider secrets in evidence; treating webhooks as settlement. |
| Status | No external provider. |
| Dependencies | B07/B12 if a gateway is ever requested — separate decision. |

---

## 4. Architecture challenges (do not paper over)

1. **`toefl_house` can still become a second ERP.** It currently is not: it is a placement engine. Admission + Enrollment Request + Progression + Teaching Work + Domain Operation, if all built as masters, would be a clone. Default answer to a new DocType is **no**.
2. **TH Enrollment Request is more dangerous than TH Admission Decision.** Admission Decision fills a proven native gap (Applicant not submittable; Admitted is a side effect). Enrollment Request duplicates Program Enrollment unless it is strictly an orchestration pointer. **Do not bundle it with Admission.**
3. **Course-map codes are not courses.** `SYN-COURSE-GENERAL` is a synthetic fixture. Linking operational maps to native Course is configuration/extension of *placement policy*, not a catalog project. Do not reopen Placement to build a course directory.
4. **Student Admission ≠ person admission.** Using the wrong native DocType will either skip institutional approval or force a custom admissions ERP. The thin decision record exists so we can keep Student Applicant.
5. **`enroll_student` is not an Admission API.** S8: mapped conversion ignores mapping permissions. An Admission slice that “just calls enroll” would violate A10 and A13. Admission **stops at the decision**. Enrollment is a later native-controlled step.
6. **Synthetic Placement subject is a User.** That was valid for isolated qualification. Staff must not productize it as CRM. Admission uses Lead/Applicant.
7. **Stale status docs** (corrected in this review’s navigation updates): root README still described Placement as in-progress increment 7; `review-status.json` still said `toefl_house` was not created. Historical architecture-gate text in IMPLEMENTATION-READINESS remains a 2026-09-14 snapshot and is not rewritten as if it were this review.
8. **Phase 2 REJECT still caps every domain.** Capability labels do not authorize production, real student/payroll data, or portal go-live.

---

## 5. Redundant custom functionality — avoid (nothing to delete from Placement)

Placement’s DocTypes are **not** redundant with Education Assessment; do not remove them.

**Do not add** (would be redundant with the foundation):

| Temptation | Native authority already |
|---|---|
| TH Applicant / CRM pipeline | Lead + Student Applicant |
| TH Student / learner master | Student |
| TH Course / Program / Offering / Class | Program, Course, Student Group, Course Schedule |
| TH Enrollment ledger / Course Enrollment copy | Program Enrollment / Course Enrollment |
| TH Invoice / balance / cashbook | Sales Invoice, Payment Entry, GL |
| TH Attendance (student or staff) | Student Attendance / HRMS Attendance |
| TH Academic exam engine | Assessment Plan/Result |
| TH Payroll / payslip | HRMS payroll |
| TH Teacher master | Instructor + Employee |
| Replacement student portal | Education website + Desk (portal itself DEFERRED) |
| Official TOEFL/CEFR engine | **Excluded** (A07) |
| TH External Result Evidence | **Withdrawn** |
| Global TH Domain Operation bus | Placement Operation already covers placement; native RQ otherwise |

**Do not expand Placement** with Sitting/portal/Physical/audio/CEFR “while we are here.”

---

## 6. Dependency graph (implementation order if authorized)

```text
[NATIVE config] Program, Course, Academic Year/Term, Student Admission windows
        │
        ▼
Placement (CLOSED) ── released TH Placement Decision
        │
        ▼
Admission slice (thin): native Student Applicant + TH Admission Decision
        │
        ▼
[NATIVE] Student conversion ──► Program Enrollment ──► Course Enrollment
        │                              │
        │                              └── A08 Sales Invoice
        ▼
[NATIVE] Student Group / Course Schedule / Attendance / Assessment Result
        │
        ▼
[NATIVE] Employee / Instructor / HRMS payroll   (A09 still BLOCKED for custom input)
```

Blocked or conditional gates that **do not** stop a thin Admission *design* but **do** stop operational conversion, portals, repeats, payroll and production: A02, A03, A04, A05, A09, A11, A13, B01–B12, Phase 2 REJECT.

---

## 7. Recommended next domain

**Closed thin slices (in dependency order):** Admission
([ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md)) → Enrollment
([ENROLLMENT-CLOSURE.md](ENROLLMENT-CLOSURE.md)) → Teaching Operations —
Scheduling & Attendance ([TEACHING-CLOSURE.md](TEACHING-CLOSURE.md)):
native Student Group roster from submitted Program Enrollments, native Course
Schedule sessions with serialized native overlap validation, submitted native
Student Attendance → **Finance — tuition & placement billing**
([FINANCE-CLOSURE.md](FINANCE-CLOSURE.md)): native `Fees` tuition receivable
from submitted Program Enrollments and configuration-driven native
`Sales Invoice` placement billing under the owner-approved R05/B07 framework
([FINANCE-POLICY-APPROVAL.md](FINANCE-POLICY-APPROVAL.md)). No money master
was cloned; ERPNext accounts remain the only money authority.

**No further domain may start without its business gate resolved.** The
remaining lifecycle domains are gated, and none may be unblocked by
inventing values:

- **Academic assessment / progression:** requires approved B04/B05 grading,
  weights, pass/completion and correction rules; placement thresholds cannot
  substitute.
- **Workforce / payroll (P3.7):** A09 BLOCKED until pay basis and exactly one
  native input path per basis are proven.
- Reopening Placement, TH Enrollment Request, applicant/candidate portals and
  TH Student/Course/Invoice/Attendance DocTypes remain out of scope.

**Still not production.** Isolated synthetic work remains REJECT for deployment.

---

## 8. Strategy statement

**Yes — the overall project still follows reuse-the-enterprise-foundation**, provided Admission and later slices obey this map. Placement was the exception that proves the rule: Education cannot host pre-enrollment placement without misusing Assessment Result. Everything else on this list already has a native owner.

If a future slice needs a new master for Student, Course, Enrollment, money, attendance or pay, the strategy has failed and architecture must be reopened — not silently extended.
