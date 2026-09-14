# Entity ownership and logical model

> Supporting design detail. The current authoritative gate is
> [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md),
> [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) and
> [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md).
> A01–A13 supersede earlier alternatives; old D01–D13 references are legacy questions
> mapped in the decision record. Nothing here authorizes implementation or production.


**All `TH` names and `th_*` fields are proposals, not installed schema.** Physical field types, indexes and migrations require review. Source-confirmed facts are catalogued in [pinned-source-review.json](pinned-source-review.json); other designs below are not claims of existing functionality.

## A. Native authorities: configure or extend, never duplicate

| Domain | Canonical native entities / owner | Proposed extension or boundary |
|---|---|---|
| Tenant/security | Frappe Site, User, Role, User Permission, File, native sharing | Exact business links; preserve generic security extension. Branch and Company are not site isolation |
| Inquiry | ERPNext Lead; Contact/Address where appropriate | Controlled application provenance, consent purpose and branch assignment; no `TH Applicant` master |
| Admissions | Education Student Admission, Student Applicant | Student Admission is intake publication/configuration, not one person's case. Applicant requires Program/year; link proposed `th_lead` and approved decision |
| Student/guardian | Education Student, Guardian, Student Guardian child rows | Native Applicant/User/Customer links; explicit Guardian.user relationships and access-safe activation |
| Catalog/calendar | Education Program, Program Course, Course, Academic Year/Term | Reviewed level/prerequisite metadata and policy references; never encode current learner scores in Course masters |
| Registration | Education Program Enrollment, Course Enrollment | Owned request coordinates approvals; native submit creates course records. No duplicate enrollment table |
| Classes | Education Student Group and its roster/instructor rows; Student Batch Name | Branch/location mapping, approved roster operations. Batch is a label, not a full class |
| Timetable | Education Course Schedule, Room | Academic resource conflicts and actual schedules; shared coordination with placement sittings |
| Learning attendance | Education Student Attendance, Student Leave Application | Assigned-teacher scope, correction approval and cutoffs. Not HR Attendance |
| Academic results | Education Assessment Plan/Criteria/Result, Grading Scale; native activity records | Enrolled learning evidence; separate placement domain. Progression reads these authorities |
| Fees/pricing | Education Fee Structure/Schedule/categories; ERPNext Item, pricing/quotation/order, Payment Terms | One approved source of each charge. Test native fee generation and select a single billing route per charge type |
| Receivables/cash | ERPNext Customer, Sales Invoice, Payment Entry, Journal Entry and native GL/payment ledgers | Invoice/credit/refund/reconciliation workflows; no stored custom outstanding balance |
| Procurement/expenses/assets | ERPNext Supplier, Purchase Invoice, native payment/asset/accounting records; HRMS Expense Claim | Native approvals, company/cost center and budget reporting; no parallel cashbook |
| Teachers | ERPNext Employee plus HRMS behavior; Education Instructor.employee | Native Instructor for teaching, Employee for employment. Qualifications/availability may use small reviewed fields/child rows |
| HR | HRMS recruitment, onboarding, Employee lifecycle, shifts/check-ins/Attendance, leave and expense workflows | Native employee data and approvals; contractor and jurisdiction rules require review |
| Payroll | HRMS Salary Component/Structure/Assignment, Salary Slip, Payroll Entry, Additional Salary; native accounting/payment docs | Native calculation/posting. Course work is only a proposed approved input, never a custom payslip/ledger |
| Communication/audit | Frappe Email Queue/Communication/Notification, Version and native integration records where suitable | Minimized messages, after-commit delivery and evidence references; no second messaging platform |

Relevant exact-source constraints: Student's controller can create/update Customer, provision User and set Applicant status to Admitted. Program Enrollment is submittable and calls fee creation and Course Enrollment creation on submit; cancel deletes Course Enrollments. Its duplicate check includes student/program/year/term. Student Applicant itself is not submittable in the inspected schema. Do not invent `docstatus=1` approval for it; an owned decision or reviewed native Workflow expresses approval.

## Relationship cardinalities and authority direction

