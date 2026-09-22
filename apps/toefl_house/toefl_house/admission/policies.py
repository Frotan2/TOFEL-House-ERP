"""Owner configuration commands: the returning-student policy (OD-NEW-01/B).

Same governance surface as the academic control plane: NOT
synthetic-gated — the Course Owner configures the real institution —
and fail-closed on every input. Exactly ONE policy row exists (the
house has one returning-student rule); its versions carry the
effective-dated history of the owner's choice.

Modes are capabilities the admission commands execute, never labels:
``placement_per_term`` lets a subject with no open admission journey
start a new applicant after re-sitting placement. With no policy, no
governing version, or a retired policy, the intake refuses exactly as
before — the owner opts in by appending a version, never by default.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Returning Student Policy"

# Every mode here must be executable by the admission commands today. A
# placement-free returning lane (OD-NEW-01/A) needs its own intake
# command first and stays out of this tuple until that slice lands.
RETURNING_MODES = ("placement_per_term",)


def validate_mode(value):
    if value not in RETURNING_MODES:
        raise ValueError(
            "Mode must be one of: {}".format(", ".join(RETURNING_MODES)))
    return value


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown returning-student policy: {code}")
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
        "governing_mode": (governing.get("mode") or "") if governing else "",
    }
    if extra:
        result.update(extra)
    return result


def governing_returning_mode(on_date=None):
    """Read-only resolver: the mode governing a date, or "" when unconfigured.

    No receipt: this is a pure read used inside command work() closures,
    exactly like the assessment governing resolution. Fail-closed in
    three ways — no policy row, retired policy, no effective version —
    and every one of them means the intake refuses returning applicants.
    """
    rows = frappe.db.get_all(POLICY, fields=["name"], limit=1)
    if not rows:
        return ""
    doc = frappe.get_doc(POLICY, rows[0]["name"])
    if doc.status != "Active":
        return ""
    versions = [row.as_dict() for row in (doc.get("versions") or [])]
    governing = configuration_rules.resolve_governing(
        versions, on_date or frappe.utils.today())
    if not governing:
        return ""
    return governing.get("mode") or ""


@frappe.whitelist(methods=["POST"])
def create_returning_student_policy(request_key, code, title,
                                    description=""):
    """Define the returning-student policy shell (OD-NEW-01 mechanism).

    Creates the single policy row with NO versions: the intake stays
    denied until the Course Owner appends the first effective-dated
    version. The shell carries no mode — the owner's choice arrives
    only through versions, and only after owner decision OD-NEW-01.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Returning-student policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A returning-student policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Returning-student policy {clean_code} already exists")
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
        "create_returning_student_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_returning_student_policy_version(request_key, policy, effective_from,
                                         reason, mode):
    """Append an effective-dated returning-student policy version.

    The version enacts one executable mode from ``effective_from``; a
    change reason is mandatory; backdated or same-day versions are
    refused. The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_mode = validate_mode((mode or "").strip())
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Returning-student policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="returning-student policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "mode": clean_mode,
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
               "reason": reason, "mode": mode}
    return configuration_audit.execute(
        "set_returning_student_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_returning_student_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the returning-student policy.

    Retiring is the off-switch: with no active policy the intake
    refuses returning applicants again. In-flight returning journeys
    keep their recorded decisions — the policy gates intake only, and
    history is never rewritten by a later switch.
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
        "set_returning_student_policy_status", request_key, payload, work)
