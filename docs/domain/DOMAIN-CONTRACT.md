# Authoritative TOEFL House domain contract

> **Placement scope revision:** [PLACEMENT-ASSESSMENT-MODEL.md](PLACEMENT-ASSESSMENT-MODEL.md)
> is the current authoritative placement design: governed question bank, blueprint-based
> randomized forms, six-skill automatic/manual assessment and digital/physical/hybrid delivery.
> It supersedes earlier staff-assisted-only/assessor-led-only scope and blanket exclusions
> of objective-bank delivery or digital speaking evidence. Recording permissions and
> operational policies remain conditional; R03 organizational owners and other domain
> boundaries are unchanged. Earlier approval/checklist text below is historical where
> it conflicts. No implementation authorization or production approval is granted.


Date: 2026-09-16 · Active branch: `arena/01a0b084-tofel-house-erp`. Contract status: **authoritative architecture specification; not production authorization**. Decision authority: [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md) plus the canonical [owner-decision record](../engineering/canonical-owner-decision-record.json). CONDITIONAL/BLOCKED decisions and unsupplied business policy are not implemented defaults. Selected foundation, pins, upstream source and production REJECT are unchanged.

## Owner-decision alignment and deployment phases

The canonical owner record selects Course Owner as system owner and final
strategic/ownership authority; General Manager for overall administrative and
routine operations; Academic Manager for academic operations and student progress;
Finance Manager for finance and payroll; and Reception for student intake and
reception operations. Staff access is role-based, important activity is auditable,
and offboarding revokes active access while preserving historical records.

Multi-branch architecture and branch-level operational isolation are required.
Use native ERPNext Company/Branch and User Permission authorities where applicable,
with server-side branch scope checks for custom commands; Company/Branch is not
assumed to be tenant isolation by itself. Course Owner and authorized senior
management may view permitted organization-level aggregates without bypassing
branch-level operational isolation.

The current deployment phase is local/server-based, with authorized staff
accessing the local database and files through Tailscale. Future internet hosting
is a separate phase; no provider, hostname, DNS, public edge or public TLS value
is selected here. Automated multi-version encrypted backup and recovery onto
another system are requirements; preserving data has priority over minimizing
recovery time, and future off-site backup support is a direction rather than a
selected destination. Engineering owns MFA, RBAC mechanics, network/session
controls, encryption/secrets, backup rotation, monitoring, recovery, rollback,
configuration versioning, CI/CD and deployment hardening.

Fees, discounts, courses, levels, skills, semesters/terms, teacher compensation
models, and other business values remain configurable policy. Native
Frappe/ERPNext/Education/HRMS remain authorities for identity, students,
academics, accounting, employees and payroll. The student/guardian portal is
future scope and online payment gateway integration is not required at launch.
Course Owner requires a controlled role/permission administration surface and a
high-level system health/attention view; these do not create parallel masters or
ledgers. Production remains **REJECT** until technical evidence closes the
applicable release gates.

## 1. Mandatory meaning and lifecycle

TOEFL House is a language education/training center. Its **Placement Test** is an internal entrance assessment that determines a learner's **current English level** and recommends an appropriate **TOEFL House course/level before enrollment**.

The business lifecycle is:

```text
Prospect → Applicant → Placement → Admission → Student → Enrollment
         → Course Participation → Academic Assessment → Completion

Placement itself:
entrance assessment → section/component evidence where applicable
→ assessor/teacher review where applicable → English-level determination
→ course/level recommendation with rationale → released Placement Result
```

Each stage has its own evidence and transition. The application stage is a **business intention to seek admission**, not necessarily immediate creation of the native Student Applicant document. Physical routing under A01 reconciles the lifecycle with native required fields:

- **Program unknown:** native Lead represents the prospect/applicant person and intention; the placement case references that Lead. Placement and recommendation occur first; a native Student Applicant is created once a real Program/year is chosen, before admission approval.
- **Real program already intended:** create native Student Applicant, then perform placement before academic enrollment. Intent is not proof that the course is suitable.
- **Returning Student:** preserve the existing Student and original enrollment history. A new placement attempt can inform a future course decision **before that new enrollment**. This does not erase the learner's past academic enrollment or require another Student.

