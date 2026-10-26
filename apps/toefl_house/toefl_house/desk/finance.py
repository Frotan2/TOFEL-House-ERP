"""Finance Manager desk: today's money facts and the receivable work list.

Read-only over the native money authorities (Fees, Sales Invoice, Payment
Entry) plus the owned correction queue. Native ERPNext stays the only money
authority: this projection computes no ledger, no balance and no policy. The
charged / paid / outstanding distinction is the native numbers themselves, and
refund/cancel states come only from native docstatus and Sales Invoice status.
Sections are specified in docs/ROLE-DESKS.md.
"""
import frappe
from frappe.utils import today

from toefl_house.configuration import rules as foundation
from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    LIMIT_TODAY,
    guided_action,
    issuable_plans,
    plan_with_components,
    project_count,
    project_rows,
    require_desk_audience,
    scope_filters,
    section,
)

from toefl_house.finance import cashier as cashier_money
from toefl_house.finance import taxes as tax_configuration
from toefl_house.finance import shamsi as solar_calendar

SLUG = "th-finance-desk"

FEES = "Fees"
INVOICE = "Sales Invoice"
PAYMENT = "Payment Entry"
CORRECTION = "TH Correction Request"
POLICY = "TH Correction Policy"
ENROLLMENT = "Program Enrollment"
FEE_STRUCTURE = "Fee Structure"
FEE_ROW = "Fee Component"
ASSIGNMENT = "TH Teaching Assignment"
PLAN_FIELDS = ["name", "program", "academic_year", "company", "docstatus"]
POLICY_FIELDS = ["name", "approver_role", "correction_window_days",
                 "effective_from", "reason", "set_by", "set_on",
                 "superseded_on", "status", "synthetic"]
AUDIT = "TH Placement Audit Event"
POLICY_STREAM = "TH Correction Policy"
VALIDATE_ACTION = "validate_correction_policy"
CONFIGURE_ENDPOINT = "toefl_house.finance.corrections.configure_correction_policy"
VALIDATE_ENDPOINT = "toefl_house.finance.corrections.validate_correction_policy"
STATUS_ENDPOINT = "toefl_house.finance.corrections.set_correction_policy_status"
ASSIGNMENT_FIELDS = ["name", "student_group", "skill", "instructor", "contract",
                     "course_schedule", "effective_start", "effective_end"]
CONTRACT = "TH Instructor Contract"
INSTRUCTOR = "Instructor"
# Identity and window only: no rate, term or amount leaves the desk
# (D12 read containment — the same rule as the assignments section).
CONTRACT_FIELDS = ["name", "instructor", "employee", "compensation_model",
                   "effective_start", "effective_end"]
INSTRUCTOR_FIELDS = ["name", "instructor_name", "employee", "status"]
CREATE_CONTRACT_ENDPOINT = ("toefl_house.teaching.compensation."
                            "create_teaching_contract")
REVISE_CONTRACT_ENDPOINT = ("toefl_house.teaching.compensation."
                            "revise_teaching_contract")
CALCULATE_COMPENSATION_ENDPOINT = ("toefl_house.teaching.compensation."
                                   "calculate_teaching_compensation")
CONTRACT_STAGE_DEFINITION = ("One instructor's active compensation terms; "
                             "a revision supersedes, never rewrites.")
PLAN_ROW_FIELDS = ["name", "parent", "parenttype", "fees_category", "amount", "idx"]
CASHIER_DAY = "TH Cashier Day"
CASHIER_DAY_FIELDS = ["name", "date", "company", "cashier", "total_expected",
                      "total_counted", "total_variance", "reconciled_on",
                      "docstatus"]
RECONCILE_ENDPOINT = "toefl_house.finance.cashier.reconcile_cashier_day"
PLAN_ENDPOINT = "toefl_house.finance.installments.issue_tuition_installment_plan"


def _money_state(row):
    """Fact rows for money documents. Never a projection-local enum."""
    if row.get("docstatus") == 2:
        return "Cancelled"
    outstanding = float(row.get("outstanding_amount") or 0)
    if outstanding <= 0:
        return "Settled"
    if row.get("status") in ("Overdue",) or (
            row.get("due_date") and str(row["due_date"]) < today() and row.get("docstatus") == 1):
        return "Overdue"
    return "Outstanding"


def _invoice_display_state(row):
    """Native Sales Invoice status wins; the fact layer only adds docstatus."""
    if row.get("docstatus") == 2:
        return "Cancelled"
    status = row.get("status") or ""
    if status:
        return status
    return _money_state(row)


