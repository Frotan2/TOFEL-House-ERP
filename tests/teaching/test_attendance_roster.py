"""Attendance Recorder class-list read (teaching.attendance_roster).

The recorder's command page marks students from this roster instead of a
typed JSON object. The read uses the same role and Branch/Company scope as
the record command, refuses closed or future sessions, and lists only active
members without a recorded mark. The write command still re-validates
everything under lock (covered by the attendance journey tests).
"""
import sys
import types
import unittest
from unittest.mock import Mock

from tests.teaching.operations_site import OperationsSite, PermissionError_, ValidationError

RECORDER = "attendance.recorder@example.test"


class AttendanceRosterTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.site.set_roles(RECORDER, ["Attendance Recorder"])
        self.ops.login(RECORDER)
        security = sys.modules["toefl_house.security"]
        security.KIND_ROLES = {"record_attendance": "Attendance Recorder"}

        def authorize(role):
            user = self.site.user
            if role not in self.site.roles.get(user, []):
                raise PermissionError_("An explicitly assigned non-administrator actor is required")
            return user
        security.authorize = authorize
        self.scope = types.ModuleType("toefl_house.command_scope")
        self.scope.authorize_command_scope = Mock()
        sys.modules["toefl_house.command_scope"] = self.scope
        for student, name in (("STU-1", "Ahmad Karimi"), ("STU-2", "Sara Rahimi"), ("STU-3", "Left Class")):
            self.ops.seed_student(student, student_name=name)
        self.ops.seed_class(name="GRP-A", members=["STU-1", "STU-2", "STU-3"])
        for row in self.site.all("Student Group Student"):
            row["student_name"] = {"STU-1": "Ahmad Karimi", "STU-2": "Sara Rahimi", "STU-3": "Left Class"}[row["student"]]
            if row["student"] == "STU-3":
                row["active"] = 0
        self.session = self.ops.seed_session(name="SES-1", date="2026-09-22")

    def test_lists_active_unmarked_members_with_session_facts(self):
        roster = self.ops.teaching.attendance_roster("SES-1")
        self.assertEqual(roster["course_schedule"], "SES-1")
        self.assertEqual(roster["date"], "2026-09-22")
        self.assertEqual(roster["roster"], [{"student": "STU-1", "name": "Ahmad Karimi"},
                                            {"student": "STU-2", "name": "Sara Rahimi"}])
        self.scope.authorize_command_scope.assert_called_once_with(
            "record_attendance", {"course_schedule": "SES-1"}, RECORDER)

    def test_already_marked_students_are_left_out(self):
        self.site.add("Student Attendance", student="STU-1", course_schedule="SES-1", status="Present", docstatus=1)
        roster = self.ops.teaching.attendance_roster("SES-1")
        self.assertEqual([row["student"] for row in roster["roster"]], ["STU-2"])
        self.assertEqual(roster["already_marked"], 1)

    def test_other_roles_are_refused(self):
        self.site.set_roles(RECORDER, ["Instructor"])
        with self.assertRaises(PermissionError_):
            self.ops.teaching.attendance_roster("SES-1")

    def test_branch_scope_is_enforced(self):
        self.scope.authorize_command_scope.side_effect = PermissionError_("outside this login's permitted branches")
        with self.assertRaises(PermissionError_):
            self.ops.teaching.attendance_roster("SES-1")

    def test_future_cancelled_unknown_and_inactive_sessions_are_refused(self):
        self.ops.seed_session(name="SES-FUTURE", date="2026-09-30")
        self.ops.seed_session(name="SES-CANCELLED", date="2026-09-21", status="Cancelled")
        self.ops.seed_class(name="GRP-DONE", status="Completed", members=["STU-1"])
        self.ops.seed_session(name="SES-DONE", group="GRP-DONE", date="2026-09-21")
        for name, message in (("SES-FUTURE", "future session"), ("SES-CANCELLED", "Scheduled sessions only"),
                              ("SES-NONE", "Unknown course schedule"), ("SES-DONE", "Active")):
            with self.subTest(session=name), self.assertRaisesRegex(ValidationError, message):
                self.ops.teaching.attendance_roster(name)


if __name__ == "__main__":
    unittest.main()
