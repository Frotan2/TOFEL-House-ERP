# Permission, identity and privacy model

**Proposed policy only.** Names below are business roles to map to reviewed Frappe roles; they are not installed roles or a claim that stock Role Permissions enforce these scopes. Site/branch/company/assignment checks, native permissions and field visibility must all hold. Current foundation tests do not qualify these new domains.

## 1. Authorization rule

For every action: authenticated active User **AND** trusted site **AND** approved role/action **AND** allowed branch/company **AND** verified relationship/assignment **AND** allowed document state **AND** field/evidence visibility. Fail closed on missing or ambiguous links. Explicit constraints and separation-of-duty rules must not disappear when role permissions are unioned for a multi-role user.

No client role/score/parent/status/`ignore_permissions` flag or hidden button confers authority. Enforce invariants in document/controller hooks as well as command endpoints so REST/RPC, native mapping APIs, imports, reports, jobs and administrative workflows cannot silently skip them. Privileged maintenance/import needs a narrowly approved, logged process—not an unaudited magic bypass flag.

## 2. Proposed role matrix

`Own` means verified subject/account links, not email similarity or File.owner. `Assigned` means current case/attempt/group/schedule/work assignment and effective time. All rows are site-scoped and branch/company-restricted where applicable.

| Business role | Read scope | Create/update/transition | Explicit exclusions |
|---|---|---|---|
| Reception | Assigned branch Lead/application contact and scheduling data | Intake drafts, placement registration, document collection | No scoring keys, ratings, unrestricted HR/payroll, payment settlement or admission override |
| Admissions Officer | Assigned applicants, released placement summaries, offer/clearance status | Application review, offer/request drafting, acceptance evidence | Cannot alter raw scores, approve own exceptional admission or manufacture paid status |
| Admissions Approver | Assigned admission cases and necessary eligibility evidence | Approve/defer/reject/exempt with reasons; independent exceptional approval | No ledger posting or unrestricted test key access |
| Placement Author / Publisher | Authorized item/key/rubric/policy library | Draft/publish revisions with separation where required | No automatic access to all candidate recordings; author cannot self-approve controlled publication |
| Placement Coordinator / Proctor | Assigned sittings, candidate identity and attempt state | Register/start/record incidents under policy | No keys or private human ratings by default; cannot change scores/deadlines without approved exception |
| Assessor | Assigned attempt material and rubric, minimized identity | Draft/submit own ratings | No other assessor's blind draft, finance/HR records, global recordings or self/family assessment |
| Academic Moderator / Approver | Assigned scoring evidence, policy and conflict history | Moderate, approve/release/supersede decision with reason | Cannot silently edit sealed responses/raw scores or approve own conflicted case |
| Academic Operations | Branch catalog, rosters, schedules, released placement/admission eligibility | Configure actual offerings, registration/transfer requests, schedule and roster commands | No direct bypass of approvals/capacity, payroll detail or payment settlement |
| Teacher / Instructor | Assigned active groups, relevant student learning data, plans/results | Session attendance and assigned academic results; correction requests | No broad Student export, placement bank, other teachers' work/pay or financial ledger; academic scope does not grant HR access |
| Cashier / Collections | Authorized Customer/invoice/payment fields needed for collection | Native receipt/payment drafts or allowed posting within cash/bank policy | No refunds/discount exceptions approval, scoring/recordings, HR pay data |
| Accountant / Finance Approver | Authorized company ledgers and reconciliations | Native invoice/credit/refund/close workflows and financial approvals | No academic score/placement override; sensitive payroll details only when specifically assigned |
| HR Officer | Authorized employee/employment/leave/work data | Native HR lifecycle and approved payroll-input preparation | No candidate test evidence, student financial detail or unapproved payroll posting |
| Payroll Processor / Approver | Authorized company employees, payroll inputs and slips | Prepare/review/post native payroll with independent authorization | No academic grading, unrestricted other-company payroll, self-approval of own pay adjustment |
| Branch Manager | Scoped operational summaries, approved escalations | Approvals explicitly delegated by type/value scope | Not System Manager; no automatic answer-key, raw recording or all-employee salary access |
| Auditor / Privacy Officer | Purpose-limited approved records/audit | Read/review and records-request processing, not transaction editing | Export separately authorized; no broad PII download from a generic reporting role |
| Applicant | Own verified application, active attempt delivery/responses, released decisions | Own allowed drafts/answers, submission and review requests | No direct item-bank/key/form administration, ratings, other applicants, Student creation or enrollment approval |
| Student | Own approved enrollment/schedule/attendance/results and permitted student-facing invoice/payment summaries | Own requests; permitted attempt submissions | A student role never grants employee payslip access. No peer rosters, unrestricted Customer/accounting fields or staff data |
| Guardian | Explicitly linked children and purpose-allowed released records/requests | Approved guardian requests/payment initiation, not settlement | No authority from contact email, ownership of old files or unrelated child/customer links; restricted child data may need separate policy |
| Employee self-service | Own Employee, leave, approved work and native payslip disclosures | Own native requests | Not access to all students because employed, or all payroll because a teacher |
| Integration / Background service | Exact configured operation/resource scope | Verified commands and retries with operation IDs | No general-purpose CRUD, broad events or reusable Administrator credentials in client/job payloads |

