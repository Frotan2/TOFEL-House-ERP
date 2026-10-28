"""TH Guardian Lifecycle Policy: guarded policy commands (track 4, 2026-09-25).

Category B of the decision-classification rule (constitution §17): the
guardian lifecycle policy — merge/activation policy, delegation and
pre-admission proxy rules, consent/evidence/expiry, records/recording
rights — is owner business policy, never an engineering constant
(O-D4: "OWNER DECISION REQUIRED (advanced; narrow remedy stands)").

Native-and-existing-surface audit: Frappe/HRMS carry no guardian concept
at all; Education models the PEOPLE link (native Student carries a
`guardians` table) but no merge/activation/delegation/proxy/consent
semantics. The working Mini-ERP today deliberately ships no guardian
portal or advanced features — identity/guardian access behaves exactly
as the SEC-GUARDIAN-01 containment enforces it ("Defer advanced" is the
active owner disposition). Recording the owner's POLICY therefore
cannot take a native surface: the platform has nothing with versioning,
readiness, audit, or fail-closed semantics for these decisions. This
module records the policy inside the configuration engine only.

Fail-closed by construction: with no policy row, a retired policy, or
no effective version, ``governing_guardian_lifecycle`` resolves to {}
and every guard built later must refuse. Retiring is the off-switch:
the previous behavior — exactly the SEC-GUARDIAN-01 containment —
applies again. Nothing about the ownership boundary changes SEC-GUARDIAN-01
itself; the remedy stands (O-D4 records both facts).

Versions are append-only and monotone by effective date; a newer
version closes the predecessor's ``superseded_on`` without rewriting
it. Commands route through the receipted Course Owner gate
(business_policy authority); every mutation keeps its hash-chained
configuration audit event.

PERMANENT RULE respected: authorization/custody boundaries are never
business settings. This policy decides the lifecycle TERMS
(windows, proxy posture, consent evidence and expiry, records rights
text); it never grants any User, Role, row, or key any access by
itself, and `tools` + permissions enforcement carry no reference to it
(pin-tested).
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Guardian Lifecycle Policy"

# Technical option sets for the three enumerated terms. The owner picks
# among them; no default is offered anywhere.
PRE_ADMISSION_PROXY_KINDS = ("Allowed", "Refused")
CONSENT_EVIDENCE_KINDS = ("Link", "Attachment", "Both")

# Technical typo-guard ceilings (named + tested). Not business values:
# they cap magnitude, never set the policy. A delegation window or
# consent expiry longer than ten years reads as a mistake.
DELEGATION_WINDOW_MAX = 3650
CONSENT_EXPIRY_MAX = 3650
RECORDS_RIGHTS_MAX = 2000


def validate_terms(delegation_window_days, pre_admission_proxy,
                   consent_evidence, consent_expiry_days,
                   records_recording_rights):
    """Shape-check one version's five policy terms (command + controller).

    Returns them cleaned (numeric strings coerced, text stripped).
    Raises ValueError on anything outside the technical bounds; no owner
    choice is ever synthesized — every term is required and owner-picked.
    """
    window = _coerce_int(delegation_window_days)
    if (isinstance(window, bool) or not isinstance(window, int)
            or not 1 <= window <= DELEGATION_WINDOW_MAX):
        raise ValueError(
            "Delegation window days must be a whole number between 1 "
            f"and {DELEGATION_WINDOW_MAX}")
    if pre_admission_proxy not in PRE_ADMISSION_PROXY_KINDS:
        raise ValueError(
            "Pre-admission proxy must be one of "
            + " / ".join(PRE_ADMISSION_PROXY_KINDS) + "; it has no default")
    if consent_evidence not in CONSENT_EVIDENCE_KINDS:
        raise ValueError(
            "Consent evidence must be one of "
            + " / ".join(CONSENT_EVIDENCE_KINDS) + "; it has no default")
    expiry = _coerce_int(consent_expiry_days)
    if (isinstance(expiry, bool) or not isinstance(expiry, int)
            or not 1 <= expiry <= CONSENT_EXPIRY_MAX):
        raise ValueError(
            "Consent expiry days must be a whole number between 1 "
            f"and {CONSENT_EXPIRY_MAX}")
    rights = str(
        records_recording_rights if records_recording_rights is not None
        else "").strip()
    if not (1 <= len(rights) <= RECORDS_RIGHTS_MAX):
        raise ValueError(
            f"Records and recording rights text is required, at most "
            f"{RECORDS_RIGHTS_MAX} characters; it is never a default")
    return window, pre_admission_proxy, consent_evidence, expiry, rights


def _coerce_int(value):
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(
            f"Unknown guardian lifecycle policy: {code}")
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
        "governing_delegation_window_days": (
            governing.get("delegation_window_days") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_guardian_lifecycle(on_date=None):
    """Read-only resolver: governing guardian lifecycle terms, or {} when unset.

    No receipt: a pure read used inside command work() closures and by
    future lifecycle feature consumers. Fail-closed in three ways — no
    policy row, retired policy, no effective version — and every one
    means advanced guardian features refuse (identity/guardian behavior
    remains exactly what SEC-GUARDIAN-01 enforces). No owner choice is
    ever synthesized here; the terms are reported exactly as configured.
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
        "delegation_window_days": governing.get("delegation_window_days"),
        "pre_admission_proxy": governing.get("pre_admission_proxy") or "",
        "consent_evidence": governing.get("consent_evidence") or "",
        "consent_expiry_days": governing.get("consent_expiry_days"),
        "records_recording_rights": governing.get("records_recording_rights") or "",
    }


