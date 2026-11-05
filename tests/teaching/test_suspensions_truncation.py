"""Refinement of Group 4 (C-03/C-08): suspension reads must not silently
truncate.

The prior fix moved scope filtering for the class case into the query and
fixed interval overlap — but `overlapping_suspension`,
`_class_suspension_covering` and `active_suspension` still fetch with
`limit_page_length=50` and filter dates in Python. With more than 50
Active rows for a group, the covering/overlapping row can sit past the
cap and the check silently answers "no suspension". These tests seed
that shape directly (bypassing `_suspend`, which is the guard under
test) and reproduce the miss before the fix.
"""
import unittest

from tests.teaching.operations_site import (
    OperationsSite, ValidationError)


class SuspensionTruncationTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=2,
                            members=["STU-1", "STU-2"])
        self.ops.seed_student("STU-1")
        self.ops.seed_student("STU-2")
        self.ops.seed_room("ROOM-1")
        self.ops.seed_instructor("INS-1")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")

    def _seed(self, name, scope, student, from_date, until_date):
        return self.site.add(
            "TH Class Suspension", name=name, scope=scope,
            student_group="GRP-A", student=student or None,
            from_date=from_date, until_date=until_date,
            reason="seeded", status="Active")

    def test_covering_class_row_beyond_first_50_is_found(self):
        for i in range(50):
            self._seed(f"SUSP-NON-{i:02d}", "Class", "",
                       "2026-08-01", "2026-08-05")
        self._seed("SUSP-COVER", "Class", "", "2026-09-21", "2026-09-23")
        row = self.ops.suspensions._class_suspension_covering(
            "GRP-A", "2026-09-22")
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "SUSP-COVER")

    def test_active_suspension_finds_student_row_beyond_first_50(self):
        for i in range(50):
            self._seed(f"SUSP-NON-{i:02d}", "Student", "STU-1",
                       "2026-08-01", "2026-08-05")
        self._seed("SUSP-COVER", "Student", "STU-1",
                   "2026-09-21", "2026-09-23")
        row = self.ops.suspensions.active_suspension(
            "GRP-A", "STU-1", "2026-09-22")
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "SUSP-COVER")

    def test_overlap_beyond_first_50_is_found(self):
        for i in range(50):
            self._seed(f"SUSP-NON-{i:02d}", "Student", "STU-1",
                       f"2026-08-{i % 20 + 1:02d}", f"2026-08-{i % 20 + 1:02d}")
        self._seed("SUSP-OVERLAP", "Student", "STU-1",
                   "2026-09-22", "2026-09-24")
        row = self.ops.suspensions.overlapping_suspension(
            "GRP-A", "STU-1", "Student", "2026-09-23", "2026-09-25")
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "SUSP-OVERLAP")

    def test_suspend_refuses_overlap_hidden_beyond_the_cap(self):
        for i in range(50):
            self._seed(f"SUSP-NON-{i:02d}", "Student", "STU-1",
                       f"2026-08-{i % 20 + 1:02d}", f"2026-08-{i % 20 + 1:02d}")
        self._seed("SUSP-OVERLAP", "Student", "STU-1",
                   "2026-09-22", "2026-09-24")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspend_student_membership(
                "suspend-hidden-overlap", "GRP-A", "STU-1", "again",
                "2026-09-23", "2026-09-25")
        self.assertIn("already has an active suspension", str(ctx.exception))

    def test_class_suspension_beyond_the_cap_blocks_scheduling(self):
        for i in range(50):
            self._seed(f"SUSP-NON-{i:02d}", "Class", "",
                       "2026-08-01", "2026-08-05")
        self._seed("SUSP-COVER", "Class", "", "2026-09-21", "2026-09-23")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.assert_scheduling_allowed("GRP-A", "2026-09-22")
        self.assertIn("is suspended on 2026-09-22", str(ctx.exception))

    def test_every_same_day_student_suspension_is_enforced(self):
        # 51 different students suspended on the same day; the 51st
        # student's Present mark must still be refused.
        for i in range(1, 52):
            self._seed(f"SUSP-STU-{i:02d}", "Student", f"STU-{i:02d}",
                       "2026-09-21", "2026-09-25")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.assert_attendance_allowed(
                "GRP-A", "2026-09-22", {"STU-51": "Present"})
        self.assertIn("Student STU-51 is suspended", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
