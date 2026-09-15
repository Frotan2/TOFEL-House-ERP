# TOEFL House domain architecture

> Supporting design detail. The current authoritative gate is
> [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md),
> [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) and
> [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md).
> Reuse-versus-custom classification: [ERP-CAPABILITY-MAP.md](ERP-CAPABILITY-MAP.md)
> (challenges a custom enrollment ledger; do not treat the Enrollment Request
> coordinator below as authorized). A01–A13 supersede earlier alternatives; old
> D01–D13 references are legacy questions mapped in the decision record. Nothing
> here authorizes implementation or production. Placement is CLOSED. Admission is
> not started. Production remains REJECT.


## 1. Architectural shape

Use the selected **site-based modular monolith**, not a new CRM, LMS, financial service, authentication system or SPA. A future owned app, tentatively `toefl_house`, extends native documents through supported hooks, namespaced Custom Fields, fixtures, workflows and reviewed service methods. Keep the generic `foundation_security` app separate from institution-specific policy; preserve its fail-closed checks and test extension composition on the exact pinned bundle.

No upstream core edits, global dependency overrides, replacement controllers competing with HRMS, new infrastructure platform or database migration away from MariaDB is proposed. The experimental frontend dependency lock remains unadopted.

### Context map

```text
Frappe site: identity, permissions, files, jobs, audit and configuration
 ├─ ERPNext CRM: Lead → formal application link
 ├─ TOEFL House placement: Case → Attempt → Ratings → Placement Decision
 ├─ Education admissions: Student Admission window → Student Applicant
 │    └─ TOEFL House Admission Decision → Enrollment Request coordinator
 ├─ Education: Student ↔ Guardian → Program Enrollment → Course Enrollment
 │    └─ Student Group → Course Schedule → Student Attendance / Assessment Result
 │         └─ TOEFL House Progression Decision (reads native evidence)
 ├─ ERPNext: Customer → Sales Invoice → Payment Entry → GL / reconciliation
 └─ ERPNext Employee + HRMS: Instructor link → work/leave → payroll → accounting
```

Arrows are references or business transitions, **not** automatic permission grants or a promise of one atomic transaction. The [ownership map](entity-ownership.md) specifies the writer for each authority.

## 2. Organizational and time model

- **Site:** institution/tenant boundary. A site database contains all installed apps. Cross-site identifiers, cookies, jobs and files confer no authority. Stronger trust separation may require separate deployments; Company/Branch is not a tenant boundary.
- **Company:** legal/accounting employer and ledger scope. Do not treat an academic branch as a legal company unless finance approves that structure.
- **Branch:** operational location; link native resources and relevant owned records using reviewed `th_branch` fields where no native field exists. Multi-branch permissions require explicit scoped queries and writes, not a cosmetic filter.
- **Department / Cost Center:** HR and accounting dimensions, mapped explicitly to branches; do not infer a universal one-to-one relationship.
- **Academic Year/Term:** actual institutional calendar periods. Program is a curriculum/path; Course is a subject/module; Student Group is the teaching roster. Student Batch Name is a cohort label, not a replacement class aggregate.
- **Offering:** a logical view over Program/year/term, course-based Student Groups and schedules. Start without a duplicate `TH Class` or `TH Course Offering` table. A future coordination document is justified only if native relationships cannot express an approved invariant; it must not own a second roster.
- **Time:** choose and record institutional/site timezone and academic calendars. Preserve server timestamps for deadlines; store reporting timezone and date boundaries. The user's location is not sufficient to decide fiscal, labor, privacy or curriculum jurisdiction.

Default proposal for rolling courses: define real intake terms with approved dates and group membership. Native Program Enrollment rejects a duplicate student/program/year/term, including another draft. Same-term repeat enrollments and transfers must be reconciled with that rule before implementation; do not manufacture terms per student or cancel historical enrollment merely to bypass uniqueness.

## 3. Identity and lifecycle boundaries

1. **Prospect:** native Lead; reusable contact details only where native Contact/Address semantics fit. Deduplicate by reviewed identity evidence; never merge solely on a shared phone/email.
2. **Application:** native Student Applicant for a real program/year, possibly more than one genuine application for a person. A proposed `th_lead` Link on the applicant preserves provenance; it does not make applications a second person directory.
3. **Placement subject:** exactly one original native Lead, Student Applicant or Student. A case captures testing purpose and provenance, not copied identity. Preserve the original subject on sealed attempts; resolve later Lead→Applicant→Student links without rewriting history.
4. **Student:** canonical academic identity. Re-enrollment uses the existing Student. Returning students must not be recreated as a new person to obtain another placement attempt.
5. **Customer:** canonical accounting party maintained by native Student behavior. A guardian paying is not automatically a replacement Customer or entitled to the student's full accounting record.
6. **User:** authentication identity, distinct from every business identity. Provision explicitly and verify linkage; no automatic account sharing or email-based Guardian authorization.
7. **Employee / Instructor:** Employee is employment identity; Instructor is the academic teaching role linked to Employee. An instructor's teaching assignment does not authorize payroll administration.

