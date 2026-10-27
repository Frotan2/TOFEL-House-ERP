"""Book inventory, price, return and refund integrity (Agent 2).

Pins the book-commerce rules that sit on top of native ERPNext stock and
accounts: configured selling prices, warehouse stock cover, warehouse-
true and rate-capped returns, cancellable reversals, Company-scoped
refunds, valued stock receipts and approved stock adjustments.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


class Doc:
    """Attribute document with the dict-style ``.get`` Frappe rows offer."""

    def __init__(self, **values):
        self.__dict__.update(values)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)


class FakeDB:
    def __init__(self):
        self.tables = {}

    def add(self, doctype, **row):
        self.tables.setdefault(doctype, []).append(row)
        return row

    def _match(self, row, filters):
        for key, expected in (filters or {}).items():
            if isinstance(expected, (list, tuple)) and expected \
                    and expected[0] == "in":
                if row.get(key) not in expected[1]:
                    return False
            elif row.get(key) != expected:
                return False
        return True

    def get_all(self, doctype, filters=None, fields=None,
                limit_page_length=None, pluck=None):
        rows = [row for row in self.tables.get(doctype, [])
                if self._match(row, filters)]
        if pluck:
            return [row.get(pluck) for row in rows]
        if fields:
            return [{**{f: row.get(f) for f in fields},
                     "name": row.get("name")} for row in rows]
        return [dict(row) for row in rows]

    def get_value(self, doctype, name, field, as_dict=False):
        rows = self.tables.get(doctype, [])
        if isinstance(name, dict):
            row = next((r for r in rows if self._match(r, name)), None)
        else:
            row = next((r for r in rows if r.get("name") == name), None)
        if row is None:
            return None
        if as_dict:
            return {f: row.get(f) for f in field}
        return row.get(field)


def load_modules(db, user="cashier@example.test", roles=()):
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ValidationError
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.db = db
    frappe.session = types.SimpleNamespace(user=user)
    frappe.get_roles = lambda _user=None: list(roles)
    frappe.has_permission = lambda *a, **k: True
    sys.modules["frappe"] = frappe
    security = types.ModuleType("toefl_house.security")
    security.require_operational = lambda: None
    sys.modules["toefl_house.security"] = security

    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, APP / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    books = load("toefl_house.finance.books", "finance/books.py")
    package = types.ModuleType("toefl_house.finance")
    package.books = books
    sys.modules["toefl_house.finance"] = package
    refunds = load("toefl_house.finance.refunds", "finance/refunds.py")
    return books, refunds, frappe


class PurePriceTests(unittest.TestCase):
    def setUp(self):
        self.books, _, _ = load_modules(FakeDB())

    def test_configured_price_resolution_prefers_customer_then_slab(self):
        rows = [
            {"price_list_rate": 300.0, "min_qty": 0, "customer": ""},
            {"price_list_rate": 280.0, "min_qty": 10, "customer": ""},
            {"price_list_rate": 260.0, "min_qty": 0, "customer": "SYN-CUST"},
        ]
        self.assertEqual(self.books.choose_item_price(rows, 2), 260.0)
        generic = [r for r in rows if not r["customer"]]
        self.assertEqual(self.books.choose_item_price(generic, 2), 300.0)
        self.assertEqual(self.books.choose_item_price(generic, 25), 280.0)

    def test_expired_or_future_or_free_prices_do_not_authorize_a_sale(self):
        choose = self.books.choose_item_price
        self.assertIsNone(choose(
            [{"price_list_rate": 300.0, "valid_upto": "2026-01-01"}],
            1, "2026-10-26"))
        self.assertIsNone(choose(
            [{"price_list_rate": 300.0, "valid_from": "2027-01-01"}],
            1, "2026-10-26"))
        self.assertIsNone(choose([{"price_list_rate": 0.0}], 1))
        self.assertIsNone(choose([{"price_list_rate": float("nan")}], 1))
        self.assertIsNone(choose([], 1))

    def test_sale_lines_must_bill_the_configured_price(self):
        ok = self.books.sale_prices_ok
        line = {"item_code": "B", "qty": 2, "rate": 300.0}
        self.assertTrue(ok([line], {"B": 300.0}))
        self.assertFalse(ok([{**line, "rate": 250.0}], {"B": 300.0}))
        self.assertFalse(ok([{**line, "rate": 350.0}], {"B": 300.0}))
        self.assertFalse(ok([{**line, "rate": 0.0}], {"B": 300.0}))
        self.assertFalse(ok([{**line, "rate": float("nan")}], {"B": 300.0}))
        self.assertFalse(ok([line], {"B": None}))
        self.assertFalse(ok([line], {}))
        self.assertFalse(ok([{**line, "conversion_factor": 12}], {"B": 300.0}))

    def test_pricing_rule_may_only_price_below_list(self):
        ok = self.books.sale_prices_ok
        ruled = {"item_code": "B", "qty": 1, "rate": 270.0,
                 "pricing_rules": '["SYN-RULE"]'}
        self.assertTrue(ok([ruled], {"B": 300.0}))
        self.assertFalse(ok([{**ruled, "rate": 330.0}], {"B": 300.0}))
        self.assertFalse(ok([{**ruled, "pricing_rules": "[]"}], {"B": 300.0}))

    def test_stock_cover_refuses_oversell_per_warehouse(self):
        cover = self.books.stock_cover_ok
        available = {("B", "WH-A"): 5.0, ("B", "WH-B"): 1.0}
        self.assertTrue(cover(available, {("B", "WH-A"): 5.0}))
        self.assertFalse(cover(available, {("B", "WH-A"): 6.0}))
        # Stock in another warehouse never covers this warehouse's sale.
        self.assertFalse(cover(available, {("B", "WH-B"): 5.0}))
        self.assertFalse(cover(available, {("B", "WH-C"): 1.0}))
        self.assertFalse(cover(available, {("B", "WH-A"): float("inf")}))

    def test_reconciliation_compares_bin_to_ledger_truth(self):
        reconcile = self.books.reconcile_book_stock
        bins = [{"item_code": "B", "warehouse": "WH-A",
                 "actual_qty": 8.0, "stock_value": 1400.0}]
        ledger = [
            {"item_code": "B", "warehouse": "WH-A", "actual_qty": 10.0,
             "stock_value_difference": 1750.0},
            {"item_code": "B", "warehouse": "WH-A", "actual_qty": -2.0,
             "stock_value_difference": -350.0},
        ]
        report = reconcile(bins, ledger)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["total_qty"], 8.0)
        short = reconcile([{**bins[0], "actual_qty": 7.0}], ledger)
        self.assertFalse(short["ok"])
        self.assertEqual(short["discrepancies"][0]["qty_difference"], -1.0)
        orphan = reconcile([], ledger)
        self.assertFalse(orphan["ok"])


def invoice_db():
    """SYN-SALE: 2 books @300 from WH-A, 1 book @300 from WH-B (=900)."""
    db = FakeDB()
    db.add("Sales Invoice", name="SYN-SALE", grand_total=900.0)
    db.add("Sales Invoice Item", parent="SYN-SALE", parenttype="Sales Invoice",
           item_code="SYN-BOOK", qty=2.0, warehouse="WH-A", rate=300.0,
           amount=600.0, net_amount=600.0)
    db.add("Sales Invoice Item", parent="SYN-SALE", parenttype="Sales Invoice",
           item_code="SYN-BOOK", qty=1.0, warehouse="WH-B", rate=300.0,
           amount=300.0, net_amount=300.0)
    return db


def return_doc(rows, total, **extra):
    return Doc(items=[Doc(**row) for row in rows], grand_total=total, **extra)


ORIGINAL = {"name": "SYN-SALE", "grand_total": 900.0}


class ReturnSeamTests(unittest.TestCase):
    def setUp(self):
        self.db = invoice_db()
        _, self.refunds, _ = load_modules(self.db)

    def permitted(self, doc):
        return self.refunds.book_return_permitted(doc, dict(ORIGINAL))

    def test_partial_return_at_sold_rate_and_warehouse_is_allowed(self):
        doc = return_doc([{"item_code": "SYN-BOOK", "qty": -1.0,
                           "warehouse": "WH-A", "rate": 300.0,
                           "amount": -300.0, "net_amount": -300.0}], -300.0)
        self.assertTrue(self.permitted(doc))

    def test_restock_into_a_warehouse_that_never_sold_is_refused(self):
        doc = return_doc([{"item_code": "SYN-BOOK", "qty": -1.0,
                           "warehouse": "WH-C", "rate": 300.0,
                           "amount": -300.0, "net_amount": -300.0}], -300.0)
        self.assertFalse(self.permitted(doc))

    def test_return_quantity_is_capped_per_warehouse_not_per_item(self):
        # Three books sold in total, but only two left WH-A.
        doc = return_doc([{"item_code": "SYN-BOOK", "qty": -3.0,
                           "warehouse": "WH-A", "rate": 300.0,
                           "amount": -900.0, "net_amount": -900.0}], -900.0)
        self.assertFalse(self.permitted(doc))

    def test_credit_above_the_sold_rate_is_refused(self):
        # One book back, credited at the whole WH-A line value.
        doc = return_doc([{"item_code": "SYN-BOOK", "qty": -1.0,
                           "warehouse": "WH-A", "rate": 600.0,
                           "amount": -600.0, "net_amount": -600.0}], -600.0)
        self.assertFalse(self.permitted(doc))

    def _seed_full_return(self):
        self.db.add("Sales Invoice", name="SYN-RET", return_against="SYN-SALE",
                    docstatus=1, is_return=1, grand_total=-900.0)
        for warehouse, qty in (("WH-A", -2.0), ("WH-B", -1.0)):
            self.db.add("Sales Invoice Item", parent="SYN-RET",
                        parenttype="Sales Invoice", item_code="SYN-BOOK",
                        qty=qty, warehouse=warehouse)

    def test_cancelling_a_submitted_full_return_is_allowed(self):
        self._seed_full_return()
        doc = return_doc(
            [{"item_code": "SYN-BOOK", "qty": -2.0, "warehouse": "WH-A",
              "rate": 300.0, "amount": -600.0, "net_amount": -600.0},
             {"item_code": "SYN-BOOK", "qty": -1.0, "warehouse": "WH-B",
              "rate": 300.0, "amount": -300.0, "net_amount": -300.0}],
            -900.0, name="SYN-RET", docstatus=1)
        self.assertTrue(self.permitted(doc))

    def test_a_second_full_return_after_the_first_is_still_refused(self):
        self._seed_full_return()
        doc = return_doc(
            [{"item_code": "SYN-BOOK", "qty": -2.0, "warehouse": "WH-A",
              "rate": 300.0, "amount": -600.0, "net_amount": -600.0}],
            -600.0, docstatus=0)
        self.assertFalse(self.permitted(doc))


class RefundCompanyScopeTests(unittest.TestCase):
    def _permitted(self, actor, permissions):
        db = FakeDB()
        db.add("Sales Invoice", name="SYN-CREDIT", docstatus=1, is_return=1,
               customer="SYN-CUST", company="TOEFL House",
               outstanding_amount=-600.0, grand_total=-600.0)
        db.add("Company", name="TOEFL House",
               default_receivable_account="Debtors - TH")
        db.add("Account", name="Cash - TH", company="TOEFL House",
               is_group=0, disabled=0, account_type="Cash")
        for value in permissions:
            db.add("User Permission", user=actor, allow="Company",
                   for_value=value)
        _, refunds, _ = load_modules(db, user=actor)
        doc = Doc(payment_type="Pay", party_type="Customer",
                  party="SYN-CUST", company="TOEFL House",
                  paid_from="Cash - TH", paid_to="Debtors - TH",
                  unallocated_amount=0.0, paid_amount=600.0,
                  references=[Doc(reference_doctype="Sales Invoice",
                                  reference_name="SYN-CREDIT",
                                  allocated_amount=-600.0)],
                  deductions=[])
        # refund_permitted reads child rows via doc.get(...); Doc.get
        # returns the attribute value, rows need as_dict-style access.
        doc.references[0].as_dict = lambda: {
            "reference_doctype": "Sales Invoice",
            "reference_name": "SYN-CREDIT", "allocated_amount": -600.0}
        return refunds.refund_permitted(doc)

    def test_unrestricted_finance_login_may_refund(self):
        self.assertTrue(self._permitted("hq@example.test", []))

    def test_company_scoped_login_may_refund_its_own_company(self):
        self.assertTrue(self._permitted("a@example.test", ["TOEFL House"]))

    def test_company_scoped_login_may_not_refund_another_company(self):
        self.assertFalse(self._permitted("b@example.test", ["Other Co"]))


class StockDocumentGuardTests(unittest.TestCase):
    def _guard(self, rows, roles, **header):
        db = FakeDB()
        db.add("Item", name="SYN-BOOK", item_group="Books", is_stock_item=1)
        db.add("Item", name="SYN-SERVICE", item_group="Services",
               is_stock_item=0)
        db.add("Item Group", name="Books", lft=1, rgt=10)
        db.add("Item Group", name="Services", lft=20, rgt=30)
        books, _, _ = load_modules(db, roles=roles)
        doc = Doc(items=[Doc(**row) for row in rows],
                  company="TOEFL House", **header)
        return books.guard_stock_entry(doc)

    def test_zero_value_book_receipt_is_refused(self):
        with self.assertRaises(_ValidationError):
            self._guard([{"item_code": "SYN-BOOK", "qty": 5,
                          "t_warehouse": "WH-A", "basic_rate": 0}],
                        roles=("Stock User",))

    def test_valued_book_receipt_is_allowed(self):
        self.assertIsNone(self._guard(
            [{"item_code": "SYN-BOOK", "qty": 5, "t_warehouse": "WH-A",
              "basic_rate": 175}], roles=("Stock User",)))

    def test_book_write_off_needs_approver_role_and_reason(self):
        rows = [{"item_code": "SYN-BOOK", "qty": 1, "s_warehouse": "WH-A"}]
        with self.assertRaises(_ValidationError):
            self._guard(rows, roles=("Stock User",),
                        remarks="Water damage counted 2026-10-26")
        with self.assertRaises(_ValidationError):
            self._guard(rows, roles=("Stock Manager",))
        self.assertIsNone(self._guard(
            rows, roles=("Stock Manager",),
            remarks="Water damage counted 2026-10-26"))

    def test_non_book_stock_entries_pass_untouched(self):
        self.assertIsNone(self._guard(
            [{"item_code": "SYN-SERVICE", "qty": 1, "s_warehouse": "WH-A"}],
            roles=()))


class WiringTests(unittest.TestCase):
    def test_hooks_pin_the_book_stock_guards_on_all_seams(self):
        hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        for doctype in ("Stock Entry", "Stock Reconciliation"):
            block = hooks.split(f'"{doctype}": {{')[1].split("},")[0]
            for seam in ("validate", "before_cancel",
                         "before_update_after_submit"):
                self.assertIn(seam, block, (doctype, seam))
            self.assertIn("toefl_house.finance.books.guard_", block)

    def test_book_sale_guard_checks_company_warehouse_price_and_group(self):
        source = (APP / "finance" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('books.user_value_permitted(user, "Company"', source)
        self.assertIn('books.user_value_permitted(user, "Warehouse"', source)
        self.assertIn("books.book_item_group_ok(item.item_group)", source)
        self.assertIn("books.book_sale_terms_ok(doc)", source)
        # Reversal paths skip the new-sale price/stock terms.
        self.assertIn('"before_cancel", "before_update_after_submit"', source)


def tearDownModule():
    for name in ("frappe", "toefl_house", "toefl_house.security",
                 "toefl_house.finance", "toefl_house.finance.books",
                 "toefl_house.finance.refunds"):
        sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
