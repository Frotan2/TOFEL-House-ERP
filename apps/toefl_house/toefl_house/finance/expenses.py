"""Institute operating expenses on the native ERPNext Journal Entry.

Rent, utilities, supplies, maintenance and other running costs are recorded
as ONE submitted native ``Journal Entry`` per payment: the selected Expense
account is debited and the paying Cash or Bank account is credited. The
general ledger therefore stays the single financial authority; this module
keeps no second expense register, balance or category list. A "category" is
simply the native Expense account in the company's chart of accounts, which
the Course Owner maintains with the standard ERPNext accounts tree.

Controls (each enforced on the server, never in the browser):

* Recording is a Finance Officer command; voiding is a Finance Manager
  command performed by a DIFFERENT person than the recorder (separation of
  duties). Both run through the shared idempotent, audited command executor.
* Amounts are positive, at most two decimals, in the company currency.
* The paying account must be an active Cash or Bank account of the same
  company. A Reception counter drawer is refused: counter cash belongs to
  the receipt/handover cycle and must reach main Cash first.
* Cash may not go negative: the drawer's ledger balance must cover the
  payment on the posting date and today.
* Posting dates are never in the future, never older than the governing
  billing policy's backdate window (only today when no policy is active),
  and never on or before a business day the cashier has already closed when
  cash is involved, so a submitted cash close never drifts silently.
* Native Desk, REST, cancel, amend and delete routes cannot alter an
  expense journal; the void command cancels the native document and leaves
  the original and its reversal in the ledger history.
"""
from datetime import date as _date
from decimal import Decimal

import frappe

from toefl_house.api import _execute
from toefl_house.finance import collection_rules as rules
from toefl_house.finance.company_scope import require_finance_company
from toefl_house.policy import digest
from toefl_house.security import active_command_kind, record_synthetic_flag, require_operational

JOURNAL = "Journal Entry"
ACCOUNT = "Account"
CASHIER_DAY = "TH Cashier Day"
FIELDS = ("th_expense_recorder", "th_expense_synthetic")
COMMANDS = frozenset({"record_expense", "void_expense"})
PAYING_TYPES = ("Cash", "Bank")
OPTION_LIMIT = 200


def _text(value, label, maximum=140, minimum=1):
    if isinstance(value, str):
        # A multi-line description box may send line breaks or tabs; store
        # one clean line (other control characters are still refused).
        value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    try:
        clean = rules.bounded_text(value, label, maximum)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if len(clean) < minimum:
        raise frappe.ValidationError(f"Enter a longer {label}")
    return clean


def _optional_text(value, label, maximum=140):
    if value in (None, ""):
        return ""
    return _text(value, label, maximum)


def _money(value):
    try:
        return rules.money(value)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc).replace("cash amount", "amount")) from exc


def schema_ready():
    try:
        return all(frappe.db.has_column(JOURNAL, field) for field in FIELDS)
    except Exception:
        return False


def require_schema():
    if not schema_ready():
        raise frappe.ValidationError("Expense recording needs the supported application migration first")


def _company_currency(company):
    return frappe.get_cached_value("Company", company, "default_currency")


def category_account(name, company):
    """Return the active, postable Expense account or refuse."""
    doc = frappe.db.get_value(ACCOUNT, name, ["name", "company", "root_type", "is_group", "disabled",
                                              "account_currency", "account_name"], as_dict=True)
    currency = _company_currency(company)
    if (not doc or doc.company != company or doc.root_type != "Expense" or int(doc.is_group or 0)
            or int(doc.disabled or 0) or (doc.account_currency or currency) != currency):
        raise frappe.ValidationError(
            "Choose an active expense category (Expense account) of the same company and currency")
    return doc


def _reception_counters(company):
    rows = frappe.get_all("User Permission", filters={"allow": ACCOUNT}, fields=["user", "for_value"],
                          limit_page_length=1001)
    if len(rows) > 1000:
        raise frappe.ValidationError("The Owner must resolve the counter assignments before expenses are paid")
    counters = set()
    for row in rows:
        if "Reception" in frappe.get_roles(row.get("user")):
            counters.add(row.get("for_value"))
    return counters


