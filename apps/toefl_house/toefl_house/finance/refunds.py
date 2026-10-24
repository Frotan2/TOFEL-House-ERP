"""Refund and return integrity for native book commerce.

Two native documents move money *out* of the institute, and both are easy to
misuse if nothing checks their shape:

- a **credit note** (``Sales Invoice`` with ``is_return=1``) restocks books and
  creates a receivable in the customer's favour;
- a **refund** (``Payment Entry`` with ``payment_type="Pay"``) settles that
  credit note in cash or bank.

The rules below keep both inside native accounting:

*Return* — a return may only restock what an invoice actually sold. The
cumulative returned quantity for an item can never exceed the invoiced
quantity, and the cumulative credited value can never exceed the invoice's
``grand_total``. This refuses the "return everything twice" and the
"return two books from a one-book sale" cases that a per-document native check
cannot see, because it only inspects one return at a time.

*Refund* — a customer refund must settle a submitted credit note of the same
customer and company, for no more than that credit note still owes, out of a
Cash/Bank account of the company, with no unallocated remainder. An
unreferenced "cash out to a customer", an over-allocation, a refund through an
income/equity account, or a refund against a live sales invoice (money back
without a return) is refused. Supplier, payroll and staff-advance payments are
untouched by this guard.

Nothing here computes an amount, a rate or a tax: every number is the native
document's own.
"""
import math

import frappe

INVOICE = "Sales Invoice"
PAYMENT = "Payment Entry"
TOLERANCE = 0.005
CASH_ACCOUNT_TYPES = ("Cash", "Bank")


def _flt(value):
    return round(float(value or 0), 6)


# --- Returns -------------------------------------------------------------

def return_quantities_ok(original_items, prior_returns, current_items):
    """Cumulative restocked quantity never exceeds what was sold.

    ``original_items`` and ``current_items`` are ``{item_code: qty}`` maps,
    ``prior_returns`` a list of such maps from already-submitted returns of
    the same invoice. The current return must sell nothing the invoice did
    not, in a warehouse-bearing line (checked by the caller), and its
    cumulative total per item must stay within ``original_items``.
    """
    original = {code: _flt(qty) for code, qty in (original_items or {}).items()}
    already = {}
    for rows in (prior_returns or []):
        for code, qty in rows.items():
            already[code] = already.get(code, 0.0) + _flt(qty)
    running = dict(already)
    for code, qty in (current_items or {}).items():
        if code not in original:
            return False
        amount = _flt(qty)
        if amount <= 0:
            return False
        running[code] = running.get(code, 0.0) + amount
        if running[code] - original[code] > TOLERANCE:
            return False
    return True


def return_value_ok(original_grand_total, prior_credited, current_grand_total):
    """Cumulative credited value never exceeds the invoice's billed value."""
    original = abs(_flt(original_grand_total))
    already = abs(_flt(prior_credited))
    current = abs(_flt(current_grand_total))
    if current <= 0:
        return False
    return already + current - original <= TOLERANCE


# --- Refunds -------------------------------------------------------------

def refund_allocation_ok(payment, credit_notes, party_account, cash_accounts,
                         *, existing=False):
    """A customer refund settles credit notes, from cash, with no leftovers.

    ``payment`` exposes the native fields (``party_type``, ``party``,
    ``company``, ``paid_from``, ``paid_to``, ``paid_amount``,
    ``unallocated_amount``, ``references``); ``credit_notes`` maps the
    referenced invoice names to their live facts
    (``docstatus``, ``is_return``, ``customer``, ``company``,
    ``outstanding_amount``, ``grand_total``).

    ``existing=True`` judges an already-submitted refund on its cancel or
    post-submit edit path: the credit note it settled now owes nothing, so
    the "no more than it still owes" ceiling would read every legitimate
    cancellation as an over-allocation. The rest of the shape (a submitted
    return of the same customer/company, paid from cash, fully allocated)
    still has to hold.
    """
    if (_payment(payment, "payment_type") != "Pay"
            or _payment(payment, "party_type") != "Customer"):
        return True  # not a customer refund; this guard judges only refunds
    references = _payment(payment, "reference_rows") or []
    if not references:
        return False  # money out to a customer without a credit note
    if abs(_flt(_payment(payment, "unallocated_amount"))) > TOLERANCE:
        return False
    paid_from = _payment(payment, "paid_from")
    paid_to = _payment(payment, "paid_to")
    if paid_from not in (cash_accounts or ()):
        return False
    if party_account and paid_to != party_account:
        return False
    company = _payment(payment, "company")
    party = _payment(payment, "party")
    # A reference can be repeated across child rows. Compare its COMBINED
    # allocation to the live balance, not each row independently.
    allocated_by_note = {}
    for row in references:
        if not isinstance(row, dict) or row.get("reference_doctype") not in (
                None, "Sales Invoice"):
            return False
        name = row.get("reference_name")
        note = (credit_notes or {}).get(name)
        if not note:
            return False
        if int(note.get("docstatus") or 0) != 1 or not int(note.get("is_return") or 0):
            return False
        if note.get("customer") != party or note.get("company") != company:
            return False
        allocated = abs(_flt(row.get("allocated_amount")))
        if not math.isfinite(allocated) or allocated <= 0:
            return False
        allocated_by_note[name] = allocated_by_note.get(name, 0.0) + allocated
        if not existing:
            outstanding = abs(_flt(note.get("outstanding_amount")))
            if not math.isfinite(outstanding):
                return False
            if allocated_by_note[name] - outstanding > TOLERANCE:
                return False
    total_allocated = sum(allocated_by_note.values())
    paid = _payment(payment, "paid_amount")
    if paid is None or not math.isfinite(_flt(paid)) or _flt(paid) <= 0:
        return False
    if not math.isfinite(total_allocated) or abs(total_allocated - _flt(paid)) > TOLERANCE:
        return False
    # No unreviewed deductions can reduce the amount actually paid while
    # still reporting the credit as fully refunded.
    deductions = _payment(payment, "deductions") or []
    if any(not isinstance(row, dict) or
           not math.isfinite(_flt(row.get("amount"))) or
           abs(_flt(row.get("amount"))) > TOLERANCE
           for row in deductions):
        return False
    return True


