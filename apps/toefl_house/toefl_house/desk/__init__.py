"""Role desk projections: safe daily-work reads over the native authorities.

This package is the product layer described in docs/product/ROLE-DESKS.md.

Discipline (binding for every module in this package):

- A desk endpoint is a read. It never writes a document, never mutates
  configuration and never grants authority. Guided actions are prefills for
  EXISTING guarded commands, included only when the viewer already holds the
  acting role.
- Every endpoint gates on its declared desk audience before touching the
  database and fails closed with a human-readable message otherwise.
- Every query selects an explicit, per-desk allow-list of fields
  (PROJECTION_FIELDS) and carries an explicit limit. There is no `*` and no
  unbounded read anywhere in this package.
- Scope is native: company-scoped records are filtered through the viewer's
  User Permission on Company (and Branch where a record carries the field).
  The helper refuses to invent a scope the records do not have.
- Elevated reads exist only through _project_rows / _project_count, which
  require the caller to name the desk audience and are covered by the desk
  test suite.
"""
import frappe

DESK_MODULES = ("reception", "academic", "finance", "operations", "owner", "setup")

DESKS = {
    "th-reception-desk": {
        "title": "TOEFL House Reception Desk",
        "description": "Find any person in the admission funnel and see the stage, what is missing and who acts next.",
        "roles": ["Reception"],
        "module": "Operations",
    },
    "th-academic-desk": {
        "title": "TOEFL House Academic Desk",
        "description": "Placement and admission queues, classes, sessions and teaching assignments that need an academic decision.",
        "roles": ["Academic Manager"],
        "module": "Operations",
    },
    "th-finance-desk": {
        "title": "TOEFL House Finance Desk",
        "description": "Today's collections, outstanding receivables, enrollments awaiting billing, teaching assignments for native payroll, and the correction queue.",
        "roles": ["Finance Manager"],
        "module": "Operations",
    },
    "th-operations-desk": {
        "title": "TOEFL House Operations Desk",
        "description": "Cross-role funnel, exceptions and staffing across the whole operation.",
        "roles": ["General Manager"],
        "module": "Operations",
    },
    "th-owner-cockpit": {
        "title": "TOEFL House Owner Cockpit",
        "description": "Business state with every definition stated, plus the fail-closed release posture.",
        "roles": ["Course Owner"],
        "module": "Operations",
    },
    "th-academic-setup": {
        "title": "TOEFL House Academic Setup",
        "description": "The Owner's configuration surface: programs, ordered levels, effective-dated durations and progression, feeding every other desk and command.",
        "roles": ["Course Owner"],
        "module": "Operations",
    },
}

