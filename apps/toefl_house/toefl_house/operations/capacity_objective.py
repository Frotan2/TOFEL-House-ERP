"""TH Capacity Objective: guarded numeric-objective commands (track 3, 2026-09-25).

Category B of the decision-classification rule (constitution §17): the
numeric capacity/availability objectives — concurrency profile, data
scale, workload mix, availability objective — are owner business
numbers, never engineering constants (O-D8N: "numbers only; mechanism
is engineering"). There is no native surface for this policy: planning
capacity exists in the platform only as infrastructure configuration
(worker counts, rate limits), not as a versioned business objective
record with readiness and audit. This module is the guarded shell for
those numbers; it carries no value for the owner.

Fail-closed by construction: with no carrier row, a retired objective,
or no effective version, ``governing_capacity_objective`` resolves to
{} and any measurement activity must refuse to claim an objective.
The owner opts in by appending an effective-dated version, never by
default. Each version carries exactly the four objectives as numbers —
``concurrent_users_target``, ``document_scale_target``,
``read_share_percent``, ``availability_target_percent`` — each
validated against technical bounds that are typo guards, plus the
mandatory change reason.

Versions are append-only and monotone by effective date; a newer
version closes the predecessor's ``superseded_on`` without rewriting
it. Commands route through the receipted Course Owner gate
(business_policy authority); every mutation keeps its hash-chained
configuration audit event.

PERMANENT RULE respected: the D8 capacity/availability release gate is
a release-authorization control and is NEVER configured from any
business setting — ``tools/foundation/d8_validate.py`` contains no
Frappe coupling and reads no site state (pin-tested). While no
objective is configured the gate's verdict is exactly what it already
is (D8-CAPACITY-AVAILABILITY NOT_SELECTED, gate BLOCKED); measurement
against an owner-selected objective remains a real-host engineering
proof.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Capacity Objective"

# Technical typo-guard ceilings (named + tested). Not business values:
# they cap magnitude, never set the objective.
CONCURRENT_USERS_MAX = 100000
DOCUMENT_SCALE_MAX = 1000000000
READ_SHARE_PERCENT_MIN = 0
READ_SHARE_PERCENT_MAX = 100


def validate_terms(concurrent_users_target, document_scale_target,
                   read_share_percent, availability_target_percent):
    """Shape-check one version's four objectives (command + controller).

    Returns them cleaned (numeric strings coerced). Raises ValueError
    on anything outside the technical bounds; no owner value is ever
    synthesized — every objective is required and owner-entered.
    """
    users = _coerce_int(concurrent_users_target)
    if (isinstance(users, bool) or not isinstance(users, int)
            or not 1 <= users <= CONCURRENT_USERS_MAX):
        raise ValueError(
            "Concurrent users target must be a whole number between 1 "
            f"and {CONCURRENT_USERS_MAX}")
    documents = _coerce_int(document_scale_target)
    if (isinstance(documents, bool) or not isinstance(documents, int)
            or not 1 <= documents <= DOCUMENT_SCALE_MAX):
        raise ValueError(
            "Document scale target must be a whole number between 1 "
            f"and {DOCUMENT_SCALE_MAX}")
    share = _coerce_int(read_share_percent)
    if (isinstance(share, bool) or not isinstance(share, int)
            or not READ_SHARE_PERCENT_MIN <= share <= READ_SHARE_PERCENT_MAX):
        raise ValueError(
            "Read share percent must be a whole number between "
            f"{READ_SHARE_PERCENT_MIN} and {READ_SHARE_PERCENT_MAX}")
    availability = _coerce_float(availability_target_percent)
    if (isinstance(availability, bool)
            or not isinstance(availability, (int, float))
            or not 0 < float(availability) <= 100):
        raise ValueError(
            "Availability target percent must be a number greater than "
            "0 and at most 100")
    return users, documents, share, float(availability)


def _coerce_int(value):
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _coerce_float(value):
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    return value


def _objective_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown capacity objective: {code}")
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


def _objective_result(doc, extra=None):
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(versions),
        "governing_effective_from": (
            str(governing.get("effective_from")) if governing else ""),
        "governing_concurrent_users_target": (
            governing.get("concurrent_users_target") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_capacity_objective(on_date=None):
    """Read-only resolver: governing objective numbers, or {} when unset.

    No receipt: a pure read used inside command work() closures and by
    future measurement consumers. Fail-closed in three ways — no
    carrier row, retired objective, no effective version — and every
    one means no objective may be claimed. No owner number is ever
    synthesized here; the values are reported exactly as configured.
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
        "concurrent_users_target": governing.get("concurrent_users_target"),
        "document_scale_target": governing.get("document_scale_target"),
        "read_share_percent": governing.get("read_share_percent"),
        "availability_target_percent": governing.get(
            "availability_target_percent"),
    }


