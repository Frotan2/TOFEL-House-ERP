"""S12 catalog linkage (OD-NEW-09): effective-dated owner control over
whether the TH academic catalog governs intake (S7/S8/S9/S10/S11
singleton mechanics).

The catalog already guards itself on the way out — retiring a level is
refused while submitted enrollments run on its native program — but
nothing consults it on the way in: new enrollments flow into retired
levels' programs unchecked. When the owner sets enforcement to
``enforcing``, ``enroll_in_program`` resolves the TH level anchored to
the admission's native program and refuses retired levels; ``advisory``
leaves intake unjudged and the owner maintains both planes by hand.
Native programs without a level are never catalog business: the
catalog governs what it maps, nothing more.

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, enrollment refuses — the owner opts in by
appending a version, never by default. The gate judges live terms at
enrollment time (S8-cutoff precedent): history is grandfathered, only
new commitments are judged.
"""

import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Catalog Linkage Policy"
LEVEL = "TH Program Level"

ADVISORY = "advisory"
ENFORCING = "enforcing"
ENFORCEMENT_CHOICES = (ADVISORY, ENFORCING)


def validate_enforcement(enforcement):
    """Shape-check the enforcement vocabulary (command + controller).

    ``advisory`` leaves intake unjudged; ``enforcing`` refuses new
    enrollments into retired levels' programs. The owner picks one per
    version; unmapped native programs stay allowed under both.
    """
    if enforcement not in ENFORCEMENT_CHOICES:
        raise ValueError(
            "Catalog linkage enforcement must be one of: "
            + ", ".join(ENFORCEMENT_CHOICES))
    return enforcement


def check_intake_open(program):
    """Refuse enrollment into a retired level's program when enforcing.

    Fails closed without a governing version; advisory versions judge
    nothing; native programs no level maps stay allowed — the catalog
    governs what it maps, nothing more.
    """
    terms = governing_linkage_terms()
    if not terms:
        raise ValueError("No active catalog linkage policy governs "
                         "enrollment; the Course Owner must set one first")
    if terms["enforcement"] == ADVISORY:
        return
    level = frappe.db.get_value(
        LEVEL, {"native_program": program}, ["code", "status"], as_dict=True)
    if level and level.status == "Retired":
        raise ValueError(
            f"Level {level.code} is retired; the catalog no longer admits "
            f"enrollment into {program}")


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown catalog linkage policy: {code}")
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
        "governing_enforcement": (
            (governing.get("enforcement") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_linkage_terms(on_date=None):
    """Read-only resolver: governing terms, or {} when unconfigured.

    No receipt: a pure read used inside the enrollment work() closure.
    Fail-closed in three ways — no policy row, retired policy, no
    effective version — and every one means enrollment refuses.
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
        "enforcement": governing.get("enforcement") or "",
    }


@frappe.whitelist(methods=["POST"])
def create_catalog_linkage_policy(request_key, code, title, description=""):
    """Define the catalog linkage policy shell (OD-NEW-09 mechanism).

    Creates the single policy row with NO versions: enrollment stays
    denied until the Course Owner appends the first effective-dated
    version. The shell carries no terms — the owner's choice of
    advisory vs enforcing arrives only through versions.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Catalog linkage policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A catalog linkage policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Catalog linkage policy {clean_code} already exists")
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
        "create_catalog_linkage_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_catalog_linkage_version(request_key, policy, effective_from, reason,
                                enforcement):
    """Append an effective-dated catalog linkage policy version.

    The version enacts one enforcement choice from ``effective_from``;
    a change reason is mandatory; backdated or same-day versions are
    refused. The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_enforcement = validate_enforcement(enforcement)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Catalog linkage policy {clean_code} is retired; reactivate "
                "it before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="catalog linkage version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "enforcement": clean_enforcement,
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
               "reason": reason, "enforcement": enforcement}
    return configuration_audit.execute(
        "set_catalog_linkage_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_catalog_linkage_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the catalog linkage policy.

    Retiring is the off-switch: with no active policy enrollment
    refuses again. Earlier enrollments keep their recorded receipts —
    the policy gates creation only, and history is never rewritten by
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
        "set_catalog_linkage_status", request_key, payload, work)
