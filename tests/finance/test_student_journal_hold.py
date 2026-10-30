"""Fast policy boundaries; real Journal Entry calls run in Native CI."""
import importlib.util
import unittest
from pathlib import Path

POLICY = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/student_payout_policy.py"
spec = importlib.util.spec_from_file_location("student_journal_policy_under_test", POLICY)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
student_journal_write_allowed = policy.student_journal_write_allowed


class StudentJournalHoldTests(unittest.TestCase):
    def test_student_cash_and_fees_credit_surfaces_are_held(self):
        for rows in ([{"party_type": "Student"}],
                     [{"party_type": "Customer", "reference_type": "Fees"}],
                     [{"party_type": "Student", "reference_type": "Fees"}]):
            for method in (None, "validate", "before_submit", "before_update_after_submit"):
                with self.subTest(rows=rows, method=method):
                    self.assertFalse(student_journal_write_allowed(rows, method))

    def test_legacy_reversal_is_not_disabled(self):
        self.assertTrue(student_journal_write_allowed([{"party_type": "Student"}], "before_cancel"))

    def test_employee_payroll_supplier_and_operating_journals_remain_native(self):
        for party in ("Employee", "Supplier", "Customer", None):
            self.assertTrue(student_journal_write_allowed([{"party_type": party}], "validate"))


if __name__ == "__main__":
    unittest.main()