def _correction_items(rows, policies=()):
    roles_by_policy = {row.get("name"): row.get("approver_role")
                       for row in (policies or [])}
    fallback_role = None
    fallback_known = False
    items = []
    for row in rows:
        pending = row["status"] == "Requested"
        is_fees = bool(row.get("fees"))
        target = row.get("fees") or row.get("sales_invoice") or ""
        # Each request carries the approver role of the version it pinned;
        # rows that predate versioned policy fall back to the active one.
        approver_role = roles_by_policy.get(row.get("correction_policy") or "")
        if not approver_role and not fallback_known:
            fallback_role = _active_policy_role()
            fallback_known = True
        if not approver_role:
            approver_role = fallback_role
        item = {
            "id": row["name"],
            "person": target,
            "detail": row.get("reason") or "",
            "status": row["status"],
            "stage": "Correction " + str(row["status"] or "").lower(),
            "stage_definition": "Fees correction request." if is_fees else "Invoice correction request from the correction framework.",
            "next": "Approve or deny the request." if pending else "No action; the request is decided.",
            "next_role": (approver_role or "Finance Officer") if pending else None,
            "waiting_since": row.get("modified"),
        }
        if pending and approver_role:
            endpoint = ("toefl_house.finance.corrections.approve_fees_correction"
                        if is_fees else "toefl_house.finance.corrections.approve_invoice_correction")
            item["action"] = guided_action(approver_role, endpoint,
                                           "Approve correction", {"request": row["name"]})
        elif pending:
            # No active policy: the command would deny every approval. Say so
            # instead of showing a button that can only fail.
            item["next"] = "No active correction policy is configured, so this request cannot be approved. A Finance Officer must configure the policy first."
            item["next_role"] = "Finance Officer"
        items.append(item)
    return items


def _active_policy_role():
    rows = project_rows("finance", POLICY,
                        ["name", "approver_role", "correction_window_days", "status"],
                        filters={"status": "Active"}, order_by="modified desc", limit=1)
    return rows[0]["approver_role"] if rows else None


def _current_validation(snapshot):
    """Whether a validation event commits to this exact version snapshot.

    Matched by count, never projected: the hash stays in the filter, so no
    hash field ever enters a desk projection (read-boundary discipline).
    """
    return project_count("finance", AUDIT, filters={
        "target": POLICY_STREAM, "action": VALIDATE_ACTION,
        "after_hash": snapshot,
    }) > 0


def _policy_sections(policies, day):
    """Correction-policy configuration: readiness facts + version queue.

    Readiness is COMPUTED from the version rows on every load - never
    stored, never toggled. Each version item states its own terms and
    state; the latest item carries the single next recommended action.
    """
    try:
        rows = [dict(row) for row in (policies or [])]
        snapshot = foundation.snapshot_digest(rows)
        evidence = ([{"after_hash": snapshot}]
                    if rows and _current_validation(snapshot)
                    else [])
        latest = foundation.latest_version(rows)
        status = latest.get("status") if latest else "Active"
        readiness = foundation.compute_readiness(
            status=status, versions=rows, validations=evidence,
            today=day, what="correction policy")
        fault = ""
    except ValueError as exc:
        # Ambiguous history is an integrity fault: surfaced, never
        # hidden, and never rendered as a readiness state.
        rows, readiness, fault = [], "", str(exc)
    if fault:
        facts = [{
            "label": "Policy readiness",
            "definition": "The version history contradicts itself, so no "
                          "readiness state can be computed.",
            "value": "Integrity fault", "owner": "Finance Officer",
        }]
        items = [{
            "id": "fault",
            "person": "Configuration integrity fault",
            "detail": fault,
            "status": "Integrity fault",
            "stage": "Correction policy",
            "stage_definition": ("The version history contradicts itself, "
                                 "so no readiness state can be computed."),
            "next": ("Ask the administrator to repair the version history; "
                     "new requests fail closed until then."),
            "next_role": "Finance Officer",
            "waiting_since": None,
        }]
        return facts, items
    governing = foundation.resolve_governing(rows, day) if rows else None
    facts = [{
        "label": "Policy readiness",
        "definition": ("Computed configuration readiness of the correction "
                       "policy versions. Production readiness is separate "
                       "and is never decided here."),
        "value": readiness.capitalize(), "owner": "Finance Officer",
    }]
    if governing:
        facts.append({
            "label": "Governing version",
            "definition": ("The policy version governing new correction "
                           "requests."),
            "value": (f"Effective {governing.get('effective_from')}; "
                      f"approver {governing.get('approver_role')}; "
                      f"window {governing.get('correction_window_days')} days"),
            "owner": "Finance Officer",
        })
    elif rows:
        facts.append({
            "label": "Governing version",
            "definition": ("The policy version governing new correction "
                           "requests."),
            "value": ("Nothing effective yet; the latest version is "
                      "scheduled for the future"),
            "owner": "Finance Officer",
        })
    else:
        facts.append({
            "label": "Governing version",
            "definition": ("The policy version governing new correction "
                           "requests."),
            "value": "No versions recorded yet",
            "owner": "Finance Officer",
        })
    ordered = foundation.normalize_versions(rows)
    latest_name = latest.get("name") if latest else None
    items = []
    for row in ordered:
        state = foundation.version_state(row, day)
        detail = (f"Approver {row.get('approver_role')}; window "
                  f"{row.get('correction_window_days')} days; {state}")
        is_latest = row.get("name") == latest_name
        if is_latest:
            detail += f"; policy readiness {readiness}"
            next_text, action = _latest_policy_next(
                row, readiness, ordered, day)
        elif state == "scheduled":
            next_text, action = (
                f"Takes effect {row.get('effective_from')}.", None)
        else:
            next_text, action = (
                "No action; superseded by a newer version.", None)
        item = {
            "id": row.get("name"),
            "person": f"Effective {row.get('effective_from')}",
            "detail": detail,
            "status": (row.get("status") or state).capitalize()
            if is_latest else state.capitalize(),
            "stage": "Correction policy",
            "stage_definition": ("One effective-dated correction policy "
                                 "version. Older versions are closed, never "
                                 "rewritten."),
            "next": next_text,
            "next_role": "Finance Officer",
            "waiting_since": row.get("set_on"),
        }
        if action:
            item["action"] = action
        items.append(item)
    return facts, items