The business “Applicant” stage is not a new `TH Applicant` person master, a fake Student or a placeholder Program. No transition depends on a fictitious enrollment. Native Student creation can affect User/Customer and Applicant status, but it is not completed enrollment or course participation.

### Three non-interchangeable result types

| Concept | Authoritative meaning | Owner / permitted use |
|---|---|---|
| **Placement Result** | Internal TOEFL House entrance/English-level determination and course/level recommendation, with evidence/review/rationale | Owned TH Placement Decision; supports separate admission review; not academic achievement or certification |
| **Academic Assessment** | Assessment of learning during a legitimate enrolled course | Native Education Assessment Plan/Result; supports native academic progress/completion |
| **Official TOEFL Score** | Externally issued examination result | **Outside this contract.** Placement must never generate or represent it, or produce a mock TOEFL performance score |

No official CEFR certification is generated. No CEFR mapping is enabled in the baseline contract. A future explicitly approved internal CEFR reference must have separate mapping/version/provenance and the label “internal reference — not certification”; it may never replace or relabel the internal Placement Result. No official examination integration or `TH External Result Evidence` entity is part of this implementation scope.

## 2. Domain ownership and relationships

`TH` names below identify proposed logical entities only; no schema exists. Use the minimum approved set for the selected assessment process, not an examination platform copied from TOEFL. B13 controls physical entity necessity.

| Boundary | Canonical entities / ownership | Cardinality and restrictions |
|---|---|---|
| Authentication/organization scope | Frappe Site/User/Role/User Permission/File and native operational facilities; native Company/Branch where applicable | Site is the deployment boundary; Company/Branch is operational scope, not tenant isolation by itself. Branch-level access requires native permission plus custom-command enforcement. User is authentication, not a learner master |
| Governance and operational authority | Native User/Role/User Permission plus controlled TOEFL House administration Page; Course Owner, General Manager, Academic Manager, Finance Manager and Reception are role scopes, not person records | Role assignment is auditable and fail-closed. Offboarding revokes access without deleting history. Sensitive financial/strategic changes retain management/Course Owner controls. |
| Prospect/application | ERPNext Lead; Education Student Applicant and Student Admission intake configuration | One verified person may have genuine applications over time; dedup is not email equality. No parallel applicant/person master |
| Placement governance | Owned TH Placement Policy Revision; rubric/form/component definitions; item/key revisions only if objective/item-based delivery is approved | Published policy/content meaning frozen. Internal level vocabulary and native course mappings have explicit versions; no external-exam scale assumed |
| Placement execution | Owned TH Placement Case, Attempt, Responses/evidence, assigned Ratings and Review Requests as required | Case has exactly one original Lead/Applicant/Student subject. Multiple attempts allowed; each references exact inputs. Private evidence never implies broad bank/learner access |
| **Placement Result** | Owned **TH Placement Decision** | One effective released decision per defined case/purpose under approved policy; prior decisions/attempts retained. Result is not a second native Assessment Result |
| Admission | Native Applicant plus owned TH Admission Decision | Application identity remains native. Decision references placement, eligible target and conditions; original placement recommendation is not edited by admissions |
| Student/customer | Education Student/Guardian/Student Guardian; ERPNext Customer | Native controlled links. Returning learner reuses Student; guardian/payer contact is not automatically Customer replacement or permission grant |
| Enrollment/participation | Native Program/Course, Academic Year/Term, Program Enrollment/Course Enrollment, Student Group/roster, Course Schedule/Room | Program Enrollment owns native Course Enrollment side effects. Coordinator TH Enrollment Request holds references/status, not a second registration ledger |
| Academic learning | Native Student Attendance/Leave and Assessment Plan/Result/Grading Scale; owned Progression Decision/policy if institution-specific approval is needed | Placement does not write academic records. Completion depends on native course evidence, never placement success alone |
| Finance | Native fee configuration → ERPNext Sales Invoice/Payment Entry/credit/refund/GL and allocations | A08 selects enrollment-generated tuition invoice chain; no competing producer or custom balance. Legacy Fees cannot duplicate it |
| Employment/payroll | ERPNext Employee, native Education Instructor link, HRMS work/leave/pay structures/inputs/slips/Payroll Entry; native accounting | A09 blocks pay-basis/input implementation. HRMS remains sole payroll authority; classroom attendance is not employee attendance |
| Coordination/integrations | Proposed TH Domain Operation; native integration/queue facilities first; minimal missing inbox/outbox capability only after B13 | Technical records own dedup/status/result references, not scores, balances, enrollment or salary truth |
| Reporting | Source owners above; named domain stewards own metric definitions; scoped queries first | Derived projections are rebuildable and non-authoritative; source changes do not permit rewriting historical released decisions |

