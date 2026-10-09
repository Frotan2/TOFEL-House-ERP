"""Guarded Course Owner policy for the remaining cross-domain business settings.

This is a single global, effective-dated carrier. Existing domain authorities
remain authoritative where they already exist (Billing Policy and Enrollment
Exit Policy); this carrier owns only the missing cross-domain terms and
surfaces them in one Settings-plane record.

No secrets, credentials, private keys, custodians or authorization grants are
stored. A public recovery key may be recorded because it cannot decrypt without
the externally held private key. Custody fields describe requirements/evidence
only; ceremonies remain outside Frappe as required by the separate-control
principle.
"""
import base64
import hashlib
import json
import math
import re
from datetime import datetime

import frappe
from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as foundation
from toefl_house.policy import digest

POLICY = "TH Owner Operations Policy"
MAX_REASON = 500
MAX_CUSTODY = 2000
MIN_BACKUP_VERSIONS = 2
MAX_BACKUP_VERSIONS = 10000
MAX_BACKUP_PUBLIC_KEY = 65536
RETENTION_PRESERVE_ALL = "Preserve all valid backup sets"
RETENTION_DELETE_BEYOND_KEEP = "Delete valid older sets beyond keep count"
BACKUP_RETENTION_BEHAVIORS = frozenset({
    RETENTION_PRESERVE_ALL,
    RETENTION_DELETE_BEYOND_KEEP,
})


def _policy_doc(for_update=False):
    rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
    if not rows:
        return None
    return frappe.get_doc(POLICY, rows[0]["name"], for_update=for_update)


def _bool(value, label):
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ("1", "true", "yes"): return True
        if value in ("0", "false", "no"): return False
    if isinstance(value, bool): return value
    if value in (0, 1): return bool(value)
    raise ValueError(f"{label} must be true or false")


def _int(value, label, minimum=0, maximum=3650):
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a whole number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def _backup_schedule_time(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", text):
        raise ValueError("Nightly backup time is required in 24-hour HH:MM format")
    for clock_format in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, clock_format).strftime("%H:%M")
        except ValueError:
            pass
    raise ValueError("Nightly backup time is required in 24-hour HH:MM format")


def _backup_public_key(value):
    key = str(value or "").strip()
    lines = key.splitlines()
    if (len(key) > MAX_BACKUP_PUBLIC_KEY or not key.isascii()
            or not lines
            or lines[0] != "-----BEGIN PGP PUBLIC KEY BLOCK-----"
            or lines[-1] != "-----END PGP PUBLIC KEY BLOCK-----"
            or re.search(r"PRIVATE KEY", key, re.IGNORECASE)):
        raise ValueError(
            "A valid ASCII-armored public recovery key is required; private-key material must stay outside Frappe")
    return key


def _backup_retention_behavior(value):
    behavior = str(value or "").strip()
    if behavior not in BACKUP_RETENTION_BEHAVIORS:
        raise ValueError(
            "An explicit backup retention behavior is required: preserve all valid sets, or delete valid older sets beyond the keep count")
    return behavior


