# Lifecycle Journey Audit — one learner, governed end to end

Date: 2026-09-19 · Branch: `arena/01a0ba0d-tofel-house-erp` · Harness:
`tools/placement/native_checks.py` (574 checks) · Desks:
`docs/product/ROLE-DESKS.md` (7 desks)

This audit traces a single synthetic learner through every governed stage and
names, per stage, the commands that move it, the native artifacts produced,
the desk surface where each role sees it, and the hosted checks that prove
it. Nothing here invents authority: every claim points at a check, a
command, or a pinned native behavior. The journey fixture chain is
candidate5 → applicant → admission → Student → Program Enrollment →
SYN-GRP-MAIN-1/2 → tuition fee → correction probes.

## 1. Placement — supervised digital assessment, internal release

Commands (`toefl_house.api`): `create_case` → `allocate_attempt` →
`verify_attempt` → `deliver_attempt` → `save_response` → `seal_attempt` →
`score_attempt` → `review_attempt` → `finalize_attempt` →
`release_decision`. The release carries an internal level
(`SYN-LEVEL-GENERAL`), a course code (`SYN-COURSE-GENERAL`), and a
validity window (90 days) — no CEFR label, no TOEFL score, no cutoff.

- Native artifacts: `TH Placement *` ledger rows (case, attempt, manifest,
  exposure, response, score, decision) plus operation receipts and audit
  events. Placement writes no `Student`, no `Student Applicant`
  (`placement-closed-without-student-or-applicant`).
- Desk visibility: Reception funnel/people, Academic admissions queue,
  GM funnel. Every number is a governed ledger count.
- Checks: `alloc-*`, `deliver-*`, `score-*`, `review-*`, `finalize-*`,
  `decision-*`, each with role denials, idempotent replay, rollback
  proofs, transient-recovery and exhaustion bounds, and second-site
  absence.
- Fail-closed boundary: each transition needs its role, its predecessor
  state and its exact version; stale, duplicate, forged or cross-site
  work is refused.

## 2. Admission — thin decision over native applicant/student

Commands (`toefl_house.admission`): `record_applicant` →
`create_admission` → `review_admission` → `decide_admission` (Approved
with reason) → `accept_offer` → `convert_applicant`. Conversion creates
the native `Student` and flips the applicant to Admitted; it creates no
enrollment (`converted['program_enrollment']==0`).

- Native artifacts: `Student Applicant`, `Student`, `TH Admission
  Decision`.
- Desk visibility: Reception people (applicant stage), Academic
  admissions queue, GM funnel. Reception lookup stages read the governed
  class fact, never a flag (`role-desk-hosted-qualification` D4 probes).
- Checks: `admission-*` including withdraw/reject/conditional/expire
  branches, SoD (officer cannot review/decide/convert own work), the
  `deny_enroll_student` containment, and the direct-`Program Enrollment`
  denial.
- Fail-closed boundary: no decision without review; no conversion without
  acceptance; no enrollment from admission at all.

## 3. Enrollment — one native enrollment per converted admission

Command (`toefl_house.enrollment`): `enroll_in_program`. Produces a
submitted `Program Enrollment` with its `Course Enrollment` rows and no
invoice (`enrolled['sales_invoice']==0`).

- Desk visibility: Reception people (Enrolled stage), Academic classes
  intake, GM funnel.
- Checks: `enrollment-*` including duplicate denial, atomic rollback,
  and the officer-holds-no-PE-CRUD parity proof.
- Fail-closed boundary: withdrawn/rejected/expired admissions cannot
  enroll; direct `Program Enrollment` inserts stay denied even for
  Administrator.

## 4. Class — rostered from enrollments, activated explicitly

Commands (`toefl_house.teaching`): `create_student_group` (roster derived
strictly from submitted `Program Enrollment` rows — no manual lists) →
`transition_class` (Planned → Active) → `schedule_session` →
`record_attendance` (roster members, Present/Absent only).

