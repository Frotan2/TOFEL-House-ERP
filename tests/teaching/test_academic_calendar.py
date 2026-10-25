"""Mission 3 configurable academic calendars: holidays, closures, reopenings.

A calendar answers one question — may teaching happen on this date — and the
owner's configuration is the only source of that answer. The suite proves the
precedence rules (branch over global, explicit Working Day over a closure),
that a calendar change can never rewrite a session already scheduled, and that
the calendar itself is only writable through the guarded owner commands.
"""
import unittest

from tests.teaching.operations_site import (
    COURSE_OWNER, OperationsSite, ValidationError)


class CalendarRuleTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.calendars = self.ops.calendars

    def test_a_branch_calendar_outranks_the_global_calendar(self):
        rows = [{"branch": "", "kind": "Holiday"},
                {"branch": "BR-KABUL", "kind": "Working Day"}]
        self.assertEqual(self.calendars.resolve_day_kinds(rows, "BR-KABUL"),
                         "Working Day")
        self.assertEqual(self.calendars.resolve_day_kinds(rows, "BR-HERAT"),
                         "Holiday")

    def test_an_explicit_working_day_reopens_an_equally_specific_closure(self):
        rows = [{"branch": "", "kind": "Closed"},
                {"branch": "", "kind": "Working Day"}]
        self.assertEqual(self.calendars.resolve_day_kinds(rows, ""),
                         "Working Day")
        rows = [{"branch": "", "kind": "Closed"},
                {"branch": "", "kind": "Holiday"}]
        self.assertEqual(self.calendars.resolve_day_kinds(rows, ""), "Closed")

    def test_no_matching_row_means_no_restriction(self):
        self.assertEqual(self.calendars.resolve_day_kinds([], "BR-KABUL"), "")
        self.assertEqual(self.calendars.resolve_day_kinds(
            [{"branch": "BR-HERAT", "kind": "Holiday"}], "BR-KABUL"), "")

    def test_weekday_matching_uses_the_configured_teaching_days(self):
        matches = self.calendars.weekday_matches
        self.assertTrue(matches("2026-09-21", ("Mon", "Tue")))
        self.assertFalse(matches("2026-09-25", ("Mon", "Tue")))
        self.assertEqual(self.calendars.weekday_code("2026-09-21"), "Mon")

    def test_refusal_messages_name_the_reason(self):
        refusal = self.calendars.teaching_refusal(
            "2026-09-24", ("Mon", "Tue", "Wed", "Thu"),
            {"2026-09-24": "Holiday"})
        self.assertEqual(refusal, "2026-09-24 is a Holiday day in the academic calendar")
        refusal = self.calendars.teaching_refusal("2026-09-25", ("Mon",),
                                                  {})
        self.assertIn("is a Fri", refusal)
        self.assertIn("does not teach", refusal)
        self.assertIn("Friday", self.calendars.teaching_refusal(
            "2026-09-25", None, {}))
        self.assertIn("Friday", self.calendars.teaching_refusal(
            "2026-09-25", ("Fri",), {}))
        # Exceptional Friday opening must be an explicit Course Owner
        # calendar day, not a weekly policy that quietly changes holidays.
        self.assertEqual(self.calendars.teaching_refusal(
            "2026-09-25", ("Mon",),
            {"2026-09-25": "Working Day"}), "")
        self.assertIn("Friday", self.calendars.teaching_refusal(
            "2026-10-02", ("Mon",),
            {"2026-09-25": "Working Day"}))

    def test_blocked_dates_are_only_the_blocking_kinds(self):
        plan = {"2026-09-21": "Holiday", "2026-09-22": "Working Day",
                "2026-09-23": "Closed", "2026-09-24": ""}
        self.assertEqual(self.ops.calendars.blocked_dates(plan),
                         {"2026-09-21", "2026-09-23"})


class CalendarPlanningTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.calendars = self.ops.calendars

    def test_plan_merges_active_calendars_of_the_same_year_and_branch(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-24", "kind": "Holiday"}])
        self.ops.seed_calendar(code="CAL-OLD", year="2025-26",
                               days=[{"date": "2026-09-24", "kind": "Holiday"}])
        self.ops.seed_calendar(code="CAL-BR", branch="BR-KABUL",
                               days=[{"date": "2026-09-24",
                                      "kind": "Working Day"}])
        global_plan = self.calendars.calendar_plan(
            "2026-09-21", "2026-09-30", "2026-27", "")
        self.assertEqual(global_plan["2026-09-24"], "Holiday")
        branch_plan = self.calendars.calendar_plan(
            "2026-09-21", "2026-09-30", "2026-27", "BR-KABUL")
        self.assertEqual(branch_plan["2026-09-24"], "Working Day")

    def test_a_retired_calendar_stops_applying_but_keeps_its_days(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-24", "kind": "Holiday"}])
        self.site.user = COURSE_OWNER
        self.calendars.set_academic_calendar_status(
            "calendar-status-0001", "CAL-2026", False)
        self.assertEqual(self.calendars.calendar_plan(
            "2026-09-21", "2026-09-30", "2026-27", ""), {})
        stored = self.site.get("TH Academic Calendar", "CAL-2026")
        self.assertEqual(stored["status"], "Retired")
        self.assertEqual(len(stored["days"]), 1)

    def test_the_plan_reads_only_the_requested_range(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-24", "kind": "Holiday"},
                                     {"date": "2026-12-25", "kind": "Holiday"}])
        plan = self.calendars.calendar_plan("2026-09-21", "2026-09-30",
                                            "2026-27", "")
        self.assertEqual(list(plan), ["2026-09-24"])

    def test_assert_teaching_allowed_refuses_a_holiday_and_a_closed_day(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-24", "kind": "Holiday"},
                                     {"date": "2026-09-27", "kind": "Closed"}])
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.assert_teaching_allowed(
                "2026-09-24", ("Mon", "Tue", "Wed", "Thu"), "2026-27", "")
        self.assertIn("Holiday day", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.assert_teaching_allowed(
                "2026-09-27", None, "2026-27", "")
        self.assertIn("Closed day", str(ctx.exception))
        self.assertEqual(self.calendars.assert_teaching_allowed(
            "2026-09-22", ("Mon", "Tue"), "2026-27", ""), "2026-09-22")

    def test_next_teaching_days_skips_weekends_and_closures(self):
        self.ops.seed_calendar(days=[{"date": "2026-09-24", "kind": "Holiday"}])
        days = self.calendars.next_teaching_days(
            "2026-09-23", 4, ("Mon", "Tue", "Wed", "Thu"), "2026-27", "")
        self.assertEqual(days, ["2026-09-23", "2026-09-28", "2026-09-29",
                                "2026-09-30"])


class CalendarCommandTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.calendars = self.ops.calendars
        self.site.user = COURSE_OWNER
        self.site.add("Academic Year", name="2026-27")
        self.site.add("Branch", name="BR-KABUL", branch_name="Kabul")

    def test_create_normalizes_the_code_and_refuses_duplicates(self):
        result = self.calendars.create_academic_calendar(
            "calendar-create-0001", "cal-2026", "Institute calendar",
            "2026-27", "BR-KABUL", "national holidays")
        self.assertEqual(result["name"], "CAL-2026")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["academic_year"], "2026-27")
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.create_academic_calendar(
                "calendar-create-0002", "CAL-2026", "Again", "", "", "")
        self.assertIn("already exists", str(ctx.exception))

    def test_create_refuses_unknown_references(self):
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.create_academic_calendar(
                "calendar-create-0003", "CAL-X", "X", "2027-28", "", "")
        self.assertIn("Unknown academic year", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.create_academic_calendar(
                "calendar-create-0004", "CAL-Y", "Y", "", "BR-NONE", "")
        self.assertIn("Unknown branch", str(ctx.exception))

    def test_days_are_appended_once_and_only_to_an_active_calendar(self):
        self.ops.seed_calendar(days=[])
        self.calendars.add_academic_calendar_day(
            "calendar-day-0001", "CAL-2026", "2026-09-24", "Holiday",
            "national day")
        doc = self.site.get("TH Academic Calendar", "CAL-2026")
        self.assertEqual(doc["days"][0]["date"], "2026-09-24")
        self.assertEqual(doc["days"][0]["kind"], "Holiday")
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.add_academic_calendar_day(
                "calendar-day-0002", "CAL-2026", "2026-09-24", "Closed", "")
        self.assertIn("already recorded", str(ctx.exception))
        self.calendars.set_academic_calendar_status(
            "calendar-retire-0001", "CAL-2026", False)
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.add_academic_calendar_day(
                "calendar-day-0003", "CAL-2026", "2026-09-25", "Holiday", "")
        self.assertIn("retired calendar", str(ctx.exception))

    def test_a_day_kind_must_be_one_of_the_three(self):
        self.ops.seed_calendar(days=[])
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.add_academic_calendar_day(
                "calendar-day-0004", "CAL-2026", "2026-09-24", "Half Day", "")
        self.assertIn("Holiday, Closed or Working Day", str(ctx.exception))

    def test_removing_a_day_requires_a_reason_and_keeps_the_rest(self):
        self.ops.seed_calendar(days=[
            {"date": "2026-09-24", "kind": "Holiday"},
            {"date": "2026-09-27", "kind": "Closed"}])
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.remove_academic_calendar_day(
                "calendar-remove-0001", "CAL-2026", "2026-09-24", "")
        self.assertIn("reason is required", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.calendars.remove_academic_calendar_day(
                "calendar-remove-0002", "CAL-2026", "2026-10-01", "fix")
        self.assertIn("is not recorded", str(ctx.exception))
        self.calendars.remove_academic_calendar_day(
            "calendar-remove-0003", "CAL-2026", "2026-09-24", "closure moved")
        stored = self.site.get("TH Academic Calendar", "CAL-2026")
        self.assertEqual([row["date"] for row in stored["days"]],
                         ["2026-09-27"])

    def test_a_later_calendar_change_never_rewrites_a_scheduled_session(self):
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=2, members=["STU-1"])
        self.ops.seed_room("ROOM-1")
        self.ops.seed_instructor("INS-1")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")
        session = self.ops.teaching.schedule_session(
            "calendar-session-0001", "GRP-A", "2026-09-21", "09:00:00",
            "10:00:00", "INS-1", "ROOM-1", "ENG-101")
        self.ops.seed_calendar(days=[{"date": "2026-09-21",
                                      "kind": "Holiday"}])
        stored = self.site.get("Course Schedule", session["name"])
        self.assertEqual(stored["schedule_date"], "2026-09-21")
        self.assertEqual(stored["th_session_status"], "Scheduled")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.teaching.schedule_session(
                "calendar-session-0002", "GRP-A", "2026-09-21", "11:00:00",
                "12:00:00", "INS-1", "ROOM-1", "ENG-101")
        self.assertIn("Holiday day in the academic calendar",
                      str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
