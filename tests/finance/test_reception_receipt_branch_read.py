"""Reception cash receipts must stop being readable after branch access removal.

Use the actual GET handler with isolated Frappe and command-scope doubles.
No money document is created; this test protects historical student/cash
privacy after a staff member's permission is revoked.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/toefl_house/toefl_house/finance/collections.py"
ACTOR = "staff-reception@example.test"


class ReceiptReadBranchTests(unittest.TestCase):
    def setUp(self):
        self.allowed = {"Kabul"}
        self.roles = {"Reception"}
        self.collector = ACTOR
        self.scoped = Mock()
        self.document = types.SimpleNamespace(
            name="ACC-PAY-TEST", th_collection_fees="EDU-FEE-TEST",
            docstatus=1, th_reception_collector=self.collector,
            payment_type="Receive", party_type="Student", party="STU-TEST",
            references=[types.SimpleNamespace(
                reference_doctype="Fees", reference_name="EDU-FEE-TEST")])

        frappe = types.ModuleType("frappe")
        frappe.PermissionError = type("AccessDenied", (Exception,), {})
        frappe.ValidationError = type("BadRequest", (Exception,), {})
        frappe.session = types.SimpleNamespace(user=ACTOR)
        frappe.get_roles = lambda _actor: set(self.roles)
        frappe.db = types.SimpleNamespace(
            get_value=lambda dt, _name, col: 1 if dt == "User" and col == "enabled" else None)
        frappe.get_doc = Mock(side_effect=lambda _dt, _name: self.document)
        frappe.whitelist = lambda **kwargs: lambda func: func
        frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})

        mods = {"frappe": frappe}
        def module(name, **attrs):
            value = types.ModuleType(name)
            for key, item in attrs.items():
                setattr(value, key, item)
            mods[name] = value
            return value

        module("toefl_house")
        module("toefl_house.api", _execute=lambda *args, **kwargs: None)
        audit = module("toefl_house.configuration.audit")
        module("toefl_house.configuration", audit=audit)
        module("toefl_house.finance")
        module("toefl_house.finance.collection_rules",
               bounded_text=lambda value, label, maximum=140: value)
        module("toefl_house.finance.collection_reads", native_reference_reads=lambda *a: None)
        module("toefl_house.finance.company_scope", require_finance_company=lambda *a: None)
        module("toefl_house.policy", digest=lambda *a: "digest")
        module("toefl_house.security", active_command_kind=lambda: None,
               record_synthetic_flag=lambda: 1)
        scope = module("toefl_house.command_scope")
        scope.actor_branches = lambda _actor: set(self.allowed)
        scope.authorize_command_scope = self.scoped

        # from ...finance import collection_rules and nested import resolution
        mods["toefl_house.finance"].collection_rules = mods["toefl_house.finance.collection_rules"]
        mods["toefl_house.configuration"].audit = audit
        ctx = patch.dict(sys.modules, mods)
        ctx.start()
        self.addCleanup(ctx.stop)
        spec = importlib.util.spec_from_file_location(
            "th_receipt_read_under_test", SOURCE)
        target = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(target)
        target.require_schema = lambda: None
        target.receipt_facts = lambda doc: {"number": doc.name}
        self.handler = target.get_collection_receipt
        self.frappe = frappe

    def test_own_receipt_is_available_while_branch_is_assigned(self):
        self.assertEqual(self.handler("ACC-PAY-TEST")["number"], "ACC-PAY-TEST")
        self.scoped.assert_called_once_with(
            "read_collection_receipt", {"payment_entry": "ACC-PAY-TEST"}, ACTOR)

    def test_branch_revocation_removes_access_to_prior_own_receipt(self):
        self.handler("ACC-PAY-TEST")
        self.allowed = set()
        self.scoped.reset_mock()
        self.frappe.get_doc.reset_mock()
        with self.assertRaisesRegex(self.frappe.PermissionError, "currently assigned Branch"):
            self.handler("ACC-PAY-TEST")
        self.scoped.assert_not_called()
        self.frappe.get_doc.assert_not_called()

    def test_receipt_from_another_receptionist_is_not_readable(self):
        self.document.th_reception_collector = "other-reception@example.test"
        with self.assertRaisesRegex(self.frappe.PermissionError, "only its own"):
            self.handler("ACC-PAY-TEST")

    def test_unrelated_payment_entry_cannot_be_printed_as_a_reception_receipt(self):
        invalid_updates = (
            {"payment_type": "Internal Transfer"},
            {"party_type": "Customer"},
            {"party": ""},
            {"th_reception_collector": None},
            {"th_collection_fees": None},
            {"docstatus": 0},
            {"references": []},
            {"references": [types.SimpleNamespace(
                reference_doctype="Sales Invoice", reference_name="EDU-FEE-TEST")]},
            {"references": [types.SimpleNamespace(
                reference_doctype="Fees", reference_name="DIFFERENT-FEE")]},
        )
        original = dict(vars(self.document))
        for update in invalid_updates:
            with self.subTest(update=update):
                vars(self.document).update(original)
                vars(self.document).update(update)
                with self.assertRaisesRegex(
                        self.frappe.PermissionError, "not an issued Reception receipt"):
                    self.handler("ACC-PAY-TEST")

    def test_void_receipt_still_has_explicit_auditable_read(self):
        self.document.docstatus = 2
        self.assertEqual(self.handler("ACC-PAY-TEST")["number"], "ACC-PAY-TEST")

    def test_disabled_or_unauthorized_actor_is_denied_before_loading_receipt(self):
        self.roles = set()
        self.frappe.get_doc.reset_mock()
        with self.assertRaisesRegex(self.frappe.PermissionError, "permitted staff"):
            self.handler("ACC-PAY-TEST")
        self.frappe.get_doc.assert_not_called()
        self.roles = {"Reception"}
        self.frappe.db.get_value = lambda *args: 0
        with self.assertRaisesRegex(self.frappe.PermissionError, "permitted staff"):
            self.handler("ACC-PAY-TEST")
        self.frappe.get_doc.assert_not_called()

    def test_foreign_branch_is_rechecked_before_loading_receipt(self):
        self.scoped.side_effect = self.frappe.PermissionError("outside Branch")
        with self.assertRaisesRegex(self.frappe.PermissionError, "outside Branch"):
            self.handler("ACC-PAY-TEST")
        self.frappe.get_doc.assert_not_called()

    def test_finance_manager_read_uses_independent_finance_scope(self):
        self.roles = {"Finance Manager"}
        self.allowed = set()
        self.document.th_reception_collector = "other-reception@example.test"
        self.assertEqual(self.handler("ACC-PAY-TEST")["number"], "ACC-PAY-TEST")
        self.scoped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