- Native artifacts: `Student Group` (+ `th_class_*` facts, immutable
  after insert except status via transition), `Course Schedule`,
  `Student Attendance` (submitted).
- Desk visibility: Academic classes/sessions (lifecycle stage, schedule
  prefills for Teaching Scheduler holders only), Teacher my-classes and
  today (assigned only), GM funnel.
- Checks: `teaching-*` (capacity/name/year/duration/roster denials,
  state machine, attendance batch rules), `teaching-retired-skill-runtime-policy`
  (history preserved, new work refused, retirement one-way).
- Fail-closed boundary: no duration policy, no class; no Active status,
  no sessions; no roster membership, no attendance mark.

## 5. Teaching work — assignments in, assigned-only desks out

Commands (`toefl_house.teaching.compensation`): `create_teaching_contract`
(finance side; instructor↔employee integrity, active-employee rule) →
`assign_teaching_skill` (scheduler side; one instructor per skill area per
class window; contract must belong to the instructor and be assignable) →
`end_teaching_assignment` (end date recorded once).

- Desk visibility: the Teacher desk (`toefl_house.desk.teacher.work`):
  my classes, today, sessions/attendance, students (roster only),
  academic work (recorded scores, no thresholds — grading is owner
  decision D1), compensation facts (contract identity/window; pay runs
  through native payroll, the desk calculates nothing).
- Checks: `teaching-compensation-contract-authority`,
  `teaching-assignment-facts`, `teaching-compensation-calculation`
  (pre-revision rates, one-off payable basis D12, no double-pay),
  `role-desk-teacher-hosted` (assigned-only classes/rosters,
  off-roster exclusion, no-money key pin, unlinked empty state),
  `desk-broad-isolation-matrix` (desk scope vs user-permission scope).
- Fail-closed boundary: identity resolves through the native chain only
  (`User` → `Employee.user_id` → `Instructor.employee` → assignment);
  an unlinked Instructor login sees an empty state naming the missing
  link, never another teacher's classes.

## 6. Billing and corrections — net receivables, native money only

Commands (`toefl_house.finance`): `issue_tuition_fees` (OD-CP G1: one
discount winner per line by precedence with deterministic tie-break;
retired and non-matching rules ignored; the fee bills the NET amount
because native `Fees.calculate_total()` sums components) →
`request_fees_correction` / `approve_fees_correction` /
`deny_fees_correction` (full-amount only until owner terms exist; the
approval re-validates total, window and submitted state, then reverses
via native cancellation).

- Native artifacts: `Fees` (submitted, GL equals receivable),
  `Payment Entry` collections, cancelled-fee reversals, `TH Correction
  Request` rows. No TH refund/override/partial/branch-fee doctype exists
  (`odcp-legacy-vocabulary-absent`); submitted fees are not invoice-
  correction targets (`odcp-refund-surface-absent`).
- Desk visibility: Finance billing/corrections/outstanding (native
  invoice states, policy-blocked requests named with the evidence),
  GM exceptions (pending corrections), Owner attention.
- Checks: `odcp-*`, `finance-correction-*`, `finance-write-containment`,
  and the D6 end-to-end fees-correction chain inside
  `role-desk-hosted-qualification` (HTTP request → desk row naming the
  fee → HTTP approval → native reversal → desk reads decided).
- Fail-closed boundary: partial amounts refused; stale approvals
  (changed total, closed window, unsubmitted fee) refused with the fee
  untouched; denials post nothing and reopen the door.

## 7. Oversight — posture, health, configuration

- GM desk: funnel, exceptions, recent recorded actions (existing audit
  receipts, not a second log), role coverage, system health, desk links.
- Owner cockpit: everything the GM sees (counts), plus governance
  attention (fail-closed release facts), release posture (REJECT), and
  definitions on every tile.
