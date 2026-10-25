"""Mission 3 scheduling: conflicts, calendars, durations, postponement, make-up.

Every rule here is enforced server-side inside the command transaction. The
suite proves the operational failures an institute actually hits — a double
booked instructor, a class scheduled into a holiday, a room too small for the
cohort, a make-up that ignores the owner's window — and that the original
session row is never rewritten when a session moves.
"""
import unittest

from tests.teaching.operations_site import (
    OperationsSite, PermissionError_, ValidationError)


class SchedulingTestBase(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=2,
                            members=["STU-1", "STU-2"])
        self.ops.seed_class(name="GRP-B", capacity=2, members=["STU-3"])
        self.ops.seed_student("STU-1")
        self.ops.seed_student("STU-2")
        self.ops.seed_student("STU-3")
        self.ops.seed_room("ROOM-1", seating=30)
        self.ops.seed_room("ROOM-SMALL", seating=1)
        self.ops.seed_instructor("INS-1")
        self.ops.seed_instructor("INS-2")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")

    def schedule(self, group="GRP-A", day="2026-09-21", start="09:00:00",
                 end="10:00:00", instructor="INS-1", room="ROOM-1",
                 course="ENG-101", key="schedule-0001"):
        return self.ops.teaching.schedule_session(
            key, group, day, start, end, instructor, room, course)


