# Role Desks — the daily-work product layer

Date: 2026-09-19 · Active branch: `arena/01a0ba0d-tofel-house-erp`

This document specifies the role product layer built on top of the qualified
command slices. It is the contract between the eight desk audiences and the
server projections that serve them. Every section states its data source, its
definition, its empty state and its failure state. Nothing here creates a
parallel master, ledger, accounting model, permission model or workflow engine.

## What was missing

The qualified slices are *command-complete but product-incomplete*: every
mutation exists behind a guarded, idempotent, role-checked endpoint, but a
person could not answer "what is my next action?" without knowing record names,
statuses and which colleague owns the next step. The management roles —
Reception, Academic Manager, Finance Manager, General Manager and the Course
Owner — plus the Instructor role had no surface at all. The desks close that
gap without widening any authority.

## Architecture

```
Role Desk Page (native Page, Page Has-Role gated)
  └─ one whitelisted read: toefl_house.desk.<role>.work()
       ├─ role gate      (explicit desk audience, fail closed)
       ├─ scope          (native User Permission on Company/Branch honoured;
       │                  company-scoped where the record carries `company`)
       ├─ minimal fields (declared per desk in desk/__init__.py PROJECTION_FIELDS)
       ├─ bounded reads  (every query carries an explicit limit)
       └─ sections       (facts / queues; every item carries stage + next action)
  └─ guided actions: per item, ONLY if the viewer also holds the acting role,
     the projection embeds a prefill for the EXISTING guarded command endpoint.
     The client never decides authority; it renders what the server sent.
```

Rules that are binding for every desk:

1. **Real data.** Projections read the native records the lifecycle already
   runs on (`Student Applicant`, `Student`, `Program Enrollment`, `Student
   Group`, `Course Schedule`, `Student Attendance`, `Fees`, `Sales Invoice`,
   `Payment Entry`) and the owned slice records (`TH Placement Attempt`,
   `TH Placement Decision`, `TH Admission Decision`, `TH Teaching Assignment`,
   `TH Correction Request`, `TH Placement Audit Event`). No derived master is created.
2. **Smallest authority.** A desk role receives no document permissions. Where
   a desk shows a record the role cannot natively read, the read happens inside
   the desk projection, is gated by the desk audience, exposes only the fields
   declared in `PROJECTION_FIELDS`, and is never writable.
3. **Never blur money or status.** Finance facts use the native vocabulary:
   `docstatus` (draft/submitted/cancelled), native `Sales Invoice.status`
   (Overdue, Paid, Unpaid, Return, Credit Note Issued, Cancelled), and the
   native `outstanding_amount`. Charged = submitted `grand_total`; paid =
   submitted `grand_total − outstanding_amount`; outstanding = native
   `outstanding_amount`. Refund/credit-note states come from the native
   `is_return` / `Credit Note Issued` / `Return` statuses, never from a
   projection-local enum.
4. **No invented business metrics.** A tile is a count of a named record state
   with its definition in the tile. Where a threshold would be business policy
   (e.g. "at risk"), the desk shows facts and names the owner decision it waits
   for; it does not fabricate a definition.
5. **Fail closed.** Every desk endpoint first checks the desk audience.
   Unknown viewers, disabled users and errors produce explicit empty/error
   states in the client — never partial data, never a spinner that hangs.
6. **Escape everything.** Every server value is rendered through the shared
   escaping helper before it reaches markup (pinned by
   `tests/foundation/test_role_desks.cjs`).
7. **One round trip per desk.** A desk load is a single `work()` call with a
   bounded, budgeted query set (see the per-desk query budget below).

## The desks

| Page (slug) | Audience (Page Has Role) | Module | Endpoint |
| --- | --- | --- | --- |
| `th-reception-desk` | Reception | Operations | `toefl_house.desk.reception.work` |
| `th-academic-desk` | Academic Manager | Operations | `toefl_house.desk.academic.work` |
| `th-finance-desk` | Finance Manager | Operations | `toefl_house.desk.finance.work` |
| `th-operations-desk` | General Manager | Operations | `toefl_house.desk.operations.work` |
| `th-owner-cockpit` | Course Owner | Operations | `toefl_house.desk.owner.cockpit` |
| `th-academic-setup` | Course Owner | Operations | `toefl_house.desk.setup.work` |
| `th-teacher-desk` | Instructor | Operations | `toefl_house.desk.teacher.work` |
| `th-configuration` | Course Owner | Operations | `toefl_house.desk.configuration.work` |

`toefl_house.desk.available` tells any desk (and the command-centre
landing page) which desks the *server* believes this viewer holds — the client
never guesses roles.

### Reception desk — "Is this person in the system, and what happens next?"

Sections:

- **Applicant funnel** — counts per lifecycle stage (see `desk/lifecycle.py`).
  Definition of every tile is the stage definition itself.
- **People in the funnel** — the most recent applicants and their live stage
  (applicant record, admission decision, placement decision) with the next
  action and the role that owns it. If the viewer also holds the acting role,
  the item carries a prefill for that guarded command.