Native Student requires an email and can auto-create a website User unless `Education Settings.user_creation_skip` is enabled. Proposed onboarding uses the supported skip setting and a separate verified activation command after scopes are provisioned. This needs regression qualification. Students without a unique usable email, shared family emails, and external contractors are **review blockers**, not permission to fabricate emails, fake Employees or weaken required fields. A legitimate institution-managed mailbox policy is an option for review, not a chosen identity service.

## 4. Bounded contexts

| Context | Responsibility | Must not own |
|---|---|---|
| Inquiry/admission | Lead/application provenance, eligibility, decisions, consent and offer acceptance | Student master, ledger or authentication credentials |
| Placement | Versioned test content, attempts, responses, human scoring, internal placement recommendation | Enrolled academic results or official TOEFL/CEFR certification |
| Academic delivery | Native enrollment, roster, timetable, attendance, assessments; approved progression decisions | A second course/student/attendance master |
| Finance | Native pricing, invoices, collections, aid approvals, refunds and reconciliation | Placement outcomes or a custom balance table |
| People/workforce | Native employment, instructor assignments, leave, approved work and payroll inputs | Payroll copies in teacher profiles or student attendance as employee attendance |
| Coordination/reporting | Idempotent business commands, exception queues, scoped projections and evidence lineage | An alternative transactional system of record |

## 5. Non-negotiable invariants

- One institution-scoped canonical Student per verified person; duplicate detection is reviewed, and merges preserve links, financial records and audit. Email is not sufficient proof of person equality.
- Admission approval, placement release, roster membership and financial clearance are **independent predicates**. A rejected/deferred applicant is not enrolled; a payment is not admission approval; a recommended Course is not a Course Enrollment.
- Each attempt freezes form/items/rubric/policy versions. Sealed responses and submitted ratings are not overwritten. Corrections create superseding records with reasons and preserved evidence.
- Scores have valid ranges and units, complete required dimensions and deterministic normalization/rounding. Missing data is not zero. No approval from client-calculated scores or unofficial test equivalences.
- Native Program Enrollment creates its Course Enrollments and configured fee side effects. No second writer recreates them from events.
- Capacity, timetable conflicts, duplicate registration and financial idempotency must survive concurrent requests and retries, not only single-user UI validation.
- One economic obligation produces one approved native billing chain. Legacy Fees and invoice billing cannot both bill the same obligation. Native ledgers determine outstanding amounts and realized cash.
- Teacher attendance/work and student attendance are independent. Payroll pays only approved native payroll inputs; a canceled lesson does not itself determine legally payable time.
- Every privileged transition rechecks current server-side role, relationship, tenant, branch/company and document state. No trust in client-provided role, total, account, parent link or workflow status.
- Private evidence access follows its parent and current assignment, even if the requester uploaded/owns the File. Report, export, print, ZIP and job/realtime paths require the same scope.
- Notifications/payment providers are not part of an assumed database transaction. External effects use stable identities, after-commit dispatch, retry-safe handling and reconciliation.

## 6. Placement versus official examinations

Placement is the internal **entrance and English-level placement assessment** of a language-training center. Its output determines current English level and recommends the appropriate TOEFL House course/level **before the relevant enrollment**. It is not an official TOEFL examination, mock TOEFL performance score, academic final examination, external certificate or official CEFR certification.

Section/component results and assessor/teacher review apply according to the approved internal policy, not an assumed TOEFL exam structure. No overall total, four-section format, external scale or certification claim is selected. A06 leaves the actual internal levels, rubrics, mappings, moderation and retest parameters conditional on business decisions. Every retest preserves earlier attempts and decisions.

A07 excludes official/external examination features and any CEFR output from the active baseline. The earlier conditional `TH External Result Evidence` proposal is withdrawn from this contract. A future explicit requirement could introduce a separate external evidence domain or a calibrated **internal reference** mapping, never official certification or automatic substitution for the placement decision. No rights to licensed examination content are assumed.

## 7. Audit, records and reporting semantics

Use native Version/history where applicable plus a restricted append-oriented business decision trail: actor, approver, reason, timestamp, input/output references and policy revision. This is not cryptographic immutability against administrators. Stronger tamper evidence, retention, legal holds and operator access must be qualified before real data.

Native draft/submitted/canceled states remain native. Owned workflow states must not overload those values. A published revision is semantically frozen; retirement prevents new use without changing historical content. Define retention separately for recordings, identity evidence, item banks, assessments, education records, HR and statutory finance records, including backups. No retention duration or legal basis is assumed.

[Workflows](workflows.md), [permissions](permission-model.md), [integration boundaries](integration-boundaries.md) and [review gates](implementation-plan.md) complete this proposal.