- Academic Setup: configuration health, programs, levels with governing
  durations (actor + reason stated), progression, fee plans, fee types,
  discount rules (Policy A), academic years with per-year coverage, and
  the grading placeholder (D1 undecided — no grading rules anywhere).
- System health (new in §6): native ping, unseen error rows, failed
  background jobs, observed workers with verbatim states, stopped
  schedules, failed scheduled runs, plus generated alert conditions.
  Conditions are generated, never delivered: no receiver exists
  (`toefl_house/observability.py`, RECEIVER BOUNDARY). Tracebacks and
  error text stay on the native forms.
- Checks: `role-desk-hosted-qualification` (all seven desks over HTTP,
  audience/negative/guest cells, plain-language scan, registry),
  `role-desk-observability-hosted` (Administrator refusal, key-set pin,
  owner/GM count equality).

## 8. Isolation envelope — who can see the journey, on which surface

Proven by `desk-broad-isolation-matrix` (two branches, two students,
eight logins) together with the pre-existing R2/R3/A13 proofs:

| Surface | Allow (proven) | Deny (proven) | Enforcement layer |
|---|---|---|---|
| Desk RPC (7 desks × 8 logins) | each audience 200 | cross-audience, outsider, guest | `require_desk_audience` + enabled-user check; Administrator refused |
| Native list | branch-A class for a UP-scoped Instructor | branch-B class (incl. backfilled fixtures) hidden | role read × user permissions (`get_list`/`DatabaseQuery`) |
| Desk projection | assigned classes incl. the far-branch one | off-roster learners, other teachers' classes | audience + assignment join; ignores user permissions (asserted); identity resolves scope-exempt |
| REST doc read | own-branch class 200 | cross-branch, outsider, guest | native doc + user permissions |
| Export | finance CSV of Fees 200 | outsider (no read); Instructor on classes (no export bit) | `DatabaseQuery` then `can_export` (frappe@988e54f) |
| Print | — (no product print path) | outsider `download_pdf` denied | native print permission |
| Report | finance roles run the registers | non-audience roles denied | Report role table + ref-doctype report perm |
| File | auditor reads parent-gated attachment | non-members denied | parent-document access (R3, pre-existing) |

Three boundaries are asserted, not hidden:

1. The desk path (`frappe.get_all`, elevated) does not honor branch
   user-permissions. Branch scoping lives on the native surfaces;
   desk scope is audience/assignment. The matrix pins both halves:
   `get_list` returns `{SYN-GRP-ISOL-A}` while `get_all` returns all
   four groups and the desk still shows the far-branch assigned class.
2. The `Student` master has no branch dimension, so the native student
   list stays role-wide for Instructor (both matrix students plus the
   off-roster probe are listed). Per-student isolation is desk-level:
   the teacher desk shows assigned rosters only, and the off-roster
   learner is excluded there.
3. Native non-strict user-permissions keep branchless rows visible
   (pinned `frappe@988e54f` empty-link skip). The matrix proves the
   shape first (branchless fixtures listed, far-branch class excluded)
   then moves the branchless fixtures to the far branch, so the exact
   cell runs between two populated branches on the default mode.

## Steps — the 18 governed moves

Each step names its source of truth, actor, permission gate, record,
next step, failure mode, and proving checks. Actors are the
`security.KIND_ROLES` command roles; desk reads gate on
`require_desk_audience`. Check names are the hosted families from the
stages above (all green in the 574-check run).

**Step 1 — Open the placement case and allocate the attempt**
(`create_case`, `allocate_attempt`).
Truth: `TH Placement Case` + attempt ledger. Actor: Placement
Publisher. Permission: publisher command role. Record: case, attempt,
manifest rows. Next: step 2. Failure: duplicate/replayed allocation
replays idempotently without duplicate audit rows. Audit: `alloc-*`.

**Step 2 — Verify and deliver the attempt**
(`verify_attempt`, `deliver_attempt`).
Truth: attempt ledger state. Actor: Placement Invigilator.
Permission: invigilator command role. Record: verification + exposure
rows. Next: step 3. Failure: wrong-state or cross-site delivery
refused. Audit: `deliver-*`.

