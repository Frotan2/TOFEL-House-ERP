"""Operating expenses on the native Journal Entry (finance/expenses.py).

The module runs against a small in-memory frappe so every server rule is
exercised without a bench: separation of duties, paying-account rules,
Reception counter refusal, cash cover, posting-date window, closed cash
days, bank references, the native-route guard and the month position.
The real-site lifecycle (posting, GL rows, cancel) is covered by the native
checks in tools/native.
"""
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
TODAY = "2026-11-28"


class AttrDict(dict):
    __getattr__ = dict.get


class ValidationError(Exception):
    pass


class FramePermissionError(Exception):
    pass


class FakeJournal(AttrDict):
    def __init__(self, world, data):
        super().__init__(data)
        self.world = world
        self.flags = types.SimpleNamespace()
        self.comments = []

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def is_new(self):
        return not self.get("name")

    def insert(self, ignore_permissions=False):
        self.world.journal_seq += 1
        self["name"] = f"ACC-JV-{self.world.journal_seq:05d}"
        self["docstatus"] = 0
        self.world.guard(self, "validate")
        self.world.journals[self["name"]] = self
        return self

    def submit(self):
        self["docstatus"] = 1
        self.world.guard(self, "validate")
        total = sum(Decimal(str(row["debit_in_account_currency"])) for row in self["accounts"])
        self["total_debit"] = float(total)
        self["total_credit"] = float(sum(Decimal(str(row["credit_in_account_currency"])) for row in self["accounts"]))
        self["accounts"] = [AttrDict(row) for row in self["accounts"]]

    def cancel(self):
        self.world.guard(self, "before_cancel")
        self["docstatus"] = 2

    def add_comment(self, kind, text):
        self.comments.append((kind, text))


class World:
    def __init__(self):
        self.user = "officer@th.example"
        self.roles = {
            "officer@th.example": {"Finance Officer"},
            "manager@th.example": {"Finance Manager"},
            "manager2@th.example": {"Finance Manager", "Finance Officer"},
            "reception@th.example": {"Reception"},
            "teacher@th.example": {"Instructor"},
        }
        self.accounts = {
            "Rent - TH": AttrDict(name="Rent - TH", company="TOEFL House", root_type="Expense", is_group=0,
                                  disabled=0, account_currency="AFN", account_name="Rent"),
            "Utilities - TH": AttrDict(name="Utilities - TH", company="TOEFL House", root_type="Expense",
                                       is_group=0, disabled=0, account_currency="AFN", account_name="Utilities"),
            "Cash - TH": AttrDict(name="Cash - TH", company="TOEFL House", root_type="Asset", account_type="Cash",
                                  is_group=0, disabled=0, account_currency="AFN", account_name="Cash"),
            "Counter 1 - TH": AttrDict(name="Counter 1 - TH", company="TOEFL House", root_type="Asset",
                                       account_type="Cash", is_group=0, disabled=0, account_currency="AFN",
                                       account_name="Counter 1"),
            "Bank - TH": AttrDict(name="Bank - TH", company="TOEFL House", root_type="Asset", account_type="Bank",
                                  is_group=0, disabled=0, account_currency="AFN", account_name="Bank"),
            "Debtors - TH": AttrDict(name="Debtors - TH", company="TOEFL House", root_type="Asset",
                                     account_type="Receivable", is_group=0, disabled=0, account_currency="AFN",
                                     account_name="Debtors"),
            "Rent - OTHER": AttrDict(name="Rent - OTHER", company="Other Co", root_type="Expense", is_group=0,
                                     disabled=0, account_currency="AFN", account_name="Rent"),
        }
        self.user_permissions = [AttrDict(user="reception@th.example", allow="Account", for_value="Counter 1 - TH")]
        self.cash_balance = Decimal("10000")
        self.cashier_days = []
        self.billing_terms = {}
        self.journals = {}
        self.journal_seq = 0
        self.kind = None
        self.locked = []
        self.gl_rows = []
        self.guard = lambda doc, method: None

    # -- frappe surface ------------------------------------------------
    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, **kw):
        filters = filters or {}
        if doctype == "User Permission":
            rows = [row for row in self.user_permissions
                    if all(row.get(key) == value for key, value in filters.items())]
            return [row[pluck] for row in rows] if pluck else rows
        if doctype == "TH Cashier Day":
            rows = [row for row in self.cashier_days
                    if row["company"] == filters["company"] and row["docstatus"] == filters["docstatus"]
                    and row["date"] >= filters["date"][1]]
            return rows[:1]
        if doctype == "Company":
            return ["TOEFL House"]
        if doctype == "Account":
            rows = [row for row in self.accounts.values() if row["company"] == filters["company"]
                    and row["root_type"] == filters["root_type"] and not row["is_group"] and not row["disabled"]]
            if "account_type" in filters:
                rows = [row for row in rows if row.get("account_type") in filters["account_type"][1]]
            return rows
        raise AssertionError(f"unexpected get_all {doctype}")

    def get_value(self, doctype, name, fields=None, as_dict=False):
        if doctype == "Account":
            row = self.accounts.get(name)
            if row is None:
                return None
            if isinstance(fields, str):
                return row.get(fields)
            return AttrDict({key: row.get(key) for key in fields})
        if doctype == "Journal Entry":
            doc = self.journals.get(name)
            if doc is None:
                return None
            if isinstance(fields, str):
                return doc.get(fields)
            return AttrDict({key: doc.get(key) for key in fields})
        if doctype == "User":
            return 1
        raise AssertionError(f"unexpected get_value {doctype}")

    def sql(self, query, values=None, as_dict=False):
        if "for update" in query:
            self.locked.append(values)
            return []
        if "sum(debit - credit)" in query:
            return [[self.cash_balance]]
        if "root_type" in query:
            return self.gl_rows
        raise AssertionError("unexpected sql")


