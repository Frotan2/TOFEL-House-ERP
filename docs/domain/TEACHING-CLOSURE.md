# Teaching Operations (Scheduling & Attendance) — CLOSED / QUALIFIED (synthetic isolated build)

Date: 2026-09-15 · Session branch: `arena/01a0a496-tofel-house-erp`
· Qualifying product commit: `6ba56633ddbfbee5baa6c1ece19e1524ba42a80b`
(slice `0e83c62` + hosted-failure fixes `99d9d46` wizard-equivalent
Warehouse Type fixture, `bcee14b` Teaching Auditor receipt DocPerm,
`6ba5663` race-check fixture correction)
· Enrollment predecessor: [ENROLLMENT-CLOSURE.md](ENROLLMENT-CLOSURE.md) (CLOSED / QUALIFIED, `756614e`, hosted run `34946981784`). Enrollment was not reopened.
· Admission predecessor: [ADMISSION-CLOSURE.md](ADMISSION-CLOSURE.md) (CLOSED / QUALIFIED, `4da6f1b`, hosted run `34941341845`). Admission was not reopened.
· Placement predecessor: [PLACEMENT-CLOSURE.md](PLACEMENT-CLOSURE.md) (CLOSED / QUALIFIED, `4571e6c`, hosted run `34932512626`). Placement was not reopened.

**Status: CLOSED / QUALIFIED — bounded thin Teaching Operations slice implemented and
qualified on the hosted synthetic runner (see Evidence). Synthetic-data implementation
only, authorized for the bounded isolated build. Production remains REJECT. Do not
deploy. Do not reopen Placement, Admission or Enrollment. Do not start the next
domain. No academic grading, fees or payroll values are invented.**

This records the **thin Teaching Operations slice** (bounded part of plan P3.5):
**submitted native Program Enrollment → native Student Group roster → native Course
Schedule sessions → submitted native Student Attendance records.** No TH roster,
timetable, attendance ledger, grading, invoice or payroll record exists. Assessment
Plan/Result, progression, fees, payroll, transfers and same-term repeats remain later
authorities with unchanged gates (B04/B05, B07, A09, A05/A11).

## 0. Why this domain was selected next

The capability-map dependency graph after a closed Enrollment points to
`[NATIVE] Student Group / Course Schedule / Attendance / Assessment Result`, then
HR/payroll. The candidates were ranked by gate state, not preference:

| Candidate | Verdict |
|---|---|
| **Scheduling & Attendance (selected)** | The capability map classifies Batches/Scheduling and Attendance as **NATIVE** with no custom code. It requires **zero uninvented business values**: roster semantics, Present/Absent/Leave statuses, calendar windows and instructor/room/group overlap are all pinned-native. It is the first capability that turns an enrollment ledger into an operating school (classes, sessions, participation evidence). |
| Finance / tuition invoicing (P3.6) | Blocked by **B07**: the contract requires a real finance policy (legal entity, jurisdiction, currency/tax/fiscal rules, prices, refund terms) that must not be invented. The Enrollment closure explicitly deferred it. A08 stays DECIDED for a later slice. |
| Academic assessment / progression | Gated by **B04/B05** (native grading, weights, pass/completion, correction rules must be approved before implementation). Recording arbitrary grades would invent academic policy. |
| Workforce / payroll (P3.7) | **A09 BLOCKED** until pay basis and exactly one native input path are proven. |

Treatment follows the map exactly: **native authorities, thin owned containment**.
This slice adds **no new DocType** — the strongest possible evidence that the
reuse-the-foundation strategy still holds (§8 of the capability map).

## 1. What was implemented

- **Authorities (all native, pinned Education v16.1.0, source-reviewed at
  `93bc707`):** **Student Group** (roster, capacity, duplicate-student rules),
  **Course Schedule** (session; native academic-calendar window and
  group/instructor/room/Assessment-Plan overlap validation), **Student Attendance**
  (submitted participation record; native roster-membership, duplication and
  holiday-list validation). Instructor and Room are native catalog documents.
