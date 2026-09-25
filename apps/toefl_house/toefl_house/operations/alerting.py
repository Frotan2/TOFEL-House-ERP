"""TH Alerting Policy: guarded receiver-policy commands (track 2, 2026-09-25).

Category B of the decision-classification rule (constitution §17):
selecting an alert receiver — and the retention / escalation policy
around it — is business policy, never an engineering constant (the
observability RECEIVER BOUNDARY declares exactly this owner decision).
Native Frappe provides delivery *mechanisms* (Notification/email,
Webhooks, realtime publish) but no versioned, ready-checked, fail-closed
receiver POLICY surface, and creating a native Notification row would
start delivering — which is exactly what recording a policy must not do.
This module is the guarded shell for that policy; it carries no value
for the owner and nothing here delivers anything.

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, ``governing_alerting_policy`` resolves to {} and
any alert-delivery mechanism must refuse. The owner opts in by
appending an effective-dated version, never by default. Each version
carries exactly the receiver terms — the channel kind (one of the
mechanisms engineering can qualify natively: Email / Webhook /
Dashboard; SMS has no native mechanism and is offered nowhere), the
owner-provided receiver destination string, the retention days
(required: retention is declared whenever a receiver is selected), and
the optional escalate-after minutes — plus the mandatory change reason.

Versions are append-only and monotone by effective date; a newer
version closes the predecessor's ``superseded_on`` without rewriting
it, so a future delivery mechanism can value-pin its governing receiver
terms at activation time, exactly like pinned correction terms.
Commands route through the receipted Course Owner gate
(business_policy authority); every mutation keeps its hash-chained
configuration audit event.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Alerting Policy"

# Technical option set: the delivery mechanisms engineering can qualify
# natively. The owner picks among them; SMS is absent because no native
# SMS mechanism exists at the pinned platform (that absence is
# deliberate, not an omission).
CHANNEL_KINDS = ("Email", "Webhook", "Dashboard")

# Technical typo-guard ceilings (named + tested, like the change-reason
# bound in configuration/rules.py). Not business values: they cap input
# size and magnitude, never content or policy.
RECEIVER_REFERENCE_MAX = 140
ESCALATION_MINUTES_MAX = 525600  # 366 days in minutes
RETENTION_DAYS_MIN = 1
RETENTION_DAYS_MAX = 3650


def validate_terms(channel_kind, receiver_reference, escalate_after_minutes,
                   retention_days):
    """Shape-check one policy version's receiver terms (command + controller).

    Returns (channel_kind, reference, escalate_after_minutes,
    retention_days) cleaned: text stripped, numeric strings coerced.
    Raises ValueError on anything outside the technical bounds; no owner
    value is ever synthesized.
    """
    if channel_kind not in CHANNEL_KINDS:
        raise ValueError(
            "Channel kind must be one of " + " / ".join(CHANNEL_KINDS))
    reference = str(
        receiver_reference if receiver_reference is not None else "").strip()
    if not (1 <= len(reference) <= RECEIVER_REFERENCE_MAX):
        raise ValueError(
            f"Receiver reference is required, at most "
            f"{RECEIVER_REFERENCE_MAX} characters")
    if escalate_after_minutes in (None, ""):
        escalate_after_minutes = None
    else:
        escalate_after_minutes = _coerce_int(escalate_after_minutes)
        if (isinstance(escalate_after_minutes, bool)
                or not isinstance(escalate_after_minutes, int)
                or not 1 <= escalate_after_minutes <= ESCALATION_MINUTES_MAX):
            raise ValueError(
                f"Escalate-after minutes must be a whole number between 1 "
                f"and {ESCALATION_MINUTES_MAX}, or empty for no escalation")
    retention_days = _coerce_int(retention_days)
    if (isinstance(retention_days, bool) or not isinstance(retention_days, int)
            or not RETENTION_DAYS_MIN <= retention_days <= RETENTION_DAYS_MAX):
        raise ValueError(
            f"Retention days must be a whole number between "
            f"{RETENTION_DAYS_MIN} and {RETENTION_DAYS_MAX}; retention is "
            "declared whenever a receiver is selected")
    return channel_kind, reference, escalate_after_minutes, retention_days


def _coerce_int(value):
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown alerting policy: {code}")
    return frappe.get_doc(POLICY, name, for_update=for_update)


def _as_bool(value, what):
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no"):
        return False
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{what} must be true or false")


def _policy_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
        "governing_channel_kind": (
            (governing.get("channel_kind") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_alerting_policy(on_date=None):
    """Read-only resolver: governing receiver terms, or {} when unset.

    No receipt: a pure read used inside command work() closures and by
    future alert-delivery consumers. Fail-closed in three ways — no
    policy row, retired policy, no effective version — and every one
    means alert delivery refuses. No owner value is ever synthesized
    here; the terms are reported exactly as configured.
    """
    rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
    if not rows:
        return {}
    doc = frappe.get_doc(POLICY, rows[0]["name"])
    if doc.status != "Active":
        return {}
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, on_date or frappe.utils.today())
    if not governing:
        return {}
    return {
        "effective_from": str(governing.get("effective_from") or ""),
        "channel_kind": governing.get("channel_kind") or "",
        "receiver_reference": governing.get("receiver_reference") or "",
        "escalate_after_minutes": governing.get("escalate_after_minutes"),
        "retention_days": governing.get("retention_days"),
    }


@frappe.whitelist(methods=["POST"])
def create_alerting_policy(request_key, code, title, description=""):
    """Define the alerting policy shell (receiver-policy mechanism).

    Creates the single policy row with NO versions: alert delivery stays
    refused until the Course Owner appends the first effective-dated
    version. The shell carries no receiver — the owner's selection
    arrives only through versions.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Alerting policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "An alerting policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Alerting policy {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": POLICY,
            "code": clean_code, "title": clean_title, "status": "Active",
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _policy_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "description": description}
    return configuration_audit.execute(
        "create_alerting_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_alerting_policy_version(request_key, policy, effective_from, reason,
                                channel_kind, receiver_reference,
                                retention_days, escalate_after_minutes=None):
    """Append an effective-dated alerting policy version.

    The version enacts one channel kind, one receiver reference and one
    retention term (plus an optional escalation) from ``effective_from``;
    a change reason is mandatory; backdated or same-day versions are
    refused. The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_channel, clean_reference, clean_escalate, clean_retention = (
                validate_terms(channel_kind, receiver_reference,
                               escalate_after_minutes, retention_days))
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Alerting policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="alerting policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "channel_kind": clean_channel,
            "receiver_reference": clean_reference,
            "escalate_after_minutes": clean_escalate,
            "retention_days": clean_retention,
            "reason": clean_reason, "set_by": actor,
            "set_on": frappe.utils.now_datetime()})
        if current:
            # Close the superseded version; never rewrite its meaning, only
            # record the date it stopped governing new activity.
            for row in doc.get("versions") or []:
                if (str(row.get("effective_from")) == str(current.get("effective_from"))
                        and not row.get("superseded_on")):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason, "channel_kind": channel_kind,
               "receiver_reference": receiver_reference,
               "retention_days": retention_days,
               "escalate_after_minutes": escalate_after_minutes}
    return configuration_audit.execute(
        "set_alerting_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_alerting_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the alerting policy.

    Retiring is the off-switch: with no active policy, alert delivery
    refuses again. Recorded versions and receipts are never rewritten by
    a later switch.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(versions)])
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "active": active}
    return configuration_audit.execute(
        "set_alerting_policy_status", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def validate_alerting_policy(request_key, policy):
    """Validate an alerting policy's structure and record evidence.

    Structural checks only: active policy, versions present and
    unambiguous, every row's terms well-formed (channel kind among the
    natively qualifiable mechanisms, receiver reference within bounds,
    retention declared, escalation within its bound). No completeness
    judgement is invented here. Success writes a validation audit event
    over the exact version snapshot; any later version change stales it
    automatically, returning readiness to ``configured``.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Alerting policy {clean_code} is retired; only active "
                "policies validate")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        if not versions:
            raise frappe.ValidationError(
                f"Alerting policy {clean_code} has no versions yet; add "
                "the first version before validating")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                versions, what="alerting policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in versions:
            try:
                validate_terms(row.get("channel_kind") or "",
                               row.get("receiver_reference") or "",
                               row.get("escalate_after_minutes"),
                               row.get("retention_days"))
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        before = configuration_audit.latest_after_hash(doc.name)
        after = configuration_rules.snapshot_digest(versions)
        readiness = configuration_rules.compute_readiness(
            status=doc.status, versions=versions,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="alerting policy")
        return _policy_result(doc, extra={"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy}
    return configuration_audit.execute(
        "validate_alerting_policy", request_key, payload, work)