@frappe.whitelist(methods=["POST"])
def create_guardian_lifecycle_policy(request_key, code, title,
                                     description=""):
    """Define the guardian lifecycle policy shell (mechanism).

    Creates the single policy row with NO versions: advanced guardian
    features stay refused until the Course Owner appends the first
    effective-dated version. The shell carries no terms — the owner's
    choices arrive only through versions.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(
                title, "Guardian lifecycle policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A guardian lifecycle policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Guardian lifecycle policy {clean_code} already exists")
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
        "create_guardian_lifecycle_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_guardian_lifecycle_policy_version(request_key, policy,
                                          effective_from, reason,
                                          delegation_window_days,
                                          pre_admission_proxy,
                                          consent_evidence,
                                          consent_expiry_days,
                                          records_recording_rights):
    """Append an effective-dated guardian lifecycle policy version.

    The version enacts the five owner terms from ``effective_from``; a
    change reason is mandatory; backdated or same-day versions are
    refused. The superseded version is closed, never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            (clean_window, clean_proxy, clean_evidence, clean_expiry,
             clean_rights) = validate_terms(
                delegation_window_days, pre_admission_proxy,
                consent_evidence, consent_expiry_days,
                records_recording_rights)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Guardian lifecycle policy {clean_code} is retired; "
                "reactivate it before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="guardian lifecycle policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from,
            "delegation_window_days": clean_window,
            "pre_admission_proxy": clean_proxy,
            "consent_evidence": clean_evidence,
            "consent_expiry_days": clean_expiry,
            "records_recording_rights": clean_rights,
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
        return _policy_result(doc), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy, "effective_from": effective_from,
               "reason": reason,
               "delegation_window_days": delegation_window_days,
               "pre_admission_proxy": pre_admission_proxy,
               "consent_evidence": consent_evidence,
               "consent_expiry_days": consent_expiry_days,
               "records_recording_rights": records_recording_rights}
    return configuration_audit.execute(
        "set_guardian_lifecycle_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_guardian_lifecycle_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the guardian lifecycle policy.

    Retiring is the off-switch: with no active policy, every lifecycle
    feature refuses again and behavior remains exactly what the
    SEC-GUARDIAN-01 containment enforces. Recorded versions and receipts
    are never rewritten by a later switch.
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
        "set_guardian_lifecycle_policy_status", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def validate_guardian_lifecycle_policy(request_key, policy):
    """Validate a guardian lifecycle policy's structure and record evidence.

    Structural checks only: active policy, versions present and
    unambiguous, every row's five terms well-formed. No completeness
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
                f"Guardian lifecycle policy {clean_code} is retired; only "
                "active policies validate")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        if not versions:
            raise frappe.ValidationError(
                f"Guardian lifecycle policy {clean_code} has no versions "
                "yet; add the first version before validating")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                versions, what="guardian lifecycle policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in versions:
            try:
                validate_terms(row.get("delegation_window_days"),
                               row.get("pre_admission_proxy"),
                               row.get("consent_evidence"),
                               row.get("consent_expiry_days"),
                               row.get("records_recording_rights"))
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        before = configuration_audit.latest_after_hash(doc.name)
        after = configuration_rules.snapshot_digest(versions)
        readiness = configuration_rules.compute_readiness(
            status=doc.status, versions=versions,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="guardian lifecycle policy")
        return _policy_result(doc, extra={"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy}
    return configuration_audit.execute(
        "validate_guardian_lifecycle_policy", request_key, payload, work)