## 3. Placement contract

### Inputs and outputs

An attempt identifies subject, purpose, exact approved assessment/rubric/policy, assessor assignment, permitted delivery window/accommodation and evidence references. It does not require a Student, Course Enrollment or Academic Assessment Plan.

A released Placement Result includes:

- subject and case/attempt references; assessment date and validity under approved policy;
- **internal English-level code/label and meaning**, bound to its policy revision;
- section/component observations or scores **where applicable**, with units, bounds and completeness;
- reviewer/assessor evidence where applicable and the approved decision rationale;
- recommended native Program/Course and internal course-level mapping, including unmet prerequisites or manual-review outcomes;
- approver, release information, supersession/revocation links and appeal/retest lineage.

An overall numeric total is **not mandatory**. Do not assume TOEFL's sections, 0–30/0–120 scoring, mock performance prediction, or official CEFR output. Internal numeric normalization/aggregation is allowed only after B04 approves its purpose, units and formula. Missing evidence is not zero; unlike scales are not averaged; no client-calculated result is authoritative. Academic course grading has a separate native policy and source set. B04 must separately supply native grading scales, weights, pass/progression criteria, correction authority and policy-version comparability; none is inferred from the placement policy.

The exact internal levels, components, rubric, thresholds, moderation, mapping, retest interval, validity and interrupted-attempt rules are **unresolved B04/B05 inputs**, not defaults. No automatic highest-score/latest-score rule or placement exemption exists. Until required policy is approved and evidence complete, the decision remains unreleased/review-required rather than guessed.

### State and integrity rules

| Aggregate | Logical states / transition rule |
|---|---|
| Policy/form/rubric/key revision | Draft → Approved/Published → Retired. Retirement stops new use, not historic interpretation; semantic changes require a new revision |
| Case | Open → Ready → In Progress → Awaiting Decision → Closed; withdrawal is explicit. Its original subject is not overwritten at conversion |
| Attempt | Registered → Started → Submitted or Timed Out → Marking/Review → Finalized; No Show/Voided are explicit outcomes, not silent zeros |
| Response/evidence | Revisioned draft → sealed manifest at submission; stale autosaves or late files cannot overwrite sealed responses |
| Rating | Draft → Submitted → Moderated or Superseded; independent review/conflict rules follow approved policy |
| Placement Decision | Draft → Reviewed → Approved → Released; later Superseded or Revoked through a new audited action |
| Review/retest | Appeal requests review; correction creates a superseding decision. Retest creates a **new attempt**, preserving prior raw evidence, ratings, policy and rationale |

Logical states are not extra native `docstatus` values. A submitted/retired flag cannot be used to alter immutable scoring content. Administrative/database access is not made cryptographically powerless by this contract; stronger audit/retention controls remain production requirements.

## 4. Admission, Student and enrollment separation

A10 selects a distinct Admission Decision referencing the native applicant and released valid internal placement. Admission evaluates actual eligible course/intake, conditions, offer acceptance and approved prerequisites. It does not turn a recommendation into enrollment automatically. Default initial entry follows placement; external evidence, tuition payment or prior learning does not silently manufacture/replace the required Placement Result.

Admission logical states: Draft → Review → Conditional / Approved / Deferred / Rejected, with acceptance, expiry, withdrawal, revocation and fulfillment recorded distinctly. Conditional offers cannot trigger enrollment before required predicates hold. B06 supplies real conditions/authorities/validity; no condition values are invented here.

Native Student conversion occurs only through the approved identity/admission path and may legitimately precede a tuition advance or Program Enrollment. Native Applicant “Admitted” at Student creation is **not authoritative proof of institutional approval or completed registration**.

Enrollment Request states: Requested → Validated → Applying → Completed, or Blocked / Needs Reconciliation / Failed Review. Completion requires the applicable native submitted enrollment, expected Course Enrollments, roster/entitlement and finance predicates, not merely a returned Student ID. Course participation requires actual approved membership/schedule, not simply a draft enrollment or paid receipt.

