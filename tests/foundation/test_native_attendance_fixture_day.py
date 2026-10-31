"""Attendance correction qualification must work on every weekday and timezone date."""
from datetime import date, timedelta
import unittest

from tools.native.native_checks import previous_fixture_teaching_day


class NativeAttendanceFixtureDay(unittest.TestCase):
    def test_all_weekdays_keep_past_attendance_inside_correction_window(self):
        for offset in range(14):
            reference = date(2026, 10, 24) + timedelta(days=offset)
            with self.subTest(reference=reference):
                chosen = date.fromisoformat(previous_fixture_teaching_day(reference))
                self.assertLess(chosen, reference)
                self.assertNotEqual(chosen.weekday(), 4)
                self.assertLessEqual((reference - chosen).days, 7)
                if (reference - timedelta(days=1)).weekday() != 4:
                    self.assertEqual(chosen, reference - timedelta(days=1))

    def test_saturday_site_date_never_selects_friday(self):
        # UTC Friday evening can already be Saturday in the synthetic site's timezone.
        self.assertEqual(previous_fixture_teaching_day('2026-10-31'), '2026-10-29')

    def test_year_boundary_remains_in_the_past(self):
        self.assertEqual(previous_fixture_teaching_day('2027-01-01'), '2026-12-31')
