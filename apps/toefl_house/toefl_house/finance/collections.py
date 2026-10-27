"""Reception receipts and independent Finance cash handovers, on native ledgers."""
from decimal import Decimal

import frappe

from toefl_house.api import _execute
from toefl_house.configuration import audit as configuration_audit
from toefl_house.finance import collection_rules as rules
from toefl_house.finance.collection_reads import native_reference_reads
from toefl_house.finance.company_scope import require_finance_company
from toefl_house.policy import digest
from toefl_house.security import active_command_kind, record_synthetic_flag

PAYMENT = "Payment Entry"
FIELDS = ("th_reception_collector", "th_collection_fees", "th_collection_handover", "th_collection_synthetic")


def _text(value, label, maximum=140):
    try:
        return rules.bounded_text(value, label, maximum)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _money(value):
    try:
        return rules.money(value)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _names(value):
    try:
        return rules.receipt_names(value)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def require_schema():
    if not all(frappe.db.has_column(PAYMENT, field) for field in FIELDS):
        raise frappe.ValidationError("Reception receipts need the supported application migration first")


def cash_account(name, company):
    doc = frappe.get_doc("Account", name)
    currency = frappe.get_cached_value("Company", company, "default_currency")
    if (doc.company != company or doc.is_group or doc.disabled or doc.account_type != "Cash"
            or doc.root_type != "Asset" or (doc.account_currency or currency) != currency):
        raise frappe.ValidationError("The counter must be an active Cash account in the same company and currency")
    return doc


def counter_for(actor, company):
    rows = frappe.get_all("User Permission", filters={"user": actor, "allow": "Account"},
                          pluck="for_value", limit_page_length=101)
    if len(rows) > 100:
        raise frappe.ValidationError("The Owner must resolve the counter assignments")
    counters = []
    for name in set(rows):
        row = frappe.db.get_value("Account", name, ["company", "account_type", "is_group"], as_dict=True)
        if row and row.account_type == "Cash" and not row.is_group:
            counters.append((name, row.company))
    if len(counters) != 1 or counters[0][1] != company:
        raise frappe.ValidationError("Ask the Owner to assign one cash counter for this receptionist and company")
    return cash_account(counters[0][0], company)


@frappe.whitelist(methods=["POST"])
def configure_reception_counter(request_key, user, company, counter_label, reason):
    configuration_audit.require_authority("business_policy")
    user = _text(user, "receptionist")
    company = _text(company, "company")
    label = _text(counter_label, "counter name", 100)
    reason = _text(reason, "assignment reason", 300)
    require_finance_company(company)  # Rechecked even for a saved configuration receipt.
    target = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if (user in {"Guest", "Administrator"} or not target or not target.enabled
            or target.user_type != "System User" or "Reception" not in frappe.get_roles(user)):
        raise frappe.ValidationError("Select an enabled Reception staff account")
    target_companies = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"},
                                      pluck="for_value", limit_page_length=101)
    if target_companies and company not in target_companies:
        raise frappe.PermissionError("The receptionist is not permitted to work in this company")
    main = frappe.get_cached_value("Company", company, "default_cash_account")
    if not main:
        raise frappe.ValidationError("Finance must configure the company's main Cash account first")
    main_account = cash_account(main, company)

    def work(actor):
        frappe.get_doc("User", user, for_update=True)
        name = frappe.db.get_value("Account", {"company": company, "account_name": label}, "name")
        if not name:
            name = frappe.get_doc(dict(doctype="Account", account_name=label, company=company,
                parent_account=main_account.parent_account, account_type="Cash", is_group=0,
                account_currency=frappe.get_cached_value("Company", company, "default_currency"))).insert(
                    ignore_permissions=True).name
        if name == main:
            raise frappe.ValidationError("Reception needs its own counter, separate from main Cash")
        cash_account(name, company)
        if frappe.db.exists("User Permission", {"allow": "Account", "for_value": name,
                                                "user": ("!=", user)}):
            raise frappe.ValidationError("Each receptionist needs a separately assigned cash counter")
        previous = frappe.get_all("User Permission", filters={"user": user, "allow": "Account"},
                                   fields=["name", "for_value"], limit_page_length=101)
        if len(previous) > 100:
            raise frappe.ValidationError("The Owner must resolve the counter assignments")
        for row in previous:
            account = frappe.db.get_value("Account", row["for_value"], ["account_type", "is_group"], as_dict=True)
            if account and account.account_type == "Cash" and not account.is_group and row["for_value"] != name:
                frappe.delete_doc("User Permission", row["name"], ignore_permissions=True)
        if not frappe.db.exists("User Permission", {"user": user, "allow": "Account", "for_value": name}):
            frappe.get_doc(dict(doctype="User Permission", user=user, allow="Account", for_value=name,
                                apply_to_all_doctypes=1, hide_descendants=1)).insert(ignore_permissions=True)
        audit_target = "ReceptionCounter:" + digest(user)
        result = dict(user=user, company=company, counter_account=name, reason=reason)
        return result, dict(target=audit_target, before_hash=configuration_audit.latest_after_hash(audit_target),
                            after_hash=digest(result))

    return configuration_audit.execute("configure_reception_counter", request_key,
        dict(user=user, company=company, counter_label=label, reason=reason), work)


