# TOEFL House ERP — Operational Ownership Charter

Date: 2026-09-16 · Branch: `arena/01a0a9f7-tofel-house-erp`

**Status: T5 delivered as a code-derived charter; production remains REJECT.**

## 1. Purpose and authority boundary

This is the canonical operational ownership record for the **shipped,
synthetic-only** TOEFL House application surface. It translates actual role
fixtures, guarded commands, document permissions and reports into operational
responsibilities. It is not a staffing plan, an assignment of a person, a
service-level commitment, an approval of deployment, or a new business-policy
decision.

The authoritative executable sources are:

- `apps/toefl_house/toefl_house/fixtures/role.json` — the 18 installed custom
  role names;
- `security.py:KIND_ROLES` and the `authorize` / non-serializable `command`
  context — command authority;
- `hooks.py` and the native-document guards — alternate-write containment;
- the DocType `permissions` arrays plus `permissions.py` — direct read/list
  scope; and
- the standard Query Report JSON files — report audiences.

Every command also requires the isolated-site condition in `require_synthetic`:
`allow_tests=1`, `toefl_house_synthetic_only=1`, and one of the two named
qualification sites. Therefore this charter does **not** make any role usable
on a production site. Direct document write/create/submit authority is not
assigned to any custom role; commands create their own short-lived context and
are the only supported writer route for guarded records.

## 2. Application operating-role matrix

“Own” and “all” below describe the current code, not an organizational job
assignment. A listed command is a necessary role check, not a guarantee that a
transition is valid: the server also rechecks state, record links,
idempotency, synthetic scope and the separation controls stated in the final
column.

| Installed role | Existing guarded command responsibility | Current direct record/report surface | Code-enforced boundary |
|---|---|---|---|
| Placement Author | Create/revise item drafts; create/revise blueprint, policy and course-map drafts | Own item/key/config drafts; published item/config revisions | Cannot publish; no case/attempt access as Author alone; author-only draft changes and item-family namespace are checked server-side |
| Placement Publisher | Publish an item; review/publish/retire blueprint, policy and course-map revisions; create a case; allocate an attempt | Placement content, config and operational records needed by the Publisher; no receipt/audit ledger | Cannot publish own item/config or publish a config it reviewed; configuration and allocation prerequisites are revalidated |
| Placement Invigilator | Verify, deliver, save response for, and seal a digital attempt | Case, attempt, exposure and response rows; not the manifest or answer keys | Must be the assigned non-allocator session operator; state/version/occurrence checks remain server-side |
| Placement Assessor | Score a sealed attempt | Case, attempt, response and score rows; not manifest or keys | Scoring loads protected keys only in the server command; only sealed supported-format attempts score |
| Placement Reviewer | Independently review and finalize a marked digital attempt | Case, attempt, response and score rows; not manifest or keys | A scorer cannot review or finalize the same attempt; finalization also rejects the reviewer |
| Placement Releaser | Release a finalized placement decision | Case, attempt, response, score and released-decision rows; not manifest or keys | Server rejects a scorer, reviewer or finalizer releasing that attempt and requires a valid published course map/pinned policy |
| Placement Auditor | No transaction command | All implemented placement records, including operations and audit events; published item/config filtering is applied to lists | Read/select only; no answer-key read and no write path |
| Admission Officer | Record a synthetic applicant; create, accept, withdraw or expire an admission decision | TH Admission Decision rows | Cannot review/approve/revoke/convert; commands do not create enrollment, payment, attendance or payroll |
| Admission Reviewer | Review an admission decision | TH Admission Decision rows | Read/select only outside the guarded review transition |
| Admission Approver | Decide, revoke, or convert an admission decision to native Student | TH Admission Decision rows | Decision-state and conversion preconditions are checked; approval does not enroll or bill |
| Admission Auditor | No transaction command | TH Admission Decision plus shared operation/audit ledger | Read/select only; no placement key, decision or manifest access |
| Enrollment Officer | Submit an eligible native Program Enrollment | No owned admission/placement document read is granted by this role | Admission actor separation, accepted eligibility and native Student linkage are rechecked; no invoice/attendance/payroll command |
| Enrollment Auditor | No transaction command | Shared operation/audit ledger | Read/select only; no admission/key/decision access |
| Teaching Scheduler | Create native Student Group and Course Schedule; record/end TH Teaching Assignment facts | TH Teaching Assignment rows | No native Education CRUD role; roster comes only from submitted Program Enrollments and native schedule checks still run |
| Attendance Recorder | Record submitted native Student Attendance facts | No owned attendance ledger/read surface | No native Education CRUD role; complete roster statuses and duplicate/session checks are server-side |
| Teaching Auditor | No transaction command | TH Teaching Assignment plus shared operation/audit ledger | Read/select only; no native attendance report is shipped (D9 option d) |
| Finance Officer | Issue tuition Fees/placement Sales Invoice; create/revise instructor contract; calculate compensation; configure/request/approve/deny correction framework actions | TH Instructor Contract, TH Teaching Assignment, correction policy/request; **report-only** access to TH Placement Operation; tuition and placement billing reports as configured | `Accounts User` is an upstream native prerequisite in the qualification fixture, not an app-managed role grant; correction approval additionally requires the configured approver role; native money/HR documents remain the authorities |
| Finance Auditor | No transaction command | Shared operation/audit ledger, instructor contract/teaching assignment and correction rows; TH Placement Billing Register | Read/select only; no tuition-register audience and no direct money-document permission is created by this app |