**Step 3 — Capture responses, seal, and score**
(`save_response`, `seal_attempt`, `score_attempt`).
Truth: response rows, then the score row. Actor: Placement
Invigilator (capture/seal), Placement Assessor (score). Permission:
respective command roles. Record: responses, seal receipt, score.
Next: step 4. Failure: post-seal edits refused; assessor-only scoring.
Audit: `score-*` plus key-history preservation.

**Step 4 — Review, finalize, and release the decision**
(`review_attempt`, `finalize_attempt`, `release_decision`).
Truth: review + decision rows. Actor: Placement Reviewer
(review/finalize), Placement Releaser (release). Permission:
respective command roles. Record: internal level + course code +
validity window (no CEFR, no TOEFL score). Next: step 5. Failure:
self-review/self-publish denied despite role union; stale versions
refused. Audit: `review-*`, `finalize-*`, `decision-*`.

**Step 5 — Record the applicant** (`record_applicant`).
Truth: `Student Applicant`. Actor: Admission Officer. Permission:
officer command role. Record: applicant row linked to the placement
decision. Next: step 6. Failure: live-decision reuse and duplicates
refused. Audit: `admission-*`.

**Step 6 — Create and review the admission**
(`create_admission`, `review_admission`).
Truth: `TH Admission Decision` (review state). Actor: Admission
Officer (create), Admission Reviewer (review). Permission: respective
command roles. Record: admission + review rows. Next: step 7.
Failure: the officer cannot review their own work (SoD). Audit:
`admission-*` review/withdraw branches.

**Step 7 — Decide and accept the offer**
(`decide_admission`, `accept_offer`).
Truth: `TH Admission Decision` (Approved with reason). Actor:
Admission Approver (decide), Admission Officer (accept). Permission:
respective command roles. Record: decision + acceptance rows. Next:
step 8. Failure: no decision without review; reject/conditional/expire
branches stay terminal. Audit: `admission-*` decision branches.

**Step 8 — Convert the applicant to a student**
(`convert_applicant`).
Truth: `Student` + admitted applicant. Actor: Admission Approver.
Permission: approver command role. Record: `Student`; applicant
flipped to Admitted; `program_enrollment==0`. Next: step 9. Failure:
conversion without acceptance refused; no enrollment is created here.
Audit: `admission-*` conversion proofs.

**Step 9 — Enroll in the program** (`enroll_in_program`).
Truth: submitted `Program Enrollment` + `Course Enrollment` rows.
Actor: Enrollment Officer. Permission: officer command role. Record:
enrollment; `sales_invoice==0`. Next: step 10. Failure: withdrawn /
rejected / expired admissions cannot enroll; direct inserts denied
even for Administrator. Audit: `enrollment-*`.

**Step 10 — Create the class** (`create_student_group`).
Truth: `Student Group` with `th_class_*` facts. Actor: Teaching
Scheduler. Permission: scheduler command role. Record: the group;
roster derived strictly from submitted enrollments. Next: step 11.
Failure: no duration policy, no class; capacity/name/year/roster
denials. Audit: `teaching-*` group cells.

**Step 11 — Activate the class and schedule sessions**
(`transition_class`, `schedule_session`).
Truth: class status + `Course Schedule` rows. Actor: Teaching
Scheduler. Permission: scheduler command role. Record: Active status,
scheduled sessions. Next: step 12. Failure: sessions require Active
status; retired skills refuse new work one-way. Audit: `teaching-*`
state machine, `teaching-retired-skill-runtime-policy`.

**Step 12 — Mark attendance** (`record_attendance`).
Truth: submitted `Student Attendance`. Actor: Attendance Recorder.
Permission: recorder command role. Record: Present/Absent marks for
roster members only. Next: step 13. Failure: off-roster marks and
non-batch statuses refused. Audit: `teaching-*` attendance cells.

