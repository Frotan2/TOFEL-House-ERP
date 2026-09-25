"""D7 metric stewardship policy (decision classification, 2026-09-25).

Category B of the decision-classification rule (constitution §17): naming
metric stewards and disclosure rules for DERIVED metrics is business
policy, never an engineering constant. This module is the guarded shell
for that policy; it carries no value for the owner.

Architecture anchor: the reporting register (toefl_house.reporting)
defines raw business facts in code — visibility rules of native queries,
which is engineering. DERIVED metrics (anything computed across facts,
with denominators, ratios, windows or cohorts) are different: their
definition is a business act and needs a named accountable steward and
disclosure rules (D12/A12 discipline: provenance, separated grains,
permissions). Nothing derives metrics anywhere in the product today.

Fail-closed by construction: with no policy row, a retired policy, or no
effective version, ``governing_stewardship`` resolves to {} and any
derived-metric mechanism must refuse. The owner opts in by appending an
effective-dated version, never by default. Each version carries exactly
the two D7 terms — the steward role (a native Role link the owner picks;
engineering picks none) and the disclosure rules (the owner's policy
text; engineering writes none of it) — plus the mandatory change reason.

Versions are append-only and monotone by effective date; a newer version
closes the predecessor's ``superseded_on`` without rewriting it, so a
future derived metric can value-pin its governing stewardship at
definition time, exactly like pinned correction terms. Commands route
through the receipted Course Owner gate (business_policy authority);
every mutation keeps its hash-chained configuration audit event.
"""
import frappe

from toefl_house.academic import rules
from toefl_house.configuration import audit as configuration_audit
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest

POLICY = "TH Metric Stewardship Policy"

# Technical bound on the owner's disclosure text (named + tested, like the
# change-reason bound in configuration/rules.py). Not a business value: it
# caps input size, never content.
DISCLOSURE_RULES_MAX = 2000


def validate_terms(steward_role, disclosure_rules):
    """Shape-check one policy version's terms (command + controller)."""
    if not isinstance(steward_role, str) or not steward_role \
            or len(steward_role) > 140:
        raise ValueError("Steward role required")
    if not isinstance(disclosure_rules, str) or not disclosure_rules.strip():
        raise ValueError(
            "Disclosure rules are required: state who may see derived "
            "metrics and how they are labelled")
    rules_text = disclosure_rules.strip()
    if len(rules_text) > DISCLOSURE_RULES_MAX:
        raise ValueError(
            f"Disclosure rules must be at most {DISCLOSURE_RULES_MAX} "
            "characters")
    return steward_role, rules_text


