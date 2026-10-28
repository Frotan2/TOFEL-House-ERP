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


_MAX_CATALOG_ROWS = 500
_MAX_COMPONENT_ROWS = 100


def _bounded_rows(doctype, *, bound=_MAX_CATALOG_ROWS, **kwargs):
    """Fail closed rather than silently preview only Frappe's first 20 rows."""
    rows = frappe.db.get_all(doctype, limit_page_length=bound + 1, **kwargs)
    if len(rows) > bound:
        raise frappe.ValidationError(
            f"Setup cannot safely inspect more than {bound} {doctype} records; "
            "an administrator must review the catalog before continuing")
    return rows


def _unique_by(rows, key, description):
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip() or value in result:
            raise frappe.ValidationError(
                f"Missing or duplicate {description}; setup preview cannot proceed")
        result[value] = row
    return result


def _snapshot():
    families = _bounded_rows(
        "TH Academic Program", fields=["name", "code", "title", "status"])
    _unique_by(families, "name", "program identifier")
    family_by_code = _unique_by(families, "code", "program code")
    program_codes = {row.name: row.code for row in families}
    programs = {code: {"title": row.title, "status": row.status}
                for code, row in family_by_code.items()}
    level_rows = _bounded_rows(
        "TH Program Level",
        fields=["name", "code", "title", "family", "native_program",
                "next_level", "status"])
    _unique_by(level_rows, "name", "level identifier")
    _unique_by(level_rows, "code", "level code")
    levels = {}
    tuition = {}
    for row in level_rows:
        duration_rows = _bounded_rows(
            "TH Level Duration", filters={"parent": row.name},
            fields=["duration_value", "duration_unit", "effective_from"],
            order_by="effective_from desc", bound=1)
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
            "status": row.status,
            "native_program": row.native_program or "",
            "next_level": row.next_level or "",
        }
        if row.native_program:
            structures = _bounded_rows(
                "Fee Structure", filters={"program": row.native_program, "docstatus": 0},
                fields=["name", "academic_year"], order_by="name",
                bound=_MAX_COMPONENT_ROWS)
            for structure in structures:
                component_rows = _bounded_rows(
                    "Fee Component", filters={"parent": structure.name,
                                               "parenttype": "Fee Structure"},
                    fields=["fees_category", "amount"], bound=_MAX_COMPONENT_ROWS)
                charges = [c for c in component_rows
                           if c.fees_category == "Semester Tuition Fee"]
                # A draft with zero/multiple tuition components, unexpected
                # extra components or a bad amount is a conflict, NOT absence.
                price = None
                if len(charges) == 1 and len(component_rows) == 1:
                    try:
                        price = float(charges[0].amount)
                    except (ValueError, TypeError):
                        pass
                key = str(structure.academic_year)
                # A second draft for this level/year is always ambiguous.
                known = tuition.setdefault(row.code, {})
                known[key] = price if key not in known else None
    years = {}
    for year in _bounded_rows(
            "Academic Year", fields=["name", "year_start_date", "year_end_date"]):
        if year.name in years:
            raise frappe.ValidationError("Duplicate academic year in setup preview")
        years[year.name] = {"start": str(year.year_start_date),
                            "end": str(year.year_end_date)}
    categories = [row.name for row in _bounded_rows(
        "Fee Category", fields=["name"])]
    return {"programs": programs, "levels": levels, "years": years,
            "fee_categories": categories, "tuition": tuition}


@frappe.whitelist(methods=["GET"])
def preview_owner_initial_setup():
    """Inspect data only; NEVER initialize, post, replace, or approve."""
    _owner()
    snapshot = _snapshot()
    preview = preview_catalog(snapshot)
    if preview["counts"]["review"] == 0:
        from toefl_house.setup_presets.installer import preview_digest
        preview["plan_hash"] = preview_digest(snapshot)
    else:
        preview["plan_hash"] = None
    return preview
