"""D3 correction framework (owner: "framework approved; exact terms later").

Fail-closed by construction: with no Active TH Correction Policy every
correction command is denied, and the policy's approval terms (approver
role, correction window) are owner-entered configuration - nothing here
supplies a default term, amount, tax or refund rule.

Scope v1: full-amount corrections of TH placement Sales Invoices through
the NATIVE credit-note mechanism (erpnext make_sales_return -> a Sales
Invoice with is_return=1 and return_against set). Partial refunds and
Fees-side corrections await the owner's exact terms and are refused with
an explicit message rather than approximated. No parallel ledger: the
request row carries facts and the decision trail; the native credit note
is the only money artifact.
"""
from datetime import date, timedelta
import frappe
from toefl_house.api import _execute
from toefl_house.policy import digest, validate_correction_window_days

POLICY = "TH Correction Policy"
REQUEST = "TH Correction Request"
INVOICE = "Sales Invoice"
FEES = "Fees"


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def _active_policy():
    rows = frappe.db.get_all(POLICY, filters={"status": "Active"}, fields=["name"])
    if not rows:
        raise frappe.ValidationError(
            "No active correction policy; corrections fail closed until one is configured")
    name = rows[0]["name"] if isinstance(rows[0], dict) else rows[0].name
    return frappe.get_doc(POLICY, name)


def _require_approver(policy, actor):
    if policy.approver_role not in frappe.get_roles(actor):
        raise frappe.PermissionError("Actor does not hold the policy-configured approver role")


def _pending_request(req_name):
    if not frappe.db.exists(REQUEST, req_name):
        raise frappe.ValidationError("Unknown correction request")
    frappe.db.sql("select name from `tabTH Correction Request` where name=%s for update",
                  (req_name,))
    req = frappe.get_doc(REQUEST, req_name)
    if req.status != "Requested":
        raise frappe.ValidationError("Correction request is not pending")
    return req


@frappe.whitelist(methods=["POST"])
def configure_correction_policy(request_key, approver_role, correction_window_days):
    """Record the owner's correction approval terms (configuration carrier).

    At most one Active policy exists; reconfiguring retires the previous
    policy (immutable, audited) rather than editing it.
    """
    def work(actor):
        role = _name(approver_role, "Approver role")
        try:
            days = validate_correction_window_days(correction_window_days)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("Role", role):
            raise frappe.ValidationError("Unknown role")
        for row in frappe.db.get_all(POLICY, filters={"status": "Active"}, fields=["name"]):
            frappe.db.sql("select name from `tabTH Correction Policy` where name=%s for update",
                          (row.name,))
            old = frappe.get_doc(POLICY, row.name)
            old.flags.ignore_permissions = True
            old.status = "Retired"
            old.save(ignore_permissions=True)
        policy = frappe.get_doc(dict(doctype=POLICY, approver_role=role,
                                     correction_window_days=days, status="Active",
                                     synthetic=1))
        policy.flags.ignore_permissions = True
        policy.insert(ignore_permissions=True)
        result = {"name": policy.name, "approver_role": role,
                  "correction_window_days": days, "status": "Active"}
        return result, dict(target=policy.name,
                            after_hash=digest([policy.name, role, days]))

    return _execute("configure_correction_policy", request_key,
                    {"approver_role": approver_role,
                     "correction_window_days": correction_window_days}, work)


