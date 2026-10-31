"""Safety regression for direct native Student Pay disbursement hold."""
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP))
# D2: student_payout_policy is pure, but importing it through the
# toefl_house.finance package runs finance/__init__, which imports
# frappe. Register stub packages pointing at the real directories so
# only the pure submodule loads, then restore the previous entries
# (the imported function stays bound). No product code changes.
import types as _types  # noqa: E402
_previous = {name: sys.modules.get(name)  # noqa: E402
             for name in ("toefl_house", "toefl_house.finance")}
_root = _types.ModuleType("toefl_house")  # noqa: E402
_root.__path__ = [str(APP / "toefl_house")]
_finance = _types.ModuleType("toefl_house.finance")  # noqa: E402
_finance.__path__ = [str(APP / "toefl_house" / "finance")]
sys.modules["toefl_house"] = _root
sys.modules["toefl_house.finance"] = _finance
from toefl_house.finance.student_payout_policy import (  # noqa: E402
    student_pay_write_allowed,
)
for _name, _old in _previous.items():
    if _old is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _old


class StudentPayoutHoldTests(unittest.TestCase):
    def test_new_student_pay_denied_across_new_write_surfaces(self):
        for method in (None, "validate", "before_submit",
                       "before_update_after_submit", ""):
            with self.subTest(method=method):
                self.assertFalse(student_pay_write_allowed("Pay", "Student", method))

    def test_preexisting_student_pay_may_be_cancelled(self):
        self.assertTrue(student_pay_write_allowed("Pay", "Student", "before_cancel"))

    def test_student_receipts_are_not_affected(self):
        for method in (None, "validate", "before_cancel", "before_update_after_submit"):
            with self.subTest(method=method):
                self.assertTrue(student_pay_write_allowed("Receive", "Student", method))

    def test_supplier_payment_and_cash_handover_unchanged(self):
        for party_type in ("Supplier", "Customer", "Employee"):
            self.assertTrue(student_pay_write_allowed("Pay", party_type, None))
        self.assertTrue(student_pay_write_allowed("Internal Transfer", None, None))

    def test_real_hook_enforces_guard_before_native_customer_refund_path(self):
        source = (APP / "toefl_house" / "finance" / "refunds.py").read_text("utf-8")
        hooks = (APP / "toefl_house" / "hooks.py").read_text("utf-8")
        self.assertIn("from toefl_house.finance.student_payout_policy import student_pay_write_allowed", source)
        self.assertIn("if not student_pay_write_allowed(", source)
        self.assertIn("Direct Student Pay is denied.", source)
        self.assertIn('"before_cancel": "toefl_house.finance.refunds.guard_payment_entry"', hooks)
        self.assertIn('"validate": "toefl_house.finance.refunds.guard_payment_entry"', hooks)
        self.assertIn('"before_update_after_submit": "toefl_house.finance.refunds.guard_payment_entry"', hooks)
        self.assertLess(source.index("if not student_pay_write_allowed("),
                        source.index("if refund_permitted(doc, existing="))


if __name__ == "__main__":
    unittest.main()