def _fee(name):
    doc = frappe.get_doc("Fees", _text(name, "tuition bill"), for_update=True)
    if int(doc.docstatus) != 1 or not doc.student or not doc.receivable_account:
        raise frappe.ValidationError("Select a submitted tuition bill with its student and receivable account")
    require_finance_company(doc.company)
    currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    account_currency = frappe.db.get_value("Account", doc.receivable_account, "account_currency") or currency
    if doc.currency != currency or account_currency != currency:
        raise frappe.ValidationError("Counter collection requires the company's exact accounting currency")
    frappe.db.sql("select name from `tabStudent` where name=%s for update", (doc.student,))
    return doc


def _new_receipt(fee, amount, counter, collector, *, posting_date=None, amended_from=None):
    currency = fee.currency
    doc = frappe.get_doc(dict(doctype=PAYMENT, payment_type="Receive", company=fee.company,
        posting_date=posting_date or frappe.utils.today(), party_type="Student", party=fee.student,
        paid_from=fee.receivable_account, paid_to=counter,
        paid_from_account_currency=currency, paid_to_account_currency=currency,
        source_exchange_rate=1, target_exchange_rate=1,
        paid_amount=float(amount), received_amount=float(amount), amended_from=amended_from,
        th_reception_collector=collector, th_collection_fees=fee.name,
        th_collection_synthetic=record_synthetic_flag(),
        references=[dict(reference_doctype="Fees", reference_name=fee.name, allocated_amount=float(amount))]))
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    doc.flags.ignore_permissions = True
    doc.submit()
    if int(doc.docstatus) != 1 or float(doc.unallocated_amount or 0) != 0:
        raise frappe.ValidationError("The receipt must be posted and fully allocated to the selected tuition bill")
    return doc


def receipt_facts(doc):
    return dict(number=doc.name, student=doc.party,
        student_name=frappe.db.get_value("Student", doc.party, "student_name") or doc.party,
        fees=doc.th_collection_fees, company=doc.company, date=str(doc.posting_date),
        amount=float(doc.received_amount), currency=doc.paid_to_account_currency,
        collector=doc.th_reception_collector, counter_account=doc.paid_to,
        status="Void" if int(doc.docstatus) == 2 else "Issued",
        handover=doc.th_collection_handover, replaces=doc.amended_from,
        synthetic=bool(doc.th_collection_synthetic))


@frappe.whitelist(methods=["POST"])
def record_reception_collection(request_key, fees, amount):
    def work(actor):
        require_schema()
        received = _money(amount)
        fee = _fee(fees)
        if received > Decimal(str(fee.outstanding_amount or 0)):
            raise frappe.ValidationError("The receipt cannot exceed the tuition bill's current outstanding amount")
        counter = counter_for(actor, fee.company)
        with native_reference_reads([("Fees", fee.name), ("Student", fee.student)]):
            doc = _new_receipt(fee, received, counter.name, actor)
        outstanding = Decimal(str(frappe.db.get_value("Fees", fee.name, "outstanding_amount")))
        if abs(Decimal(str(fee.outstanding_amount)) - outstanding - received) > Decimal("0.005"):
            raise frappe.ValidationError("The native tuition balance did not reconcile with this receipt")
        result = dict(payment_entry=doc.name, fees=fee.name, student=fee.student, company=fee.company,
            amount=float(received), currency=fee.currency, counter_account=counter.name,
            outstanding_after=float(outstanding),
            receipt=receipt_facts(doc))
        return result, dict(target=doc.name, after_hash=digest(result))
    return _execute("record_reception_collection", request_key, dict(fees=fees, amount=amount), work)