- A learner-person Lead may link to multiple genuine Student Applicants over time. An Applicant has at most one original native Student conversion; person-level duplicate checks must span applications. A returning Student retains its original `student_applicant` provenance. If a new formal application is required, its owned Admission Decision may reference the verified **existing Student** rather than overwrite that provenance or create another Student.
- Student ↔ Guardian is many-to-many through native child membership. Student → Customer and Student → User use native links; their existence does not authorize arbitrary customer/user records. Shared identity/party scenarios require D02/D07 review, not assumed cardinality relaxation.
- Student → Program Enrollment is one-to-many across valid native keys. Each Program Enrollment owns many Course Enrollments; each Course Enrollment links one Course. Student Group membership is a separate native teaching roster, not another enrollment ledger.
- Student Group → Course Schedule is one-to-many; schedules reference native teaching/room resources. Student Attendance records identify Student and session/group/date according to native rules; owned commands enforce the approved business uniqueness.
- Placement Case has exactly one original subject and many Attempts. Attempt freezes one Form Revision, many Responses and assigned Ratings. A Decision references an explicit attempt/evidence set and may be superseded by another Decision; historical versions remain addressable.
- Admission Decision references one native Applicant and may reference a verified existing Student. Enrollment Request references exactly one new-admission or existing-student re-enrollment basis and returns native records. A recommendation can support multiple considered offers, but does not itself create enrollment or authorize repeated conversion.
- Employee → Instructor is an explicit native Link, not shared identity by name. Native work/payroll inputs reference Employee; course schedules reference Instructor. Regular employee instructors require that link. Contractor handling is conditional on D08, not a reason to fabricate Employee records.
- Native invoice/payment allocation is many-to-many under native accounting constraints. Owned operations hold result references only; they do not own allocation amounts or outstanding balances.

## B. Proposed owned placement aggregates

This is a conditional logical inventory, not a requirement to build every DocType. Under A06/B13, item/key/response/sitting structures apply only where the approved delivery process needs them; human-led component/rubric assessment must not be forced into an item-bank examination platform.

Common keys: native Frappe `name`, site scope, branch/company where relevant, owner/modified audit, and explicit business uniqueness below. Use references rather than copied PII. Historical snapshots are labeled evidence, not competing masters.

| Proposed DocType | Core fields / links | Lifecycle and key constraints |
|---|---|---|
| **TH Placement Case** | Subject kind plus exactly one Lead / Student Applicant / Student Link; purpose, branch, requested skills, consent/evidence references | Open → Ready → In Progress → Awaiting Decision → Closed / Withdrawn. One case may have many attempts; originals remain linked after conversion. No parallel contact/name master |
| **TH Placement Item Revision** | Stable item family ID, revision, skill, prompt, allowed response type, maximum/time expectations, private/media references, content rights | Draft → Published → Retired. Unique family/revision; published content immutable. Never expose author-only notes or keys in candidate DTOs |
| **TH Placement Key Revision** | Item revision, answer/rule definition for objective scoring, marking method, maximum | Separate restricted authority from prompts/responses. Published immutable; no arbitrary Python/JS evaluation or key fields in candidate-readable parent records |
| **TH Placement Rubric Revision** | Criteria child rows with bounds/units/descriptors, moderation policy, revision | Published immutable; criterion identity unique within revision; used by human ratings |
| **TH Placement Policy Revision** | Approved internal components and English-level definitions; normalization/weights/rounding only if approved; internal level thresholds; minimum-skill/tie/missing-data rules; Program/Course mapping, prerequisites, expiry/retake rules | Draft → Approved → Retired; approved snapshots immutable. No numerical policy selected; no baseline CEFR or official/mock TOEFL representation |
| **TH Placement Form Revision** | Approved component/rubric references; ordered item/key revisions only for approved item-based delivery; timing/accommodation rules, policy revision | Draft → Published → Retired. Publication validates completeness and licensing; live attempts keep frozen revisions even after retirement |
| **TH Placement Sitting** | Time window, branch, Room, proctor(s), capacity and form eligibility | Planned → Open → Running → Completed / Canceled. Coordinates resource conflicts with native schedules; candidates reside in attempt registrations, not a duplicate student group |
| **TH Placement Attempt** | Case, attempt number, form revision, optional Sitting, server timestamps/deadline, accommodations, integrity/review flags | Registered → Started → Submitted/Timed Out → Marking → Review → Finalized; terminal No Show/Voided as explicit alternatives. Unique case/attempt number; retries must return same attempt, not increment |
| **TH Placement Response** | Attempt + item occurrence, response revision, answer data or private File, received time, seal/hash | Draft autosave revisions until seal. Unique attempt/item occurrence/revision, one current revision; finalization seals a manifest. Item occurrences allow explicitly repeated items without ambiguous keys |
| **TH Placement Rating** | Attempt, item/skill criterion, assessor assignment, rubric/key revision, raw score, rationale/evidence, supersedes | Draft → Submitted → Moderated/Superseded. Unique assignment/criterion/revision. Submitted values not edited; blind independent ratings where policy requires |
| **TH Placement Decision** | Attempt, policy revision, sealed response/rating IDs, component evidence/calculations with approved units, current internal English level, recommended native Program/Courses and internal course-level mapping, approver, validity, release status | Draft → Reviewed → Approved → Released → Superseded/Revoked. Only authorized released decisions are learner-visible; one effective decision per purpose via server-enforced transition |
| **TH Placement Review Request** | Attempt/decision, requester, grounds, evidence, assigned reviewer and resolution/new decision link | Open → Investigating → Upheld/Corrected/Dismissed. Requests do not mutate scores; independent reviewer and restricted evidence |