A05 blocks unsupported same-term repeats; A11 blocks unsafe history-affecting cancellation. Do not delete Course Enrollments to free a uniqueness key or replace earned academic history with placement evidence. Progression/completion uses native attendance/results and a separate approved progression policy; completion may recommend a subsequent course but does not itself enroll the learner.

## 5. Permission boundary

Each transition requires active native User, trusted site, permitted role/action, branch/company scope where applicable, verified subject or current assignment, allowed state and field/evidence visibility. Native access and domain policy are conjunctive. Role unions and client flags cannot override denials. Multi-branch isolation is enforced as authorization/data scope; aggregate views are separately authorized and cannot become a branch-operational bypass. Offboarding must revoke active sessions/roles while preserving historical records.

- Prospect/applicant access is subject-specific; placement entry does not grant Student or academic-group access.
- Guardian access uses explicit native Student membership after conversion. Pre-admission proxy authority remains A03 conditional; contact/payer status is not permission. No fake Student for login.
- Conflicting staff/learner/guardian account scopes remain A04 conditional and default-denied. A role selector cannot relax the current global exact guard.
- Candidate delivery is limited to allowed active-attempt content; keys and author-only notes are separate restricted records, not hidden child fields in a readable document.
- Assessors see assigned evidence, not the whole learner/recording bank. Submitted ratings and released decisions require authorized review; self/conflicted approval is prohibited according to the approved delegation policy.
- Admissions sees released placement and necessary eligibility evidence, not unrestricted raw keys/recordings. Finance cannot change level decisions; teachers do not gain payroll administration through teaching assignments.
- Private Files require parent permission **and** purpose/time/assignment visibility. Ownership, a known URL/job ID or a previous login is not enough. New parent types/staff roles require qualification beyond the existing guard's tested scope.
- Reports, lists, searches, exports, print/ZIP, asynchronous retrieval and realtime recheck equivalent row/field/resource access. Scoped views cannot leak full native documents through an alternate API.

Use the detailed role matrix in [permission-model.md](permission-model.md) only subject to A02–A04/A13 constraints. It is a target policy, not installed role configuration. B09/B10 must define retention, sensitive disclosures, conflict/approval rules and audited break-glass access.

## 6. Finance and workforce contract

### Finance

One economic obligation has one active native posting chain. A08 chooses **native enrollment-generated tuition Sales Invoice** through reviewed fee configuration, not simultaneous batch generation, duplicate legacy Fees or a custom cashbook. Commercial quotations/orders, if needed for offers, are not receivables or settlement.

If a deposit is required before invoice generation, use an approved native Customer advance/credit path after legitimate identity/party creation. Admission, invoice posting, payment allocation, settlement, refunds and entitlement remain separate. Browser redirects, screenshots and client `paid` values are not settlement evidence. Native amendments/credits/refunds preserve original references; never delete posted history to repair an orchestration failure.

B07 must approve actual company/currency/tax/fiscal/pricing/clearance/aid/refund/payer policy. None is configured in this gate. A later change to the tuition producer needs a new decision and obligation reconciliation, not a runtime flag that lets two producers race.

### Teachers, HR and payroll

Native Employee/Instructor links preserve employment versus teaching identities. Planned, delivered, approved-payable, posted and paid work are distinct. Student Attendance is not Employee Attendance and does not automatically pay or deduct salary.

HRMS remains the **single canonical payroll calculation/input authority** with native accounting/payment effects. Exactly one approved native input path applies per employee/pay-component/period/source basis. An owned work approval may contribute a uniquely referenced authorized input only if a native gap is proven; it cannot own a second salary amount or ingest the same basis through both Timesheet and Additional Salary.

A09 blocks choosing/implementing that path until employment classification, pay basis, payable work, leave/overtime/statutory rules and actual native behavior are established. Supplier contractors, if approved, use native supplier/purchasing/payment semantics rather than fake Employee payroll. No jurisdiction is inferred from the user's location.

The owner requirement is that teacher compensation support configurable fixed,
skill-based, and combined models. Rates, effective dates, skill vocabulary,
statutory rules and approval policy remain configuration/business inputs; the
implementation must feed the single native HRMS/payroll authority and must not
create a parallel compensation or payroll ledger.

## 7. Integration, transaction and retry contract