def _owned_receipt(doc):
    if (int(doc.docstatus) != 1 or doc.payment_type != "Receive" or doc.party_type != "Student"
            or not doc.th_reception_collector or not doc.th_collection_fees
            or doc.th_collection_handover or doc.unallocated_amount
            or bool(doc.th_collection_synthetic) != bool(record_synthetic_flag())):
        raise frappe.ValidationError("Select an issued Reception receipt that has not been handed over")
    amount = _money(doc.received_amount)
    currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    if (Decimal(str(doc.paid_amount)) != amount
            or doc.paid_from_account_currency != currency or doc.paid_to_account_currency != currency
            or len(doc.references) != 1 or doc.references[0].reference_doctype != "Fees"
            or doc.references[0].reference_name != doc.th_collection_fees
            or Decimal(str(doc.references[0].allocated_amount)) != amount
            or frappe.db.get_value("Fees", doc.th_collection_fees, "student") != doc.party):
        raise frappe.ValidationError("The native receipt allocation or accounting currency no longer reconciles")


@frappe.whitelist(methods=["POST"])
def accept_reception_handover(request_key, payment_entries, counted_amount):
    def work(actor):
        require_schema()
        names = _names(payment_entries)
        docs = [frappe.get_doc(PAYMENT, name, for_update=True) for name in names]
        for doc in docs:
            _owned_receipt(doc)
            require_finance_company(doc.company)
        first = docs[0]
        if first.th_reception_collector == actor:
            raise frappe.PermissionError("Another Finance staff member must accept this collector's handover")
        if any((doc.company, doc.paid_to, doc.th_reception_collector, doc.paid_to_account_currency) !=
               (first.company, first.paid_to, first.th_reception_collector, first.paid_to_account_currency)
               for doc in docs):
            raise frappe.ValidationError("One handover covers one collector, company, counter and currency")
        total = _money(sum((Decimal(str(doc.received_amount)) for doc in docs), Decimal(0)))
        if _money(counted_amount) != total:
            raise frappe.ValidationError("Counted cash must equal the selected receipts; investigate a difference first")
        counter = cash_account(first.paid_to, first.company)
        main = frappe.get_cached_value("Company", first.company, "default_cash_account")
        if not main or main == counter.name:
            raise frappe.ValidationError("Finance needs a separate main Cash account for the handover")
        cash_account(main, first.company)
        frappe.db.sql("select name from `tabAccount` where name=%s for update", (counter.name,))
        from toefl_house.finance.cashier import drawer_balances
        balances = drawer_balances(first.company, [counter.name], frappe.utils.today())
        if not balances or Decimal(str(balances[0]["closing"])) < total:
            raise frappe.ValidationError("The counter ledger does not cover these receipts; investigate before handover")
        currency = first.paid_to_account_currency
        transfer = frappe.get_doc(dict(doctype=PAYMENT, payment_type="Internal Transfer",
            company=first.company, posting_date=frappe.utils.today(), paid_from=counter.name, paid_to=main,
            paid_from_account_currency=currency, paid_to_account_currency=currency,
            source_exchange_rate=1, target_exchange_rate=1,
            paid_amount=float(total), received_amount=float(total),
            th_reception_collector=first.th_reception_collector,
            th_collection_synthetic=record_synthetic_flag()))
        transfer.flags.ignore_permissions = True
        transfer.insert(ignore_permissions=True)
        transfer.flags.ignore_permissions = True
        transfer.submit()
        for doc in docs:
            doc.th_collection_handover = transfer.name
            doc.flags.ignore_permissions = True
            doc.save(ignore_permissions=True)
        result = dict(payment_entry=transfer.name, company=first.company,
            collector=first.th_reception_collector, counter_account=counter.name,
            main_cash_account=main, amount=float(total), currency=currency, receipts=names)
        return result, dict(target=transfer.name, after_hash=digest(result))
    return _execute("accept_reception_handover", request_key,
        dict(payment_entries=payment_entries, counted_amount=counted_amount), work)