def _latest_policy_next(row, readiness, ordered, day):
    """The single next recommended step for the latest version."""
    if readiness == "retired":
        return ("The policy is retired and governs nothing; reactivate it "
                "to allow new requests.",
                guided_action(
                    "Finance Officer", STATUS_ENDPOINT,
                    "Reactivate policy", {"status": "Active"}))
    if readiness == "configured":
        return ("Versions exist but no validation covers the current set; "
                "validate the policy.",
                guided_action(
                    "Finance Officer", VALIDATE_ENDPOINT,
                    "Validate policy", {}))
    if readiness == "validated":
        first = str(row.get("effective_from") or "")
        return (f"The policy is validated and takes effect {first}.",
                guided_action(
                    "Finance Officer", CONFIGURE_ENDPOINT,
                    "Record new version", {}))
    if readiness == "effective":
        governing = foundation.resolve_governing(ordered, day)
        since = (governing.get("effective_from")
                 if governing else row.get("effective_from"))
        return (f"The policy governs since {since}. Record a new version "
                "to change future terms.",
                guided_action(
                    "Finance Officer", CONFIGURE_ENDPOINT,
                    "Record new version", {}))
    return ("Record the first version; the policy governs nothing until "
            "then.",
            guided_action(
                "Finance Officer", CONFIGURE_ENDPOINT,
                "Record new version", {}))


