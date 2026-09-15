"""Pure local unit checks for thin enrollment policy. Not native Frappe qualification."""
import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import can_read, enrollment_is_eligible

ROOT = Path(__file__).resolve().parents[2]
ENROLLMENT = ROOT / "apps/toefl_house/toefl_house/enrollment/__init__.py"


class EnrollmentEligibilityTests(unittest.TestCase):
    def test_approved_accepted_converted_is_eligible(self):
        self.assertTrue(enrollment_is_eligible("Approved", 1, "EDU-STU-2026-00001"))

    def test_unconverted_denied(self):
        with self.assertRaises(ValueError):
            enrollment_is_eligible("Approved", 1, "")

    def test_unaccepted_denied(self):
        with self.assertRaises(ValueError):
            enrollment_is_eligible("Approved", 0, "EDU-STU-2026-00001")

    def test_conditional_denied(self):
        with self.assertRaises(ValueError):
            enrollment_is_eligible("Conditional", 1, "EDU-STU-2026-00001", conditions="Awaiting documents.")

    def test_rejected_denied(self):
        with self.assertRaises(ValueError):
            enrollment_is_eligible("Rejected", 0, "")

    def test_returning_student_denied(self):
        with self.assertRaises(ValueError):
            enrollment_is_eligible("Approved", 1, "EDU-STU-2026-00001", existing_student="EDU-STU-2025-00001")


class EnrollmentReadBoundaryTests(unittest.TestCase):
    def test_enrollment_officer_does_not_read_admission_or_keys(self):
        self.assertFalse(can_read("admission_decision", ["Enrollment Officer"], "u", "someone"))
        self.assertFalse(can_read("key", ["Enrollment Officer"], "u", "u"))
        self.assertFalse(can_read("manifest", ["Enrollment Officer"], "u", "someone"))
        self.assertFalse(can_read("decision", ["Enrollment Officer"], "u", "someone"))

    def test_enrollment_auditor_reads_operation_receipts_not_keys(self):
        self.assertTrue(can_read("audit", ["Enrollment Auditor"], "a", "someone"))
        self.assertTrue(can_read("operation", ["Enrollment Auditor"], "a", "someone"))
        self.assertFalse(can_read("key", ["Enrollment Auditor"], "a", "a"))
        self.assertFalse(can_read("admission_decision", ["Enrollment Auditor"], "a", "someone"))

    def test_admission_roles_do_not_gain_enrollment_read_via_union(self):
        self.assertFalse(can_read("key", ["Admission Officer"], "u", "u"))
        self.assertTrue(can_read("admission_decision", ["Admission Officer"], "u", "someone"))


class NestedWorkScopeTests(unittest.TestCase):
    def test_work_does_not_assign_enclosing_parameters(self):
        tree = ast.parse(ENROLLMENT.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            params = {arg.arg for arg in node.args.args}
            for child in node.body:
                if not (isinstance(child, ast.FunctionDef) and child.name == "work"):
                    continue
                assigned = set()
                for inner in ast.walk(child):
                    if isinstance(inner, ast.Assign):
                        for target in inner.targets:
                            if isinstance(target, ast.Name):
                                assigned.add(target.id)
                    if isinstance(inner, ast.AnnAssign) and isinstance(inner.target, ast.Name):
                        assigned.add(inner.target.id)
                overlap = sorted(assigned & params)
                self.assertEqual(
                    overlap,
                    [],
                    "%s.work assigns enclosing parameters %s (UnboundLocalError)"
                    % (node.name, overlap),
                )


if __name__ == "__main__":
    unittest.main()