class SessionValidationTests(SchedulingTestBase):
    def test_a_session_lands_on_the_native_record_with_its_status(self):
        result = self.schedule()
        stored = self.site.get("Course Schedule", result["name"])
        self.assertEqual(stored["th_session_status"], "Scheduled")
        self.assertEqual(stored["th_session_kind"], "Regular")
        self.assertEqual(stored["student_group"], "GRP-A")
        self.assertEqual(stored["schedule_date"], "2026-09-21")

    def test_unknown_or_departed_instructors_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(instructor="INS-MISSING")
        self.assertIn("Unknown instructor", str(ctx.exception))
        self.site.get("Instructor", "INS-1")["status"] = "Left"
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(key="schedule-0002")
        self.assertIn("departed instructor", str(ctx.exception))

    def test_a_course_outside_the_program_catalog_is_refused(self):
        self.site.add("Course", name="MAT-900", course_name="Maths")
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(course="MAT-900")
        self.assertIn("program catalog", str(ctx.exception))

    def test_a_disabled_class_and_a_planned_class_are_refused(self):
        self.site.get("Student Group", "GRP-A")["disabled"] = 1
        with self.assertRaises(ValidationError) as ctx:
            self.schedule()
        self.assertIn("disabled", str(ctx.exception))
        self.site.get("Student Group", "GRP-A")["disabled"] = 0
        self.site.get("Student Group", "GRP-A")["th_class_status"] = "Planned"
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(key="schedule-0002")
        self.assertIn("Active classes", str(ctx.exception))

    def test_a_session_outside_the_class_window_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(day="2027-01-05")
        self.assertIn("outside the class window", str(ctx.exception))

    def test_a_session_on_a_calendar_holiday_is_refused(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-21",
                                      "kind": "Holiday"}])
        with self.assertRaises(ValidationError) as ctx:
            self.schedule()
        self.assertIn("Holiday day in the academic calendar", str(ctx.exception))

    def test_an_explicit_working_day_reopens_a_closed_date(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-21", "kind": "Closed"}])
        with self.assertRaises(ValidationError) as ctx:
            self.schedule()
        self.assertIn("Closed", str(ctx.exception))
        self.ops.seed_calendar(code="CAL-REOPEN",
                               days=[{"date": "2026-09-21",
                                      "kind": "Working Day"}])
        result = self.schedule(key="schedule-0002")
        self.assertEqual(result["schedule_date"], "2026-09-21")

    def test_a_non_teaching_weekday_is_refused_by_policy(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(day="2026-09-26")  # Saturday, not in this class policy
        self.assertIn("does not teach on that weekday", str(ctx.exception))

    def test_session_duration_bounds_come_from_the_policy(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(start="09:00:00", end="09:15:00")
        self.assertIn("15-minute session", str(ctx.exception))
        self.ops.append_policy("2026-09-02", min_session_minutes=15,
                               max_session_minutes=240)
        result = self.schedule(key="schedule-0002", start="09:00:00",
                               end="09:15:00")
        self.assertEqual(result["to_time"], "09:15:00")

    def test_the_daily_session_limit_is_enforced_per_class(self):
        self.schedule(day="2026-09-21", key="schedule-0001")
        self.schedule(day="2026-09-21", start="10:00:00", end="11:00:00",
                      key="schedule-0002")
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(day="2026-09-21", start="11:00:00", end="12:00:00",
                          key="schedule-0003")
        self.assertIn("at most 2 per day", str(ctx.exception))

    def test_class_instructor_and_room_overlaps_are_all_refused(self):
        self.schedule(key="schedule-0001")
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(key="schedule-0002", start="09:30:00", end="10:30:00")
        self.assertIn("already has session", str(ctx.exception))
        # A different class with the same instructor still collides.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "schedule-0003", "GRP-B", "2026-09-21", "09:30:00",
                "10:30:00", "INS-1", "ROOM-1", "ENG-101")
        self.assertIn("Instructor INS-1", str(ctx.exception))
        # A different class and instructor with the same room still collides.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "schedule-0004", "GRP-B", "2026-09-21", "09:30:00",
                "10:30:00", "INS-2", "ROOM-1", "ENG-101")
        self.assertIn("Room ROOM-1", str(ctx.exception))

    def test_back_to_back_sessions_do_not_conflict(self):
        self.schedule(key="schedule-0001")
        result = self.schedule(start="10:00:00", end="11:00:00",
                               key="schedule-0002")
        self.assertEqual(result["from_time"], "10:00:00")

    def test_a_double_booked_student_is_refused(self):
        # STU-1 sits in GRP-A and GRP-B: the second class's session would put
        # the same learner in two rooms at 09:00.
        self.site.add("Student Group Student", parent="GRP-B",
                      student="STU-1", active=1, idx=2)
        self.ops.seed_room("ROOM-2", seating=30)
        self.schedule(key="schedule-0001")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "schedule-0002", "GRP-B", "2026-09-21", "09:00:00",
                "10:00:00", "INS-2", "ROOM-2", "ENG-101")
        self.assertIn("Student STU-1 is already in session", str(ctx.exception))

    def test_a_room_smaller_than_the_cohort_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schedule(room="ROOM-SMALL")
        self.assertIn("seats 1, below the class capacity 2", str(ctx.exception))

    def test_a_class_without_dates_cannot_be_scheduled(self):
        self.site.get("Student Group", "GRP-A")["th_class_end_date"] = None
        with self.assertRaises(ValidationError) as ctx:
            self.schedule()
        self.assertIn("no start/end window", str(ctx.exception))


