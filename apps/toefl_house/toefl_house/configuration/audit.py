"""Hash-chained command audit for configuration (governance boundary).

This reuses the placement Operation/Audit pattern — request-key
idempotency, input hash, receipt + event inside one retried transaction,
before/after hash chain per target — without the placement site-mode
machinery: configuration is governance state, deliberately NOT
synthetic-gated, the same boundary as ``toefl_house.administration`` and
the academic control plane. No safety control or evidence gate reads or
writes this ledger; production authorization never flows through it.

Ledger: ``TH Configuration Operation`` (idempotency receipt) +
``TH Configuration Audit Event`` (hash-chained trail). Both are read-only
for every role; only the guarded configuration commands write them,
inside the bound-authority gate, and the controllers keep receipts
immutable and events append-only.
"""
import json

import frappe

from toefl_house.configuration import rules as foundation
from toefl_house.policy import (canonical, digest, request_digest,
                                validate_request_key)
from toefl_house.transactions import run_with_retry

OPERATION = "TH Configuration Operation"
AUDIT = "TH Configuration Audit Event"

# Command kind -> bound authority. Only kinds listed here may write the
# ledger; the authority must be bound in foundation.AUTHORITIES or the
# command refuses. The D1 configuration commands (policy shell, versions,
# status, validation, and the seven facet setters) bind here, as do the
# twelve academic catalog commands (S5 idempotency: they validate keys
# and now keep receipts, so a retried call replays instead of erroring).
KIND_AUTHORITY = {
    "create_assessment_policy": "business_policy",
    "set_assessment_policy_version": "business_policy",
    "set_assessment_policy_status": "business_policy",
    "validate_assessment_policy": "business_policy",
    "set_assessment_components": "business_policy",
    "set_assessment_weights": "business_policy",
    "set_assessment_pass_rules": "business_policy",
    "set_assessment_rubrics": "business_policy",
    "set_assessment_progression": "business_policy",
    "set_assessment_retakes": "business_policy",
    "set_assessment_mapping": "business_policy",
    "create_program": "business_policy",
    "create_level": "business_policy",
    "set_level_duration": "business_policy",
    "set_next_level": "business_policy",
    "set_program_status": "business_policy",
    "set_level_status": "business_policy",
    "create_academic_year": "business_policy",
    "create_fee_type": "business_policy",
    "set_level_fee_component": "business_policy",
    "remove_level_fee_component": "business_policy",
    "create_discount_rule": "business_policy",
    "set_discount_rule_status": "business_policy",
    "create_returning_student_policy": "business_policy",
    "set_returning_student_policy_version": "business_policy",
    "set_returning_student_policy_status": "business_policy",
    "create_roster_change_policy": "business_policy",
    "set_roster_change_policy_version": "business_policy",
    "set_roster_change_policy_status": "business_policy",
    "create_attendance_correction_policy": "business_policy",
    "set_attendance_correction_policy_version": "business_policy",
    "set_attendance_correction_policy_status": "business_policy",
    "create_enrollment_exit_policy": "business_policy",
    "set_enrollment_exit_policy_version": "business_policy",
    "set_enrollment_exit_policy_status": "business_policy",
    "create_billing_policy": "business_policy",
    "set_billing_policy_version": "business_policy",
    "set_billing_policy_status": "business_policy",
    "create_catalog_linkage_policy": "business_policy",
    "set_catalog_linkage_version": "business_policy",
    "set_catalog_linkage_status": "business_policy",
    "create_adjustment_posting_policy": "business_policy",
    "set_adjustment_posting_version": "business_policy",
    "set_adjustment_posting_status": "business_policy",
    "create_metric_stewardship_policy": "business_policy",
    "set_metric_stewardship_policy_version": "business_policy",
    "set_metric_stewardship_policy_status": "business_policy",
    "validate_metric_stewardship_policy": "business_policy",
}


def require_authority(authority):
    """The acting-role gate for configuration commands.

    Governance boundary: the viewer invariants mirror
    ``toefl_house.security.authorize`` (explicitly assigned,
    non-administrator, enabled actor holding the bound role) but the site
    activation gate deliberately does NOT apply — exactly like the
    academic control plane and the administration surface.
    """
    try:
        roles = foundation.require_bound_authority(authority)
    except ValueError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    user = frappe.session.user
    if (user in (None, "Guest", "Administrator")
            or not set(roles) & set(frappe.get_roles(user))):
        names = " or ".join(roles)
        raise frappe.PermissionError(
            f"Configuration under the {authority} authority needs the "
            f"{names} role; ask them for this change")
    if not frappe.db.get_value("User", user, "enabled"):
        raise frappe.PermissionError("Actor has been disabled")
    return user


def latest_after_hash(target):
    """The most recent after-hash for a target, or "" when none exists.

    Reads the tail of the chain (newest first, one row): the before-hash
    of the next event, keeping the per-target chain continuous.
    """
    rows = frappe.db.get_all(
        AUDIT, filters={"target": target}, fields=["after_hash"],
        order_by="creation desc", limit_page_length=1)
    return rows[-1]["after_hash"] if rows else ""


def execute(kind, request_key, payload, work):
    """Run a configuration command with idempotency + hash-chained audit.

    ``work`` is a closure receiving the gated actor and returning
    ``(result, event)`` where event carries target/before_hash/after_hash.
    A replayed (kind, request_key) with the identical payload returns the
    recorded result instead of double-applying; a conflicting payload
    under the same key is refused.
    """
    return run_with_retry(
        lambda: _execute_once(kind, request_key, payload, work))


def _execute_once(kind, request_key, payload, work):
    authority = KIND_AUTHORITY.get(kind)
    if authority is None:
        raise frappe.PermissionError(
            f"Unknown configuration command: {kind}")
    actor = require_authority(authority)
    # The command context is what the controllers require: every write
    # below (receipt, policy mutation, audit event) happens inside it, so
    # any save attempted outside a command — native form, REST, import —
    # meets the controllers' business-language refusal instead.
    with foundation.command_context(kind):
        return _apply_once(kind, request_key, payload, work, actor)


def _apply_once(kind, request_key, payload, work, actor):
    try:
        validate_request_key(request_key)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    op_name = digest([kind, request_key])
    try:
        input_hash = request_digest(payload, frappe.conf.get("encryption_key"))
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc

    def existing():
        row = frappe.db.get_value(
            OPERATION, op_name, ["actor", "input_hash", "status",
                                 "result_json"],
            as_dict=True, for_update=True)
        if (not row or row.actor != actor or row.input_hash != input_hash
                or row.status != "Complete"):
            raise frappe.ValidationError(
                "Idempotency key conflicts with an existing request")
        return json.loads(row.result_json)

    if frappe.db.exists(OPERATION, op_name):
        return existing()
    op = frappe.get_doc(dict(doctype=OPERATION, name=op_name, kind=kind,
                             actor=actor, input_hash=input_hash,
                             status="Applying"))
    try:
        op.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        return existing()
    result, event = work(actor)
    target = (event or {}).get("target") or ""
    before = (event or {}).get("before_hash") or ""
    after = (event or {}).get("after_hash") or ""
    if not target or not after:
        raise frappe.ValidationError(
            "Configuration audit requires a target and an after-hash")
    frappe.get_doc(dict(doctype=AUDIT, actor=actor, operation=op.name,
                        action=kind, target=target, before_hash=before,
                        after_hash=after)).insert(ignore_permissions=True)
    op.status = "Complete"
    op.result_json = canonical(result)
    op.save(ignore_permissions=True)
    # Do not commit here: receipt + mutation + audit are one request
    # transaction, exactly like the placement command pattern.
    return result
