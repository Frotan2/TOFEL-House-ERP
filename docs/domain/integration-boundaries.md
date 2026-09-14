# Integration, consistency and reporting contracts

## 1. Extension boundary

A future `toefl_house` app would contain domain DocTypes, controllers, fixtures, policy validation, permission hooks, reports and narrowly scoped service commands. This document defines interfaces, **not an API implementation**. Keep native authority in Frappe/ERPNext/Education/HRMS; use supported document methods and lifecycle behavior rather than copying controllers or writing transactional SQL directly.

- Use namespaced fields only when a native relationship is absent. Export reviewed fixtures and migrations, not manual production edits.
- Prefer additive document hooks and supported v16 class extensions where appropriate. Test hook ordering with HRMS and `foundation_security`. No competing wholesale override of Employee, File, Payment Entry or enrollment controllers.
- Never bypass admission, capacity, private-file or financial policy simply because a stock API is whitelisted. Inspect all alternate writers before granting a role; apply server-side invariants to native records as well as the domain command.
- Keep English names/fields/APIs and native Desk behavior. No new SPA, frontend build chain, domain UI redesign or forced dependency upgrade is selected.
- No external gateway, biometric device, official exam provider, AI scorer, SMS vendor or object store is chosen. Such adapters remain optional, separately reviewed integrations.

## 2. Proposed command contracts

Commands would accept native/owned document references, expected revision and idempotency identity—not an unrestricted DocType/method or client-assigned approval state. Server derives actor, site, scope, rates, score outputs and authoritative totals.

| Command family | Authorization / authoritative inputs | Durable result |
|---|---|---|
| Register/start/submit placement | Verified subject, Case/Form/Sitting, valid window/consent and current state | Attempt, sealed response receipt; never a client-computed final score |
| Submit rating / release decision | Assigned assessor or independent approver, frozen rubric/policy, valid evidence set | Immutable rating or new released decision revision |
| Decide admission | Assigned approver, native applicant/program/year, placement/exemption and eligibility evidence | TH Admission Decision; no automatic posting or enrollment |
| Execute enrollment | Approved request, native subject and target, current prerequisites/financial clearance/capacity | Existing-or-new native Student and one Program Enrollment chain, Course Enrollments and native billing references |
| Apply roster/academic change | Approved typed request, original records and impact plan | Supported native mutations plus correction/compensation references |
| Collect / reconcile / refund | Scoped native finance role, approved charge and payment evidence | Native invoice/payment/credit/refund records; no custom balance |
| Approve teaching work / payroll inputs | Current employee/schedule assignment, approved pay basis and units | Native work/payroll-input reference or adjustment; HRMS owns calculation and posting |
| Request report/export | Approved metric/filter/purpose and current row/field scope | Scoped report or private expiring artifact, reauthorized at retrieval |

Expected errors distinguish validation failure, forbidden scope, stale revision, duplicate-with-different-payload, capacity conflict and pending reconciliation. Return sanitized identifiers/status, not stack traces, response keys, payroll data or provider secrets. Retry behavior is part of the API contract, not left to clients guessing whether a timeout succeeded.

## 3. Concurrency, uniqueness and transactions