@frappe.whitelist(methods=["POST"])
def request_invoice_correction(request_key, sales_invoice, reason, requested_amount):
    """Open a correction request for a TH placement invoice.

    v1 validates full-amount corrections inside the policy window;
    partial amounts are refused until the owner defines partial terms.
    """
    def work(actor):
        policy = _active_policy()
        si_name = _name(sales_invoice, "Sales invoice")
        if not isinstance(reason, str) or not reason or len(reason) > 300:
            raise frappe.ValidationError("Reason required")
        if (isinstance(requested_amount, bool)
                or not isinstance(requested_amount, (int, float))
                or float(requested_amount) <= 0):
            raise frappe.ValidationError("Requested amount must be a positive number")
        if not frappe.db.exists(INVOICE, si_name):
            raise frappe.ValidationError("Unknown sales invoice")
        frappe.db.sql("select name from `tabSales Invoice` where name=%s for update",
                      (si_name,))
        si = frappe.db.get_value(INVOICE, si_name,
                                 ["docstatus", "is_return", "th_placement_case",
                                  "grand_total", "posting_date"], as_dict=True)
        if int(si.docstatus or 0) != 1 or int(si.is_return or 0) == 1:
            raise frappe.ValidationError("Corrections require a submitted original invoice")
        if not si.th_placement_case:
            raise frappe.ValidationError(
                "Only TH placement invoices are correctable in this framework version")
        if round(float(si.grand_total), 2) != round(float(requested_amount), 2):
            raise frappe.ValidationError(
                "Partial corrections await owner-defined terms; "
                "v1 corrects the full invoice amount")
        limit = date.fromisoformat(str(si.posting_date)) + timedelta(
            days=int(policy.correction_window_days))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this invoice has closed")
        if frappe.db.exists(REQUEST, {"sales_invoice": si_name,
                                      "status": ("in", ("Requested", "Posted"))}):
            raise frappe.ValidationError(
                "Invoice already has an open or posted correction request")
        if frappe.db.exists(INVOICE, {"return_against": si_name, "docstatus": ("!=", 2)}):
            raise frappe.ValidationError("Invoice already has a credit note")
        request = frappe.get_doc(dict(
            doctype=REQUEST, sales_invoice=si_name, reason=reason,
            requested_amount=round(float(requested_amount), 2),
            status="Requested", synthetic=1))
        request.flags.ignore_permissions = True
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        result = {"name": request.name, "sales_invoice": si_name,
                  "requested_amount": round(float(requested_amount), 2),
                  "status": "Requested"}
        return result, dict(target=request.name,
                            after_hash=digest([request.name, si_name,
                                               round(float(requested_amount), 2)]))

    return _execute("request_invoice_correction", request_key,
                    {"sales_invoice": sales_invoice, "reason": reason,
                     "requested_amount": requested_amount}, work)


@frappe.whitelist(methods=["POST"])
def approve_invoice_correction(request_key, request):
    """Approve and post the correction as a native credit note.

    Dual key: command access (Finance Officer) plus the policy-configured
    approver role. The money artifact is the native credit note produced
    by erpnext make_sales_return; the request row only records the
    decision trail (approver, credit-note link).
    """
    def work(actor):
        policy = _active_policy()
        _require_approver(policy, actor)
        req = _pending_request(_name(request, "Correction request"))
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
        note = make_sales_return(req.sales_invoice)
        note.flags.ignore_permissions = True
        note.flags.ignore_links = True
        note.insert(ignore_permissions=True)
        note.flags.ignore_permissions = True
        note.submit()
        if int(note.is_return or 0) != 1 or note.return_against != req.sales_invoice:
            raise frappe.ValidationError("Native credit note was not produced")
        if round(float(note.grand_total), 2) != -round(float(req.requested_amount), 2):
            raise frappe.ValidationError(
                "Credit note amount does not match the approved request")
        req.flags.ignore_permissions = True
        req.status = "Posted"
        req.approved_by = actor
        req.credit_note = note.name
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Posted", "credit_note": note.name,
                  "credit_total": round(float(note.grand_total), 2)}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Posted", note.name]))

    return _execute("approve_invoice_correction", request_key, {"request": request}, work)


@frappe.whitelist(methods=["POST"])
def deny_invoice_correction(request_key, request):
    """Deny a pending request; no money artifact is produced."""
    def work(actor):
        policy = _active_policy()
        _require_approver(policy, actor)
        req = _pending_request(_name(request, "Correction request"))
        req.flags.ignore_permissions = True
        req.status = "Denied"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Denied"}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Denied"]))

    return _execute("deny_invoice_correction", request_key, {"request": request}, work)