def _payment(payment, key):
    """Read one fact from a Payment Entry draft or a plain dict."""
    if isinstance(payment, dict) and key in payment:
        return payment[key]
    if key == "reference_rows":
        rows = getattr(payment, "references", None) or []
        return [row.as_dict() if hasattr(row, "as_dict") else dict(row)
                for row in rows]
    value = getattr(payment, key, None)
    return value


# --- Site seams ----------------------------------------------------------

def _cash_accounts(company):
    rows = frappe.db.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0,
                 "account_type": ["in", list(CASH_ACCOUNT_TYPES)]},
        fields=["name"],
        limit_page_length=200,
    )
    return {row["name"] for row in (rows or [])}


def refund_permitted(doc, *, existing=False):
    """Refund shape check used by the Payment Entry guard."""
    if (getattr(doc, "payment_type", None) != "Pay"
            or getattr(doc, "party_type", None) != "Customer"):
        return True
    company = getattr(doc, "company", None)
    if not company:
        return False
    names = [row.get("reference_name") for row in (doc.get("references") or [])]
    notes = {}
    for name in names:
        if not name:
            continue
        row = frappe.db.get_value(
            INVOICE, name,
            ["docstatus", "is_return", "customer", "company", "outstanding_amount",
             "grand_total"], as_dict=True)
        if row:
            notes[name] = dict(row)
    party_account = frappe.db.get_value(
        "Company", company, "default_receivable_account")
    facts = {
        "payment_type": getattr(doc, "payment_type", None),
        "party_type": getattr(doc, "party_type", None),
        "party": getattr(doc, "party", None),
        "company": company,
        "paid_from": getattr(doc, "paid_from", None),
        "paid_to": getattr(doc, "paid_to", None),
        "unallocated_amount": getattr(doc, "unallocated_amount", 0) or 0,
        "paid_amount": getattr(doc, "paid_amount", None),
        "deductions": [row.as_dict() if hasattr(row, "as_dict") else dict(row)
                       for row in (doc.get("deductions") or [])],
        "reference_rows": [row.as_dict() if hasattr(row, "as_dict") else dict(row)
                           for row in (doc.get("references") or [])],
    }
    return refund_allocation_ok(facts, notes, party_account,
                                _cash_accounts(company), existing=existing)


def guard_payment_entry(doc, method=None):
    """``Payment Entry`` seam: customer refunds must settle a credit note.

    Receipts, supplier payments and every other native payment type pass
    through untouched — the native validations remain the authority for them.
    """
    from toefl_house.security import require_operational
    require_operational()
    # Cancelling a submitted refund and editing its post-submit fields are
    # native reversal paths, not new money out: the credit note they settled
    # legitimately owes nothing by then, so only the settlement shape is
    # re-asserted. Creation and submission keep the full ceiling.
    if refund_permitted(doc, existing=method in (
            "before_cancel", "before_update_after_submit")):
        return
    raise frappe.ValidationError(
        "A customer refund must settle a submitted credit note of the same "
        "customer, for no more than it owes, paid from a Cash or Bank "
        "account with no unallocated remainder")


def prior_returns_for(invoice):
    """Already-submitted returns of an invoice: quantities and credited value."""
    rows = frappe.db.get_all(
        INVOICE,
        filters={"return_against": invoice, "docstatus": 1, "is_return": 1},
        fields=["name"],
        limit_page_length=200,
    )
    quantities = []
    credited = 0.0
    for row in (rows or []):
        items = frappe.db.get_all(
            "Sales Invoice Item",
            filters={"parent": row["name"], "parenttype": INVOICE},
            fields=["item_code", "qty"],
            limit_page_length=200,
        )
        per_item = {}
        for item in (items or []):
            code = item["item_code"]
            per_item[code] = per_item.get(code, 0.0) + abs(_flt(item["qty"]))
        quantities.append(per_item)
        credited += abs(_flt(frappe.db.get_value(INVOICE, row["name"], "grand_total")))
    return quantities, credited


def book_return_permitted(doc, original):
    """Return shape check for a stock-book credit note.

    ``original`` is the source invoice's facts
    (``grand_total``, ``docstatus``, ``customer``, ``company``,
    ``update_stock``, ``th_placement_case``). Returns ``False`` when the
    return would restock more than was sold or credit more than was billed.
    """
    original_items = {}
    for row in (frappe.db.get_all(
            "Sales Invoice Item",
            filters={"parent": original.get("name"), "parenttype": INVOICE},
            fields=["item_code", "qty"],
            limit_page_length=200) or []):
        original_items[row["item_code"]] = \
            original_items.get(row["item_code"], 0.0) + abs(_flt(row["qty"]))
    current_items = {}
    for row in (doc.get("items") or []):
        code = row.get("item_code")
        qty = abs(_flt(row.get("qty")))
        if not code or qty <= 0:
            return False
        current_items[code] = current_items.get(code, 0.0) + qty
    prior, credited = prior_returns_for(original.get("name"))
    if not return_quantities_ok(original_items, prior, current_items):
        return False
    return return_value_ok(original.get("grand_total"), credited,
                           doc.get("grand_total") or 0)
