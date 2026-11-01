"""End-to-end Mission 3 journey on one synthetic site.

The scenario is the operational one an institute actually runs: configure the
rules, build a timetable, hit the conflicts, fill a class, queue a learner, use
an authorized override, transfer a student, pause a membership, change the
calendar, and prove at the end that nothing was duplicated and no history was
lost. Every assertion is made against the stored native and owned rows.
"""
import json
import unittest
from unittest.mock import patch

from tests.teaching.operations_site import (
    ACTOR, APPROVER, COURSE_OWNER, RECEPTION, OperationsSite,
    PermissionError_, ValidationError)


class RosterControlTests(unittest.TestCase):
    """The roster commands against the real policy/seat modules."""

    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_class(name="GRP-A", capacity=2,
                            members=["STU-1", "STU-2"])
        self.ops.seed_class(name="GRP-B", capacity=2, members=[])
        self.ops.seed_student("STU-1")
        self.ops.seed_student("STU-2")
        self.ops.seed_student("STU-3")
        for student in ("STU-1", "STU-2", "STU-3"):
            self.ops.seed_enrollment(student)

    def test_removing_a_member_keeps_the_row_as_history(self):
        self.ops.seed_policy()
        result = self.ops.teaching.remove_class_member(
            "remove-member-0001", "GRP-A", "STU-2", "withdrew from the class")
        self.assertEqual(result["active"], 0)
        self.assertEqual(result["reason"], "withdrew from the class")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 0)])
        self.assertEqual(len(self.ops.roster("GRP-A")), 2,
                         "the row is preserved, never deleted")

    def test_removal_can_be_switched_off_by_policy(self):
        self.ops.seed_policy(remove_member_allowed=0)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.remove_class_member(
                "remove-member-0002", "GRP-A", "STU-2", "reason")
        self.assertIn("disabled by the class-operations policy",
                      str(ctx.exception))

    def test_removal_refuses_a_non_member_and_a_missing_reason(self):
        self.ops.seed_policy()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.remove_class_member(
                "remove-member-0003", "GRP-A", "STU-3", "reason")
        self.assertIn("not an active member", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.remove_class_member(
                "remove-member-0004", "GRP-A", "STU-2", "")
        self.assertIn("removal reason is required", str(ctx.exception))

    def test_direct_moves_follow_the_policy_switch(self):
        self.ops.seed_policy()  # direct_moves_allowed = 0
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.move_class_member(
                "move-member-0001", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("Direct roster moves are disabled", str(ctx.exception))
        self.ops.append_policy("2026-09-02", direct_moves_allowed=1)
        result = self.ops.teaching.move_class_member(
            "move-member-0002", "GRP-A", "STU-1", "GRP-B")
        self.assertEqual(result["to_group"], "GRP-B")
        self.assertEqual(self.ops.roster("GRP-A"), [("STU-1", 0), ("STU-2", 1)])
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-1", 1)])


class ReceptionBranchAvailabilityTests(unittest.TestCase):
    """A front-desk login must not read another branch's seats or waiting students."""

    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_class(name="GRP-A", branch="BR-A", capacity=3,
                            members=["STU-1"])
        self.ops.seed_class(name="GRP-B", branch="BR-B", capacity=3,
                            members=["STU-2"])
        self.site.add("TH Class Waiting List", name="WAIT-A",
                      student="STU-3", student_group="GRP-A",
                      status="Waiting", priority=0, requested_on="2026-09-22")
        self.site.add("TH Class Waiting List", name="WAIT-B",
                      student="STU-FOREIGN", student_group="GRP-B",
                      status="Waiting", priority=0, requested_on="2026-09-22")
        self.ops.login(RECEPTION)

    def test_without_branch_assignment_both_read_endpoints_deny(self):
        for fn in (self.ops.capacity.class_availability,
                   self.ops.capacity.waiting_list_board):
            with self.subTest(method=fn.__name__):
                with self.assertRaises(PermissionError_):
                    fn()

    def test_one_assigned_branch_sees_only_its_classes_and_waiting_students(self):
        self.site.add("User Permission", name="BR-ALLOW-A",
                      user=RECEPTION, allow="Branch", for_value="BR-A")
        available = self.ops.capacity.class_availability()
        self.assertEqual([r["student_group"] for r in available["classes"]], ["GRP-A"])
        board = self.ops.capacity.waiting_list_board()
        self.assertEqual([r["student"] for r in board["entries"]], ["STU-3"])
        self.assertEqual([r["entry"] for r in board["entries"]], ["WAIT-A"])
        with self.assertRaises(PermissionError_):
            self.ops.capacity.class_availability(branch="BR-B")
        with self.assertRaises(PermissionError_):
            self.ops.capacity.waiting_list_board(student_group="GRP-B")
        self.assertEqual(self.ops.capacity.class_availability(
            student_group="GRP-B")["classes"], [])

    def test_truncated_availability_and_waiting_board_cannot_claim_exact_counts(self):
        self.site.add("User Permission", name="BR-LIMIT-A",
                      user=RECEPTION, allow="Branch", for_value="BR-A")
        for i in range(self.ops.capacity.MAX_CLASSES):
            self.site.add("Student Group", name=f"MORE-A-{i}",
                          th_branch="BR-A", disabled=0,
                          student_group_name=f"Many {i}")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.class_availability()
        self.assertIn("Too many classes", str(ctx.exception))

        # The class-specific read must remain available even when the
        # overall branch scope has too many classes to show completely.
        single = self.ops.capacity.class_availability(student_group="GRP-A")
        self.assertEqual([c["student_group"] for c in single["classes"]], ["GRP-A"])
        for i in range(self.ops.capacity.MAX_ENTRIES):
            self.site.add("TH Class Waiting List", name=f"WAIT-A-{i}",
                          student=f"STU-{i}", student_group="GRP-A",
                          status="Waiting", priority=0,
                          requested_on="2026-09-22")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.waiting_list_board(student_group="GRP-A")
        self.assertIn("choose one class", str(ctx.exception))

        # Even when class is selected, a seat summary cannot silently
        # undercount a large waiting queue.
        for i in range(self.ops.capacity.MAX_CLASSES * 4):
            self.site.add("TH Class Waiting List", name=f"WAIT-EXTRA-{i}",
                          student=f"OTHER-{i}", student_group="GRP-A",
                          status="Waiting", priority=0,
                          requested_on="2026-09-22")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.class_availability(student_group="GRP-A")
        self.assertIn("Waiting-list totals exceed", str(ctx.exception))

    def test_terminal_or_archived_class_does_not_advertise_free_seats(self):
        self.site.add("User Permission", name="BR-TERMINAL-A",
                      user=RECEPTION, allow="Branch", for_value="BR-A")
        self.ops.seed_class(name="GRP-COMPLETED", branch="BR-A",
                            status="Completed", capacity=20)
        self.ops.seed_class(name="GRP-CANCELLED", branch="BR-A",
                            status="Cancelled", capacity=20)
        self.ops.seed_class(name="GRP-ARCHIVED", branch="BR-A",
                            status="Active", capacity=20)
        self.site.get("Student Group", "GRP-ARCHIVED")["disabled"] = 1
        self.site.add("TH Class Waiting List", name="WAIT-CLOSED",
                      student="STU-PRIVATE", student_group="GRP-COMPLETED",
                      status="Waiting", priority=0, requested_on="2026-09-22")
        report = self.ops.capacity.class_availability()
        self.assertEqual([row["student_group"] for row in report["classes"]],
                         ["GRP-A"])
        self.assertEqual(self.ops.capacity.waiting_list_board(
            student_group="GRP-COMPLETED")["entries"], [])
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        board = self.ops.capacity.waiting_list_board(student_group="GRP-COMPLETED")
        self.assertEqual(len(board["entries"]), 1)
        self.assertEqual(board["entries"][0]["next_command"], "")
        self.assertEqual(board["entries"][0]["next_role"], "Academic Manager")

    def test_branch_rule_restricts_academic_manager_but_hq_without_one_can_read(self):
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        self.assertEqual(len(self.ops.capacity.class_availability()["classes"]), 2)
        self.site.add("User Permission", name="BR-MANAGER-ALLOW",
                      user=APPROVER, allow="Branch", for_value="BR-A")
        self.assertEqual(
            [row["student_group"] for row in self.ops.capacity.class_availability()["classes"]],
            ["GRP-A"])


class ClassOperationsJourneyTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_policy()
        self.ops.seed_calendar(days=[{"date": "2026-09-28", "kind": "Holiday"}])
        self.ops.seed_template(slots=[
            {"weekday": "Mon", "from_time": "09:00:00", "to_time": "10:00:00",
             "course": "ENG-101", "room": "ROOM-1", "instructor": "INS-1"},
            {"weekday": "Tue", "from_time": "09:00:00", "to_time": "10:00:00",
             "course": "ENG-101", "room": "ROOM-1", "instructor": "INS-1"},
            {"weekday": "Wed", "from_time": "13:00:00", "to_time": "14:00:00",
             "course": "ENG-101", "room": "ROOM-1", "instructor": "INS-1"}])
        self.ops.seed_class(name="GRP-A", capacity=3,
                            members=["STU-1", "STU-2"])
        self.ops.seed_class(name="GRP-B", capacity=2, members=[],
                            start="2026-09-01")
        for index in range(1, 5):
            self.ops.seed_student(f"STU-{index}")
            self.ops.seed_enrollment(f"STU-{index}")
        self.ops.seed_room("ROOM-1")
        self.ops.seed_room("ROOM-2")
        self.ops.seed_instructor("INS-1")
        self.ops.seed_instructor("INS-2")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")

    def test_the_whole_operational_workflow(self):
        # 1. The owner's configuration materializes the weekly timetable.
        generated = self.ops.scheduling.generate_timetable(
            "journey-generate-0001", "GRP-A", "TT-1", "2026-09-21",
            "2026-09-30")
        self.assertEqual([row["schedule_date"] for row in generated["sessions"]],
                         ["2026-09-21", "2026-09-22", "2026-09-23",
                          "2026-09-29", "2026-09-30"])
        self.assertEqual(generated["skipped_calendar_days"], ["2026-09-28"])

        # 2. A conflicting session is refused before anything is written.
        before = len(self.site.all("Course Schedule"))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "journey-session-0001", "GRP-A", "2026-09-21", "09:30:00",
                "10:30:00", "INS-2", "ROOM-2", "ENG-101")
        self.assertIn("already has session", str(ctx.exception))
        self.assertEqual(len(self.site.all("Course Schedule")), before)

        # 3. The class fills up; the next learner cannot be added.
        added = self.ops.teaching.add_class_member(
            "journey-add-0001", "GRP-A", "STU-3")
        self.assertFalse(added["reactivated"])
        self.assertEqual(added["seats_available"], 0)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.add_class_member(
                "journey-add-0002", "GRP-A", "STU-4")
        self.assertIn("is full", str(ctx.exception))

        # 4. The waiting list is the actionable answer for the next learner.
        entry = self.ops.capacity.join_waiting_list(
            "journey-wait-0001", "GRP-A", "STU-4", "wants the morning class")
        self.assertEqual(entry["position"], 1)
        self.site.user = RECEPTION
        board = self.ops.capacity.waiting_list_board("GRP-A")
        self.assertEqual(board["entries"][0]["next_command"], "")
        self.assertIn("No seat yet", board["entries"][0]["next"])
        report = self.ops.capacity.class_availability(program="TH-PROG")
        intake = report["intake"][0]
        self.assertEqual((intake["seats_available"], intake["waiting"],
                          intake["projected_unmet_demand"]), (2, 1, 0))

        # 5. An authorized override admits the queued learner, once.
        self.ops.login(APPROVER)
        override = self.ops.capacity.create_capacity_override(
            "journey-override-0001", "GRP-A", "STU-4", 1,
            "sibling admission approved by the Academic Manager",
            "2026-10-02")
        admitted = self.ops.capacity.admit_from_waiting_list(
            "journey-admit-0001", entry["name"], override=override["name"])
        self.assertEqual(admitted["status"], "Admitted")
        self.assertEqual(admitted["override"]["override"], override["name"])
        self.assertEqual(self.site.get("TH Capacity Approval",
                                       override["name"])["status"], "Used")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list(
                "journey-admit-0002", entry["name"])
        self.assertIn("Admitted", str(ctx.exception))
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 1), ("STU-3", 1),
                          ("STU-4", 1)])

        # 6. A transfer moves a learner with eligibility, approval and proof.
        self.site.add("Student Attendance", student="STU-2",
                      course_schedule=generated["sessions"][0]["name"],
                      status="Present", docstatus=1)
        self.ops.login(ACTOR)
        history = {doctype: len(self.site.all(doctype)) for doctype in
                   ("Student Attendance", "Program Enrollment",
                    "TH Teaching Assignment", "Fees")}
        # Simulate an explicitly superseded D5 for this synthetic-only
        # positive journey. Real deployments still refuse transfers.
        with patch.object(self.ops.transfers, "_transfer_scope_authorized",
                          return_value=True):
            transfer = self.ops.transfers.request_class_transfer(
                "journey-transfer-0001", "STU-2", "GRP-A", "GRP-B",
                "moves to the afternoon cohort", "2026-09-25")
            self.assertEqual(transfer["transfer_kind"], "Class")
            # A pending future transfer is NOT a roster move. Execute when
            # the approved effective day arrives in this synthetic journey.
            self.site.today = "2026-09-25"
            self.ops.login(APPROVER)
            executed = self.ops.transfers.approve_class_transfer(
                "journey-transfer-0002", transfer["name"])
            self.assertEqual(executed["status"], "Executed")
            self.assertEqual(self.ops.roster("GRP-A"),
                             [("STU-1", 1), ("STU-2", 0), ("STU-3", 1),
                              ("STU-4", 1)])
            self.assertEqual(self.ops.roster("GRP-B"), [("STU-2", 1)])
            self.assertEqual(
                {doctype: len(self.site.all(doctype)) for doctype in history},
                history, "no attendance, enrollment or finance row was rewritten")
            preserved = json.loads(self.site.get("TH Class Transfer",
                                                 transfer["name"])["preserved_json"])
            self.assertEqual(preserved["attendance_in_source_class"]["count"], 1)

        # 7. A temporary suspension pauses marking, never the history.
        self.ops.login(ACTOR)
        self.site.set_roles(ACTOR, ["Teaching Scheduler"])
        suspension = self.ops.suspensions.suspend_student_membership(
            "journey-suspend-0001", "GRP-A", "STU-1", "medical leave",
            "2026-09-30", "2026-09-30")
        last = generated["sessions"][-1]["name"]
        # Advance the synthetic clock to the scheduled session; attendance is
        # a record of an actual day, not a future planning entry.
        self.site.today = "2026-09-30"
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.record_attendance(
                "journey-attend-0001", last, {"STU-1": "Present"})
        self.assertIn("is suspended on 2026-09-30", str(ctx.exception))
        recorded = self.ops.teaching.record_attendance(
            "journey-attend-0002", last, {"STU-1": "Leave"})
        self.assertEqual(recorded["marked"], 1)
        self.ops.suspensions.resume_suspension("journey-resume-0001",
                                               suspension["name"], "returned")
        self.assertEqual(self.site.get("TH Class Suspension",
                                       suspension["name"])["status"], "Ended")

        # 8. A later calendar change never rewrites what was scheduled.
        self.ops.login(COURSE_OWNER)
        self.ops.calendars.add_academic_calendar_day(
            "journey-calendar-0001", "CAL-2026", "2026-09-29", "Holiday",
            "unexpected closure")
        self.assertEqual(self.site.get("Course Schedule",
                                       generated["sessions"][3]["name"])[
                           "th_session_status"], "Scheduled")
        self.ops.login(ACTOR)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "journey-session-0002", "GRP-A", "2026-09-29", "11:00:00",
                "12:00:00", "INS-1", "ROOM-1", "ENG-101")
        self.assertIn("Holiday day", str(ctx.exception))

        # 9. Role boundaries hold at the command edge.
        self.ops.login(ACTOR)
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.capacity.create_capacity_override(
                "journey-override-0002", "GRP-A", "STU-3", 1, "no", "")
        self.assertIn("Academic Manager", str(ctx.exception))
        self.site.set_roles(APPROVER, ["Academic Manager"])
        self.ops.login(ACTOR)
        with patch.object(self.ops.transfers, "_transfer_scope_authorized",
                          return_value=True):
            pending = self.ops.transfers.request_class_transfer(
                "journey-transfer-0003", "STU-3", "GRP-A", "GRP-B",
                "second transfer request", "2026-10-01")
            with self.assertRaises(PermissionError_) as ctx:
                self.ops.transfers.approve_class_transfer(
                    "journey-transfer-0004", pending["name"])
        self.assertIn("Academic Manager", str(ctx.exception))
        self.ops.login("finance.officer@example.test")
        self.site.set_roles("finance.officer@example.test", ["Finance Officer"])
        with self.assertRaises(PermissionError_):
            self.ops.capacity.class_availability()

        # 10. Reception sees ONLY the class seats in its assigned Branch.
        # The synthetic earlier scheduling scenario left Branch blank; bind
        # its existing classes at the desk checkpoint, not retroactively.
        for group in self.site.all("Student Group"):
            group["th_branch"] = "BR-A"
        self.site.add("User Permission", name="RECEPTION-BR-A",
                      user=RECEPTION, allow="Branch", for_value="BR-A")
        self.ops.login(RECEPTION)
        final = self.ops.capacity.class_availability(program="TH-PROG")
        by_group = {row["student_group"]: row for row in final["classes"]}
        self.assertEqual((by_group["GRP-A"]["capacity"],
                          by_group["GRP-A"]["rostered"],
                          by_group["GRP-A"]["available"]), (3, 4, 0))
        self.assertEqual((by_group["GRP-B"]["capacity"],
                          by_group["GRP-B"]["rostered"],
                          by_group["GRP-B"]["available"]), (2, 1, 1))
        self.assertEqual(by_group["GRP-A"]["waiting"], 0)
        for student_group in ("GRP-A", "GRP-B"):
            students = [student for student, _active
                        in self.ops.roster(student_group)]
            self.assertEqual(len(students), len(set(students)),
                             f"{student_group} has a duplicated roster row")


if __name__ == "__main__":
    unittest.main()