| Invariant | Proposed protection | Required failure test |
|---|---|---|
| Same command retried | Unique site/operation/idempotency key plus canonical request hash; same key+same hash returns original result; different hash conflicts | Lost HTTP response, repeated click and concurrent replay produce one effect |
| One Student conversion per approved application/person | Lock the native applicant/identity resolution record; enforce native applicant uniqueness and approved identity merge procedure | Two simultaneous conversions; returning student; duplicate contact information |
| Enrollment uniqueness | Lock stable Student/target coordination row; preserve native student/program/year/term check and reject conflicting active requests | Concurrent draft/submitted duplicate; same-term repeat request blocked, not “fixed” with fake periods |
| Seat/timetable conflicts | Lock native group/resource or reviewed reservation claim in deterministic order; recheck capacity and overlapping schedules under lock | Last seat, two coordinators, replacement teacher, simultaneous placement/class booking |
| Response/rating integrity | Unique attempt/item occurrence/revision and assignment/criterion/revision; optimistic revision checks and server deadline/seal | Autosave after submit, out-of-order retries, duplicate assessor submissions |
| One effective decision | Serialized approval/supersession on parent case/attempt; immutable evidence set | Two approvers, appeal racing admission, policy retirement during scoring |
| One economic charge | Stable business obligation identity and one active native posting chain; amendments/credits retain the chain, not duplicate original charges | Enrollment and batch fee generation racing; provider retries; canceled/amended invoice |
| One payroll input per approved work basis | Unique source work occurrence/period/component mapping to native result; corrections reference original | Reimport, reapproval, substitute overlaps, reversal then corrected adjustment |
| One external event application | Unique provider/account/event ID and verified payload hash, signature/freshness, currency/amount/party match | Replay, out-of-order refund/settlement, duplicate reference with changed payload |

Database uniqueness and explicit locking strategies are proposals to validate on the fixed MariaDB/Frappe stack. Lookup-before-insert alone is not sufficient. Do not silently add intrusive unique constraints to native tables with existing duplicates; assess data, use a minimal owned coordination claim where justified, and review migration/rollback first.

### Local and external transaction boundary

Use the native request transaction where the invoked code actually permits it. Inspect controller side effects, internal commits, enqueue/send behavior and exception paths before asserting atomicity. In particular, pinned Education's bulk attendance path commits, and enrollment submission can produce academic and billing side effects. Do not wrap such paths and claim distributed all-or-nothing behavior.

A coordination operation moves Requested → Validated → Applying → Completed or Blocked/Needs Reconciliation. Record native result references durably. On retry, inspect existing outcomes before creating anything. External delivery happens after commit through native queues or a minimal durable dispatch intent; a recovery scanner resumes undispatched intents. Do not add Kafka, a second scheduler or a parallel workflow engine.

Financial compensation uses native cancellation/amendment/credit/refund under authorization, never direct GL edits or deletion of submitted history. Academic compensation preserves original attendance/results and evaluates Course Enrollment deletion risk. A request is not Completed while required effects remain unresolved; operational queues expose partial completion safely.

Use transactional row locks and database constraints as supported by the framework. Do not invent distributed transactions, exactly-once delivery or guaranteed rollback of email/provider actions. Async handlers are retryable and idempotent; actor authority is rechecked at execution. Revoked actors require an explicit authorized recovery decision, not silent continuation under Administrator.

## 4. Integration interfaces

### Native identity and activation

Native User remains authentication authority. Proposed enrollment activation uses supported `user_creation_skip` configuration to prevent premature native auto-provisioning, then creates/links a verified User, required native User Permissions and institution-specific scopes before enabling access or sending invitations. Explicitly qualify welcome-email ordering, Guardian link updates, shared-email conflicts and recovery. The current foundation guard must not be disabled because a new domain record is missing links.

### Finance / Payments

Retain Payments as required by the pinned bundle; that is not approval of any gateway. If a provider is added, use server-side verified events and transaction lookup as appropriate; browser redirects are advisory only. Store minimal receipt identity/hash/status and native document references; keep secrets outside code/evidence. Signature replay prevention and native document idempotency are separate requirements.

Reconcile accepted events to bank/provider settlement and native payments. Handle pending, failed, partial, reversed, disputed and refunded outcomes without inventing a separate cash ledger. Amount/currency/customer/account must match the approved native obligation; a user-supplied invoice name alone is insufficient.

### HR / teaching work

Prefer native Instructor→Employee, schedule, Timesheet/Attendance and HRMS payroll inputs. An adapter may translate an approved work decision into one native supported input only after finance/HR signs off. Do not sum classroom minutes directly into a payslip without an approved employment/pay rule. Native Salary Structure and payroll controllers own calculation; native accounting owns resulting entries and settlement. Course revenue is not teacher compensation by default.

