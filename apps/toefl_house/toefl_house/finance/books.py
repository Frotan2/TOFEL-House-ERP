"""Book commerce integrity over native ERPNext stock and accounts.

Native records stay the only authorities: ``Item``/``Item Group Books`` is
the catalog, ``Item Price`` in the invoice's selling price list is the
selling price, ``Bin``/``Stock Ledger Entry`` are stock truth, and native
``Sales Invoice``/``Payment Entry``/``Stock Entry`` documents post every
movement. Nothing here computes a price, a valuation or a balance; the
checks below only refuse book documents whose shape contradicts those
native facts:

* a new book sale must be priced at the configured native selling price
  (a lower rate is allowed only when a native Pricing Rule produced it),
  may not carry a hand-typed document discount, and may not sell more
  than the warehouse bin holds — the free-typed rate and the negative
  bin are refused before native posting;
* a stock receipt of books must carry a positive valuation rate, and a
  book stock issue/correction (Material Issue, Stock Reconciliation) is
  an approved adjustment: Stock Manager or Finance Manager only, with a
  stated reason;
* Company and Warehouse User Permissions bind every book document the
  same way they bind guarded finance commands (PR #90);
* items in ``Books`` *or any program sub-group the owner nests below
  it* are books.

Reversal paths (cancel, post-submit edits) deliberately skip the
price/stock-cover checks: changing today's price list must never make
yesterday's legitimate sale uncancellable.
"""
import math

import frappe

BOOKS_GROUP = "Books"
PRICE_TOLERANCE = 0.01  # per-unit currency rounding, never a discount
QUANTITY_TOLERANCE = 0.0000005  # native stock quantities keep six decimals
ADJUSTMENT_ROLES = ("Stock Manager", "Finance Manager")


def _flt(value):
    try:
        return round(float(value or 0), 6)
    except (TypeError, ValueError):
        return float("nan")


def _row_value(row, key):
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _has_pricing_rule(row):
    value = _row_value(row, "pricing_rules")
    if not value:
        return False
    if isinstance(value, (list, tuple)):
        return bool(value)
    return str(value).strip() not in ("", "[]", "null", "None")


# --- Pure price / stock / reconciliation rules --------------------------

def choose_item_price(rows, qty, on_date=None):
    """Deterministically pick the configured native price for a quantity.

    ``rows`` are Item Price facts for one item, price list and currency
    (``price_list_rate``, ``min_qty``, ``customer``, ``valid_from``,
    ``valid_upto``). Customer-specific rows beat generic ones, then the
    highest satisfied quantity slab wins. Returns ``None`` when no valid
    positive price is configured — book sales then fail closed.
    """
    quantity = _flt(qty)
    if not math.isfinite(quantity) or quantity <= 0:
        return None
    day = str(on_date) if on_date else None
    candidates = []
    for row in rows or []:
        rate = _flt(_row_value(row, "price_list_rate"))
        if not math.isfinite(rate) or rate <= 0:
            continue
        minimum = _flt(_row_value(row, "min_qty"))
        if not math.isfinite(minimum) or minimum < 0:
            continue
        if day:
            starts = _row_value(row, "valid_from")
            ends = _row_value(row, "valid_upto")
            if starts and str(starts) > day:
                continue
            if ends and str(ends) < day:
                continue
        candidates.append((bool(_row_value(row, "customer")), minimum, rate))
    satisfied = [c for c in candidates if c[1] <= quantity]
    if not satisfied:
        return None
    # Customer-specific first, then the deepest satisfied slab, then the
    # lowest rate inside it (native quantity slabs price down, not up).
    satisfied.sort(key=lambda c: (c[0], c[1], -c[2]))
    return satisfied[-1][2]


