"""Native Reception → Finance cash handover: isolated command-behaviour proof.

Execute the real domain command against a guarded fake document and ledger
boundary. This is NOT a native MariaDB posting acceptance test.
"""
import importlib.util
from decimal import Decimal
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
FINANCE = "finance-manager@example.test"
COLLECTOR = "reception@example.test"


class Transfer:
    def __init__(self, facts, test):
        self.__dict__.update(facts)
        self.name = "ACC-HANDOVER-TEST"
        self.flags = types.SimpleNamespace(ignore_permissions=False)
        self.test = test
        self.insert = Mock(return_value=self)
        self.submit = Mock(side_effect=self.post)

    def post(self):
        # A submit call returning is not evidence that a transfer posted.
        # The test deliberately models corrupt/non-posted outcomes.
        if self.test.transfer_override:
            self.__dict__.update(self.test.transfer_override)
        else:
            self.docstatus = 1


class Receipt:
    def __init__(self, name, amount="100.00", collector=COLLECTOR, company="TOEFL House",
                 counter="Reception Cash", currency="AFN", student="STU-1",
                 fees="EDU-FEE-1"):
        self.name = name
        self.docstatus = 1
        self.payment_type = "Receive"
        self.party_type = "Student"
        self.party = student
        self.th_reception_collector = collector
        self.th_collection_fees = fees
        self.th_collection_handover = None
        self.th_collection_synthetic = 1
        self.unallocated_amount = 0
        self.company = company
        self.paid_to = counter
        self.paid_from_account_currency = currency
        self.paid_to_account_currency = currency
        self.paid_amount = Decimal(amount)
        self.received_amount = Decimal(amount)
        self.references = [types.SimpleNamespace(
            reference_doctype="Fees", reference_name=fees,
            allocated_amount=Decimal(amount))]
        self.flags = types.SimpleNamespace(ignore_permissions=False)
        self.save = Mock(return_value=self)


