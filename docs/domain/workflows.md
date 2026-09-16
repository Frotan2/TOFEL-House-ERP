# Workflows, state transitions and exception handling

> Supporting design detail. The current authoritative gate is
> [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md),
> [DOMAIN-CONTRACT.md](DOMAIN-CONTRACT.md) and
> [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md).
> A01–A13 supersede earlier alternatives; old D01–D13 references are legacy questions
> mapped in the decision record. Nothing here authorizes implementation or production.


These are **proposed domain workflows**, not implemented Frappe Workflows. Every transition requires current server-side permission and business-state checks. Native `docstatus` semantics remain unchanged. R = requester/author; A = independent approver where separation of duties applies.

## W01 — Inquiry and application

1. Reception creates or matches a native Lead, records purpose/consent evidence and branch assignment. Possible duplicates enter manual identity review; shared household contact details do not auto-merge people.
2. If the applicant already has a genuine intended Program and year, create a native Student Applicant and link provenance. Use Student Admission for the actual intake window and eligibility configuration.
3. If program selection depends on placement, create a **Lead-linked TH Placement Case**. Do not insert a fake Program, fake Student or unapproved Program Enrollment. After the released placement recommendation and applicant choice identify a real program/year, create the native applicant and link the existing evidence.
4. Admissions checks required documents, age/guardian requirements, accommodation and contact/identity policy. Missing or disputed identity blocks conversion/account activation, not just the UI's Next button.
5. Withdraw/reject/archive with reason and retention handling. Reapplication is a new legitimate application linked to the existing person, not a destructive reset of the previous decision.

**R:** Reception / Admissions. **A:** Admissions reviewer for duplicate merges and eligibility exceptions. Native `application_status` is not extended with invented Select values; proposal-level tasks/decisions provide the additional process detail.

## W02 — Test instrument governance

Academic authors draft item, key, rubric, form and policy revisions. A separate academic publisher verifies score bounds, skill coverage, thresholds, rights, accessibility, key separation and deterministic scoring cases before publication. Published content cannot change in-place; retire it for new attempts and publish a new revision. Existing attempts retain the old revision.

A technical administrator does not acquire academic score-setting authority through system access alone. Detect overlapping band intervals, gaps, invalid weights, duplicate criteria, ambiguous course mappings and unsupported expressions at publication. The policy may send unresolved cases to review rather than invent an outcome. No live candidate data is used in synthetic instrument tests.

## W03 — Placement registration and delivery

1. Match subject; confirm consent/accommodation and any placement-fee policy using native billing, separate from tuition. Associate Case, exact Form Revision and Sitting, or an approved on-demand window.
2. Atomically claim a seat if capacity-limited; check Room/proctor conflicts against both placement sittings and native Course Schedules. A read-then-insert capacity check is insufficient.
3. Start an attempt only within its authorized window. Server time establishes deadline and allowed items; accommodation changes before start are versioned, while changes during an attempt require an authorized, audited exception.
4. Autosave typed responses with a client request key and monotonic revision. Stale retries do not overwrite newer answers. Uploaded media must be private, size/type constrained and subject to a qualified scanning/quarantine policy before assessor access.
5. Submit atomically seals an explicit response manifest. Duplicate submits return the original receipt. Server-received timestamps define deadline acceptance; no unapproved offline/backdated upload rule. If offline delivery is required, it is a separate review decision and protocol.
6. Timeout, no-show, interrupted or integrity-flagged attempts take distinct states. Late files are quarantined for review, not silently attached to sealed responses. A flagged attempt is not automatically a zero or a disciplinary finding.

Candidates never receive the entire question bank or scoring keys. Item/media delivery checks the active attempt and allowed occurrence. Per-attempt sanitized delivery files/records, if needed, are projections—not new item masters—and require purpose/time-aware parent permissions. Download, copy, ZIP and shared-URL alias cases must be tested.

## W04 — Marking, moderation and placement release

1. Objective scoring uses only the frozen approved key and bounded marking method. Human work is assigned to qualified assessors; a worker must not score using an arbitrary formula string supplied by the client.
2. Assessor submits criterion-level ratings with exact rubric and evidence references. Where required, second ratings remain blind until both are sealed; conflicts of interest exclude self/family scoring.
3. The calculation service validates complete dimensions, bounds, units, weights and rounding, then produces a reproducible draft. Missing/invalid data routes to review. Recalculation against a new policy is a new decision, not an overwrite.
4. Moderator resolves required discrepancies; academic approver accepts or records an override with reason, affected dimensions, authority and original computed recommendation preserved. Overrides do not alter raw ratings.
5. Release a learner-facing decision containing approved internal band, Program/Course recommendations, limitations and validity. Internal integrity notes, unpublished keys and third-party/private assessor information are excluded.
6. Appeal creates TH Placement Review Request. Corrections supersede the decision and notify admissions if eligibility changed. Retakes create a new attempt under an approved retake/validity rule; historical attempts remain. Never silently select “highest score” or “latest score” without policy.

