"""Child row controller for TH Cashier Count.

The row is written only as part of a guarded cashier day close, so the
parent's validation owns the rules. This controller exists because every
DocType directory in the app carries its own module, and it keeps the child
honest if a future native path ever writes it: counted money is never
negative and the variance is counted minus expected.
"""
import frappe
from frappe.model.document import Document


class THCashierCount(Document):
    def validate(self):
        counted = frappe.utils.flt(self.get("counted_amount"))
        expected = frappe.utils.flt(self.get("expected_amount"))
        if counted < 0:
            frappe.throw("A counted amount cannot be negative")
        self.set("variance", round(counted - expected, 2))
