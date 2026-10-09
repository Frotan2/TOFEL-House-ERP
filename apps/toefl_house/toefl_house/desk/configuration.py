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
from toefl_house.enrollment.exits import governing_exit_terms
from toefl_house.operations.owner_configuration import current_backup_policy
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
     "The guarded exit commands fail closed unless the effective version cites a resolved Course Owner decision in the immutable release copy of docs/owner-decisions.json. The record must explicitly supersede D5, name the exact exit scope, and authorize both withdrawal and dismissal; a reason or well-formed but unrecorded reference cannot activate exits. Canonical D5 currently defers withdrawal/transfer terms. The separate Owner Operations withdrawal field is not consumed here."),
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

# Domains whose business policy remains a decision input without a qualified
# canonical runtime consumer. Each renders as an explicit deferred fact —
# never a dead link, never a guessing readiness badge.
FUTURE_DOMAINS = (
    ("reporting-metrics", "Reporting & Metrics",
     "Owner-selected reporting review interval and class-capacity target are Owner decision inputs; "
     "no derived metric or capacity enforcement consumes them until its canonical domain authority is explicitly bound."),
    ("finance", "Finance",
     "Billing and correction authorities remain on the Finance desk; tax terms are a decision carrier only "
     "and are NOT a live tax authority until a native finance consumer is explicitly implemented and qualified."),
    ("enrollment-lifecycle", "Enrollment & Lifecycle",
     "The guarded Enrollment Exit Policy is the withdrawal/dismissal resolver. Canonical D5 still defers withdrawal/transfer; exits remain fail-closed until a release-packaged, resolved Course Owner record explicitly supersedes D5 and authorizes both exit actions. Transfer and calendar carrier fields have no runtime consumer."),
    ("security", "Security",
     "Custody requirements and recovery quorum are decision requirements only; recording them is not proof "
     "that recovery controls are implemented. Keys, credentials, custodians and authorization ceremonies remain outside Frappe."),
)

CURRENT_BACKUP_DOMAIN = (
    "Backup & Recovery",
    "Intended local scope is a verified encrypted backup on a separate local drive. The Windows helper is on preservation hold: the Owner must explicitly choose to preserve all valid sets or authorize deletion of older valid sets beyond the keep count. There is no default; an unset choice blocks backup and activation. Do not run the helper or proceed through activation until the Owner resolves the retention behavior and the implementation/docs agree. Off-site, NAS, second-device and cloud copies remain deferred. Restore and release authorization require separate evidence.",
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
    backup_title, backup_body = CURRENT_BACKUP_DOMAIN
    sections.append(section(
        "backup-recovery", backup_title, "queue",
        items=[_owner_policy_item(today, backup_title, backup_body)],
        empty_title=backup_title, empty_body=backup_body))
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
                empty_body="Guardian lifecycle terms are a configuration carrier only; no runtime feature consumes them. Advanced guardian/portal features remain deferred and refused. Identity and access remain exactly as SEC-GUARDIAN-01 enforces, even if terms are later recorded."))
    sections.append(
        section("operations", "Operations", "facts",
                facts=_alerting_facts(alerting, alerting_readiness,
                                      alerting_by_policy, today),
                empty_title="No alerting policy exists",
                empty_body="The alerting policy records receiver and retention terms only; no runtime delivery consumer is implemented, so adding a version does not send alerts."))
    sections.append(section("system-readiness", "System Readiness", "queue",
                            items=_readiness_items(
                                policies, versions_by_policy,
                                readiness_by_policy, all_faults, today,
                                alerting,
                                alerting_by_policy, alerting_readiness,
                                guardian,
                                guardian_by_policy, guardian_readiness),
                            empty_title="Nothing configured yet",
                            empty_body="No assessment policy exists. Academic grading and progression remain deferred by D1; this readiness section reports configuration only, and nothing computes grades or promotion decisions."))
    return {
        "desk": SLUG,
        "sections": sections,
    }



