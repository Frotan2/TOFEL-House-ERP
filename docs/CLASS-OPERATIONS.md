# Class operations — the operator runbook

How a class is configured, scheduled, filled, moved, paused and closed with the
Mission 3 commands. Everything here writes native ERPNext Education facts
(`Student Group`, `Student Group Student`, `Course Schedule`,
`Student Attendance`, `Program Enrollment`, `Fees`) or one TOEFL House
operational record that points at them. There is no second roster, student
master or ledger.

Every command is a `POST` with a `request_key` first argument, is idempotent for
that key, and either completes or writes nothing. A refusal is a sentence you
can read to a parent, and the same call can be retried with the corrected value.

## Who can do what

| Role | Commands |
| --- | --- |
| **Course Owner** | the configuration carriers: `TH Class Operations Policy` versions/status, `TH Academic Calendar` days, `TH Timetable Template` slots. Course Owner is the only writer; the write is receipted in the configuration audit chain. |
| **Teaching Scheduler** | `generate_timetable`, `schedule_session`, `postpone_session`, `schedule_replacement_session`, `cancel_session`, `suspend_class`, `suspend_student_membership`, `resume_suspension`, `offer_waiting_list_seat`, `admit_from_waiting_list`, `request_class_transfer`, `cancel_class_transfer`, `add_class_member`, `move_class_member`, `remove_class_member`, `transition_class` |
| **Academic Manager** | `create_capacity_override`, `revoke_capacity_override`, `approve_class_transfer`, `deny_class_transfer` |
| **Reception** | `join_waiting_list`, `leave_waiting_list`, and the seat/queue reads below |
| **Attendance Recorder** | `record_attendance` and the correction requests |
| **Teaching Auditor** | read-only: the operational records and the seat/queue projections |

Roles the governing policy pins (replacement approver, override approver,
transfer approver) are a **second key**: holding the role above is not enough
if the effective policy names a different approver role, and the policy role
holder cannot act without the command role.

## 1. Configure the term (Course Owner)

```python
class_operations.create_class_operations_policy(request_key, code, title, description="")
class_operations.set_class_operations_policy_version(
    request_key, policy, effective_from, reason, terms)   # all 28 terms, no defaults
class_operations.set_class_operations_policy_status(request_key, policy, active)
```

`terms` carries every rule explicitly: teaching days, session minutes
(default/min/max), sessions per day, timetable horizon, postpone/cancel/
replacement switches and their roles/windows, suspension limits, waiting-list
switches and offer validity, member removal, capacity override role/seats/
expiry, transfer switches (class/time vs program/branch), transfer approver and
window, and direct roster moves. A version is effective-dated, immutable and
refuses backdated or same-day changes; the latest validated version governs
today and `governing_operations()` is the only resolver.

Then the two operational carriers:

```python
calendars.create_academic_calendar(request_key, code, title, academic_year="", branch="", description="")
calendars.add_academic_calendar_day(request_key, calendar, day, kind, description="")   # Holiday / Closed / Working Day
timetables.create_timetable_template(request_key, code, title, program="", branch="", delivery_mode="On-site")
timetables.set_timetable_slots(request_key, template, slots, reason)                    # replaces the whole pattern
```

A calendar row with no year/branch is global; a branch row beats it; on the same
date an explicit `Working Day` beats `Closed`, which beats `Holiday`. With no
calendar at all nothing is blocked here — the policy's teaching days still apply.

**Until an active policy version exists**, every policy-gated command refuses
with `NOT CONFIGURED` language. That is deliberate: there is no built-in default
capacity, session length or transfer rule.

## 2. Schedule sessions (Teaching Scheduler)

```python
scheduling.generate_timetable(request_key, student_group, template, start_date, end_date)
teaching.schedule_session(request_key, student_group, schedule_date, from_time, to_time, instructor, room, course)
```

`generate_timetable` materialises the template inside the policy horizon and
returns the sessions plus `skipped_calendar_days`. Both paths run the same
server-side gate, in this order, before anything is written:

1. date and window shape (ISO date; `HH:MM`/`HH:MM:SS`; start < end);
2. the class is **Active**;
3. the date is inside the class start/end window;
4. the session length and the daily session cap;
5. the academic calendar and the configured teaching days;
6. the course is part of the class's program catalog;
7. instructor, room and class overlap, and student double-booking;
8. the room seats at least the class capacity.

Times are compared as wall-clock values regardless of whether the driver hands
back `datetime.timedelta`, `datetime.time` or text — a stored session and a new
session are always compared on the same footing.

Postpone, make up, cancel (each keeps the original row):

```python
scheduling.postpone_session(request_key, course_schedule, reason, new_date,
                            from_time="", to_time="", room="", instructor="")
scheduling.schedule_replacement_session(request_key, course_schedule, reason,
                                        schedule_date, from_time, to_time, room="", instructor="")
scheduling.cancel_session(request_key, course_schedule, reason)
```

The original becomes `Postponed` (or `Cancelled`) with the operator's note; the
replacement is a new `Replacement` row whose `th_replaces` points back. A
session that already carries attendance is never postponed or cancelled — the
session happened; correct the record instead.