def _policy_doc(code, for_update=False):
    name = frappe.db.get_value(POLICY, {"code": code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown metric-stewardship policy: {code}")
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
        "governing_steward_role": (
            (governing.get("steward_role") or "") if governing else ""),
    }
    if extra:
        result.update(extra)
    return result


def governing_stewardship(on_date=None):
    """Read-only resolver: governing stewardship terms, or {} when unset.

    No receipt: a pure read used inside command work() closures and by
    future derived-metric consumers. Fail-closed in three ways — no
    policy row, retired policy, no effective version — and every one
    means derived metrics refuse. No owner value is ever synthesized
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
        "steward_role": governing.get("steward_role") or "",
        "disclosure_rules": governing.get("disclosure_rules") or "",
    }


@frappe.whitelist(methods=["POST"])
def create_metric_stewardship_policy(request_key, code, title,
                                     description=""):
    """Define the metric-stewardship policy shell (D7 mechanism).

    Creates the single policy row with NO versions: derived metrics stay
    refused until the Course Owner appends the first effective-dated
    version. The shell carries no terms — the owner's choice arrives
    only through versions.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(code)
            clean_title = rules.validate_title(title, "Metric-stewardship policy title")
            clean_description = rules.validate_reason(description)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if frappe.db.get_all(POLICY, fields=["name"], limit=1):
            raise frappe.ValidationError(
                "A metric-stewardship policy already exists; version it instead")
        if frappe.db.exists(POLICY, clean_code):
            raise frappe.ValidationError(
                f"Metric-stewardship policy {clean_code} already exists")
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
        "create_metric_stewardship_policy", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_metric_stewardship_policy_version(request_key, policy,
                                          effective_from, reason,
                                          steward_role, disclosure_rules):
    """Append an effective-dated metric-stewardship policy version.

    The version enacts one steward role and one disclosure-rules text
    from ``effective_from``; a change reason is mandatory; backdated or
    same-day versions are refused. The superseded version is closed,
    never rewritten.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
            clean_from = rules.parse_date(effective_from)
            clean_reason = configuration_rules.validate_change_reason(reason)
            clean_role, clean_rules = validate_terms(steward_role,
                                                     disclosure_rules)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("Role", clean_role):
            raise frappe.ValidationError("Unknown steward role")
        doc = _policy_doc(clean_code, for_update=True)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Metric-stewardship policy {clean_code} is retired; reactivate it "
                "before adding a version")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        try:
            configuration_rules.check_appends(
                versions, clean_from, what="metric-stewardship policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        current = configuration_rules.latest_version(versions)
        before = configuration_audit.latest_after_hash(doc.name)
        doc.append("versions", {
            "effective_from": clean_from, "steward_role": clean_role,
            "disclosure_rules": clean_rules,
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
               "reason": reason, "steward_role": steward_role,
               "disclosure_rules": disclosure_rules}
    return configuration_audit.execute(
        "set_metric_stewardship_policy_version", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def set_metric_stewardship_policy_status(request_key, policy, active):
    """Deactivate (retire) or reactivate the metric-stewardship policy.

    Retiring is the off-switch: with no active policy derived metrics
    refuse again. Recorded versions and receipts are never rewritten by
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
        "set_metric_stewardship_policy_status", request_key, payload, work)


@frappe.whitelist(methods=["POST"])
def validate_metric_stewardship_policy(request_key, policy):
    """Validate a metric-stewardship policy's structure and record evidence.

    Structural checks only: active policy, versions present and
    unambiguous, every row's terms well-formed, and every referenced
    steward role still resolving. No completeness judgement is invented
    here. Success writes a validation audit event over the exact version
    snapshot; any later version change stales it automatically,
    returning readiness to ``configured``.
    """
    def work(actor):
        try:
            clean_code = rules.validate_code(policy)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        doc = _policy_doc(clean_code)
        if doc.status != "Active":
            raise frappe.ValidationError(
                f"Metric-stewardship policy {clean_code} is retired; only "
                "active policies validate")
        versions = [row.as_dict() for row in (doc.get("versions") or [])]
        if not versions:
            raise frappe.ValidationError(
                f"Metric-stewardship policy {clean_code} has no versions "
                "yet; add the first version before validating")
        try:
            configuration_rules.assert_no_ambiguous_versions(
                versions, what="metric-stewardship policy version")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        for row in versions:
            try:
                clean_role, _rules_text = validate_terms(
                    row.get("steward_role") or "",
                    row.get("disclosure_rules") or "")
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
            if not frappe.db.exists("Role", clean_role):
                raise frappe.ValidationError(
                    f"Steward role {clean_role} no longer exists; repair "
                    "the policy version before validating")
        before = configuration_audit.latest_after_hash(doc.name)
        after = configuration_rules.snapshot_digest(versions)
        readiness = configuration_rules.compute_readiness(
            status=doc.status, versions=versions,
            validations=[{"after_hash": after}],
            today=frappe.utils.today(), what="metric-stewardship policy")
        return _policy_result(doc, extra={"readiness": readiness}), {
            "target": doc.name, "before_hash": before, "after_hash": after,
        }

    payload = {"policy": policy}
    return configuration_audit.execute(
        "validate_metric_stewardship_policy", request_key, payload, work)