def paying_account(name, company):
    """Return the active Cash/Bank account that pays the expense or refuse."""
    doc = frappe.db.get_value(ACCOUNT, name, ["name", "company", "root_type", "account_type", "is_group",
                                              "disabled", "account_currency", "account_name"], as_dict=True)
    currency = _company_currency(company)
    if (not doc or doc.company != company or doc.root_type != "Asset" or doc.account_type not in PAYING_TYPES
            or int(doc.is_group or 0) or int(doc.disabled or 0)
            or (doc.account_currency or currency) != currency):
        raise frappe.ValidationError(
            "Pay from an active Cash or Bank account of the same company and currency")
    if doc.name in _reception_counters(company):
        raise frappe.ValidationError(
            "A Reception counter drawer cannot pay expenses. Accept the cash handover into main Cash first")
    return doc


def _posting_date(value, today):
    try:
        posted = _date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise frappe.ValidationError("Enter the payment date as a valid date") from None
    now = _date.fromisoformat(str(today))
    if posted > now:
        raise frappe.ValidationError("An expense cannot be dated in the future")
    from toefl_house.finance import policies as billing_policies
    terms = billing_policies.governing_billing_terms()
    window = int(terms["max_backdate_days"]) if terms and terms.get("max_backdate_days") is not None else 0
    if (now - posted).days > window:
        raise frappe.ValidationError(
            "This date is older than the billing policy allows. Record the expense with a recent date"
            if window else "With no active billing policy, expenses can only be recorded with today's date")
    return posted.isoformat()


def _refuse_closed_cash_day(company, posted):
    closed = frappe.get_all(CASHIER_DAY, filters={"company": company, "docstatus": 1, "date": (">=", posted)},
                            fields=["name", "date"], order_by="date desc", limit_page_length=1)
    if closed:
        raise frappe.ValidationError(
            f"The cash day {closed[0]['date']} is already closed. Record this cash expense with a later date")


def _cash_balance(account, company, on):
    row = frappe.db.sql("""select coalesce(sum(debit - credit), 0) from `tabGL Entry`
                           where account=%s and company=%s and is_cancelled=0 and posting_date<=%s""",
                        (account, company, on))
    return Decimal(str((row and row[0][0]) or 0))


def _require_cash_cover(account, company, posted, amount, today):
    from toefl_house.finance.tuition_refund_native import lock_cash_accounts
    lock_cash_accounts([account])
    for on in sorted({posted, str(today)}):
        if _cash_balance(account, company, on) < amount:
            raise frappe.ValidationError(
                "The cash drawer's recorded balance does not cover this payment. Check the drawer or pay by bank")


def _cost_center(company):
    center = frappe.get_cached_value("Company", company, "cost_center")
    if not center:
        raise frappe.ValidationError("Ask the Course Owner to set the company's default cost center first")
    return center


def expense_facts(doc):
    rows = doc.get("accounts") or []
    debit = next((row for row in rows if float(row.get("debit_in_account_currency") or 0) > 0), None)
    credit = next((row for row in rows if float(row.get("credit_in_account_currency") or 0) > 0), None)
    return dict(journal_entry=doc.name, company=doc.company, date=str(doc.posting_date),
                expense_account=debit.get("account") if debit else "",
                paid_from=credit.get("account") if credit else "",
                amount=float(doc.total_debit or 0), currency=_company_currency(doc.company),
                payee=doc.pay_to_recd_from or "", description=doc.user_remark or "",
                reference=doc.cheque_no or doc.bill_no or "", recorded_by=doc.th_expense_recorder,
                status="Void" if int(doc.docstatus) == 2 else "Posted",
                synthetic=bool(doc.get("th_expense_synthetic")))