A released Placement Result determines current internal English level and recommends a suitable TOEFL House course/level with rationale. It neither admits nor enrolls, creates native academic results, predicts mock TOEFL performance, nor generates an official TOEFL/CEFR result.

## W05 — Admission decision and offer

Admissions reviews the native applicant, real program/year/term, valid released internal placement, eligibility/prerequisites and requested service. A10 fixes the initial entrance flow through placement; no automatic exemption for external results, payment or prior learning is included. A06 leaves returning-learner validity/retesting policy to explicit approval, without creating a new Student or overwriting prior attempts.

TH Admission Decision: **Draft → Review → Conditional / Approved / Deferred / Rejected**. Approved/conditional offers require documented acceptance within validity. Withdrawal, expiry, revocation and supersession are explicit. Conditions are individually identified and evaluated; do not treat Conditional as permission to enroll.

The decision references approved native quotation/order/pricing and payment terms as needed. Placement approvers do not approve scholarship/refund amounts. Admissions cannot mark payment settled; finance cannot change placement scores. A new admission after an override checks prerequisites and capacity again.

## W06 — Registration, capacity and native side effects

1. Enrollment Request records a stable idempotency identity, approved admission/re-enrollment basis and intended native target.
2. Recheck applicant/student identity, decision validity, valid released internal placement, company/branch, actual term, course prerequisites, seat capacity and approved financial-clearance policy. Lock a stable native roster/resource row or reviewed coordination claim while checking capacity. Every roster writer must use the same protection.
3. For a new student, create through native Student behavior once after authorization. Preserve Applicant/Customer/User links. Native Applicant may become “Admitted” here; the institution must **not** report completed registration yet.
4. Financial policy must avoid a cycle: default proposal is **enrollment-generated billing** through the configured native fee path. If a deposit is required before enrollment, finance may verify a native Customer advance or approved credit arrangement; do not require an invoice that only enrollment submission will create. Student creation is not itself course access.
5. Save/submit the one native Program Enrollment, letting its controller own Course Enrollment and the A08-selected native tuition Sales Invoice creation path. Do not separately issue the same tuition invoice, recreate Course Enrollments or run a competing batch/legacy Fees producer. A producer switch requires a new architecture/migration decision; no fee configuration is changed in this gate.
6. Confirm generated billing references, required financial approval/allocation and roster membership. Mark the request Completed only when all applicable predicates hold. Course access follows approved active enrollment **and** roster/entitlement policy, not the existence of a Student or draft request.
7. Partial completion enters reconciliation: link existing native results, identify missing effects and resume idempotently. Do not replay the entire native conversion or delete submitted finance records to “undo” an error.

Native uniqueness is student/program/year/term; same-term repeat enrollment is not assumed possible. The pinned enrollment API's permission-bypassing mapper must not bypass approval checks. Future document hooks must cover direct native APIs, generic CRUD, imports, jobs and mapped operations; a custom wrapper/UI alone is insufficient. This is a required test, not a claim that the proposed checks already exist.

## W07 — Class delivery and timetable

Academic operations configures Program/Course relationships, real calendars, Student Groups, instructor assignments and Room schedules. Native Course Schedule remains the class-session authority. Capacity includes approved active memberships and explicitly expiring reservations where used; reservations are not attendance or enrollment.

Schedule creation/change checks instructor, student-group and room conflicts, including placement sittings. Approved substitutions update native schedule/instructor assignment with history and notify affected recipients after commit. The substitute receives time-bounded access to the assigned class, not all students or the replaced teacher's HR data. Rescheduled/canceled sessions preserve audit and do not automatically generate attendance, refunds or payroll deductions.

## W08 — Attendance, leave, academic results and progression

- Assigned instructor/proxy records native Student Attendance for eligible students and the actual session. Present/Absent/Leave follow supported native semantics; lateness or excused absence requires reviewed supplementary metadata, not invented upstream status values. Unmarked is unknown, not automatically absent.
- Bulk attendance reports each student's result. A pinned native attendance path explicitly commits; do not promise one all-or-nothing roster transaction when using it. Retries must identify existing records and show partial completion.
- Corrections after a cutoff/submission use approved Academic Change Request and supported native amend/cancel behavior, with original values and reason retained. Approval authorizes only the requested correction, not arbitrary document edits.
- Student Leave Application is distinct from HR leave. Approved leave affects denominators only according to an approved academic policy and actual scheduled sessions.
- Enrolled assessments use native Assessment Plan/Criteria/Result and Grading Scale. Teacher enters results for assigned plans/students; academic review releases them. Placement Attempt/Decision is not substituted for Assessment Result.
- Progression Decision reads an explicit evidence set and approved policy, handling canceled sessions, transfers, missing results and appeals. Completion, repeat, remedial work or next-course recommendation is reviewed. New enrollment goes through W06; it is never silently created by a grade or report.

