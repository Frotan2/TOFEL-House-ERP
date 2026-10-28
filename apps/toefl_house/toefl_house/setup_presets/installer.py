"""Release-gated, Owner-authorized, atomic academic first-run setup.

The endpoint is intentionally disabled on every existing installation.
Setting just one switch cannot enable it. The verified customer installer must
explicitly qualify the release *and* authorize clean-site catalog setup. The
endpoint never creates students, staff, grades, salaries or posted Fees, and
never changes Owner backup/retention policy or tax.
"""
from __future__ import annotations

import frappe

from toefl_house import academic
from toefl_house.policy import digest
from toefl_house.setup_presets.api import _owner, _snapshot
from toefl_house.setup_presets.catalog_plan import action_request_key, prepare_catalog_plan
from toefl_house.setup_presets.preset import load_preset, preview_catalog


_ALLOWED = {
    "create_academic_year": academic.create_academic_year,
    "create_program": academic.create_program,
    "create_level": academic.create_level,
    "set_next_level": academic.set_next_level,
    "create_fee_type": academic.create_fee_type,
    "set_level_fee_component": academic.set_level_fee_component,
}
_NO_LIVE_RECORDS = ("Student", "Student Applicant", "Program Enrollment",
                    "Fees", "Payment Entry", "Sales Invoice", "Salary Slip")


def _qualified_site():
    if (frappe.conf.get("toefl_house_customer_release_approved") is not True
            or frappe.conf.get("toefl_house_owner_catalog_install_enabled") is not True):
        raise frappe.PermissionError(
            "Owner first-run setup remains disabled until independent release "
            "acceptance and clean-site installation are approved")
    for doctype in _NO_LIVE_RECORDS:
        if frappe.db.count(doctype):
            raise frappe.ValidationError(
                "First-run setup refuses any site with existing admissions, "
                "students, bills, payments or payroll; preserve this site")
    if frappe.db.get_single_value("TH Backup Control", "enabled") in (1, "1", True):
        raise frappe.ValidationError(
            "First-run setup refuses a site with Backup Control switched On")


def _finance_preconditions():
    if not frappe.db.exists("Item Group", "Fee Component"):
        raise frappe.ValidationError(
            "Native Education Fee Component Item Group is missing; complete "
            "Education installation before initializing the catalog")
    companies = frappe.db.get_all("Company", fields=["name"], limit=2)
    if len(companies) != 1:
        raise frappe.ValidationError(
            "Exactly one approved legal Company must be configured before "
            "initializing draft fee plans")
    company = companies[0].name
    if not frappe.db.get_value("Company", company, "default_receivable_account"):
        raise frappe.ValidationError(
            "Finance must configure the Company's default receivable account "
            "before initializing draft tuition plans")


def preview_digest(snapshot):
    """Bound precondition proof to the exact planned catalog operations."""
    plan = prepare_catalog_plan(snapshot)
    return digest({"preset_id": plan["preset_id"], "actions": plan["actions"],
                   "review": plan["preview"]["counts"]["review"]})


@frappe.whitelist(methods=["POST"])
def initialize_owner_catalog(expected_plan_hash, confirmation):
    """Create only absent, approved native catalog masters and DRAFT fee plans.

    No silent update, no general permission bypass, no site restoration, no
    release activation. An exception fails the entire request's transaction;
    audited native commands never commit individually.
    """
    _owner()
    _qualified_site()
    if confirmation != "APPLY_TO_NEW_COURSE_SITE":
        raise frappe.ValidationError("Explicit first-run setup confirmation is required")
    snapshot = _snapshot()
    plan = prepare_catalog_plan(snapshot)
    if (not isinstance(expected_plan_hash, str)
            or expected_plan_hash != preview_digest(snapshot)):
        raise frappe.ValidationError(
            "Setup changed since it was reviewed; refresh the preview and "
            "confirm the current exact plan before proceeding")
    if not plan["actions"]:
        return {"status": "ALREADY_MATCHED", "created": 0,
                "preset_id": plan["preset_id"], "production_ready": False}

    # Require all accounting prerequisites before creating a single master.
    _finance_preconditions()
    # Existing categories without their native accounting Item are unsafe.
    required_category = load_preset()["fee_policy"]["category"]
    if frappe.db.exists("Fee Category", required_category):
        if not frappe.db.get_value("Fee Category", required_category, "item"):
            raise frappe.ValidationError(
                "Existing tuition Fee Category has no native accounting Item")
    # Run the native Owner configuration commands under one Frappe POST
    # transaction. Request-key receipts make each operation independently
    # idempotent if a network retry follows a successful commit.
    created = []
    year = load_preset()["academic_years"][0]["start"]
    for action in plan["actions"]:
        operation = action["operation"]
        arguments = {key: value for key, value in action.items()
                     if key != "operation"}
        if operation == "create_level":
            arguments["effective_from"] = year
        arguments["request_key"] = action_request_key(plan["preset_id"], action)
        _ALLOWED[operation](**arguments)
        created.append(operation)

    after = preview_catalog(_snapshot())
    if after["counts"]["review"] or after["counts"]["create"]:
        raise frappe.ValidationError(
            "New catalog did not pass exact post-write verification; "
            "the transaction must be rolled back")
    return {"status": "CATALOG_DRAFTS_INITIALIZED",
            "created": len(created), "preset_id": plan["preset_id"],
            "production_ready": False,
            "note": "Academic assessment, staffing, backup and release approval remain separate"}