def _compensation_items(contracts, instructors):
    """The compensation readiness queue (P1-6 operational readiness).

    The three guarded compensation commands are Finance Officer commands, but
    a viewer without the acting role must still be able to SEE what is
    waiting and who acts next. This section projects the readiness facts and
    — only when the viewer also holds the acting role — embeds the guided
    action (server decides, client renders):

    - one row per ACTIVE teaching contract (identity + window only), offering
      the revise command;
    - one row per active instructor who has a payroll employee but no active
      contract, offering the create command (the employee is prefilled from
      the native Instructor.employee link so the dialog opens ready);
    - one row per active instructor with NO payroll employee link, failing
      closed (a contract cannot be recorded until the HR record is complete);
    - a recurring payroll-period row offering the calculation command, present
      while at least one active contract exists.

    No rate, term, amount or statutory figure is projected — the desk never
    calculates pay (D12); it only points at the guarded command that does.
    """
    display = {row["name"]: (row.get("instructor_name") or row["name"])
               for row in instructors}
    contracted = {row.get("instructor") for row in contracts}
    items = []
    for row in contracts:
        window = "from " + str(row.get("effective_start"))
        if row.get("effective_end"):
            window += " to " + str(row.get("effective_end"))
        item = {
            "id": row["name"],
            "person": display.get(row.get("instructor")) or row.get("instructor") or "",
            "detail": "{}; effective {}".format(
                row.get("compensation_model") or "Teaching contract", window),
            "status": "Active contract",
            "stage": "Teaching contract",
            "stage_definition": CONTRACT_STAGE_DEFINITION,
            "next": "Revise the contract when the terms change; the revision "
                    "supersedes and never rewrites.",
            "next_role": "Finance Officer",
            "waiting_since": row.get("effective_start"),
        }
        action = guided_action("Finance Officer", REVISE_CONTRACT_ENDPOINT,
                               "Revise teaching contract", {"contract": row["name"]})
        if action:
            item["action"] = action
        items.append(item)
    for row in instructors:
        if row.get("employee") and row["name"] not in contracted:
            item = {
                "id": row["name"],
                "person": display.get(row["name"]),
                "detail": "Payroll employee " + str(row.get("employee")),
                "status": "No active contract",
                "stage": "Teaching contract",
                "stage_definition": CONTRACT_STAGE_DEFINITION,
                "next": "Record the teaching contract before this instructor's "
                        "work is compensated.",
                "next_role": "Finance Officer",
                "waiting_since": None,
            }
            action = guided_action(
                "Finance Officer", CREATE_CONTRACT_ENDPOINT,
                "Record teaching contract",
                {"instructor": row["name"], "employee": row.get("employee")})
            if action:
                item["action"] = action
            items.append(item)
        elif not row.get("employee"):
            items.append({
                "id": row["name"],
                "person": display.get(row["name"]),
                "detail": "No payroll employee linked",
                "status": "No payroll record",
                "stage": "Teaching contract",
                "stage_definition": CONTRACT_STAGE_DEFINITION,
                "next": "Link the payroll employee on this instructor's HR "
                        "record first; a contract needs it to pay the right "
                        "person.",
                "next_role": "Course Owner",
                "waiting_since": None,
            })
    if contracts:
        items.append({
            "id": "payroll-period",
            "person": "Payroll period",
            "detail": "Calculate auditable native Additional Salary drafts for eligible "
                      "teaching facts. These are not submitted wages or payments.",
            "status": "Periodic",
            "stage": "Compensation period",
            "stage_definition": ("Calculation prepares native Additional Salary drafts. "
                                 "Authorized payroll staff must review and submit "
                                 "them before HRMS Salary Slip; fixed-salary "
                                 "instructors stay on native Salary Structure."),
            "next": "Calculate when the period closes. Authorized payroll staff must "
                    "review and submit the Additional Salary drafts, then process "
                    "Salary Slip under normal HRMS approvals.",
            "next_role": "Finance Officer",
            "waiting_since": None,
        })
        action = guided_action(
            "Finance Officer", CALCULATE_COMPENSATION_ENDPOINT,
            "Calculate compensation",
            {"period_start": "", "period_end": "", "company": "",
             "salary_component": "", "deduction_component": ""})
        if action:
            items[-1]["action"] = action
    return items


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Finance desk payload: today, outstanding, awaiting billing, corrections."""
    require_desk_audience(SLUG)
    day = today()

    payments = project_rows("finance", PAYMENT,
                            ["name", "payment_type", "party_type", "party", "paid_amount",
                             "received_amount", "paid_from_account_currency", "company",
                             "posting_date", "docstatus"],
                            filters={"docstatus": 1, "payment_type": "Receive",
                                     "posting_date": day},
                            order_by="posting_date desc, name desc", limit=LIMIT_TODAY)
    invoices_today = project_rows("finance", INVOICE,
                                  ["name", "customer", "customer_name", "th_placement_case",
                                   "posting_date", "due_date", "grand_total", "outstanding_amount",
                                   "currency", "company", "status", "is_return", "docstatus"],
                                  filters={"docstatus": 1, "posting_date": day},
                                  order_by="posting_date desc, name desc", limit=LIMIT_TODAY)
    fees_today = project_rows("finance", FEES,
                              ["name", "student", "student_name", "program",
                               "program_enrollment", "academic_year", "posting_date",
                               "due_date", "grand_total", "outstanding_amount", "currency",
                               "company", "docstatus"],
                              filters={"docstatus": 1, "posting_date": day},
                              order_by="posting_date desc, name desc", limit=LIMIT_TODAY)

    outstanding_invoices = project_rows("finance", INVOICE,
                                        ["name", "customer", "customer_name", "th_placement_case",
                                         "posting_date", "due_date", "grand_total",
                                         "outstanding_amount", "currency", "company", "status",
                                         "is_return", "docstatus"],
                                        filters={"docstatus": 1,
                                                 "outstanding_amount": (">", 0)},
                                        order_by="due_date asc, name asc", limit=LIMIT_QUEUES)
    outstanding_fees = project_rows("finance", FEES,
                                    ["name", "student", "student_name", "program",
                                     "program_enrollment", "academic_year", "posting_date",
                                     "due_date", "grand_total", "outstanding_amount", "currency",
                                     "company", "docstatus"],
                                    filters={"docstatus": 1,
                                             "outstanding_amount": (">", 0)},
                                    order_by="due_date asc, name asc", limit=LIMIT_QUEUES)

    corrections = project_rows("finance", CORRECTION,
                               ["name", "sales_invoice", "fees", "correction_policy",
                                "reason", "requested_amount",
                                "status", "approved_by", "credit_note", "modified"],
                               filters={"status": ("in", ["Requested", "Approved", "Denied", "Posted"])},
                               order_by="modified desc", limit=LIMIT_QUEUES)

    policies = project_rows("finance", POLICY, POLICY_FIELDS,
                            order_by="effective_from asc", limit=LIMIT_QUEUES)
    policy_facts, version_items = _policy_sections(policies, day)

    # Awaiting billing: submitted enrollments with no Fees row referencing them.
    enrollments = project_rows("finance", ENROLLMENT,
                               ["name", "student", "student_name", "program", "academic_year",
                                "enrollment_date", "docstatus"],
                               filters={"docstatus": 1},
                               order_by="enrollment_date asc", limit=BOUNCE_WINDOW)
    billed = set()
    if enrollments:
        billed_names = [row["name"] for row in enrollments]
        for row in project_rows("finance", FEES, ["name", "program_enrollment"],
                                filters={"program_enrollment": ("in", billed_names), "docstatus": ("!=", 2)},
                                order_by="name asc", limit=BOUNCE_WINDOW):
            if row.get("program_enrollment"):
                billed.add(row["program_enrollment"])
    awaiting_billing = [row for row in enrollments if row["name"] not in billed]

    assignments = project_rows("finance", ASSIGNMENT, ASSIGNMENT_FIELDS,
                               order_by="effective_start asc", limit=LIMIT_QUEUES)
    contracts = project_rows("finance", CONTRACT, CONTRACT_FIELDS,
                             filters={"status": "Active"},
                             order_by="effective_start desc, name desc",
                             limit=LIMIT_QUEUES)
    instructors = project_rows("finance", INSTRUCTOR, INSTRUCTOR_FIELDS,
                               filters={"status": "Active"},
                               order_by="name asc", limit=LIMIT_QUEUES)

    # Owner installment terms for the billing prefill (read once per load).
    from toefl_house.finance import policies as billing_policy
    installment_terms = billing_policy.governing_billing_terms()

    if (installment_terms.get("installment_cadence") == "Solar Hijri Month"
            and int(installment_terms.get("installments_allowed") or 0)):
        grace = int(installment_terms.get("payment_grace_days") or 0)
        first_solar_due = solar_calendar.monthly_due_dates(
            solar_calendar.month_key(day), 1, grace)[0].isoformat()
        installment_message = (
            f"Solar Hijri monthly, first of each month + {grace} grace days; "
            f"up to {int(installment_terms.get('max_installments') or 0)} charges")
    else:
        first_solar_due = None
        installment_message = (
            f"Allowed, up to {int(installment_terms.get('max_installments') or 0)}"
            f" every {int(installment_terms.get('installment_interval_days') or 0)} days"
            if installment_terms and int(installment_terms.get("installments_allowed") or 0)
            else "Not enabled")

    money_facts = [
        {"label": "Collected today",
         "definition": "Money received today from posted payment records, summed per receiving currency.",
         "value": _summarize(payments, "paid_amount",
                              currency_key="paid_from_account_currency"),
         "owner": None},
        {"label": "Invoiced today",
         "definition": "Amounts billed today across invoices and tuition fees, summed per currency.",
         "value": _summarize(invoices_today + fees_today, "grand_total"),
         "owner": None},
        {"label": "Outstanding invoices",
         "definition": "Invoices posted and still owing money.",
         "value": len(outstanding_invoices), "owner": "Finance Officer"},
        {"label": "Outstanding tuition fees",
         "definition": "Issued tuition fees still owing money.",
         "value": len(outstanding_fees), "owner": "Finance Officer"},
        {"label": "Corrections pending",
         "definition": "Correction requests (invoice or tuition fee) in Requested status.",
         "value": sum(1 for row in corrections if row["status"] == "Requested"),
         "owner": "Finance Officer"},
        {"label": "Enrollments awaiting billing",
         "definition": "Confirmed enrollments that no issued bill covers; cancelled bills do not count.",
         "value": len(awaiting_billing), "owner": "Finance Officer"},
        {"label": "Installments",
         "definition": ("The governing billing policy's installment terms. The "
                        "Course Owner decides whether a configured price may be "
                        "split and how far apart the due dates fall."),
         "value": installment_message,
         "owner": "Course Owner"},
        {"label": "Teaching assignments on file",
         "definition": "Instructor skill assignments. Pay is native payroll, one-off per assignment; this desk does not calculate pay.",
         "value": len(assignments), "owner": "Finance Officer"},
    ]

    def money_item(row, kind):
        state = _invoice_display_state(row) if kind == "Sales Invoice" else _money_state(row)
        # An ISO due date is preserved as the native bookkeeping date;
        # the Afghan Solar Hijri month is a read-only human label, never
        # an alternative mutable invoice date or a second receivable.
        due_iso = str(row.get("due_date") or "")
        try:
            due_label = solar_calendar.solar_month_label(
                solar_calendar.month_key(due_iso)) if due_iso else ""
        except ValueError:
            due_label = ""
        return {
            "id": row["name"],
            "person": row.get("customer_name") or row.get("customer")
            or row.get("student_name") or row.get("student") or "",
            "detail": row.get("program") or row.get("th_placement_case") or "",
            "status": state,
            # U5: staff read "Invoice"/"Tuition fee", not the doctype name.
            "stage": {"Sales Invoice": "Invoice", "Fees": "Tuition fee"}.get(kind, kind),
            "stage_definition": (
                "Charged {grand} {currency}; outstanding {outstanding} {currency}. "
                "Solar Hijri due month: {period}. "
                "Amounts are read straight from the posted document; this is "
                "a CURRENT balance, not a historical month-end GL report.").format(
                    grand=row.get("grand_total") or 0, currency=row.get("currency") or "",
                    outstanding=row.get("outstanding_amount") or 0,
                    period=due_label or "Not recorded"),
            "next": ("Record the payment against this document in the finance workspace. "
                     "This desk does not collect money itself.")
            if state in ("Outstanding", "Overdue", "Unpaid")
            else "No action.",
            "next_role": "Finance Officer" if state in ("Outstanding", "Overdue", "Unpaid") else None,
            "waiting_since": row.get("due_date") or row.get("posting_date"),
            "amount": row.get("grand_total") or 0,
            "currency": row.get("currency") or "",
        }

    payment_items = [{
        "id": row["name"],
        "person": row.get("party") or "",
        "detail": row.get("company") or "",
        "status": "Received",
        "stage": "Payment today",
        "stage_definition": "A payment received, posted today.",
        "next": "No action.",
        "next_role": None,
        "waiting_since": row.get("posting_date"),
        "amount": row.get("paid_amount") or row.get("received_amount") or 0,
        "currency": row.get("paid_from_account_currency") or "",
    } for row in payments]

    # §18: resolve the Owner's configured fee plan (Academic Control Plane)
    # into the billing prefill. One source of truth: the plan is the native
    # Fee Structure for (program, academic year); the Officer never types a
    # structure name, and a missing/incomplete plan names its owner.
    plans = project_rows("finance", FEE_STRUCTURE, PLAN_FIELDS,
                         order_by="name asc", limit=LIMIT_QUEUES)
    plan_rows = project_rows("finance", FEE_ROW, PLAN_ROW_FIELDS,
                             filters={"parenttype": FEE_STRUCTURE},
                             order_by="idx asc", limit=LIMIT_QUEUES * 4)
    rows_by_plan = {}
    for plan_row in plan_rows:
        rows_by_plan.setdefault(plan_row.get("parent"), []).append(plan_row)
    plans_by_key = {}
    for plan in plans:
        plans_by_key.setdefault(
            (plan.get("program"), plan.get("academic_year") or ""), []).append(plan)

    def installment_next(plan, row):
        """The installment-plan action, or None when the owner has not enabled it.

        The schedule length and interval are the owner's policy terms: the
        prefill offers a split only inside them, and the command re-judges
        every term on the server anyway.
        """
        if not installment_terms or not int(installment_terms.get("installments_allowed") or 0):
            return None
        maximum = int(installment_terms.get("max_installments") or 1)
        if maximum < 2:
            return None
        return guided_action(
            "Finance Officer", PLAN_ENDPOINT,
            "Issue installment plan",
            {"program_enrollment": row["name"],
             "fee_structure": plan["name"],
             "posting_date": day,
             # For an approved Shamsi cadence the *contractual* date is
             # 1st of the present Afghan month + configured grace, even
             # when a student joins after that date. The server permits
             # current-month arrears only; it never backdates the GL.
             "first_due_date": first_solar_due or day,
             # Propose a two-month plan for the common short semester,
             # not the maximum invoice count. Finance explicitly
             # changes this field for Owner-configured longer courses.
             "installments": min(2, maximum)})

    def billing_guidance(row):
        """Resolve the plan for one unbilled enrollment into next/action.

        U9: the promise matches the command — a plan counts when it is not
        cancelled and carries components, submitted or draft alike. Editing
        stays the Draft-only Owner control; issuance does not care.
        """
        usable = issuable_plans(plans_by_key, row.get("program"),
                                row.get("academic_year"))
        complete = plan_with_components(usable, rows_by_plan)
        if len(complete) == 1:
            plan = complete[0]
            split = installment_next(plan, row)
            if split:
                return ("Split the configured plan into the owner-authorized "
                        "installment schedule, or bill it in one payment.",
                        "Finance Officer", split)
            return ("Issue the tuition fees from the configured plan for this "
                    "level and academic year.", "Finance Officer",
                    guided_action(
                        "Finance Officer", "toefl_house.finance.issue_tuition_fees",
                        "Issue tuition fees",
                        {"program_enrollment": row["name"],
                         "fee_structure": plan["name"],
                         "posting_date": day, "due_date": ""}))
        if complete:
            return ("More than one complete fee plan exists for this level and "
                    "year; billing stays paused until exactly one is kept.",
                    "Finance Officer", None)
        if usable:
            return ("The fee plan for this level and year has no components yet; "
                    "the Course Owner completes it in Academic Setup before this "
                    "enrollment can be billed.", "Course Owner", None)
        return ("No fee plan is configured for this level and academic year "
                "yet; the Course Owner defines fee plans in Academic Setup.",
                "Course Owner", None)

    billing_items = []
    for row in awaiting_billing[:LIMIT_QUEUES]:
        next_text, next_role, action = billing_guidance(row)
        item = {
            "id": row["name"],
            "person": row.get("student_name") or row.get("student") or "",
            "detail": " · ".join(part for part in (row.get("program"), row.get("academic_year")) if part),
            "status": "Unbilled",
            "stage": "Awaiting billing",
            "stage_definition": "A confirmed enrollment that no issued bill covers yet.",
            "next": next_text,
            "next_role": next_role,
            "waiting_since": row.get("enrollment_date"),
        }
        if action:
            item["action"] = action
        billing_items.append(item)

    assignment_items = [{
        "id": row["name"],
        "person": row.get("instructor") or "",
        "detail": " · ".join(part for part in (row.get("student_group"), row.get("skill")) if part),
        "status": row.get("effective_end") or "open",
        "stage": "Teaching assignment",
        "stage_definition": ("An instructor skill assignment. Pay is one-off in the first "
                             "covering payroll period, through native payroll."),
        "next": "Run native payroll for the covering period. This desk does not calculate pay.",
        "next_role": "Finance Officer",
        "waiting_since": row.get("effective_start"),
    } for row in assignments]

    # Every link must pass both the finance acting-role gate AND the native
    # DocType permission check. Accounts User cannot normally read Bin or
    # create Stock Entry; hiding those shortcuts avoids dead-end access errors
    # without granting stock-management rights to the cashier.
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    book_shop = []
    if {"Finance Manager", "Finance Officer", "Accounts User"}.issubset(roles):
        native_links = (
            ("Book items", "Item", "read"),
            ("Configure book prices", "Item Price", "create"),
            ("Warehouse stock", "Bin", "read"),
            ("Receive book stock", "Stock Entry", "create"),
            ("Sell books / sales invoices", "Sales Invoice", "create"),
            ("Record a customer payment", "Payment Entry", "create"),
        )
        links = [
            {"title": title, "slug": "List/" + doctype}
            for title, doctype, action in native_links
            if frappe.has_permission(doctype, action, user=user)
            and frappe.has_permission(doctype, "read", user=user)
        ]
        if links:
            book_shop = [section(
                "book-shop", "Book sales and stock", "links", items=links,
                empty_title="No book-shop shortcuts",
                empty_body="Book sales require the native Books item group and stock.",
            )]

    cash_section, tax_section, history_section = _cash_close_sections(day)

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("today", "Today", "queue", items=payment_items,
                    empty_title="No payments recorded today",
                    empty_body="No payment has been received for today. Payments appear here the moment they are posted."),
            section("facts", "Money facts", "facts", facts=money_facts,
                    empty_title="No money facts yet",
                    empty_body="Facts appear once the native billing and payment records exist."),
            section("outstanding", "Outstanding receivables", "queue",
                    items=[money_item(row, "Sales Invoice") for row in outstanding_invoices]
                          + [money_item(row, "Fees") for row in outstanding_fees],
                    empty_title="Nothing is outstanding",
                    empty_body="No submitted invoice or fee carries an outstanding amount for your scope."),
            section("billing", "Awaiting billing", "queue", items=billing_items,
                    empty_title="Everything submitted is billed",
                    empty_body="Every confirmed enrollment has an issued bill, or no enrollment has been confirmed yet."),
            section("policy", "Correction policy", "facts", facts=policy_facts,
                    empty_title="No correction policy yet",
                    empty_body="No correction policy version is recorded; new correction requests fail closed until a Finance Officer records the first version."),
            section("policy-versions", "Policy versions", "queue", items=version_items,
                    empty_title="No policy versions",
                    empty_body="No correction policy version is recorded; new correction requests fail closed until a Finance Officer records the first version."),
            section("corrections", "Correction queue", "queue",
                    items=_correction_items(corrections, policies),
                    empty_title="No correction requests",
                    empty_body="No correction request (invoice or tuition fee) is open. Requests appear here the moment they are created."),
            section("assignments", "Teaching assignments (native payroll)", "queue",
                    items=assignment_items,
                    empty_title="No teaching assignments",
                    empty_body="No instructor skill assignment is on file. Assignments appear here from teaching scheduling; pay stays on native payroll."),
            section("compensation", "Teaching compensation", "queue",
                    items=_compensation_items(contracts, instructors),
                    empty_title="No teaching compensation work yet",
                    empty_body="No active teaching contract or instructor on file; the queue appears as soon as contracts are recorded or payroll instructors exist."),
            cash_section,
            history_section,
            tax_section,
        ] + book_shop,
    }


def _scope_companies():
    """The viewer's native Company scope, or None for an unrestricted viewer."""
    allowed = scope_filters("finance").get("company")
    return None if allowed is None else list(allowed)


