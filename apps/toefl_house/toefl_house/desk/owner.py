"""Owner cockpit: business state with every definition stated.

Adds the fail-closed release posture (the same reviewed static facts the
administration control centre serves) to the operational projection. The
Owner role is Course Owner, the system owner of record. No business metric
without an owner-approved definition is invented here; every tile carries its
definition inline. Sections are specified in docs/product/ROLE-DESKS.md.
"""
import frappe

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_QUEUES,
    active_cohort_rows,
    project_count,
    project_rows,
    require_desk_audience,
    section,
    viewer_roles,
)
from toefl_house.desk import lifecycle
from toefl_house.desk.operations import _staff_counts, _role_items, _age_label

SLUG = "th-owner-cockpit"

ATTEMPT = "TH Placement Attempt"
ADMISSION = "TH Admission Decision"
DECISION = "TH Placement Decision"
STUDENT = "Student"
GROUP = "Student Group"

# The release posture facts are static, reviewed constants — the same records
# the canonical ledger and the administration control centre state. They are
# not computed from the database and no gate state can be derived here.
# Deployment value is the owner's selected current deployment (local/server
# through Tailscale) per canonical-owner-decision-record.json as of 2026-09-16.
# The line carries the as-of date so a future ledger change cannot silently
# stale the cockpit.
RELEASE_POSTURE = [
    {"label": "Production",
     "definition": "Production acceptance state from the acceptance ledger.",
     "value": "REJECT", "owner": None},
    {"label": "Dependency security (SEC-DEPS-01)",
     "definition": "Upstream dependency-audit failure; a hard production stop.",
     "value": "UPSTREAM-BLOCKED / REJECT", "owner": None},
    {"label": "Synthetic-only activation",
     "definition": "All owned business commands stay confined to explicitly isolated synthetic sites until the owner authorizes activation.",
     "value": "REQUIRED", "owner": None},
    {"label": "Deployment",
     "definition": "Current deployment decision recorded by the owner in canonical-owner-decision-record.json (as of 2026-09-16).",
     "value": "LOCAL_SERVER_TAILSCALE (as of 2026-09-16 per canonical-owner-decision-record.json)", "owner": None},
]


@frappe.whitelist(methods=["GET", "POST"])
def cockpit():
    """Owner cockpit payload: business state, exceptions, posture, desks."""
    require_desk_audience(SLUG)

    admissions_open = project_rows("management", ADMISSION,
                                   ["name", "student_applicant", "program", "status",
                                    "version", "accepted", "native_student", "modified"],
                                   filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                                   order_by="modified asc", limit=BOUNCE_WINDOW)
    attempts_running = project_count("management", ATTEMPT, {
        "status": ("in", [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])})
    released = project_count("management", DECISION, {"status": "Released"})
    students = project_count("management", STUDENT, {"enabled": 1})
    groups = project_rows("management", GROUP,
                          ["name", "student_group_name", "program", "academic_year",
                           "max_strength", "course", "disabled", "th_class_status"],
                          filters={"disabled": 0}, order_by="student_group_name asc",
                          limit=LIMIT_QUEUES)

    business_facts = [
        {"label": "Active students",
         "definition": "Active learner records in the student register.",
         "value": students, "owner": "Admission Approver"},
        {"label": "Admissions in flight",
         "definition": "Open admission decisions (Draft, Review, Approved, Conditional).",
         "value": len(admissions_open), "owner": "Admission Approver"},
        {"label": "Placement sessions running",
         "definition": "Attempts from Allocated through Review.",
         "value": attempts_running, "owner": "Placement Invigilator"},
        {"label": "Released placement results",
         "definition": "Decisions in Released status.",
         "value": released, "owner": "Placement Releaser"},
        {"label": "Classes running",
         "definition": "Classes whose lifecycle is Active; a class counts from activation to completion.",
         "value": len(active_cohort_rows(groups)), "owner": "Teaching Scheduler"},
    ]

    oldest = admissions_open[0] if admissions_open else None
    attention_items = []
    if oldest:
        attention_items.append({
            "id": oldest["name"],
            "person": oldest.get("student_applicant") or "",
            "detail": oldest.get("program") or "",
            "status": oldest["status"],
            "stage": "Oldest open admission",
            "stage_definition": "The open admission decision waiting longest for its next action.",
            "next": lifecycle.admission_stage(oldest["status"], bool(oldest.get("accepted")),
                                              bool(oldest.get("native_student")))["next"],
            "next_role": lifecycle.admission_stage(oldest["status"], bool(oldest.get("accepted")),
                                                   bool(oldest.get("native_student")))["role"],
            "waiting_since": oldest.get("modified"),
            "age": _age_label(oldest.get("modified")),
        })

    held = viewer_roles()
    desks_for_viewer = []
    for slug, spec in DESKS.items():
        if slug == SLUG:
            continue
        if set(spec["roles"]) & held:
            desks_for_viewer.append({"slug": slug, "title": spec["title"]})

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("business", "Business state", "facts", facts=business_facts,
                    empty_title="No business records yet",
                    empty_body="Counts appear as soon as the placement, admission and enrollment workflows create their first records."),
            section("attention", "Attention", "queue", items=attention_items,
                    empty_title="Nothing needs owner attention",
                    empty_body="No open admission is waiting and no exception is recorded."),
            section("posture", "Release posture (fail-closed facts)", "facts",
                    facts=RELEASE_POSTURE,
                    empty_title="Release posture is always stated",
                    empty_body="These facts come from the reviewed acceptance ledger, not from a live computation."),
            section("staffing", "Role coverage", "queue", items=_role_items(_staff_counts()),
                    empty_title="No operational roles",
                    empty_body="No shipped operational role is assigned to an enabled user."),
            section("desks", "Your desks", "links", items=desks_for_viewer,
                    empty_title="No other desks for your account",
                    empty_body="This account holds only the Owner Cockpit."),
        ],
    }
