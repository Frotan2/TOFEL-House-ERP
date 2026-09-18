"""Controller for TH Discount Rule: identity and validation on every write path."""
import frappe
from frappe import _

from toefl_house.academic import rules


def validate(doc, method=None):
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Discount rule title")
    rules.validate_discount_percentage(doc.discount_percentage)
    rules.validate_precedence(doc.precedence)
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