- **Find a person** — `toefl_house.desk.reception.lookup(query)` matches
  applicant/student name or email (bounded, no wildcards) and returns the same
  stage projection. This is the "student walks in" answer in one place.

### Academic Manager desk

- **Academic funnel** — placement attempts by state, decisions awaiting
  release, admissions awaiting review/decision/acceptance/conversion,
  enrollments awaiting a class.
- **Classes & sessions today** — native `Course Schedule` for today and native
  `Student Group` facts (capacity vs. roster size facts only).
- **Admission validations** — the exact decision records waiting on an
  Academic-side role, with prefill actions when the viewer holds that role.
- **Teaching assignments & workload** — `TH Teaching Assignment` facts and
  sessions per instructor for the visible window (facts, not ratings).

### Finance Manager desk

- **Today** — collections (`Payment Entry`, submitted, type Receive) and
  billings issued today, each with its native amount and currency.
- **Outstanding** — submitted `Fees` and `Sales Invoice` with native
  `outstanding_amount > 0`, grouped by document type, oldest due date first.
  Each row shows charged / paid / outstanding / native status. Refunds and
  credit notes surface through the native statuses only.
- **Awaiting billing** — submitted `Program Enrollment` records with no
  `Fees` row yet (definition: enrollment submitted, zero Fees referencing it).
- **Correction queue** — `TH Correction Request` by status (pending /
  approved / denied), each with its invoice, requested amount and state.
- **Teaching assignments** — `TH Teaching Assignment` identity and window
  only (instructor, skill, class, dates). Pay is native payroll, one-off per
  assignment (D12). The desk does not calculate pay and does not project
  rates or Additional Salary rows.

### General Manager desk (operations, not a second Owner cockpit)

- **Cross-role funnel** — the same lifecycle tiles, branch-wide, with the
  stage that holds the oldest waiting item called out.
- **Exceptions** — correction requests pending, admissions stuck in Review
  with waiting age, attempts past their deadline, unpublished finalized
  decisions. Facts with ages; no invented severity.
- **Staffing** — count of enabled users per shipped operational role (native
  `Has Role`), so an assignment gap is visible before it becomes a queue.
- **Recent recorded actions** — the last bounded set of completed guarded
  commands, projected from the existing audit receipts (actor, action, target,
  when). Hashes, keys and result payloads stay off the desk. Session saves and
  draft authoring stay on the auditor workspace. This is not a second log.
- **System health** — native health facts (application ping, unseen error
  rows, failed background jobs, observed workers with verbatim states,
  stopped schedules, failed scheduled runs) plus failed-job/error/stopped
  work items and generated alert conditions. Conditions are generated,
  never delivered: no receiver exists in this product (see
  `toefl_house/observability.py`, RECEIVER BOUNDARY). Tracebacks and error
  text stay on the native forms.
- **Links** — one row per role desk the viewer may open.

### Academic Setup desk (the configuration control plane)

The Owner's configuration surface (docs/product/CONFIGURATION-PLANE.md):
configuration health facts — including surfaced integrity faults such as a
level missing its native anchor — the program families, their ordered levels
with the *governing effective-dated duration* resolved from version history
(each stating the actor and reason that set it), the academic years with
per-year fee-plan coverage, and guided actions into the guarded configuration
commands (`toefl_house.academic.*`). Deactivation is offered only where the
server allows it; refusals arrive in business language with real counts.
Grading stays an explicit placeholder: owner decision D1 has not been made,
so no grading rules exist anywhere in the product.

### Teacher desk — "What do I teach today?"

Audience: the Instructor role. Identity resolves through the native chain
only (session `User` → `Employee.user_id` → `Instructor.employee` →
`TH Teaching Assignment`); a role holder who resolves to no instructor gets
an explicit empty state naming the missing link, never another teacher's
classes. Sections follow the daily path:

- **My classes** — assigned classes with lifecycle state, skill, roster
  size and assignment window. Closed classes stay listed as past work.
- **Today** — today's sessions for my classes with time, course, room and
  attendance state; unrecorded sessions prefill `record_attendance` for
  viewers who hold Attendance Recorder.
- **Sessions and attendance** — recent sessions with submitted-attendance
  counts (marked/absent); only submitted rows count.
- **Students** — my class rosters (name, roll, roster state).
- **Academic work** — recorded assessment results for my classes, shown
  exactly as recorded (score, maximum, grade, draft/submitted state). No
  thresholds are stated: grading policy is owner decision D1.
- **Compensation facts** — teaching-contract identity and window only
  (model, basis, frequency, dates, status). Pay runs through native
  payroll; the desk calculates nothing and shows no rates or amounts.

### Owner cockpit

Everything the GM desk shows, plus:

- **Governance attention** — the fail-closed release facts (production REJECT,
  SEC-DEPS-01 upstream-blocked) from the same static, reviewed constants the
  administration control centre uses. Not new policy — the same recorded state.
- **System health counts** — the same native health counts the GM desk
  shows (failed-job detail lives on the GM desk).
- **Recent recorded actions** — the same existing audit receipts the GM desk
  shows. Not a second trail.