@frappe.whitelist(methods=["POST"])
def correct_reception_collection(request_key, payment_entry, fees, reason):
    def work(actor):
        require_schema()
        explanation = _text(reason, "correction reason", 300)
        original = frappe.get_doc(PAYMENT, _text(payment_entry, "receipt"), for_update=True)
        _owned_receipt(original)
        require_finance_company(original.company)
        # Lock both bills in stable order before native cancellation/reissue.
        target_name = _text(fees, "tuition bill")
        bills = {name: _fee(name) for name in sorted({original.th_collection_fees, target_name})}
        target = bills[target_name]
        amount = _money(original.received_amount)
        if target.company != original.company or target.currency != original.paid_to_account_currency:
            raise frappe.ValidationError("A correction must retain the same company and currency")
        cash_account(original.paid_to, original.company)
        references = [("Fees", fee.name) for fee in bills.values()] + [("Student", fee.student) for fee in bills.values()]
        with native_reference_reads(references):
            original.flags.ignore_permissions = True
            original.cancel()
            target.reload()
            if amount > Decimal(str(target.outstanding_amount or 0)):
                raise frappe.ValidationError("The replacement bill does not owe the receipt amount")
            replacement = _new_receipt(target, amount, original.paid_to, original.th_reception_collector,
                posting_date=original.posting_date, amended_from=original.name)
        original.add_comment("Comment", "Owner correction: " + explanation + "; replacement " + replacement.name)
        result = dict(payment_entry=replacement.name, company=replacement.company,
            fees=target.name, student=target.student, replaced=original.name, reason=explanation,
            receipt=receipt_facts(replacement))
        return result, dict(target=replacement.name, before_hash=digest(original.name), after_hash=digest(result))
    return _execute("correct_reception_collection", request_key,
        dict(payment_entry=payment_entry, fees=fees, reason=reason), work)


@frappe.whitelist(methods=["GET"])
def get_collection_receipt(payment_entry):
    actor = frappe.session.user
    roles = set(frappe.get_roles(actor))
    if (actor in {None, "Guest", "Administrator"} or not frappe.db.get_value("User", actor, "enabled")
            or not roles & {"Reception", "Finance Officer", "Finance Manager", "Course Owner", "Finance Auditor"}):
        raise frappe.PermissionError("A permitted staff account is required")
    require_schema()
    from toefl_house.command_scope import authorize_command_scope
    authorize_command_scope("read_collection_receipt", {"payment_entry": payment_entry}, actor)
    doc = frappe.get_doc(PAYMENT, _text(payment_entry, "receipt"))
    if not doc.th_collection_fees or int(doc.docstatus) not in {1, 2}:
        raise frappe.PermissionError("This is not an issued Reception receipt")
    if not roles & {"Finance Officer", "Finance Manager", "Course Owner", "Finance Auditor"} and doc.th_reception_collector != actor:
        raise frappe.PermissionError("Reception can view only its own numbered receipts")
    return receipt_facts(doc)


def guard_collection_fields(doc, method=None):
    before = doc.get_doc_before_save() if callable(getattr(doc, "get_doc_before_save", None)) else None
    if not any(doc.get(field) or (before and before.get(field)) for field in FIELDS):
        return
    kind = active_command_kind()
    if method == "on_trash" or kind not in {
            "record_reception_collection", "accept_reception_handover", "correct_reception_collection"}:
        raise frappe.PermissionError("Reception receipts and handovers change only through their authorized commands")
    if method == "before_cancel":
        if kind != "correct_reception_collection" or doc.th_collection_handover or not doc.th_collection_fees:
            raise frappe.PermissionError("Only an Owner correction can void an unhanded Reception receipt")
        return
    if doc.th_collection_fees:
        if (doc.payment_type != "Receive" or doc.party_type != "Student" or not doc.th_reception_collector
                or len(doc.references) != 1 or doc.references[0].reference_doctype != "Fees"
                or doc.references[0].reference_name != doc.th_collection_fees):
            raise frappe.ValidationError("A Reception receipt must settle exactly its selected tuition bill")
        if kind == "record_reception_collection" and doc.th_reception_collector != frappe.session.user:
            raise frappe.PermissionError("The collector must be the authenticated receptionist")
        if kind == "accept_reception_handover":
            if (not before or int(before.docstatus) != 1 or not doc.th_collection_handover
                    or before.th_collection_handover):
                raise frappe.ValidationError("A handover must retain its issued source receipt")
            for field in ("company", "payment_type", "party_type", "party", "paid_from", "paid_to",
                          "paid_amount", "received_amount", "posting_date", "th_reception_collector",
                          "paid_from_account_currency", "paid_to_account_currency",
                          "source_exchange_rate", "target_exchange_rate",
                          "th_collection_fees", "th_collection_synthetic", "amended_from"):
                if doc.get(field) != before.get(field):
                    raise frappe.PermissionError("Handover cannot rewrite the student receipt")
    elif kind != "accept_reception_handover" or doc.payment_type != "Internal Transfer":
        raise frappe.ValidationError("A cash handover must be a native internal transfer")
