"""Cashier day close: the counted drawer against the native ledger.

The close is a control record, not a ledger entry. These tests pin the shape
rules that make it trustworthy: only company Cash/Bank drawers, one row per
drawer, expected money computed from the ledger (never typed), variance equal
to counted minus expected, and a written explanation whenever they differ.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


class _Row:
    """A Frappe child row: attribute access plus .get()."""

    def __init__(self, **fields):
        self.__dict__["_fields"] = dict(fields)

    def __getattr__(self, name):
        try:
            return self._fields[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, field, default=None):
        return self._fields.get(field, default)


class _Close:
    def __init__(self, **fields):
        self.__dict__["_fields"] = dict(fields)

    def get(self, name, default=None):
        return self._fields.get(name, default)


def load_cashier(drawers=()):
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ValidationError
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.whitelist = lambda **kwargs: (lambda func: func)
    frappe.utils = types.SimpleNamespace(
        today=lambda: "2026-10-24",
        now_datetime=lambda: "2026-10-24 18:00:00",
    )
    frappe.session = types.SimpleNamespace(user="cashier@example.com")
    frappe.has_permission = lambda *args, **kwargs: True
    frappe.db = types.SimpleNamespace(
        get_all=lambda doctype, **kwargs: list(drawers) if doctype == "Account" else [],
        get_value=lambda *args, **kwargs: None,
        exists=lambda doctype, name: True,
        sql=lambda *args, **kwargs: [],
        count=lambda *args, **kwargs: 0,
    )
    frappe.get_all = frappe.db.get_all
    sys.modules["frappe"] = frappe

    policy = types.ModuleType("toefl_house.policy")
    policy.digest = lambda value: "digest"
    sys.modules["toefl_house.policy"] = policy

    security = types.ModuleType("toefl_house.security")
    security.require_operational = lambda: None
    security.finance_command_active = lambda doctype: True
    security.record_synthetic_flag = lambda: 1
    sys.modules["toefl_house.security"] = security

    api = types.ModuleType("toefl_house.api")
    api._execute = lambda kind, key, payload, work: work("cashier@example.com")
    sys.modules["toefl_house.api"] = api

    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    sys.modules["toefl_house"] = package

    finance_pkg = types.ModuleType("toefl_house.finance")
    finance_pkg.__path__ = [str(APP / "finance")]
    sys.modules["toefl_house.finance"] = finance_pkg

    policies = types.ModuleType("toefl_house.finance.policies")
    policies.governing_billing_terms = lambda on_date=None: {
        "max_backdate_days": 7, "max_future_days": 0}
    sys.modules["toefl_house.finance.policies"] = policies

    spec = importlib.util.spec_from_file_location(
        "toefl_house.finance.cashier", APP / "finance" / "cashier.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["toefl_house.finance.cashier"] = module
    spec.loader.exec_module(module)
    return module


DRAWERS = [{"name": "Cash - TH", "account_type": "Cash"},
           {"name": "Bank - TH", "account_type": "Bank"}]


def close(**overrides):
    rows = overrides.pop("accounts", [
        _Row(account="Cash - TH", account_type="Cash", expected_amount=1000.0,
             counted_amount=1000.0, variance=0.0, note=""),
    ])
    payload = {
        "date": "2026-10-24", "company": "TOEFL House",
        "accounts": rows,
        "total_expected": round(sum(float(row.get("expected_amount") or 0) for row in rows), 2),
        "total_counted": round(sum(float(row.get("counted_amount") or 0) for row in rows), 2),
        "total_variance": round(sum(float(row.get("variance") or 0) for row in rows), 2),
    }
    payload.update(overrides)
    return _Close(**payload)


class CloseShapeTests(unittest.TestCase):
    def setUp(self):
        # These individual validation cases use one approved cash drawer;
        # the multi-drawer completeness contract has a separate test.
        self.module = load_cashier(DRAWERS[:1])

    def test_partial_company_drawer_close_is_refused(self):
        module = load_cashier(DRAWERS)
        with self.assertRaisesRegex(_ValidationError, "every enabled Cash/Bank drawer"):
            module.validate_close(close())

    def test_balanced_close_is_accepted(self):
        self.assertIsNone(self.module.validate_close(close()))

    def test_nonfinite_values_cannot_bypass_drawer_or_total_checks(self):
        for value in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", True):
            for field in ("expected_amount", "counted_amount", "variance"):
                doc = close()
                doc.get("accounts")[0]._fields[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(_ValidationError):
                    self.module.validate_close(doc)
            for field in ("total_expected", "total_counted", "total_variance"):
                with self.subTest(field=field, value=value), self.assertRaises(_ValidationError):
                    self.module.validate_close(close(**{field: value}))

    def test_nonfinite_count_is_refused_before_close_creation(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e9999", True):
            with self.subTest(value=value), self.assertRaises(_ValidationError):
                self.module._counted(value, "Counted amount")

    def test_cashier_count_does_not_silently_round_fractional_minor_units(self):
        for value in ("0.001", "1.005", "100.999", 0.0001, 1.234):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(_ValidationError, "two decimal places"):
                    self.module._counted(value, "Counted amount")
        self.assertEqual(self.module._counted("0.01", "Counted amount"), 0.01)
        self.assertEqual(self.module._counted("20.000", "Counted amount"), 20.0)

    def test_signed_ledger_overdraft_and_explained_variance_are_valid(self):
        row = _Row(account="Cash - TH", account_type="Cash", expected_amount=-20,
                   counted_amount=0, variance=20, note="Overdraft requires Finance review")
        self.assertIsNone(self.module.validate_close(close(accounts=[row])))

    def test_expected_money_is_never_negative_becomes_variance(self):
        row = _Row(account="Cash - TH", account_type="Cash", expected_amount=1000.0,
                   counted_amount=980.0, variance=-20.0, note="paid a courier")
        self.assertIsNone(self.module.validate_close(
            close(accounts=[row], total_expected=1000.0,
                  total_counted=980.0, total_variance=-20.0)))

    def test_variance_without_an_explanation_is_refused(self):
        row = _Row(account="Cash - TH", account_type="Cash", expected_amount=1000.0,
                   counted_amount=980.0, variance=-20.0, note="  ")
        with self.assertRaisesRegex(_ValidationError, "Explain"):
            self.module.validate_close(
                close(accounts=[row], total_expected=1000.0,
                      total_counted=980.0, total_variance=-20.0))

    def test_variance_must_equal_counted_minus_expected(self):
        row = _Row(account="Cash - TH", account_type="Cash", expected_amount=1000.0,
                   counted_amount=980.0, variance=0.0, note="short")
        with self.assertRaisesRegex(_ValidationError, "counted minus expected"):
            self.module.validate_close(
                close(accounts=[row], total_expected=1000.0,
                      total_counted=980.0, total_variance=-20.0))

    def test_totals_must_match_the_rows(self):
        with self.assertRaisesRegex(_ValidationError, "total expected"):
            self.module.validate_close(close(total_expected=9999.0))
        with self.assertRaisesRegex(_ValidationError, "total counted"):
            self.module.validate_close(close(total_counted=9999.0))
        with self.assertRaisesRegex(_ValidationError, "total variance"):
            self.module.validate_close(close(total_variance=5.0))

    def test_non_cash_account_is_refused(self):
        row = _Row(account="Debtors - TH", account_type="Receivable",
                   expected_amount=0.0, counted_amount=0.0, variance=0.0, note="")
        with self.assertRaisesRegex(_ValidationError, "not a Cash or Bank account"):
            self.module.validate_close(
                close(accounts=[row], total_expected=0.0, total_counted=0.0,
                      total_variance=0.0))

    def test_the_same_drawer_twice_is_refused(self):
        rows = [_Row(account="Cash - TH", account_type="Cash", expected_amount=10.0,
                     counted_amount=10.0, variance=0.0, note=""),
                _Row(account="Cash - TH", account_type="Cash", expected_amount=10.0,
                     counted_amount=10.0, variance=0.0, note="")]
        with self.assertRaisesRegex(_ValidationError, "counted twice"):
            self.module.validate_close(
                close(accounts=rows, total_expected=20.0, total_counted=20.0,
                      total_variance=0.0))

    def test_negative_counted_is_refused(self):
        row = _Row(account="Cash - TH", account_type="Cash", expected_amount=10.0,
                   counted_amount=-5.0, variance=-15.0, note="impossible")
        with self.assertRaisesRegex(_ValidationError, "cannot be negative"):
            self.module.validate_close(
                close(accounts=[row], total_expected=10.0, total_counted=-5.0,
                      total_variance=-15.0))

    def test_future_business_day_is_refused(self):
        with self.assertRaisesRegex(_ValidationError, "future"):
            self.module.validate_close(close(date="2026-10-25"))

    def test_empty_close_is_refused(self):
        with self.assertRaisesRegex(_ValidationError, "at least one drawer"):
            self.module.validate_close(
                close(accounts=[], total_expected=0.0, total_counted=0.0,
                      total_variance=0.0))


class DrawerTruthTests(unittest.TestCase):
    """Expected money is the ledger aggregate, never a typed number."""

    def setUp(self):
        self.module = load_cashier(DRAWERS)

    def test_balance_shape_and_exclusion_of_cancelled_entries(self):
        statements = []

        def sql(statement, params=None, **kwargs):
            statements.append((statement, params))
            return [{"opening": 100.0, "movement": -20.0, "closing": 80.0}]

        self.module.frappe.db.sql = sql
        rows = self.module.drawer_balances("TOEFL House", ["Cash - TH"], "2026-10-24")
        self.assertEqual(rows, [{"account": "Cash - TH", "opening": 100.0,
                                 "movement": -20.0, "closing": 80.0}])
        statement, params = statements[0]
        self.assertIn("is_cancelled = 0", statement)
        self.assertEqual(params, ("2026-10-24", "2026-10-24", "2026-10-24",
                                  "Cash - TH", "TOEFL House"))

    def test_no_drawers_means_nothing_to_reconcile(self):
        self.assertEqual(load_cashier().cash_drawers("TOEFL House"), [])


class CloseDriftTests(unittest.TestCase):
    """Never hide a cancelled old GL row or offsetting post-close movement."""

    def setUp(self):
        self.module = load_cashier(DRAWERS)
        self.saved = [
            {"account": "Cash - TH", "expected_amount": 100.0},
            {"account": "Bank - TH", "expected_amount": 50.0},
        ]
        self.live = [
            {"account": "Cash - TH", "opening": 100.0,
             "movement": 0.0, "closing": 100.0},
            {"account": "Bank - TH", "opening": 50.0,
             "movement": 0.0, "closing": 50.0},
        ]
        self.after = False
        self.closed = True
        self.module.cash_drawers = lambda company: DRAWERS
        self.module.drawer_balances = lambda company, accounts, day: self.live

        def get_all(doctype, **kwargs):
            if doctype == self.module.DAY:
                return ([{"name": "TH-CASH-2026-01",
                          "reconciled_on": "2026-10-24 18:00:00",
                          "total_expected": 150.0}] if self.closed else [])
            if doctype == self.module.COUNT:
                self.assertEqual(kwargs["filters"]["parent"], "TH-CASH-2026-01")
                self.assertEqual(kwargs["filters"]["parenttype"], self.module.DAY)
                self.assertEqual(kwargs["limit_page_length"],
                                 self.module.MAX_DRAWERS + 1)
                return self.saved
            self.fail("Unexpected accounting read: " + doctype)

        self.module.frappe.db.get_all = get_all
        self.module.frappe.db.sql = (
            lambda *args, **kwargs: [{"name": "new posted GL"}] if self.after else [])

    def position(self):
        positions = self.module.cashier_position(
            day="2026-10-24", companies=["TOEFL House"])
        self.assertEqual(len(positions), 1)
        return positions[0]

    def test_exact_match_is_not_drift(self):
        self.assertFalse(self.position()["drift"])

    def test_cancelled_historical_entry_changed_balance_without_new_gl(self):
        # No GL creation after close: native cancellation invalidated an
        # earlier debit by marking its original GL Entry cancelled.
        self.live[0]["closing"] = 80.0
        self.assertTrue(self.position()["drift"])

    def test_offsetting_movements_do_not_hide_drift(self):
        # The combined company balance remains 150, but both drawers differ.
        self.live[0]["closing"] = 80.0
        self.live[1]["closing"] = 70.0
        self.assertTrue(self.position()["drift"])

    def test_missing_or_duplicated_closed_drawer_is_drift(self):
        self.saved.pop()
        self.assertTrue(self.position()["drift"])
        self.saved.append({"account": "Cash - TH", "expected_amount": 100.0})
        self.assertTrue(self.position()["drift"])

    def test_new_backdated_gl_keeps_existing_audit_signal(self):
        # A balance-neutral new posting still matters to a closed ledger.
        self.after = True
        self.assertTrue(self.position()["drift"])

    def test_no_close_is_not_misreported_as_drift(self):
        self.closed = False
        self.assertFalse(self.position()["drift"])

    def test_malformed_snapshot_never_looks_reconciled(self):
        self.saved[0]["expected_amount"] = "Infinity"
        self.assertTrue(self.position()["drift"])


class CommandContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (APP / "finance" / "cashier.py").read_text(encoding="utf-8")
        cls.security = (APP / "security.py").read_text(encoding="utf-8")
        cls.hooks = (APP / "hooks.py").read_text(encoding="utf-8")

    def test_close_is_a_receipted_finance_officer_command(self):
        self.assertIn('"reconcile_cashier_day": "Finance Officer"', self.security)
        self.assertIn('_execute("reconcile_cashier_day", request_key', self.source)

    def test_the_close_posts_nothing(self):
        # No posting primitive may appear in the close's own code.
        for forbidden in ("make_gl_entries", "Journal Entry", "journal_entry",
                          "get_payment_entry", "Stock Entry", "Sales Invoice"):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("posts nothing", self.source)

    def test_duplicate_day_is_refused_under_a_lock(self):
        self.assertIn("already closed for this company", self.source)
        self.assertIn("for update", self.source)

    def test_command_only_on_every_seam(self):
        handlers = self.hooks.split('"TH Cashier Day": {')[1].split("}")[0]
        for seam in ("validate", "before_cancel", "before_update_after_submit"):
            self.assertIn(seam, handlers)
        self.assertIn("toefl_house.finance.cashier.guard", handlers)

    def test_closing_window_is_the_owner_billing_policy(self):
        self.assertIn("governing_billing_terms", self.source)
        self.assertIn("older than the billing policy's closing window", self.source)

    def test_command_refuses_a_company_outside_the_cashier_scope(self):
        module = load_cashier(DRAWERS)
        module.frappe.get_all = lambda doctype, **kwargs: (
            ["Other Company"] if doctype == "User Permission" else [])
        with self.assertRaises(module.frappe.PermissionError) as caught:
            module.reconcile_cashier_day(
                "fin_cashier_scope_00001", "TOEFL House", "2026-10-24", [])
        self.assertIn("not permitted to record a cash close", str(caught.exception))

    def test_explicit_company_read_scope_is_not_trusted(self):
        module = load_cashier(DRAWERS)
        module.frappe.get_all = lambda doctype, **kwargs: (
            ["TOEFL House"] if doctype == "User Permission" else [])
        self.assertEqual(
            module._resolve_companies(["Other Company", "TOEFL House"]),
            ["TOEFL House"])

    def test_a_cashier_with_no_company_permission_is_unrestricted(self):
        module = load_cashier(DRAWERS)
        self.assertTrue(module._company_permitted("Any Company"))

    def test_company_scope_is_checked_before_any_write(self):
        self.assertIn("_company_permitted(company)", self.source)
        self.assertIn('filters={"user": user, "allow": COMPANY}', self.source)

    def test_command_rejects_an_invalid_date_with_a_business_message(self):
        # The command's public parameter is named `date` (the desk field). If
        # that shadows the date class, `date.fromisoformat` raises
        # AttributeError and only the native run finds out (2026-10-24).
        module = load_cashier(DRAWERS)
        with self.assertRaises(_ValidationError) as caught:
            module.reconcile_cashier_day(
                "fin_cashier_bad_date_01", "TOEFL House", "not-a-date",
                [{"account": "Cash - TH", "counted_amount": 1}])
        self.assertIn("A valid business date is required", str(caught.exception))

    def test_http_form_encoded_drawer_counts_are_bounded_and_parsed(self):
        module = load_cashier(DRAWERS)
        for invalid, message in (
                ("not JSON", "counts are invalid"),
                ('{"account":"Cash - TH"}', "must be a list"),
                ("[" + " " * 20001 + "]", "request is too large"),
                ('[{}]' * 26, "counts are invalid")):
            with self.subTest(message=message), self.assertRaisesRegex(
                    _ValidationError, message):
                module.reconcile_cashier_day(
                    "fin_cashier_transport_001", "TOEFL House",
                    "2026-10-24", invalid)
        with self.assertRaisesRegex(_ValidationError, "valid business date"):
            module.reconcile_cashier_day(
                "fin_cashier_transport_002", "TOEFL House",
                "not-a-date",
                '[{"account":"Cash - TH","counted_amount":1000,"note":""}]')

    def test_finance_desk_offers_counted_not_expected_amount_as_input(self):
        desk = (APP / "desk" / "finance.py").read_text(encoding="utf-8")
        gui = (APP / "public" / "js" / "th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn('"Close today\'s company cash drawers"', desk)
        self.assertIn('"drawers": [{"account": d["account"]', desk)
        self.assertIn('"toefl_house.finance.cashier.reconcile_cashier_day"', gui)
        self.assertIn('fieldname: "drawer_counted_" + index', gui)
        self.assertIn("args.counts = JSON.stringify(counts);", gui)
        self.assertIn("never an assumed ledger amount.", gui)
        self.assertIn('No payment or cash movement is created.', gui)

    def test_package_date_class_is_not_shadowed_inside_the_command(self):
        import ast
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef)
                    and node.name == "reconcile_cashier_day"):
                continue
            self.assertIn("date", {a.arg for a in node.args.args})
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Attribute)
                        and inner.attr == "fromisoformat"
                        and isinstance(inner.value, ast.Name)
                        and inner.value.id == "date"):
                    self.fail("the `date` parameter shadows the date class")
        self.assertIn("from datetime import date as _date", self.source)

    def test_naming_series_the_command_passes_exists_on_the_doctype(self):
        # Autoname "naming_series:" needs a naming_series field; without it a
        # real site refuses the insert and only the native run would notice.
        import json
        doctype = json.loads(
            (APP / "finance" / "doctype" / "th_cashier_day" /
             "th_cashier_day.json").read_text(encoding="utf-8"))
        self.assertEqual(doctype["autoname"], "naming_series:")
        fields = {row["fieldname"]: row for row in doctype["fields"]}
        self.assertIn("naming_series", fields)
        series = fields["naming_series"]["options"]
        self.assertIn("TH-CASH-.YYYY.-", series)
        self.assertIn("naming_series", doctype["field_order"])
        self.assertIn('DAY_SERIES = "TH-CASH-.YYYY.-"', self.source)
        self.assertIn("naming_series=DAY_SERIES", self.source)

    def test_every_doctype_that_uses_a_naming_series_declares_the_field(self):
        # Same rule, every doctype in this app: the native insert path cannot
        # resolve a series that is not a field on the document.
        import json
        broken = []
        for path in (APP / "finance" / "doctype").glob("*/*.json"):
            doctype = json.loads(path.read_text(encoding="utf-8"))
            if doctype.get("autoname") != "naming_series:":
                continue
            names = {row.get("fieldname") for row in doctype.get("fields") or []}
            if "naming_series" not in names:
                broken.append(doctype.get("name") or path.parent.name)
        self.assertEqual(broken, [])


def tearDownModule():
    """Drop the stubs this module installed so later suites load fresh."""
    for name in ("frappe", "toefl_house", "toefl_house.policy", "toefl_house.api", "toefl_house.security", "toefl_house.finance", "toefl_house.finance.policies", "toefl_house.finance.cashier", "toefl_house.finance.taxes", "toefl_house.finance.refunds", "toefl_house.finance.installments",):
        sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
