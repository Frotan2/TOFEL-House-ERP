"""Guarded Course Owner policy for the remaining cross-domain business settings.

This is a single global, effective-dated carrier. Existing domain authorities
remain authoritative where they already exist (Billing Policy and Enrollment
Exit Policy); this carrier owns only the missing cross-domain terms and
surfaces them in one Settings-plane record.

No secrets, credentials, keys, custodians or authorization grants are stored.
Custody fields describe requirements/evidence only; ceremonies remain outside
Frappe as required by the separate-control principle.
"""
import frappe
from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as foundation
from toefl_house.policy import digest

POLICY = "TH Owner Operations Policy"
MAX_REASON = 500
MAX_DESTINATION = 200
MAX_CUSTODY = 2000
DESTINATION_KINDS = ("Owner-controlled off-site hardware",)


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


def validate_terms(values):
    review = _int(values.get("reporting_review_days"), "Reporting review days", 1, 366)
    capacity = _int(values.get("capacity_target"), "Class capacity target", 1, 1000)
    tax_enabled = _bool(values.get("tax_enabled"), "Tax enabled")
    rate = values.get("tax_rate")
    try:
        rate = float(rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tax rate must be numeric") from exc
    if not 0 <= rate <= 100:
        raise ValueError("Tax rate must be between 0 and 100")
    inclusive = _bool(values.get("tax_inclusive"), "Tax inclusive")
    transfer = _bool(values.get("transfer_allowed"), "Transfers allowed")
    withdrawal = _bool(values.get("withdrawal_allowed"), "Withdrawals allowed")
    notice = _int(values.get("calendar_notice_days"), "Calendar notice days", 0, 366)
    offsite = _bool(values.get("backup_offsite_required"), "Off-site backup required")
    kind = (values.get("backup_destination_kind") or "").strip()
    ref = (values.get("backup_destination_reference") or "").strip()
    if offsite:
        if kind not in DESTINATION_KINDS:
            raise ValueError("A backup destination kind is required when off-site backup is required")
        if not ref or len(ref) > MAX_DESTINATION:
            raise ValueError("A non-secret backup destination reference is required")
        lowered = ref.lower()
        if any(secret in lowered for secret in ("password=", "token=", "secret=", "private_key=", "access_key=")):
            raise ValueError("Backup destination reference must not contain credentials or secret material")
    custody = str(values.get("custody_requirement") or "").strip()
    if not 1 <= len(custody) <= MAX_CUSTODY:
        raise ValueError("Key custody requirement is required and must be concise")
    quorum = _int(values.get("recovery_quorum"), "Recovery quorum", 1, 20)
    reason = foundation.validate_change_reason(values.get("reason") or "")
    return {
        "reporting_review_days": review, "capacity_target": capacity,
        "tax_enabled": tax_enabled, "tax_rate": rate,
        "tax_inclusive": inclusive, "transfer_allowed": transfer,
        "withdrawal_allowed": withdrawal, "calendar_notice_days": notice,
        "backup_offsite_required": offsite,
        "backup_destination_kind": kind if offsite else "",
        "backup_destination_reference": ref if offsite else "",
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
        validate_terms(row)


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
                                        backup_offsite_required,
                                        backup_destination_kind="",
                                        backup_destination_reference="",
                                        custody_requirement="",
                                        recovery_quorum=1):
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
                "backup_offsite_required": backup_offsite_required,
                "backup_destination_kind": backup_destination_kind,
                "backup_destination_reference": backup_destination_reference,
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
            for row in rows: validate_terms(row)
            foundation.assert_no_ambiguous_versions(rows, what="owner operational policy version")
        except ValueError as exc: raise frappe.ValidationError(str(exc))
        before = configuration_audit.latest_after_hash(doc.name)
        after = foundation.snapshot_digest(rows)
        readiness = foundation.compute_readiness(
            status=doc.status, versions=rows, validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="owner operational policy")
        return _result(doc, {"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after}
    return configuration_audit.execute(
        "validate_owner_operations_policy", request_key, {"policy": policy}, work)


GOVERNING_FIELDS = (
    "effective_from", "reporting_review_days", "capacity_target",
    "tax_enabled", "tax_rate", "tax_inclusive", "transfer_allowed",
    "withdrawal_allowed", "calendar_notice_days", "backup_offsite_required",
    "backup_destination_kind", "backup_destination_reference",
    "custody_requirement", "recovery_quorum",
)

def governing_owner_operations(on_date=None):
    """Return only governing business terms; never expose audit metadata."""
    doc = _policy_doc()
    if not doc or doc.status != "Active":
        return {}
    rows = [r.as_dict() for r in (doc.get("versions") or [])]
    row = foundation.resolve_governing(rows, on_date or frappe.utils.today())
    if not row:
        return {}
    return {field: row.get(field) for field in GOVERNING_FIELDS}
