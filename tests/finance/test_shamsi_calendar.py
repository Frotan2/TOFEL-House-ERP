"""Afghan Solar Hijri date-boundary acceptance independent of Frappe.

Dates below are known Nowruz boundaries; a 30-day Gregorian installment
approximation must not accidentally pass these business-calendar checks.
"""
import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[2] /
          "apps/toefl_house/toefl_house/finance/shamsi.py")
spec = importlib.util.spec_from_file_location("_shamsi_calendar_under_test", SOURCE)
shamsi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shamsi)


class AfghanShamsiTests(unittest.TestCase):
    def test_known_nowruz_and_leap_end_boundaries(self):
        examples = (
            ((1403, 1, 1), "2024-03-20"),
            ((1403, 12, 30), "2025-03-20"),
            ((1404, 1, 1), "2025-03-21"),
            ((1405, 1, 1), "2026-03-21"),
            ((1405, 7, 1), "2026-09-23"),
            ((1405, 8, 1), "2026-10-23"),
        )
        for solar, gregorian in examples:
            with self.subTest(solar=solar):
                self.assertEqual(str(shamsi.shamsi_to_gregorian(*solar)), gregorian)
                self.assertEqual(shamsi.gregorian_to_shamsi(gregorian), solar)
        self.assertTrue(shamsi.is_leap_year(1403))
        self.assertFalse(shamsi.is_leap_year(1404))
        with self.assertRaises(ValueError):
            shamsi.shamsi_to_gregorian(1404, 12, 30)

    def test_full_daily_round_trip_across_year_and_leap_boundaries(self):
        current = date(2023, 1, 1)
        last = date(2035, 1, 1)
        while current <= last:
            self.assertEqual(shamsi.shamsi_to_gregorian(
                *shamsi.gregorian_to_shamsi(current)), current)
            current += timedelta(days=1)

    def test_month_lengths_and_fiscal_year(self):
        self.assertEqual(shamsi.days_in_month(1405, 6), 31)
        self.assertEqual(shamsi.days_in_month(1405, 7), 30)
        self.assertEqual(shamsi.days_in_month(1403, 12), 30)
        self.assertEqual(shamsi.days_in_month(1404, 12), 29)
        self.assertEqual(tuple(str(x) for x in shamsi.fiscal_year_bounds(1404)),
                         ("2025-03-21", "2026-03-20"))
        self.assertEqual(tuple(str(x) for x in shamsi.month_bounds("1404-12")),
                         ("2026-02-20", "2026-03-20"))

    def test_semester_bounds_clamped_month_ends_on_the_last_day(self):
        # Sonbola 31 + 1 month ends Mehr 30, not 21 Mehr; Bahman 30 + 1
        # month ends Hoot 29, not 19 Hoot: a clamped day must not lose a
        # second day to the day-before rule.
        a, b = shamsi.semester_bounds("2026-09-22", 1)
        self.assertEqual((str(a), str(b)), ("2026-09-22", "2026-10-22"))
        a, b = shamsi.semester_bounds("2027-02-19", 1)
        self.assertEqual((str(a), str(b)), ("2027-02-19", "2027-03-20"))

    def test_two_solar_month_semester_not_sixty_gregorian_days(self):
        a, b = shamsi.semester_bounds("2026-09-23")
        self.assertEqual((str(a), str(b)), ("2026-09-23", "2026-11-21"))
        self.assertEqual((b - a).days + 1, 60)
        # The class has an independent start date, even when the student
        # joins late; the calendar doesn't create a new semester per student.
        a, b = shamsi.semester_bounds("2026-03-21")
        self.assertEqual((str(a), str(b)), ("2026-03-21", "2026-05-21"))
        self.assertEqual((b - a).days + 1, 62)

    def test_solar_month_due_dates_preferred_payday_and_optional_grace(self):
        dates = shamsi.monthly_due_dates("1405-06", 4)
        self.assertEqual(list(map(str, dates)), [
            "2026-08-23", "2026-09-23", "2026-10-23", "2026-11-22"])
        self.assertEqual(list(map(str, shamsi.monthly_due_dates("1405-07", 2, 3))),
                         ["2026-09-26", "2026-10-26"])
        self.assertEqual(str(shamsi.payroll_priority_date("1405-07")),
                         "2026-11-06")
        self.assertEqual(str(shamsi.payroll_following_month_end("1405-07")),
                         "2026-11-21")
        self.assertEqual(shamsi.month_key("2026-10-25"), "1405-08")
        self.assertEqual(shamsi.solar_month_label("1405-08"), "عقرب 1405")

    def test_only_fridays_are_generated_for_the_afghan_fiscal_year(self):
        holidays = shamsi.friday_holidays_for_fiscal_year(1405)
        first, last = shamsi.fiscal_year_bounds(1405)
        self.assertIn(len(holidays), (52, 53))
        self.assertEqual(len(set(holidays)), len(holidays))
        self.assertTrue(all(first <= d <= last and d.weekday() == 4
                            for d in holidays))
        self.assertFalse(any(d.weekday() in (5, 6) for d in holidays))

    def test_last_supported_year_1499_is_usable(self):
        # U-16: days_in_month(1499, 12) used to raise because
        # is_leap_year(1499) refused the last supported year. The leap
        # check now computes the 1500 Nowruz as a boundary only; 1500
        # itself stays unsupported.
        self.assertFalse(shamsi.is_leap_year(1499))
        self.assertEqual(shamsi.days_in_month(1499, 12), 29)
        self.assertEqual(tuple(str(x) for x in shamsi.month_bounds("1499-12")),
                         ("2121-02-20", "2121-03-20"))
        self.assertEqual(str(shamsi.shamsi_to_gregorian(1499, 12, 29)),
                         "2121-03-20")
        # Gregorian dates in early 2121 still belong to 1499 (its last
        # day is 2121-03-20); the 1500 Nowruz is the first out-of-range day.
        self.assertEqual(shamsi.gregorian_to_shamsi("2121-03-20"),
                         (1499, 12, 29))
        self.assertEqual(shamsi.gregorian_to_shamsi("2121-01-01"),
                         (1499, 10, 11))
        with self.assertRaises(ValueError):
            shamsi.gregorian_to_shamsi("2121-03-21")
        # The last supported fiscal year ends the day before the 1500
        # Nowruz (1499-12-29, inside the supported range), so its bounds
        # are computable with the 1500 Nowruz as a boundary only — the
        # same defect class as days_in_month(1499, 12). Its Friday list
        # works too.
        self.assertEqual(tuple(str(x) for x in shamsi.fiscal_year_bounds(1499)),
                         ("2120-03-21", "2121-03-20"))
        holidays = shamsi.friday_holidays_for_fiscal_year(1499)
        first, last = shamsi.fiscal_year_bounds(1499)
        self.assertIn(len(holidays), (52, 53))
        self.assertTrue(all(first <= d <= last and d.weekday() == 4
                            for d in holidays))
        # 1500 stays unsupported on every path.
        for call in (lambda: shamsi.is_leap_year(1500),
                     lambda: shamsi.days_in_month(1500, 1),
                     lambda: shamsi._nowruz(1500),
                     lambda: shamsi.fiscal_year_bounds(1500),
                     lambda: shamsi.following_month("1499-12")):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_invalid_dates_and_ambiguous_policy_inputs_fail_closed(self):
        for value in ("1405-8", "۱۴۰۵-۰۸", "1405-00", "1405-13", "2026-08", None):
            with self.subTest(period=value), self.assertRaises(ValueError):
                shamsi.parse_shamsi_month(value)
        for args in ((1405, 0, 1), (1405, 13, 1), (1405, 2, 32),
                     (1405, 12, 30), (True, 1, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                shamsi.shamsi_to_gregorian(*args)
        with self.assertRaises(ValueError):
            shamsi.monthly_due_dates("1405-07", True)
        with self.assertRaises(ValueError):
            shamsi.payroll_priority_date("1405-07", 30)
        with self.assertRaises(ValueError):
            shamsi.gregorian_to_shamsi("2099-45-01")


if __name__ == "__main__":
    unittest.main()
