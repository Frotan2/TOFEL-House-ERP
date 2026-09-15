"""Pure local unit checks for thin teaching-operations policy.

Not native Frappe qualification; hosted acceptance lives in
tools/placement/native_checks.py on the branch-restricted runner.
"""
import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (can_read, validate_attendance_statuses, validate_capacity,
                                validate_group_name, validate_schedule_date,
                                validate_session_window)

ROOT = Path(__file__).resolve().parents[2]
TEACHING = ROOT / "apps/toefl_house/toefl_house/teaching/__init__.py"
HOOKS = ROOT / "apps/toefl_house/toefl_house/hooks.py"


class GroupNameTests(unittest.TestCase):
    def test_synthetic_name_accepted(self):
        self.assertEqual(validate_group_name("SYN-GRP-MAIN-1"), "SYN-GRP-MAIN-1")

    def test_operational_name_denied(self):
        for bad in ("REAL-CLASS-1", "SYN grp", "", "SYN-" + "X" * 60, 7, None):
            with self.assertRaises(ValueError):
                validate_group_name(bad)


class CapacityTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(validate_capacity(1), 1)
        self.assertEqual(validate_capacity(500), 500)
        for bad in (0, 501, -1, "2", 2.0, True, None):
            with self.assertRaises(ValueError):
                validate_capacity(bad)


class ScheduleDateTests(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(validate_schedule_date("2026-09-21"), "2026-09-21")

    def test_bad_dates_denied(self):
        for bad in ("21/09/2026", "2026-13-01", "", None, 20260921):
            with self.assertRaises(ValueError):
                validate_schedule_date(bad)


class SessionWindowTests(unittest.TestCase):
    def test_normalized(self):
        self.assertEqual(validate_session_window("09:00", "10:30"), ("09:00:00", "10:30:00"))
        self.assertEqual(validate_session_window("09:00:00", "09:00:01"), ("09:00:00", "09:00:01"))

    def test_inverted_or_zero_length_denied(self):
        with self.assertRaises(ValueError):
            validate_session_window("10:30:00", "09:00:00")
        with self.assertRaises(ValueError):
            validate_session_window("09:00:00", "09:00:00")

    def test_malformed_times_denied(self):
        for bad in (("25:00", "26:00"), ("9:00", "10:00"), ("abc", "def"), (9, 10), ("", "")):
            with self.assertRaises(ValueError):
                validate_session_window(*bad)


class AttendanceBatchTests(unittest.TestCase):
    def test_native_statuses_only(self):
        self.assertEqual(
            validate_attendance_statuses({"EDU-STU-1": "Present", "EDU-STU-2": "Absent"}),
            {"EDU-STU-1": "Present", "EDU-STU-2": "Absent"})
        self.assertEqual(validate_attendance_statuses({"EDU-STU-1": "Leave"}),
                         {"EDU-STU-1": "Leave"})

    def test_invented_status_denied(self):
        with self.assertRaises(ValueError):
            validate_attendance_statuses({"EDU-STU-1": "Late"})

    def test_json_string_batch(self):
        self.assertEqual(validate_attendance_statuses('{"EDU-STU-1": "Present"}'),
                         {"EDU-STU-1": "Present"})
        with self.assertRaises(ValueError):
            validate_attendance_statuses("not json")

    def test_bounds_and_shape(self):
        with self.assertRaises(ValueError):
            validate_attendance_statuses({})
        with self.assertRaises(ValueError):
            validate_attendance_statuses({f"EDU-STU-{i}": "Present" for i in range(101)})
        with self.assertRaises(ValueError):
            validate_attendance_statuses(["Present"])
        with self.assertRaises(ValueError):
            validate_attendance_statuses({"": "Present"})


class TeachingReadBoundaryTests(unittest.TestCase):
    def test_teaching_auditor_reads_receipts_only(self):
        self.assertTrue(can_read("audit", ["Teaching Auditor"], "a", "someone"))
        self.assertTrue(can_read("operation", ["Teaching Auditor"], "a", "someone"))
        self.assertFalse(can_read("key", ["Teaching Auditor"], "a", "a"))
        self.assertFalse(can_read("admission_decision", ["Teaching Auditor"], "a", "someone"))

    def test_scheduler_and_recorder_read_no_owned_records(self):
        for role in ("Teaching Scheduler", "Attendance Recorder"):
            for kind in ("audit", "operation", "key", "item", "decision", "admission_decision"):
                self.assertFalse(can_read(kind, [role], "u", "u"), (role, kind))

    def test_other_auditors_unchanged(self):
        self.assertTrue(can_read("audit", ["Enrollment Auditor"], "a", "someone"))
        self.assertTrue(can_read("operation", ["Placement Auditor"], "a", "someone"))


class GuardWiringTests(unittest.TestCase):
    def test_hooks_guard_the_three_native_doctypes(self):
        source = HOOKS.read_text(encoding="utf-8")
        for doctype, guard in (("Student Group", "guard_student_group"),
                               ("Course Schedule", "guard_course_schedule"),
                               ("Student Attendance", "guard_student_attendance")):
            self.assertIn(f'"{doctype}"', source)
            self.assertIn(f"toefl_house.teaching.{guard}", source)
        tree = ast.parse(TEACHING.read_text(encoding="utf-8"))
        guards = {node.name for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name.startswith("guard_")}
        self.assertEqual(guards, {"guard_student_group", "guard_course_schedule",
                                  "guard_student_attendance"})

    def test_work_does_not_assign_enclosing_parameters(self):
        tree = ast.parse(TEACHING.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            params = {arg.arg for arg in node.args.args}
            for child in node.body:
                if not (isinstance(child, ast.FunctionDef) and child.name == "work"):
                    continue
                assigned = set()
                for inner in ast.walk(child):
                    if isinstance(inner, ast.Assign):
                        for target in inner.targets:
                            if isinstance(target, ast.Name):
                                assigned.add(target.id)
                    if isinstance(inner, ast.AnnAssign) and isinstance(inner.target, ast.Name):
                        assigned.add(inner.target.id)
                overlap = sorted(assigned & params)
                self.assertEqual(
                    overlap, [],
                    "%s.work assigns enclosing parameters %s (UnboundLocalError)"
                    % (node.name, overlap))


if __name__ == "__main__":
    unittest.main()
