"""Owner configuration commands: the roster-change policy (OD-NEW-05 mechanism).

Same governance surface as the academic control plane and the
returning-student policy: NOT synthetic-gated — the Course Owner
configures the real institution — and fail-closed on every input.
Exactly ONE policy row exists (the house has one roster-change rule);
its versions carry the effective-dated history of the owner's choice.

Each version carries one facet, ``changes_allowed_until``: the last
date (inclusive) on which mid-term roster changes may execute. With
no policy, no governing version, a retired policy, or a passed cutoff,
the roster commands refuse exactly as before — the owner opts in by
appending a version with a live cutoff, never by default. Closing
changes immediately is done by retiring the policy, never by a cutoff
that precedes the version's own effective date.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Roster Change Policy"


def validate_cutoff(value, effective_from):
    """A cutoff must be a real date on or after the version's start."""
    clean = rules.parse_date(str(value or "").strip(),
                             "Changes-allowed-until")
    if clean < str(effective_from or "").strip():
        raise ValueError(
            "Changes-allowed-until must not precede the version's "
            "effective date; retire the policy to close changes")
    return clean


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown roster-change policy: {code}")
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
        "governing_changes_allowed_until": (
            str(governing.get("changes_allowed_until") or "")
            if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_cutoff_date(on_date=None):
    """Read-only resolver: the cutoff governing a date, or "" when unconfigured.

    No receipt: this is a pure read used inside command work() closures,
    exactly like the returning-mode governing resolution. Fail-closed
    in three ways — no policy row, retired policy, no effective
    version — and every one of them means the roster commands refuse.
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
    return str(governing.get("changes_allowed_until") or "")


@frappe.whitelist(methods=["POST"])
def create_roster_change_policy(request_key, code, title,
                                description=""):
    """Define the roster-change policy shell (OD-NEW-05 mechanism).

    Creates the single policy row with NO versions: roster changes
    stay denied until the Course Owner appends the first
    effective-dated version. The shell carries no cutoff — the owner's
    choice arrives only through versions, and only after owner
    decision OD-NEW-05.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Roster-change policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A roster-change policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Roster-change policy {clean_code} already exists")
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
        "create_roster_change_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_roster_change_policy_version(request_key, policy, effective_from,
                                     reason, changes_allowed_until):
    """Append an effective-dated roster-change policy version.

    The version permits roster changes up to and including its cutoff
    from ``effective_from``; a change reason is mandatory; backdated
    or same-day versions are refused. The superseded version is
    closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_until = validate_cutoff(changes_allowed_until, clean_from)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Roster-change policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="roster-change policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from,
            "changes_allowed_until": clean_until,
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
               "reason": reason, "changes_allowed_until": changes_allowed_until}
    return configuration_audit.execute(
        "set_roster_change_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_roster_change_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the roster-change policy.

    Retiring is the off-switch: with no active policy the roster
    commands refuse again. Earlier roster changes keep their recorded
    receipts — the policy gates execution only, and history is never
    rewritten by a later switch.
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
        "set_roster_change_policy_status", request_key, payload, work)
