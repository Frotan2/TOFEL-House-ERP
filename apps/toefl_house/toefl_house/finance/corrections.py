"""D3 correction framework (owner: "framework approved; exact terms later").

Fail-closed by construction: with no Active TH Correction Policy every
new correction request is denied, and the policy's approval terms
(approver role, correction window) are owner-entered configuration -
nothing here supplies a default term, amount, tax or refund rule.

Policy terms are append-only, effective-dated VERSIONS (D1 mechanics on
the Finance authority track): reconfiguring appends a strictly later
version and supersedes - never rewrites - the previous one. Each
correction request pins the version governing its creation date, and
approvals judge policy terms against that pinned version even after it
is superseded or the policy is retired. Live document facts (existence,
submitted state, totals) are always re-proven against the live document.

Scope v1: full-amount corrections of TH placement Sales Invoices through
the NATIVE credit-note mechanism (erpnext make_sales_return -> a Sales
Invoice with is_return=1 and return_against set), and full-amount tuition
Fees corrections through native Fees cancellation. Partial refunds await
the owner's exact terms and are refused with an explicit message rather
than approximated. No parallel ledger: the request row carries facts and
the decision trail; the native money artifact (credit note or fee
cancellation) is the only posting.
"""
from datetime import date, timedelta
import frappe
from toefl_house.api import _execute
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import (CORRECTION_POLICY_STATUSES, digest,
                                validate_correction_window_days,
                                validate_schedule_date)
from toefl_house.security import record_synthetic_flag

POLICY = "TH Correction Policy"
REQUEST = "TH Correction Request"
INVOICE = "Sales Invoice"
FEES = "Fees"
AUDIT = "TH Placement Audit Event"
# The singleton policy is one audit stream: every configure/status/
# validate event targets this stable key (the target column is free
# text), so the per-target hash chain spans versions instead of ending
# at each version row. Request events keep targeting their request row.
POLICY_STREAM = "TH Correction Policy"
POLICY_FIELDS = ["name", "approver_role", "correction_window_days",
                 "effective_from", "reason", "set_by", "set_on",
                 "superseded_on", "status", "synthetic"]


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def _policy_rows():
    """All correction policy versions as plain rows, unsorted."""
    return [dict(row) for row in frappe.db.get_all(
        POLICY, filters={}, fields=POLICY_FIELDS)]


def _governing_policy(rows, on_date):
    """The policy version governing new requests on a date.

    The latest version must be Active (a retired policy fails closed for
    new requests exactly as before); among all versions, the one
    governing the date may be a superseded row whose successor is still
    scheduled - superseded rows keep governing their own dates.
    """
    latest = configuration_rules.latest_version(rows or [])
    if latest is None or latest.get("status") != "Active":
        raise frappe.ValidationError(
            "No active correction policy; corrections fail closed until one is configured")
    try:
        governing = configuration_rules.resolve_governing_strict(
            rows, on_date, what="correction policy version")
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if governing is None:
        raise frappe.ValidationError(
            "No correction policy version is effective yet; the latest "
            "version is scheduled for the future")
    return governing


def _pinned_policy(req):
    """The version a request pinned at creation, re-read defensively.

    The pin is what approvals judge terms against, so a version row that
    disappeared after the request was raised fails closed with a repair
    path instead of falling back to whatever is current.
    """
    pinned = req.get("correction_policy")
    if not pinned:
        raise frappe.ValidationError(
            "This correction request predates versioned policy; raise a "
            "new request under the current policy version")
    try:
        return frappe.get_doc(POLICY, pinned)
    except frappe.DoesNotExistError as exc:
        raise frappe.ValidationError(
            "The correction policy version behind this request no longer "
            "exists; raise a new request under the current policy version"
        ) from exc


def _stream_after_hash():
    """The tail after-hash of the policy audit stream, or "" when none."""
    rows = frappe.db.get_all(AUDIT, filters={"target": POLICY_STREAM},
                             fields=["after_hash"], order_by="creation asc")
    rows = list(rows or [])
    return rows[-1]["after_hash"] if rows else ""


