"""Synthetic class creation and late-enrollment regressions against shipped commands.

The site and native Education adapter are in-memory stand-ins; these tests do
not claim a real Frappe, MariaDB, HTTP or browser run.
"""
import sys
import types
import unittest
from pathlib import Path

from tests.teaching.operations_site import OperationsSite, PermissionError_, ValidationError, load_real

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class ClassCreationJourney(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite(today="2026-09-23")
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.site.add("Program", name="GE-A1")
        self.site.add("Program", name="SPEAKING")
        self.site.add("Academic Year", name="1405")
        self.site.add("Academic Term", name="AUTUMN", academic_year="1405",
                      term_start_date="2026-09-23", term_end_date="2026-12-21")
        self.site.add("Branch", name="KABUL")
        self.site.add("Branch", name="OTHER")
        self.site.add("TH Program Level", name="GE-L1", native_program="GE-A1",
                      durations=[{"duration_unit": "Solar Hijri Month", "duration_value": 2,
                                  "effective_from": "2026-01-01"}])
        self.site.add("TH Program Level", name="SPEAKING-L1", native_program="SPEAKING",
                      durations=[{"duration_unit": "Week", "duration_value": 3,
                                  "effective_from": "2026-01-01"}])
        # Use the real pure duration resolver and real Solar Hijri converter.
        rules = load_real("academic_duration_test_rules", APP / "academic/rules.py")
        self.ops.teaching.resolve_duration = rules.resolve_duration
        finance = types.ModuleType("toefl_house.finance")
        finance.__path__ = [str(APP / "finance")]
        sys.modules["toefl_house.finance"] = finance
        load_real("toefl_house.finance.shamsi", APP / "finance/shamsi.py")

        native_name = "education.education.doctype.student_group.student_group"
        native = types.ModuleType(native_name)

        def enrolled(year, term, program):
            return [dict(student=row["student"], student_name=row["student"])
                    for row in self.site.all("Program Enrollment")
                    if row.get("program") == program and row.get("academic_year") == year
                    and (not term or row.get("academic_term") == term)
                    and row.get("docstatus") == 1]

        native.get_program_enrollment = enrolled
        sys.modules[native_name] = native
        self.branches = {"STU-1": "KABUL", "STU-2": "KABUL", "STU-3": "OTHER"}
        scope = types.ModuleType("toefl_house.command_scope")
        scope.resolve_creation_branch = lambda branch, actor: branch or ""
        scope.roster_for_branch = lambda rows, branch: [
            row for row in rows if not branch or self.branches.get(row["student"]) == branch]
        sys.modules["toefl_house.command_scope"] = scope
        for student in self.branches:
            self.ops.seed_student(student, student_name=student)
            self.ops.seed_enrollment(student, program="GE-A1", year="1405", term="AUTUMN")
        self.ops.seed_policy(effective_from="2026-09-01")

    def create(self, key="academic-create-0001", name="SYN-GE-A", **kwargs):
        args = dict(program="GE-A1", academic_year="1405", academic_term="AUTUMN",
                    max_strength=2, class_start_date="2026-09-23", branch="KABUL")
        args.update(kwargs)
        return self.ops.teaching.create_student_group(key, name, **args)

    def test_ge_window_and_late_join_keep_common_dates(self):
        first = self.create(students=["STU-1"])
        self.assertEqual((first["class_start_date"], first["class_end_date"]),
                         ("2026-09-23", "2026-11-21"))
        group = first["name"]
        self.site.today = "2026-10-05"
        joined = self.ops.teaching.add_class_member("academic-late-0001", group, "STU-2")
        self.assertEqual(joined["student"], "STU-2")
        stored = self.site.get("Student Group", group)
        self.assertEqual((stored["th_class_start_date"], stored["th_class_end_date"]),
                         ("2026-09-23", "2026-11-21"))
        self.assertEqual({r["student"] for r in self.site.all("Student Group Student")
                          if r["parent"] == group and r["active"]}, {"STU-1", "STU-2"})
        with self.assertRaisesRegex(ValidationError, "already an active member"):
            self.ops.teaching.add_class_member("academic-late-0002", group, "STU-2")

    def test_split_intake_into_two_classes_using_checked_student_ids(self):
        first = self.create(students="STU-1")
        second = self.create("academic-create-0002", "SYN-GE-B", students='["STU-2"]')
        self.assertEqual(first["roster"], ["STU-1"])
        self.assertEqual(second["roster"], ["STU-2"])
        self.assertEqual(first["class_end_date"], second["class_end_date"])

    def test_blank_selection_preserves_legacy_receipt_and_branch_scope_for_hq(self):
        result = self.create()
        self.assertEqual(result["roster"], ["STU-1", "STU-2"])
        kind, _, payload = self.site.commands[-1]
        self.assertEqual(kind, "create_student_group")
        self.assertNotIn("students", payload)

    def test_unenrolled_foreign_duplicate_and_malformed_selection_are_refused(self):
        for index, selection in enumerate(("STU-3", "STU-NOT-ENROLLED", "STU-1,STU-1",
                                          "[]", "[broken", ["STU-1", 3])):
            with self.subTest(selection=selection), self.assertRaises(ValidationError):
                self.create(f"academic-invalid-{index:04d}", f"SYN-INVALID-{index}", students=selection)
        self.assertEqual(self.site.all("Student Group"), [])

    def test_mismatched_solar_end_and_term_are_refused_before_insert(self):
        with self.assertRaisesRegex(ValidationError, "approved Solar"):
            self.create(class_end_date="2026-11-22", students=["STU-1"])
        self.site.get("Academic Term", "AUTUMN")["term_end_date"] = "2026-10-31"
        with self.assertRaisesRegex(ValidationError, "fit within"):
            self.create("academic-term-0002", students=["STU-1"])
        self.site.get("Academic Term", "AUTUMN").update(
            academic_year="1404", term_end_date="2026-12-21")
        with self.assertRaisesRegex(ValidationError, "selected academic year"):
            self.create("academic-term-0003", students=["STU-1"])
        self.assertEqual(self.site.all("Student Group"), [])

    def test_eap_also_uses_its_configured_two_solar_month_window(self):
        self.site.add("Program", name="EAP-A1")
        self.site.add("TH Program Level", name="EAP-L1", native_program="EAP-A1",
                      durations=[{"duration_unit": "Solar Hijri Month", "duration_value": 2,
                                  "effective_from": "2026-01-01"}])
        self.ops.seed_enrollment("STU-1", program="EAP-A1", year="1405", term="AUTUMN")
        result = self.create("academic-eap-0001", "SYN-EAP", program="EAP-A1", students=["STU-1"])
        self.assertEqual((result["class_start_date"], result["class_end_date"]),
                         ("2026-09-23", "2026-11-21"))

    def test_speaking_uses_its_own_three_week_duration(self):
        self.ops.seed_enrollment("STU-1", program="SPEAKING", year="1405", term="AUTUMN")
        result = self.create("academic-speaking-0001", "SYN-SPEAK", program="SPEAKING",
                             students=["STU-1"])
        self.assertEqual(result["class_end_date"], "2026-10-14")


class InstructorScopeTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite(today="2026-10-05")
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.site.add("Employee", name="EMP-1", user_id="teacher", status="Active")
        self.site.add("Instructor", name="T1", employee="EMP-1", status="Active")
        self.site.add("TH Teaching Assignment", name="ASSIGN-1", student_group="G1",
                      instructor="T1", effective_start="2026-09-01", effective_end=None,
                      course_schedule=None)
        self.session = types.SimpleNamespace(student_group="G1", instructor="T1", schedule_date="2026-09-22")

    def require(self, name="S1"):
        return self.ops.teaching._require_own_instructor_session("teacher", self.session, name)

    def test_current_assignment_must_cover_both_today_and_session(self):
        self.require()
        assignment = self.site.get("TH Teaching Assignment", "ASSIGN-1")
        for update in ({"effective_end": "2026-09-30"},
                       {"effective_start": "2026-09-23", "effective_end": None},
                       {"effective_start": "2026-11-01", "effective_end": None},
                       {"effective_start": "2026-09-01", "effective_end": "not-a-date"}):
            assignment.update(update)
            with self.subTest(update=update), self.assertRaises(PermissionError_):
                self.require()

    def test_specific_session_cross_instructor_and_ambiguous_identity_are_denied(self):
        assignment = self.site.get("TH Teaching Assignment", "ASSIGN-1")
        assignment["course_schedule"] = "S1"
        self.require("S1")
        with self.assertRaises(PermissionError_):
            self.require("S2")
        self.session.instructor = "T2"
        with self.assertRaises(PermissionError_):
            self.require()
        self.session.instructor = "T1"
        self.site.add("Instructor", name="T2", employee="EMP-1", status="Active")
        with self.assertRaises(PermissionError_):
            self.require()
        self.site.get("Instructor", "T2")["status"] = "Left"
        self.require()
        self.site.add("Employee", name="EMP-2", user_id="teacher", status="Active")
        with self.assertRaises(PermissionError_):
            self.require()


class AttendanceTruthTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite(today="2026-09-22")
        self.addCleanup(self.ops.close)
        self.ops.seed_class(name="GRP-A", members=["STU-1"])
        self.ops.seed_student("STU-1")
        self.session = self.ops.seed_session(group="GRP-A", date="2026-09-23")

    def test_future_session_cannot_be_recorded_by_either_attendance_path(self):
        # Model an otherwise authorized instructor; identity and revocation
        # have separate command-scope regressions.
        self.ops.teaching._require_own_instructor_session = lambda *args: None
        for endpoint in (self.ops.teaching.record_attendance,
                         self.ops.teaching.record_instructor_attendance):
            with self.subTest(endpoint=endpoint.__name__), self.assertRaisesRegex(ValidationError, "future session"):
                endpoint("future-attendance-0001", self.session, {"STU-1": "Present"})
        self.assertEqual(self.ops.site.all("Student Attendance"), [])

    def test_planned_class_cannot_accept_attendance(self):
        self.ops.site.today = "2026-09-23"
        self.ops.site.get("Student Group", "GRP-A")["th_class_status"] = "Planned"
        with self.assertRaisesRegex(ValidationError, "unless.*Active"):
            self.ops.teaching.record_attendance("planned-attendance-0001", self.session, {"STU-1": "Present"})
        self.assertEqual(self.ops.site.all("Student Attendance"), [])


if __name__ == "__main__":
    unittest.main()