## W09 — Transfers, withdrawal and closure

A change request identifies current and proposed Program/group/term and effective date. Academic reviewer checks continuity/capacity; finance independently evaluates charges, credits and refunds. Preserve attendance and assessment history against their original sessions.

A11 is BLOCKED for history-affecting cancellation/transfer implementation. Evaluate supported prospective membership/effective-date operations, but do not assume they preserve all required history. Do **not** assume canceling Program Enrollment is a harmless transfer: the pinned controller deletes Course Enrollments. Cancellation requires a dependency/financial impact plan and qualification; if history cannot be preserved, block that transition until an approved native-compatible approach exists. Disable course entitlement prospectively without deleting earned results. Withdrawal does not itself create a refund, cancel employment or erase retained records.

## W10 — Finance, collection, aid and refund

1. Finance configures company, chart, accounts, cost centers, fiscal periods, Items/fee structures and currency/tax policies. Admission and placement charges have separate approved charge identities.
2. Generate each charge through its designated native path. An invoice is a receivable only in its approved native state; a Sales Order is not cash or a second receivable. Legacy Fees must not duplicate invoice billing.
3. Cashier records native Payment Entry with cash/bank authority and references. A guardian/sponsor is a payer/contact relationship, not automatically a replacement accounting party. Client screenshots or provider redirects do not establish settlement.
4. Installments use native payment terms. Discounts/scholarships/waivers require authorized approval and native price/credit treatment. Do not subtract money in a custom “balance” field. Overpayments remain native unallocated credits pending reconciliation.
5. Refund request verifies original invoice/payment, eligibility and prior refunds. Authorized finance uses native credit note/return and refund/disbursement flow as appropriate, preserving the original trail. Approval and disbursement are separate; cashiers cannot approve their own exceptions.
6. Provider webhooks and bank reconciliation are verified/idempotent; disputed/failed/reversed settlement enters a review queue. Reversals do not silently erase academic history or alter scores.
7. Period close reconciles charges, invoices, allocations, cash/bank, refunds and GL by company/currency. Use native exchange-rate and tax rules; no invented local fiscal policy.

## W11 — People, teaching work and payroll

HR creates/maintains the native Employee, employment terms, department/branch, leave/shift settings and salary assignment. Academic operations links the native Instructor and assigns schedules/qualifications. External instructors require an explicit employment/contractor decision; do not create fake Employees or promise contractors native employee self-service. If true supplier contractors are approved, evaluate a native Supplier/Contact and Purchase Invoice payment path with a reviewed Instructor reference rather than Salary Slips; employment classification and tax treatment remain D08 decisions.

Separate **planned teaching hours**, **actual delivered sessions**, **approved payable work** and **payroll posting**. Student attendance cannot be used as employee attendance. HR/academic supervisor approves substitutions, cancellations, preparation work and overtime under the chosen policy. A09 blocks choosing the salary-based/time-based native input until business rules and native behavior are established. Use conditional Teaching Work Approval only for a proven gap, not a payroll authority. Each approved work item can contribute once to the chosen native payroll input; revisions produce authorized adjustments, not duplicate Additional Salary.

Payroll: define native Salary Components/Structures/Assignments and periods → collect approved native inputs → generate/review Salary Slips → authorize Payroll Entry/native posting → reconcile accounting and bank payment → release payslips to the employee. Exact statutory deductions, working-day/hour conversion, leave effects, currency, advances, expense treatment, overtime and termination settlement require jurisdictional approval. No custom payroll calculation engine or student-fee-to-salary automatic offset.

Offboarding ends instructor access/assignments, rotates/revokes sessions and delegated jobs, reconciles payroll/advances and retains required records. It does not delete historical teaching or financial evidence.

## W12 — Reporting, communication and records requests

Reports use the ownership/metric contracts in [integration boundaries](integration-boundaries.md), with the same row/field permissions as source records. Bulk exports and asynchronous reports reauthorize at execution **and** download. Scoped managers are not site-wide administrators.

Queue minimal notifications after committed transitions. Resolve current recipients and authority when rendering/sending; never broadcast scores, payroll or payment details to a site-wide room. Failed delivery does not roll back a valid enrollment/payment; show delivery status independently.

Correction/access/erasure requests route to the authorized privacy/records owner. Respect legal holds and statutory records, minimize unnecessary copies and include derived exports/backups in the retention design. No automatic deletion of ledgers, finalized decisions or canonical enrollment history is authorized by this proposal.