class TimetableGenerationTests(SchedulingTestBase):
    def _template(self, slots=None, **kwargs):
        slots = slots or [{"weekday": "Mon", "from_time": "09:00:00",
                           "to_time": "10:00:00", "course": "ENG-101",
                           "room": "ROOM-1", "instructor": "INS-1"}]
        self.ops.seed_template(slots=slots, **kwargs)
        return "TT-1"

    def test_generation_materializes_only_teaching_days_and_reports_skips(self):
        template = self._template(slots=[
            {"weekday": "Mon", "from_time": "09:00:00", "to_time": "10:00:00",
             "course": "ENG-101", "room": "ROOM-1", "instructor": "INS-1"},
            {"weekday": "Tue", "from_time": "09:00:00", "to_time": "10:00:00",
             "course": "ENG-101", "room": "ROOM-1", "instructor": "INS-1"}])
        self.ops.seed_calendar(days=[{"date": "2026-09-28", "kind": "Holiday"}])
        result = self.ops.scheduling.generate_timetable(
            "generate-0001", "GRP-A", template, "2026-09-21", "2026-09-30")
        dates = [row["schedule_date"] for row in result["sessions"]]
        self.assertEqual(dates, ["2026-09-21", "2026-09-22", "2026-09-29"])
        self.assertEqual(result["generated"], 3)
        self.assertEqual(result["skipped_calendar_days"], ["2026-09-28"])
        stored = self.site.get("Course Schedule", result["sessions"][0]["name"])
        self.assertEqual(stored["th_session_kind"], "Regular")
        self.assertEqual(stored["th_session_status"], "Scheduled")

    def test_generation_is_bounded_by_the_policy_horizon(self):
        template = self._template()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0002", "GRP-A", template, "2026-09-21", "2026-12-01")
        self.assertIn("at most 60 days", str(ctx.exception))

    def test_generation_refuses_a_range_with_no_teachable_day(self):
        template = self._template()
        self.ops.seed_calendar(days=[
            {"date": day, "kind": "Holiday"}
            for day in ("2026-09-21", "2026-09-22", "2026-09-23",
                        "2026-09-28", "2026-09-29", "2026-09-30")])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0003", "GRP-A", template, "2026-09-21", "2026-09-23")
        self.assertIn("No teachable date", str(ctx.exception))

    def test_generation_refuses_a_template_from_another_program_or_mode(self):
        template = self._template(program="TH-OTHER")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0004", "GRP-A", template, "2026-09-21", "2026-09-23")
        self.assertIn("different program", str(ctx.exception))
        template = self._template(delivery_mode="Online")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0005", "GRP-A", template, "2026-09-21", "2026-09-23")
        self.assertIn("delivery mode", str(ctx.exception))

    def test_regenerating_the_same_range_cannot_duplicate_sessions(self):
        template = self._template()
        self.ops.scheduling.generate_timetable(
            "generate-0006", "GRP-A", template, "2026-09-21", "2026-09-23")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0007", "GRP-A", template, "2026-09-21", "2026-09-23")
        self.assertIn("2026-09-21 09:00:00", str(ctx.exception))
        self.assertIn("already has session", str(ctx.exception))
        self.assertEqual(len(self.site.all("Course Schedule")), 1)

    def test_generation_requires_a_governing_policy(self):
        template = self._template()
        self.site.get("TH Class Operations Policy", "TH-CLASS-OPS")["status"] = \
            "Retired"
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.generate_timetable(
                "generate-0008", "GRP-A", template, "2026-09-21", "2026-09-23")
        self.assertIn("No active class-operations policy", str(ctx.exception))


