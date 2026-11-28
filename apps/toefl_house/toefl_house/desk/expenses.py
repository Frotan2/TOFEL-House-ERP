"""Finance Desk expense queue and the month's income/expense position.

Read-only presentation over native ERPNext records. The expense journals
come through the allow-listed ``project_rows`` seam; the ledger position is
computed by ``finance.expenses.month_position`` (native GL Entry grouped by
Account root type) for the current Solar Hijri month. Different currencies
are never added together.
"""
import frappe
from frappe.utils import today

from toefl_house.desk import LIMIT_QUEUES, guided_action, project_rows, section, viewer_roles
from toefl_house.finance import expenses as expense_commands

JOURNAL = "Journal Entry"
JOURNAL_FIELDS = ["name", "company", "posting_date", "pay_to_recd_from", "user_remark", "total_debit",
                  "docstatus", "th_expense_recorder", "voucher_type", "cheque_no"]
PREFIX = "toefl_house.finance.expenses."


def _money(value, currency):
    return f"{float(value or 0):,.2f} {currency or ''}".strip()


def position_facts(day=None):
    """Income / Expenses / Net facts for the month, or an explicit unavailable fact."""
    unavailable = [{"label": "This month", "value": "—", "owner": None,
                    "definition": "Income and expenses could not be read from the general ledger. "
                                  "A failed read is never shown as zero."}]
    try:
        positions = expense_commands.month_position(day)
    except Exception:
        return unavailable
    facts = []
    many = len(positions) > 1
    for row in positions:
        suffix = f" — {row['company']}" if many else ""
        period = f"{row['period']} ({row['start']} to {row['end']})"
        facts.extend([
            {"label": "Income this month" + suffix, "value": _money(row["income"], row["currency"]), "owner": None,
             "definition": f"Posted income (tuition, placement fees, book sales…) for {period}, from the general ledger."},
            {"label": "Expenses this month" + suffix, "value": _money(row["expense"], row["currency"]), "owner": None,
             "definition": f"Posted expenses (rent, utilities, salaries, supplies…) for {period}, from the general ledger."},
            {"label": "Net result this month" + suffix, "value": _money(row["net"], row["currency"]), "owner": None,
             "definition": "Income minus expenses for the same period. A negative value means the month so far "
                           "has cost more than it earned."},
        ])
    return facts


def _expense_item(row, viewer, may_void, currencies):
    posted = int(row.get("docstatus") or 0) == 1
    currency = currencies.get(row.get("company")) or ""
    amount = float(row.get("total_debit") or 0)
    item = {
        "id": row["name"],
        "person": row.get("pay_to_recd_from") or "",
        "detail": " · ".join(part for part in (row.get("user_remark"), row.get("cheque_no")) if part),
        "status": "Posted" if posted else "Void",
        "stage": "Cash payment" if row.get("voucher_type") == "Cash Entry" else "Bank payment",
        "stage_definition": "A paid institute expense posted to the general ledger.",
        "next": "No action." if posted else "Voided; the original and its reversal stay in the ledger.",
        "next_role": None,
        "waiting_since": row.get("posting_date"),
        "amount": amount,
        "currency": currency,
        "meta": [_money(amount, currency), "Recorded by " + (row.get("th_expense_recorder") or "—")],
    }
    if posted and may_void and row.get("th_expense_recorder") != viewer:
        action = guided_action("Finance Manager", PREFIX + "void_expense", "Void expense",
                               {"journal_entry": row["name"],
                                "summary": f"{item['person']} · {_money(amount, currency)} · {row.get('posting_date')}"})
        if action:
            item["action"] = action
    return item


def finance_sections(day=None, viewer=None):
    """The Finance Desk expense queue (with guided actions) and month position."""
    if not expense_commands.schema_ready():
        return []
    day = str(day or today())
    viewer = viewer or frappe.session.user
    _, label, start, end = expense_commands.month_period(day)
    rows = project_rows("finance", JOURNAL, JOURNAL_FIELDS,
                        filters={"th_expense_recorder": ("is", "set"), "docstatus": ("in", [1, 2]),
                                 "posting_date": ("between", [start, end])},
                        order_by="posting_date desc, name desc", limit=LIMIT_QUEUES)
    currencies = {company: frappe.get_cached_value("Company", company, "default_currency")
                  for company in {row.get("company") for row in rows if row.get("company")}}
    may_void = "Finance Manager" in viewer_roles()
    items = [_expense_item(row, viewer, may_void, currencies) for row in rows]
    totals = {}
    for row in rows:
        if int(row.get("docstatus") or 0) == 1:
            currency = currencies.get(row.get("company")) or ""
            totals[currency] = totals.get(currency, 0.0) + float(row.get("total_debit") or 0)
    record = guided_action("Finance Officer", PREFIX + "record_expense", "Record an expense", {"posting_date": day})
    listed = ("Listed total: " + ", ".join(_money(v, k) for k, v in sorted(totals.items())) + ". ") if totals else ""
    notes = (f"Expenses for {label}, newest first (up to {LIMIT_QUEUES}). {listed}"
             "The full ledger stays in Accounting → General Ledger.")
    return [section("expenses", f"Expenses — {label}", "queue", items=items,
                    empty_title="No expenses recorded this month",
                    empty_body="Record rent, utilities, supplies and other payments as they are paid. "
                               "Each one posts to the general ledger immediately.",
                    notes=notes, actions=[record] if record else None),
            section("month-position", f"This month at a glance — {label}", "facts", facts=position_facts(day),
                    empty_title="No postings yet",
                    empty_body="Income, expenses and the net result appear once money is posted.")]
