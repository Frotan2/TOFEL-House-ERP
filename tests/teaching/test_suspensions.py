"""Mission 3 temporary suspensions: pause the permission, never the history.

A class suspension stops sessions being scheduled inside its window; a student
suspension stops that learner being marked Present. Neither edits the roster,
deletes an attendance record, or frees a seat — the pause is a bounded,
resumable operational fact, and the suite proves exactly that.
"""
import unittest

from tests.teaching.operations_site import (
    ACTOR, OperationsSite, ValidationError)


class SuspensionWindowTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)

    def test_a_window_cannot_end_before_it_starts(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspension_window_valid(
                "2026-09-25", "2026-09-23", 14, "Class")
        self.assertIn("cannot end before it starts", str(ctx.exception))

    def test_a_window_cannot_exceed_the_policy_limit(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspension_window_valid(
                "2026-09-21", "2026-10-10", 14, "Student")
        self.assertIn("may not exceed 14 day(s)", str(ctx.exception))
        self.assertEqual(
            self.ops.suspensions.suspension_window_valid(
                "2026-09-21", "2026-09-30", 14, "Student"),
            ("2026-09-21", "2026-09-30"))

    def test_bad_dates_are_named(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspension_window_valid(
                "21-09-2026", "2026-09-30", 14, "Class")
        self.assertIn("must be a date", str(ctx.exception))


class ClassSuspensionTests(unittest.TestCase):
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

    def test_a_class_suspension_is_recorded_with_its_window_and_reason(self):
        result = self.ops.suspensions.suspend_class(
            "suspend-class-0001", "GRP-A", "flooded classroom",
            "2026-09-22", "2026-09-24")
        self.assertEqual(result["scope"], "Class")
        self.assertEqual(result["status"], "Active")
        self.assertEqual((result["from_date"], result["until_date"]),
                         ("2026-09-22", "2026-09-24"))
        stored = self.site.get("TH Class Suspension", result["name"])
        self.assertEqual(stored["requested_by"], ACTOR)
        self.assertEqual(stored["policy_effective_from"], "2026-09-01")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 1)],
                         "a suspension never edits the roster")

    def test_the_feature_must_be_enabled(self):
        self.ops.append_policy("2026-09-02", allow_class_suspension=0)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspend_class(
                "suspend-class-0002", "GRP-A", "reason",
                "2026-09-22", "2026-09-23")
        self.assertIn("not permitted", str(ctx.exception))

    def test_overlapping_class_suspensions_are_refused(self):
        self.ops.suspensions.suspend_class(
            "suspend-class-0003", "GRP-A", "one", "2026-09-22", "2026-09-24")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspend_class(
                "suspend-class-0004", "GRP-A", "two", "2026-09-23",
                "2026-09-25")
        self.assertIn("already has an active suspension", str(ctx.exception))

    def test_scheduling_inside_the_window_is_refused_and_outside_allowed(self):
        self.ops.suspensions.suspend_class(
            "suspend-class-0005", "GRP-A", "flood", "2026-09-21",
            "2026-09-23")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "suspend-session-0001", "GRP-A", "2026-09-22", "09:00:00",
                "10:00:00", "INS-1", "ROOM-1", "ENG-101")
        self.assertIn("is suspended on 2026-09-22", str(ctx.exception))
        result = self.ops.teaching.schedule_session(
            "suspend-session-0002", "GRP-A", "2026-09-24", "09:00:00",
            "10:00:00", "INS-1", "ROOM-1", "ENG-101")
        self.assertEqual(result["schedule_date"], "2026-09-24")

    def test_resume_ends_the_pause_once_and_keeps_the_row(self):
        result = self.ops.suspensions.suspend_class(
            "suspend-class-0006", "GRP-A", "flood", "2026-09-22",
            "2026-09-30")
        resumed = self.ops.suspensions.resume_suspension(
            "resume-0001", result["name"], "rooms dried out")
        self.assertEqual(resumed["status"], "Ended")
        stored = self.site.get("TH Class Suspension", result["name"])
        self.assertEqual(stored["status"], "Ended")
        self.assertEqual(stored["ended_by"], ACTOR)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.resume_suspension("resume-0002",
                                                   result["name"])
        self.assertIn("already Ended", str(ctx.exception))

    def test_a_class_suspension_blocks_every_present_mark(self):
        self.ops.suspensions.suspend_class(
            "suspend-class-0007", "GRP-A", "flood", "2026-09-21",
            "2026-09-21")
        session = self.ops.seed_session(date="2026-09-21",
                                        instructor="INS-1", room="ROOM-1")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.record_attendance(
                "suspend-attend-0001", session,
                {"STU-1": "Present", "STU-2": "Absent"})
        self.assertIn("no Present marks can be recorded", str(ctx.exception))
        result = self.ops.teaching.record_attendance(
            "suspend-attend-0002", session,
            {"STU-1": "Absent", "STU-2": "Leave"})
        self.assertEqual(result["marked"], 2,
                         "truthful Absent/Leave records are still allowed")


class StudentSuspensionTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=2,
                            members=["STU-1", "STU-2"])
        self.ops.seed_student("STU-1")
        self.ops.seed_student("STU-2")
        self.ops.seed_student("STU-9")
        self.ops.seed_room("ROOM-1")
        self.ops.seed_instructor("INS-1")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")

    def test_a_student_suspension_requires_a_current_membership(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspend_student_membership(
                "suspend-student-0001", "GRP-A", "STU-9", "travelling",
                "2026-09-22", "2026-09-24")
        self.assertIn("not an active member", str(ctx.exception))

    def test_only_the_suspended_student_is_blocked(self):
        self.ops.suspensions.suspend_student_membership(
            "suspend-student-0002", "GRP-A", "STU-2", "travelling",
            "2026-09-21", "2026-09-25")
        session = self.ops.seed_session(date="2026-09-21",
                                        instructor="INS-1", room="ROOM-1")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.record_attendance(
                "suspend-attend-0003", session,
                {"STU-1": "Present", "STU-2": "Present"})
        self.assertIn("Student STU-2 is suspended", str(ctx.exception))
        result = self.ops.teaching.record_attendance(
            "suspend-attend-0004", session,
            {"STU-1": "Present", "STU-2": "Leave"})
        self.assertEqual(result["marked"], 2)
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 1)])

    def test_the_student_limit_comes_from_the_policy(self):
        self.ops.append_policy("2026-09-02", student_suspension_max_days=3)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.suspensions.suspend_student_membership(
                "suspend-student-0003", "GRP-A", "STU-1", "long",
                "2026-09-21", "2026-09-30")
        self.assertIn("may not exceed 3 day(s)", str(ctx.exception))

    def test_a_suspension_stops_applying_after_its_window(self):
        row = self.ops.suspensions.suspend_student_membership(
            "suspend-student-0004", "GRP-A", "STU-2", "travelling",
            "2026-09-22", "2026-09-23")
        self.assertIsNotNone(self.ops.suspensions.active_suspension(
            "GRP-A", "STU-2", "2026-09-23"))
        self.assertIsNone(self.ops.suspensions.active_suspension(
            "GRP-A", "STU-2", "2026-09-24"))
        self.assertEqual(self.site.get("TH Class Suspension",
                                       row["name"])["status"], "Active",
                         "the row stays Active; the window is what expires")


if __name__ == "__main__":
    unittest.main()