def _native_owner_policy_item(sid, title, doctype, create_endpoint,
                               version_endpoint, status_endpoint, description):
    """Index an existing canonical policy without creating a second authority."""
    fields = ["name", "code", "title", "status", "description", "modified"]
    projectors = {
        "TH Catalog Linkage Policy": lambda: project_rows("configuration", "TH Catalog Linkage Policy", fields, limit=1),
        "TH Returning Student Policy": lambda: project_rows("configuration", "TH Returning Student Policy", fields, limit=1),
        "TH Enrollment Exit Policy": lambda: project_rows("configuration", "TH Enrollment Exit Policy", fields, limit=1),
        "TH Billing Policy": lambda: project_rows("configuration", "TH Billing Policy", fields, limit=1),
        "TH Roster Change Policy": lambda: project_rows("configuration", "TH Roster Change Policy", fields, limit=1),
        "TH Attendance Correction Policy": lambda: project_rows("configuration", "TH Attendance Correction Policy", fields, limit=1),
        "TH Adjustment Posting Policy": lambda: project_rows("configuration", "TH Adjustment Posting Policy", fields, limit=1),
    }
    rows = projectors[doctype]()
    if not rows:
        next_text = (
            "Keep exits inactive. No resolved D5 supersession is currently in the canonical ledger. After the Course Owner's explicit decision is recorded and shipped, configure a version that cites its exact record ID; the guarded command resolves and audits it."
            if sid == "enrollment-exit" else
            "Create the policy shell, then add its first effective-dated version through the guarded command; that command validates and audits its terms.")
        return {
            "id": sid, "person": title,
            "detail": "No policy shell exists; the governed feature stays fail-closed until the Course Owner configures it.",
            "status": "Owner configuration required", "stage": "Course Owner policy",
            "stage_definition": description,
            "next": next_text,
            "next_role": "Course Owner", "waiting_since": None,
            "action": {"endpoint": create_endpoint, "label": "Create policy",
                       "args": {"code": "", "title": title, "description": description}},
        }
    row = rows[0]
    status = row.get("status") or ""
    detail = description
    if sid == "enrollment-exit" and status == "Active":
        terms = governing_exit_terms()
        if terms:
            status_label = "Exit policy authorized by resolved D5 supersession"
            detail = (description + " Current version cites canonical Owner decision " +
                      terms["superseding_owner_decision_reference"] +
                      " from " + terms["effective_from"] + ". The runtime resolved its scope and both authorized exit actions in the immutable release ledger.")
            next_text = "Keep the referenced Owner decision and this version's audit event together; use the guarded status command to retire exits if that authority is withdrawn."
        else:
            status_label = "Exit behavior fail-closed (D5 unresolved)"
            detail = (description + " No effective version resolves to an explicit, in-scope D5 supersession decision in the canonical release ledger.")
            next_text = "Keep exits inactive. Do not add a version until an explicit Owner decision that supersedes D5 and authorizes both withdrawal and dismissal is recorded in the canonical ledger and shipped; a reason or fabricated ID cannot activate exits."
    else:
        status_label = "Owner policy active" if status == "Active" else "Owner policy retired"
        next_text = "Append effective-dated terms or change status through this domain's guarded commands; each command validates its input and records the audit event."
    return {
        "id": row["code"], "person": row["title"],
        "detail": detail,
        "status": status_label,
        "stage": "Course Owner policy", "stage_definition": description,
        "next": next_text,
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
    is_backup = title == "Backup & Recovery"
    item_id = "backup-recovery" if is_backup else OWNER_POLICY
    policy = project_rows("configuration", OWNER_POLICY,
                          ["name", "code", "title", "status", "description"],
                          limit=1)
    if not policy:
        detail = (
            "No Owner Operations policy exists; no explicit retention behavior is configured, so backup and activation fail closed."
            if is_backup else
            "No owner policy exists yet; this domain has no governing terms.")
        next_text = (
            "After receiving the Course Owner's decision, create the policy and explicitly choose to preserve all valid sets or authorize deletion beyond the keep count; no default is supplied. Do not run the backup helper or proceed through activation while this choice is unresolved."
            if is_backup else
            "Create TH Owner Operations Policy, then add and validate its first effective-dated version.")
        return {
            "id": item_id, "person": title if is_backup else "TH Owner Operations Policy",
            "detail": detail,
            "status": "Owner configuration required", "stage": "Owner configuration",
            "stage_definition": body,
            "next": next_text,
            "next_role": "Course Owner", "waiting_since": None,
            "action": {
                "endpoint": "toefl_house.operations.owner_configuration.create_owner_operations_policy",
                "label": "Create owner policy",
                "args": {"code": "TH-OWNER-OPS", "title": "TH Owner Operations Policy"}
            },
        }
    row = policy[0]
    if row["status"] != "Active":
        status_label = "Owner policy retired"
        detail = "Owner policy is retired; its terms cannot govern the scheduled backup."
        next_text = "Reactivate the owner policy, then add and validate current effective-dated terms."
    elif is_backup:
        backup = current_backup_policy(today)
        if backup.get("configured") is True:
            status_label = "Backup policy configured"
            detail = (f"Nightly at {backup['schedule_time']} local time; "
                      f"configured keep count {backup['retention_versions']} "
                      "(used only in the explicit deletion mode); retention behavior: "
                      f"{backup['retention_behavior']}; the configured public recovery key "
                      "encrypts the site-config recovery artifact.")
            next_text = ("Keep the matching private recovery key under the Owner's separate custody requirement. The retention behavior must be an explicit Course Owner decision. Do not run Backup TOEFL House ERP.cmd or proceed through activation until the Owner resolves the preservation hold described in the launch runbook and the implementation/docs agree.")
        else:
            status_label = "Owner backup configuration required"
            detail = "Nightly schedule, multi-version retention count, explicit retention behavior (preserve all or authorize deletion beyond the keep count), or ASCII-armored public recovery key is missing or invalid. Backup activation remains refused."
            next_text = (
                "Complete every required Owner field with approved values "
                "(reporting review, class capacity, tax, transfers/withdrawals, "
                "calendar, nightly backup, retention count/behavior, public key, custody and "
                "quorum); no defaults or placeholders. Set an effective-dated "
                "version and validate it. Explicitly choose to preserve all "
                "valid sets or authorize deleting older valid sets beyond the "
                "keep count; there is no default. Do not run Backup TOEFL House "
                "ERP.cmd or proceed through activation until the Owner resolves "
                "this choice and the implementation/docs agree; see the launch "
                "runbook. Keep the matching private "
                "key outside Frappe and the backup drive."
            )
    else:
        status_label = "Owner policy active"
        detail = "The Owner Operations fields for reporting, capacity target, tax, transfer/withdrawal and calendar are decision inputs only; native ERPNext tax settings and the separate Enrollment Exit Policy remain their canonical authorities. This policy's runtime-bound domain is the current local backup path; custody/quorum records do not prove a ceremony."
        next_text = "Add or replace effective-dated terms, then validate the current policy."
    return {
        "id": item_id, "person": title if is_backup else row["title"],
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
                "The policy stores the selected alert receiver and retention "
                "terms only; no runtime delivery consumer exists, so even an "
                "effective version does not send alerts. "
                + (f"Effective in configuration since "
                   f"{governing.get('effective_from')} on channel {channel}, "
                   f"retained {retention} day(s)"
                   + (f", escalation term {escalation} minute(s)."
                      if escalation else "."))
                if governing else
                ("Versions exist but none is effective in configuration."
                 if rows else
                 "No versions are configured; no alert delivery is active."))})
    return facts