- **Commands (owned, thin):**
  - `toefl_house.teaching.create_student_group` (**Teaching Scheduler**). The roster
    is derived **only** from submitted native Program Enrollments via the native
    `get_program_enrollment` query — no manual student lists are accepted, so an
    unenrolled learner cannot enter a class. Declared capacity is required
    (engineering bound 1–500; native `max_strength` remains the enforcing authority).
    Group names are explicit `SYN-` synthetic fixtures.
  - `toefl_house.teaching.schedule_session` (**Teaching Scheduler**). Creates a
    native Course Schedule inside a rostered group. Additional thin integrity:
    the course must belong to the group's program catalog (native Program Course
    rows) and a **Left** instructor cannot be scheduled (native `Instructor.status`).
    Group, instructor and room rows are locked **before** the native overlap checks
    so concurrent scheduling serializes (read-then-insert is not a concurrency
    proof). Native validation stays authoritative for the calendar window and all
    overlap dimensions.
  - `toefl_house.teaching.record_attendance` (**Attendance Recorder**). Creates
    **submitted** native Student Attendance documents for one scheduled session.
    Only the native Select statuses **Present/Absent/Leave** are accepted; missing
    students are never defaulted. Roster membership is enforced; the session row is
    locked and existing records are checked **under lock**, so concurrent marking
    cannot double-record (native duplication check remains the backstop).
- **Containment (A13 pattern, unchanged architecture):** deny-by-default `validate`
  hooks on Student Group, Course Schedule and Student Attendance confine every write
  — including direct `ignore_permissions` inserts and Administrator writes — to the
  matching authorized teaching command. The three roles hold **no native CRUD
  permissions** on any Education doctype; HTTP direct CRUD is denied by native
  permissions. Idempotency, receipts and audit reuse the qualified
  `TH Placement Operation` / `TH Placement Audit Event` machinery unchanged.
- **Honest native side effects kept:** the roster read inside
  `record_attendance` patches only the module-level `get_student_group_students`
  reference for the duration of the command (that native helper enforces a Desk
  read permission the Recorder must not hold). No session switching, no
  `frappe.has_permission` relaxation. The committing native bulk path
  (`education.api.mark_attendance`, S8) is **not used**; the command path performs
  no internal commit, and true single-transaction rollback is proven at runtime.

## 2. Native / custom boundary

| Authority | Owner |
|---|---|
| Registration ledger | Education **Program Enrollment** (closed Enrollment slice) |
| **Class roster** | Education **Student Group** |
| **Class session** | Education **Course Schedule** |
| **Participation record** | Education **Student Attendance** (submitted) |
| Instructor / Room / Course / Program / Academic Year | Education catalog (native) |
| Operation receipts / audit | `TH Placement Operation` / `TH Placement Audit Event` (reused; no new DocType) |
| Assessment / grading / progression | Native — **not this slice** (B04/B05) |
| Invoice / payment / GL / payroll | Native — **not this slice** (B07 / A09) |

**Student Attendance is not Employee Attendance.** The slice writes no HRMS
Attendance, Timesheet, Additional Salary, Salary Slip or Employee record, and the
hosted suite asserts those tables are unchanged.

## 3. Files

| File | Change |
|---|---|
| `apps/toefl_house/toefl_house/teaching/__init__.py` | `create_student_group`, `schedule_session`, `record_attendance`; three deny-by-default guards; scoped roster-read wrapper |
| `apps/toefl_house/toefl_house/policy.py` | Pure validators (`validate_group_name`, `validate_capacity`, `validate_schedule_date`, `validate_session_window`, `validate_attendance_statuses`); Teaching Auditor receipt read |
| `apps/toefl_house/toefl_house/security.py` | KIND_ROLES for the three commands; `teaching_command_active` context gate |
| `apps/toefl_house/toefl_house/hooks.py` / `permissions.py` / `fixtures/role.json` | doc_events guards; Teaching Auditor on operation/audit reads; Teaching Scheduler / Attendance Recorder / Teaching Auditor roles |
| `tests/teaching/test_policy.py` | Local pure validator, read-boundary, guard-wiring and scoping checks |
| `tools/placement/native_checks.py` | 58 new native checks; retained Placement/Admission/Enrollment checks unchanged |
| `.github/workflows/placement-content.yml`, `tools/placement/run_native.py`, `tools/foundation/runner_probe.py`, `tools/foundation/publish_evidence.py` | Session branch lock moved to `arena/01a0a496-tofel-house-erp`; `tests/teaching` discovery |

## 4. Evidence

<!-- Filled from actual execution output only; no inferred or relabeled results. -->

