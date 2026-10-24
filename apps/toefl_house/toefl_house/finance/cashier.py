"""Cashier day close: native ledger truth vs. physically counted cash.

The cashier workflow this module supports, end to end:

1. the drawer's **expected** amount is the native general-ledger closing
   balance of the company's Cash/Bank accounts at the end of the business day
   — never a number a cashier types and never an owned running total;
2. the cashier **counts** the physical money and records it;
3. the difference is the variance, and any non-zero variance requires the
   cashier's written explanation;
4. the close is a submitted, immutable control record; it posts nothing. Real
   money movements stay native ``Payment Entry`` documents, so the general
   ledger remains the single source of truth and period-correct history is
   never rewritten.

Two further controls live here:

- **One close per company per business day.** A second close cannot re-state
  the same day; the first submitted record stands and a correction is a
  documented management action, not a silent overwrite.
- **Drift detection.** If an accounting posting lands on or before a closed
  day *after* the close was taken, the close is reported as drifted so the
  cashier knows the drawer figures no longer match the ledger.

The closing window (how far back a day may still be closed) is the governing
billing policy's ``max_backdate_days`` — the owner's existing bound, reused
rather than a second invented limit. No active policy means no closes.
"""
# The command's public parameter is named ``date`` (the desk field), so the
# class is imported under an alias: inside ``reconcile_cashier_day`` the
# name ``date`` is the argument, and ``date.fromisoformat`` would be an
# AttributeError on the string (caught only by the native run, 2026-10-24).
from datetime import date as _date
import frappe

from toefl_house.api import _execute
from toefl_house.finance import policies as billing_policies
from toefl_house.policy import digest
from toefl_house.security import (finance_command_active,
                                  record_synthetic_flag, require_operational)

DAY = "TH Cashier Day"
DAY_SERIES = "TH-CASH-.YYYY.-"
COUNT = "TH Cashier Count"
GL = "GL Entry"
ACCOUNT = "Account"
COMPANY = "Company"
CASH_TYPES = ("Cash", "Bank")
MAX_DRAWERS = 25
TOLERANCE = 0.005
MAX_HISTORY = 25


def assert_command_context():
    """Refuse a cashier close raised outside its guarded finance command."""
    require_operational()
    if finance_command_active(DAY):
        return
    raise frappe.PermissionError(
        "A cashier day close is recorded only through the guarded finance "
        "command, so every close keeps its actor, receipt and audit trail")


def _counted(value, what):
    """Cashier-entered amount with a business-language refusal."""
    try:
        return _money(value, what)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _money(value, what):
    if isinstance(value, bool):
        raise ValueError(f"{what} must be an amount")
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be an amount") from exc
    if amount < 0:
        raise ValueError(f"{what} cannot be negative")
    return amount


def cash_drawers(company):
    """The company's postable native Cash and Bank accounts."""
    rows = frappe.db.get_all(
        ACCOUNT,
        filters={"company": company, "is_group": 0, "disabled": 0,
                 "account_type": ["in", list(CASH_TYPES)]},
        fields=["name", "account_type"],
        order_by="name asc",
        limit_page_length=200,
    )
    return [dict(row) for row in (rows or [])]


def drawer_balances(company, accounts, day):
    """Opening, movement and closing per drawer, straight from the ledger.

    ``opening`` is the ledger balance strictly before ``day``, ``movement``
    is the day's net movement, ``closing`` is the balance at end of day.
    Cancelled entries are excluded by the native ``is_cancelled`` flag.
    """
    out = []
    for account in accounts:
        row = frappe.db.sql(
            """select
                 coalesce(sum(case when posting_date < %s
                                   then debit - credit else 0 end), 0) as opening,
                 coalesce(sum(case when posting_date = %s
                                   then debit - credit else 0 end), 0) as movement,
                 coalesce(sum(case when posting_date <= %s
                                   then debit - credit else 0 end), 0) as closing
               from `tabGL Entry`
               where account = %s and company = %s and is_cancelled = 0""",
            (day, day, day, account, company),
            as_dict=True,
        )
        values = (row or [{}])[0] or {}
        out.append({
            "account": account,
            "opening": round(float(values.get("opening") or 0), 2),
            "movement": round(float(values.get("movement") or 0), 2),
            "closing": round(float(values.get("closing") or 0), 2),
        })
    return out


