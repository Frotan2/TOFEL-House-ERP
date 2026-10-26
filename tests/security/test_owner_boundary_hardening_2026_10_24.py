"""Regression contracts for branch-scope and maker/checker privilege boundaries."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


def source(path, fn):
    text = (ROOT / path).read_text(encoding="utf-8")
    mod = ast.parse(text)
    node = next(n for n in mod.body
                if isinstance(n, ast.FunctionDef) and n.name == fn)
    return ast.get_source_segment(text, node)


class SecurityHardeningContracts(unittest.TestCase):
    def test_scoped_filter_intersection_rejects_bypasses(self):
        statement = source("desk/__init__.py", "_intersect_scope_filter")
        # The pure helper is isolated from Desk and DB imports.
        namespace = {"frappe": type("Frappe", (), {"ValidationError": ValueError})()}
        exec(compile(statement, "<scope-helper>", "exec"), namespace)
        f = namespace["_intersect_scope_filter"]
        self.assertEqual(f("student-2", ["student-1"]), ("in", []))
        self.assertEqual(f(("in", ["s2", "s1"]), ["s1"]), ("in", ["s1"]))
        self.assertEqual(f(("=", "s1"), ["s1"]), ("in", ["s1"]))
        self.assertEqual(f("s1", ["s1"]), ("in", ["s1"]))
        with self.assertRaises(ValueError):
            f(("not in", ["s1"]), ["s1"])

    def test_attendance_uses_active_roster_and_open_class(self):
        self.assertIn("active=1", (ROOT / "teaching/native_attendance.py").read_text())
        self.assertNotIn("native.get_student_group_students =", source("teaching/__init__.py", "_roster_read"))
        attendance = source("teaching/__init__.py", "_record_attendance")
        self.assertIn("active=1", attendance)
        self.assertIn("_TERMINAL_CLASS_STATUSES", attendance)
        self.assertIn("group.disabled", attendance)
        self.assertIn("_require_own_instructor_session(actor, session, schedule_name)", attendance)
        for role_path in ("record_attendance", "record_instructor_attendance"):
            self.assertIn("_record_attendance(", source("teaching/__init__.py", role_path))

    def test_business_admin_rejects_system_identity(self):
        self.assertIn("PROTECTED_USERS", source("administration.py", "_require_control_role"))
        mutable = source("administration.py", "set_managed_role")
        self.assertIn("PROTECTED_USERS", mutable)
        self.assertIn('if "Course Owner" not in actor_roles:', mutable)

    def test_separate_approver_for_corrections(self):
        for fn in ("approve_invoice_correction", "approve_fees_correction"):
            text = source("finance/corrections.py", fn)
            self.assertIn('getattr(req, "owner", None)', text)
            self.assertIn("frappe.PermissionError", text)
        att = source("teaching/attendance_corrections.py", "approve_attendance_correction")
        self.assertIn('getattr(req, "requested_by", None)', att)

    def test_correction_requests_scope_fee_and_sale(self):
        text = source("desk/__init__.py", "_branch_allowed_names")
        self.assertIn('"sales_invoice"', text)
        self.assertIn('"fees"', text)


if __name__ == "__main__":
    unittest.main()
