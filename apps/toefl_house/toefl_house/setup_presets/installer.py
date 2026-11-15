"""Release-gated, Owner-authorized, atomic academic first-run setup.

Only the explicitly qualified customer path or a separately authorized
internal installation may initialize the catalog on an empty site. The
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
_NO_LIVE_RECORDS = (
    "Student", "Student Applicant", "Program Enrollment",
    "Student Group", "Course Schedule", "Student Attendance",
    "TH Placement Attempt", "TH Assessment Book", "TH Academic Result",
    "Fees", "Payment Entry", "Sales Invoice", "Salary Slip", "Payroll Entry",
    "TH Tuition Refund Request",
)


def _qualified_site():
    internal_site = frappe.conf.get("toefl_house_internal_catalog_site")
    internal_approved = False
    if isinstance(internal_site, str) and internal_site:
        from toefl_house.security import is_production
        internal_approved = internal_site == frappe.local.site and is_production()
    customer_approved = (
        frappe.conf.get("toefl_house_customer_release_approved") is True
        and frappe.conf.get("toefl_house_owner_catalog_install_enabled") is True
    )
    if not (internal_approved or customer_approved):
        raise frappe.PermissionError(
            "Complete the authorized activation for this installation "
            "before initializing the first-run catalog")
    for doctype in _NO_LIVE_RECORDS:
        if frappe.db.count(doctype):
            raise frappe.ValidationError(
                "First-run setup refuses any site with existing admissions, "
                "students, bills, payments or payroll; preserve this site")
    backup_on = frappe.db.get_single_value("TH Backup Control", "enabled") in (1, "1", True)
    if internal_approved and not backup_on:
        raise frappe.ValidationError(
            "Keep the approved Backup Control switched On for internal setup")
    if not internal_approved and backup_on:
        raise frappe.ValidationError(
            "Customer first-run setup refuses a site with Backup Control switched On")


def _finance_preconditions(*, lock=False):
    """Read the one native accounting target shown to the approving Owner."""
    if frappe.db.get_value("Item Group", "Fee Component", "is_group") not in (1, "1", True):
        raise frappe.ValidationError(
            "Native Education Fee Component must be an Item Group with "
            "Is Group checked. Ask the installation administrator to review it")
    companies = frappe.db.get_all("Company", fields=["name"], limit_page_length=2)
    if len(companies) != 1:
        raise frappe.ValidationError(
            "Exactly one approved legal Company must be configured before "
            "initializing draft fee plans")
    company = companies[0].name
    defaults = frappe.db.get_value(
        "Company", company, ["default_currency", "default_receivable_account",
                             "default_income_account", "cost_center"],
        as_dict=True, for_update=lock)
    if not defaults or defaults.default_currency != "AFN":
        raise frappe.ValidationError(
            "The approved TOEFL House Company must use AFN as its accounting "
            "currency before any tuition plan is initialized")
    receivable = defaults.default_receivable_account
    income = defaults.default_income_account
    cost_center = defaults.cost_center
    for label, name, root in (
            ("receivable", receivable, "Asset"), ("income", income, "Income")):
        account = frappe.db.get_value(
            "Account", name,
            ["company", "root_type", "account_type", "account_currency", "is_group", "disabled"],
            as_dict=True, for_update=lock) if name else None
        if (not account or account.company != company or account.root_type != root
                or (label == "receivable" and account.account_type != "Receivable")
                or account.account_currency not in (None, "", "AFN")
                or account.is_group not in (0, "0", False)
                or account.disabled not in (0, "0", False)):
            raise frappe.ValidationError(
                f"Finance must set an enabled same-Company AFN {label} ledger "
                "in the native Company defaults")
    center = frappe.db.get_value(
        "Cost Center", cost_center, ["company", "is_group", "disabled"],
        as_dict=True, for_update=lock) if cost_center else None
    if (not center or center.company != company
            or center.is_group not in (0, "0", False)
            or center.disabled not in (0, "0", False)):
        raise frappe.ValidationError(
            "Finance must set an enabled same-Company leaf cost center "
            "in the native Company defaults")
    return {"company": company, "receivable_account": receivable,
            "income_account": income, "cost_center": cost_center, "currency": "AFN"}


def preview_digest(plan, finance):
    """Bind Owner confirmation to planned operations and the native ledger identity."""
    return digest({"preset_id": plan["preset_id"], "actions": plan["actions"],
                   "review": plan["preview"]["counts"]["review"], "finance": finance})


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
    # Serialize two simultaneous first-run POSTs on one existing native row.
    # Without a lock, both callers can preview the same missing catalog and
    # independently attempt to create duplicate programs/fee structures.
    # Rechecking AFTER acquiring the lock observes any committed first run.
    frappe.db.get_value("DocType", "TH Academic Program", "name", for_update=True)
    _qualified_site()
    snapshot = _snapshot()
    plan = prepare_catalog_plan(snapshot)
    finance = _finance_preconditions(lock=True)
    if (not isinstance(expected_plan_hash, str)
            or expected_plan_hash != preview_digest(plan, finance)):
        raise frappe.ValidationError(
            "Setup changed since it was reviewed; refresh the preview and "
            "confirm the current exact plan before proceeding")
    if not plan["actions"]:
        return {"status": "ALREADY_MATCHED", "created": 0,
                "preset_id": plan["preset_id"], "production_ready": False}

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
        if operation == "set_level_fee_component":
            arguments["company"] = finance["company"]
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