Use field-level restrictions/DTOs to exclude answer keys, moderation notes, bank details, health/accommodation specifics, government IDs, salary and unrelated household records. A custom role name alone does not protect fields in generic document, search, list, report or export responses.

## 3. Identity, guardianship and multi-role conflicts

- Provision applicant/student/guardian/employee links explicitly. Proposed applicant self-service is optional and blocked until the `User → native subject` claim/verification and required-email policy are reviewed. Staff-assisted intake does not resolve native Student's email requirement by itself.
- Guardian.user and Student Guardian rows remain canonical. Grant exact child/customer scopes; relinking, new children, revoked guardianship and shared accounts require immediate revalidation. Existing single-purpose guard assumptions must be tested for multiple children, not broadened blindly.
- The current foundation guard enforces exact Student/Guardian scopes globally, including all-doctype native User Permissions. A role selector cannot turn that into broader teacher access. The matrix describes desired policy, not proven same-account mixed-role usability. Default to denying conflicting grants until D02/D10 are resolved. Separate explicitly linked native staff and learner/guardian User accounts may be evaluated for one person, without duplicating Student or Employee masters; no shared credentials, fabricated email or weakening of the guard is authorized.
- Existing Guardian login expects actual Student membership, not only a Student Applicant guardian child row. Pre-admission guardian self-service is therefore **not assumed supported**. Staff-assisted intake or a separately approved applicant/proxy relationship must be designed and qualified under D02; do not create fake Students to enable login. Any assisted response capture must record both actor and subject and explicit delegation, not impersonate the candidate.
- A teacher who is also a guardian must not gain cohort-wide learner self-service; an employee who is also a student must not expose salary through student APIs. Self-service reads use the selected verified relationship, while staff actions require the corresponding staff assignment and field scope.
- Impersonation and break-glass access are restricted, time-bounded and audited, with independent review. Technical Administrator remains a privileged capability, not a routine business persona. This design does not claim an application can make database administrators powerless.
- Termination, reassignment, disabled accounts and relationship revocation invalidate sessions/queued access where appropriate. Permissions are rechecked for live events and downloads; a token or earlier successful login is not permanent authorization.

## 4. File and test-content security

Every sensitive File requires current parent permission plus purpose-specific access (response, prompt delivery, scoring key, ID, accommodation, payroll). File ownership cannot override parent scope. The generic foundation protection must be assessed/extended through owned supported mechanisms for **new parent types and staff roles**; it is not already proof for placement/payroll attachments.

Prompt/media delivery must validate active attempt, allowed item and time/release policy without granting bank read. Responses/recordings are private and assignment-scoped. Scoring keys are separate restricted documents. Never place secrets in a candidate-readable child table or rely on front-end hiding. Exports, generated PDFs/ZIPs, thumbnail/copy endpoints, duplicate file URLs, orphan/reparented files and legacy owners need explicit negative tests.

No public object-storage bucket, permanent bearer download link or new storage service is selected. Retention, recording consent and malware/media processing are unqualified requirements. URLs and job IDs are identifiers, not authorization secrets.

## 5. Reporting and communications

Scope list queries and Link searches, report source rows, aggregates, cached results and drill-downs. Suppress or restrict small-cohort sensitive aggregates as approved; a count can leak private outcomes. Permission predicates must run before pagination/aggregation, not filter a full downloaded dataset client-side.

Asynchronous exports capture requester/purpose/filter scope, then recheck at execution and retrieval. Revocation after job submission must deny download. Generated artifacts inherit sensitivity and expiry policy. Finance/HR exports and bulk messaging require separate capabilities and audit.

Realtime events use explicit resource authorization and fresh session checks; no broad site/group task payloads with scores, identities, finance or payroll. Follow existing deny-only realtime boundaries rather than introducing a second permissive event path. Notification templates minimize personal detail and recheck recipient relationships.

## 6. Required security test matrix

For each role and action, test both permitted and denied paths through Desk, generic REST, whitelisted/native RPC, list/search, reports, export/print/ZIP/files, imports, scheduled/background jobs and realtime. Include cross-site, cross-company/branch, unrelated student/child, missing scope, stale assignment, self-approval, tampered totals/parent links, old file ownership, disabled user, expired attempt and retry/concurrency cases.

Special fixtures: two applicants; two students; guardian with multiple children and an unrelated child; teacher with own child in another class; employee/student combined identity; finance/HR users in two companies; replacement assessor; late media upload; revoked guardian with owned attachments; service retry after actor revocation. Existing passed foundation cases remain regressions, not permission to skip these new tests.