def _require_approver(policy, actor):
    if policy.get("approver_role") not in frappe.get_roles(actor):
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
def configure_correction_policy(request_key, approver_role,
                                correction_window_days, effective_from,
                                reason):
    """Append an effective-dated correction policy version.

    Versions the existing business terms only (approver role, correction
    window). The new version must start strictly after the latest one;
    every previous Active version is superseded (Retired, closed with the
    new effective date) rather than edited. At most one Active version
    exists. The unique effective date is the serialization backstop: a
    concurrent same-date append fails closed with a business message.
    """
    def work(actor):
        role = _name(approver_role, "Approver role")
        try:
            days = validate_correction_window_days(correction_window_days)
            clean_from = validate_schedule_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("Role", role):
            raise frappe.ValidationError("Unknown role")
        rows = _policy_rows()
        for row in rows:
            frappe.db.sql("select name from `tabTH Correction Policy` where name=%s for update",
                          (row["name"],))
        try:
            configuration_rules.check_appends(
                rows, clean_from, what="correction policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in rows:
            if row.get("status") != "Active":
                continue
            old = frappe.get_doc(POLICY, row["name"])
            old.flags.ignore_permissions = True
            old.status = "Retired"
            old.superseded_on = clean_from
            old.save(ignore_permissions=True)
        policy = frappe.get_doc(dict(
            doctype=POLICY, approver_role=role,
            correction_window_days=days, effective_from=clean_from,
            reason=clean_reason, set_by=actor,
            set_on=frappe.utils.now_datetime(), status="Active",
            synthetic=record_synthetic_flag()))
        policy.flags.ignore_permissions = True
        try:
            policy.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError as exc:
            raise frappe.ValidationError(
                "A correction policy version with this effective date was "
                "just recorded; retry with a later date") from exc
        before = _stream_after_hash()
        after = configuration_rules.snapshot_digest(_policy_rows())
        result = {"name": policy.name, "approver_role": role,
                  "correction_window_days": days,
                  "effective_from": clean_from, "status": "Active"}
        return result, dict(target=POLICY_STREAM, before_hash=before,
                            after_hash=after)

    return _execute("configure_correction_policy", request_key,
                    {"approver_role": approver_role,
                     "correction_window_days": correction_window_days,
                     "effective_from": effective_from,
                     "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def set_correction_policy_status(request_key, status):
    """Retire or reactivate the correction policy (latest version only).

    Retiring fails new requests closed until reactivation; requests
    already raised keep resolving their pinned version. Older
    (superseded) versions are never touched.
    """
    def work(actor):
        if status not in CORRECTION_POLICY_STATUSES:
            raise frappe.ValidationError(
                "Unknown correction policy status: "
                f"{status!r} (expected Active or Retired)")
        rows = _policy_rows()
        latest = configuration_rules.latest_version(rows)
        if latest is None:
            raise frappe.ValidationError(
                "No correction policy is configured yet")
        frappe.db.sql("select name from `tabTH Correction Policy` where name=%s for update",
                      (latest["name"],))
        doc = frappe.get_doc(POLICY, latest["name"])
        if doc.status == status:
            raise frappe.ValidationError(
                f"Correction policy is already {status}")
        doc.flags.ignore_permissions = True
        doc.status = status
        doc.save(ignore_permissions=True)
        before = _stream_after_hash()
        after = configuration_rules.snapshot_digest(_policy_rows())
        result = {"name": doc.name, "status": status}
        return result, dict(target=POLICY_STREAM, before_hash=before,
                            after_hash=after)

    return _execute("set_correction_policy_status", request_key,
                    {"status": status}, work)


@frappe.whitelist(methods=["POST"])
def validate_correction_policy(request_key):
    """Validate the correction policy's structure and record the evidence.

    Structural checks only: an Active latest version exists, versions are
    present and unambiguous, at most one version is Active, and every
    row's terms still resolve (approver role still exists, window still
    well-formed). Success writes a validation audit event over the exact
    version snapshot; any later version change stales it automatically,
    returning readiness to ``configured``.
    """
    def work(actor):
        rows = _policy_rows()
        latest = configuration_rules.latest_version(rows)
        if latest is None:
            raise frappe.ValidationError(
                "No correction policy is configured yet; configure the "
                "first version before validating")
        if latest.get("status") != "Active":
            raise frappe.ValidationError(
                "Correction policy is retired; only active policies validate")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                rows, what="correction policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        actives = [row for row in rows if row.get("status") == "Active"]
        if len(actives) > 1:
            raise frappe.ValidationError(
                "Two correction policy versions are Active; history is "
                "ambiguous until the configuration is repaired")
        for row in rows:
            role = row.get("approver_role") or ""
            if not frappe.db.exists("Role", role):
                raise frappe.ValidationError(
                    f"Role {role} no longer exists; repair the policy "
                    "version before validating")
            try:
                validate_correction_window_days(
                    row.get("correction_window_days"))
            except ValueError as exc:
                raise frappe.ValidationError(
                    "Correction policy version effective "
                    f"{row.get('effective_from')} carries an invalid "
                    f"window; repair the policy version: {exc}") from exc
        before = _stream_after_hash()
        after = configuration_rules.snapshot_digest(rows)
        readiness = configuration_rules.compute_readiness(
            status=latest.get("status"), versions=rows,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="correction policy")
        result = {"versions": len(rows), "readiness": readiness,
                  "latest_effective_from": latest.get("effective_from")}
        return result, dict(target=POLICY_STREAM, before_hash=before,
                            after_hash=after)

    return _execute("validate_correction_policy", request_key, {}, work)


@frappe.whitelist(methods=["POST"])
def request_invoice_correction(request_key, sales_invoice, reason, requested_amount):
    """Open a correction request for a TH placement invoice.

    v1 validates full-amount corrections inside the policy window;
    partial amounts are refused until the owner defines partial terms.
    The version governing today is pinned onto the request, so later
    policy changes never reinterpret this request.
    """
    def work(actor):
        governing = _governing_policy(_policy_rows(), frappe.utils.today())
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
            days=int(governing["correction_window_days"]))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this invoice has closed")
        if frappe.db.exists(REQUEST, {"sales_invoice": si_name,
                                      "status": ("in", ("Requested", "Posted"))}):
            raise frappe.ValidationError(
                "Invoice already has an open or posted correction request")
        if frappe.db.exists(INVOICE, {"return_against": si_name, "docstatus": ("!=", 2)}):
            raise frappe.ValidationError("Invoice already has a credit note")
        request = frappe.get_doc(dict(
            doctype=REQUEST, sales_invoice=si_name,
            correction_policy=governing["name"], reason=reason,
            requested_amount=round(float(requested_amount), 2),
            status="Requested", synthetic=record_synthetic_flag()))
        request.flags.ignore_permissions = True
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        result = {"name": request.name, "sales_invoice": si_name,
                  "correction_policy": governing["name"],
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

    Request and approval are separate commands. The invoice is locked and
    the request-time invariants are re-proven here, the same way
    approve_fees_correction re-proves the fee: a stale approval would post
    a credit note whose amount no longer matches the live invoice.
    Policy terms (approver role, window) come from the version the
    request pinned at creation, never from whatever is current.
    """
    def work(actor):
        req = _pending_request(_name(request, "Correction request"))
        terms = _pinned_policy(req)
        _require_approver(terms, actor)
        if not req.sales_invoice:
            raise frappe.ValidationError("Correction request is not for an invoice")
        frappe.db.sql("select name from `tabSales Invoice` where name=%s for update",
                      (req.sales_invoice,))
        si = frappe.db.get_value(INVOICE, req.sales_invoice,
                                 ["docstatus", "is_return", "th_placement_case",
                                  "grand_total", "posting_date"], as_dict=True)
        if not si:
            raise frappe.ValidationError(
                "The invoice behind this correction request no longer exists")
        if int(si.docstatus or 0) != 1 or int(si.is_return or 0) == 1:
            raise frappe.ValidationError(
                "The invoice is no longer submitted; this correction request "
                "can no longer be approved")
        if not si.th_placement_case:
            raise frappe.ValidationError(
                "Only TH placement invoices are correctable in this framework version")
        if round(float(si.grand_total), 2) != round(float(req.requested_amount), 2):
            raise frappe.ValidationError(
                "The invoice total changed after this request was raised; v1 corrects "
                "the full invoice amount, so raise a new request for the current total")
        limit = date.fromisoformat(str(si.posting_date)) + timedelta(
            days=int(terms.correction_window_days))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this invoice has closed")
        if frappe.db.exists(INVOICE, {"return_against": req.sales_invoice,
                                      "docstatus": ("!=", 2)}):
            raise frappe.ValidationError("Invoice already has a credit note")
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
    """Deny a pending request; no money artifact is produced.

    The approver role comes from the version the request pinned at
    creation, never from whatever is current.
    """
    def work(actor):
        req = _pending_request(_name(request, "Correction request"))
        terms = _pinned_policy(req)
        _require_approver(terms, actor)
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
    The version governing today is pinned onto the request, so later
    policy changes never reinterpret this request.
    """
    def work(actor):
        governing = _governing_policy(_policy_rows(), frappe.utils.today())
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
            days=int(governing["correction_window_days"]))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this fee has closed")
        if frappe.db.exists(REQUEST, {"fees": fee_name,
                                      "status": ("in", ("Requested", "Posted"))}):
            raise frappe.ValidationError("Fee already has an open or posted correction request")
        request = frappe.get_doc(dict(
            doctype=REQUEST, fees=fee_name,
            correction_policy=governing["name"], reason=reason,
            requested_amount=round(float(requested_amount), 2),
            status="Requested", synthetic=record_synthetic_flag()))
        request.flags.ignore_permissions = True
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        result = {"name": request.name, "fees": fee_name,
                  "correction_policy": governing["name"],
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
    reverses the GL receivable without any parallel ledger. Policy terms
    (approver role, window) come from the version the request pinned at
    creation, never from whatever is current.
    """
    def work(actor):
        req = _pending_request(_name(request, "Correction request"))
        terms = _pinned_policy(req)
        _require_approver(terms, actor)
        if not req.fees:
            raise frappe.ValidationError("Correction request is not for a Fees record")
        # Re-validate the fee at approval time, under the same row lock the
        # request used. Request and approval are separate commands that can be
        # separated by any interval, so the invariants proven at request time
        # cannot be assumed to still hold: the fee could have been amended, its
        # total could have changed, or the correction window could have closed.
        # Approving on stale state would cancel a fee whose amount no longer
        # equals the recorded requested_amount while still reporting that amount
        # as the refund - an inaccurate financial record. These are the same
        # checks the request performed; nothing new is being decided here.
        frappe.db.sql("select name from `tabFees` where name=%s for update", (req.fees,))
        fee_row = frappe.db.get_value(FEES, req.fees,
                                      ["docstatus", "grand_total", "posting_date"],
                                      as_dict=True)
        if not fee_row:
            raise frappe.ValidationError("The fee behind this correction request no longer exists")
        if int(fee_row.docstatus or 0) != 1:
            raise frappe.ValidationError(
                "The fee is no longer submitted; this correction request can no longer be approved")
        if round(float(fee_row.grand_total), 2) != round(float(req.requested_amount), 2):
            raise frappe.ValidationError(
                "The fee total changed after this request was raised; v1 corrects the full fee "
                "amount, so raise a new request for the current total")
        limit = date.fromisoformat(str(fee_row.posting_date)) + timedelta(
            days=int(terms.correction_window_days))
        if date.today() > limit:
            raise frappe.ValidationError("Correction window for this fee has closed")
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
    """Deny a pending Fees correction request; no money artifact is produced.

    The approver role comes from the version the request pinned at
    creation, never from whatever is current.
    """
    def work(actor):
        req = _pending_request(_name(request, "Correction request"))
        terms = _pinned_policy(req)
        _require_approver(terms, actor)
        req.flags.ignore_permissions = True
        req.status = "Denied"
        req.approved_by = actor
        req.save(ignore_permissions=True)
        result = {"name": req.name, "status": "Denied"}
        return result, dict(target=req.name,
                            before_hash=digest([req.name, "Requested"]),
                            after_hash=digest([req.name, "Denied"]))

    return _execute("deny_fees_correction", request_key, {"request": request}, work)

