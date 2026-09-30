"""Drop the retired TH Capacity Objective / TH Metric Stewardship Policy doctypes.

Both carriers had no consumer in the product (no report derived metrics and the
release gate that referenced capacity objectives was retired). Their code was
removed; this patch removes the orphaned DocType records and tables on sites
that installed an earlier build.
"""
import frappe

RETIRED = (
    "TH Capacity Objective Version",
    "TH Capacity Objective",
    "TH Metric Stewardship Policy Version",
    "TH Metric Stewardship Policy",
)


def execute():
    for doctype in RETIRED:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