def validate_close(doc):
    """Shape-consistency checks for a close (command + controller).

    The expected amounts and variances are the command's arithmetic; this
    function proves the stored document agrees with them, so a tampered row
    cannot pass as a legitimate close.
    """
    day = doc.get("date")
    company = doc.get("company")
    if not day or not company:
        raise frappe.ValidationError("A cashier close needs a business date and a company")
    if _date.fromisoformat(str(day)) > _date.fromisoformat(str(frappe.utils.today())):
        raise frappe.ValidationError("A cashier close cannot cover a future business day")
    rows = list(doc.get("accounts") or [])
    if not rows:
        raise frappe.ValidationError("A cashier close needs at least one drawer")
    if len(rows) > MAX_DRAWERS:
        raise frappe.ValidationError(
            f"A cashier close covers at most {MAX_DRAWERS} drawers")
    drawers = {row["name"]: row.get("account_type") for row in cash_drawers(company)}
    seen = set()
    total_expected = 0.0
    total_counted = 0.0
    for row in rows:
        account = row.get("account")
        if not account or account not in drawers:
            raise frappe.ValidationError(
                f"{account or 'A drawer'} is not a Cash or Bank account of {company}")
        if account in seen:
            raise frappe.ValidationError(f"{account} is counted twice in one close")
        seen.add(account)
        expected = round(float(row.get("expected_amount") or 0), 2)
        counted = _counted(row.get("counted_amount"), f"Counted amount for {account}")
        stored_variance = round(float(row.get("variance") or 0), 2)
        variance = round(counted - expected, 2)
        if abs(variance - stored_variance) > TOLERANCE:
            raise frappe.ValidationError(
                f"The variance recorded for {account} does not equal counted minus expected")
        if abs(variance) > TOLERANCE and not (row.get("note") or "").strip():
            raise frappe.ValidationError(
                f"Explain the {variance:.2f} variance for {account} before closing")
        total_expected += expected
        total_counted += counted
    if abs(round(float(doc.get("total_expected") or 0), 2) - round(total_expected, 2)) > TOLERANCE:
        raise frappe.ValidationError("The close total expected does not match its drawers")
    if abs(round(float(doc.get("total_counted") or 0), 2) - round(total_counted, 2)) > TOLERANCE:
        raise frappe.ValidationError("The close total counted does not match its drawers")
    if abs(round(float(doc.get("total_variance") or 0), 2)
           - round(total_counted - total_expected, 2)) > TOLERANCE:
        raise frappe.ValidationError("The close total variance does not match its drawers")


def guard(doc, method=None):
    """Document seam: command-only writes, then the close's own soundness."""
    assert_command_context()
    validate_close(doc)


def _closing_window(day):
    """The owner's backdate bound: the newest/oldest day a close may cover."""
    terms = billing_policies.governing_billing_terms()
    if not terms:
        raise frappe.ValidationError(
            "No active billing policy governs cash closes; the Course Owner "
            "must configure one first")
    today = _date.fromisoformat(str(frappe.utils.today()))
    posted = _date.fromisoformat(str(day))
    if posted > today:
        raise frappe.ValidationError("A cashier close cannot cover a future business day")
    if (today - posted).days > int(terms["max_backdate_days"]):
        raise frappe.ValidationError(
            "The business day is older than the billing policy's closing window")
    return terms


