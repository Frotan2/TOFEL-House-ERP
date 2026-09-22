# S4 Lifecycle Design Brief (options only — no owner answer invented)

Status: SCOPED ONLY. Nothing below is implemented. Each item names the gap, the
decision the owner must make, and the engineering options once answered. Verdict
stays NOT READY; production stays REJECT/BLOCKED.

## GAP-REENROLL (critical) → OD-NEW-01

Fact: applicant email is globally unique forever; returning paths are denied at
`enrollment_is_eligible`, `convert_applicant`, and `record_applicant`. A student
continuing to the next level/term has no path except a second email identity.

- Option A — returning admission lane: new commands `record_returning_applicant`
  (binds existing Student, no placement required) + `enroll_continuation`
  (new Program Enrollment for the existing student, same SoD lattice).
- Option B — placement-per-term: returning students re-sit placement; relax the
  email rule to one ACTIVE applicant per subject instead of one ever.
- Owner decides: identity rule (A, B, or hybrid) and whether continuation needs
  a new admission decision or a lighter enrollment-only act.
- SHIPPED AS S7 2026-09-22 (HOSTED-PROVEN pending at write time): option B
  with a native-forced pivot — pinned native Student Applicant email is
  UNIQUE, so "one active applicant" is impossible; instead the returning
  journey REUSES the one applicant row and the new decision is the
  per-journey vehicle (open = active + unconverted). Convert links the
  existing Student/Customer. Option A (placement-free lane) deferred.
  Fix 2026-09-22 (hosted run 35775071986): the duplicate-Student guard
  runs on the first-time lane only (the linked Student pre-exists by
  construction on the returning lane), and the returning journey
  enrolls into the NEXT term — same-intake double enrollment stays
  refused by both convert and enroll_in_program.

## GAP-CONDITIONAL → OD-NEW-02

Fact: Conditional decisions can never convert and have no onward transition.

- Option A — satisfaction command: `satisfy_conditions` (evidence note +
  authority) moves Conditional → Approved, then the normal accept/convert path.
- Option B — direct conditional conversion: convert accepts Conditional with
  recorded acceptance of the conditions.
- Owner decides: who may declare conditions met, and what evidence is required.

## GAP-ROSTER → OD-NEW-05

Fact: the class roster freezes at `create_student_group`; late joiners, transfers,
and section splits are impossible.

- Option A — roster commands: `add_class_member` / `move_class_member` with
  capacity + eligibility checks, each a receipted command on Student Group Student.
- Option B — re-creation flow: close and re-create the class (loses session
  continuity; likely wrong for attendance history).
- Owner decides: who authorizes mid-term roster changes and the cutoff rules.
- SHIPPED AS S8 2026-09-22 (HOSTED-PROVEN pending at write time): option A
  with the cutoff as an effective-dated owner mechanism (TH Roster Change
  Policy: single `changes_allowed_until` facet, fail-closed unconfigured,
  retire = off-switch). Teaching Scheduler executes; moves deactivate the
  source row (native counts every row toward max_strength); eligibility
  mirrors intake (submitted enrollment for the target program/year/term).

## GAP-ATT-CORRECT → OD-NEW-06

Fact: submitted Student Attendance has no correction path; errors are permanent.

- Option A — correction command mirroring D3: request/approve with reason, window,
  and audit event; native record amended through the command context.
- Option B — same-day recorder edit: narrow window, no approval.
- Owner decides: authority, window, and whether history must show both marks.
- SHIPPED AS S9 2026-09-22 (HOSTED-PROVEN pending at write time): option A
  as a D3-shaped request/approve/deny flow (TH Attendance Correction
  Policy with approver-role + window-days terms; requests value-pin the
  governing terms). Approval voids the erroneous mark and submits a
  replacement for the same student/session, so history shows both marks
  by construction; no mark is ever rewritten in place.

## GAP-EXIT → OD-NEW-07

Fact: no unenroll/withdraw/expel path; no post-conversion revocation.

- Option A — exit command family: `withdraw_enrollment` (student-initiated, date,
  reason) + `dismiss_enrollment` (authority + approval), each defining the
  receivable consequence by referencing (not re-implementing) native documents.
- Owner decides: exit categories, authorities, and financial consequences
  (forfeit vs prorate vs refund — amounts stay native config, but the POLICY is
  the owner's).

## GAP-CATALOG-LINKAGE → possible OD-NEW-09

Fact: operations run on native programs and never consult the TH academic catalog;
retiring a TH level changes nothing operationally.

- Option A — catalog governs: enrollment/billing resolve the TH level and refuse
  retired/unknown mappings.
- Option B — catalog stays advisory: Owner maintains both planes; no enforcement.
- Needs an owner/architecture answer on the catalog's authority before slicing.

## GAP-DATES / GAP-FEE-TIMING → OD-NEW-03 / OD-NEW-04

Billing-date bounds and placement-fee timing are pure policy inputs. Engineering
needs only the answer; implementation is validators + tests (small slice).

## GAP-ACADEMIC-IDEMPOTENCY (not owner-gated)

Academic control-plane commands validate request keys but keep no receipts, so a
retried call errors instead of replaying. Later engineering slice: route academic
commands through receipt semantics (new kinds in KIND_ROLES + op/audit writes).
Sequenced after S4 decisions, or alongside if capacity allows — no owner input needed.

## Sequencing rule

No S4 implementation starts until its OD answer is recorded in DECISION-REGISTER.md.
GAP-REENROLL is first (it blocks real term-over-term operation); the rest follow in
OD-answer order.