def sale_prices_ok(lines, prices):
    """Every sale line is billed at its configured native selling price.

    ``lines`` expose ``item_code``, ``qty``, ``rate``, ``pricing_rules``
    and optionally ``conversion_factor``; ``prices`` maps item codes to
    the configured rate (or ``None``). Equality is required, except that
    a native Pricing Rule may legitimately price *below* the list rate.
    """
    if not lines:
        return False
    for row in lines:
        code = _row_value(row, "item_code")
        qty = _flt(_row_value(row, "qty"))
        rate = _flt(_row_value(row, "rate"))
        factor = _row_value(row, "conversion_factor")
        factor = 1.0 if factor in (None, "") else _flt(factor)
        if (not code or not math.isfinite(qty) or qty <= 0
                or not math.isfinite(rate) or rate <= 0
                or not math.isfinite(factor) or abs(factor - 1.0) > 1e-9):
            return False
        configured = (prices or {}).get(code)
        if configured is None:
            return False
        configured = _flt(configured)
        if not math.isfinite(configured) or configured <= 0:
            return False
        if rate - configured > PRICE_TOLERANCE:
            return False  # never above the configured price
        if configured - rate > PRICE_TOLERANCE and not _has_pricing_rule(row):
            return False  # below list only via a native Pricing Rule
    return True


def stock_cover_ok(available, requested):
    """Requested quantities never exceed what each warehouse bin holds.

    Both maps are keyed by ``(item_code, warehouse)``. This is the
    pre-posting half of native negative-stock protection: it refuses an
    oversell on save even on sites whose Stock Settings still allow
    negative stock for other inventory.
    """
    if not requested:
        return False
    for key, qty in requested.items():
        wanted = _flt(qty)
        held = _flt((available or {}).get(key, 0.0))
        if not math.isfinite(wanted) or wanted <= 0 or not math.isfinite(held):
            return False
        if wanted - held > QUANTITY_TOLERANCE:
            return False
    return True


def reconcile_book_stock(bins, ledger_rows):
    """Compare the Bin projection against Stock Ledger Entry truth.

    ``bins`` expose ``item_code``, ``warehouse``, ``actual_qty`` and
    ``stock_value``; ``ledger_rows`` are the non-cancelled native ledger
    rows (``actual_qty``, ``stock_value_difference``). Returns a
    deterministic report; ``ok`` is true only when every bin equals the
    sum of its ledger rows in both quantity and value.
    """
    ledger = {}
    sound = True
    for row in ledger_rows or []:
        key = (_row_value(row, "item_code"), _row_value(row, "warehouse"))
        qty = _flt(_row_value(row, "actual_qty"))
        value = _flt(_row_value(row, "stock_value_difference"))
        if not key[0] or not key[1] or not math.isfinite(qty) \
                or not math.isfinite(value):
            sound = False
            continue
        held_qty, held_value = ledger.get(key, (0.0, 0.0))
        ledger[key] = (held_qty + qty, held_value + value)
    discrepancies = []
    seen = set()
    total_qty = 0.0
    total_value = 0.0
    for row in bins or []:
        key = (_row_value(row, "item_code"), _row_value(row, "warehouse"))
        bin_qty = _flt(_row_value(row, "actual_qty"))
        bin_value = _flt(_row_value(row, "stock_value"))
        seen.add(key)
        if not key[0] or not key[1] or not math.isfinite(bin_qty) \
                or not math.isfinite(bin_value):
            sound = False
            continue
        total_qty += bin_qty
        total_value += bin_value
        led_qty, led_value = ledger.get(key, (0.0, 0.0))
        if abs(bin_qty - led_qty) > 0.000001 or abs(bin_value - led_value) > 0.01:
            discrepancies.append({
                "item_code": key[0], "warehouse": key[1],
                "bin_qty": bin_qty, "ledger_qty": round(led_qty, 6),
                "qty_difference": round(bin_qty - led_qty, 6),
                "bin_value": bin_value, "ledger_value": round(led_value, 6),
                "value_difference": round(bin_value - led_value, 6),
            })
    for key, (led_qty, led_value) in ledger.items():
        if key not in seen and (abs(led_qty) > 0.000001 or abs(led_value) > 0.01):
            discrepancies.append({
                "item_code": key[0], "warehouse": key[1],
                "bin_qty": 0.0, "ledger_qty": round(led_qty, 6),
                "qty_difference": round(-led_qty, 6),
                "bin_value": 0.0, "ledger_value": round(led_value, 6),
                "value_difference": round(-led_value, 6),
            })
    discrepancies.sort(key=lambda d: (str(d["item_code"]), str(d["warehouse"])))
    return {
        "ok": sound and not discrepancies,
        "checked_bins": len(seen),
        "total_qty": round(total_qty, 6),
        "total_value": round(total_value, 6),
        "discrepancies": discrepancies,
    }