class NativeCashHandoverTests(unittest.TestCase):
    def setUp(self):
        self.receipts = {
            "PAY-1": Receipt("PAY-1"),
            "PAY-2": Receipt("PAY-2", amount="50.00", fees="EDU-FEE-2"),
        }
        self.transfer = None
        self.transfer_override = None
        self.ledger_closing = Decimal("150.00")
        self.actor = FINANCE
        self.locked_receipts = []
        self.account_locks = []
        frappe = types.ModuleType("frappe")
        frappe.ValidationError = type("BadRequest", (Exception,), {})
        frappe.PermissionError = type("Forbidden", (Exception,), {})
        frappe.DuplicateEntryError = type("Duplicate", (Exception,), {})
        frappe.session = types.SimpleNamespace(user=FINANCE)
        frappe.whitelist = lambda **_kwargs: lambda fn: fn
        frappe.utils = types.SimpleNamespace(today=lambda: "2026-11-02")
        frappe.get_cached_value = lambda dt, name, field: (
            "Main Cash" if field == "default_cash_account" else "AFN")
        def get_doc(doctype, name=None, for_update=False):
            if isinstance(doctype, dict):
                self.transfer = Transfer(doctype, self)
                return self.transfer
            if doctype == "Payment Entry" and name in self.receipts and for_update:
                self.locked_receipts.append(name)
                return self.receipts[name]
            raise AssertionError(("unexpected native read", doctype, name))
        frappe.get_doc = get_doc
        def get_value(dt, name, field):
            if dt == "Fees" and field == "student":
                return "STU-1"
            raise AssertionError((dt, name, field))
        def sql(stmt, params):
            self.account_locks.append(tuple(params))
            return []
        frappe.db = types.SimpleNamespace(sql=sql, get_value=get_value)

        mods = {"frappe": frappe}
        def module(name, **attrs):
            obj = types.ModuleType(name)
            for k, v in attrs.items():
                setattr(obj, k, v)
            mods[name] = obj
            return obj
        module("toefl_house")
        module("toefl_house.api", _execute=lambda _kind, _key, _payload, work: work(self.actor)[0])
        audit = module("toefl_house.configuration.audit")
        module("toefl_house.configuration", audit=audit)
        finance = module("toefl_house.finance")
        spec = importlib.util.spec_from_file_location(
            "toefl_house.finance.collection_rules", APP / "finance/collection_rules.py")
        rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rules)
        mods["toefl_house.finance.collection_rules"] = rules
        finance.collection_rules = rules
        module("toefl_house.finance.collection_reads", native_reference_reads=lambda *a: None)
        module("toefl_house.finance.company_scope", require_finance_company=lambda *a: None)
        module("toefl_house.finance.cashier", drawer_balances=lambda company, accounts, day: [
            {"closing": self.ledger_closing}])
        module("toefl_house.policy", digest=lambda value: "test-audit-hash")
        module("toefl_house.security", active_command_kind=lambda: "accept_reception_handover",
               record_synthetic_flag=lambda: 1)
        self.ctx = patch.dict(sys.modules, mods)
        self.ctx.start()
        self.addCleanup(self.ctx.stop)
        spec = importlib.util.spec_from_file_location(
            "cash_handover_under_test", APP / "finance/collections.py")
        target = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(target)
        target.require_schema = lambda: None
        target.require_finance_company = lambda company: company
        target.cash_account = lambda name, company: types.SimpleNamespace(name=name)
        self.handler = target.accept_reception_handover
        self.frappe = frappe

    def handover(self, names=None, amount="150.00", key="handover-001"):
        return self.handler(key, names or ["PAY-1", "PAY-2"], amount)

    def test_exact_count_posts_one_native_transfer_then_marks_each_receipt(self):
        result = self.handover(names=["PAY-2", "PAY-1"])
        self.assertEqual(result["amount"], 150)
        self.assertEqual(result["receipts"], ["PAY-1", "PAY-2"])
        self.assertEqual(self.locked_receipts, ["PAY-1", "PAY-2"],
                         "sorted locks prevent reversed batch lock order")
        self.assertEqual(self.account_locks, [("Reception Cash",)])
        self.assertEqual(self.transfer.payment_type, "Internal Transfer")
        self.assertEqual(self.transfer.paid_from, "Reception Cash")
        self.assertEqual(self.transfer.paid_to, "Main Cash")
        self.assertEqual(self.transfer.paid_amount, 150)
        self.assertEqual(self.transfer.docstatus, 1)
        self.transfer.submit.assert_called_once_with()
        for receipt in self.receipts.values():
            self.assertEqual(receipt.th_collection_handover, "ACC-HANDOVER-TEST")
            receipt.save.assert_called_once_with(ignore_permissions=True)

    def test_second_handover_of_same_source_receipts_fails(self):
        self.handover()
        first_transfer = self.transfer
        with self.assertRaisesRegex(self.frappe.ValidationError, "not been handed over"):
            self.handover(key="different-key")
        self.assertIs(self.transfer, first_transfer)
        for receipt in self.receipts.values():
            receipt.save.assert_called_once()

    def test_wrong_physical_cash_count_or_insufficient_native_ledger_refuses_transfer(self):
        for count, closing in (("149.99", "150.00"), ("150.01", "150.00"),
                               ("150.00", "149.99")):
            with self.subTest(count=count, closing=closing):
                self.ledger_closing = Decimal(closing)
                with self.assertRaises(self.frappe.ValidationError):
                    self.handover(amount=count)
                self.assertIsNone(self.transfer)
                self.assertTrue(all(r.th_collection_handover is None
                                    for r in self.receipts.values()))
        self.ledger_closing = Decimal("150")

    def test_self_handover_and_mixed_collector_or_counter_are_refused(self):
        self.actor = COLLECTOR
        with self.assertRaisesRegex(self.frappe.PermissionError, "Another Finance"):
            self.handover()
        self.actor = FINANCE
        self.receipts["PAY-2"].th_reception_collector = "another-reception@example.test"
        with self.assertRaisesRegex(self.frappe.ValidationError, "one collector"):
            self.handover()
        self.receipts["PAY-2"].th_reception_collector = COLLECTOR
        self.receipts["PAY-2"].paid_to = "Other Cash"
        with self.assertRaisesRegex(self.frappe.ValidationError, "one collector"):
            self.handover()
        self.assertIsNone(self.transfer)

    def test_duplicate_or_nonpositive_handovers_are_refused(self):
        for names, amount in ((["PAY-1", "PAY-1"], "200"), ([], "150"),
                              (["PAY-1"], "0"), (["PAY-1"], "-1")):
            with self.subTest(names=names, amount=amount):
                with self.assertRaises(self.frappe.ValidationError):
                    self.handler("another-key", names, amount)
                self.assertIsNone(self.transfer)

    def test_transfer_must_be_posted_and_reconciled_before_any_receipt_is_marked(self):
        for override in ({"docstatus": 0}, {"paid_amount": 149},
                         {"received_amount": 151}, {"paid_to": "Foreign Cash"},
                         {"paid_from_account_currency": "USD"}):
            with self.subTest(override=override):
                self.transfer_override = override
                with self.assertRaisesRegex(self.frappe.ValidationError,
                                            "native cash transfer did not reconcile"):
                    self.handover()
                self.assertIsNotNone(self.transfer)
                for receipt in self.receipts.values():
                    self.assertIsNone(receipt.th_collection_handover)
                    receipt.save.assert_not_called()
                self.transfer = None
        self.transfer_override = None


if __name__ == "__main__":
    unittest.main()
