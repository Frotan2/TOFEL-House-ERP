"""Canonical reporting definition register (§29).

Central repository of defined business facts, metric calculations, and
governance owners across all role desks. Desks and reports consume these
canonical definitions so presentation stays consistent across surfaces.
"""

REPORTING_DEFINITIONS = {
    # Money & Receivable Facts
    "collected_today": {
        "label": "Collected today",
        "definition": "Submitted Payment Entry rows of type Receive posted today, summed per currency.",
        "owner": None,
        "category": "Finance",
    },
    "invoiced_today": {
        "label": "Invoiced today",
        "definition": "Submitted Sales Invoice and Fees grand totals posted today, summed per currency.",
        "owner": None,
        "category": "Finance",
    },
    "outstanding_invoices": {
        "label": "Outstanding invoices",
        "definition": "Submitted Sales Invoices with native outstanding_amount above zero.",
        "owner": "Finance Officer",
        "category": "Finance",
    },
    "outstanding_tuition": {
        "label": "Outstanding tuition fees",
        "definition": "Submitted Fees with native outstanding_amount above zero.",
        "owner": "Finance Officer",
        "category": "Finance",
    },
    "corrections_pending": {
        "label": "Corrections pending",
        "definition": "Correction requests in Requested status.",
        "owner": "Finance Officer",
        "category": "Finance",
    },
    "awaiting_billing": {
        "label": "Enrollments awaiting billing",
        "definition": "Submitted Program Enrollments with no non-cancelled Fees row.",
        "owner": "Finance Officer",
        "category": "Finance",
    },

    # Academic Control Plane & Governance Facts
    "active_programs": {
        "label": "Active academic programs",
        "definition": "TH Academic Program rows in Active status.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "active_levels": {
        "label": "Active program levels",
        "definition": "TH Program Level rows in Active status.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "ungoverned_levels": {
        "label": "Levels with no governing duration",
        "definition": "Active levels whose duration versions contain no version effective on today's date.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "unanchored_levels": {
        "label": "Levels without native anchor",
        "definition": "Levels whose native Program link is absent. This is a configuration integrity fault.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "levels_in_use": {
        "label": "Levels in active use",
        "definition": "Levels whose native program carries at least one submitted native enrollment.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "progression_linked": {
        "label": "Levels with configured progression",
        "definition": "Levels whose next level is configured.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "active_fee_types": {
        "label": "Active fee types",
        "definition": "Native Fee Category records (each carries its own accounting Item).",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "unplanned_levels": {
        "label": "Active levels without fee plan",
        "definition": "Active levels with no editable native Fee Structure for the current academic year.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "unanchored_native_programs": {
        "label": "Native programs outside control plane",
        "definition": "Native Education Program records no configured level points to.",
        "owner": "Course Owner",
        "category": "Academic",
    },
    "discount_rules_active": {
        "label": "Active discount rules",
        "definition": "TH Discount Rule rows in Active status under Policy A (single discount per charge line).",
        "owner": "Course Owner",
        "category": "Academic",
    },
}


def get_reporting_definition(key):
    """Retrieve canonical definition tuple (label, definition, owner)."""
    item = REPORTING_DEFINITIONS.get(key)
    if not item:
        raise KeyError(f"Unknown reporting definition: {key}")
    return item["label"], item["definition"], item["owner"]


def all_definitions():
    """Return dictionary of all defined reporting facts."""
    return dict(REPORTING_DEFINITIONS)
