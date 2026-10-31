"""Least-privilege Course Owner creation of a native Education grading scale.

A grading scale is created as a NEW submitted native document, never patched
in place. Historical assessment versions keep their exact native scale link.
The owner is not granted the broad Academics User role or direct Page rights.
"""
from __future__ import annotations

import frappe

from toefl_house.academic import rules as academic_rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest, validate_request_key
from toefl_house.setup_presets.grading_rules import normalize_intervals


@frappe.whitelist(methods=["POST"])
def create_owner_grading_scale(request_key, grading_scale_name, intervals, reason):
    """Create and submit a new immutable, native scale under Owner authority.

    A replacement requires a different name and a new effective-dated
    assessment policy version. No direct native Role or Page permissions change.
    """
    def work(actor):
        try:
            validate_request_key(request_key)
            name = academic_rules.validate_title(grading_scale_name, "Grading scale name")
            clean_reason = configuration_rules.validate_change_reason(reason)
            rows = normalize_intervals(intervals)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.exists("Grading Scale", name):
            raise frappe.ValidationError(
                "A grading scale with this name already exists. "
                "Create a NEW named version instead of changing historical grades")
        doc = frappe.get_doc({
            "doctype": "Grading Scale",
            "grading_scale_name": name,
            "description": f"Owner-approved scale. Reason: {clean_reason}",
            "intervals": rows,
        })
        # The business command's explicit Course Owner authority is narrow.
        # Native Grading Scale permissions otherwise grant Academics User
        # broad rights; do not add that role to the Owner's login.
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        if int(doc.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "Native grading scale submission did not complete; "
                "no policy version may link to this draft")
        result = {
            "name": doc.name, "status": "Submitted",
            "intervals": rows, "reason": clean_reason,
            "next_step": "Link the new scale in a separately reviewed assessment policy version",
        }
        return result, {
            "target": f"Grading Scale:{doc.name}",
            "before_hash": configuration_audit.latest_after_hash(
                f"Grading Scale:{doc.name}"),
            "after_hash": digest(result),
        }

    return configuration_audit.execute(
        "create_owner_grading_scale", request_key,
        {"grading_scale_name": grading_scale_name, "intervals": intervals,
         "reason": reason}, work)
