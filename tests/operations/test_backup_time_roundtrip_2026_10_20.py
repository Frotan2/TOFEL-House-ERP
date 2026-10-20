"""Regression: a saved Owner backup time must still validate after the database round trip.

Frappe returns a Time field as ``datetime.timedelta``; ``str(timedelta(hours=2, minutes=30))``
is ``"2:30:00"`` (no leading zero). Before this fix the strict HH:MM check refused every
schedule between 00:00 and 09:59 at validation time, although saving the same value succeeded.
The native check ``owner-operations-lifecycle-validated-gate-off-switch`` runs the same path
on a real site with 02:30.
"""
import ast
import re
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house" / "toefl_house"
          / "operations" / "owner_configuration.py")


def _load_backup_schedule_time():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_backup_schedule_time":
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {"re": re, "datetime": datetime, "timedelta": timedelta, "_clock_time": time}
            exec(compile(module, str(SOURCE), "exec"), namespace)
            return namespace["_backup_schedule_time"]
    raise AssertionError("_backup_schedule_time not found")


class BackupScheduleRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.parse = _load_backup_schedule_time()

    def test_string_values_still_accepted(self):
        self.assertEqual(self.parse("02:30"), "02:30")
        self.assertEqual(self.parse("23:59:00"), "23:59")

    def test_database_timedelta_before_ten_am_round_trips(self):
        # The exact failure seen on the real site: 02:30 -> timedelta -> "2:30:00".
        self.assertEqual(self.parse(timedelta(hours=2, minutes=30)), "02:30")

    def test_midnight_and_last_minute_round_trip(self):
        self.assertEqual(self.parse(timedelta(0)), "00:00")
        self.assertEqual(self.parse(timedelta(hours=23, minutes=59)), "23:59")

    def test_out_of_range_timedelta_is_refused(self):
        with self.assertRaises(ValueError):
            self.parse(timedelta(days=1))
        with self.assertRaises(ValueError):
            self.parse(timedelta(seconds=-1))

    def test_malformed_strings_are_still_refused(self):
        for bad in ("25:00", "2:30", "noon", "", None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                self.parse(bad)


if __name__ == "__main__":
    unittest.main()
