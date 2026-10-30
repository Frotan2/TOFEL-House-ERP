"""Native paired tuition credit/payout, with exact in-process write authority.

This is server-only accounting infrastructure. No function is whitelisted.
The public command must use execute_atomic so any failure removes both native
documents, the request transition, operation receipt and audit event together.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

import frappe

from toefl_house.finance import tuition_refunds as rules
from toefl_house.finance.company_scope import require_finance_company
from toefl_house.security import active_command_kind, require_command, require_operational, site_mode, SYNTHETIC

REQUEST = "TH Tuition Refund Request"
_PAIR = ContextVar("th_exact_native_refund_pair", default=None)
_FINANCIAL_FIELDS = ("paid_amount", "received_amount", "paid_from", "paid_to", "company", "party_type", "party",
                 "payment_type", "paid_from_account_currency", "paid_to_account_currency",
                 "source_exchange_rate", "target_exchange_rate", "posting_date")


def money(value):
    if isinstance(value, bool):
        raise frappe.ValidationError("Invalid native accounting amount")
    try:
        amount = Decimal(str(value or 0))
        if (not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99")
                or amount != amount.quantize(Decimal("0.01"))):
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise frappe.ValidationError("Invalid native accounting amount") from exc


def _account(name, company, *, root, kinds=None, historical=False):
    row = frappe.get_doc("Account", name, for_update=True)
    if (row.company != company or row.is_group or (row.disabled and not historical)
            or row.root_type != root or (kinds and row.account_type not in kinds)
            or (row.account_currency or "AFN") != "AFN"):
        raise frappe.ValidationError("Refund accounts must retain the original company and AFN accounting currency")
    return row


def lock_cash_accounts(names):
    """Serialize native cash writers before refund availability is read."""
    names = sorted({name for name in names if isinstance(name, str) and name})
    if len(names) > 1000 or any(len(name) > 140 for name in names):
        raise frappe.ValidationError("Invalid native Cash account references")
    if names:
        frappe.db.sql("select name from `tabAccount` where account_type='Cash' and name in %s order by name for update",
                      (tuple(names),))


def _gl(doctype, name):
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

    fields = ["account", "debit", "credit", "party_type", "party", "against_voucher_type", "against_voucher",
              "cost_center", "project", *get_accounting_dimensions()]
    fields = list(dict.fromkeys(fields))
    if any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", field) for field in fields):
        raise frappe.ValidationError("Invalid native accounting dimension column")
    columns = ",".join("`" + field + "`" for field in fields)
    rows = frappe.db.sql("select " + columns + " from `tabGL Entry` where voucher_type=%s and voucher_no=%s "
                         "and is_cancelled=0 limit 1001 for update", (doctype, name), as_dict=True)
    if len(rows) > 1000:
        raise frappe.ValidationError("Native accounting evidence exceeds the qualified limit")
    return rows


def _key(row):
    return tuple(row.get(field) or "" for field in ("account", "party_type", "party", "against_voucher_type", "against_voucher"))


def _check_gl(doctype, name, expected, dimensions=None):
    rows = _gl(doctype, name)
    actual = {_key(row): (money(row.debit), money(row.credit)) for row in rows}
    if len(rows) != len(expected) or actual != expected:
        raise frappe.ValidationError("Native refund/receipt ledger rows do not reconcile exactly")
    if dimensions and any((row.get(key) or None) != (value or None)
                          for row in rows for key, value in dimensions[row.account].items()):
        raise frappe.ValidationError("Native refund accounting dimensions differ from the original tuition ledger")
    return rows


def _fee_dimensions(fee):
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

    total = money(fee.grand_total)
    rows = _check_gl("Fees", fee.name, {_party_key(fee): (total, Decimal(0)),
        (fee.income_account, "", "", "", ""): (Decimal(0), total)})
    fields = ("cost_center", "project", *get_accounting_dimensions())
    # A native Journal Entry child fills None with its :Company defaults
    # before before_validate. An explicit empty Link preserves the original
    # unassigned dimension instead; GL comparison normalizes both to None.
    # In particular, do not introduce a cost center on the Fees receivable.
    return {row.account: {key: row.get(key) or "" for key in fields} for row in rows}


def _party_key(fee):
    return (fee.receivable_account, "Student", fee.student, "Fees", fee.name)


def _snapshot(fee, known_vouchers):
    where = (fee.company, fee.receivable_account, fee.student, fee.name)
    rows = frappe.db.sql("select debit,credit,voucher_type,voucher_no from `tabGL Entry` where company=%s "
        "and account=%s and party_type='Student' and party=%s and against_voucher_type='Fees' "
        "and against_voucher=%s and is_cancelled=0 limit 1001 for update", where, as_dict=True)
    if len(rows) > 1000 or any((row.voucher_type, row.voucher_no) not in known_vouchers for row in rows):
        raise frappe.ValidationError("Unqualified tuition accounting references require reconciliation before refund")
    gl = sum((money(row.debit) - money(row.credit) for row in rows), Decimal(0))
    payment_rows = frappe.db.sql("select amount_in_account_currency from `tabPayment Ledger Entry` "
        "where company=%s and account=%s and party_type='Student' and party=%s "
        "and against_voucher_type='Fees' and against_voucher_no=%s and delinked=0 limit 1001 for update", where)
    if len(payment_rows) > 1000:
        raise frappe.ValidationError("Payment Ledger evidence exceeds the qualified limit")
    ple = sum((Decimal(str(row[0])) for row in payment_rows), Decimal(0))
    outstanding = Decimal(str(frappe.db.get_value("Fees", fee.name, "outstanding_amount", for_update=True)))
    if gl != ple or gl != outstanding:
        raise frappe.ValidationError("Fees, General Ledger and Payment Ledger outstanding must reconcile before refund")
    return outstanding


def _payment_shape(doc, fee, amount, cash, *, direction):
    references = doc.get("references") or []
    debit, credit = (cash, fee.receivable_account) if direction == "Pay" else (fee.receivable_account, cash)
    return (doc.payment_type == direction and doc.party_type == "Student" and doc.party == fee.student
        and doc.company == fee.company and doc.paid_from == debit and doc.paid_to == credit
        and doc.paid_from_account_currency == doc.paid_to_account_currency == "AFN"
        and Decimal(str(doc.source_exchange_rate or 0)) == Decimal(1)
        and Decimal(str(doc.target_exchange_rate or 0)) == Decimal(1)
        and money(doc.paid_amount) == money(doc.received_amount) == amount
        and not doc.get("deductions") and not doc.get("taxes") and money(doc.get("unallocated_amount")) == 0
        and money(doc.get("difference_amount")) == 0 and len(references) == 1
        and references[0].reference_doctype == "Fees" and references[0].reference_name == fee.name
        and money(references[0].allocated_amount) == amount)


def _collections(fee):
    references = frappe.db.sql("select r.parent from `tabPayment Entry Reference` r join `tabPayment Entry` p "
        "on p.name=r.parent where r.reference_doctype='Fees' and r.reference_name=%s "
        "and p.docstatus=1 and p.payment_type='Receive' limit 1001 for update", (fee.name,), as_dict=True)
    if len(references) > 1000:
        raise frappe.ValidationError("Tuition receipt evidence exceeds the qualified limit")
    rows, known = [], set()
    for name in sorted({row.parent for row in references}):
        payment = frappe.get_doc("Payment Entry", name, for_update=True)
        if int(payment.docstatus) != 1 or payment.payment_type != "Receive":
            continue
        amount = money(payment.received_amount)
        if not amount or not _payment_shape(payment, fee, amount, payment.paid_to, direction="Receive"):
            raise frappe.ValidationError("Each source receipt must be fully allocated to this student's original tuition bill")
        _account(payment.paid_to, fee.company, root="Asset", kinds={"Cash", "Bank"}, historical=True)
        dimension = {field: payment.get(field) for field in _fee_dimensions(fee)[fee.receivable_account]}
        if dimension.get("cost_center"):
            center = frappe.db.get_value("Cost Center", dimension["cost_center"], "company", for_update=True)
            if center != fee.company:
                raise frappe.ValidationError("Source receipt cost center belongs to another company")
        _check_gl("Payment Entry", name, {_party_key(fee): (Decimal(0), amount),
            (payment.paid_to, "", "", "", ""): (amount, Decimal(0))},
            {fee.receivable_account: dimension, payment.paid_to: dimension})
        rows.append(dict(payment_entry=name, student=fee.student, company=fee.company, fees=fee.name,
                         docstatus=1, amount=str(amount)))
        known.add(("Payment Entry", name))
    return rows, known


def _verify_pair(req, fee):
    amount = money(req.approved_amount)
    credit = frappe.get_doc("Journal Entry", req.credit_journal, for_update=True)
    payout = frappe.get_doc("Payment Entry", req.payment_entry, for_update=True)
    if (not amount or int(credit.docstatus) != 1 or int(payout.docstatus) != 1
            or credit.company != fee.company or credit.voucher_type != "Credit Note"
            or not _payment_shape(payout, fee, amount, payout.paid_from, direction="Pay")):
        raise frappe.ValidationError("Refund request must bind one complete native credit and payout")
    _account(payout.paid_from, fee.company, root="Asset", kinds={"Cash"}, historical=True)
    dimensions = _fee_dimensions(fee)
    _check_gl("Journal Entry", credit.name, {_party_key(fee): (Decimal(0), amount),
        (fee.income_account, "", "", "", ""): (amount, Decimal(0))}, dimensions)
    _check_gl("Payment Entry", payout.name, {_party_key(fee): (amount, Decimal(0)),
        (payout.paid_from, "", "", "", ""): (Decimal(0), amount)},
        {fee.receivable_account: dimensions[fee.receivable_account], payout.paid_from: dimensions[fee.receivable_account]})
    return amount


def _prior_refunds(fee):
    rows, known = [], set()
    payments = frappe.db.sql("select distinct p.name from `tabPayment Entry` p join `tabPayment Entry Reference` r "
        "on r.parent=p.name where p.docstatus=1 and p.payment_type='Pay' "
        "and r.reference_doctype='Fees' and r.reference_name=%s limit 1001 for update", (fee.name,), as_dict=True)
    if len(payments) > 1000:
        raise frappe.ValidationError("Tuition refund evidence exceeds the qualified limit")
    for row in payments:
        names = frappe.db.sql("select name from `tabTH Tuition Refund Request` where payment_entry=%s limit 2 for update",
                              (row.name,))
        if len(names) != 1:
            raise frappe.ValidationError("Unbound legacy tuition payout requires an independent accounting audit")
        req = frappe.get_doc(REQUEST, names[0][0], for_update=True)
        if req.status != "Paid" or (req.company, req.student, req.fees) != (fee.company, fee.student, fee.name):
            raise frappe.ValidationError("Prior tuition refund ownership/status does not reconcile")
        amount = _verify_pair(req, fee)
        rows.append(dict(payment_entry=row.name, student=fee.student, company=fee.company, fees=fee.name,
                         docstatus=1, amount=str(amount)))
        known.update({("Payment Entry", row.name), ("Journal Entry", req.credit_journal)})
    return rows, known


@dataclass(frozen=True)
class _NativePair:
    request: str
    payer: str
    approver: str
    fee: object
    amount: Decimal
    cash: str
    posting_date: str
    income_dimensions: dict
    receivable_dimensions: dict
    payout_dimensions: dict
    credit: object
    payout: object


@contextmanager
def _posting_pair(context):
    if _PAIR.get() is not None:
        raise frappe.PermissionError("Nested tuition posting is forbidden")
    token = _PAIR.set(context)
    try:
        yield
    finally:
        _PAIR.reset(token)


def exact_native_write_allowed(doc, method=None):
    context = _PAIR.get()
    if (context is None or method in {"before_cancel", "on_trash", "before_update_after_submit"}
            or active_command_kind() != "pay_tuition_refund" or frappe.session.user != context.payer
            or context.payer == context.approver):
        return False
    fee, amount = context.fee, context.amount
    if doc is context.payout:
        return (not doc.get("amended_from") and str(doc.posting_date) == context.posting_date
                and doc.reference_no == context.request
                and all((doc.get(key) or None) == (value or None) for key, value in context.payout_dimensions.items())
                and _payment_shape(doc, fee, amount, context.cash, direction="Pay"))
    if doc is not context.credit or doc.company != fee.company or doc.voucher_type != "Credit Note":
        return False
    accounts = doc.get("accounts") or []
    if len(accounts) != 2 or doc.get("amended_from") or str(doc.posting_date) != context.posting_date:
        return False
    income, receivable = accounts
    return (income.account == fee.income_account and not income.party_type and not income.party
        and not income.reference_type and not income.reference_name
        and money(income.debit_in_account_currency) == amount and money(income.credit_in_account_currency) == 0
        and receivable.account == fee.receivable_account and receivable.party_type == "Student"
        and receivable.party == fee.student and receivable.reference_type == "Fees" and receivable.reference_name == fee.name
        and money(receivable.credit_in_account_currency) == amount and money(receivable.debit_in_account_currency) == 0
        and all((income.get(key) or None) == (value or None) for key, value in context.income_dimensions.items())
        and all((receivable.get(key) or None) == (value or None) for key, value in context.receivable_dimensions.items()))


def protect_bound_artifact(doc):
    context = _PAIR.get()
    if context and (doc is context.credit or doc is context.payout):
        raise frappe.PermissionError("The exact native refund pair cannot be mutated outside its permitted posting step")
    if callable(getattr(doc, "is_new", None)) and doc.is_new():
        return
    field = {"Journal Entry": "credit_journal", "Payment Entry": "payment_entry"}.get(doc.doctype)
    bound = frappe.db.sql("select name from `tabTH Tuition Refund Request` where `" + field + "`=%s limit 1 for update",
                          (doc.name,)) if field and doc.name else []
    if bound:
        raise frappe.PermissionError("A tuition refund's native documents require a separately authorized paired reversal")


def assert_paid_transition(req):
    context = _PAIR.get()
    if (context is None or active_command_kind() != "pay_tuition_refund" or req.name != context.request
            or req.paying_user != context.payer or req.approved_by != context.approver
            or req.credit_journal != context.credit.name or req.payment_entry != context.payout.name
            or money(req.approved_amount) != context.amount):
        raise frappe.PermissionError("Paid tuition refunds require the exact authorized native pair")
    _verify_pair(req, context.fee)


def post_approved_refund(name):
    kind, actor = require_command(REQUEST)
    if kind != "pay_tuition_refund":
        raise frappe.PermissionError("Native tuition payout requires its exact Finance command")
    fee_name = frappe.db.get_value(REQUEST, name, "fees")
    if not fee_name:
        raise frappe.ValidationError("Unknown tuition refund request")
    company = frappe.db.get_value("Fees", fee_name, "company")
    cash = frappe.db.get_value("Company", company, "default_cash_account") if company else None
    if not cash:
        raise frappe.ValidationError("Finance must configure the company's main Cash account before payout")
    lock_cash_accounts([cash])
    fee = frappe.get_doc("Fees", fee_name, for_update=True)
    req = frappe.get_doc(REQUEST, name, for_update=True)
    require_finance_company(fee.company)
    permitted = frappe.db.sql("select for_value from `tabUser Permission` where user=%s and `allow`='Account' "
        "limit 1001 for update", (actor,))
    if len(permitted) > 1000 or (permitted and cash not in {row[0] for row in permitted}):
        raise frappe.PermissionError("This Finance login has no authority for the configured main Cash account")
    if (req.fees != fee.name or req.company != fee.company or req.student != fee.student
            or int(fee.docstatus) != 1 or req.status != "Approved" or not req.approval_evidence
            or money(req.requested_amount) != money(req.approved_amount) or req.payment_entry or req.get("credit_journal")):
        raise frappe.ValidationError("Refund approval must match the unchanged submitted tuition bill")
    if fee.currency != "AFN" or frappe.get_cached_value("Company", fee.company, "default_currency") != "AFN":
        raise frappe.ValidationError("Tuition refund qualification currently requires exact AFN accounting")
    _account(fee.receivable_account, fee.company, root="Asset", kinds={"Receivable"})
    _account(fee.income_account, fee.company, root="Income")
    if fee.company != company:
        raise frappe.ValidationError("The refund's accounting company changed during authorization")
    _account(cash, fee.company, root="Asset", kinds={"Cash"})
    dimensions = _fee_dimensions(fee)
    collections, collection_vouchers = _collections(fee)
    if sum((Decimal(row["amount"]) for row in collections), Decimal(0)) > money(fee.grand_total):
        raise frappe.ValidationError("Collections exceed the original bill; reconcile the overpayment before a tuition refund")
    refunds, refund_vouchers = _prior_refunds(fee)
    authority = rules.validate_payment_authority({"status": req.status, "student": req.student,
        "company": req.company, "fees": req.fees, "approved_amount": str(req.approved_amount),
        "reason": req.reason, "approved_by": req.approved_by}, payer=actor,
        payer_roles=frappe.get_roles(actor), collections=collections, refunds=refunds)
    from toefl_house.finance.tuition_refund_commands import _existing_requests

    if rules.open_amount(_existing_requests(fee.name), fees=fee.name) > Decimal(authority["remaining_refundable_afn"]):
        raise frappe.ValidationError("Open tuition refund reservations exceed current verified collections")
    known = {("Fees", fee.name)} | collection_vouchers | refund_vouchers
    before = _snapshot(fee, known)
    amount = money(req.approved_amount)
    balance = Decimal(str(frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` "
        "where company=%s and account=%s and is_cancelled=0 for update", (fee.company, cash))[0][0]))
    if balance < amount:
        raise frappe.ValidationError("Main Cash has insufficient verified funds; complete an authorized handover or funding first")
    income_dimensions, receivable_dimensions = dimensions[fee.income_account], dimensions[fee.receivable_account]
    payout_dimensions = dict(receivable_dimensions)
    today = frappe.utils.today()
    credit = frappe.get_doc(dict(doctype="Journal Entry", voucher_type="Credit Note", company=fee.company,
        posting_date=today, user_remark="Approved tuition refund " + req.name,
        accounts=[dict(account=fee.income_account, debit_in_account_currency=float(amount), **income_dimensions),
                  dict(account=fee.receivable_account, party_type="Student", party=fee.student,
                       reference_type="Fees", reference_name=fee.name, credit_in_account_currency=float(amount), **receivable_dimensions)]))
    payout = frappe.get_doc(dict(doctype="Payment Entry", payment_type="Pay", company=fee.company,
        posting_date=today, party_type="Student", party=fee.student, paid_from=cash, paid_to=fee.receivable_account,
        paid_from_account_currency="AFN", paid_to_account_currency="AFN", source_exchange_rate=1, target_exchange_rate=1,
        paid_amount=float(amount), received_amount=float(amount), reference_no=req.name, reference_date=today,
        references=[dict(reference_doctype="Fees", reference_name=fee.name, allocated_amount=float(amount))], **payout_dimensions))
    context = _NativePair(req.name, actor, req.approved_by, fee, amount, cash, today,
                          income_dimensions, receivable_dimensions, payout_dimensions, credit, payout)
    with _posting_pair(context):
        for document in (credit, payout):
            document.flags.ignore_permissions = True
            document.insert(ignore_permissions=True)
            document.flags.ignore_permissions = True
            document.submit()
        req.credit_journal, req.payment_entry = credit.name, payout.name
        req.paying_user, req.status = actor, "Paid"
        _verify_pair(req, fee)
        known.update({("Journal Entry", credit.name), ("Payment Entry", payout.name)})
        if _snapshot(fee, known) != before:
            raise frappe.ValidationError("The paired refund changed the student's original tuition outstanding")
        req.flags.ignore_permissions = True
        req.save(ignore_permissions=True)
    return req, dict(name=req.name, status="Paid", credit_journal=credit.name, payment_entry=payout.name,
        approved_amount=str(amount), gross_collections=authority["verified_collections_afn"],
        prior_refunds=authority["prior_refunds_afn"], remaining_refundable=authority["remaining_after_proposal_afn"], currency="AFN")


def guard_payment(doc, method=None):
    require_operational()
    # Exact newly constructed documents are authorized only while their
    # independently authenticated command owns this nonserializable context.
    if exact_native_write_allowed(doc, method):
        return True
    protect_bound_artifact(doc)
    lock_cash_accounts([doc.get("paid_from"), doc.get("paid_to")])
    stored = frappe.get_doc("Payment Entry", doc.name, for_update=True) if doc.name and not doc.is_new() else None
    current_refs = doc.get("references") or []
    stored_refs = (stored.get("references") or []) if stored else []
    fee_names = {row.reference_name for row in [*current_refs, *stored_refs]
                 if row.reference_doctype == "Fees" and row.reference_name}
    if not fee_names:
        return False
    fees = {name: frappe.get_doc("Fees", name, for_update=True) for name in sorted(fee_names)}
    if doc.payment_type == "Receive" and doc.party_type == "Student" and method not in {"before_cancel", "on_trash"}:
        actor = frappe.session.user
        roles = set(frappe.get_roles(actor))
        command = active_command_kind()
        controlled = command in {"record_reception_collection", "correct_reception_collection"}
        if actor == "Administrator":
            if site_mode() != SYNTHETIC:
                raise frappe.PermissionError("Administrator tuition receipt fixtures are restricted to synthetic sites")
        elif not controlled and not roles & {"Finance Officer", "Finance Manager"}:
            raise frappe.PermissionError("Tuition receipts require authorized Reception or Finance")
        else:
            require_finance_company(doc.company)
            from toefl_house.command_scope import authorize_command_scope

            for fee in fees.values():
                authorize_command_scope("request_tuition_refund", {"fees": fee.name, "company": doc.company}, actor)
        for row in current_refs:
            if row.reference_doctype != "Fees":
                continue
            fee = fees[row.reference_name]
            if (int(fee.docstatus) != 1 or fee.student != doc.party or fee.company != doc.company
                    or fee.receivable_account != doc.paid_from):
                raise frappe.ValidationError("Student tuition receipts must match their submitted Fees, company and receivable account")
        if not stored or int(stored.docstatus) != 1:
            for name, fee in fees.items():
                allocated = sum((money(row.allocated_amount) for row in current_refs
                                 if row.reference_doctype == "Fees" and row.reference_name == name), Decimal(0))
                if not allocated or allocated > Decimal(str(fee.outstanding_amount)):
                    raise frappe.ValidationError("Tuition collection cannot exceed the locked current Fees outstanding")
    if stored and int(stored.docstatus) == 1 and stored.payment_type == "Receive" and stored.party_type == "Student":
        from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

        def references(rows):
            return sorted((row.reference_doctype or "", row.reference_name or "", str(Decimal(str(row.allocated_amount or 0))))
                          for row in rows)

        def same(field):
            current, previous = doc.get(field), stored.get(field)
            if field in {"paid_amount", "received_amount", "source_exchange_rate", "target_exchange_rate"}:
                return Decimal(str(current or 0)) == Decimal(str(previous or 0))
            return str(current or "") == str(previous or "")

        financial_fields = (*_FINANCIAL_FIELDS, "cost_center", "project", "finance_book", *get_accounting_dimensions())
        changing = (method in {"before_cancel", "on_trash"}
                    or (method == "before_update_after_submit" and active_command_kind() != "accept_reception_handover")
                    or not all(same(field) for field in financial_fields)
                    or references(current_refs) != references(stored_refs))
        if changing:
            for fee in fees.values():
                requests = frappe.db.sql("select name,status,payment_entry,credit_journal from `tabTH Tuition Refund Request` "
                    "where fees=%s and status in ('Requested','Approved','Paid') limit 1001 for update", (fee.name,), as_dict=True)
                if len(requests) > 1000:
                    raise frappe.ValidationError("Refund source evidence exceeds the qualified limit")
                if any(row.status in {"Requested", "Approved"}
                       or (row.status == "Paid" and (frappe.db.get_value("Payment Entry", row.payment_entry, "docstatus") != 2
                           or frappe.db.get_value("Journal Entry", row.credit_journal, "docstatus") != 2)) for row in requests):
                    raise frappe.PermissionError("Resolve the approved/refunded tuition case before changing its original collection")
    return False


def protect_fee(doc, method=None):
    if method not in {"before_cancel", "on_trash", "before_update_after_submit"} or not doc.name:
        return
    requests = frappe.db.sql("select name from `tabTH Tuition Refund Request` where fees=%s "
        "and status in ('Requested','Approved','Paid') limit 1 for update", (doc.name,))
    if requests:
        raise frappe.PermissionError("Resolve pending/refunded tuition cases before changing the original Fees")
