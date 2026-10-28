"""Course-Owner-only, read-only initial setup preview.

This endpoint intentionally does not seed a customer database or perform any
privileged write. It reuses native Education/ERPNext catalog facts and reports
conflicts for an explicit, audited Owner decision.
"""
from __future__ import annotations

import frappe

from toefl_house.setup_presets.preset import preview_catalog


def _owner():
    actor = getattr(frappe.session, "user", "Guest")
    if not actor or actor == "Guest" or "Course Owner" not in frappe.get_roles(actor):
        raise frappe.PermissionError("Only the Course Owner may inspect the installation preset")
    return actor


def _snapshot():
    families = frappe.db.get_all("TH Academic Program", fields=["name", "code", "title"])
    program_codes = {row.name: row.code for row in families}
    programs = {row.code: {"title": row.title} for row in families}
    level_rows = frappe.db.get_all(
        "TH Program Level", fields=["name", "code", "title", "family", "native_program"])
    levels = {}
    tuition = {}
    for row in level_rows:
        duration_rows = frappe.db.get_all(
            "TH Level Duration", filters={"parent": row.name},
            fields=["duration_value", "duration_unit", "effective_from"],
            order_by="effective_from desc", limit=1)
        months = None
        if duration_rows:
            duration = duration_rows[0]
            if str(duration.duration_unit).lower() in ("month", "months"):
                value = float(duration.duration_value)
                months = int(value) if value.is_integer() else None
        levels[row.code] = {
            "title": row.title,
            "family": program_codes.get(row.family) or "",
            "duration_months": months,
        }
        if row.native_program:
            structures = frappe.db.get_all(
                "Fee Structure", filters={"program": row.native_program, "docstatus": 0},
                fields=["name", "academic_year"], order_by="name")
            for structure in structures:
                component_rows = frappe.db.get_all(
                    "Fee Component", filters={"parent": structure.name, "parenttype": "Fee Structure"},
                    fields=["fees_category", "amount"])
                charges = [float(c.amount) for c in component_rows
                           if c.fees_category == "Semester Tuition Fee"]
                if len(charges) == 1:
                    key = str(structure.academic_year)
                    # An ambiguous second structure must not be accepted as a match.
                    (tuition.setdefault(row.code, {}))[key] = (
                        charges[0] if key not in tuition[row.code] else None)
    years = {}
    for year in frappe.db.get_all(
            "Academic Year", fields=["name", "year_start_date", "year_end_date"]):
        years[year.name] = {"start": str(year.year_start_date),
                            "end": str(year.year_end_date)}
    categories = [row.name for row in frappe.db.get_all("Fee Category", fields=["name"])]
    return {"programs": programs, "levels": levels, "years": years,
            "fee_categories": categories, "tuition": tuition}


@frappe.whitelist(methods=["GET"])
def preview_owner_initial_setup():
    """Inspect data only; NEVER initialize, post, replace, or approve."""
    _owner()
    return preview_catalog(_snapshot())