# --- Site seams ----------------------------------------------------------

def _as_dict(row):
    return dict(row) if row else {}


def book_item_group_ok(item_group):
    """ ``Books`` itself or any program sub-group nested below it."""
    if not item_group:
        return False
    if item_group == BOOKS_GROUP:
        return True
    books = _as_dict(frappe.db.get_value(
        "Item Group", BOOKS_GROUP, ["lft", "rgt"], as_dict=True))
    group = _as_dict(frappe.db.get_value(
        "Item Group", item_group, ["lft", "rgt"], as_dict=True))
    try:
        return bool(books and group
                    and int(books["lft"]) < int(group["lft"])
                    and int(group["rgt"]) < int(books["rgt"]))
    except (KeyError, TypeError, ValueError):
        return False


def user_value_permitted(user, allow, value):
    """Native User Permission semantics for one linked value.

    A user with no User Permission rows for ``allow`` is unrestricted
    (the HQ pattern PR #90 kept for Company); a scoped user may act only
    on the explicitly allowed values.
    """
    if not user or not value:
        return False
    rows = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": allow},
        fields=["for_value"],
        limit_page_length=1000,
    ) or []
    if not rows:
        return True
    allowed = {_row_value(row, "for_value") for row in rows}
    return value in allowed


def configured_selling_price(item_code, price_list, currency, customer,
                             qty, on_date):
    # Field list is pinned-schema exact (erpnext 4048fb70 Item Price has
    # no min_qty column; quantity slabs are a later-version concept, so
    # choose_item_price simply sees no slab dimension on this stack).
    rows = frappe.db.get_all(
        "Item Price",
        filters={"item_code": item_code, "price_list": price_list,
                 "selling": 1, "currency": currency},
        fields=["price_list_rate", "customer", "uom",
                "valid_from", "valid_upto"],
        limit_page_length=200,
    ) or []
    # Books bill in their stock unit at conversion factor 1 (enforced in
    # sale_prices_ok), so only stock-unit prices can price a book line.
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    rows = [dict(row) for row in rows
            if (not row.get("customer") or row.get("customer") == customer)
            and (not row.get("uom") or row.get("uom") == stock_uom)]
    return choose_item_price(rows, qty, on_date)


def book_sale_terms_ok(doc):
    """Price authority + stock cover for a *new* book sale invoice."""
    price_list = getattr(doc, "selling_price_list", None)
    currency = getattr(doc, "currency", None)
    customer = getattr(doc, "customer", None)
    items = getattr(doc, "items", None) or []
    if not price_list or not currency or not customer or not items:
        return False
    # A hand-typed document-level discount reprices every line away from
    # the configured prices; discounts belong to native Pricing Rules.
    manual_discount = (
        abs(_flt(getattr(doc, "discount_amount", 0))) > 0.005
        or abs(_flt(getattr(doc, "additional_discount_percentage", 0))) > 1e-9)
    if manual_discount and not any(_has_pricing_rule(row) for row in items):
        return False
    on_date = getattr(doc, "posting_date", None)
    lines, prices, requested, available = [], {}, {}, {}
    for row in items:
        code = getattr(row, "item_code", None)
        warehouse = getattr(row, "warehouse", None)
        qty = _flt(getattr(row, "qty", None))
        if not code or not warehouse:
            return False
        prices[code] = configured_selling_price(
            code, price_list, currency, customer, qty, on_date)
        lines.append({
            "item_code": code, "qty": qty,
            "rate": getattr(row, "rate", None),
            "pricing_rules": getattr(row, "pricing_rules", None),
            "conversion_factor": getattr(row, "conversion_factor", None),
        })
        key = (code, warehouse)
        requested[key] = requested.get(key, 0.0) + qty
        if key not in available:
            available[key] = frappe.db.get_value(
                "Bin", {"item_code": code, "warehouse": warehouse},
                "actual_qty") or 0.0
    return sale_prices_ok(lines, prices) and stock_cover_ok(available, requested)