@frappe.whitelist(methods=["POST"])
def create_capacity_objective(request_key, code, title, description=""):
    """Define the capacity objective shell (numeric-objective mechanism).

    Creates the single carrier row with NO versions: no objective may
    be claimed until the Course Owner appends the first effective-dated
    version with the four numbers. The shell carries no values.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Capacity objective title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A capacity objective already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Capacity objective {clean_code} already exists")
        doc = frappe.get_doc({
            "doctype": POLICY,
            "code": clean_code, "title": clean_title, "status": "Active",
            "description": clean_description,
        })
        doc.insert(ignore_permissions=True)
        return _objective_result(doc), {
            "target": doc.name, "before_hash": "",
            "after_hash": configuration_rules.snapshot_digest([]),
        }

    payload = {"code": code, "title": title, "description": description}
    return configuration_audit.execute(
        "create_capacity_objective", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_capacity_objective_version(request_key, objective, effective_from,
                                   reason, concurrent_users_target,
                                   document_scale_target, read_share_percent,
                                   availability_target_percent):
    """Append an effective-dated capacity objective version.

    The version enacts the four owner numbers from ``effective_from``;
    a change reason is mandatory; backdated or same-day versions are
    refused. The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(objective)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            (clean_users, clean_documents, clean_share,
             clean_availability) = validate_terms(
                concurrent_users_target, document_scale_target,
                read_share_percent, availability_target_percent)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _objective_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Capacity objective {clean_code} is retired; reactivate "
                "it before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="capacity objective version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from,
            "concurrent_users_target": clean_users,
            "document_scale_target": clean_documents,
            "read_share_percent": clean_share,
            "availability_target_percent": clean_availability,
            "reason": clean_reason, "set_by": actor,
            "set_on": frappe.utils.now_datetime()})
        if current:
            # Close the superseded version; never rewrite its meaning,
            # only record the date it stopped governing new activity.
            for row in doc.get("versions") or []:
                if (str(row.get("effective_from")) == str(current.get("effective_from"))
                        and not row.get("superseded_on")):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = configuration_rules.snapshot_digest(
            [row.as_dict() for row in (doc.get("versions") or [])])
        return _objective_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"objective": objective, "effective_from": effective_from,
               "reason": reason,
               "concurrent_users_target": concurrent_users_target,
               "document_scale_target": document_scale_target,
               "read_share_percent": read_share_percent,
               "availability_target_percent": availability_target_percent}
    return configuration_audit.execute(
        "set_capacity_objective_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_capacity_objective_status(request_key, objective, active):
    """Deactivate (retire) or reactivate the capacity objective.

    Retiring is the off-switch: with no active objective, no capacity
    objective may be claimed again. Recorded versions and receipts are
    never rewritten by a later switch.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(objective)
            flag = _as_bool(active, "active")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _objective_doc(clean_code, for_update=True)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        after = digest(["status", doc.status,
                        configuration_rules.snapshot_digest(versions)])
        return _objective_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"objective": objective, "active": active}
    return configuration_audit.execute(
        "set_capacity_objective_status", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def validate_capacity_objective(request_key, objective):
    """Validate a capacity objective's structure and record evidence.

    Structural checks only: active objective, versions present and
    unambiguous, every row's four numbers within technical bounds. No
    completeness judgement is invented here. Success writes a validation
    audit event over the exact version snapshot; any later version
    change stales it automatically, returning readiness to
    ``configured``.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(objective)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _objective_doc(clean_code)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Capacity objective {clean_code} is retired; only "
                "active objectives validate")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        if not versions:
            raise frappe.ValidationError(
                f"Capacity objective {clean_code} has no versions yet; "
                "add the first version before validating")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                versions, what="capacity objective version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in versions:
            try:
                validate_terms(row.get("concurrent_users_target"),
                               row.get("document_scale_target"),
                               row.get("read_share_percent"),
                               row.get("availability_target_percent"))
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        before = configuration_audit.latest_after_hash(doc.name)
        after = configuration_rules.snapshot_digest(versions)
        readiness = configuration_rules.compute_readiness(
            status=doc.status, versions=versions,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="capacity objective")
        return _objective_result(doc, extra={"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"objective": objective}
    return configuration_audit.execute(
        "validate_capacity_objective", request_key, payload, work)
