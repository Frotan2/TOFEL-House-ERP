"""Finance Manager desk: today's money facts and the receivable work list.

Read-only over the native money authorities (Fees, Sales Invoice, Payment
Entry) plus the owned correction queue. Native ERPNext stays the only money
authority: this projection computes no ledger, no balance and no policy. The
charged / paid / outstanding distinction is the native numbers themselves, and
refund/cancel states come only from native docstatus and Sales Invoice status.
Sections are specified in docs/product/ROLE-DESKS.md.
"""
import frappe
from frappe.utils import today

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    LIMIT_TODAY,
    guided_action,
    issuable_plans,
    plan_with_components,
    project_rows,
    require_desk_audience,
    section,
)

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
ASSIGNMENT_FIELDS = ["name", "student_group", "skill", "instructor", "contract",
                     "course_schedule", "effective_start", "effective_end"]
PLAN_ROW_FIELDS = ["name", "parent", "parenttype", "fees_category", "amount", "idx"]


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


def _correction_items(rows):
    approver_role = _active_policy_role()
    items = []
    for row in rows:
        pending = row["status"] == "Requested"
        is_fees = bool(row.get("fees"))
        target = row.get("fees") or row.get("sales_invoice") or ""
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
                               ["name", "sales_invoice", "fees", "reason", "requested_amount",
                                "status", "approved_by", "credit_note", "modified"],
                               filters={"status": ("in", ["Requested", "Approved", "Denied", "Posted"])},
                               order_by="modified desc", limit=LIMIT_QUEUES)

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

    money_facts = [
        {"label": "Collected today",
         "definition": "Money received today from posted payment records, summed per receiving currency.",
         "value": _summarize(payments, "paid_amount"),
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
        {"label": "Teaching assignments on file",
         "definition": "Instructor skill assignments. Pay is native payroll, one-off per assignment; this desk does not calculate pay.",
         "value": len(assignments), "owner": "Finance Officer"},
    ]

    def money_item(row, kind):
        state = _invoice_display_state(row) if kind == "Sales Invoice" else _money_state(row)
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
                "Amounts are read straight from the posted document.").format(
                    grand=row.get("grand_total") or 0, currency=row.get("currency") or "",
                    outstanding=row.get("outstanding_amount") or 0),
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
            section("corrections", "Correction queue", "queue",
                    items=_correction_items(corrections),
                    empty_title="No correction requests",
                    empty_body="No correction request (invoice or tuition fee) is open. Requests appear here the moment they are created."),
            section("assignments", "Teaching assignments (native payroll)", "queue",
                    items=assignment_items,
                    empty_title="No teaching assignments",
                    empty_body="No instructor skill assignment is on file. Assignments appear here from teaching scheduling; pay stays on native payroll."),
        ],
    }


def _summarize(rows, field):
    """Per-currency totals of an existing row list. No new query, no rounding
    policy beyond two decimals for display."""
    totals = {}
    for row in rows:
        currency = row.get("currency") or ""
        totals[currency] = totals.get(currency, 0) + float(row.get(field) or 0)
    if not totals:
        return "0"
    return ", ".join(f"{value:.2f} {code}".strip() for code, value in sorted(totals.items()))