### Content, files and media

Internal placement uploads are private native Files linked to authorized attempt/evidence records. Scanner/transcoder needs a resource-scoped service interface, bounded input/output and private temporary storage. Quarantine and cleanup semantics need qualification; no scanning capability is claimed from merely naming it. Released learner documents are separate sanitized views from internal evidence. No answer keys or confidential payroll data in client bundles or notifications.

### Realtime / background execution

Use the existing resource-authorized delivery boundary and native RQ/scheduler. Job messages carry references and operation IDs, not bulk sensitive payloads. Authorize event subscribers and delivery against current record/attempt/assignment scope. A user-scoped progress stream still needs a valid operation relationship. Multi-resource and broad broadcasts are denied unless separately designed and qualified; identifiers alone are never capability tokens.

## 5. Reporting ownership and metric definitions

Reports are scoped read models; the native/owned source record remains authoritative. Materialization, if needed after measuring load, carries source revision, cutoff/as-of time and refresh status. No warehouse, new database or unbounded cross-site analytics is selected.

| Report / question | Source and grain | Definition / reconciliation rule |
|---|---|---|
| Inquiry/admission funnel | Lead, native Applicant, Admission Decision, Enrollment Request; person vs application grains separate | Distinguish unique prospects, application counts, accepted offers and completed requests backed by submitted native enrollment. Native Applicant “Admitted” alone is insufficient |
| Placement operations | Case/Sitting/Attempt at attempt grain | Separate registrations, starts, no-shows, submitted, flagged, awaiting marking and finalized; retakes not counted as new people |
| Skill/placement outcomes | Released Decision + frozen evidence/policy | Show policy/form revision, missing-data exclusions and cohort scope; do not mix unlike scales or label internal scores as official results |
| Academic roster/capacity | Native Student Group, active native enrollment and approved reservations | As-of membership/effective dates; reserved versus confirmed seats separate; no duplicate student counts across joined courses |
| Attendance | Native Course Schedule and Student Attendance/approved leave | Denominator is eligible held sessions (or approved duration basis), with canceled/transfer/leave rules explicit; unknown records remain unknown |
| Academic progress/completion | Native Assessment Result/Plan plus Progression Decision | Distinguish raw academic results, policy-derived eligibility and approved completion; corrections retain lineage |
| Learner account statement | Native invoice, payment allocation, credit/refund and ledger records | Company/currency/as-of scoped. Separate outstanding, allocated cash, unapplied credits and refunds; do not sum orders as receivables |
| Revenue / branch margin | Native posted accounting, company/cost center and approved dimension mapping | Recognized revenue is not cash collected or admissions count. Reconcile to GL; payroll allocation policy and shared costs explicitly defined |
| Teacher utilization | Native schedules, Instructor/Employee and approved work references | Planned, delivered, approved payable and paid units shown separately; student attendance does not establish payable time |
| HR/leave/payroll | Native employee/leave/attendance, slips/Payroll Entry/accounting/payment | Headcount vs employment periods; payroll prepared, posted and paid distinct. Restrict employee-level and small-cohort disclosures |
| Exception/control dashboard | Domain operations, native source references and access/audit records | Stuck enrollment, duplicate-charge suspicion, unallocated payment, overdue marking, failed delivery and reconciliation age; no sensitive payload dump |

Each metric needs a reviewed fixture with exact denominator, inclusion statuses, timezone, currency, rounding, as-of cutoff, permission scope and expected reconciliation. Drill-down cannot broaden access. Exports must preserve scope, source/as-of metadata and private retrieval with reauthorization.

## 6. Deployment boundary remains unchanged

Designing these interfaces does not close the failed frontend advisory gate or qualify public TLS, database/Redis/host failure, independent-host recovery, payroll posting, capacity or incident operations. Existing hosted foundation passes remain baseline regression evidence, not proof of a future domain app. No production deployment is authorized.