Child rows belong to their parent; do not pretend they have independent security boundaries. Sensitive key material is a separate restricted DocType. Assessors receive only necessary form/rubric material and assigned candidate evidence, not a global item-bank dump.

### Optional scoring mechanics — not a selected policy

A06 does not require an overall total or any official exam component/scale. The following describes conditional mechanics only, subject to B04/B05. Skill/criterion identifiers are controlled versioned policy keys; publication rejects undeclared or duplicate references. For an approved ratio-scored dimension with a zero minimum, proposed normalization is `100 × earned / possible`, using Decimal, with `possible > 0`, validated bounds and policy-defined rounding. Nonzero minima, negative marking and rubric mappings need a separately approved normalization; do not silently clamp them into the ratio formula. Rubric-based mappings may differ and must be versioned. Overall weighted aggregation is allowed only when required dimensions are complete, units compatible and approved positive weights have a valid total. No implicit missing=0, automatic renormalization or averaging of unlike scales. Objective negative/partial marking, thresholds, rounding at boundaries, retake selection, moderation and validity are academic decisions, not invented defaults. A decision snapshot must be reproducible from referenced immutable inputs without running arbitrary policy code.

## C. Admissions, registration and progress coordination

| Proposed DocType | Links / responsibility | Not an authority for |
|---|---|---|
| **TH Admission Decision** | Native Student Applicant; optional verified existing Student; exact Program/year/term; valid released internal placement decision; no default exemption; eligibility checks, offer/quotation reference, conditions, approver, acceptance and expiry evidence | Identity, scores, ledger or Course Enrollment. Distinguish decision status from derived fulfillment of conditions |
| **TH Enrollment Request** | Admission Decision for a new applicant, or existing Student with approved re-enrollment basis; target Program/year/term/group, current-policy checks, idempotency identity, resulting native Student/Program Enrollment references | A second registration ledger. State is orchestration: Requested → Validated → Applying → Completed / Blocked / Failed Review / Canceled |
| **TH Academic Change Request** | Existing Student/enrollment, transfer/withdrawal/roster or attendance correction request, proposed effective date, approvals, impact and resulting native references | Another roster, attendance table or automatic refund. Split command types with separate validators/permissions rather than a generic unrestricted mutation tool |
| **TH Progression Decision** | Student + Program Enrollment; exact native result/attendance evidence set, completion/prerequisite policy revision, reviewer, next Program/Course recommendation | Native grades or automatic new enrollment. Corrections supersede; certificates, if approved, reference the decision and native records |
| **TH Progression Policy Revision** | Required native academic evidence, attendance denominator/exclusions, completion rules and next-course mappings | Placement scoring or payroll rules. Version and approve separately; no completion percentage selected yet |

An offer's price and payment schedule are authoritative in its linked native commercial document, with a historical reference/snapshot in the decision if needed. Do not invent a custom invoice or use admission approval as proof of settlement. Native Applicant “Admitted” can be set at Student creation; reports must derive completed registration from the submitted Program Enrollment and fulfilled approved registration requirements.

## D. Conditional extensions and technical records

- **TH Teaching Work Approval (conditional):** only if native Timesheet/HRMS approval cannot express the approved teaching-pay policy. Links Employee, Instructor, actual Course Schedule/substitution, native work evidence, approved units and native payroll-input result. Unique source work occurrence/pay basis; cannot mirror general attendance or calculate the statutory payroll. A09 blocks selection of salary-based versus time-based input until B08 and native-path evidence are supplied; no payroll-input route is selected here.
- **External examination evidence: excluded by A07.** `TH External Result Evidence` is not an active Phase 3 entity. Do not create official/mock TOEFL result fields or default CEFR mapping.
- **TH Domain Operation (technical proposal):** operation kind, tenant/actor scope, idempotency key, request hash, source references, status, native result references and restricted failure detail. Atomic uniqueness on tenant/operation/key; no reusable arbitrary-DocType CRUD endpoint.
- **TH Integration Receipt / dispatch intent (conditional technical proposals):** reuse native integration/Email Queue facilities if they meet uniqueness, retention, access and retry guarantees; add only the missing durable inbox/outbox capability. Provider/event identity is unique; sensitive payloads are minimized. These records are not ledgers, business masters or a new event platform.

## E. Proposed native Custom Fields: minimum linking surface

Candidate fields include `Student Applicant.th_lead`, owned Admission Decision references, branch links where absent, and a guarded `th_domain_operation` reference on native enrollment or commercial records **only where reconciliation requires it**. Applicant portal identity may require a verified `th_user` Link on the native applicant or prospect; this is not approved authentication design until D02 is resolved. Existing native links are preferred over new fields.

Field names, permission levels, uniqueness/index strategy, backfill and uninstall behavior require a schema review before creation. Never add editable client fields that masquerade as approval, score, settlement or privileged service authorization. Do not change native required fields or status definitions to make test fixtures fit.
