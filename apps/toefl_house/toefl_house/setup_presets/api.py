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


def _native_program_has_curriculum(native_program):
    """Fail closed if an existing level cannot schedule a native Course.

    Before the integrated Course factory fix, native Programs could exist
    without any linked Course. They must be reviewed, not shown as a matched
    first-run level or silently duplicated by an installer.
    """
    if not frappe.db.exists("Program", native_program):
        return False
    links = _bounded_rows(
        "Program Course", bound=_MAX_COMPONENT_ROWS,
        filters={"parent": native_program, "parenttype": "Program"},
        fields=["course", "required"])
    names = [link.get("course") for link in links]
    if not names or any(not isinstance(name, str) or not name.strip()
                        for name in names) or len(set(names)) != len(names):
        return False
    return all(frappe.db.exists("Course", name) for name in names)


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
    native_anchors = {}
    for row in level_rows:
        if row.native_program:
            if row.native_program in native_anchors:
                raise frappe.ValidationError(
                    f"Two levels use native Program {row.native_program}; "
                    "review and correct the existing links before setup")
            native_anchors[row.native_program] = row.code
    # An older/incomplete installation may contain the native Program or
    # Course that the new level factory would otherwise create, without a
    # matching TH Program Level. The read-only preview must catch these
    # orphans before offering to create another native identity.
    native_program_rows = _bounded_rows(
        "Program", fields=["name", "program_name"])
    native_course_rows = _bounded_rows(
        "Course", fields=["name", "course_name"])
    levels = {}
    tuition = {}
    for row in level_rows:
        # Historical duration versions are expected. Fetch only the most
        # recent row without treating older effective-dated history as an error.
        duration_rows = frappe.db.get_all(
            "TH Level Duration", filters={"parent": row.name},
            fields=["duration_value", "duration_unit", "effective_from"],
            order_by="effective_from desc", limit_page_length=1)
        months = None
        if duration_rows:
            duration = duration_rows[0]
            if str(duration.duration_unit).lower() in (
                    "month", "months", "solar hijri month"):
                value = float(duration.duration_value)
                months = int(value) if value.is_integer() else None
        levels[row.code] = {
            "title": row.title,
            "family": program_codes.get(row.family) or "",
            "duration_months": months,
            "status": row.status,
            "native_program": row.native_program or "",
            "curriculum_ready": (
                _native_program_has_curriculum(row.native_program)
                if row.native_program else False),
            "next_level": row.next_level or "",
        }
        if row.native_program:
            structures = _bounded_rows(
                "Fee Structure", filters={"program": row.native_program,
                                          "docstatus": ("!=", 2)},
                fields=["name", "academic_year", "docstatus"],
                order_by="name", bound=_MAX_COMPONENT_ROWS)
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
                if (structure.docstatus == 0
                        and len(charges) == 1 and len(component_rows) == 1):
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
    category_rows = _bounded_rows(
        "Fee Category", fields=["name", "item"])
    categories = [row.name for row in category_rows]
    category_items = {row.name: row.item or "" for row in category_rows}
    if len(category_items) != len(categories):
        raise frappe.ValidationError("Duplicate native Fee Category; setup cannot continue")
    return {"programs": programs, "levels": levels, "years": years,
            "fee_categories": categories, "fee_category_items": category_items,
            "tuition": tuition,
            "native_program_titles": [p.get("program_name") for p in native_program_rows],
            "native_course_titles": [c.get("course_name") for c in native_course_rows]}


@frappe.whitelist(methods=["GET"])
def preview_owner_initial_setup():
    """Inspect data only; NEVER initialize, post, replace, or approve."""
    _owner()
    snapshot = _snapshot()
    preview = preview_catalog(snapshot)
    from toefl_house.setup_presets.preset import load_preset
    import json
    preset = load_preset()
    scale = preset["assessment"]["grading_scale"]
    preview["daily_timetable"] = preset.get("daily_timetable")
    preview["grading_scale_suggestion"] = {
        "grading_scale_name": scale["name"],
        "intervals": json.dumps([
            {"grade_code": item["grade"], "threshold": item["min_percent"]}
            for item in scale["grade_thresholds"]
        ], separators=(",", ":")),
        "exists": bool(frappe.db.exists("Grading Scale", scale["name"])),
    }
    if preview["counts"]["review"] == 0:
        from toefl_house.setup_presets.catalog_plan import prepare_catalog_plan
        from toefl_house.setup_presets.installer import preview_digest
        planned = prepare_catalog_plan(snapshot)
        preview["plan_hash"] = preview_digest(snapshot)
        operations = {}
        for action in planned["actions"]:
            kind = action["operation"]
            operations[kind] = operations.get(kind, 0) + 1
        preview["planned_actions_count"] = planned["count"]
        preview["planned_operation_counts"] = operations
    else:
        preview["plan_hash"] = None
        preview["planned_actions_count"] = None
        preview["planned_operation_counts"] = {}
    return preview
