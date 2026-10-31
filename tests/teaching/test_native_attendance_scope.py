"""The guarded native controller cannot lend roster reads to another request."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
import importlib.util
from pathlib import Path
import sys
from threading import Event
import types
import unittest

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
NATIVE = "education.education.doctype.student_attendance.student_attendance"
OWNED = "toefl_house.teaching.native_attendance"


class AttendanceScopeTests(unittest.TestCase):
    def setUp(self):
        names = ["frappe", "education", "education.education", "education.education.doctype",
                 "education.education.doctype.student_attendance", NATIVE,
                 "toefl_house", "toefl_house.security", "toefl_house.teaching", OWNED]
        previous = {name: sys.modules.get(name) for name in names}

        def restore():
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        self.addCleanup(restore)
        for name in names:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        self.active = ContextVar("synthetic_attendance_command", default=False)
        self.operational = True
        self.member = True
        self.queries = []
        self.native_reads = []
        self.native = sys.modules[NATIVE]

        def native_roster(group):
            self.native_reads.append(group)
            raise PermissionError("Native Student Group permission denied")
        self.native.get_student_group_students = native_roster
        native_module = self.native

        class NativeAttendance:
            def __init__(self, **values):
                self.__dict__.update(course_schedule=None, student_group="OWN-GROUP", student="OWN-STUDENT")
                self.__dict__.update(values)

            def validate_student(self):
                return native_module.get_student_group_students(self.student_group)
        self.native.StudentAttendance = NativeAttendance
        frappe = sys.modules["frappe"]
        frappe.ValidationError = ValueError

        def sql(statement, values):
            self.queries.append((statement, values))
            return [("SYN-MEMBER",)] if self.member and values == ("OWN-GROUP", "OWN-STUDENT") else []
        frappe.db = types.SimpleNamespace(
            sql=sql, get_value=lambda *args: "OWN-GROUP",
        )
        security = sys.modules["toefl_house.security"]
        security.teaching_command_active = lambda doctype: self.active.get() and doctype == "Student Attendance"

        def require_operational():
            if not self.operational:
                raise PermissionError("Site refused")
        security.require_operational = require_operational
        spec = importlib.util.spec_from_file_location(OWNED, APP / "teaching/native_attendance.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[OWNED] = module
        spec.loader.exec_module(module)
        self.controller = module.THStudentAttendance

    def test_native_permission_remains_in_force_outside_command(self):
        with self.assertRaisesRegex(PermissionError, "Native Student Group"):
            self.controller().validate_student()
        self.assertEqual(self.queries, [])

    def test_authorized_membership_is_active_and_schedule_derived(self):
        token = self.active.set(True)
        try:
            self.controller(course_schedule="OWN-SESSION", student_group="FORGED-GROUP").validate_student()
        finally:
            self.active.reset(token)
        self.assertEqual(len(self.queries), 1)
        statement, values = self.queries[0]
        self.assertIn("active=1", statement)
        self.assertIn("limit 1", statement)
        self.assertEqual(values, ("OWN-GROUP", "OWN-STUDENT"))
        self.assertEqual(self.native_reads, [])

    def test_inactive_or_other_student_is_refused(self):
        token = self.active.set(True)
        try:
            self.member = False
            with self.assertRaisesRegex(ValueError, "active member"):
                self.controller().validate_student()
            self.member = True
            with self.assertRaisesRegex(ValueError, "active member"):
                self.controller(student="OTHER-STUDENT").validate_student()
        finally:
            self.active.reset(token)

    def test_refused_site_cannot_use_the_guarded_controller(self):
        self.operational = False
        with self.assertRaisesRegex(PermissionError, "Site refused"):
            self.controller().validate_student()
        self.assertEqual(self.queries, [])

    def test_concurrent_request_cannot_borrow_command_context(self):
        entered, release = Event(), Event()

        def guarded_request():
            token = self.active.set(True)
            try:
                self.controller().validate_student()
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Concurrent request did not finish")
            finally:
                self.active.reset(token)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(guarded_request)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(PermissionError):
                    self.controller().validate_student()
            finally:
                release.set()
            future.result(timeout=5)
        self.assertEqual(len(self.queries), 1)
        self.assertEqual(self.native_reads, ["OWN-GROUP"])

    def test_legacy_scope_never_replaces_education_global_accessor(self):
        source = (APP / "teaching/__init__.py").read_text(encoding="utf-8")
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "_roster_read")
        namespace = {"contextmanager": contextmanager, "frappe": sys.modules["frappe"]}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<real-roster-scope>", "exec"), namespace)
        original = self.native.get_student_group_students
        with namespace["_roster_read"]():
            self.assertIs(self.native.get_student_group_students, original)
            with self.assertRaises(PermissionError):
                self.native.get_student_group_students("OTHER-GROUP")
        self.assertIs(self.native.get_student_group_students, original)

    def test_native_hook_resolves_to_the_owned_subclass(self):
        hooks = ast.parse((APP / "hooks.py").read_text(encoding="utf-8"))
        mapping = next(ast.literal_eval(node.value) for node in hooks.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "override_doctype_class"
                               for target in node.targets))
        self.assertEqual(mapping["Student Attendance"], OWNED + ".THStudentAttendance")
