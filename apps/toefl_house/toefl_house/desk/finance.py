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
        item = {
            "id": row["name"],
            "person": row.get("sales_invoice") or "",
            "detail": row.get("reason") or "",
            "status": row["status"],
            "stage": "Correction " + str(row["status"] or "").lower(),
            "stage_definition": "Invoice correction request from the correction framework.",
            "next": "Approve or deny the request." if pending else "No action; the request is decided.",
            "next_role": (approver_role or "Finance Officer") if pending else None,
            "waiting_since": row.get("modified"),
        }
        if pending and approver_role:
            item["action"] = guided_action(approver_role,
                                           "toefl_house.finance.corrections.approve_invoice_correction",
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
                             "received_amount", "currency", "company", "posting_date",
                             "docstatus"],
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
                               ["name", "sales_invoice", "reason", "requested_amount",
                                "status", "approved_by", "credit_note", "modified"],
                               filters={"status": ("in", ["Requested", "Approved", "Denied"])},
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

    money_facts = [
        {"label": "Collected today",
         "definition": "Submitted Payment Entry rows of type Receive posted today, summed per currency.",
         "value": _summarize(payments, "paid_amount"),
         "owner": None},
        {"label": "Invoiced today",
         "definition": "Submitted Sales Invoice and Fees grand totals posted today, summed per currency.",
         "value": _summarize(invoices_today + fees_today, "grand_total"),
         "owner": None},
        {"label": "Outstanding invoices",
         "definition": "Submitted Sales Invoices with native outstanding_amount above zero.",
         "value": len(outstanding_invoices), "owner": "Finance Officer"},
        {"label": "Outstanding tuition fees",
         "definition": "Submitted Fees with native outstanding_amount above zero.",
         "value": len(outstanding_fees), "owner": "Finance Officer"},
        {"label": "Corrections pending",
         "definition": "Invoice correction requests in Requested status.",
         "value": sum(1 for row in corrections if row["status"] == "Requested"),
         "owner": "Finance Officer"},
        {"label": "Enrollments awaiting billing",
         "definition": "Submitted Program Enrollments with no non-cancelled Fees row.",
         "value": len(awaiting_billing), "owner": "Finance Officer"},
    ]

    def money_item(row, kind):
        state = _invoice_display_state(row) if kind == "Sales Invoice" else _money_state(row)
        return {
            "id": row["name"],
            "person": row.get("customer_name") or row.get("customer")
            or row.get("student_name") or row.get("student") or "",
            "detail": row.get("program") or row.get("th_placement_case") or "",
            "status": state,
            "stage": kind,
            "stage_definition": (
                "Charged {grand} {currency}; outstanding {outstanding} {currency}. "
                "These are the native document amounts.").format(
                    grand=row.get("grand_total") or 0, currency=row.get("currency") or "",
                    outstanding=row.get("outstanding_amount") or 0),
            "next": "Record the payment against this document." if state in ("Outstanding", "Overdue", "Unpaid")
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
        "stage_definition": "Submitted Payment Entry, type Receive, posted today.",
        "next": "No action.",
        "next_role": None,
        "waiting_since": row.get("posting_date"),
        "amount": row.get("paid_amount") or row.get("received_amount") or 0,
        "currency": row.get("currency") or "",
    } for row in payments]

    billing_items = [{
        "id": row["name"],
        "person": row.get("student_name") or row.get("student") or "",
        "detail": " · ".join(part for part in (row.get("program"), row.get("academic_year")) if part),
        "status": "Unbilled",
        "stage": "Awaiting billing",
        "stage_definition": "Submitted enrollment with no Fees record referencing it.",
        "next": "Issue the tuition fees from a configured Fee Structure.",
        "next_role": "Finance Officer",
        "waiting_since": row.get("enrollment_date"),
        "action": guided_action("Finance Officer", "toefl_house.finance.issue_tuition_fees",
                                "Issue tuition fees",
                                {"program_enrollment": row["name"], "fee_structure": "",
                                 "posting_date": day, "due_date": ""}),
    } for row in awaiting_billing[:LIMIT_QUEUES]]

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("today", "Today", "queue", items=payment_items,
                    empty_title="No payments recorded today",
                    empty_body="No submitted Payment Entry of type Receive is posted for today. Check the date or record the payment natively."),
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
                    empty_body="Every submitted Program Enrollment has a Fees record, or no enrollment has been submitted yet."),
            section("corrections", "Correction queue", "queue",
                    items=_correction_items(corrections),
                    empty_title="No correction requests",
                    empty_body="No invoice correction has been requested. Requests appear here the moment they are created."),
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