- **Definitions** — every tile ships its definition inline, because a number
  without a definition is not evidence (mission §11).

### Configuration desk — "what is configured, and is it ready?"

Audience: the Course Owner. One `work()` call returns the configuration map:
every configuration domain as a fact section whose values come from the
projected policy rows themselves, with computed readiness on every load.
Configuration readiness is shown here; production readiness is separate and
is never decided here.

- **Academic** — link section onto Academic Setup (programs, levels,
  durations, progression, the D1 assessment reference).
- **Student & Guardian** — the guardian lifecycle policy facts (track 4);
  empty until the Owner enters the terms, with advanced guardian features
  failing closed meanwhile and SEC-GUARDIAN-01 containment unchanged.
- **Reporting & Metrics** — the metric-stewardship policy facts (track 1);
  derived metrics stay refused until a steward and disclosure policy exist.
- **Operations** — the alerting policy facts (track 2) and capacity-objective
  facts (track 3); alert delivery and capacity projections stay refused while
  unconfigured.
- **System Readiness** — the readiness queue across the assessment,
  metric-stewardship, alerting, capacity and guardian domains: each domain
  runs the same command-side validation the guarded commands run, so the desk
  never reports readiness a command would refuse. Faults surface, never hide.
- **Domains not yet implemented** (finance, enrollment lifecycle,
  backup-recovery, security) render as explicitly absent — named, never
  silently missing.

## Guided actions (the cross-role chain, §13)

A queue item's next action is rendered as a button only when the server says
the viewer holds the acting role. The button opens a dialog whose fields are
the endpoint's reviewed signature, pre-filled from the projection, with a fresh
client-generated idempotency key (same behaviour and contract as the command
pages). Submitting calls the same whitelisted, guarded command endpoint — the
desks add context, not authority. Where a dialog can check a server rule
instantly (conditions belong to Conditional outcomes), the client mirrors it
as a courtesy guard so the actor never burns a round trip; the server command
remains the only authority and re-validates everything:

```
Reception (find person) → record_applicant → create_admission
  → review_admission → decide_admission → accept_offer → convert_applicant
  → enroll_in_program → create_student_group / schedule_session
  → record_attendance → issue_tuition_fees / issue_placement_fee
```

## Workspace navigation (declared answer for U8)

- `TH Finance` workspace is gated on `Finance Officer` — the role that does
  daily finance work reaches its DocType links (Fees, Sales Invoice, Payment
  Entry, Fee Structure, etc.) through that workspace.
- `TH Receipts` workspace is gated on the five Auditor roles (Placement,
  Admission, Enrollment, Teaching, Finance Auditor) — it surfaces the
  operation/audit DocTypes for audit review.
- All other operational Officer roles (Placement Author, Publisher, Releaser,
  Invigilator, Admission Officer/Reviewer/Approver, Enrollment Officer,
  Teaching Scheduler, Attendance Recorder, etc.) intentionally land on **no
  workspace**. They reach their work through the role desks (which embed
  guided actions into the existing guarded command Pages) and through the
  command Pages themselves. This is deliberate, not accidental: adding a native
  Workspace for each Officer role would widen native read scopes beyond the
  guarded commands and violate the A13 containment boundary. The declared
  navigation is: desks first, command Pages second, no per-role Workspace.

## What is deliberately NOT here

- No invented teacher identity: the teacher desk exists only because the
  link is native (`Employee.user_id` at erpnext 4048fb70,
  `Instructor.employee` at education 93bc707, mismatch refused by
  `create_teaching_contract`). The earlier "owner decision" blocker is
  superseded by that verification; unlinked logins get an empty state, not
  a guess. Teaching Scheduler and Attendance Recorder keep their qualified
  command pages; the Academic desk carries the assignment/workload facts.
- No alert delivery: conditions name facts; no receiver, severity model,
  risk score or payroll number is invented anywhere in the desk layer.
- No widening of any pinned Page audience: `PAGE_SPEC` command pages are
  untouched, `app_home` is untouched, and the desks are separate Pages whose
  audiences are pinned by the desk contract tests.
- No bypass of the synthetic-only activation boundary or any production gate.
  Production remains REJECT; the desks run wherever the owned app is installed
  and authorized, and they fail closed exactly like the commands they launch.

## Verification

- `tests/desk/` — audience gates, projection field allow-lists, bounded queries,
  lifecycle stage machine, finance vocabulary, page-audience ties, guided
  endpoint signatures against the reviewed Python functions, and a runtime
  smoke that EXECUTES every desk endpoint under the frappe stub (a desk that
  imports but cannot run — the `today()` class of bug — fails here, and the
  wrong-role refusal is proven at runtime, not by source scan).
- `tests/foundation/test_role_desks.cjs` — page/registry/client tie-out,
  escaping under hostile payloads, loading/empty/error transitions, guided
  dialogs against the reviewed endpoint signatures, forbidden primitives.
- `tests/foundation/test_command_pages.cjs` still pins the original 14 surfaces
  unchanged, and `tools/placement/native_checks.py` `PAGE_SPEC` still qualifies
  them; the desks are additive and cannot move those pins.