**Step 13 — Contract the instructor and assign the skill**
(`create_teaching_contract`, `assign_teaching_skill`).
Truth: `TH Instructor Contract` + `TH Teaching Assignment`. Actor:
Finance Officer (contract), Teaching Scheduler (assignment).
Permission: respective command roles. Record: contract (active
employee, instructor↔employee integrity) + assignment (one instructor
per skill area per class window). Next: step 14. Failure: assignable
/ belonging / window violations refused. Audit:
`teaching-compensation-contract-authority`, `teaching-assignment-facts`.

**Step 14 — Teach from the assigned-only desk**
(`toefl_house.desk.teacher.work`; `end_teaching_assignment` closes).
Truth: assignment rows joined to groups/schedules/roster/scores.
Actor: Instructor (reads), Teaching Scheduler (end date).
Permission: Instructor desk audience; scheduler command role. Record:
no new writes except the once-recorded end date; compensation stays
facts-only (native payroll calculates). Next: step 15. Failure:
unlinked logins see the named empty state, never another teacher's
classes; the end date records once. Audit: `role-desk-teacher-hosted`,
`teaching-compensation-calculation`.

**Step 15 — Bill the net tuition** (`issue_tuition_fees`).
Truth: submitted `Fees` (GL equals receivable). Actor: Finance
Officer. Permission: officer command role + OD-CP G1 discount
precedence. Record: the fee net of the single winning discount per
line. Next: step 16. Failure: retired/non-matching rules ignored;
legacy refund vocabulary absent. Audit: `odcp-*`,
`odcp-legacy-vocabulary-absent`.

**Step 16 — Correct the fee in full or not at all**
(`request_fees_correction`, `approve_fees_correction`,
`deny_fees_correction`).
Truth: `TH Correction Request` + native reversal. Actor: Finance
Officer (request/approve/deny) with the policy approver role as dual
key. Permission: officer command role + in-command approver check.
Record: full-amount reversal via native cancellation; denials post
nothing and reopen the door. Next: step 17. Failure: partial amounts
refused; stale approvals (changed total, closed window, unsubmitted
fee) refused with the fee untouched. Audit: `finance-correction-*`,
`finance-write-containment`, the D6 desk-chain cells.

**Step 17 — Oversee funnel, health, and configuration**
(GM desk, Owner cockpit, Academic Setup reads).
Truth: governed ledger counts + native scheduler/configuration rows.
Actor: General Manager, Course Owner. Permission: desk audiences;
Administrator refused on product desks. Record: no writes — funnel,
exceptions, health counts, posture (REJECT), years/durations/discounts,
grading-D1 placeholder. Next: step 18. Failure: RQ reads denied to
non-readers surface `Not readable`, never zero; conditions generate,
never deliver. Audit: `role-desk-hosted-qualification`,
`role-desk-observability-hosted`.

**Step 18 — Prove the isolation envelope on every surface**
(`desk-broad-isolation-matrix` + R2/R3/A13).
Truth: the enforcement layers themselves (audience gates, role ×
user permissions, export bit, print perm, report roles, parent-gated
files). Actor: all matrix logins (two branches, two students, eight
logins). Permission: each surface's native gate. Record: the matrix
observation (allow/deny per surface). Next: none — the journey
closes. Failure: any cross-surface leak fails the run; the three
honest boundaries stay asserted, not hidden. Audit:
`desk-broad-isolation-matrix`.

## Verdict

The journey is closed: every stage moves only through its governed
commands, every artifact is native or a command-created receipt, every
role sees its slice through an audience-gated desk or a natively
permitted surface, and every refusal is proven on the hosted bench. No
parallel master, ledger, workflow, permission model, alert receiver, or
grading rule was introduced to make the journey readable. The 18 steps
above carry the per-step facets; the hosted click-through on a live
deployment remains future work owned by `launch-rehearsal`, since no
deployment exists to click through.