# --- Native stock document guards ---------------------------------------

def _book_stock_rows(doc):
    """Child rows of a native stock document whose item is a book."""
    found = []
    for row in (getattr(doc, "items", None) or []):
        code = getattr(row, "item_code", None)
        if not code:
            continue
        item = _as_dict(frappe.db.get_value(
            "Item", code, ["item_group", "is_stock_item"], as_dict=True))
        if item and int(item.get("is_stock_item") or 0) == 1 \
                and book_item_group_ok(item.get("item_group")):
            found.append(row)
    return found


def _require_adjustment_authority(doc, label, reason_fields=("remarks",)):
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.ValidationError(f"{label} requires an authorized login")
    if user != "Administrator" and not set(
            frappe.get_roles(user)).intersection(ADJUSTMENT_ROLES):
        raise frappe.ValidationError(
            f"{label} of book stock is an approved adjustment: it requires "
            "a Stock Manager or Finance Manager")
    reason = ""
    for field in reason_fields:
        value = getattr(doc, field, None)
        if isinstance(value, str) and value.strip():
            reason = value.strip()
            break
    if not reason:
        raise frappe.ValidationError(
            f"{label} of book stock requires a stated reason")
    company = getattr(doc, "company", None)
    if company and not user_value_permitted(user, "Company", company):
        raise frappe.ValidationError(
            "This login has no stock authority for the document company")


def guard_stock_entry(doc, method=None):
    """Book receipts need real valuation; book issues are approved.

    Non-book stock entries pass untouched. A books-only Material Receipt
    at a zero/blank rate would poison native moving-average valuation
    and understate the stock GL; a Material Issue silently writes stock
    off. Both shapes are refused here, before any native posting.
    """
    from toefl_house.security import require_operational
    require_operational()
    rows = _book_stock_rows(doc)
    if not rows:
        return
    user = frappe.session.user
    company = getattr(doc, "company", None)
    if not user or user == "Guest" or (company and not
                                       user_value_permitted(user, "Company", company)):
        raise frappe.ValidationError(
            "This login has no book-stock authority for the document company")
    is_issue = False
    for row in rows:
        source = getattr(row, "s_warehouse", None)
        target = getattr(row, "t_warehouse", None)
        if target and not source:
            rate = _flt(getattr(row, "basic_rate", None))
            if not math.isfinite(rate) or rate <= 0:
                raise frappe.ValidationError(
                    "Receiving book stock requires the positive purchase "
                    "cost per book (Basic Rate); zero-value receipts are "
                    "refused so inventory valuation stays truthful")
        if source and not target:
            is_issue = True
    if is_issue:
        _require_adjustment_authority(doc, "Issuing book stock without a sale")


def guard_stock_reconciliation(doc, method=None):
    """A physical-count correction of books is an approved adjustment."""
    from toefl_house.security import require_operational
    require_operational()
    if not _book_stock_rows(doc):
        return
    # Stock Reconciliation has no Remarks field in the pinned schema; its
    # native Purpose is the stated reason there.
    _require_adjustment_authority(
        doc, "Correcting counted book stock",
        reason_fields=("remarks", "purpose"))