@frappe.whitelist(methods=["POST"])
def reconcile_cashier_day(request_key, company, date, counts):
    """Record one cashier day close against the native ledger.

    ``counts`` is a list of ``{account, counted_amount, note}``. The expected
    amount is computed here from the ledger; the caller cannot supply it.
    """
    def work(actor):
        day = str(date or "").strip()
        try:
            _date.fromisoformat(day)
        except ValueError as exc:
            raise frappe.ValidationError("A valid business date is required") from exc
        if not isinstance(company, str) or not company or len(company) > 140:
            raise frappe.ValidationError("A company is required")
        if not frappe.db.exists(COMPANY, company):
            raise frappe.ValidationError("Unknown company")
        if not isinstance(counts, list) or not counts:
            raise frappe.ValidationError("Record the counted amount for at least one drawer")
        if len(counts) > MAX_DRAWERS:
            raise frappe.ValidationError(
                f"A cashier close covers at most {MAX_DRAWERS} drawers")
        _closing_window(day)

        drawers = {row["name"]: row.get("account_type") for row in cash_drawers(company)}
        if not drawers:
            raise frappe.ValidationError(
                f"{company} has no Cash or Bank account to reconcile")
        prepared = {}
        for entry in counts:
            if not isinstance(entry, dict):
                raise frappe.ValidationError("Each drawer needs an account and a counted amount")
            account = entry.get("account")
            if not isinstance(account, str) or account not in drawers:
                raise frappe.ValidationError(
                    f"{account or 'A drawer'} is not a Cash or Bank account of {company}")
            if account in prepared:
                raise frappe.ValidationError(f"{account} is counted twice in one close")
            counted = _counted(entry.get("counted_amount"), f"Counted amount for {account}")
            note = entry.get("note") or ""
            if not isinstance(note, str) or len(note) > 500:
                raise frappe.ValidationError(f"Explanation for {account} is too long")
            prepared[account] = {"counted": counted, "note": note.strip()}

        # Serialize closes for the same company/day, then refuse a duplicate.
        existing = frappe.db.sql(
            """select name from `tabTH Cashier Day`
               where company = %s and `date` = %s and docstatus < 2
               for update""",
            (company, day),
        )
        if existing:
            raise frappe.ValidationError(
                "This business day is already closed for this company; a "
                "submitted close is never overwritten")

        balances = {row["account"]: row for row in
                    drawer_balances(company, sorted(prepared), day)}
        rows = []
        for account in sorted(prepared):
            expected = balances[account]["closing"]
            counted = prepared[account]["counted"]
            variance = round(counted - expected, 2)
            note = prepared[account]["note"]
            if abs(variance) > TOLERANCE and not note:
                raise frappe.ValidationError(
                    f"Explain the {variance:.2f} variance for {account} before closing")
            rows.append({
                "account": account,
                "account_type": drawers[account],
                "expected_amount": expected,
                "counted_amount": counted,
                "variance": variance,
                "note": note,
            })

        doc = frappe.get_doc(dict(
            doctype=DAY,
            naming_series=DAY_SERIES,
            date=day, company=company, cashier=actor,
            reconciled_on=frappe.utils.now_datetime(),
            total_expected=round(sum(row["expected_amount"] for row in rows), 2),
            total_counted=round(sum(row["counted_amount"] for row in rows), 2),
            total_variance=round(sum(row["variance"] for row in rows), 2),
            accounts=rows,
            synthetic=record_synthetic_flag(),
        ))
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        doc.flags.ignore_permissions = True
        doc.submit()
        stored = frappe.db.get_value(
            DAY, doc.name,
            ["docstatus", "total_expected", "total_counted", "total_variance"],
            as_dict=True)
        if int(stored.docstatus or 0) != 1:
            raise frappe.ValidationError("The cashier close must be submitted")
        result = {
            "cashier_day": doc.name, "company": company, "date": day,
            "cashier": actor,
            "total_expected": round(float(stored.total_expected), 2),
            "total_counted": round(float(stored.total_counted), 2),
            "total_variance": round(float(stored.total_variance), 2),
            "drawers": rows,
        }
        return result, dict(
            target=doc.name,
            after_hash=digest([company, day, actor,
                               [(row["account"], row["counted_amount"])
                                for row in rows]]))

    return _execute("reconcile_cashier_day", request_key,
                    {"company": company, "date": date, "counts": counts}, work)


def _resolve_companies(companies):
    """The companies to read: an explicit (already scoped) list, or all.

    Callers that serve a person must pass the native Company User Permission
    scope (the desk does); the default is the configuration/readiness use.
    """
    if companies is not None:
        return [name for name in companies if name]
    return [row.get("name") for row in
            (frappe.db.get_all(COMPANY, fields=["name"], limit_page_length=50) or [])]


def cashier_position(day=None, companies=None):
    """Read-only drawer position and close state, for the finance desk.

    Returns one row per native Cash/Bank account with opening/movement/closing
    and the day's close (if any), plus a drift flag when a close no longer
    matches the ledger. No writes, no owned arithmetic beyond addition.
    """
    day = str(day or frappe.utils.today())
    companies = _resolve_companies(companies)
    out = []
    for name in companies:
        drawers = cash_drawers(name)
        if not drawers:
            continue
        balances = drawer_balances(name, [row["name"] for row in drawers], day)
        closes = frappe.db.get_all(
            DAY,
            filters={"company": name, "date": day, "docstatus": 1},
            fields=["name", "total_expected", "total_counted", "total_variance",
                    "cashier", "reconciled_on"],
            order_by="creation desc",
            limit_page_length=1,
        )
        close = dict(closes[0]) if closes else None
        drift = False
        if close:
            # A posting dated on or before the closed day but created after
            # the close means the counted figures no longer match the books.
            drift = bool(frappe.db.sql(
                """select 1 from `tabGL Entry`
                   where company = %s and posting_date <= %s
                     and is_cancelled = 0 and creation > %s
                   limit 1""",
                (name, day, close["reconciled_on"]),
            ))
        out.append({
            "company": name,
            "date": day,
            "drawers": balances,
            "close": close,
            "drift": drift,
        })
    return out


def cashier_history(companies=None, limit=MAX_HISTORY):
    """Read-only close history, newest first (bounded)."""
    filters = {"docstatus": 1}
    resolved = _resolve_companies(companies)
    filters["company"] = ["in", resolved] if resolved else ["in", [""]]
    rows = frappe.db.get_all(
        DAY,
        filters=filters,
        fields=["name", "date", "company", "cashier", "total_expected",
                "total_counted", "total_variance", "reconciled_on"],
        order_by="date desc, creation desc",
        limit_page_length=min(int(limit), MAX_HISTORY),
    )
    return [dict(row) for row in (rows or [])]


def day_window_hint():
    """The closing window in plain language, for the desk's next-action text."""
    terms = billing_policies.governing_billing_terms()
    if not terms:
        return ""
    return f"{terms['max_backdate_days']} days"