## 3. Fill a class, and answer "is there room?"

```python
teaching.add_class_member(request_key, student_group, student, override=None)
teaching.remove_class_member(request_key, student_group, student, reason)
teaching.move_class_member(request_key, student_group, student, to_group)
```

A free seat means `max_strength − every roster row − unexpired waiting offers`.
Deactivated roster rows still count (they are history, not capacity), so
`available` is what a walk-in can actually take. A full class refuses with the
seat arithmetic in the message; the two legitimate answers are the waiting list
(`capacity.join_waiting_list`) and an approved capacity approval.

```python
capacity.join_waiting_list(request_key, student_group, student, note="")
capacity.leave_waiting_list(request_key, entry, reason)
capacity.offer_waiting_list_seat(request_key, entry, expires_on="")
capacity.admit_from_waiting_list(request_key, entry, override="")
capacity.create_capacity_override(request_key, student_group, student, seats, reason, expires_on="")
capacity.revoke_capacity_override(request_key, override, reason)
```

Joining refuses when a seat is actually free (that student should be enrolled,
not queued). An offer holds one seat until its expiry. Admission re-proves the
seat, the enrollment and the class state, then reactivates the student's
existing roster row instead of adding a second one. A capacity approval must
name exactly this student and class, is consumed (`Used`) in the same
transaction as the roster row, and can never be replayed.

Reads for the front desk and the academic desk:

```python
capacity.class_availability(student_group="", program="", academic_year="", branch="")
capacity.waiting_list_board(student_group="")
```

`class_availability` returns `capacity / rostered / reserved / available /
waiting / full` per class plus a per-program intake projection (`seats_available`,
`waiting`, `next_class_end`, `projected_unmet_demand`). `waiting_list_board`
returns each open entry with `next`, `next_command` and `next_role` — the one
action to take and who must take it. Both are role-gated to Reception, Academic
staff, Scheduler, Auditor, Enrollment Officer and the Owner/GM; Finance is
refused.

## 4. Move a student between classes (transfer)

```python
transfers.request_class_transfer(request_key, student, from_group, to_group, reason, effective_date)
transfers.approve_class_transfer(request_key, transfer, override="")
transfers.deny_class_transfer(request_key, transfer, reason)
transfers.cancel_class_transfer(request_key, transfer, reason)
```

A request proves eligibility and **snapshots** it: source and target facts, the
transfer kind (`Class`, `Time`, `Program`, `Branch`), the pinned policy version,
the target seat position, the target-timetable collision check, the suspension
check and the preserved-history evidence (attendance counts, assessment results,
fees, enrollments, instructor assignments). Program and branch moves are refused
unless the pinned version enables them.

Approval re-proves every fact under row locks, refuses self-approval, refuses
when the pinned version is no longer governing, requires the approver role the
policy names, requires an open roster-change window (a transfer **is** a roster
change), and executes in one transaction: source row deactivated, target row
activated, transfer `Executed`. Nothing else is rewritten — the attendance,
assessments, fees and assignments stay exactly where they happened, and the
evidence is stored on the transfer row for later audit. A full target needs an
approved capacity approval for this student, consumed in the same call.

## 5. Pause and return (suspension)

```python
suspensions.suspend_class(request_key, student_group, reason, from_date, until_date)
suspensions.suspend_student_membership(request_key, student_group, student, reason, from_date, until_date)
suspensions.resume_suspension(request_key, suspension, reason="")
```

Inside its window a class suspension refuses new sessions, and a student
suspension refuses a `Present` mark for that learner. `Absent` and `Leave` stay
recordable — the learner is away, and the record must still be truthful. The
roster row is never touched, capacity keeps counting it, and `resume` ends the
window while keeping the row for history. Both windows are bounded by the
policy.

## 6. Reporting and audit

Every command stores its actor, request key and result under the existing
receipts (`TH Placement Operation` / `TH Placement Audit Event` for operational
commands, `TH Configuration Operation` / `TH Configuration Audit Event` for the
Course Owner carriers). The operational records themselves keep their status
history: `TH Class Transfer` (`Requested → Executed / Denied / Cancelled`),
`TH Class Waiting List` (`Waiting / Offered / Admitted / Expired / Withdrawn`),
`TH Capacity Approval` (`Approved → Used / Revoked / Expired`),
`TH Class Suspension` (`Active → Ended`), and every `Course Schedule` row keeps
`th_session_kind`, `th_session_status`, `th_replaces` and `th_session_note`.

## What this does not do

- It does not cancel an enrollment, withdraw a student or repeat a term. A05
  (rolling terms/repeats) and A11 (enrollment cancellation) remain **BLOCKED**,
  and enrollment withdrawal/dismissal stays gated on owner decision D5.
- It does not read the Owner Operations `capacity_target`,
  `calendar_notice_days`, `transfer_allowed` or `withdrawal_allowed` fields.
  Those remain decision inputs; `TH Class Operations Policy` is the bounded
  resolver that makes class-level capacity, calendar and mobility operational.
- It does not change payroll, contracts or compensation
  (`teaching/compensation.py` is untouched), and it does not change the shared
  Desk frontends — the seat/queue reads are endpoint-only for those surfaces.