def validate_terms(values, *, allow_legacy_backup=False):
    review = _int(values.get("reporting_review_days"), "Reporting review days", 1, 366)
    capacity = _int(values.get("capacity_target"), "Class capacity target", 1, 1000)
    tax_enabled = _bool(values.get("tax_enabled"), "Tax enabled")
    rate = values.get("tax_rate")
    if isinstance(rate, bool):
        raise ValueError("Tax rate must be numeric")
    try:
        rate = float(rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tax rate must be numeric") from exc
    if not math.isfinite(rate) or not 0 <= rate <= 100:
        raise ValueError("Tax rate must be between 0 and 100")
    inclusive = _bool(values.get("tax_inclusive"), "Tax inclusive")
    transfer = _bool(values.get("transfer_allowed"), "Transfers allowed")
    withdrawal = _bool(values.get("withdrawal_allowed"), "Withdrawals allowed")
    notice = _int(values.get("calendar_notice_days"), "Calendar notice days", 0, 366)
    custody = str(values.get("custody_requirement") or "").strip()
    if not 1 <= len(custody) <= MAX_CUSTODY:
        raise ValueError("Key custody requirement is required and must be concise")
    quorum = _int(values.get("recovery_quorum"), "Recovery quorum", 1, 20)

    schedule_value = values.get("backup_schedule_time")
    retention_value = values.get("backup_retention_versions")
    retention_behavior_value = values.get("backup_retention_behavior")
    recovery_key = str(values.get("backup_recovery_public_key") or "").strip()
    if allow_legacy_backup and retention_behavior_value in (None, ""):
        retention_behavior = ""
    else:
        retention_behavior = _backup_retention_behavior(retention_behavior_value)
    if allow_legacy_backup and not recovery_key:
        # Historical versions predate the required recovery key. Preserve
        # their saveability (and validate any old fields they did set), while
        # current_backup_policy remains NOT CONFIGURED until a new version
        # supplies the schedule, count, retention behavior and public key.
        schedule = _backup_schedule_time(schedule_value) if schedule_value else ""
        retention = (
            _int(retention_value, "Backup versions to retain",
                 MIN_BACKUP_VERSIONS, MAX_BACKUP_VERSIONS)
            if retention_value not in (None, "") else None
        )
    else:
        schedule = _backup_schedule_time(schedule_value)
        retention = _int(retention_value, "Backup versions to retain",
                         MIN_BACKUP_VERSIONS, MAX_BACKUP_VERSIONS)
        recovery_key = _backup_public_key(recovery_key)

    reason = foundation.validate_change_reason(values.get("reason") or "")
    return {
        "reporting_review_days": review, "capacity_target": capacity,
        "tax_enabled": tax_enabled, "tax_rate": rate,
        "tax_inclusive": inclusive, "transfer_allowed": transfer,
        "withdrawal_allowed": withdrawal, "calendar_notice_days": notice,
        "backup_schedule_time": schedule,
        "backup_retention_versions": retention,
        "backup_retention_behavior": retention_behavior,
        "backup_recovery_public_key": recovery_key,
        "custody_requirement": custody, "recovery_quorum": quorum,
        "reason": reason,
    }


def validate_policy(doc):
    foundation.assert_command_context(
        "Owner operational policy changes only through guarded Course Owner commands")
    rules.validate_code(doc.code or "")
    rules.validate_title(doc.title or "", "Owner operational policy title")
    if doc.status not in ("Active", "Retired"):
        frappe.throw("Status must be Active or Retired")
    rows = [row.as_dict() for row in (doc.get("versions") or [])]
    dates = [str(row.get("effective_from") or "") for row in rows]
    if len(dates) != len(set(dates)):
        frappe.throw("Two owner operational policy versions cannot share one effective date")
    for row in rows:
        validate_terms(row, allow_legacy_backup=True)


def _result(doc, extra=None):
    rows = [r.as_dict() for r in (doc.get("versions") or [])]
    governing = foundation.resolve_governing(rows, frappe.utils.today())
    result = {
        "name": doc.name, "code": doc.code, "title": doc.title,
        "status": doc.status, "version_count": len(rows),
        "governing_effective_from": str(governing.get("effective_from")) if governing else "",
    }
    if extra: result.update(extra)
    return result


@frappe.whitelist(methods=["POST"])
def create_owner_operations_policy(request_key, code, title, description=""):
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Owner operational policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc))
        if _policy_doc():
            raise frappe.ValidationError("An owner operational policy already exists; version it instead")
        doc = frappe.get_doc({"doctype": POLICY, "code": clean_code,
                              "title": clean_title, "status": "Active",
                              "description": clean_description})
        doc.insert(ignore_permissions=True)
        return _result(doc), {"target": doc.name, "before_hash": "",
                              "after_hash": foundation.snapshot_digest([])}
    return configuration_audit.execute(
        "create_owner_operations_policy", request_key,
        {"code": code, "title": title, "description": description}, work)


