"""Controller for TH Discount Rule: identity and validation on every write path."""
import frappe
from frappe import _
from frappe.model.document import Document

from toefl_house.academic import rules
from toefl_house.configuration import rules as configuration_rules


class THDiscountRule(Document):
    def validate(self):
        validate(self)


def validate(doc, method=None):
    # Native form, API and data-import edits cannot bypass the audited
    # Course Owner configuration command, which records every activation.
    try:
        configuration_rules.assert_command_context(_(
            "Discounts must be created and approved through guided "
            "configuration actions, not changed directly in the form"))
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    if configuration_rules.active_command() not in (
            "create_discount_rule", "set_discount_rule_status"):
        raise frappe.PermissionError(
            "Discount changes require the audited discount configuration action")
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Discount rule title")
    rules.validate_discount_award(
        doc.discount_percentage, doc.get("student") or "",
        doc.get("description") or "", active=doc.status == "Active")
    rules.validate_precedence(doc.precedence)
    if doc.status not in ("Active", "Retired"):
        frappe.throw(_("Status must be Active or Retired"))
