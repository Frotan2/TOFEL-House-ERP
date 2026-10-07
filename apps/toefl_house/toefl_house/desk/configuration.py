"""TOEFL House Configuration desk: the Course Owner configuration map and guarded control surface.

Audience: Course Owner only. This desk is a projection over the configuration
domains. It computes readiness from canonical records and exposes guarded
Course Owner actions where the domain has a supported configuration carrier.
The desk never mutates documents directly and never decides production
readiness.

Two honesties are load-bearing here:

- Configuration readiness (incomplete/configured/validated/effective/
  retired) is COMPUTED from records on every load. It is not stored, not
  toggled, and shares no inputs with production readiness.
- Production readiness is separate and is never decided here: this desk
  shows configuration state only, and says so on the face of the
  System Readiness section.
"""
import frappe

from toefl_house.configuration import rules as foundation
from toefl_house.desk import (
    LIMIT_QUEUES,
    project_count,
    project_rows,
    require_desk_audience,
    section,
)

SLUG = "th-configuration"

ASSESSMENT_POLICY = "TH Assessment Policy"
ASSESSMENT_VERSION = "TH Assessment Policy Version"
ALERTING_POLICY = "TH Alerting Policy"
ALERTING_VERSION = "TH Alerting Policy Version"
GUARDIAN_POLICY = "TH Guardian Lifecycle Policy"
GUARDIAN_VERSION = "TH Guardian Lifecycle Policy Version"
OWNER_POLICY = "TH Owner Operations Policy"
OWNER_VERSION = "TH Owner Operations Policy Version"
CONFIG_AUDIT = "TH Configuration Audit Event"

NATIVE_OWNER_POLICIES = (
    ("catalog-linkage", "Catalog Linkage", "TH Catalog Linkage Policy",
     "toefl_house.academic.catalog_linkage.create_catalog_linkage_policy",
     "toefl_house.academic.catalog_linkage.set_catalog_linkage_version",
     "toefl_house.academic.catalog_linkage.set_catalog_linkage_status",
     "The Course Owner controls whether catalog linkage is advisory or enforcing."),
    ("returning-student", "Returning Student", "TH Returning Student Policy",
     "toefl_house.admission.policies.create_returning_student_policy",
     "toefl_house.admission.policies.set_returning_student_policy_version",
     "toefl_house.admission.policies.set_returning_student_policy_status",
     "The Course Owner controls the returning-student intake mode."),
    ("enrollment-exit", "Enrollment Exit", "TH Enrollment Exit Policy",
     "toefl_house.enrollment.exits.create_enrollment_exit_policy",
     "toefl_house.enrollment.exits.set_enrollment_exit_policy_version",
     "toefl_house.enrollment.exits.set_enrollment_exit_policy_status",
     "The Course Owner controls the approver role for enrollment exits."),
    ("billing", "Billing", "TH Billing Policy",
     "toefl_house.finance.policies.create_billing_policy",
     "toefl_house.finance.policies.set_billing_policy_version",
     "toefl_house.finance.policies.set_billing_policy_status",
     "The Course Owner controls posting bounds and placement-fee timing."),
    ("roster-change", "Roster Change", "TH Roster Change Policy",
     "toefl_house.teaching.policies.create_roster_change_policy",
     "toefl_house.teaching.policies.set_roster_change_policy_version",
     "toefl_house.teaching.policies.set_roster_change_policy_status",
     "The Course Owner controls the roster-change cutoff."),
    ("attendance-correction", "Attendance Correction", "TH Attendance Correction Policy",
     "toefl_house.teaching.attendance_corrections.create_attendance_correction_policy",
     "toefl_house.teaching.attendance_corrections.set_attendance_correction_policy_version",
     "toefl_house.teaching.attendance_corrections.set_attendance_correction_policy_status",
     "The Course Owner controls the correction approver and correction window."),
    ("adjustment-posting", "Adjustment Posting", "TH Adjustment Posting Policy",
     "toefl_house.teaching.adjustment_posting.create_adjustment_posting_policy",
     "toefl_house.teaching.adjustment_posting.set_adjustment_posting_version",
     "toefl_house.teaching.adjustment_posting.set_adjustment_posting_status",
     "The Course Owner controls orphan payroll posting behavior."),
)


