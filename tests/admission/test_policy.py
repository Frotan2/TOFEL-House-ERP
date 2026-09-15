"""Pure local unit checks for thin admission policy. Not native Frappe qualification."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (ADMISSION_OUTCOMES, ADMISSION_TRANSITIONS, can_read,
                                is_admission_transition, validate_admission_text)


class AdmissionTransitionTests(unittest.TestCase):
    def test_locked_transitions(self):
        self.assertTrue(is_admission_transition("Draft", "Review"))
        self.assertTrue(is_admission_transition("Review", "Approved"))
        self.assertTrue(is_admission_transition("Review", "Conditional"))
        self.assertTrue(is_admission_transition("Review", "Rejected"))
        self.assertTrue(is_admission_transition("Approved", "Revoked"))
        self.assertTrue(is_admission_transition("Draft", "Withdrawn"))
        self.assertTrue(is_admission_transition("Review", "Withdrawn"))
        self.assertTrue(is_admission_transition("Approved", "Expired"))
        self.assertTrue(is_admission_transition("Conditional", "Expired"))
        self.assertFalse(is_admission_transition("Draft", "Approved"))
        self.assertFalse(is_admission_transition("Approved", "Review"))
        self.assertFalse(is_admission_transition("Rejected", "Approved"))
        self.assertFalse(is_admission_transition("Conditional", "Approved"))
        self.assertNotIn(("Approved", "Enrolled"), ADMISSION_TRANSITIONS)
        self.assertEqual(ADMISSION_OUTCOMES,
                         ("Approved", "Conditional", "Deferred", "Rejected"))

    def test_reason_bounds(self):
        self.assertEqual(validate_admission_text("Eligible after placement.", "reason"),
                         "Eligible after placement.")
        with self.assertRaises(ValueError):
            validate_admission_text("short", "reason")
        with self.assertRaises(ValueError):
            validate_admission_text("x" * 501, "reason")
        with self.assertRaises(ValueError):
            validate_admission_text(None, "reason")


class AdmissionReadBoundaryTests(unittest.TestCase):
    def test_admission_staff_read_decision_not_keys(self):
        for role in ("Admission Officer", "Admission Reviewer",
                     "Admission Approver", "Admission Auditor"):
            self.assertTrue(can_read("admission_decision", [role], "u", "someone"))
            self.assertFalse(can_read("key", [role], "u", "u"))
            self.assertFalse(can_read("manifest", [role], "u", "someone"))
            self.assertFalse(can_read("decision", [role], "u", "someone"))

    def test_placement_roles_do_not_read_admission(self):
        for role in ("Placement Author", "Placement Publisher", "Placement Auditor",
                     "Placement Invigilator", "Placement Assessor", "Placement Reviewer",
                     "Placement Releaser"):
            with self.subTest(role=role):
                self.assertFalse(can_read("admission_decision", [role], "u", "someone"))

    def test_admission_auditor_reads_operation_receipts(self):
        self.assertTrue(can_read("audit", ["Admission Auditor"], "a", "someone"))
        self.assertTrue(can_read("operation", ["Admission Auditor"], "a", "someone"))
        self.assertFalse(can_read("admission_decision", ["Placement Auditor"], "a", "someone"))


if __name__ == "__main__":
    unittest.main()