def _cash_close_sections(day):
    """Cashiers' drawer position, close history and native tax readiness.

    Every number here is computed from the native ledger (or is the control
    record's own stored count); the desk never posts, and the guided action is
    the existing guarded close command, offered only to a Finance Officer.
    """
    companies = _scope_companies()
    position = cashier_money.cashier_position(day, companies=companies)
    history = cashier_money.cashier_history(companies=companies, limit=LIMIT_TODAY)

    drawers = [(row["company"], drawer) for row in position
               for drawer in row.get("drawers", [])]
    closed = [row for row in position if row.get("close")]
    drifted = [row["company"] for row in position if row.get("drift")]
    # In multi-company mode, a close in ONE company is never a global close.
    # Add each closed company's recorded expectation and each still-open
    # company's current native ledger position, without dropping either.
    expected_total = round(sum(
        float((row["close"] or {}).get("total_expected") or 0)
        if row.get("close") else sum(d["closing"] for d in row.get("drawers", []))
        for row in position), 2)
    variance_total = round(sum(
        float(row.get("close", {}).get("total_variance") or 0) for row in closed), 2)

    facts = [
        {"label": "Drawers in scope",
         "definition": ("Native Cash and Bank accounts of the companies in your "
                        "scope. Expected money is their ledger closing balance."),
         "value": len(drawers), "owner": None},
        {"label": "Cash close today",
         "definition": ("All in-scope companies must have a submitted close to show Closed. "
                        "Partial company closes and posting drift are never reported as Closed."),
         "value": ("No drawers" if not drawers else
                   "Drift" if drifted else
                   "Closed" if len(closed) == len(position) else
                   "Partially closed" if closed else "Open"),
         "owner": "Finance Officer"},
        {"label": "Expected at close",
         "definition": ("Ledger closing balance of the drawers: the counted "
                        "figure when a close exists, otherwise the live position."),
         "value": f"{expected_total:.2f}", "owner": None},
        {"label": "Variance recorded",
         "definition": ("Counted minus expected on the submitted close, exactly "
                        "as the control record states it."),
         "value": f"{variance_total:.2f}" if closed else "Not closed",
         "owner": "Finance Officer"},
        {"label": "Ledger drift",
         "definition": ("A posting dated on or before a closed day was created "
                        "after the close, so the counted figures are stale."),
         "value": ", ".join(drifted) if drifted else "None",
         "owner": "Finance Auditor"},
    ]

    closing_window = cashier_money.day_window_hint()
    items = []
    closes = {row["company"]: row.get("close") for row in position}
    for company, drawer in drawers:
        close = closes.get(company)
        if close and drifted and company in drifted:
            state, next_text = "Drift", ("Re-check the drawer against the ledger; "
                                         "the day was posted to after the close. "
                                         "The Finance Auditor reviews the difference.")
        elif close:
            state = "Closed"
            next_text = "No action; the day is closed and cannot be re-stated."
        else:
            state = "Open"
            next_text = ("Count the drawer and record the close for today "
                         + ("within " + closing_window + "." if closing_window
                            else "; no billing policy governs the closing window yet."))
        item = {
            "id": f"{company}:{drawer['account']}",
            "person": drawer["account"],
            "detail": f"{company} · opening {drawer['opening']:.2f}, "
                      f"today {drawer['movement']:.2f}",
            "status": state,
            "stage": "Cash drawer",
            "stage_definition": ("Expected money is the native ledger closing "
                                 "balance of this account; counted money is what "
                                 "the cashier records."),
            "next": next_text,
            "next_role": "Finance Officer",
            "waiting_since": day,
            "amount": drawer["closing"],
            "currency": "",
        }
        items.append(item)

    cash = section("cash-close", "Cash close", "queue", items=items,
                   facts=facts,
                   empty_title="No cash drawer in scope",
                   empty_body="This company has no native Cash or Bank account yet; nothing can be counted until Finance configures one.")

    history_items = [{
        "id": row["name"],
        "person": row.get("cashier") or "",
        "detail": f"{row.get('date')} · expected {float(row.get('total_expected') or 0):.2f}, "
                  f"counted {float(row.get('total_counted') or 0):.2f}",
        "status": "Variance" if abs(float(row.get("total_variance") or 0)) > 0.005
                  else "Balanced",
        "stage": "Cash close",
        "stage_definition": ("A submitted cashier day close: the counted drawer "
                             "against the native ledger for that business day."),
        "next": "No action; a submitted close is never overwritten.",
        "next_role": None,
        "waiting_since": row.get("date"),
        "amount": row.get("total_variance") or 0,
        "currency": "",
    } for row in history]
    history_section = section(
        "cash-history", "Cash close history", "queue", items=history_items,
        empty_title="No cash close recorded",
        empty_body="No cashier day has been closed yet; closes appear here the moment they are submitted.")

    tax_rows = [tax_configuration.describe_tax_configuration(name)
                for name in (companies if companies is not None else [])
                if name]
    if not tax_rows:
        tax_rows = [tax_configuration.describe_tax_configuration()]
    tax_facts = []
    for entry in tax_rows:
        for row in entry.get("companies", []) or []:
            tax_facts.append({
                "label": f"Native tax — {row['company']}",
                "definition": ("Whether the owner has configured a native sales "
                               "tax template. Unconfigured means the explicit "
                               "zero the owner decision records; no rate is "
                               "invented here."),
                "value": row["state"] + (
                    f" ({row['configured_tax_lines']} lines)" if row["configured_tax_lines"] else ""),
                "owner": "Course Owner",
            })
    tax_section = section(
        "tax", "Tax configuration", "facts", facts=tax_facts,
        empty_title="No company tax state",
        empty_body="No company is visible in your scope, so no native tax configuration can be reported.")

    return cash, tax_section, history_section


def _summarize(rows, field, currency_key="currency"):
    """Per-currency totals of an existing row list. No new query, no rounding
    policy beyond two decimals for display. Payment rows carry the paying
    account's currency, not a flat `currency` column (pinned authority)."""
    totals = {}
    for row in rows:
        currency = row.get(currency_key) or ""
        totals[currency] = totals.get(currency, 0) + float(row.get(field) or 0)
    if not totals:
        return "0"
    return ", ".join(f"{value:.2f} {code}".strip() for code, value in sorted(totals.items()))
