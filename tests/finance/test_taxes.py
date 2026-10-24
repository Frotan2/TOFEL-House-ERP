"""Tax application is native configuration, never an invented rule.

Owner decision (FINANCE-POLICY-APPROVAL.md §1.2): tax templates stay
unconfigured until the owner supplies the tax policy. These tests pin the two
consequences: an invoice may only carry tax lines that a configured native
template supplies, and an invoice with no configuration may carry none.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


def load_taxes():
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ValidationError
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.whitelist = lambda **kwargs: (lambda func: func)
    frappe.db = types.SimpleNamespace()
    frappe.session = types.SimpleNamespace(user="officer@example.com")
    frappe.get_roles = lambda user: {"Finance Officer"}
    sys.modules["frappe"] = frappe
    spec = importlib.util.spec_from_file_location(
        "toefl_house.finance.taxes", APP / "finance" / "taxes.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["toefl_house.finance.taxes"] = module
    spec.loader.exec_module(module)
    return module


def template_row(account="Tax Payable - TH", charge_type="On Net Total", rate=2.0):
    return {"charge_type": charge_type, "account_head": account,
            "rate": rate, "description": "", "cost_center": None}


def invoice_row(account="Tax Payable - TH", charge_type="On Net Total",
                rate=2.0, tax_amount=500.0):
    return {"charge_type": charge_type, "account_head": account,
            "rate": rate, "tax_amount": tax_amount}


class TaxVerificationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_taxes()
        self.allowed = [template_row()]

    def verify(self, rows, allowed=None, net=25000.0, grand=None, is_return=False):
        return self.module.verify_tax_rows(
            rows, self.allowed if allowed is None else allowed,
            net_total=net,
            grand_total=net + 500.0 if grand is None else grand,
            is_return=is_return)

    def test_configured_template_line_passes(self):
        self.verify([invoice_row()])

    def test_no_configuration_means_no_tax_lines(self):
        self.assertEqual(self.verify([], allowed=[], net=25000.0, grand=25000.0), [])

    def test_unbacked_tax_line_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.verify([invoice_row(account="Suspense - TH")])

    def test_rate_outside_the_template_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.verify([invoice_row(rate=99.0, tax_amount=24750.0)],
                        grand=49750.0)

    def test_charge_type_outside_the_native_vocabulary_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.verify([invoice_row(charge_type="Made Up")])

    def test_tax_total_must_equal_the_native_difference(self):
        with self.assertRaisesRegex(ValueError, "do not add up"):
            self.verify([invoice_row()], grand=26000.0)

    def test_negative_tax_on_a_sale_is_refused(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            self.verify([invoice_row(tax_amount=-500.0)], grand=24500.0)

    def test_credit_note_carries_the_signed_tax(self):
        # A native credit note's own totals are negative; its tax rows follow.
        self.module.verify_tax_rows(
            [invoice_row(tax_amount=-500.0)], self.allowed,
            net_total=-25000.0, grand_total=-25500.0, is_return=True)

    def test_positive_tax_on_a_credit_note_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot be positive"):
            self.module.verify_tax_rows(
                [invoice_row(tax_amount=500.0)], self.allowed,
                net_total=-25000.0, grand_total=-24500.0, is_return=True)

    def test_missing_line_when_a_template_applies_is_refused(self):
        with self.assertRaisesRegex(ValueError, "carries no tax line"):
            self.verify([], net=25000.0, grand=25500.0)

    def test_zero_tax_configured_template_is_not_a_violation(self):
        # A zero-rate template legitimately produces no line and no difference.
        self.assertEqual(self.verify([], net=25000.0, grand=25000.0), [])

    def test_multi_line_template_is_matched_row_by_row(self):
        allowed = [template_row("Tax Payable - TH", "On Net Total", 2.0),
                   template_row("Municipal - TH", "Actual", 100.0)]
        rows = [invoice_row(), invoice_row("Municipal - TH", "Actual", 100.0, 100.0)]
        result = self.module.verify_tax_rows(
            rows, allowed, net_total=25000.0, grand_total=25600.0)
        self.assertEqual(len(result), 2)

    def test_actual_template_row_must_name_its_configured_account(self):
        allowed = [template_row("Municipal - TH", "Actual", 100.0)]
        rows = [invoice_row("Other - TH", "Actual", 100.0, 100.0)]
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.module.verify_tax_rows(rows, allowed, net_total=25000.0,
                                        grand_total=25100.0)


class GuardSurfaceTests(unittest.TestCase):
    """The rule is applied at both seams: the pre-save guard and the posting seam."""

    @classmethod
    def setUpClass(cls):
        cls.hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        cls.finance = (APP / "finance" / "__init__.py").read_text(encoding="utf-8")

    def test_invoice_before_submit_verifies_taxes(self):
        self.assertIn('"before_submit": "toefl_house.finance.taxes.verify_document_taxes"',
                      self.hooks)

    def test_book_sale_guard_uses_the_same_rule(self):
        self.assertIn("taxes.supplied_taxes_permitted(", self.finance)


def tearDownModule():
    """Drop the stubs this module installed so later suites load fresh."""
    for name in ("frappe", "toefl_house", "toefl_house.policy", "toefl_house.api", "toefl_house.security", "toefl_house.finance", "toefl_house.finance.policies", "toefl_house.finance.cashier", "toefl_house.finance.taxes", "toefl_house.finance.refunds", "toefl_house.finance.installments",):
        sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
