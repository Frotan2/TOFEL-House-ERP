"""S11 billing policy (OD-NEW-03/OD-NEW-04): effective-dated owner bounds
for billing dates and placement-fee timing (S7/S8/S9/S10 singleton
mechanics).

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, billing is denied — the owner opts in by
appending a version, never by default. Both billing commands read the
governing terms live (S8-cutoff precedent; no pinning — a bill judges
the terms in force on its posting date, never older ones).

Terms per version: how far back a posting date may reach
(max_backdate_days), how far forward it may reach (max_future_days),
and the pipeline progress a case must show before its placement fee
bills (placement_fee_timing). Due dates stay unbounded native terms:
only the booking date is bounded, never the commercial term.
"""

from datetime import date
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import ATTEMPT_STATUSES, digest

POLICY = "TH Billing Policy"
ATTEMPT = "TH Placement Attempt"
DECISION = "TH Placement Decision"

ANY_PROGRESS = "any"
RELEASED = "released"
TIMING_CHOICES = (ANY_PROGRESS,) + tuple(ATTEMPT_STATUSES) + (RELEASED,)
DAY_BOUND_MAX = 366


def validate_day_bound(value, what):
    """A day bound is a non-negative integer within one year.

    The year cap is a mechanism guardrail, not policy: the owner picks
    any bound inside it, and multi-year backbilling is a data-migration
    conversation, never daily billing.
    """
    if isinstance(value, bool) or not isinstance(value, int) or not (
            0 <= value <= DAY_BOUND_MAX):
        raise ValueError(
            f"{what} must be an integer number of days (0-{DAY_BOUND_MAX})")
    return value


def validate_timing(timing):
    """Shape-check the placement-fee timing vocabulary (command + controller).

    ``any`` bills at any pipeline progress (upfront); a native attempt
    stage bills once any of the case's attempts reaches it; ``released``
    bills once a decision is released for the case. Stages and their
    order are the native attempt ladder, never invented here.
    """
    if timing not in TIMING_CHOICES:
        raise ValueError(
            "Placement-fee timing must be one of: "
            + ", ".join(TIMING_CHOICES))
    return timing


def validate_terms(backdate_days, future_days, timing):
    """Shape-check one policy version's terms (command + controller)."""
    back = validate_day_bound(backdate_days, "Max backdate days")
    fut = validate_day_bound(future_days, "Max future days")
    return back, fut, validate_timing(timing)


def check_posting_bounds(posting, today, backdate_days, future_days):
    """Refuse a posting date outside the owner's backdate/future bounds."""
    posted = date.fromisoformat(str(posting))
    now = date.fromisoformat(str(today))
    if (now - posted).days > int(backdate_days):
        raise ValueError(
            f"Posting date {posted} is more than {backdate_days} days back")
    if (posted - now).days > int(future_days):
        raise ValueError(
            f"Posting date {posted} is more than {future_days} days forward")


def check_fee_timing(case, timing):
    """Refuse a placement-fee bill while the case is below the threshold."""
    if timing == ANY_PROGRESS:
        return
    attempts = frappe.db.get_all(
        ATTEMPT, filters={"case_name": case}, fields=["name", "status"])
    if timing == RELEASED:
        names = [row["name"] for row in attempts]
        if names and frappe.db.exists(DECISION, {"attempt": ["in", names]}):
            return
        raise ValueError("Placement fee bills only after the decision is released")
    ladder = list(ATTEMPT_STATUSES)
    need = ladder.index(timing)
    best = max([ladder.index(row["status"]) for row in attempts
                if row["status"] in ladder], default=-1)
    if best < need:
        raise ValueError(f"Placement fee bills once the case reaches {timing}")


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown billing policy: {code}")
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
        "governing_max_backdate_days": (
            governing.get("max_backdate_days") if governing else ""),
        "governing_max_future_days": (
            governing.get("max_future_days") if governing else ""),
        "governing_placement_fee_timing": (
            (governing.get("placement_fee_timing") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_billing_terms(on_date=None):
    """Read-only resolver: governing terms, or {} when unconfigured.

    No receipt: a pure read used inside command work() closures.
    Fail-closed in three ways — no policy row, retired policy, no
    effective version — and every one means billing refuses.
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
        "max_backdate_days": governing.get("max_backdate_days"),
        "max_future_days": governing.get("max_future_days"),
        "placement_fee_timing": governing.get("placement_fee_timing") or "",
    }


@frappe.whitelist(methods=["POST"])
def create_billing_policy(request_key, code, title, description=""):
    """Define the billing policy shell (OD-NEW-03/OD-NEW-04 mechanism).

    Creates the single policy row with NO versions: billing stays
    denied until the Course Owner appends the first effective-dated
    version. The shell carries no terms — the owner's choice arrives
    only through versions, and only after owner decisions OD-NEW-03
    (date bounds) and OD-NEW-04 (fee timing).
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Billing policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A billing policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Billing policy {clean_code} already exists")
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
        "create_billing_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_billing_policy_version(request_key, policy, effective_from, reason,
                               max_backdate_days, max_future_days,
                               placement_fee_timing):
    """Append an effective-dated billing policy version.

    The version enacts one pair of posting-date bounds plus one
    placement-fee timing threshold from ``effective_from``; a change
    reason is mandatory; backdated or same-day versions are refused.
    The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_back, clean_fut, clean_timing = validate_terms(
                max_backdate_days, max_future_days, placement_fee_timing)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Billing policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="billing policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "max_backdate_days": clean_back,
            "max_future_days": clean_fut,
            "placement_fee_timing": clean_timing,
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
               "reason": reason, "max_backdate_days": max_backdate_days,
               "max_future_days": max_future_days,
               "placement_fee_timing": placement_fee_timing}
    return configuration_audit.execute(
        "set_billing_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_billing_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the billing policy.

    Retiring is the off-switch: with no active policy billing refuses
    again. Earlier bills keep their recorded receipts — the policy
    gates creation only, and history is never rewritten by a later
    switch.
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
        "set_billing_policy_status", request_key, payload, work)
