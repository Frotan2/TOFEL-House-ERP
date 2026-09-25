"""TOEFL House Configuration desk: the configuration map, as a surface.

Audience: Course Owner only. This desk is a read-only map over the nine
configuration domains — it shows each domain's computed configuration
readiness and links to the domain's own surface. It configures nothing
itself and offers no mutating action in Phase 1.

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
STEWARDSHIP_POLICY = "TH Metric Stewardship Policy"
STEWARDSHIP_VERSION = "TH Metric Stewardship Policy Version"
CONFIG_AUDIT = "TH Configuration Audit Event"

POLICY_FIELDS = ["name", "family", "code", "title", "status", "description",
                 "modified"]
FACET_FIELDS = ["components", "weights", "pass_rules", "rubrics",
                "progression", "retakes", "level_mapping"]
VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                  "grading_scale"] + FACET_FIELDS + [
                      "reason", "set_by", "set_on", "superseded_on"]
STEWARDSHIP_FIELDS = ["name", "code", "title", "status", "description",
                      "modified"]
STEWARDSHIP_VERSION_FIELDS = ["name", "parent", "parenttype",
                              "effective_from", "steward_role", "reason",
                              "set_by", "set_on", "superseded_on"]

# Domains with no configuration surface yet. Each renders as an
# explicit "not implemented" fact — never a dead link, never a guessing
# readiness badge. (Reporting & Metrics left this list when the D7
# metric-stewardship carrier shipped on 2026-09-25.)
FUTURE_DOMAINS = (
    ("finance", "Finance",
     "Correction terms live on the Finance desk; tax readiness arrives "
     "in a later phase."),
    ("student-guardian", "Student & Guardian",
     "Delegation and guardianship rules arrive in a later phase."),
    ("enrollment-lifecycle", "Enrollment & Lifecycle",
     "Calendar and lifecycle rules arrive in a later phase."),
    ("operations", "Operations",
     "Capacity objectives arrive in a later phase."),
    ("backup-recovery", "Backup & Recovery",
     "Offsite destination records arrive in a later phase."),
    ("security", "Security",
     "Custody records arrive in a later phase; safety controls stay "
     "code-controlled and are never configured from any desk."),
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

    stewardship = project_rows("configuration", STEWARDSHIP_POLICY,
                               STEWARDSHIP_FIELDS, order_by="code asc",
                               limit=LIMIT_QUEUES)
    stewardship_versions = project_rows(
        "configuration", STEWARDSHIP_VERSION, STEWARDSHIP_VERSION_FIELDS,
        filters={"parenttype": STEWARDSHIP_POLICY},
        order_by="effective_from asc", limit=LIMIT_QUEUES * 4)
    stewardship_by_policy = {}
    for row in stewardship_versions:
        stewardship_by_policy.setdefault(row.get("parent"), []).append(row)

    readiness_by_policy, faults = _domain_readiness(
        policies, versions_by_policy, today, "assessment policy",
        "validate_assessment_policy", _current_validation)
    stewardship_readiness, stewardship_faults = _domain_readiness(
        stewardship, stewardship_by_policy, today, "metric-stewardship policy",
        "validate_metric_stewardship_policy", _current_validation)
    all_faults = faults + stewardship_faults

    sections = [
        section("academic", "Academic", "links",
                items=[{"title": "Academic Setup",
                        "slug": "th-academic-setup"}],
                empty_title="Academic Setup",
                empty_body="Programs, levels, durations, progression and the "
                           "D1 assessment reference live on Academic Setup."),
    ]
    for sid, title, body in FUTURE_DOMAINS:
        sections.append(section(sid, title, "facts",
                                facts=[{
                                    "value": "Not implemented",
                                    "label": "Configuration surface",
                                    "definition": body,
                                }],
                                empty_title=f"{title} is not implemented",
                                empty_body=body))
    sections.append(
        section("reporting-metrics", "Reporting & Metrics", "facts",
                facts=_stewardship_facts(stewardship, stewardship_readiness,
                                         stewardship_by_policy, today),
                empty_title="No metric-stewardship policy exists",
                empty_body="Derived metrics stay refused (fail-closed) until "
                           "the Course Owner enters the steward and "
                           "disclosure policy."))
    sections.append(section("system-readiness", "System Readiness", "queue",
                            items=_readiness_items(
                                policies, versions_by_policy,
                                readiness_by_policy, all_faults, today,
                                stewardship, stewardship_by_policy,
                                stewardship_readiness),
                            empty_title="Nothing configured yet",
                            empty_body="No assessment policy exists; the "
                                       "Academic domain is incomplete."))
    return {
        "desk": SLUG,
        "sections": sections,
    }


def _domain_readiness(policies, versions_by_policy, today, what,
                      validate_action, evidence_lookup):
    """Computed readiness per policy for one domain (assessment/stewardship).

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


def _stewardship_facts(policies, readiness_by_policy, versions_by_policy,
                       today):
    """The Reporting & Metrics domain facts for the configuration map.

    The D7 carrier is a shell with no owner values until the Course Owner
    versions it; the desk says exactly that, and names the governing
    steward only when the engine computes one. Fail-closed language is
    deliberate: derived metrics refuse while nothing governs.
    """
    facts = []
    for policy in policies:
        readiness = readiness_by_policy.get(policy["name"])
        if not readiness:
            continue
        rows = versions_by_policy.get(policy["name"], [])
        governing = foundation.resolve_governing(rows, today)
        steward = (governing.get("steward_role") or "") if governing else ""
        facts.append({
            "value": readiness.capitalize(),
            "label": f"{policy['code']} configuration readiness",
            "definition": (
                "Metric stewardship governs whether derived metrics may be "
                "defined at all. "
                + (f"Governing since {governing.get('effective_from')} "
                   f"with steward role {steward}."
                   if governing else
                   ("Versions exist but none governs today."
                    if rows else
                    "No versions; derived metrics stay refused "
                    "(fail-closed).")))})
    return facts


def _readiness_items(policies, versions_by_policy, readiness_by_policy,
                     faults, today, stewardship=(), stewardship_by_policy=None,
                     stewardship_readiness=None):
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
    for policy in (stewardship or []):
        name = policy["name"]
        readiness = (stewardship_readiness or {}).get(name)
        if not readiness:
            continue
        rows = (stewardship_by_policy or {}).get(name, [])
        governing = foundation.resolve_governing(rows, today)
        detail = f"{len(rows)} version(s)"
        if governing:
            detail += f"; governing since {governing.get('effective_from')}"
            steward = governing.get("steward_role") or ""
            detail += f"; steward role: {steward}" if steward else "; no steward named"
        elif rows:
            detail += "; nothing effective yet"
        else:
            detail += "; no versions"
        items.append({
            "id": policy["code"],
            "person": policy["title"],
            "detail": detail,
            "status": readiness.capitalize(),
            "stage": "Reporting & Metrics",
            "stage_definition": ("Computed configuration readiness for the "
                                 "D7 metric-stewardship policy. Derived "
                                 "metrics stay refused until a version "
                                 "governs. Production readiness is separate "
                                 "and is never decided here."),
            "next": _readiness_next(policy, readiness, governing, rows,
                                    "through the guarded "
                                    "metric-stewardship commands"),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    for sid, title, _body in FUTURE_DOMAINS:
        items.append({
            "id": sid,
            "person": title,
            "detail": "No configuration surface in Phase 1.",
            "status": "Not implemented",
            "stage": "Configuration",
            "stage_definition": ("This domain has no configuration records "
                                 "yet, so readiness cannot be computed."),
            "next": f"{title} configuration arrives in a later phase.",
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