@frappe.whitelist(methods=["POST"])
def request_fees_correction(request_key, fees, reason, requested_amount):
    """Open a correction request for an issued tuition Fees document.

    Under OD-CP-2 Option B: full-amount corrections only inside the policy
    window; partial amounts are refused until the owner defines partial terms.
    """
    def work(actor):
        policy = _active_policy()
        fee_name = _name(fees, "Fees")
        if not isinstance(reason, str) or not reason or len(reason) > 300:
            raise frappe.ValidationError("Reason required")
        if (isinstance(requested_amount, bool)
                or not isinstance(requested_amount, (int, float))
                or float(requested_amount) <= 0):
            raise frappe.ValidationError("Requested amount must be a positive number")
        if not frappe.db.exists(FEES, fee_name):
            raise frappe.ValidationError("Unknown fee")
        frappe.db.sql("select name from `tabFees` where name=%s for update", (fee_name,))
        fee_row = frappe.db.get_value(FEES, fee_name,
                                      ["docstatus", "grand_total", "posting_date"],
                                      as_dict=True)
        if int(fee_row.docstatus or 0) != 1:
            raise frappe.ValidationError("Corrections require a submitted fee")
        if round(float(fee_row.grand_total), 2) != round(float(requested_amount), 2):
            raise frappe.ValidationError(
                "Partial corrections await owner-defined terms; "
                "v1 corrects the full fee amount")
        limit = date.fromisoformat(str(fee_row.posting_date)) + timedelta(
            days=int(policy.correction_window_days))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this fee has closed")
        if frappe.db.exists(REQUEST, {"fees": fee_name,
                                      "status": ("in", ("Requested", "Posted"))}):
            raise frappe.ValidationError("Fee already has an open or posted correction request")
        request = frappe.get_doc(dict(
            doctype=REQUEST, fees=fee_name, reason=reason,
            requested_amount=round(float(requested_amount), 2),
            status="Requested", synthetic=1))
        request.flags.ignore_permissions = True
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        result = {"name": request.name, "fees": fee_name,
                  "requested_amount": round(float(requested_amount), 2),
                  "status": "Requested"}
        return result, dict(target=request.name,
                            after_hash=digest([request.name, fee_name,
                                               round(float(requested_amount), 2)]))

    return _execute("request_fees_correction", request_key,
                    {"fees": fees, "reason": reason,
                     "requested_amount": requested_amount}, work)


@frappe.whitelist(methods=["POST"])
def approve_fees_correction(request_key, request):
    """Approve and post the tuition Fees correction natively.

    Dual key: Finance Officer command gate plus the policy-configured approver
    role. The native money artifact is native Fees cancellation, which
    reverses the GL receivable without any parallel ledger.
    """
    def work(actor):
        policy = _active_policy()
        _require_approver(policy, actor)
        req = _pending_request(_name(request, "Correction request"))
        if not req.fees:
            raise frappe.ValidationError("Correction request is not for a Fees record")
        fee_doc = frappe.get_doc(FEES, req.fees)
        fee_doc.flags.ignore_permissions = True
        fee_doc.cancel()
        req.flags.ignore_permissions = True
        req.status = "Posted"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Posted", "fees": req.fees,
                  "refunded_total": round(float(req.requested_amount), 2)}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Posted", req.fees]))

    return _execute("approve_fees_correction", request_key, {"request": request}, work)


@frappe.whitelist(methods=["POST"])
def deny_fees_correction(request_key, request):
    """Deny a pending Fees correction request; no money artifact is produced."""
    def work(actor):
        policy = _active_policy()
        _require_approver(policy, actor)
        req = _pending_request(_name(request, "Correction request"))
        req.flags.ignore_permissions = True
        req.status = "Denied"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Denied"}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Denied"]))

    return _execute("deny_fees_correction", request_key, {"request": request}, work)