def load(world):
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = ValidationError
    frappe.PermissionError = FramePermissionError
    class Session:
        user = property(lambda _self: world.user)
    frappe.session = Session()
    frappe.whitelist = lambda **kw: (lambda fn: fn)
    frappe.get_roles = lambda user=None: sorted(world.roles.get(user, set()))
    frappe.get_all = world.get_all
    frappe.get_cached_value = lambda dt, name, field: {"default_currency": "AFN",
                                                        "cost_center": "Main - TH"}.get(field)
    frappe.db = types.SimpleNamespace(get_value=world.get_value, sql=world.sql,
                                      has_column=lambda dt, field: True, exists=lambda *a, **k: True)
    utils = types.ModuleType("frappe.utils")
    utils.today = lambda: TODAY
    frappe.utils = utils

    def get_doc(*args, **kwargs):
        if isinstance(args[0], dict):
            return FakeJournal(world, args[0])
        return world.journals[args[1]]
    frappe.get_doc = get_doc

    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    finance = types.ModuleType("toefl_house.finance")
    finance.__path__ = [str(APP / "finance")]
    api = types.ModuleType("toefl_house.api")

    def execute(kind, request_key, payload, work):
        world.kind = kind
        world.executed.append((kind, request_key, payload))
        try:
            result, event = work(world.user)
        finally:
            world.kind = None
        world.events.append(event)
        return result
    api._execute = execute
    world.executed, world.events = [], []
    security = types.ModuleType("toefl_house.security")
    security.active_command_kind = lambda: world.kind
    security.record_synthetic_flag = lambda: 1
    security.require_operational = lambda: None
    company_scope = types.ModuleType("toefl_house.finance.company_scope")

    def require_finance_company(company):
        if company not in ("TOEFL House", "Other Co"):
            raise ValidationError("Unknown accounting company")
        return company
    company_scope.require_finance_company = require_finance_company
    policies = types.ModuleType("toefl_house.finance.policies")
    policies.governing_billing_terms = lambda on_date=None: dict(world.billing_terms)
    native = types.ModuleType("toefl_house.finance.tuition_refund_native")
    native.lock_cash_accounts = lambda names: world.locked.append(tuple(names))
    modules = {"frappe": frappe, "frappe.utils": utils, "toefl_house": package, "toefl_house.finance": finance,
               "toefl_house.api": api, "toefl_house.security": security,
               "toefl_house.finance.company_scope": company_scope, "toefl_house.finance.policies": policies,
               "toefl_house.finance.tuition_refund_native": native}
    context = patch.dict(sys.modules, modules)
    context.start()
    spec = importlib.util.spec_from_file_location("toefl_house.finance.expenses", APP / "finance/expenses.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["toefl_house.finance.expenses"] = module
    spec.loader.exec_module(module)
    world.guard = module.guard_expense_journal
    return module, context


class ExpenseTestCase(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.module, context = load(self.world)
        self.addCleanup(context.stop)

    def record(self, **overrides):
        args = dict(request_key="k-1", company="TOEFL House", posting_date=TODAY, expense_account="Rent - TH",
                    paid_from="Cash - TH", amount="2500", payee="Karimi Properties",
                    description="November rent\nmain building", reference=None)
        args.update(overrides)
        return self.module.record_expense(**args)


class RecordExpenseTests(ExpenseTestCase):
    def test_cash_expense_posts_one_balanced_native_journal(self):
        result = self.record()
        doc = self.world.journals[result["journal_entry"]]
        self.assertEqual(doc["voucher_type"], "Cash Entry")
        self.assertEqual(doc["docstatus"], 1)
        self.assertEqual(doc["th_expense_recorder"], "officer@th.example")
        self.assertEqual(doc["th_expense_synthetic"], 1)
        self.assertEqual(doc["user_remark"], "November rent main building")
        debit, credit = doc["accounts"]
        self.assertEqual((debit.account, debit.debit_in_account_currency), ("Rent - TH", 2500.0))
        self.assertEqual((credit.account, credit.credit_in_account_currency), ("Cash - TH", 2500.0))
        self.assertEqual({debit.cost_center, credit.cost_center}, {"Main - TH"})
        self.assertEqual(result["amount"], 2500.0)
        self.assertEqual(result["status"], "Posted")
        self.assertEqual(result["expense_category"], "Rent")
        self.assertIn(("Cash - TH",), self.world.locked, "the cash drawer must be locked before the cover check")
        self.assertEqual(self.world.executed[0][0], "record_expense")
        self.assertEqual(self.world.events[0]["target"], doc["name"])

    def test_bank_expense_needs_reference_and_maps_it_to_the_native_cheque_fields(self):
        with self.assertRaisesRegex(ValidationError, "reference"):
            self.record(paid_from="Bank - TH")
        result = self.record(paid_from="Bank - TH", reference="TRX-7781")
        doc = self.world.journals[result["journal_entry"]]
        self.assertEqual(doc["voucher_type"], "Bank Entry")
        self.assertEqual((doc["cheque_no"], doc["cheque_date"]), ("TRX-7781", TODAY))

    def test_bank_payment_does_not_need_cash_cover(self):
        self.world.cash_balance = Decimal("0")
        self.record(paid_from="Bank - TH", reference="TRX-1")

    def test_reception_counter_drawer_cannot_pay_expenses(self):
        with self.assertRaisesRegex(ValidationError, "Reception counter"):
            self.record(paid_from="Counter 1 - TH")
        self.assertEqual(self.world.journals, {})

    def test_paying_account_must_be_cash_or_bank_of_the_same_company(self):
        for account in ("Debtors - TH", "Rent - TH", "Missing - TH"):
            with self.subTest(account=account), self.assertRaisesRegex(ValidationError, "Cash or Bank"):
                self.record(paid_from=account)

    def test_category_must_be_a_postable_expense_account_of_the_company(self):
        self.world.accounts["Old - TH"] = AttrDict(self.world.accounts["Rent - TH"], name="Old - TH", disabled=1)
        for account in ("Cash - TH", "Rent - OTHER", "Old - TH"):
            with self.subTest(account=account), self.assertRaisesRegex(ValidationError, "expense category"):
                self.record(expense_account=account)

    def test_cash_cannot_go_negative(self):
        self.world.cash_balance = Decimal("2499.99")
        with self.assertRaisesRegex(ValidationError, "does not cover"):
            self.record()
        self.assertEqual(self.world.journals, {})

    def test_amount_rules(self):
        for amount in ("0", "-5", "abc", "1.234", True):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self.record(amount=amount)

    def test_future_and_old_dates_are_refused_without_a_policy_window(self):
        with self.assertRaisesRegex(ValidationError, "future"):
            self.record(posting_date="2026-11-29")
        with self.assertRaisesRegex(ValidationError, "today's date"):
            self.record(posting_date="2026-11-27")
        with self.assertRaisesRegex(ValidationError, "valid date"):
            self.record(posting_date="28/11/2026")

    def test_billing_policy_backdate_window_applies(self):
        self.world.billing_terms = {"max_backdate_days": 3}
        self.record(posting_date="2026-11-25")
        with self.assertRaisesRegex(ValidationError, "older than the billing policy"):
            self.record(posting_date="2026-11-24")

    def test_closed_cash_day_refuses_cash_expense_but_not_bank(self):
        self.world.billing_terms = {"max_backdate_days": 7}
        self.world.cashier_days.append(dict(name="TH-CASH-1", company="TOEFL House", docstatus=1,
                                            date="2026-11-26"))
        with self.assertRaisesRegex(ValidationError, "already closed"):
            self.record(posting_date="2026-11-25")
        self.record(posting_date="2026-11-27")
        self.record(posting_date="2026-11-25", paid_from="Bank - TH", reference="TRX-2")

    def test_payee_and_description_are_required(self):
        with self.assertRaisesRegex(ValidationError, "paid to"):
            self.record(payee=" ")
        with self.assertRaisesRegex(ValidationError, "longer description"):
            self.record(description="ok")


class VoidExpenseTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.name = self.record()["journal_entry"]

    def test_recorder_cannot_void_own_expense(self):
        self.world.roles["officer@th.example"].add("Finance Manager")
        with self.assertRaisesRegex(FramePermissionError, "Another Finance Manager"):
            self.module.void_expense("v-1", self.name, "Entered twice by mistake")
        self.assertEqual(self.world.journals[self.name]["docstatus"], 1)

    def test_a_different_manager_voids_with_a_reason_and_history(self):
        self.world.user = "manager@th.example"
        result = self.module.void_expense("v-1", self.name, "Entered twice by mistake")
        doc = self.world.journals[self.name]
        self.assertEqual(doc["docstatus"], 2)
        self.assertEqual(result["status"], "Void")
        self.assertEqual(result["voided_by"], "manager@th.example")
        self.assertIn("Entered twice by mistake", doc.comments[0][1])
        self.assertIn("before_hash", self.world.events[-1])
        with self.assertRaisesRegex(ValidationError, "not been voided"):
            self.module.void_expense("v-2", self.name, "Second attempt")

    def test_void_needs_a_real_reason(self):
        self.world.user = "manager@th.example"
        with self.assertRaisesRegex(ValidationError, "void reason"):
            self.module.void_expense("v-1", self.name, "oops")

    def test_cash_void_on_a_closed_day_is_refused(self):
        self.world.user = "manager@th.example"
        self.world.cashier_days.append(dict(name="TH-CASH-2", company="TOEFL House", docstatus=1, date=TODAY))
        with self.assertRaisesRegex(ValidationError, "already closed"):
            self.module.void_expense("v-1", self.name, "Entered twice by mistake")


class NativeRouteGuardTests(ExpenseTestCase):
    def test_native_routes_cannot_create_cancel_or_delete_expense_journals(self):
        name = self.record()["journal_entry"]
        doc = self.world.journals[name]
        for method in ("validate", "before_cancel", "before_update_after_submit", "on_trash"):
            with self.subTest(method=method), self.assertRaises(FramePermissionError):
                self.module.guard_expense_journal(doc, method)
        forged = FakeJournal(self.world, dict(th_expense_recorder="officer@th.example", accounts=[]))
        with self.assertRaises(FramePermissionError):
            self.module.guard_expense_journal(forged, "validate")
        amended = FakeJournal(self.world, dict(amended_from=name, accounts=[]))
        with self.assertRaises(FramePermissionError):
            self.module.guard_expense_journal(amended, "validate")

    def test_ordinary_journals_pass_through(self):
        plain = FakeJournal(self.world, dict(accounts=[]))
        for method in ("before_validate", "validate", "before_cancel", "on_trash"):
            self.module.guard_expense_journal(plain, method)

    def test_another_command_cannot_cancel_an_expense(self):
        name = self.record()["journal_entry"]
        self.world.kind = "record_expense"
        with self.assertRaises(FramePermissionError):
            self.module.guard_expense_journal(self.world.journals[name], "before_cancel")


class OptionsAndPositionTests(ExpenseTestCase):
    def test_options_list_names_only_and_hide_reception_counters(self):
        options = self.module.expense_options()
        (company,) = options["companies"]
        self.assertEqual(company["categories"], ["Rent - TH", "Utilities - TH"])
        self.assertEqual({row["name"] for row in company["paying_accounts"]}, {"Cash - TH", "Bank - TH"})
        self.assertEqual(options["today"], TODAY)

    def test_options_refuse_non_finance_staff(self):
        for user in ("reception@th.example", "teacher@th.example", "Guest", "Administrator"):
            self.world.user = user
            with self.subTest(user=user), self.assertRaises(FramePermissionError):
                self.module.expense_options()

    def test_month_position_uses_the_solar_hijri_month_and_ledger_signs(self):
        self.world.gl_rows = [
            AttrDict(company="TOEFL House", root_type="Income", debit=Decimal("100"), credit=Decimal("90100")),
            AttrDict(company="TOEFL House", root_type="Expense", debit=Decimal("30500.50"), credit=Decimal("500")),
        ]
        (row,) = self.module.month_position(TODAY)
        self.assertEqual((row["income"], row["expense"], row["net"]), (90000.0, 30000.5, 59999.5))
        self.assertEqual((row["start"], row["end"]), ("2026-11-22", TODAY))
        self.assertEqual(row["currency"], "AFN")
        self.assertTrue(row["period"].endswith("1405"))

    def test_month_position_omits_companies_without_postings(self):
        self.assertEqual(self.module.month_position(TODAY), [])


if __name__ == "__main__":
    unittest.main()
