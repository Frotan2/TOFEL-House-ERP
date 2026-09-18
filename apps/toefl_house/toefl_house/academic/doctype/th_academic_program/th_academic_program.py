"""Controller for TH Academic Program: identity and status rules on every path."""
import frappe
from frappe import _

from toefl_house.academic import rules


def validate(doc, method=None):
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Program title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