Proposed commands accept scoped references, expected revision and a stable idempotency key—not arbitrary DocType/method names, approval states, scores, totals or privileged flags. Server derives actor and authoritative values. Commands and native alternate writers must satisfy A13 before implementation acceptance.

1. Uniqueness is scoped by site/operation/business key. Same idempotency key and request hash returns the existing outcome; different payload with the same key conflicts.
2. Serialize conversion, current-decision changes, seat claims, calendar conflicts and native enrollment keys using reviewed native-compatible constraints/locks. Read-then-insert is not a concurrency proof.
3. Persist native result references and incomplete-operation state. On retry inspect existing effects; do not blindly repeat mapped Student conversion, invoice creation or payroll input.
4. Use one local transaction only where the native code supports it. Pinned attendance commits and enrollment side effects preclude a blanket all-or-nothing wrapper claim.
5. Send external effects after commit using native queues or a minimal justified durable dispatch intent. Reauthorize at execution, reconcile missing dispatch and make consumers idempotent. No exactly-once/distributed transaction promise.
6. Provider events, if separately approved, need signature/freshness and unique provider/account/event identity plus amount/currency/party/obligation validation. Do not select a gateway or deploy integration now.
7. Realtime and report jobs carry minimal references and authorize resource delivery/retrieval again. Revoked users cannot retain access through queued work or an earlier generated artifact.
8. Failures enter an explicit reconciliation state; financial compensation is native credit/amendment/refund. Historical academic cancellation remains blocked until A11 is resolved.

For the native `enroll_student` mapper, document hooks must enforce target admission/identity invariants independent of the mapping permission. Any native direct-write/privileged path that does not traverse those hooks needs explicit supported containment or must remain unavailable. Blocking a button or adding a wrapper alone does not satisfy the contract. Operators/database administrators remain privileged and require governed audit; this document does not claim runtime containment has been implemented.

## 8. Reporting and derived-data ownership

Each metric has a steward, source, grain, inclusion states, units, as-of time/timezone, denominator, exclusions, version and permission scope. Default to scoped source queries. Projections, if later justified, include source IDs/revisions and refresh status, are rebuildable, and cannot override their source or authorize an irreversible business action from stale data.

| Metric family | Authority and required distinction |
|---|---|
| Placement operations | Case/Attempt at explicit person/attempt grain; no-shows/retakes/finalized/released distinguished |
| English level/course recommendation | Released TH Placement Decision + internal policy; level as of assessment, not permanent identity or official TOEFL/CEFR claim |
| Academic performance | Native enrolled Assessment Result/Plan and academic grading policy; **never unioned into a generic placement/academic “test score”** |
| Admissions/enrollment | Applicant/Admission Decision/offer conditions versus submitted native enrollment and participation; Admitted status alone insufficient |
| Attendance/completion | Eligible held sessions and native results under approved progression policy; missing attendance is not automatically absence |
| Finance | Posted native invoice, allocation, credit/refund and GL; orders, cash and recognized revenue separated and reconciled by company/currency |
| Teaching/payroll | Native schedule/work/payroll/accounting evidence; planned, delivered, payable, posted and paid kept separate |

A joined learner timeline may show separately labeled placement and academic events, but must not aggregate unlike scales or copy placement scores into academic averages. Mapping/report text, CSV headers, DTO names, PDFs, notifications and dashboards all obey A07. There is no `official_toefl_score` output in this domain contract.

Aggregate and drill-down permissions apply before pagination/aggregation; downloads reauthorize after generation. Exported PII cannot be recalled by deleting a projection. Retention/legal hold, content rights and correction propagation remain B09 inputs; no retention period or legal certification is invented.

## 9. Contract closure and exclusions

The contract covers all required boundaries, but conditional identities/guardians/accounts/scoring/enforcement and blocked repeat/pay/cancellation capabilities prevent **unconditional implementation readiness**. Detailed status and explicit approvals are in [IMPLEMENTATION-READINESS.md](IMPLEMENTATION-READINESS.md).

This contract does not itself authorize an app code, DocType/schema, API, UI,
dependency, deployment or infrastructure change. No new official-exam integration,
offline protocol, parser upgrade, payroll engine, parallel ledger or parallel
learner master is authorized. Current Phase 2 failed evidence and production
**REJECT** remain unchanged. Internal consistency is a review result, not
production sign-off.
