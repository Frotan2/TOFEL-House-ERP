"""Owner cockpit: executive analytics grounded in native records.

Every figure carries its explicit definition, permission scope, source records
and drill-down path — a number without its provenance is not evidence.
The cockpit adds the fail-closed release posture (the same reviewed static
facts the administration control centre serves) to the operational projection.
The Owner role is Course Owner, the system owner of record. No business
metric without an owner-approved definition is invented here; every tile
carries its definition inline. Sections are specified in docs/ROLE-DESKS.md.

Executive analytics (Mission 6): active enrollments, admissions, attendance,
tuition collection, overdue fees, payroll where authorized, book stock,
retention, waiting lists, and operational exceptions — each with branch/course/
program/level/instructor/period breakdowns where the underlying data permits.
"""

import frappe
from frappe.utils import today

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
# analytics helper is optional in stub test env — guarded import
try:
    from toefl_house.desk import analytics
except Exception:  # pragma: no cover
    analytics = None

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

RELEASE_POSTURE = [
    {"label": "Site operational mode",
     "definition": "SYNTHETIC, PRODUCTION or REFUSED as resolved by the site's own security guard. Operational mode is not release authorization.",
     "value": None, "owner": None},
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
    try:
        from toefl_house import security
        return security.site_mode()
    except Exception:
        return "REFUSED"


def _executive_analytics_sections():
    """Executive analytics: grounded, bounded, auditable."""
    if analytics is None:
        return []
    sections = []
    try:
        enroll = analytics.enrollment_metrics()
        admiss = analytics.admission_metrics()
        tuit = analytics.tuition_metrics()
        attend = analytics.attendance_metrics()
    except Exception:
        unavailable = section(
            "executive-unavailable", "Executive metrics unavailable", "facts",
            facts=[{
                "label": "Verified executive totals", "value": "—",
                "definition": (
                    "One or more required sources cannot be fully verified. "
                    "No partial count, sum or percentage is published."),
                "source": "source verification incomplete",
                "scope": "unavailable", "drill_path": "source records list",
                "owner": "Course Owner",
            }],
            empty_title="Executive metrics unavailable",
            empty_body="Check the source records; a partial read is not zero.")
        return [unavailable]

    # A missing/denied/incomplete exit source must never become exited=0.
    # Preserve the raw overview even when retention data is unavailable.
    try:
        reten = analytics.retention_metrics()
    except Exception:
        reten = {
            "retention_rate": "—", "exited": "—",
            "status": "unavailable", "by_type": {},
            "definition": "Retention is unavailable (D7 approval pending; source could not be verified).",
            "source": "unavailable — enrollment exits could not be verified",
            "scope": "unavailable", "drill": "enrollment exits list",
        }

    hero_metrics = [
        {"label": "Active enrollments", "value": enroll["total"],
         "definition": enroll["definition"]},
        {"label": "Open admissions", "value": admiss["open"],
         "definition": "Admission decisions awaiting review, decision, acceptance or conversion."},
        {"label": "Attendance rate (D7 deferred)", "value": attend["rate"],
         "definition": attend["definition"]},
        {"label": "Outstanding fees", "value": tuit["fees_outstanding"],
         "definition": "Submitted tuition fees still owing."},
        {"label": "Overdue invoices", "value": tuit["invoices_overdue"] + tuit["fees_overdue"],
         "definition": "Submitted fees and invoices overdue: outstanding with due date before today."},
    ]
    hero_section = section("executive-hero", "Executive overview", "analytics",
                           empty_title="Executive overview", empty_body="No business records yet.")
    hero_section["hero"] = {
        "title": "Executive overview — as of today",
        "updated": f"Updated {today()}",
        "metrics": hero_metrics,
    }
    hero_section["groups"] = []
    sections.append(hero_section)

    enroll_facts = [
        {"label": "Active enrollments", "value": enroll["total"],
         "definition": enroll["definition"],
         "source": enroll["source"], "scope": enroll["scope"],
         "drill_path": enroll["drill"], "owner": "Enrollment Officer"},
        {"label": "Retention (D7 deferred)", "value": reten["retention_rate"],
         "definition": reten["definition"],
         "source": reten["source"], "scope": reten["scope"],
         "drill_path": reten["drill"], "owner": "Course Owner"},
        {"label": "Exited (withdrawn or dismissed)", "value": reten["exited"],
         "definition": "Enrollment exits — only where the governing exit policy cites a resolved supersession.",
         "source": reten["source"], "scope": reten["scope"],
         "drill_path": reten["drill"], "owner": "Course Owner"},
    ]
    enroll_section = section("enrollments", "Enrollments & retention", "facts", facts=enroll_facts,
                             empty_title="No enrollments yet", empty_body="Enrollments appear after admission conversion.")
    if enroll["by_program"]:
        enroll_section["comparison"] = {
            "title": "Active enrollments by program",
            "columns": ["Program", "Enrollments"],
            "rows": [{"label": k, "value": v, "drill": {"slug": "List/Program Enrollment"}} for k, v in sorted(enroll["by_program"].items())],
        }
    enroll_section["provenance"] = [
        {"label": "Source records", "value": enroll["source"]},
        {"label": "Permission scope", "value": enroll["scope"]},
        {"label": "Drill-down", "value": "List — enrollment records filtered by program, academic year, branch"},
    ]
    sections.append(enroll_section)

    # D7 permits raw reports, not inferred counts of "waiting for a class".
    # A zero would be especially misleading if a projection fails or is cut
    # off at LIMIT_QUEUES. Until the Owner approves a derived definition,
    # show an explicit unavailable state even when inputs appear complete.
    waiting = {
        "total": "—", "by_program": {},
        "definition": (
            "Not available: Owner decision D7 defers derived waiting-for-class "
            "metrics until a named steward, coverage rule and denominator "
            "are approved."),
        "source": "not published — derived metric on hold",
        "scope": "D7 deferred", "drill": "enrollment list",
    }
    try:
        groups_for_waiting = project_rows(
            "management", GROUP,
            ["name", "student_group_name", "program", "academic_year",
             "max_strength", "course", "disabled", "th_class_status"],
            filters={"disabled": 0}, order_by="student_group_name asc",
            limit=LIMIT_QUEUES)
        # The raw active-class count may be displayed only after proving
        # the bounded query covers all accessible class rows.
        group_total = project_count("management", GROUP, filters={"disabled": 0})
        if (not isinstance(group_total, int) or isinstance(group_total, bool)
                or group_total != len(groups_for_waiting)):
            raise RuntimeError("Class projection incomplete")
        classes_running = len(active_cohort_rows(groups_for_waiting))
    except Exception:
        groups_for_waiting = []
        classes_running = "—"

    # Native U5: describe record provenance to staff, not internal DocType names.
    waiting_facts = [
        {"label": "Waiting for a class (D7 deferred)", "value": waiting["total"],
         "definition": waiting["definition"],
         "source": waiting["source"], "scope": waiting["scope"],
         "drill_path": waiting["drill"], "owner": "Course Owner"},
        {"label": "Classes running (Active)", "value": classes_running,
         "definition": "Accessible active class count; unavailable if source is incomplete or denied.",
         "source": "class records (bounded, counted)", "scope": "Branch via class branch",
         "drill_path": "class list", "owner": "Teaching Scheduler"},
    ]
    waiting_section = section(
        "waiting", "Waiting list & cohort capacity", "facts",
        facts=waiting_facts,
        empty_title="Waiting metric deferred",
        empty_body="An unapproved or incomplete source is not evidence that no students are waiting.")
    waiting_section["provenance"] = [
        {"label": "Source records", "value": waiting["source"]},
        {"label": "Permission scope", "value": waiting["scope"]},
        {"label": "Drill-down", "value": "enrollment list and class list"},
    ]
    sections.append(waiting_section)

    admiss_facts = [
        {"label": "Open admissions", "value": admiss["open"],
         "definition": admiss["definition"],
         "source": admiss["source"], "scope": admiss["scope"],
         "drill_path": admiss["drill"], "owner": "Admission Approver"},
        {"label": "Closed admissions", "value": admiss["closed"],
         "definition": "Deferred, Rejected, Withdrawn, Revoked, Expired decisions (closed files).",
         "source": admiss["source"], "scope": admiss["scope"],
         "drill_path": admiss["drill"], "owner": "Admission Approver"},
    ]
    admiss_section = section("admissions", "Admissions funnel", "facts", facts=admiss_facts,
                             empty_title="No admissions yet", empty_body="Admissions appear when placement results are released.")
    if admiss["by_status"]:
        admiss_section["comparison"] = {
            "title": "Open admissions by status",
            "columns": ["Status", "Count"],
            "rows": [{"label": k, "value": v} for k, v in sorted(admiss["by_status"].items())],
        }
    admiss_section["provenance"] = [
        {"label": "Source records", "value": admiss["source"]},
        {"label": "Permission scope", "value": admiss["scope"]},
        {"label": "Drill-down", "value": "admission decision list filtered by status"},
    ]
    sections.append(admiss_section)

    attend_facts = [
        {"label": "Attendance records", "value": attend["total"],
         "definition": attend["definition"],
         "source": attend["source"], "scope": attend["scope"],
         "drill_path": attend["drill"], "owner": "Attendance Recorder"},
        {"label": "Present", "value": attend["present"],
         "definition": "Submitted attendance with present mark.",
         "source": attend["source"], "scope": attend["scope"],
         "drill_path": attend["drill"], "owner": "Attendance Recorder"},
        {"label": "Absent", "value": attend["absent"],
         "definition": "Submitted attendance with absent mark.",
         "source": attend["source"], "scope": attend["scope"],
         "drill_path": attend["drill"], "owner": "Attendance Recorder"},
        {"label": "Attendance rate (D7 deferred)", "value": attend["rate"],
         "definition": "Present / (Present + Absent) — submitted marks only; no threshold invented.",
         "source": attend["source"], "scope": attend["scope"],
         "drill_path": attend["drill"], "owner": "Attendance Recorder"},
    ]
    attend_section = section("attendance", "Attendance", "facts", facts=attend_facts,
                             empty_title="No attendance recorded", empty_body="Attendance appears when sessions are scheduled and marks recorded.")
    try:
        inst = analytics.attendance_by_instructor()
        if inst["by_instructor"]:
            attend_section["comparison"] = {
                "title": "Sessions by instructor",
                "columns": ["Instructor", "Sessions scheduled"],
                "rows": [{"label": k, "value": v, "drill": {"slug": "List/Course Schedule"}} for k, v in sorted(inst["by_instructor"].items(), key=lambda x: -x[1])[:10]],
            }
    except Exception:
        pass
    attend_section["provenance"] = [
        {"label": "Source records", "value": attend["source"]},
        {"label": "Permission scope", "value": attend["scope"]},
        {"label": "Drill-down", "value": "attendance list filtered by course, group, date"},
    ]
    sections.append(attend_section)

    tuit_facts = [
        {"label": "Tuition posted", "value": tuit["fees_total"],
         "definition": "Submitted tuition fees — billing record for one enrollment's program/year.",
         "source": "tuition fees (submitted)", "scope": tuit["scope"],
         "drill_path": tuit["drill"], "owner": "Finance Officer"},
        {"label": "Collectable (outstanding)", "value": tuit["fees_outstanding"],
         "definition": "Submitted fees still owing.",
         "source": "fees outstanding", "scope": tuit["scope"],
         "drill_path": tuit["drill"], "owner": "Finance Officer"},
        {"label": "Overdue tuition", "value": tuit["fees_overdue"],
         "definition": "Outstanding fees with due date before today.",
         "source": "fees overdue", "scope": tuit["scope"],
         "drill_path": tuit["drill"], "owner": "Finance Officer"},
        {"label": "Collected today", "value": tuit["collected_today"],
         "definition": "Submitted payments received today, summed per paying-account currency.",
         "source": "payments received today", "scope": tuit["scope"],
         "drill_path": "payment list", "owner": "Finance Officer"},
        {"label": "Charged (per currency)", "value": tuit["by_currency_charged"],
         "definition": "Sum of charged amounts for all submitted fees, per currency.",
         "source": "tuition fees charged", "scope": tuit["scope"],
         "drill_path": tuit["drill"], "owner": "Finance Officer"},
        {"label": "Outstanding (per currency)", "value": tuit["by_currency_outstanding"],
         "definition": "Sum of outstanding amounts for outstanding fees, per currency.",
         "source": "fees outstanding amounts", "scope": tuit["scope"],
         "drill_path": tuit["drill"], "owner": "Finance Officer"},
    ]
    tuit_section = section("tuition", "Tuition collection & overdue", "facts", facts=tuit_facts,
                           empty_title="No tuition records", empty_body="Tuition fees appear when enrollments are billed.")
    if tuit["by_program"]:
        tuit_section["chart"] = {
            "title": "Fees distribution by program",
            "rows": [{"label": k, "value": v, "tone": "info"} for k, v in sorted(tuit["by_program"].items(), key=lambda x: -x[1])[:8]],
        }
    tuit_section["provenance"] = [
        {"label": "Source records", "value": tuit["source"]},
        {"label": "Permission scope", "value": tuit["scope"]},
        {"label": "Drill-down", "value": "tuition fees list and payment list"},
    ]
    sections.append(tuit_section)

    book = analytics.book_stock_metrics()
    book_facts = [
        {"label": "Book items", "value": book["items"],
         "definition": book["definition"],
         "source": book["source"], "scope": book["scope"],
         "drill_path": book["drill"], "owner": None},
        {"label": "Book inventory bins", "value": book["bins"],
         "definition": "Accessible native warehouse bins for Item Group Books (including zero balance).",
         "source": "warehouse bins (native)", "scope": book["scope"],
         "drill_path": book["drill"], "owner": None},
        {"label": "Units on hand", "value": book["total_qty"],
         "definition": "Units in accessible Item Group Books inventory bins; unavailable if the read is incomplete.",
         "source": "warehouse bins quantity", "scope": book["scope"],
         "drill_path": book["drill"], "owner": None},
        {"label": "Low-stock items", "value": book["low_stock"],
         "definition": "Not configured: Course Owner must approve a replenishment threshold before any low-stock indicator is published.",
         "source": "bins low stock", "scope": book["scope"],
         "drill_path": book["drill"], "owner": None},
    ]
    book_section = section("books", "Book stock (native inventory)", "facts", facts=book_facts,
                           empty_title="No book inventory", empty_body="Configure book items and receive stock.")
    sections.append(book_section)

    roles = frappe.get_roles(frappe.session.user) if hasattr(frappe, "get_roles") else []
    payroll_authorized = bool(set(roles) & {"Finance Manager", "General Manager", "Course Owner"})
    pay = analytics.payroll_metrics(authorized=payroll_authorized)
    pay_facts = [
        {"label": "Payroll inputs (additional salary)", "value": pay.get("total", "—"),
         "definition": pay["definition"],
         "source": pay["source"], "scope": pay["scope"],
         "drill_path": pay["drill"], "owner": "Finance Officer" if pay.get("authorized") else None},
    ]
    if pay.get("authorized"):
        pay_facts.append({"label": "Payroll slips posted", "value": pay.get("slips", 0),
                          "definition": "Submitted salary slips — posted payroll outputs.",
                          "source": "salary slips (submitted)", "scope": pay["scope"],
                          "drill_path": "salary slip list", "owner": "Finance Officer"})
    pay_section = section("payroll", "Payroll totals (authorized only)", "facts", facts=pay_facts,
                          empty_title="No payroll data", empty_body=pay["definition"] if not pay.get("authorized") else "No payroll inputs yet.")
    sections.append(pay_section)

    try:
        exc = analytics.exception_metrics()
    except Exception:
        exc = {
            "corrections_pending": "—", "admissions_in_review": "—",
            "attempts_past_deadline": "—", "awaiting_release": "—",
            "scope": "unavailable; incomplete source", "source": "unavailable",
            "drill": "source records list",
        }
    exc_facts = [
        {"label": "Corrections pending", "value": exc["corrections_pending"],
         "definition": "Correction requests awaiting approver.",
         "source": "correction requests (requested)", "scope": "Management",
         "drill_path": "correction request list", "owner": "Finance Officer"},
        {"label": "Admissions in review", "value": exc["admissions_in_review"],
         "definition": "Admissions waiting for approver outcome — oldest first.",
         "source": "admission decisions in review", "scope": exc["scope"],
         "drill_path": "admission decision list", "owner": "Admission Approver"},
        {"label": "Placement past deadline", "value": exc["attempts_past_deadline"],
         "definition": "Placement attempts past their server-set deadline.",
         "source": "placement attempts past deadline", "scope": exc["scope"],
         "drill_path": "placement attempt list", "owner": "Placement Invigilator"},
        {"label": "Awaiting release", "value": exc["awaiting_release"],
         "definition": "Finalized placement attempts with no released decision.",
         "source": "finalized attempts without released decision", "scope": exc["scope"],
         "drill_path": "placement decision list", "owner": "Placement Releaser"},
    ]
    exc_section = section("ops-exceptions", "Operational exceptions", "facts", facts=exc_facts,
                          empty_title="No exceptions", empty_body="No items in this preview; verify all underlying sources before concluding none are pending.")
    exc_section["provenance"] = [
        {"label": "Source records", "value": exc["source"]},
        {"label": "Permission scope", "value": exc["scope"]},
        {"label": "Drill-down", "value": exc["drill"]},
    ]
    sections.append(exc_section)
    return sections


@frappe.whitelist(methods=["GET", "POST"])
def cockpit():
    require_desk_audience(SLUG)

    admissions_open = project_rows("management", ADMISSION,
                                   ["name", "student_applicant", "program", "status",
                                    "version", "accepted", "native_student", "modified"],
                                   filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                                   order_by="modified asc", limit=BOUNCE_WINDOW)
    def safe_count(doctype, filters):
        """A denied or invalid native count is unavailable, never zero."""
        try:
            value = project_count("management", doctype, filters)
            if (not isinstance(value, int) or isinstance(value, bool)
                    or value < 0):
                raise RuntimeError("Incomplete native management count")
            return value
        except Exception:
            return "—"

    attempts_running = safe_count(ATTEMPT, {
        "status": ("in", [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])})
    released = safe_count(DECISION, {"status": "Released"})
    students = safe_count(STUDENT, {"enabled": 1})
    # These are full scoped counts, not lengths of queue-sized previews.
    # If a permission or source fails, do not fabricate a zero.
    try:
        admissions_count = project_count(
            "management", ADMISSION,
            {"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))})
        if (not isinstance(admissions_count, int)
                or isinstance(admissions_count, bool)
                or admissions_count < len(admissions_open)):
            raise RuntimeError("Admissions source count incomplete")
    except Exception:
        admissions_count = "—"
    try:
        classes_running = project_count(
            "management", GROUP,
            {"disabled": 0, "th_class_status": "Active"})
        if (not isinstance(classes_running, int)
                or isinstance(classes_running, bool)
                or classes_running < 0):
            raise RuntimeError("Class source count incomplete")
    except Exception:
        classes_running = "—"

    business_facts = [
        {"label": "Active students",
         "definition": "Active learner records in the student register.",
         "value": students, "owner": "Admission Approver",
         "source": "active learners (native register)", "scope": "Branch via roster or HQ unrestricted",
         "drill_path": "student list"},
        {"label": "Admissions in flight",
         "definition": "Scoped total open admission decisions, counted independently of the oldest-record preview.",
         "value": admissions_count, "owner": "Admission Approver",
         "source": "admission decisions (open)", "scope": "Branch via applicant linkage",
         "drill_path": "admission decision list"},
        {"label": "Placement sessions running",
         "definition": "Attempts from Allocated through Review — not yet finalized.",
         "value": attempts_running, "owner": "Placement Invigilator",
         "source": "placement attempts (non-finalized)", "scope": "Branch-wide",
         "drill_path": "placement attempt list"},
        {"label": "Released placement results",
         "definition": "Decisions in Released status — intake-ready outcomes.",
         "value": released, "owner": "Placement Releaser",
         "source": "placement decisions (released)", "scope": "Branch-wide",
         "drill_path": "placement decision list"},
        {"label": "Classes running",
         "definition": "Full scoped count of non-archived classes whose lifecycle is Active.",
         "value": classes_running, "owner": "Teaching Scheduler",
         "source": "active classes", "scope": "Branch via class branch",
         "drill_path": "class list"},
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

    analytics_sections = _executive_analytics_sections()

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            *analytics_sections,
            section("business", "Business state", "facts", facts=business_facts,
                    empty_title="No business records yet",
                    empty_body="Counts appear as soon as the placement, admission and enrollment workflows create their first records."),
            section("funnel", "Operation funnel", "facts", facts=funnel_facts,
                    empty_title="No operational preview items",
                    empty_body="Verify complete pipeline sources before concluding no work is in progress."),
            section("exceptions", "Exceptions and oldest waiting work", "queue",
                    items=exception_items,
                    empty_title="No exceptions",
                    empty_body="Nothing is overdue, stuck or waiting on an approver right now."),
            section("attention", "Attention — oldest waiting", "queue", items=attention_items,
                    empty_title="No items in attention preview",
                    empty_body="A blank preview does not prove all admissions or exception sources are complete."),
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
