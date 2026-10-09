"""Owner cockpit: business state with every definition stated.

Adds the fail-closed release posture (the same reviewed static facts the
administration control centre serves) to the operational projection. The
Owner role is Course Owner, the system owner of record. No business metric
without an owner-approved definition is invented here; every tile carries its
definition inline. Sections are specified in docs/ROLE-DESKS.md.
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
from toefl_house.desk.operations import (
    _staff_counts, _role_items, _age_label, _recorded_action_items,
    _funnel_and_exceptions, _system_health,
)

SLUG = "th-owner-cockpit"

ATTEMPT = "TH Placement Attempt"
ADMISSION = "TH Admission Decision"
DECISION = "TH Placement Decision"
STUDENT = "Student"
GROUP = "Student Group"

# Release posture lines. All are the same records the administration control
# centre serves, so the cockpit and the control centre cannot disagree.
#
# Site operational mode and release authorization are separate facts. The
# former is dynamically resolved by the same security.site_mode guard used by
# the lifecycle; the latter stays REJECT until the acceptance ledger's real
# evidence and the Owner/non-engineering release gates pass. PRODUCTION mode
# must never be presented as production authorization.
#
# The dependency-security line states what SEC-DEPS-01 is today: known
# upstream advisories on the pinned stack. It gates internet exposure; the
# selected deployment (owner decision D13/D15) is loopback-only with
# private-Tailscale access and does not open internet exposure.
#
# Deployment value is the owner's selected current deployment per
# docs/owner-decisions.json; the line carries the as-of date so a future
# ledger change cannot silently stale the cockpit.
RELEASE_POSTURE = [
    {"label": "Site operational mode",
     "definition": "SYNTHETIC, PRODUCTION or REFUSED as resolved by the site's own security guard. Operational mode is not release authorization.",
     "value": None, "owner": None},  # value filled by _site_mode()
    {"label": "Production authorization",
     "definition": "Separate release decision. It stays REJECT until all evidence gates in docs/engineering/ACCEPTANCE.md and Owner/non-engineering gates pass; a PRODUCTION site mode cannot change it.",
     "value": "REJECT", "owner": "Course Owner"},
    {"label": "Dependency security (SEC-DEPS-01)",
     "definition": "The pinned stack carries known upstream advisories. The gate binds to internet exposure; the selected deployment (D13/D15) is loopback-only with private-Tailscale access and opens none.",
     "value": "OPEN (gates internet exposure)", "owner": None},
    {"label": "Synthetic and operational guards",
     "definition": "Site-mode guards, synthetic-record restrictions and production-only validation remain enforced. Changing site mode does not authorize release.",
     "value": "ENFORCED", "owner": None},
    {"label": "Deployment",
     "definition": "Current deployment decision recorded by the owner in docs/owner-decisions.json (as of 2026-09-16).",
     "value": "LOCAL_SERVER_TAILSCALE (as of 2026-09-16 per docs/owner-decisions.json)", "owner": None},
]


def _site_mode():
    """The site's operational mode; REFUSED when settings are unreadable."""
    try:
        from toefl_house import security
        return security.site_mode()
    except Exception:
        return "REFUSED"


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

    funnel_facts, exception_items = _funnel_and_exceptions()
    health_facts, _ = _system_health()

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
            section("funnel", "Operation funnel", "facts", facts=funnel_facts,
                    empty_title="No operational records yet",
                    empty_body="Nothing is running in the placement, admission, enrollment or finance pipeline."),
            section("exceptions", "Exceptions and oldest waiting work", "queue",
                    items=exception_items,
                    empty_title="No exceptions",
                    empty_body="Nothing is overdue, stuck or waiting on an approver right now."),
            section("attention", "Attention", "queue", items=attention_items,
                    empty_title="Nothing needs owner attention",
                    empty_body="No open admission is waiting and no exception is recorded."),
            section("activity", "Recent recorded actions", "queue",
                    items=_recorded_action_items(),
                    empty_title="No recorded actions yet",
                    empty_body="When staff complete an important action, the record appears here. The full trail stays with auditor roles."),
            section("posture", "Release posture (fail-closed facts)", "facts",
                    facts=[dict(row, value=_site_mode() if row["value"] is None else row["value"])
                           for row in RELEASE_POSTURE],
                    empty_title="Release posture is always stated",
                    empty_body="These facts come from the reviewed acceptance ledger, not from a live computation."),
            section("health", "System health counts", "facts", facts=health_facts,
                    empty_title="No health facts yet",
                    empty_body="Health counts appear once the native scheduler tables exist. Failed-job detail lives on the General Manager desk; tracebacks stay on the native forms."),
            section("staffing", "Role coverage", "queue", items=_role_items(_staff_counts()),
                    empty_title="No operational roles",
                    empty_body="No shipped operational role is assigned to an enabled user."),
            section("desks", "Your desks", "links", items=desks_for_viewer,
                    empty_title="No other desks for your account",
                    empty_body="This account holds only the Owner Cockpit."),
        ],
    }
