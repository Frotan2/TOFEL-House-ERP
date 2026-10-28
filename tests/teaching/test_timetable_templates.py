"""Mission 3 weekly timetable templates: the pattern, never a second timetable.

A template stores only the weekly pattern (weekday, window, course, optional
room/instructor). Materializing it produces ordinary native Course Schedule
rows through the same conflict validation as a hand-scheduled session, so the
suite checks the pattern rules (no overlapping or duplicate slots), the
deterministic bounded expansion, and that template edits cannot rewrite
sessions already generated.
"""
import unittest

from tests.teaching.operations_site import (
    COURSE_OWNER, OperationsSite, ValidationError)


class SlotValidationTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.templates = self.ops.timetables

    def _slot(self, **overrides):
        slot = {"weekday": "Mon", "from_time": "09:00:00",
                "to_time": "10:00:00", "course": "ENG-101", "room": "",
                "instructor": ""}
        slot.update(overrides)
        return slot

    def test_slots_are_normalized_and_ordered_by_weekday(self):
        slots = self.templates.validate_slots([
            self._slot(weekday="Wed", from_time="13:00:00", to_time="14:00:00"),
            self._slot(weekday="Mon")])
        self.assertEqual([row["weekday"] for row in slots], ["Mon", "Wed"])

    def test_an_unknown_weekday_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([self._slot(weekday="Funday")])
        self.assertIn("Unknown weekday 'Funday'", str(ctx.exception))

    def test_overlapping_slots_on_one_weekday_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([
                self._slot(),
                self._slot(from_time="09:30:00", to_time="10:30:00")])
        self.assertIn("slots overlap on Mon", str(ctx.exception))
        # The same window on a different weekday is fine.
        slots = self.templates.validate_slots([
            self._slot(), self._slot(weekday="Tue")])
        self.assertEqual(len(slots), 2)

    def test_exact_duplicates_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([self._slot(), self._slot()])
        self.assertIn("Duplicate timetable slot on Mon", str(ctx.exception))

    def test_slot_integrity_and_bounds(self):
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([self._slot(course="")])
        self.assertIn("Slot course is required", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([self._slot(from_time="10:00:00",
                                                      to_time="10:00:00")])
        self.assertIn("strictly before", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([])
        self.assertIn("1 to 40", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.templates.validate_slots([self._slot()] * 41)
        self.assertIn("1 to 40", str(ctx.exception))

    def test_a_json_payload_is_accepted_like_the_desk_sends_it(self):
        slots = self.templates.validate_slots(
            '[{"weekday": "Tue", "from_time": "08:00", "to_time": "09:30",'
            ' "course": "ENG-101"}]')
        self.assertEqual(slots[0]["from_time"], "08:00:00")
        self.assertEqual(self.ops.policy.session_minutes(
            slots[0]["from_time"], slots[0]["to_time"]), 90)


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.templates = self.ops.timetables
        self.slots = [
            {"weekday": "Mon", "from_time": "09:00:00", "to_time": "10:00:00",
             "course": "ENG-101", "room": "", "instructor": ""},
            {"weekday": "Tue", "from_time": "11:00:00", "to_time": "12:00:00",
             "course": "ENG-101", "room": "", "instructor": ""},
        ]

    def test_expansion_skips_non_teaching_weekdays_and_blocked_dates(self):
        candidates = self.templates.expand_slots(
            self.slots, "2026-09-21", "2026-09-30", ("Mon", "Tue"),
            {"2026-09-28", "2026-09-29"})
        self.assertEqual([row["schedule_date"] for row in candidates],
                         ["2026-09-21", "2026-09-22"])

    def test_expansion_is_deterministic_and_bounded(self):
        first = self.templates.expand_slots(
            self.slots, "2026-09-21", "2026-09-30", ("Mon", "Tue"), {})
        second = self.templates.expand_slots(
            self.slots, "2026-09-21", "2026-09-30", ("Mon", "Tue"), {})
        self.assertEqual(first, second)
        with self.assertRaises(ValueError) as ctx:
            self.templates.expand_slots(self.slots, "2026-01-01",
                                        "2027-06-01", ("Mon",), {})
        self.assertIn("exceeds 366 days", str(ctx.exception))

    def test_an_inverted_range_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.templates.expand_slots(self.slots, "2026-09-30",
                                        "2026-09-21", ("Mon",), {})
        self.assertIn("precedes its start", str(ctx.exception))


class TemplateCommandTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.templates = self.ops.timetables
        self.site.user = COURSE_OWNER
        self.site.add("Program", name="TH-PROG", program_name="English")
        self.site.add("Branch", name="BR-KABUL", branch_name="Kabul")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Room", name="ROOM-1", room_name="ROOM-1",
                      seating_capacity=30)
        self.site.add("Instructor", name="INS-1", instructor_name="INS-1")

    def test_create_normalizes_and_refuses_duplicates_or_unknown_refs(self):
        result = self.templates.create_timetable_template(
            "template-create-0001", "tt-1", "Morning cohort", "TH-PROG",
            "BR-KABUL", "On-site", "weekday mornings")
        self.assertEqual(result["name"], "TT-1")
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["delivery_mode"], "On-site")
        with self.assertRaises(ValidationError) as ctx:
            self.templates.create_timetable_template(
                "template-create-0002", "TT-1", "Again", "", "", "On-site", "")
        self.assertIn("already exists", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.templates.create_timetable_template(
                "template-create-0003", "TT-2", "X", "TH-NONE", "", "On-site",
                "")
        self.assertIn("Unknown program", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.templates.create_timetable_template(
                "template-create-0004", "TT-3", "X", "", "", "Evening", "")
        self.assertIn("Delivery mode must be one of", str(ctx.exception))

    def test_setting_slots_replaces_the_whole_pattern_and_checks_references(self):
        self.ops.seed_template(slots=[{"weekday": "Mon",
                                       "from_time": "09:00:00",
                                       "to_time": "10:00:00",
                                       "course": "ENG-101"}])
        slots = '[{"weekday": "Tue", "from_time": "13:00:00",' \
                ' "to_time": "14:00:00", "course": "ENG-101",' \
                ' "room": "ROOM-1", "instructor": "INS-1"}]'
        result = self.templates.set_timetable_slots(
            "template-slots-0001", "TT-1", slots, "afternoon cohort")
        self.assertEqual(result["slot_count"], 1)
        self.assertEqual(result["slots"][0]["weekday"], "Tue")
        with self.assertRaises(ValidationError) as ctx:
            self.templates.set_timetable_slots(
                "template-slots-0002", "TT-1",
                '[{"weekday": "Mon", "from_time": "09:00:00",'
                ' "to_time": "10:00:00", "course": "ENG-999"}]', "typo")
        self.assertIn("Unknown course: ENG-999", str(ctx.exception))

    def test_a_retired_template_cannot_be_edited_or_generated(self):
        self.ops.seed_template(slots=[])
        self.templates.set_timetable_template_status(
            "template-status-0001", "TT-1", False)
        with self.assertRaises(ValidationError) as ctx:
            self.templates.set_timetable_slots(
                "template-slots-0003", "TT-1",
                '[{"weekday": "Mon", "from_time": "09:00:00",'
                ' "to_time": "10:00:00", "course": "ENG-101"}]', "no")
        self.assertIn("retired", str(ctx.exception))

    def test_editing_a_template_never_rewrites_generated_sessions(self):
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=2, members=["STU-1"])
        self.ops.seed_instructor("INS-1")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")
        self.ops.seed_template(slots=[{"weekday": "Mon",
                                       "from_time": "09:00:00",
                                       "to_time": "10:00:00",
                                       "course": "ENG-101",
                                       "room": "ROOM-1",
                                       "instructor": "INS-1"}])
        generated = self.ops.scheduling.generate_timetable(
            "template-generate-0001", "GRP-A", "TT-1", "2026-09-21",
            "2026-09-21")
        session = generated["sessions"][0]["name"]
        self.templates.set_timetable_slots(
            "template-slots-0004", "TT-1",
            '[{"weekday": "Mon", "from_time": "11:00:00",'
            ' "to_time": "12:00:00", "course": "ENG-101"}]', "moved later")
        stored = self.site.get("Course Schedule", session)
        self.assertEqual(stored["from_time"], "09:00:00")
        self.assertEqual(stored["to_time"], "10:00:00")


if __name__ == "__main__":
    unittest.main()