def _guardian_facts(policies, readiness_by_policy, versions_by_policy,
                    today):
    """The Student & Guardian configuration facts, not runtime activation.

    The D4 carrier records terms only and has no runtime consumer.
    Advanced guardian/portal features remain deferred and refused even
    when a policy version is effective; identity/access remain exactly
    as SEC-GUARDIAN-01 enforces until a separately approved consumer is
    implemented and qualified.
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
                "This carrier stores delegation, proxy, consent and records-"
                "rights terms only; it has no runtime consumer. Advanced "
                "guardian/portal features remain deferred and refused, and "
                "identity/access remain as SEC-GUARDIAN-01 enforces, even "
                "when a version is effective. "
                + (f"Effective in configuration since "
                   f"{governing.get('effective_from')} with a delegation "
                   f"window of {window} day(s).")
                if governing else
                ("Versions exist but none is effective in configuration."
                 if rows else
                 "No versions are configured."))})
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
            "stage_definition": ("Computed configuration readiness only. "
                                 "No runtime grading, assessment or student-"
                                 "progression consumer is implemented/qualified; "
                                 "Owner decision D1 remains deferred. "
                                 "Production readiness is separate and is "
                                 "never decided here."),
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
            "stage_definition": ("Computed configuration readiness only. "
                                 "No runtime alert-delivery consumer is "
                                 "implemented; an effective version does not "
                                 "send alerts. Production readiness is "
                                 "separate and is never decided here."),
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
            "stage_definition": ("Computed configuration readiness only. "
                                 "No runtime guardian consumer is "
                                 "implemented; advanced guardian features "
                                 "remain deferred/refused even when a version "
                                 "is effective, and identity/access remain as "
                                 "SEC-GUARDIAN-01 enforces. Production "
                                 "readiness is separate and is never decided "
                                 "here."),
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
        return (f"Add the first version of {code} {surface}; no effective "
                "configuration version exists yet.")
    if readiness == "configured":
        return (f"Validate {code} {surface}; versions exist but no "
                "validation covers the current set.")
    if readiness == "validated":
        first = min(str(row.get("effective_from") or "") for row in rows)
        return (f"{code} is validated; its configuration is effective from "
                f"{first}. This does not imply runtime activation.")
    if readiness == "effective":
        return (f"{code} is effective in configuration since "
                f"{governing.get('effective_from') if governing else 'its effective date'}; "
                "this desk status is not runtime activation.")
    return f"{code} is retired and has no effective configuration."