@frappe.whitelist(methods=["POST"])
def record_expense(request_key, company, posting_date, expense_account, paid_from, amount,
                   payee, description, reference=None):
    """Record one paid institute expense as a submitted native Journal Entry."""
    payload = dict(company=company, posting_date=posting_date, expense_account=expense_account,
                   paid_from=paid_from, amount=amount, payee=payee, description=description,
                   reference=reference or "")

    def work(actor):
        require_schema()
        clean_company = require_finance_company(_text(company, "company"))
        value = _money(amount)
        clean_payee = _text(payee, "paid to (person or business)", 140, minimum=2)
        clean_description = _text(description, "description", 300, minimum=3)
        clean_reference = _optional_text(reference, "reference number")
        today = frappe.utils.today()
        posted = _posting_date(posting_date, today)
        category = category_account(_text(expense_account, "expense category"), clean_company)
        source = paying_account(_text(paid_from, "paying account"), clean_company)
        is_cash = source.account_type == "Cash"
        if not is_cash and not clean_reference:
            raise frappe.ValidationError("A bank payment needs the bank transfer or cheque reference number")
        if is_cash:
            _refuse_closed_cash_day(clean_company, posted)
            _require_cash_cover(source.name, clean_company, posted, value, today)
        center = _cost_center(clean_company)
        doc = frappe.get_doc(dict(
            doctype=JOURNAL, voucher_type="Cash Entry" if is_cash else "Bank Entry",
            company=clean_company, posting_date=posted,
            user_remark=clean_description, pay_to_recd_from=clean_payee,
            cheque_no=clean_reference or None, cheque_date=posted if clean_reference else None,
            th_expense_recorder=actor, th_expense_synthetic=record_synthetic_flag(),
            accounts=[
                dict(account=category.name, debit_in_account_currency=float(value),
                     credit_in_account_currency=0, cost_center=center),
                dict(account=source.name, debit_in_account_currency=0,
                     credit_in_account_currency=float(value), cost_center=center),
            ]))
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        doc.flags.ignore_permissions = True
        doc.submit()
        posted_row = frappe.db.get_value(JOURNAL, doc.name, ["docstatus", "total_debit", "total_credit", "company"],
                                         as_dict=True)
        if (not posted_row or int(posted_row.docstatus) != 1 or posted_row.company != clean_company
                or Decimal(str(posted_row.total_debit)) != value or Decimal(str(posted_row.total_credit)) != value):
            raise frappe.ValidationError("The native expense journal did not post exactly; nothing was recorded")
        result = expense_facts(doc)
        result["expense_category"] = category.account_name or category.name
        return result, dict(target=doc.name, after_hash=digest(result))

    return _execute("record_expense", request_key, payload, work)


def _owned_expense(name):
    doc = frappe.get_doc(JOURNAL, _text(name, "expense journal"), for_update=True)
    if (int(doc.docstatus) != 1 or not doc.get("th_expense_recorder")
            or bool(doc.get("th_expense_synthetic")) != bool(record_synthetic_flag())):
        raise frappe.ValidationError("Select a posted expense that has not been voided")
    return doc


@frappe.whitelist(methods=["POST"])
def void_expense(request_key, journal_entry, reason):
    """Cancel a mistaken expense journal; a different Finance Manager approves."""
    def work(actor):
        require_schema()
        explanation = _text(reason, "void reason", 300, minimum=5)
        doc = _owned_expense(journal_entry)
        require_finance_company(doc.company)
        if doc.th_expense_recorder == actor:
            raise frappe.PermissionError("Another Finance Manager must void an expense you recorded yourself")
        credit_accounts = [row.account for row in doc.accounts if float(row.credit_in_account_currency or 0) > 0]
        cash = [name for name in credit_accounts
                if frappe.db.get_value(ACCOUNT, name, "account_type") == "Cash"]
        if cash:
            _refuse_closed_cash_day(doc.company, str(doc.posting_date))
        before = expense_facts(doc)
        doc.flags.ignore_permissions = True
        doc.cancel()
        doc.add_comment("Comment", "Expense voided by " + actor + ": " + explanation)
        if int(frappe.db.get_value(JOURNAL, doc.name, "docstatus")) != 2:
            raise frappe.ValidationError("The native expense journal could not be voided")
        result = dict(before, status="Void", voided_by=actor, reason=explanation)
        return result, dict(target=doc.name, before_hash=digest(before), after_hash=digest(result))

    return _execute("void_expense", request_key, dict(journal_entry=journal_entry, reason=reason), work)


@frappe.whitelist(methods=["GET"])
def expense_options(company=None):
    """Choices for the guided expense form: companies, categories, paying accounts.

    A bounded, role-gated projection of account NAMES only; balances and
    ledger rows never leave the server here.
    """
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if (user in (None, "Guest", "Administrator") or not frappe.db.get_value("User", user, "enabled")
            or not roles & {"Finance Officer", "Finance Manager"}):
        raise frappe.PermissionError("A Finance staff account is required")
    permitted = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"},
                               pluck="for_value", limit_page_length=100)
    companies = sorted(permitted) if permitted else frappe.get_all(
        "Company", pluck="name", order_by="name asc", limit_page_length=50)
    if company:
        if company not in companies:
            raise frappe.PermissionError("This login has no finance authority for the selected company")
        companies = [company]
    out = []
    for name in companies[:50]:
        currency = _company_currency(name)
        categories = frappe.get_all(ACCOUNT, filters={"company": name, "root_type": "Expense", "is_group": 0,
                                                      "disabled": 0},
                                    fields=["name", "account_name", "account_currency"], order_by="account_name asc",
                                    limit_page_length=OPTION_LIMIT)
        sources = frappe.get_all(ACCOUNT, filters={"company": name, "root_type": "Asset", "is_group": 0,
                                                   "disabled": 0, "account_type": ("in", PAYING_TYPES)},
                                 fields=["name", "account_name", "account_type", "account_currency"],
                                 order_by="account_type desc, account_name asc", limit_page_length=OPTION_LIMIT)
        counters = _reception_counters(name)
        out.append(dict(
            company=name, currency=currency,
            categories=[row["name"] for row in categories if (row.get("account_currency") or currency) == currency],
            paying_accounts=[dict(name=row["name"], kind=row["account_type"]) for row in sources
                             if row["name"] not in counters
                             and (row.get("account_currency") or currency) == currency]))
    return dict(companies=out, today=frappe.utils.today())