- Local pure unit tests, executed in the session workspace on 2026-09-15
  (re-executed at the qualifying commit `6ba5663`; not native Frappe
  qualification):
  - `python3 -m unittest discover -s tests/placement -v`: **147/147 OK**
  - `python3 -m unittest discover -s tests/admission -v`: **6/6 OK**
  - `python3 -m unittest discover -s tests/enrollment -v`: **10/10 OK**
  - `python3 -m unittest discover -s tests/teaching -v`: **17/17 OK**
  - `python3 -m unittest discover -s tests/foundation -v`: **44/44 OK**
- Hosted iteration record (actual runner output; nothing relabeled):
  - Run `34960645081` (commit `0e83c62`): **FAIL** —
    `teaching-native-catalog` `LinkValidationError: Could not find
    Warehouse Type: Transit` (ERPNext company default-warehouse creation
    links a setup-wizard-seeded record absent on wizard-less sites). All
    **293** prior recorded checks passed, including the complete retained
    Placement/Admission/Enrollment suites. Fixed in `99d9d46` by creating
    the identical record from ERPNext's own `install_fixtures`.
  - Run `34962443905` (commit `99d9d46`): **FAIL** —
    `teaching-role-and-list-parity` `PermissionError` on
    `frappe.get_list('TH Placement Operation')`; the conjunctive permission
    model also requires a DocPerm read row for Teaching Auditor on the
    shared receipt/audit ledger. **331/332** recorded checks passed. Fixed
    in `bcee14b`.
  - Run `34965424648` (commit `bcee14b`): **FAIL** —
    `http-teaching-concurrent-attendance-duplicate-cas` observed `[417,417]`:
    the race was aimed at the session the positive check had already fully
    marked, so both racers failed closed correctly — a check-fixture design
    error, not a product defect (product code unchanged). **467/468**
    recorded checks passed. Fixed in `6ba5663` by racing on a fresh
    unmarked session.
  - Final qualification run: **`.github/workflows/placement-content.yml` run
    `34966681820`** (commit `6ba56633ddbfbee5baa6c1ece19e1524ba42a80b` on
    `arena/01a0a496-tofel-house-erp`): **PASSED**.
    - Check-run JSON: `Placement native checks` conclusion `success`
      (id `104375330970`); `Placement runner result` conclusion `success`
      (id `104375334073`); workflow job `content` conclusion `success`
      (id `104372690730`). Head SHA matches the product commit.
    - Pinned runner probe, pinned installs, both synthetic site installations
      and migrations: **all 86 runner steps exit 0** (`runtime_complete:
      true`, `production: REJECT`; runner report SHA-256
      `083f2964b2e9e7248dda91a73230232efd69a41094250ad44d53d04ee3608d1c`).
      `native-acceptance` exit 0, 25.052 s.
    - Native qualification: **483/483 checks pass** (`runtime_kind`
      Frappe/MariaDB/Redis/HTTP; `status: pass`; `failure: null`); 58
      teaching checks executed. Placement increments 1–7, Placement closure,
      Admission and Enrollment remain green. Native report SHA-256
      `35ec07187dbff912273fefd33a3f1f9e17ee8a69feff31549100809b0c5d6b66`.
    - Unique literal `check(` names in `tools/placement/native_checks.py`
      are **481**; hosted **483** includes the two fixture-site checks.
    Placement remains independently qualified by run `34932512626`
    (332/332, commit `4571e6c`). Admission remains independently qualified
    by run `34941341845` (397/397, commit `4da6f1b`). Enrollment remains
    independently qualified by run `34946981784` (425/425, commit `756614e`).

Production remains **REJECT**.

## 5. Limitations and deferred (do not implement in this close)

- Assessment Plan/Result, grading, progression and correction workflows (B04/B05
  business gates; `no-academic-finance-payroll-writes` asserts zero writes)
- Tuition invoicing/payments/refunds (A08 route decided; B07 values not invented)
- HR/payroll and any teaching-pay path (A09 BLOCKED)
- Transfers, group moves, same-term repeats and cancel/amend history (A05/A11
  BLOCKED); Student Attendance amend/cancel is not an activated path in this slice
- Course-based (rather than program-intake-based) Student Grouping, Student Leave
  Application, Course Scheduling Tool bulk generation, calendar UI and reminders
- Student/guardian portal visibility of schedules (portal DEFERRED)
- Real instructor↔Employee linkage stays native configuration; no Employee is
  created by this slice

**Do not start the next domain.** Teaching Operations (Scheduling & Attendance) is
CLOSED / QUALIFIED. Stop. Production remains REJECT. Do not deploy.
