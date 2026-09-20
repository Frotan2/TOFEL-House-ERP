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
CONFIG_AUDIT = "TH Configuration Audit Event"

POLICY_FIELDS = ["name", "family", "code", "title", "status", "description",
                 "modified"]
FACET_FIELDS = ["components", "weights", "pass_rules", "rubrics",
                "progression", "retakes", "level_mapping"]
VERSION_FIELDS = ["name", "parent", "parenttype", "effective_from",
                  "grading_scale"] + FACET_FIELDS + [
                      "reason", "set_by", "set_on", "superseded_on"]

# Domains with no configuration surface in Phase 1. Each renders as an
# explicit "not implemented" fact — never a dead link, never a guessing
# readiness badge.
FUTURE_DOMAINS = (
    ("finance", "Finance",
     "Correction terms live on the Finance desk; tax readiness arrives "
     "in a later phase."),
    ("student-guardian", "Student & Guardian",
     "Delegation and guardianship rules arrive in a later phase."),
    ("enrollment-lifecycle", "Enrollment & Lifecycle",
     "Calendar and lifecycle rules arrive in a later phase."),
    ("reporting-metrics", "Reporting & Metrics",
     "Metric definitions arrive in a later phase."),
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

    readiness_by_policy = {}
    faults = []
    for policy in policies:
        name = policy["name"]
        rows = versions_by_policy.get(name, [])
        snapshot = foundation.snapshot_digest(rows)
        evidence = ([{"after_hash": snapshot}]
                    if rows and _current_validation(name, snapshot)
                    else [])
        try:
            readiness_by_policy[name] = foundation.compute_readiness(
                status=policy.get("status"), versions=rows,
                validations=evidence, today=today,
                what="assessment policy")
        except ValueError as exc:
            # Ambiguous history is an integrity fault: surfaced, never
            # hidden, and never rendered as a readiness state.
            readiness_by_policy[name] = ""
            faults.append(f"{policy.get('code')}: {exc}")

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
    sections.append(section("system-readiness", "System Readiness", "queue",
                            items=_readiness_items(policies, versions_by_policy,
                                                   readiness_by_policy, faults,
                                                   today),
                            empty_title="Nothing configured yet",
                            empty_body="No assessment policy exists; the "
                                       "Academic domain is incomplete."))
    return {
        "desk": SLUG,
        "sections": sections,
    }


def _current_validation(policy_name, snapshot):
    """Whether a validation event commits to this exact version snapshot.

    Matched by count, never projected: the hash stays in the filter, so no
    hash field ever enters a desk projection (read-boundary discipline).
    One bounded count per policy; policies are few by nature.
    """
    return project_count("configuration", CONFIG_AUDIT, filters={
        "target": policy_name, "action": "validate_assessment_policy",
        "after_hash": snapshot,
    }) > 0


def _readiness_items(policies, versions_by_policy, readiness_by_policy,
                     faults, today):
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


def _readiness_next(policy, readiness, governing, rows):
    code = policy["code"]
    if readiness == "incomplete":
        return (f"Add the first version of {code} on Academic Setup; the "
                "policy governs nothing until then.")
    if readiness == "configured":
        return (f"Validate {code} on Academic Setup; versions exist but no "
                "validation covers the current set.")
    if readiness == "validated":
        first = min(str(row.get("effective_from") or "") for row in rows)
        return (f"{code} is validated and takes effect {first}.")
    if readiness == "effective":
        return (f"{code} governs since "
                f"{governing.get('effective_from') if governing else 'its effective date'}.")
    return f"{code} is retired; it governs nothing."