### Read-containment interpretation

The table deliberately distinguishes **owned-document reads** from native
upstream authority. Some API-first roles do have tightly scoped `read`/`select`
rows on TH DocTypes because their command workflow requires controlled evidence
access. They do **not** receive direct native Education/ERPNext CRUD roles for
Program Enrollment, Student Group, Course Schedule, Student Attendance, Fees
or Sales Invoice. `permissions.py` narrows the role rows further (for example,
Author-owned drafts, published configuration visibility and the internal-only
allocation guard).

The previous R1 narrative that all API-first roles had “zero document
permissions” was not literal: it conflicted with these shipped TH DocType
read rows. The canonical statement is the one above. It does not widen a role,
and it does not alter the two existing Workspace audiences.

## 3. Surface and audit matrix

| Surface | Audience exactly in shipped configuration | Scope and ownership meaning |
|---|---|---|
| **TH Receipts** Workspace | Placement, Admission, Enrollment, Teaching and Finance Auditors | Navigation to shared TH operation receipts and audit events. Workspace visibility itself grants no read authority. |
| **TH Finance** Workspace | Finance Officer | Native Accounts-module navigation plus the two billing registers. Its visibility anchor is the pre-existing upstream `Accounts User` role in the qualification fixture; it is not a substitute for a command or approval check. |
| **TH Tuition Billing Register** | Finance Officer | Raw `Fees` billing facts only; no derived metric, threshold or denominator. |
| **TH Placement Billing Register** | Finance Officer and Finance Auditor | Raw placement Sales Invoice facts only; no derived metric, threshold or denominator. |
| Shared operation/audit ledger | The five Auditor roles | The command receipt and audit chain. It is not a second accounting or payroll ledger. |

No attendance-coverage report exists: the owner selected D9 option **(d)**, so
attendance facts remain reachable only through the guarded APIs. No report
creates an approval, rate, tax, refund term, grading rule or staffing rule.

## 4. Built-in separation and custody controls

The following are ownership separations already enforced in code, rather than
new operating policy:

- author versus Publisher for item publication and config review/publication;
- allocator versus Invigilator for a session;
- scorer versus Reviewer, Finalizer and Releaser for the same attempt;
- Admission Officer/Reviewer/Approver command families, plus the Enrollment
  Officer’s separation from the admission actors of the record being enrolled;
- Teaching fact recording versus Finance/Payroll compensation calculation; and
- Finance Officer command access plus a policy-configured approver role for a
  correction approval/denial.

The last control is deliberately fail-closed until its already-defined policy
carrier has an approver role and correction window. This charter neither
selects that role nor supplies a window, amount, tax treatment or refund term.

## 5. Deployment-operation ownership slots (D8 remains open)

The application code has no production deployment, host, monitoring, backup or
identity-operations role. The following are the operational ownership slots
that remain to be selected by the owner/contract holder. They are restatements
of D8 and the existing foundation production-acceptance ledger, not new policy.
The exact minimal response and the required production evidence are in the
[D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md); it requests no
names, credentials, or invented service commitments.

| Responsibility slot needing an accountable owner | Required decision/evidence already recorded | Current state |
|---|---|---|
| Deployment/change control | Approved production bundle/topology and a full-bundle upgrade/rollback or restore-based rollback rehearsal | No production topology or operator assigned |
| Data recovery and key custody | Independent-host encrypted recovery, key availability, session revocation, and owner-defined RPO/RTO | Scoped hosted restore evidence exists; independent-host recovery and targets are not proven |
| Edge, secrets and session security | TLS/reverse-proxy/session policy and controlled secret handling | No production edge or policy configuration is in this repository |
| Capacity, monitoring and incident handling | Representative capacity/availability objectives, queue/DB/web proof, alert delivery and audit/log retention/rotation recovery | No accountable monitor/operator or measured production capacity evidence |

## 6. Genuine owner decisions still required

T5 surfaced no new business-policy question. The genuine unresolved owner work
is precise:

1. select an accountable authority for each D8 responsibility slot above,
   including the authority to operate, recover, and escalate; this document
   does not name one;
2. provide the D8 topology, recovery, capacity/monitoring and TLS/proxy/session
   decisions/targets needed to design and rehearse production operations; and
3. separately decide the already-open policy gates recorded in
   `OWNER-DECISIONS.md` (for example academic/guardian policy). They are not
   implied by this charter.

Naming a role in the application fixture does **not** assign a human, create a
contract, define a shift pattern, authorize a production operator or satisfy a
separation-of-duty staffing decision. No such policy has been invented here.

## 7. Completion and release effect

**T5 is complete:** a canonical, code-derived role/responsibility matrix and
the D8 ownership slots now exist. **D8 is not closed:** the owner must still
make the assignments and production-operation decisions above, and the
foundation production gates must be independently proven. The application is
synthetic-only; every production verdict remains **REJECT**.