@frappe.whitelist(methods=["POST"])
def set_owner_operations_policy_version(request_key, policy, effective_from,
                                        reason, reporting_review_days,
                                        capacity_target, tax_enabled, tax_rate,
                                        tax_inclusive, transfer_allowed,
                                        withdrawal_allowed, calendar_notice_days,
                                        backup_schedule_time,
                                        backup_retention_versions,
                                        backup_retention_behavior,
                                        backup_recovery_public_key,
                                        custody_requirement,
                                        recovery_quorum):
    def work(actor):
        doc = _policy_doc(for_update=True)
        if not doc or doc.code != policy:
            raise frappe.ValidationError(f"Unknown owner operational policy: {policy}")
        if doc.status != "Active":
            raise frappe.ValidationError("Owner operational policy is retired; reactivate it before adding a version")
        try:
            clean_from = rules.parse_date(effective_from)
            values = validate_terms({
                "reporting_review_days": reporting_review_days,
                "capacity_target": capacity_target,
                "tax_enabled": tax_enabled,
                "tax_rate": tax_rate,
                "tax_inclusive": tax_inclusive,
                "transfer_allowed": transfer_allowed,
                "withdrawal_allowed": withdrawal_allowed,
                "calendar_notice_days": calendar_notice_days,
                "backup_schedule_time": backup_schedule_time,
                "backup_retention_versions": backup_retention_versions,
                "backup_retention_behavior": backup_retention_behavior,
                "backup_recovery_public_key": backup_recovery_public_key,
                "custody_requirement": custody_requirement,
                "recovery_quorum": recovery_quorum,
                "reason": reason,
            })
        except ValueError as exc:
            raise frappe.ValidationError(str(exc))
        rows = [r.as_dict() for r in (doc.get("versions") or [])]
        try:
            foundation.check_appends(rows, clean_from, what="owner operational policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc))
        current = foundation.latest_version(rows)
        before = configuration_audit.latest_after_hash(doc.name)
        values.update({"effective_from": clean_from, "set_by": actor,
                       "set_on": frappe.utils.now_datetime()})
        doc.append("versions", values)
        if current:
            for row in doc.get("versions") or []:
                if str(row.get("effective_from")) == str(current.get("effective_from")) and not row.get("superseded_on"):
                    row.superseded_on = clean_from
                    break
        doc.save(ignore_permissions=True)
        after = foundation.snapshot_digest([r.as_dict() for r in (doc.get("versions") or [])])
        return _result(doc), {"target": doc.name, "before_hash": before, "after_hash": after}
    payload = {k:v for k,v in locals().items() if k != "work"}
    return configuration_audit.execute(
        "set_owner_operations_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_owner_operations_policy_status(request_key, policy, active):
    def work(actor):
        doc = _policy_doc(for_update=True)
        if not doc or doc.code != policy:
            raise frappe.ValidationError(f"Unknown owner operational policy: {policy}")
        try: flag = _bool(active, "Active")
        except ValueError as exc: raise frappe.ValidationError(str(exc))
        before = configuration_audit.latest_after_hash(doc.name)
        doc.status = "Active" if flag else "Retired"
        doc.save(ignore_permissions=True)
        rows = [r.as_dict() for r in (doc.get("versions") or [])]
        after = digest(["status", doc.status, foundation.snapshot_digest(rows)])
        return _result(doc), {"target": doc.name, "before_hash": before, "after_hash": after}
    return configuration_audit.execute(
        "set_owner_operations_policy_status", request_key,
        {"policy": policy, "active": active}, work)


@frappe.whitelist(methods=["POST"])
def validate_owner_operations_policy(request_key, policy):
    def work(actor):
        doc = _policy_doc()
        if not doc or doc.code != policy:
            raise frappe.ValidationError(f"Unknown owner operational policy: {policy}")
        if doc.status != "Active":
            raise frappe.ValidationError("Owner operational policy is retired; only active policies validate")
        rows = [r.as_dict() for r in (doc.get("versions") or [])]
        if not rows:
            raise frappe.ValidationError("Owner operational policy has no versions yet")
        try:
            for row in rows:
                validate_terms(row, allow_legacy_backup=True)
            foundation.assert_no_ambiguous_versions(rows, what="owner operational policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc))
        before = configuration_audit.latest_after_hash(doc.name)
        after = foundation.snapshot_digest(rows)
        readiness = foundation.compute_readiness(
            status=doc.status, versions=rows, validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="owner operational policy")
        return _result(doc, {"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after}
    result = configuration_audit.execute(
        "validate_owner_operations_policy", request_key, {"policy": policy}, work)
    # The validation audit event must exist before a runtime consumer may
    # resolve backup policy. Recompute after the guarded command has written
    # its receipt and event; replays are safe because the resolver verifies
    # the current version snapshot against the validation ledger each time.
    result["backup_policy"] = current_backup_policy()
    return result


GOVERNING_FIELDS = (
    "effective_from", "reporting_review_days", "capacity_target",
    "tax_enabled", "tax_rate", "tax_inclusive", "transfer_allowed",
    "withdrawal_allowed", "calendar_notice_days", "backup_schedule_time",
    "backup_retention_versions", "backup_retention_behavior",
    "backup_recovery_public_key",
    "custody_requirement", "recovery_quorum",
)


def _version_rows(doc):
    return [row.as_dict() for row in (doc.get("versions") or [])]


def _owner_policy_validation_is_current(target, rows):
    """Fail closed unless the latest policy changes follow a validation.

    A validation event commits to the exact effective-dated version snapshot.
    Any later policy mutation—including a status change—requires revalidation.
    Equal creation timestamps are treated as ambiguous and fail closed rather
    than relying on database row ordering.
    """
    if not target or not rows:
        return False
    snapshot = foundation.snapshot_digest(rows)
    events = frappe.db.get_all(
        configuration_audit.AUDIT,
        filters={"target": target},
        fields=["action", "after_hash", "creation"],
        limit_page_length=0,
    )
    matching_times = [
        str(event.get("creation") or "")
        for event in events
        if event.get("action") == "validate_owner_operations_policy"
        and event.get("after_hash") == snapshot
        and event.get("creation")
    ]
    if not matching_times:
        return False
    latest_validation = max(matching_times)
    return not any(
        event.get("action") != "validate_owner_operations_policy"
        and (not event.get("creation")
             or str(event.get("creation")) >= latest_validation)
        for event in events
    )


def _governing_owner_terms(doc, rows, on_date=None):
    if not doc or doc.status != "Active":
        return {}
    row = foundation.resolve_governing_strict(
        rows, on_date or frappe.utils.today(),
        what="owner operational policy version")
    if not row:
        return {}
    return {field: row.get(field) for field in GOVERNING_FIELDS}


def governing_owner_operations(on_date=None):
    """Return business terms only when the current snapshot is validated.

    Keep every public resolver on the same fail-closed validation boundary
    used by the backup/activation consumer; callers must not accidentally
    consume a saved-but-unvalidated Owner version as live policy.
    """
    return _validated_governing_owner_operations(on_date)


def _validated_governing_owner_operations(on_date=None):
    """Resolve terms only when the active policy's latest snapshot is validated."""
    doc = _policy_doc()
    if not doc or doc.status != "Active":
        return {}
    rows = _version_rows(doc)
    if not _owner_policy_validation_is_current(doc.name, rows):
        return {}
    return _governing_owner_terms(doc, rows, on_date)


def current_backup_policy(on_date=None):
    """Expose only a currently validated, non-secret backup policy to tooling."""
    try:
        terms = _validated_governing_owner_operations(on_date)
        if not terms:
            return {"configured": False, "status": "NOT CONFIGURED"}
        schedule_value = terms.get("backup_schedule_time")
        retention_value = terms.get("backup_retention_versions")
        retention_behavior_value = terms.get("backup_retention_behavior")
        recovery_key = str(terms.get("backup_recovery_public_key") or "").strip()
        if (not schedule_value or retention_value in (None, "")
                or not retention_behavior_value or not recovery_key):
            return {"configured": False, "status": "NOT CONFIGURED"}
        schedule = _backup_schedule_time(schedule_value)
        retention = _int(retention_value, "Backup versions to retain",
                         MIN_BACKUP_VERSIONS, MAX_BACKUP_VERSIONS)
        retention_behavior = _backup_retention_behavior(retention_behavior_value)
        try:
            recovery_key = _backup_public_key(recovery_key)
        except ValueError:
            return {"configured": False, "status": "NOT CONFIGURED"}
        recovery_key_hash = hashlib.sha256(recovery_key.encode("utf-8")).hexdigest()
        effective = str(terms["effective_from"])
        identity = {
            "effective_from": effective,
            "schedule_time": schedule,
            "retention_versions": retention,
            "retention_behavior": retention_behavior,
            "recovery_key_sha256": recovery_key_hash,
        }
        policy_hash = hashlib.sha256(json.dumps(
            identity, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return {
            "configured": True,
            "status": "CONFIGURED",
            "schedule_time": schedule,
            "retention_versions": retention,
            "retention_behavior": retention_behavior,
            "recovery_key_sha256": recovery_key_hash,
            "effective_from": effective,
            "policy_hash": policy_hash,
        }
    except (TypeError, ValueError, KeyError):
        return {"configured": False, "status": "NOT CONFIGURED"}


def current_backup_public_key_b64(on_date=None):
    """Return only the configured public recovery key, ASCII-safe for tooling."""
    policy = current_backup_policy(on_date)
    if policy.get("configured") is not True:
        return ""
    terms = _validated_governing_owner_operations(on_date)
    key = str(terms.get("backup_recovery_public_key") or "").strip()
    if hashlib.sha256(key.encode("utf-8")).hexdigest() != policy.get("recovery_key_sha256"):
        return ""
    return base64.b64encode(key.encode("utf-8")).decode("ascii")
