"""Native CRUD cannot rewrite the provenance of a cash receipt or handover."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/collections.py"


class Doc(SimpleNamespace):
    def __getattr__(self, key):
        return None

    def get(self, key):
        return getattr(self, key, None)

    def get_doc_before_save(self):
        return getattr(self, "before", None)


class CollectionGuardTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "guard_collection_fields")
        self.kind = None
        self.scope = dict(frappe=SimpleNamespace(PermissionError=PermissionError,
            ValidationError=ValueError, session=SimpleNamespace(user="reception")),
            active_command_kind=lambda: self.kind,
            FIELDS=("th_reception_collector", "th_collection_fees", "th_collection_handover", "th_collection_synthetic"))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), self.scope)
        self.guard = self.scope["guard_collection_fields"]

    def receipt(self, **updates):
        values = dict(docstatus=1, payment_type="Receive", party_type="Student", party="STUDENT",
            company="COMPANY", paid_from="AR", paid_to="COUNTER", paid_amount=100,
            received_amount=100, posting_date="2026-10-27", th_reception_collector="reception",
            paid_from_account_currency="AFN", paid_to_account_currency="AFN",
            source_exchange_rate=1, target_exchange_rate=1, amended_from=None,
            th_collection_fees="FEE", th_collection_handover=None, th_collection_synthetic=1,
            references=[Doc(reference_doctype="Fees", reference_name="FEE")])
        values.update(updates)
        return Doc(**values)

    def test_arbitrary_crud_and_erasing_tags_are_denied(self):
        original = self.receipt()
        with self.assertRaises(PermissionError):
            self.guard(original, "validate")
        blank = Doc(before=original)
        with self.assertRaises(PermissionError):
            self.guard(blank, "validate")

    def test_even_authorized_command_cannot_delete(self):
        self.kind = "correct_reception_collection"
        with self.assertRaises(PermissionError):
            self.guard(self.receipt(), "on_trash")

    def test_only_unhanded_receipt_has_owner_cancel_path(self):
        self.kind = "accept_reception_handover"
        with self.assertRaises(PermissionError):
            self.guard(self.receipt(), "before_cancel")
        self.kind = "correct_reception_collection"
        self.guard(self.receipt(), "before_cancel")
        with self.assertRaises(PermissionError):
            self.guard(self.receipt(th_collection_handover="TRANSFER"), "before_cancel")

    def test_receipt_requires_exact_fee_and_authenticated_collector(self):
        self.kind = "record_reception_collection"
        self.guard(self.receipt(), "validate")
        with self.assertRaises(PermissionError):
            self.guard(self.receipt(th_reception_collector="other"), "validate")
        with self.assertRaises(ValueError):
            self.guard(self.receipt(references=[Doc(reference_doctype="Sales Invoice", reference_name="FEE")]))

    def test_handover_can_link_but_cannot_rewrite_receipt(self):
        self.kind = "accept_reception_handover"
        before = self.receipt()
        self.guard(self.receipt(before=before, th_collection_handover="TRANSFER"), "before_update_after_submit")
        for field, value in (("paid_to", "OTHER"), ("paid_amount", 99), ("paid_to_account_currency", "USD"),
                             ("party", "OTHER"), ("source_exchange_rate", 2), ("amended_from", "OTHER")):
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.guard(self.receipt(before=before, th_collection_handover="TRANSFER", **{field: value}))
        with self.assertRaises(ValueError):
            self.guard(self.receipt(before=self.receipt(th_collection_handover="OLD"), th_collection_handover="NEW"))

    def test_tagged_transfer_is_only_available_to_handover_command(self):
        transfer = Doc(th_reception_collector="reception", payment_type="Internal Transfer")
        self.kind = "accept_reception_handover"
        self.guard(transfer)
        self.kind = "record_reception_collection"
        with self.assertRaises(ValueError):
            self.guard(transfer)


if __name__ == "__main__":
    unittest.main()
