"""Bounded cash work queues; native Payment Entry remains the ledger."""
import json
from decimal import Decimal

import frappe

from toefl_house.desk import LIMIT_QUEUES, collection_schema_ready, guided_action, project_rows, section

FEES = "Fees"
PAYMENT = "Payment Entry"
FEE_FIELDS = ["name", "student", "program", "due_date", "outstanding_amount", "currency", "company", "docstatus"]
RECEIPT_FIELDS = ["name", "party", "received_amount", "paid_to", "paid_to_account_currency",
                  "company", "posting_date", "docstatus", "th_reception_collector",
                  "th_collection_fees", "th_collection_handover"]
PREFIX = "toefl_house.finance.collections."


def _receipts(desk, own=False):
    filters = {"th_collection_fees": ("is", "set"), "docstatus": ("in", [1, 2])}
    if own:
        filters["th_reception_collector"] = frappe.session.user
    else:
        filters.update(docstatus=1, th_collection_handover=("is", "not set"))
    rows = project_rows(desk, PAYMENT, RECEIPT_FIELDS, filters=filters,
                        order_by="posting_date desc, name desc", limit=LIMIT_QUEUES)
    # Payment Entry has no direct Branch column. Recheck each Student chain
    # before any identity/amount is exposed, including settled historical Fees.
    from toefl_house.command_scope import authorize_command_scope
    visible = []
    for row in rows:
        try:
            authorize_command_scope("read_collection_receipt", {"payment_entry": row["name"]}, frappe.session.user)
        except frappe.PermissionError:
            continue
        visible.append(row)
    return visible


def reception_sections(students=None):
    if not collection_schema_ready():
        return []
    from toefl_house.finance.collections import counter_for
    filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
    if students is not None:
        filters["student"] = ("in", list(students)[:25])
    fees = project_rows("reception", FEES, FEE_FIELDS,
        filters=filters, order_by="due_date asc", limit=LIMIT_QUEUES)
    bills = []
    for row in fees:
        item = dict(id=row["name"], person=row["student"],
            detail=f'{row["program"]} · {row["outstanding_amount"]} {row["currency"]} outstanding',
            stage="Tuition due", next="Count the cash and issue one numbered receipt.", next_role="Reception")
        try:
            counter_for(frappe.session.user, row["company"])
        except (frappe.ValidationError, frappe.DoesNotExistError):
            item["next"] = "Ask the Owner to assign your separate cash counter before collecting."
        else:
            item["action"] = guided_action("Reception", PREFIX + "record_reception_collection", "Issue cash receipt",
                dict(fees=row["name"], outstanding=row["outstanding_amount"], currency=row["currency"]))
        bills.append(item)
    collection = section("collections", "Collect tuition", "queue", items=bills,
        empty_title="No tuition due in this preview", empty_body="Search for a student to find their submitted bills beyond this preview.")
    if students is not None:
        return [collection]
    receipts = [dict(id=row["name"], person=row["party"],
        detail=f'{row["received_amount"]} {row["paid_to_account_currency"]} · {row["th_collection_fees"]}',
        stage="Void" if row["docstatus"] == 2 else ("Handed to Finance" if row["th_collection_handover"] else "At your counter"),
        next="View or print the numbered receipt.", next_role="Reception",
        action=guided_action("Reception", PREFIX + "get_collection_receipt", "View receipt", dict(payment_entry=row["name"])))
        for row in _receipts("reception", own=True)]
    return [collection,
        section("collection-receipts", "My cash receipts", "queue", items=receipts,
        empty_title="No cash receipts yet", empty_body="Issued receipts reduce tuition immediately. Finance later accepts the physical cash handover.")]


def finance_sections():
    if not collection_schema_ready():
        return []
    groups = {}
    for row in _receipts("finance"):
        key = (row["th_reception_collector"], row["company"], row["paid_to"], row["paid_to_account_currency"])
        groups.setdefault(key, []).append(row)
    items = []
    for (collector, company, counter, currency), rows in groups.items():
        names = sorted(row["name"] for row in rows)
        total = sum((Decimal(str(row["received_amount"])) for row in rows), Decimal(0))
        items.append(dict(id=names[0], person=collector, detail=f"{counter} · {company} · {total} {currency}",
            stage="Cash awaiting handover", next="Count the physical cash for these listed receipts. Investigate any difference.",
            next_role="Finance Officer", action=guided_action("Finance Officer", PREFIX + "accept_reception_handover",
                "Accept cash handover", dict(payment_entries=json.dumps(names), receipt_list="\n".join(names),
                    expected_amount=float(total), currency=currency))))
    return [section("reception-handovers", "Reception cash handovers", "queue", items=items,
        empty_title="No unhanded receipts in this preview", empty_body="Each batch lists its exact receipts. Accepting cash moves it to main Cash without charging the student again.",
        notes="This bounded preview is not the complete counter ledger. Hand over only the listed receipts.")]


def owner_sections():
    return [section("reception-counters", "Reception cash controls", "queue", items=[
        dict(id="assign-counter", person="Separate reception counters", stage="Owner control",
            next="Assign one separate cash counter per receptionist.", next_role="Course Owner",
            action=guided_action("Course Owner", PREFIX + "configure_reception_counter", "Assign reception counter", {})),
        dict(id="correct-receipt", person="Correct a tuition receipt", stage="Owner control",
            next="Only an unhanded receipt can be voided and replaced. Record the reason; the cash amount stays the same.", next_role="Course Owner",
            action=guided_action("Course Owner", PREFIX + "correct_reception_collection", "Correct unhanded receipt", {})),
    ], empty_title="Reception controls", empty_body="Owner-controlled cash assignments and documented corrections.")]
