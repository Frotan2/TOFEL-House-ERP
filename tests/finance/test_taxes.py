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


def template_row(account="Tax Payable - TH", charge_type="On Net Total", rate=2.0,
                 cost_center=None):
    return {"charge_type": charge_type, "account_head": account,
            "rate": rate, "description": "", "cost_center": cost_center}


def invoice_row(account="Tax Payable - TH", charge_type="On Net Total",
                rate=2.0, tax_amount=500.0, cost_center=None):
    row = {"charge_type": charge_type, "account_head": account,
           "rate": rate, "tax_amount": tax_amount}
    if cost_center is not None:
        row["cost_center"] = cost_center
    return row


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

    def test_wrong_cost_center_is_refused_even_with_right_account_and_rate(self):
        # C-17: a template row that pins a cost centre pins it exactly.
        allowed = [template_row(cost_center="Main - TH")]
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.verify([invoice_row(cost_center="Branch - TH")], allowed=allowed)

    def test_matching_cost_center_passes(self):
        allowed = [template_row(cost_center="Main - TH")]
        self.verify([invoice_row(cost_center="Main - TH")], allowed=allowed)

    def test_template_without_cost_center_matches_any_invoice_cost_center(self):
        # A template row with no cost centre constrains nothing; older
        # templates keep matching lines that carry (or lack) one.
        self.verify([invoice_row(cost_center="Branch - TH")])
        self.verify([invoice_row()])


    def test_template_cost_center_with_missing_invoice_cost_center_is_refused(self):
        allowed = [template_row(cost_center="Main - TH")]
        with self.assertRaisesRegex(ValueError, "not part of a configured"):
            self.verify([invoice_row()], allowed=allowed)


class TaxScopeLimitTests(unittest.TestCase):
    """C-16: silent caps must raise an explicit error, never truncate."""

    def setUp(self):
        self.module = load_taxes()

    def _get_all(self, mapping):
        def fake(doctype, **kwargs):
            return list(mapping.get(doctype, []))
        return fake

    def test_more_than_twenty_default_templates_raise(self):
        rows = [{"name": f"Template-{i:02d}", "title": f"T{i}",
                 "company": "TOEFL House"} for i in range(21)]
        self.module.frappe.db.get_all = self._get_all(
            {"Sales Taxes and Charges Template": rows})
        with self.assertRaisesRegex(
                self.module.frappe.ValidationError,
                "supported limit of 20"):
            self.module.default_templates("TOEFL House")

    def test_twenty_default_templates_are_returned(self):
        rows = [{"name": f"Template-{i:02d}", "title": f"T{i}",
                 "company": "TOEFL House"} for i in range(20)]
        self.module.frappe.db.get_all = self._get_all(
            {"Sales Taxes and Charges Template": rows})
        self.assertEqual(len(self.module.default_templates("TOEFL House")), 20)

    def test_more_than_fifty_companies_raise(self):
        rows = [{"name": f"Company-{i:02d}"} for i in range(51)]
        self.module.frappe.db.get_all = self._get_all({"Company": rows})
        with self.assertRaisesRegex(
                self.module.frappe.ValidationError,
                "supported limit of 50"):
            self.module.describe_tax_configuration()

    def test_fifty_companies_are_described(self):
        rows = [{"name": f"Company-{i:02d}"} for i in range(50)]
        self.module.frappe.db.get_all = self._get_all({"Company": rows})
        result = self.module.describe_tax_configuration()
        self.assertEqual(len(result["companies"]), 50)
        self.assertEqual(result["companies"][0]["state"],
                         "No native tax configured")

    def test_more_than_two_hundred_item_tax_bindings_raise(self):
        # C-16 (Area B re-check): the silent limit_page_length=200 cap in
        # item_tax_templates could drop a configured template and refuse
        # a legitimate invoice. Over the cap must raise explicitly.
        rows = [{"parent": f"ITEM-{i % 5}", "item_tax_template": f"ITT-{i:03d}"}
                for i in range(201)]
        self.module.frappe.db.get_all = self._get_all({"Item Tax": rows})
        with self.assertRaisesRegex(
                self.module.frappe.ValidationError,
                "supported limit of 200"):
            self.module.item_tax_templates([f"ITEM-{i}" for i in range(5)])

    def test_two_hundred_item_tax_bindings_are_returned(self):
        rows = [{"parent": f"ITEM-{i % 5}", "item_tax_template": f"ITT-{i:03d}"}
                for i in range(200)]
        self.module.frappe.db.get_all = self._get_all({"Item Tax": rows})
        names = self.module.item_tax_templates([f"ITEM-{i}" for i in range(5)])
        self.assertEqual(len(names), 200)

    def test_more_than_one_hundred_rows_in_one_template_raise(self):
        # C-16 (Area B re-check): _template_rows passed no limit at all,
        # so Frappe's default 20-row page silently dropped rows 21+ of a
        # template. The read now names its cap and raises past it.
        rows = [{"charge_type": "On Net Total", "account_head": f"Acc-{i}",
                 "rate": 1.0, "description": "", "cost_center": None}
                for i in range(101)]
        self.module.frappe.db.get_all = self._get_all(
            {"Sales Taxes and Charges": rows})
        with self.assertRaisesRegex(
                self.module.frappe.ValidationError,
                "supported limit of 100"):
            self.module._template_rows("TPL-1")

    def test_one_hundred_rows_in_one_template_are_returned(self):
        rows = [{"charge_type": "On Net Total", "account_head": f"Acc-{i}",
                 "rate": 1.0, "description": "", "cost_center": None}
                for i in range(100)]
        self.module.frappe.db.get_all = self._get_all(
            {"Sales Taxes and Charges": rows})
        self.assertEqual(len(self.module._template_rows("TPL-1")), 100)

    def test_more_than_one_hundred_item_template_rows_raise(self):
        rows = [{"tax_type": f"Acc-{i}", "tax_rate": 1.0} for i in range(101)]
        self.module.frappe.db.get_all = self._get_all(
            {"Item Tax Template Detail": rows})
        with self.assertRaisesRegex(
                self.module.frappe.ValidationError,
                "supported limit of 100"):
            self.module._item_template_rows("ITT-1")

    def test_one_hundred_item_template_rows_are_returned(self):
        rows = [{"tax_type": f"Acc-{i}", "tax_rate": 1.0} for i in range(100)]
        self.module.frappe.db.get_all = self._get_all(
            {"Item Tax Template Detail": rows})
        self.assertEqual(len(self.module._item_template_rows("ITT-1")), 100)


