"""Case work for Finance and General Manager, under native refund read ACLs."""
import frappe

from toefl_house.desk import LIMIT_QUEUES, guided_action, refund_case_rows, section

FIELDS = ["name", "student", "company", "fees", "requested_amount", "approved_amount",
          "reason", "evidence", "approval_evidence", "status", "requested_by", "approved_by",
          "paying_user", "credit_journal", "payment_entry", "modified"]
PREFIX = "toefl_house.finance.tuition_refund_commands."


def refund_sections(desk):
    rows = refund_case_rows(desk, FIELDS)
    if rows is None:
        return [section("tuition-refunds", "Tuition refunds", "queue", items=[],
            empty_title="Refund migration required",
            empty_body="Ask the system administrator to complete the supported application migration before opening or paying refund cases.")]
    items = []
    if desk == "finance":
        action = guided_action("Finance Officer", PREFIX + "request_tuition_refund", "Request tuition refund", {})
        if action:
            items.append(dict(id="new-refund", person="New tuition refund case", stage="Finance request",
                next="Identify the original tuition bill and document the amount, reason and evidence for General Manager review.",
                next_role="Finance Officer", action=action))
    for row in rows[:LIMIT_QUEUES]:
        status = row["status"]
        detail = (f'{row["company"]} · Fees {row["fees"]} · Requested {row["requested_amount"]} AFN'
                  f' · {row["reason"]} · Evidence: {row["evidence"]}')
        item = dict(id=row["name"], person=row["student"], detail=detail,
                    status=status, stage="Refund " + str(status).lower(), waiting_since=row["modified"])
        args = {"request": row["name"], "recipient": row["student"], "tuition_bill": row["fees"],
                "refund_amount": row["approved_amount"] if status == "Approved" else row["requested_amount"],
                "currency": "AFN", "refund_reason": row["reason"], "supporting_evidence": row["evidence"],
                "approved_by": row["approved_by"] or "", "approval_evidence": row["approval_evidence"] or ""}
        if status == "Requested":
            item.update(next="General Manager: review the original bill, collected amount and evidence; approve or deny this case.", next_role="General Manager")
            if row["requested_by"] != frappe.session.user:
                item["action"] = guided_action("General Manager", PREFIX + "approve_tuition_refund", "Approve refund", args)
            deny = guided_action("General Manager", PREFIX + "deny_tuition_refund", "Deny refund", args)
            if deny:
                item["actions"] = [deny]
        elif status == "Approved":
            item["detail"] += (f' · Approved {row["approved_amount"]} AFN by {row["approved_by"]}'
                               f' · Approval evidence: {row["approval_evidence"]}')
            item.update(next="Independent Finance Manager: verify the recipient and amount, then record the cash payout from main Cash.", next_role="Finance Manager")
            if row["approved_by"] != frappe.session.user:
                item["action"] = guided_action("Finance Manager", PREFIX + "pay_tuition_refund", "Pay approved refund", args)
            else:
                item["next"] = "Another Finance Manager must execute this payout; the approving manager cannot pay it."
        elif status == "Paid":
            item["detail"] += (f' · Returned {row["approved_amount"]} AFN by {row["paying_user"]}'
                               f' · Native credit {row["credit_journal"]} · Native payout {row["payment_entry"]}')
            item.update(next="Retain the linked accounting evidence. An individual credit or payout cannot be cancelled separately.", next_role=None)
        elif status == "Denied":
            item.update(next="No cash was returned for this denied case. A different case requires a new documented request.", next_role=None)
        else:
            item.update(next="Ask Finance to investigate this unsupported case status before taking any action.", next_role=None)
        items.append(item)
    return [section("tuition-refunds", "Tuition refunds", "queue", items=items,
        empty_title="No refund cases in this preview", empty_body="Document each case before General Manager approval and independent Finance payout.",
        notes=("Showing the most recently changed cases in your permitted Company and Branch scope. "
               "A refund reduces native tuition income and retained cash; the original tuition outstanding remains unchanged. "
               + ("More cases exist beyond this 25-case preview." if len(rows) > LIMIT_QUEUES else "")))]
