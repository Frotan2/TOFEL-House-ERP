"""Read-only Solar Hijri aging and month close over NATIVE ERPNext documents.

Not an accounting ledger, invoice issuer, payment allocator or revenue-
recognition engine. Callers supply submitted Education Fees and allocations
from submitted ERPNext Payment Entry References. Unallocated Payment Entries
(advances), bank movements, refunds and GL revenue have separate native
sources and must not be silently inferred from cash applied to Fees.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from toefl_house.finance.shamsi import month_bounds, month_key

_CENT = Decimal("0.01")


def amount(value):
    """Normalize native currency into exact two-decimal amounts."""
    try:
        money = Decimal(str(value))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("Invalid monetary amount") from exc
    if not money.is_finite():
        raise ValueError("Monetary amount must be finite")
    return money.quantize(_CENT, rounding=ROUND_HALF_UP)


def _iso(value, label):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def invoice_balances(fees, allocations, as_of):
    """Calculate as-of balances by referenced native documents only.

    `fees`: {name,posting_date,due_date,grand_total,docstatus}.
    `allocations`: {name,reference_name,posting_date,allocated_amount,
    docstatus}. Cancelled draft rows are excluded. Unknown references,
    duplicate native receipt-row identities and over-allocation are refused.
    This is a reconciliation *view*, not a mutation or cash receipt.
    """
    cutoff = _iso(as_of, "As-of date")
    bills = {}
    for raw in fees:
        if int(raw["docstatus"]) != 1 or _iso(raw["posting_date"], "Posting date") > cutoff:
            continue
        key = str(raw["name"])
        if not key or key in bills:
            raise ValueError("Duplicate or missing native Fees identity")
        total = amount(raw["grand_total"])
        if total < 0:
            raise ValueError("Negative Fees require a separate native credit-note view")
        bills[key] = {
            "name": key, "posting_date": _iso(raw["posting_date"], "Posting date"),
            "due_date": _iso(raw["due_date"], "Due date"),
            "total": total, "paid": Decimal("0.00"),
            "collections": {},
        }
    seen = set()
    for raw in allocations:
        if int(raw["docstatus"]) != 1 or _iso(raw["posting_date"], "Payment date") > cutoff:
            continue
        receipt_id = str(raw["name"])
        if not receipt_id or receipt_id in seen:
            raise ValueError("Duplicate or missing native payment-allocation identity")
        seen.add(receipt_id)
        ref = str(raw["reference_name"])
        if ref not in bills:
            raise ValueError("Payment references an unknown or not-yet-posted Fees invoice")
        paid = amount(raw["allocated_amount"])
        if paid < 0:
            raise ValueError("Refunds and negative allocations require a separate native correction")
        bills[ref]["paid"] += paid
        payment_month = month_key(_iso(raw["posting_date"], "Payment date"))
        collections = bills[ref]["collections"]
        collections[payment_month] = collections.get(payment_month, Decimal("0.00")) + paid
    for row in bills.values():
        if row["paid"] > row["total"]:
            raise ValueError(f"Over-allocation on native Fees {row['name']}")
        row["outstanding"] = row["total"] - row["paid"]
    return bills


def solar_month_receivables(fees, allocations, period):
    """Closing student arrears and cash allocations for one Shamsi month.

    `due_in_month` measures scheduled claims, NOT earned GL revenue.
    `posted_in_month` measures newly submitted invoice face values, NOT
    collections. `collections_in_month` measures allocated native cash,
    NOT all receipts (advances require their own native Payment Entry query).
    """
    start, end = month_bounds(period)
    rows = invoice_balances(fees, allocations, end)
    zero = Decimal("0.00")
    result = {
        "period": period, "from_date": str(start), "to_date": str(end),
        "posted_in_month": zero, "due_in_month": zero,
        "collections_in_month": zero, "overdue_as_of_month_end": zero,
        "future_due_outstanding": zero, "total_outstanding": zero,
        "unallocated_advances_included": False,
        "currency_source": "native_company_currency",
        "invoices": [],
    }
    for row in sorted(rows.values(), key=lambda r:(r["due_date"], r["name"])):
        due = row["due_date"]
        result["posted_in_month"] += row["total"] if start <= row["posting_date"] <= end else zero
        result["due_in_month"] += row["total"] if start <= due <= end else zero
        result["collections_in_month"] += row["collections"].get(period, zero)
        if due <= end:
            result["overdue_as_of_month_end"] += row["outstanding"]
        else:
            result["future_due_outstanding"] += row["outstanding"]
        result["total_outstanding"] += row["outstanding"]
        result["invoices"].append({
            "fees": row["name"], "due_period": month_key(due),
            "due_date": str(due), "total": row["total"],
            "allocated": row["paid"], "outstanding": row["outstanding"],
        })
    return result


def suggest_oldest_debt_allocation(open_invoices, receipt_amount):
    """Finance proposal only: oldest due first, never posts a Payment Entry.

    Caller must verify the student, company, currency, authorization and
    current native outstanding under a DB lock before submitting anything.
    Excess is returned as an unapplied *proposal*, not an invented payment.
    """
    remainder = amount(receipt_amount)
    if remainder <= 0:
        raise ValueError("Receipt amount must be positive")
    seen = set()
    choices = []
    for row in open_invoices:
        key = str(row["name"])
        if not key or key in seen:
            raise ValueError("Duplicate or missing native Fees identity")
        seen.add(key)
        due = _iso(row["due_date"], "Due date")
        owed = amount(row["outstanding_amount"])
        if owed < 0:
            raise ValueError("Native Fees outstanding cannot be negative")
        choices.append((due, key, owed))
    applied = []
    for _due, key, owed in sorted(choices):
        if remainder <= 0:
            break
        alloc = min(remainder, owed)
        if alloc:
            applied.append({"fees": key, "allocated_amount": alloc})
            remainder -= alloc
    return {"allocations": applied, "unapplied_proposed_advance": remainder}