def guard_expense_journal(doc, method=None):
    """Native-route containment for expense journals (Desk, REST, cancel, amend, delete)."""
    recorded = doc.get("th_expense_recorder")
    previous = None
    if not recorded and not doc.is_new() and method in ("before_validate", "validate", "on_trash"):
        previous = frappe.db.get_value(JOURNAL, doc.name, "th_expense_recorder")
    if not (recorded or previous or doc.get("amended_from") and frappe.db.get_value(
            JOURNAL, doc.get("amended_from"), "th_expense_recorder")):
        return
    require_operational()
    kind = active_command_kind()
    if method == "before_cancel" and kind == "void_expense":
        return
    # The record command inserts and immediately submits its own journal;
    # both run before_validate/validate. It writes no other journal, and
    # Frappe names a new document before validate, so is_new() is not used.
    if method in ("before_validate", "validate") and kind == "record_expense":
        return
    raise frappe.PermissionError(
        "Institute expenses are recorded and voided only from the Finance Desk expense actions")


# ---------------------------------------------------------------------------
# Read-only month position for the Finance Desk and the Owner Cockpit.
# ---------------------------------------------------------------------------
COMPANY_LIMIT = 50


def month_period(day=None):
    """The Solar Hijri month containing ``day``: (key, label, start, end-so-far)."""
    from toefl_house.finance import shamsi

    day = str(day or frappe.utils.today())
    key = shamsi.month_key(day)
    start, _ = shamsi.month_bounds(key)
    return key, shamsi.solar_month_label(key), start.isoformat(), day


def viewer_companies():
    """The viewer's Company User Permissions, or every company (bounded) when unscoped."""
    permitted = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Company"},
                               pluck="for_value", limit_page_length=100)
    if permitted:
        return sorted(set(permitted))[:COMPANY_LIMIT]
    return frappe.get_all("Company", pluck="name", order_by="name asc", limit_page_length=COMPANY_LIMIT)


def month_position(day=None):
    """Income, expenses and net for the current Solar Hijri month, per company.

    Straight from the native general ledger grouped by Account ``root_type``:
    Income = credit - debit on Income accounts; Expenses = debit - credit on
    Expense accounts; Net = Income - Expenses. Cancelled ledger rows and
    opening entries are excluded. Amounts are in each company's currency and
    different companies are never added together.
    """
    _, label, start, end = month_period(day)
    companies = viewer_companies()
    if not companies:
        return []
    rows = frappe.db.sql(
        """select gle.company, acc.root_type,
                  coalesce(sum(gle.debit), 0) as debit, coalesce(sum(gle.credit), 0) as credit
             from `tabGL Entry` gle
             join `tabAccount` acc on acc.name = gle.account
            where gle.is_cancelled = 0 and gle.is_opening = 'No'
              and gle.posting_date between %s and %s
              and gle.company in %s and acc.root_type in ('Income', 'Expense')
            group by gle.company, acc.root_type""",
        (start, end, tuple(companies)), as_dict=True)
    totals = {}
    for row in rows:
        entry = totals.setdefault(row.get("company"), {"income": Decimal("0"), "expense": Decimal("0")})
        debit, credit = Decimal(str(row.get("debit") or 0)), Decimal(str(row.get("credit") or 0))
        if row.get("root_type") == "Income":
            entry["income"] += credit - debit
        else:
            entry["expense"] += debit - credit
    out = []
    for company in companies:
        if company not in totals:
            continue
        income = totals[company]["income"].quantize(Decimal("0.01"))
        expense = totals[company]["expense"].quantize(Decimal("0.01"))
        out.append(dict(company=company, currency=_company_currency(company) or "", income=float(income),
                        expense=float(expense), net=float(income - expense), period=label, start=start, end=end))
    return out
