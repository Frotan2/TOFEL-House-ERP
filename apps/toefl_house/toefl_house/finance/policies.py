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
from toefl_house.finance import shamsi
from toefl_house.policy import ATTEMPT_STATUSES, digest

POLICY = "TH Billing Policy"
ATTEMPT = "TH Placement Attempt"
DECISION = "TH Placement Decision"

ANY_PROGRESS = "any"
RELEASED = "released"
TIMING_CHOICES = (ANY_PROGRESS,) + tuple(ATTEMPT_STATUSES) + (RELEASED,)
DAY_BOUND_MAX = 366
# Installment schedule bounds. These are mechanism guardrails, not policy:
# the owner chooses any count/interval inside them, and an owner who never
# enables installments bills one document exactly as before.
MAX_INSTALLMENTS = 12
INSTALLMENT_INTERVAL_MAX = 366


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


def as_flag(value, what="value"):
    """Interpret an owner-supplied on/off value as a bool, or refuse it.

    Accepts the boolean spellings a Desk Check field, a REST payload and a
    Python caller legitimately produce. Anything else is refused: a policy
    term is never guessed from a missing or ambiguous value.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes"):
            return True
        if text in ("0", "false", "no", ""):
            return False
    raise ValueError(f"{what} must be true or false")


def validate_installment_terms(allowed, max_installments, interval_days, cadence="Days"):
    """Shape-check one version's installment schedule terms.

    Off is the only state a fresh version can be in without the owner
    saying so: with installments disabled the count and interval are
    irrelevant, and the command stores the owner's numbers unchanged so
    enabling later is one decision, not a new arithmetic.
    """
    on = as_flag(allowed, "Installments allowed")
    if isinstance(max_installments, bool) or not isinstance(max_installments, int):
        raise ValueError(
            f"Maximum installments must be an integer (1-{MAX_INSTALLMENTS})")
    if not 1 <= max_installments <= MAX_INSTALLMENTS:
        raise ValueError(
            f"Maximum installments must be between 1 and {MAX_INSTALLMENTS}")
    if isinstance(interval_days, bool) or not isinstance(interval_days, int):
        raise ValueError(
            "Installment interval must be an integer number of days "
            f"(0-{INSTALLMENT_INTERVAL_MAX})")
    if not 0 <= interval_days <= INSTALLMENT_INTERVAL_MAX:
        raise ValueError(
            "Installment interval must be between 0 and "
            f"{INSTALLMENT_INTERVAL_MAX} days")
    if on and max_installments < 2:
        raise ValueError(
            "Enabling installments needs a maximum of at least 2; a single "
            "installment is the ordinary one-document bill")
    if on and cadence == "Days" and interval_days < 1:
        raise ValueError(
            "Enabling installments needs an interval of at least 1 day")
    return on, max_installments, interval_days


def validate_shamsi_cadence(cadence, grace_days):
    """Exact Solar Hijri monthly billing is opt-in, never a 30-day guess."""
    if cadence not in ("Days", "Solar Hijri Month"):
        raise ValueError("Installment cadence must be Days or Solar Hijri Month")
    if isinstance(grace_days, bool) or not isinstance(grace_days, int) or (
            not 0 <= grace_days <= 15):
        raise ValueError("Payment grace days must be a whole number (0-15)")
    if cadence == "Days" and grace_days:
        raise ValueError("Payment grace days require Solar Hijri Month cadence")
    return cadence, grace_days


def validate_due_day(cadence, due_day):
    """The Owner's contracted Solar Hijri day-of-month for installment dues.

    The Owner approved two due-date choices for the remaining installment —
    the 25th of the starting Afghan month, or the first of the following
    month (preferred). Both are *values*, never code: ``1`` is the month's
    first day and is what a version written before this field existed means,
    so history keeps its meaning. A non-Solar cadence carries no due day.
    """
    if isinstance(due_day, bool) or not isinstance(due_day, int):
        raise ValueError("Installment due day must be a whole number")
    if cadence != "Solar Hijri Month":
        if due_day:
            raise ValueError(
                "An installment due day requires Solar Hijri Month cadence")
        return 0
    if due_day == 0:
        return 1
    try:
        return shamsi.validate_due_day(due_day)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def validate_unequal_installments(allowed, installments_allowed):
    """Owner authorization for contractual *unequal* installment shares.

    The Owner approved variable contractual shares (for example 50%/50% or
    60%/40%) that must still add up to the full net tuition. Because a share
    split is a commercial term per student, it is authorized by an
    effective-dated version and never switched on by default; a version that
    does not mention it keeps equal splits only.
    """
    flag = as_flag(allowed, "Unequal installments allowed")
    if flag and not as_flag(installments_allowed, "Installments allowed"):
        raise ValueError(
            "Unequal installments need installments enabled on the same version")
    return 1 if flag else 0


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
    return as_flag(value, what)


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
        "governing_installments_allowed": (
            int(governing.get("installments_allowed") or 0) if governing else 0),
        "governing_max_installments": (
            governing.get("max_installments") if governing else ""),
        "governing_installment_interval_days": (
            governing.get("installment_interval_days") if governing else ""),
        "governing_installment_cadence": (
            (governing.get("installment_cadence") or "Days") if governing else ""),
        "governing_payment_grace_days": (
            int(governing.get("payment_grace_days") or 0) if governing else 0),
        "governing_installment_due_day": (
            int(governing.get("installment_due_day") or 0) if governing else 0),
        "governing_allow_unequal_installments": (
            int(governing.get("allow_unequal_installments") or 0) if governing else 0),
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
    terms = {
        "effective_from": str(governing.get("effective_from") or ""),
        "max_backdate_days": governing.get("max_backdate_days"),
        "max_future_days": governing.get("max_future_days"),
        "placement_fee_timing": governing.get("placement_fee_timing") or "",
        # Installment schedule terms. A version written before this field
        # existed reads as OFF: installments stay denied until the owner
        # records a version that enables them.
        "installments_allowed": int(governing.get("installments_allowed") or 0),
        "max_installments": int(governing.get("max_installments") or 1),
        "installment_interval_days": int(
            governing.get("installment_interval_days") or 0),
        # Contractual unequal shares are authorized only by an explicit
        # effective version; a version written before this field existed
        # reads as 0, so equal splits keep their existing behavior.
        "allow_unequal_installments": int(
            governing.get("allow_unequal_installments") or 0),
    }
    # Existing policy versions are unmodified and preserve legacy fixed-day
    # behavior; only the explicit Owner-selected Solar cadence adds fields.
    if governing.get("installment_cadence") == "Solar Hijri Month":
        terms["installment_cadence"] = "Solar Hijri Month"
        terms["payment_grace_days"] = int(
            governing.get("payment_grace_days") or 0)
        # A version written before the due-day field existed means the
        # first of the month — the old behavior, unchanged.
        terms["installment_due_day"] = int(
            governing.get("installment_due_day") or 1)
    return terms


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
                               placement_fee_timing, installments_allowed=0,
                               max_installments=1,
                               installment_interval_days=0,
                               installment_cadence="Days", payment_grace_days=0,
                               installment_due_day=0,
                               allow_unequal_installments=0):
    """Append an effective-dated billing policy version.

    The version enacts one pair of posting-date bounds, one
    placement-fee timing threshold and one installment schedule from
    ``effective_from``; a change reason is mandatory; backdated or
    same-day versions are refused. The superseded version is closed,
    never rewritten. Installment terms default to OFF, so a version
    that does not mention them cannot enable split billing.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_back, clean_fut, clean_timing = validate_terms(
                max_backdate_days, max_future_days, placement_fee_timing)
            clean_cadence, clean_grace = validate_shamsi_cadence(
                installment_cadence, payment_grace_days)
            clean_inst_on, clean_inst_max, clean_inst_days = \
                validate_installment_terms(
                    installments_allowed, max_installments,
                    installment_interval_days, cadence=clean_cadence)
            clean_due_day = validate_due_day(clean_cadence, installment_due_day)
            clean_unequal = validate_unequal_installments(
                allow_unequal_installments, clean_inst_on)
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
            "installments_allowed": 1 if clean_inst_on else 0,
            "max_installments": clean_inst_max,
            "installment_interval_days": clean_inst_days,
            "installment_cadence": clean_cadence,
            "payment_grace_days": clean_grace,
            "installment_due_day": clean_due_day,
            "allow_unequal_installments": clean_unequal,
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
               "placement_fee_timing": placement_fee_timing,
               "installments_allowed": installments_allowed,
               "max_installments": max_installments,
               "installment_interval_days": installment_interval_days,
               "installment_cadence": installment_cadence,
               "payment_grace_days": payment_grace_days,
               "installment_due_day": installment_due_day,
               "allow_unequal_installments": allow_unequal_installments}
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