class PostponementAndMakeUpTests(SchedulingTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.schedule()["name"]

    def _attendance(self, session=None, status="Present"):
        return self.site.add("Student Attendance", student="STU-1",
                             course_schedule=session or self.session,
                             status=status, docstatus=1)

    def test_postponement_keeps_the_original_row_and_links_its_replacement(self):
        result = self.ops.scheduling.postpone_session(
            "postpone-0001", self.session, "instructor sick",
            "2026-09-22")
        original = self.site.get("Course Schedule", self.session)
        self.assertEqual(original["th_session_status"], "Postponed")
        self.assertEqual(original["th_session_note"], "instructor sick")
        self.assertEqual(original["schedule_date"], "2026-09-21")
        self.assertEqual(result["replacement"]["kind"], "Replacement")
        self.assertEqual(result["replacement"]["replaces"], self.session)
        self.assertEqual(result["replacement"]["schedule_date"], "2026-09-22")
        # The fake site hands stored times back the way the driver does
        # (datetime.timedelta), so a defaulted postponement must still report
        # the same HH:MM:SS text the payload contract promises.
        self.assertEqual(result["replacement"]["from_time"], "09:00:00")
        self.assertEqual(result["replacement"]["to_time"], "10:00:00")
        self.assertEqual(self.site.get("Course Schedule",
                                       result["replacement"]["name"])[
                           "th_session_status"], "Scheduled")

    def test_postponement_is_bounded_by_the_policy_window(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.postpone_session(
                "postpone-0002", self.session, "late", "2026-11-30")
        self.assertIn("at most 14 day(s)", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.postpone_session(
                "postpone-0003", self.session, "earlier", "2026-09-20")
        self.assertIn("may not move before", str(ctx.exception))

    def test_postponement_is_refused_once_attendance_exists(self):
        self._attendance()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.postpone_session(
                "postpone-0004", self.session, "too late", "2026-09-22")
        self.assertIn("Attendance is already recorded", str(ctx.exception))
        self.assertEqual(self.site.get("Course Schedule", self.session)[
                           "th_session_status"], "Scheduled")

    def test_postponement_requires_the_policy_feature(self):
        self.ops.append_policy("2026-09-02", allow_postponement=0)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.postpone_session(
                "postpone-0005", self.session, "sick", "2026-09-22")
        self.assertIn("not permitted", str(ctx.exception))

    def test_a_make_up_requires_the_configured_approver_role(self):
        # Dual key: the command role alone is not enough when the owner pins a
        # different approver role for replacement sessions.
        self.ops.append_policy("2026-09-02",
                               replacement_approver_role="Academic Manager")
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.scheduling.schedule_replacement_session(
                "replacement-0001", self.session, "make-up",
                "2026-09-23", "09:00:00", "10:00:00")
        self.assertIn("Academic Manager", str(ctx.exception))

    def test_exactly_one_make_up_per_original_session(self):
        self.ops.scheduling.postpone_session(
            "postpone-0007", self.session, "sick", "2026-09-22",
            from_time="13:00:00", to_time="14:00:00")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.schedule_replacement_session(
                "replacement-0002", self.session, "again",
                "2026-09-23", "09:00:00", "10:00:00")
        self.assertIn("already exists", str(ctx.exception))

    def test_a_make_up_stays_inside_the_replacement_window(self):
        self.ops.scheduling.cancel_session("cancel-0001", self.session, "closed")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.schedule_replacement_session(
                "replacement-0003", self.session, "late make-up",
                "2026-10-30", "09:00:00", "10:00:00")
        self.assertIn("on or before 2026-10-12", str(ctx.exception))

    def test_a_replacement_needs_a_postponed_or_cancelled_original(self):
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.schedule_replacement_session(
                "replacement-0004", self.session, "why",
                "2026-09-22", "09:00:00", "10:00:00")
        self.assertIn("postponed or cancelled", str(ctx.exception))

    def test_cancellation_keeps_the_row_for_history(self):
        result = self.ops.scheduling.cancel_session(
            "cancel-0002", self.session, "power cut")
        self.assertEqual(result["status"], "Cancelled")
        stored = self.site.get("Course Schedule", self.session)
        self.assertEqual(stored["th_session_status"], "Cancelled")
        self.assertEqual(stored["th_session_note"], "power cut")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.cancel_session("cancel-0003", self.session, "x")
        self.assertIn("already Cancelled", str(ctx.exception))

    def test_cancellation_is_refused_once_attendance_exists(self):
        self._attendance()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.scheduling.cancel_session("cancel-0004", self.session, "x")
        self.assertIn("Attendance is already recorded", str(ctx.exception))

    def test_attendance_applies_to_scheduled_sessions_only(self):
        other = self.schedule(day="2026-09-22", key="schedule-0009")["name"]
        self.ops.scheduling.postpone_session(
            "postpone-0008", self.session, "sick", "2026-09-23")
        self.ops.scheduling.cancel_session("cancel-0005", other, "closed")
        for name in (self.session, other):
            with self.assertRaises(ValidationError) as ctx:
                self.ops.scheduling.assert_session_open_for_attendance(name)
            self.assertIn("attendance applies to Scheduled sessions only",
                          str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