# Fields each desk may project. This allow-list is the read boundary for the
# elevated projection reads: anything not listed here cannot leave the server
# through a desk, including sensitive internals (answers, hashes, seeds, keys,
# payroll detail, result_json). Tested by tests/desk.
PROJECTION_FIELDS = {
    ("reception", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
        "course_code", "internal_level",
    ],
    ("reception", "TH Placement Attempt"): [
        "name", "case_name", "status",
    ],
    ("reception", "TH Placement Case"): [
        "name", "subject", "status",
    ],
    ("reception", "Student"): [
        "name", "student_name", "student_email_id", "creation",
    ],
    # Cohort truth for the walk-in lookup: the class lifecycle lives on the
    # governed th_class_status custom field (planned/active classes open a
    # cohort; completed/cancelled ones do not). No `active` column exists on
    # the pinned native Student Group (education 93bc70757533).
    ("reception", "Student Group"): [
        "name", "program", "academic_year", "disabled", "th_class_status",
    ],
    ("reception", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    ("reception", "Student Applicant"): [
        # `title` is the pinned native full-name column (education
        # 93bc70757533); Student Applicant has no `applicant_name` column.
        "name", "title", "student_email_id", "program",
        "academic_year", "application_status", "creation",
    ],
    ("reception", "TH Admission Decision"): [
        "name", "student_applicant", "program", "academic_year",
        "placement_decision", "status", "accepted", "native_student",
        "version", "modified",
    ],
    ("academic", "TH Placement Attempt"): [
        "name", "case_name", "ordinal", "status", "version", "mode",
        "deadline_at",
    ],
    ("academic", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
        "course_code", "internal_level",
    ],
    ("academic", "TH Admission Decision"): [
        "name", "student_applicant", "program", "academic_year",
        "status", "accepted", "native_student", "version", "modified",
        "drafted_by",
    ],
    # The class lifecycle fact is the governed th_class_status custom field;
    # the pinned native Student Group (education 93bc70757533) has no
    # `active` column — `disabled` is its native archive flag.
    ("academic", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    ("academic", "Course Schedule"): [
        "name", "student_group", "instructor", "course", "room",
        "from_time", "to_time", "schedule_date",
    ],
    ("academic", "TH Teaching Assignment"): [
        "name", "student_group", "skill", "instructor", "contract",
        "course_schedule", "effective_start", "effective_end",
    ],
    ("academic", "Student Attendance"): [
        "name", "student", "student_group", "course_schedule", "date",
        "status", "docstatus",
    ],
    ("academic", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    ("finance", "Fees"): [
        "name", "student", "student_name", "program", "program_enrollment",
        "academic_year", "posting_date", "due_date", "grand_total",
        "outstanding_amount", "currency", "company", "docstatus",
    ],
    ("finance", "Sales Invoice"): [
        "name", "customer", "customer_name", "th_placement_case",
        "posting_date", "due_date", "grand_total", "outstanding_amount",
        "currency", "company", "status", "is_return", "docstatus",
    ],
    # Payment Entry carries no flat `currency` column on the pinned
    # authority; the paying account's currency is the native fact.
    ("finance", "Payment Entry"): [
        "name", "payment_type", "party_type", "party", "paid_amount",
        "received_amount", "paid_from_account_currency", "company",
        "posting_date", "docstatus",
    ],
    ("finance", "TH Correction Request"): [
        "name", "sales_invoice", "fees", "reason", "requested_amount", "status",
        "approved_by", "credit_note", "modified",
    ],
    ("finance", "TH Correction Policy"): [
        "name", "approver_role", "correction_window_days", "status",
    ],
    ("finance", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    # §18 consumption: the finance desk resolves the Owner's configured fee
    # plan (control plane) into the issuance prefill — one source of truth.
    ("finance", "Fee Structure"): [
        "name", "program", "academic_year", "company", "docstatus",
    ],
    ("finance", "Fee Component"): [
        "name", "parent", "parenttype", "fees_category", "amount", "idx",
    ],
    # D12 visibility: assignment identity and window only. No rate, no
    # payable amount, no Additional Salary — native payroll stays the
    # money authority. A count of rows is a record count, not a payroll figure.
    ("finance", "TH Teaching Assignment"): [
        "name", "student_group", "skill", "instructor", "contract",
        "course_schedule", "effective_start", "effective_end",
    ],
    # Owner cockpit counts enabled Students; the projection carries the key
    # only — no student detail leaves the store through the cockpit.
    ("management", "Student"): [
        "name",
    ],
    ("management", "TH Correction Request"): [
        "name", "sales_invoice", "fees", "reason", "requested_amount", "status",
        "modified",
    ],
    ("management", "TH Admission Decision"): [
        "name", "student_applicant", "program", "status", "version",
        "accepted", "native_student", "modified",
    ],
    ("management", "TH Placement Attempt"): [
        "name", "case_name", "status", "deadline_at",
    ],
    ("management", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
    ],
    ("management", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    ("management", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    # Staffing coverage reads the native role assignment rows and the enabled
    # flag of the native User; nothing else about a user is projected.
    ("management", "Has Role"): [
        "name", "parent", "role", "parenttype",
    ],
    ("management", "User"): [
        "name",
    ],
    # Academic Setup (Course Owner): configuration masters, their effective-
    # dated duration versions, and the enrollment usage counts that guard
    # deactivation. No student detail beyond the enrollment link.
    ("setup", "TH Academic Program"): [
        "name", "code", "title", "status", "modified",
    ],
    ("setup", "TH Program Level"): [
        "name", "family", "code", "title", "sequence", "status",
        "native_program", "next_level", "modified",
    ],
    ("setup", "TH Level Duration"): [
        "name", "parent", "parenttype", "duration_value", "duration_unit",
        "effective_from", "superseded_on", "reason", "set_by",
    ],
    ("setup", "TH Discount Rule"): [
        "name", "code", "title", "discount_percentage", "precedence",
        "status", "fee_category", "program", "description", "modified",
    ],
    ("setup", "Program Enrollment"): [
        "name", "program", "enrollment_date", "docstatus",
    ],
    # Integrity audit: native Program identity/display only, to surface
    # records defined outside the control plane.
    ("setup", "Program"): [
        "name", "program_name",
    ],
    # Fee configuration (control plane slice 2): native fee masters and the
    # editable plans per level. No GL detail beyond the resolved receivable.
    ("setup", "Academic Year"): [
        "name", "year_start_date", "year_end_date",
    ],
    ("setup", "Fee Category"): [
        "name", "category_name", "description", "item",
    ],
    ("setup", "Fee Structure"): [
        "name", "program", "academic_year", "company", "receivable_account",
        "docstatus", "total_amount",
    ],
    ("setup", "Fee Component"): [
        "name", "parent", "parenttype", "fees_category", "amount", "idx",
    ],
}

# Hard upper bounds. A desk section never silently grows with the data.
LIMIT_QUEUES = 25
LIMIT_TODAY = 25
LIMIT_LOOKUP = 10
BOUNCE_WINDOW = 400


def desk_audience(slug):
    return list(DESKS[slug]["roles"])


def require_desk_audience(slug):
    """Gate: the viewer must hold at least one of the desk's roles.

    Desks are separately authorized aggregate views (the sanctioned concept in
    docs/domain/permission-model.md): read-only, minimal-field, role-gated. A
    desk read is therefore gated on the desk audience and on an enabled,
    non-guest, non-administrator user — the same viewer invariants
    toefl_house.security.authorize enforces for commands — but deliberately
    NOT on the synthetic-site activation gate, exactly like the governance
    surface in toefl_house.administration. The synthetic-only hard stop in
    security.py remains untouched and continues to confine every business
    command; a desk cannot mutate anything and adds no path around it.
    """
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if user in (None, "Guest", "Administrator") or not roles.intersection(DESKS[slug]["roles"]):
        frappe.throw(
            f"The {DESKS[slug]['title']} is limited to the "
            f"{DESKS[slug]['roles'][0]} role. Ask a Course Owner or General "
            "Manager to review your role assignment if you expected access.",
            frappe.PermissionError,
        )
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw("This account has been disabled.", frappe.PermissionError)
    return user


def viewer_roles():
    return set(frappe.get_roles(frappe.session.user))


def scope_filters(desk):
    """Native scope: the viewer's User Permission on Company/Branch, applied
    only to fields the projected doctypes really carry. Returns a dict of
    {fieldname: allowed_values} that callers merge into their filters."""
    scopes = {}
    for allow, fieldname in (("Company", "company"), ("Branch", "branch")):
        allowed = frappe.get_all(
            "User Permission",
            filters={"user": frappe.session.user, "allow": allow},
            pluck="for_value",
            limit_page_length=100,
        )
        if allowed:
            scopes[fieldname] = allowed
    return scopes


def _apply_scope(desk, doctype, filters):
    for fieldname, allowed in scope_filters(desk).items():
        meta_field = fieldname if frappe.get_meta(doctype).has_field(fieldname) else None
        if meta_field and meta_field not in filters:
            filters[meta_field] = ("in", allowed)
    return filters


def _assert_projection(desk, doctype, fields):
    allow = PROJECTION_FIELDS.get((desk, doctype))
    if not allow:
        raise frappe.ValidationError(f"No projection allow-list for {desk}/{doctype}")
    if [field for field in fields if field not in allow]:
        raise frappe.ValidationError(f"Fields outside the {desk}/{doctype} projection allow-list")
    return allow


def project_rows(desk, doctype, fields, filters=None, order_by=None, limit=LIMIT_QUEUES):
    """Elevated, allow-listed, bounded read for a desk projection.

    This is the only sanctioned way for a desk to read records its audience
    does not hold natively. It enforces the field allow-list and the limit
    before touching the database, so a caller cannot widen the projection.
    """
    _assert_projection(desk, doctype, fields)
    filters = _apply_scope(desk, doctype, dict(filters or {}))
    return frappe.get_all(
        doctype,
        filters=filters,
        fields=list(fields),
        order_by=order_by or "modified desc",
        limit_page_length=int(limit),
    )


def project_count(desk, doctype, filters=None):
    _assert_projection(desk, doctype, ["name"])
    filters = _apply_scope(desk, doctype, dict(filters or {}))
    return frappe.db.count(doctype, filters)


def section(sid, title, kind, *, items=None, facts=None, empty_title="", empty_body="", notes=None):
    """A desk section envelope. The client renders these uniformly."""
    payload = {"id": sid, "title": title, "kind": kind}
    if facts is not None:
        payload["facts"] = facts
    if items is not None:
        payload["items"] = items
    payload["empty"] = {"title": empty_title, "body": empty_body}
    if notes:
        payload["notes"] = notes
    return payload


def guided_action(role, endpoint, label, args):
    """Prefill for an existing guarded command, included only when the viewer
    holds the acting role. The server decides; the client only renders."""
    if role in viewer_roles():
        return {"role": role, "endpoint": endpoint, "label": label, "args": args}
    return None


# The class lifecycle is the governed th_class_status fact (planned → active
# → completed/cancelled, maintained by toefl_house.teaching.transition_class
# alone). A cohort is OPEN while a class is planned or active and not
# archived; completed and cancelled classes never satisfy the cohort
# requirement again. These sets are reads of that single authority — no
# parallel status is invented or maintained here.
COHORT_OPEN_STATUSES = ("Planned", "Active")
COHORT_ACTIVE_STATUSES = ("Active",)


def cohort_state(group_row):
    """Lifecycle state of one Student Group row from its governed facts."""
    if int(group_row.get("disabled") or 0):
        return "Archived"
    return group_row.get("th_class_status") or "Planned"


def open_cohort_keys(group_rows):
    """(program, academic_year) pairs whose class is planned or active."""
    return {(row.get("program"), row.get("academic_year"))
            for row in group_rows
            if cohort_state(row) in COHORT_OPEN_STATUSES}


def active_cohort_rows(group_rows):
    return [row for row in group_rows if cohort_state(row) in COHORT_ACTIVE_STATUSES]


# Fee-plan readiness is ONE rule everywhere: the guided billing text (finance
# desk), the Owner's configuration health (setup desk) and the issuance
# command must never disagree about what "configured" means. issue_tuition_fees
# consumes a structure by name and checks program/year match and components
# (U9): the desk rule mirrors exactly that, over cancelled-free plans. Editing
# stays a Draft-only act (toefl_house.academic manages Draft structures), so
# the setup desk offers edit buttons only where they can succeed.
def issuable_plans(plans_by_key, program, academic_year):
    """Plans for (program, year) that the issuance command would accept,
    split into those with components and empty drafts awaiting completion."""
    candidates = [plan for plan in plans_by_key.get((program, academic_year or ""), [])
                  if int(plan.get("docstatus") or 0) != 2]
    return candidates


def plan_with_components(candidates, rows_by_plan):
    return [plan for plan in candidates if rows_by_plan.get(plan["name"])]


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def available():
    """Registry read: which desks the SERVER believes this viewer may open.

    The client never guesses roles from its own session data; every desk and
    the command-centre landing page render their links from this answer.
    Guests get an explicit empty answer rather than an error, so a shared
    machine never sees a stack trace on the landing page.
    """
    user = frappe.session.user
    if user in (None, "Guest", "Administrator"):
        return {"desks": []}
    if not frappe.db.get_value("User", user, "enabled"):
        return {"desks": []}
    held = viewer_roles()
    return {"desks": [
        {"slug": slug, "title": spec["title"], "description": spec["description"]}
        for slug, spec in DESKS.items()
        if set(spec["roles"]) & held
    ]}