POLICY_FIELDS = ["name", "family", "code", "title", "status", "description",
                 "modified"]
FACET_FIELDS = ["components", "weights", "pass_rules", "rubrics",
                "progression", "retakes", "level_mapping"]
VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                  "grading_scale"] + FACET_FIELDS + [
                      "reason", "set_by", "set_on", "superseded_on"]
ALERTING_FIELDS = ["name", "code", "title", "status", "description",
                   "modified"]
ALERTING_VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                           "channel_kind", "escalate_after_minutes",
                           "retention_days", "reason", "set_by", "set_on",
                           "superseded_on"]
GUARDIAN_VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                           "delegation_window_days", "pre_admission_proxy",
                           "consent_evidence", "consent_expiry_days",
                           "reason", "set_by", "set_on", "superseded_on"]

# Domains with no configuration surface yet. Each renders as an
# explicit "not implemented" fact — never a dead link, never a guessing
# readiness badge.
FUTURE_DOMAINS = (
    ("reporting-metrics", "Reporting & Metrics",
     "Owner-selected reporting review interval and class-capacity target "
     "are carried by TH Owner Operations Policy."),
    ("finance", "Finance",
     "Billing and correction authorities remain on the Finance desk; "
     "tax terms are carried by TH Owner Operations Policy."),
    ("enrollment-lifecycle", "Enrollment & Lifecycle",
     "Withdrawal/dismissal remains governed by Enrollment Exit Policy; "
     "transfer and calendar terms are carried by TH Owner Operations Policy."),
    ("backup-recovery", "Backup & Recovery",
     "Off-site requirement and non-secret destination reference are carried "
     "by TH Owner Operations Policy; credentials are never stored there."),
    ("security", "Security",
     "Custody requirements and recovery quorum may be recorded as policy "
     "requirements; keys, credentials, custodians and authorization "
     "ceremonies remain outside Frappe."),
)


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Configuration map payload: nine domain sections, computed readiness."""
    require_desk_audience(SLUG)
    today = frappe.utils.today()

    policies = project_rows("configuration", ASSESSMENT_POLICY, POLICY_FIELDS,
                            order_by="code asc", limit=LIMIT_QUEUES)
    versions = project_rows("configuration", ASSESSMENT_VERSION,
                            VERSION_FIELDS,
                            filters={"parenttype": ASSESSMENT_POLICY},
                            order_by="effective_from asc",
                            limit=LIMIT_QUEUES * 4)

    versions_by_policy = {}
    for row in versions:
        versions_by_policy.setdefault(row.get("parent"), []).append(row)

    readiness_by_policy, faults = _domain_readiness(
        policies, versions_by_policy, today, "assessment policy",
        "validate_assessment_policy", _current_validation)
    alerting = project_rows("configuration", ALERTING_POLICY,
                            ALERTING_FIELDS, order_by="code asc",
                            limit=LIMIT_QUEUES)
    alerting_versions = project_rows(
        "configuration", ALERTING_VERSION, ALERTING_VERSION_FIELDS,
        filters={"parenttype": ALERTING_POLICY},
        order_by="effective_from asc", limit=LIMIT_QUEUES * 4)
    alerting_by_policy = {}
    for row in alerting_versions:
        alerting_by_policy.setdefault(row.get("parent"), []).append(row)
    alerting_readiness, alerting_faults = _domain_readiness(
        alerting, alerting_by_policy, today, "alerting policy",
        "validate_alerting_policy", _current_validation)
    guardian = project_rows("configuration", GUARDIAN_POLICY,
                            ALERTING_FIELDS, order_by="code asc",
                            limit=LIMIT_QUEUES)
    guardian_versions = project_rows(
        "configuration", GUARDIAN_VERSION, GUARDIAN_VERSION_FIELDS,
        filters={"parenttype": GUARDIAN_POLICY},
        order_by="effective_from asc", limit=LIMIT_QUEUES * 4)
    guardian_by_policy = {}
    for row in guardian_versions:
        guardian_by_policy.setdefault(row.get("parent"), []).append(row)
    guardian_readiness, guardian_faults = _domain_readiness(
        guardian, guardian_by_policy, today, "guardian lifecycle policy",
        "validate_guardian_lifecycle_policy", _current_validation)
    all_faults = faults + alerting_faults + guardian_faults

    sections = [
        section("academic", "Academic", "links",
                items=[{"title": "Academic Setup",
                        "slug": "th-academic-setup"}],
                empty_title="Academic Setup",
                empty_body="Programs, levels, durations, progression and the "
                           "D1 assessment reference live on Academic Setup."),
    ]
    for sid, title, body in FUTURE_DOMAINS:
        sections.append(section(sid, title, "queue",
                                items=[_owner_policy_item(today, title, body)],
                                empty_title=title,
                                empty_body=body))
    sections.append(
        section("owner-policies", "Course Owner Policy Controls", "queue",
                items=[_native_owner_policy_item(*spec) for spec in NATIVE_OWNER_POLICIES],
                empty_title="No native policy controls",
                empty_body="Native Course Owner policies are indexed here; mutations still use their guarded domain commands."))
    sections.append(
        section("student-guardian", "Student & Guardian", "facts",
                facts=_guardian_facts(guardian, guardian_readiness,
                                      guardian_by_policy, today),
                empty_title="No guardian lifecycle policy exists",
                empty_body="Advanced guardian features stay refused "
                           "(fail-closed) until the Course Owner enters the "
                           "guardian lifecycle terms; identity and guardian "
                           "access remain exactly as the SEC-GUARDIAN-01 "
                           "containment enforces."))
    sections.append(
        section("operations", "Operations", "facts",
                facts=_alerting_facts(alerting, alerting_readiness,
                                      alerting_by_policy, today),
                empty_title="No alerting policy exists",
                empty_body="Alert delivery stays refused (fail-closed) until "
                           "the Course Owner selects a receiver and its "
                           "retention terms."))
    sections.append(section("system-readiness", "System Readiness", "queue",
                            items=_readiness_items(
                                policies, versions_by_policy,
                                readiness_by_policy, all_faults, today,
                                alerting,
                                alerting_by_policy, alerting_readiness,
                                guardian,
                                guardian_by_policy, guardian_readiness),
                            empty_title="Nothing configured yet",
                            empty_body="No assessment policy exists; the "
                                       "Academic domain is incomplete."))
    return {
        "desk": SLUG,
        "sections": sections,
    }



def _native_owner_policy_item(sid, title, doctype, create_endpoint,
                               version_endpoint, status_endpoint, description):
    """Index an existing canonical policy without creating a second authority."""
    rows = project_rows("configuration", doctype,
                        ["name", "code", "title", "status", "description", "modified"],
                        limit=1)
    if not rows:
        return {
            "id": sid, "person": title,
            "detail": "No policy shell exists; the governed feature stays fail-closed until the Course Owner configures it.",
            "status": "Owner configuration required", "stage": "Course Owner policy",
            "stage_definition": description,
            "next": "Create the policy shell, then add and validate its first effective-dated version.",
            "next_role": "Course Owner", "waiting_since": None,
            "action": {"endpoint": create_endpoint, "label": "Create policy",
                       "args": {"code": "", "title": title, "description": description}},
        }
    row = rows[0]
    status = row.get("status") or ""
    return {
        "id": row["code"], "person": row["title"],
        "detail": description,
        "status": "Owner policy active" if status == "Active" else "Owner policy retired",
        "stage": "Course Owner policy", "stage_definition": description,
        "next": "Add or replace effective-dated terms, then validate the current policy.",
        "next_role": "Course Owner", "waiting_since": None,
        "actions": [
            {"endpoint": version_endpoint, "label": "Set policy version",
             "args": {"policy": row["code"]}},
            {"endpoint": status_endpoint, "label": "Change policy status",
             "args": {"policy": row["code"]}},
        ],
    }


def _owner_policy_item(today, title, body):
    """Project the canonical Course Owner carrier and its guarded commands."""
    policy = project_rows("configuration", OWNER_POLICY,
                          ["name", "code", "title", "status", "description"],
                          limit=1)
    if not policy:
        status = "Owner configuration required"
        detail = "No owner policy exists yet; this domain has no governing terms."
        next_text = "Create TH Owner Operations Policy, then add and validate its first effective-dated version."
        return {
            "id": OWNER_POLICY, "person": "TH Owner Operations Policy",
            "detail": detail, "status": status, "stage": "Owner configuration",
            "stage_definition": body, "next": next_text,
            "next_role": "Course Owner", "waiting_since": None,
            "action": {
                "endpoint": "toefl_house.operations.owner_configuration.create_owner_operations_policy",
                "label": "Create owner policy",
                "args": {"code": "TH-OWNER-OPS", "title": "TH Owner Operations Policy"}
            },
        }
    row = policy[0]
    status = row["status"]
    detail = "Canonical owner terms cover reporting, capacity, tax, transfer/withdrawal, calendar, backup and custody requirements."
    if status != "Active":
        status_label = "Owner policy retired"
        next_text = "Reactivate the owner policy before relying on these terms."
    else:
        status_label = "Owner policy active"
        next_text = "Add or replace effective-dated terms, then validate the current policy."
    return {
        "id": row["code"], "person": row["title"],
        "detail": detail, "status": status_label, "stage": "Owner configuration",
        "stage_definition": body, "next": next_text,
        "next_role": "Course Owner", "waiting_since": None,
        "actions": [
            {
                "endpoint": "toefl_house.operations.owner_configuration.set_owner_operations_policy_version",
                "label": "Set policy version", "args": {"policy": row["code"]}
            },
            {
                "endpoint": "toefl_house.operations.owner_configuration.validate_owner_operations_policy",
                "label": "Validate policy", "args": {"policy": row["code"]}
            },
            {
                "endpoint": "toefl_house.operations.owner_configuration.set_owner_operations_policy_status",
                "label": "Change policy status", "args": {"policy": row["code"]}
            },
        ],
    }

def _domain_readiness(policies, versions_by_policy, today, what,
                      validate_action, evidence_lookup):
    """Computed readiness per policy for one domain (assessment/alerting/guardian).

    Same rule for both carriers: evidence is matched by count against the
    exact current snapshot, ambiguous history surfaces as an integrity
    fault, never a readiness state.
    """
    readiness_by_policy = {}
    faults = []
    for policy in policies:
        name = policy["name"]
        rows = versions_by_policy.get(name, [])
        snapshot = foundation.snapshot_digest(rows)
        evidence = ([{"after_hash": snapshot}]
                    if rows and evidence_lookup(name, snapshot,
                                                validate_action)
                    else [])
        try:
            readiness_by_policy[name] = foundation.compute_readiness(
                status=policy.get("status"), versions=rows,
                validations=evidence, today=today, what=what)
        except ValueError as exc:
            # Ambiguous history is an integrity fault: surfaced, never
            # hidden, and never rendered as a readiness state.
            readiness_by_policy[name] = ""
            faults.append(f"{policy.get('code')}: {exc}")
    return readiness_by_policy, faults


def _current_validation(policy_name, snapshot, validate_action):
    """Whether a validation event commits to this exact version snapshot.

    Matched by count, never projected: the hash stays in the filter, so no
    hash field ever enters a desk projection (read-boundary discipline).
    One bounded count per policy; policies are few by nature.
    """
    return project_count("configuration", CONFIG_AUDIT, filters={
        "target": policy_name, "action": validate_action,
        "after_hash": snapshot,
    }) > 0


def _alerting_facts(policies, readiness_by_policy, versions_by_policy,
                    today):
    """The Operations domain facts for the configuration map.

    The alerting carrier records WHICH receiver the owner selected and
    the retention/escalation terms around it; it never delivers. The desk
    names the governing channel kind and terms only when the engine
    computes a governing version — alert delivery stays refused
    (fail-closed) while nothing governs.
    """
    facts = []
    for policy in policies:
        readiness = readiness_by_policy.get(policy["name"])
        if not readiness:
            continue
        rows = versions_by_policy.get(policy["name"], [])
        governing = foundation.resolve_governing(rows, today)
        channel = (governing.get("channel_kind") or "") if governing else ""
        retention = governing.get("retention_days") if governing else None
        escalation = (governing.get("escalate_after_minutes")
                      if governing else None)
        facts.append({
            "value": readiness.capitalize(),
            "label": f"{policy['code']} configuration readiness",
            "definition": (
                "The alerting policy records the selected alert receiver "
                "and its retention terms; nothing is delivered from this "
                "desk. "
                + (f"Governing since {governing.get('effective_from')} "
                   f"on channel {channel}, retained {retention} day(s)"
                   + (f", escalating after {escalation} minute(s)."
                      if escalation else "."))
                if governing else
                ("Versions exist but none governs today."
                 if rows else
                 "No versions; alert delivery stays refused "
                 "(fail-closed)."))})
    return facts


def _guardian_facts(policies, readiness_by_policy, versions_by_policy,
                    today):
    """The Student & Guardian domain facts for the configuration map.

    The O-D4 carrier records the lifecycle TERMS only; identity and
    guardian access stay exactly as SEC-GUARDIAN-01 enforces until the
    policy governs — the desk says that on the face of every fact.
    Fail-closed language is deliberate: advanced guardian features
    refuse while nothing governs.
    """
    facts = []
    for policy in policies:
        readiness = readiness_by_policy.get(policy["name"])
        if not readiness:
            continue
        rows = versions_by_policy.get(policy["name"], [])
        governing = foundation.resolve_governing(rows, today)
        window = (governing.get("delegation_window_days")
                  if governing else None)
        facts.append({
            "value": readiness.capitalize(),
            "label": f"{policy['code']} configuration readiness",
            "definition": (
                "The guardian lifecycle policy records the owner's "
                "delegation, proxy, consent and records-rights terms; "
                "identity and guardian access stay exactly as the "
                "SEC-GUARDIAN-01 containment enforces while no policy "
                "governs. "
                + (f"Governing since {governing.get('effective_from')} "
                   f"with a delegation window of {window} day(s).")
                if governing else
                ("Versions exist but none governs today; advanced guardian "
                 "features stay refused (fail-closed)."
                 if rows else
                 "No versions; advanced guardian features stay refused "
                 "(fail-closed)."))})
    return facts


def _readiness_items(policies, versions_by_policy, readiness_by_policy,
                     faults, today, alerting=(),
                     alerting_by_policy=None, alerting_readiness=None, guardian=(),
                     guardian_by_policy=None, guardian_readiness=None):
    items = []
    for fault in faults:
        items.append({
            "id": "fault",
            "person": "Configuration integrity fault",
            "detail": fault,
            "status": "Integrity fault",
            "stage": "Configuration",
            "stage_definition": ("The version history contradicts itself, "
                                 "so no readiness state can be computed."),
            "next": ("Ask the administrator to repair the version history; "
                     "nothing resolves against it until then."),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    for policy in policies:
        name = policy["name"]
        readiness = readiness_by_policy[name]
        if not readiness:
            continue
        rows = versions_by_policy.get(name, [])
        governing = foundation.resolve_governing(rows, today)
        detail = f"{len(rows)} version(s)"
        if governing:
            detail += f"; governing since {governing.get('effective_from')}"
            defined = [facet.replace("_", " ") for facet in FACET_FIELDS
                       if governing.get(facet)]
            detail += ("; facets defined: " + ", ".join(defined)
                       if defined else "; no facets defined yet")
        elif rows:
            detail += "; nothing effective yet"
        else:
            detail += "; no versions"
        items.append({
            "id": policy["code"],
            "person": policy["title"],
            "detail": detail,
            "status": readiness.capitalize(),
            "stage": "Academic",
            "stage_definition": ("Computed configuration readiness for this "
                                 "assessment policy. Production readiness "
                                 "is separate and is never decided here."),
            "next": _readiness_next(policy, readiness, governing, rows),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    for policy in (alerting or []):
        name = policy["name"]
        readiness = (alerting_readiness or {}).get(name)
        if not readiness:
            continue
        rows = (alerting_by_policy or {}).get(name, [])
        governing = foundation.resolve_governing(rows, today)
        detail = f"{len(rows)} version(s)"
        if governing:
            detail += f"; governing since {governing.get('effective_from')}"
            channel = governing.get("channel_kind") or ""
            detail += (f"; channel: {channel}" if channel
                       else "; no channel selected")
        elif rows:
            detail += "; nothing effective yet"
        else:
            detail += "; no versions"
        items.append({
            "id": policy["code"],
            "person": policy["title"],
            "detail": detail,
            "status": readiness.capitalize(),
            "stage": "Operations",
            "stage_definition": ("Computed configuration readiness for the "
                                 "alerting receiver policy. Alert delivery "
                                 "stays refused until a version governs. "
                                 "Production readiness is separate and is "
                                 "never decided here."),
            "next": _readiness_next(policy, readiness, governing, rows,
                                    "through the guarded "
                                    "alerting commands"),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    for policy in (guardian or []):
        name = policy["name"]
        readiness = (guardian_readiness or {}).get(name)
        if not readiness:
            continue
        rows = (guardian_by_policy or {}).get(name, [])
        governing = foundation.resolve_governing(rows, today)
        detail = f"{len(rows)} version(s)"
        if governing:
            detail += f"; governing since {governing.get('effective_from')}"
            window = governing.get("delegation_window_days")
            detail += (f"; delegation window: {window} day(s)" if window
                       else "; no terms set")
        elif rows:
            detail += "; nothing effective yet"
        else:
            detail += "; no versions"
        items.append({
            "id": policy["code"],
            "person": policy["title"],
            "detail": detail,
            "status": readiness.capitalize(),
            "stage": "Student & Guardian",
            "stage_definition": ("Computed configuration readiness for the "
                                 "guardian lifecycle policy. Advanced "
                                 "guardian features stay refused until a "
                                 "version governs; identity and guardian "
                                 "access remain exactly as the "
                                 "SEC-GUARDIAN-01 containment enforces. "
                                 "Production readiness is separate and is "
                                 "never decided here."),
            "next": _readiness_next(policy, readiness, governing, rows,
                                    "through the guarded "
                                    "guardian-lifecycle commands"),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    for sid, title, _body in FUTURE_DOMAINS:
        items.append({
            "id": sid,
            "person": title,
            "detail": "Terms are carried by TH Owner Operations Policy or the existing domain authority.",
            "status": "Carrier available",
            "stage": "Configuration",
            "stage_definition": ("This domain has no configuration records "
                                 "yet, so readiness cannot be computed."),
            "next": f"{title} is configured through the owner policy carrier or its existing native policy surface.",
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    return items


def _readiness_next(policy, readiness, governing, rows,
                    surface="on Academic Setup"):
    code = policy["code"]
    if readiness == "incomplete":
        return (f"Add the first version of {code} {surface}; the "
                "policy governs nothing until then.")
    if readiness == "configured":
        return (f"Validate {code} {surface}; versions exist but no "
                "validation covers the current set.")
    if readiness == "validated":
        first = min(str(row.get("effective_from") or "") for row in rows)
        return (f"{code} is validated and takes effect {first}.")
    if readiness == "effective":
        return (f"{code} governs since "
                f"{governing.get('effective_from') if governing else 'its effective date'}.")
    return f"{code} is retired; it governs nothing."