class GuardPostableTests(unittest.TestCase):
    """C-17 (Area B re-check): the pre-save guard must judge the same
    postable-account rule as the submit seam, not only the template match."""

    def setUp(self):
        from types import SimpleNamespace
        self.module = load_taxes()
        self.SimpleNamespace = SimpleNamespace

    def _install(self, account_company="TOEFL House", is_group=0, disabled=0):
        def fake_get_all(doctype, **kwargs):
            if doctype == "Sales Taxes and Charges Template":
                return [{"name": "TPL", "title": "T", "company": "TOEFL House"}]
            if doctype == "Sales Taxes and Charges":
                return [template_row(account="Tax Payable - TH")]
            return []
        SimpleNamespace = self.SimpleNamespace
        self.module.frappe.db.get_all = fake_get_all
        self.module.frappe.db.get_value = lambda doctype, name, fields, as_dict=False: \
            SimpleNamespace(company=account_company, is_group=is_group,
                            disabled=disabled)

    def test_guard_refuses_line_backed_only_by_another_companys_account(self):
        self._install(account_company="Other Company")
        self.assertFalse(self.module.supplied_taxes_permitted(
            "TOEFL House", [], [invoice_row()]))

    def test_guard_refuses_line_backed_only_by_a_group_or_disabled_account(self):
        self._install(is_group=1)
        self.assertFalse(self.module.supplied_taxes_permitted(
            "TOEFL House", [], [invoice_row()]))
        self._install(disabled=1)
        self.assertFalse(self.module.supplied_taxes_permitted(
            "TOEFL House", [], [invoice_row()]))

    def test_guard_permits_line_backed_by_a_postable_account(self):
        self._install()
        self.assertTrue(self.module.supplied_taxes_permitted(
            "TOEFL House", [], [invoice_row()]))


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
