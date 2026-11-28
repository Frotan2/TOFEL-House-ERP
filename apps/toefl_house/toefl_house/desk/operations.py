"""General Manager desk: cross-role operations, exceptions, staffing.

Read-only, fact-based, branch-wide. This is deliberately NOT a second Owner
cockpit: no release posture, no governance claims — operational queues and
exception facts only. Sections are specified in docs/ROLE-DESKS.md.
"""
import frappe
from frappe.utils import now_datetime

from toefl_house.desk import (
    ACADEMIC_REPORTS,
    BOUNCE_WINDOW,
    DESKS,
    FINANCE_REPORTS,
    LIMIT_QUEUES,
    _assert_projection,
    guided_action,
    project_count,
    project_rows,
    report_section,
    require_desk_audience,
    scope_filters,
    section,
    viewer_roles,
)
from toefl_house.desk import lifecycle
from toefl_house.desk.tuition_refunds import refund_sections
try:
    from toefl_house.desk import analytics
except Exception:
    analytics = None
from toefl_house import observability as obs

SLUG = "th-operations-desk"

ATTEMPT = "TH Placement Attempt"
DECISION = "TH Placement Decision"
ADMISSION = "TH Admission Decision"
CORRECTION = "TH Correction Request"
ENROLLMENT = "Program Enrollment"
GROUP = "Student Group"
SCHEDULE = "Course Schedule"
AUDIT = "TH Placement Audit Event"
AUDIT_FIELDS = ["name", "actor", "action", "target", "item_revision", "creation"]

# Ops-visible subset of the existing command receipts. Session saves and
# draft authoring stay on the auditor workspace; this is not a second log.
ACTION_LABELS = {
    "create_case": "Opened a placement case",
    "allocate_attempt": "Allocated a placement session",
    "verify_attempt": "Verified a placement session",
    "deliver_attempt": "Started a placement session",
    "seal_attempt": "Sealed a placement session",
    "score_attempt": "Scored a placement session",
    "review_attempt": "Reviewed a placement session",
    "finalize_attempt": "Finalized a placement session",
    "release_decision": "Released a placement result",
    "publish": "Published a placement item",
    "publish_blueprint": "Published a placement blueprint",
    "publish_policy": "Published a placement policy",
    "publish_course_map": "Published a course map",
    "retire_blueprint": "Retired a placement blueprint",
    "retire_policy": "Retired a placement policy",
    "retire_course_map": "Retired a course map",
    "record_applicant": "Recorded an applicant",
    "create_admission": "Opened an admission",
    "review_admission": "Sent an admission for review",
    "decide_admission": "Recorded an admission outcome",
    "accept_offer": "Accepted an admission offer",
    "withdraw_admission": "Withdrew an admission",
    "revoke_admission": "Revoked an admission",
    "expire_admission": "Expired an admission",
    "convert_applicant": "Created a student from an applicant",
    "enroll_in_program": "Enrolled a student",
    "create_student_group": "Created a class",
    "transition_class": "Changed a class lifecycle",
    "schedule_session": "Scheduled a session",
    "record_attendance": "Recorded attendance",
    "issue_tuition_fees": "Issued tuition",
    "issue_placement_fee": "Issued a placement fee",
    "create_teaching_contract": "Recorded a teaching contract",
    "revise_teaching_contract": "Revised a teaching contract",
    "assign_teaching_skill": "Assigned a teaching skill",
    "end_teaching_assignment": "Ended a teaching assignment",
    "configure_correction_policy": "Configured a correction policy",
    "set_correction_policy_status": "Changed the correction policy status",
    "validate_correction_policy": "Validated the correction policy",
    "request_invoice_correction": "Requested an invoice correction",
    "approve_invoice_correction": "Approved an invoice correction",
    "deny_invoice_correction": "Denied an invoice correction",
    "request_fees_correction": "Requested a tuition correction",
    "approve_fees_correction": "Approved a tuition correction",
    "deny_fees_correction": "Denied a tuition correction",
}

STAFF_ROLES = (
    "Reception", "Admission Officer", "Admission Reviewer", "Admission Approver",
    "Enrollment Officer", "Teaching Scheduler", "Attendance Recorder",
    "Finance Officer", "Academic Manager", "Finance Manager", "General Manager",
    "Instructor",
)


def _staff_counts():
    """Enabled users per shipped operational role, from the native Has Role."""
    counts = {}
    for role in STAFF_ROLES:
        holders = {row["parent"]
                   for row in project_rows("management", "Has Role",
                                           ["name", "parent", "role", "parenttype"],
                                           filters={"role": role, "parenttype": "User"},
                                           order_by="parent asc", limit=BOUNCE_WINDOW)
                   if row.get("parent") not in (None, "Administrator", "Guest", "")}
        enabled = 0
        if holders:
            rows = project_rows("management", "User", ["name"],
                                filters={"name": ("in", sorted(holders)), "enabled": 1},
                                order_by="name asc", limit=BOUNCE_WINDOW)
            enabled = len(rows)
        counts[role] = enabled
    return counts


def _progression_items():
    """Published results without a progression decision.

    The Academic Manager records the normal decision on the course assessment
    page. When the configured evidence is not met but the institute still
    promotes or completes a learner, only the General Manager may record a
    reasoned override; the evidence itself is never edited.
    """
    results = project_rows("management", "TH Academic Result",
                           ["name", "student", "student_group", "outcome",
                            "overall_percent", "passed", "status", "published_on"],
                           filters={"status": "Published"},
                           order_by="published_on asc", limit=LIMIT_QUEUES)
    if not results:
        return []
    decided = {row.get("academic_result") for row in project_rows(
        "management", "TH Progression Decision", ["name", "academic_result"],
        filters={"academic_result": ("in", [row["name"] for row in results])},
        order_by="name asc", limit=LIMIT_QUEUES)}
    items = []
    for row in results:
        if row["name"] in decided:
            continue
        items.append({
            "id": row["name"], "person": row.get("student") or "",
            "detail": "{0} \u00b7 {1} \u00b7 {2}%".format(
                row.get("student_group") or "", row.get("outcome") or "",
                row.get("overall_percent") or 0),
            "status": "Awaiting decision", "stage": "Progression",
            "stage_definition": "A published result with no Promote, Repeat, Retake or Complete decision.",
            "next": ("The Academic Manager decides on the course assessment page. Use an override "
                     "only when the evidence is not met and the institute still promotes or "
                     "completes this learner; the unmet evidence stays on record."),
            "next_role": "Academic Manager", "waiting_since": row.get("published_on"),
            "action": guided_action("General Manager",
                                    "toefl_house.academic.progression.override_progression",
                                    "Record override",
                                    {"academic_result": row["name"], "decision": "Promote",
                                     "reason": ""}),
        })
    return items


def _role_items(counts):
    return [{
        "id": role,
        "person": f"{count} enabled user" + ("" if count == 1 else "s"),
        "detail": "",
        "status": "Unstaffed" if count == 0 else "Staffed",
        "stage": "Role coverage",
        "stage_definition": f"Enabled staff accounts holding the {role} role.",
        "next": "Assign a user to this role from the Administration Control Centre." if count == 0
        else "No action.",
        "next_role": "Course Owner" if count == 0 else None,
        "waiting_since": None,
    } for role, count in counts.items()]


def _teacher_link_items():
    """Instructor logins the Teacher desk cannot resolve, before they log in.

    Mirrors desk.teacher._resolve_instructor: an enabled login holding the
    Instructor role needs exactly one Active Employee whose User ID is that
    login, and exactly one non-Left Instructor on that Employee. Anything
    else leaves the teacher with an empty desk and no attendance access.

    Only an unscoped (HQ) viewer gets these rows: a Company/Branch-scoped
    viewer cannot see other branches' Employees, so every teacher there
    would be falsely reported as unlinked.
    """
    if scope_filters("management"):
        return []
    holders = sorted({row["parent"]
                      for row in project_rows("management", "Has Role",
                                              ["name", "parent", "role", "parenttype"],
                                              filters={"role": "Instructor", "parenttype": "User"},
                                              order_by="parent asc", limit=BOUNCE_WINDOW)
                      if row.get("parent") not in (None, "Administrator", "Guest", "")})
    if not holders:
        return []
    enabled = [row["name"] for row in project_rows(
        "management", "User", ["name"], filters={"name": ("in", holders), "enabled": 1},
        order_by="name asc", limit=BOUNCE_WINDOW)]
    if not enabled:
        return []
    employees = {}
    for row in project_rows("management", "Employee", ["name", "employee_name", "status", "user_id"],
                            filters={"user_id": ("in", enabled), "status": "Active"},
                            order_by="name asc", limit=BOUNCE_WINDOW):
        employees.setdefault(row.get("user_id"), []).append(row)
    single = sorted(rows[0]["name"] for rows in employees.values() if len(rows) == 1)
    instructors = {}
    if single:
        for row in project_rows("management", "Instructor", ["name", "instructor_name", "employee", "status"],
                                filters={"employee": ("in", single)}, order_by="name asc",
                                limit=BOUNCE_WINDOW):
            if row.get("status") != "Left":
                instructors.setdefault(row.get("employee"), []).append(row)
    items = []
    for user in enabled:
        rows = employees.get(user, [])
        if not rows:
            problem = "No active Employee record has this login as its User ID."
        elif len(rows) > 1:
            problem = "More than one active Employee record uses this login."
        else:
            employee = rows[0]["name"]
            linked = len(instructors.get(employee, []))
            if linked == 1:
                continue
            problem = (f"Employee {employee} has no active Instructor record." if not linked
                       else f"Employee {employee} has more than one active Instructor record.")
        items.append({
            "id": "teacher-link-" + user,
            "person": user,
            "detail": problem,
            "status": "Not linked",
            "stage": "Teacher login",
            "stage_definition": ("A teacher sees classes and records attendance only when the "
                                 "login, one active Employee and one active Instructor are linked."),
            "next": ("On the Employee record set User ID to this login, then select that "
                     "Employee on exactly one active Instructor record."),
            "next_role": "Course Owner",
            "waiting_since": None,
        })
    return items


def _age_label(value):
    if not value:
        return ""
    try:
        from frappe.utils import get_datetime
        delta = now_datetime() - get_datetime(value)
        days = delta.days
        if days <= 0:
            return "today"
        if days == 1:
            return "1 day"
        return f"{days} days"
    except Exception:
        return ""


def _recorded_action_items():
    """Recent completed commands, as facts. No hashes, no second trail."""
    rows = project_rows(
        "management", AUDIT, AUDIT_FIELDS,
        filters={"action": ("in", tuple(ACTION_LABELS))},
        order_by="creation desc", limit=LIMIT_QUEUES)
    items = []
    for row in rows:
        label = ACTION_LABELS.get(row.get("action"))
        if not label:
            continue
        target = row.get("target") or row.get("item_revision") or ""
        items.append({
            "id": row["name"],
            "person": row.get("actor") or "",
            "detail": target,
            "status": label,
            "stage": "Recorded action",
            "stage_definition": (
                "A completed staff action wrote this record. The full trail "
                "stays with auditor roles; this desk does not add a second log."),
            "next": "No action.",
            "next_role": None,
            "waiting_since": row.get("creation"),
            "age": _age_label(row.get("creation")),
        })
    return items



def _scoped_count_or_unknown(doctype, filters, *, preview=None):
    """Full native management-scope count, never an extrapolated preview."""
    try:
        # Keep every query anchored to a module-level native DocType
        # constant so schema-ledger and projection audit can resolve it.
        if doctype == ATTEMPT:
            total = project_count("management", ATTEMPT, filters=filters)
        elif doctype == DECISION:
            total = project_count("management", DECISION, filters=filters)
        elif doctype == ADMISSION:
            total = project_count("management", ADMISSION, filters=filters)
        elif doctype == GROUP:
            total = project_count("management", GROUP, filters=filters)
        elif doctype == CORRECTION:
            total = project_count("management", CORRECTION, filters=filters)
        else:
            raise ValueError("Unapproved management count source")
        if (not isinstance(total, int) or isinstance(total, bool) or total < 0
                or (preview is not None and total < len(preview))):
            return "—"
        return total
    except Exception:
        # A denied, missing or inconsistent source is not verified zero.
        return "—"


def _funnel_and_exceptions():
    """Shared operational facts for the GM desk and the Owner cockpit.

    ROLE-DESKS: the Owner cockpit shows everything the GM desk shows, plus
    posture. This helper is the GM queues; it does not grant GM commands.
    """
    admissions_open = project_rows("management", ADMISSION,
                                   ["name", "student_applicant", "program", "status",
                                    "version", "modified"],
                                   filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                                   order_by="modified asc", limit=BOUNCE_WINDOW)
    review_waiting = [row for row in admissions_open if row["status"] == "Review"]
    corrections = project_rows("management", CORRECTION,
                               ["name", "sales_invoice", "fees", "reason",
                                "requested_amount", "status", "modified"],
                               filters={"status": "Requested"},
                               order_by="modified asc", limit=LIMIT_QUEUES)
    running_statuses = [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER
                        if s != "Finalized"]
    attempts_running = project_rows("management", ATTEMPT,
                                    ["name", "case_name", "status", "deadline_at"],
                                    filters={"status": ("in", running_statuses)},
                                    order_by="modified asc", limit=BOUNCE_WINDOW)
    finalized = project_rows("management", ATTEMPT,
                             ["name", "case_name", "status", "deadline_at"],
                             filters={"status": "Finalized"},
                             order_by="modified asc", limit=BOUNCE_WINDOW)
    released = project_rows("management", DECISION,
                            ["name", "attempt", "status", "released_at", "expires_at"],
                            filters={"status": "Released"},
                            order_by="released_at desc", limit=BOUNCE_WINDOW)
    released_attempts = {row["attempt"] for row in released if row.get("attempt")}
    awaiting_release = [row for row in finalized if row["name"] not in released_attempts]

    # D7 forbids publishing an inferred waiting-for-class KPI.
    # Verify that bounded lists cover the full population before subtracting.
    running_count = _scoped_count_or_unknown(
        ATTEMPT, {"status": ("in", running_statuses)}, preview=attempts_running)
    finalized_count = _scoped_count_or_unknown(
        ATTEMPT, {"status": "Finalized"}, preview=finalized)
    released_count = _scoped_count_or_unknown(
        DECISION, {"status": "Released"}, preview=released)
    awaiting_release_count = (
        len(awaiting_release)
        if (isinstance(finalized_count, int) and not isinstance(finalized_count, bool)
            and isinstance(released_count, int) and not isinstance(released_count, bool)
            and finalized_count == len(finalized)
            and released_count == len(released))
        else "—")
    draft_count = _scoped_count_or_unknown(ADMISSION, {"status": "Draft"})
    review_count = _scoped_count_or_unknown(
        ADMISSION, {"status": "Review"}, preview=review_waiting)
    active_classes_count = _scoped_count_or_unknown(
        GROUP, {"disabled": 0, "th_class_status": "Active"})
    corrections_count = _scoped_count_or_unknown(
        CORRECTION, {"status": "Requested"}, preview=corrections)

    overdue_deadlines = []
    deadline_evidence_complete = (
        isinstance(running_count, int)
        and not isinstance(running_count, bool)
        and running_count == len(attempts_running)
    )
    if deadline_evidence_complete and any(row.get("deadline_at") for row in attempts_running):
        try:
            from frappe.utils import get_datetime
            now = now_datetime()
            if now is None:
                raise ValueError("Placement deadline clock unavailable")
            for row in attempts_running:
                if row.get("deadline_at"):
                    deadline = get_datetime(row["deadline_at"])
                    if deadline is None:
                        raise ValueError("Invalid placement deadline")
                    if deadline < now:
                        overdue_deadlines.append(row)
        except Exception:
            # Do not silently skip a broken deadline or claim zero overdue.
            deadline_evidence_complete = False

    funnel_facts = [
        {"label": "Placement sessions running",
         "definition": "Attempts from Allocated through Review.",
         "value": running_count, "owner": "Placement Invigilator"},
        {"label": "Placement deadlines overdue",
         "definition": (
             "Running attempts whose validated server deadline has passed. "
             "Unavailable if any running attempt or deadline cannot be checked."),
         "value": len(overdue_deadlines) if deadline_evidence_complete else "—",
         "owner": "Placement Invigilator"},
        {"label": "Results awaiting release",
         "definition": "Finalized attempts with no released decision yet.",
         "value": awaiting_release_count, "owner": "Placement Releaser"},
        {"label": "Admissions in Draft",
         "definition": "Admission decisions in Draft.",
         "value": draft_count,
         "owner": "Admission Reviewer"},
        {"label": "Admissions in review",
         "definition": "Admission decisions in Review.",
         "value": review_count, "owner": "Admission Approver"},
        {"label": "Enrollments awaiting a class",
         "definition": "Owner decision D7 defers the inferred class-waiting indicator; assignment and denominator policy are not approved.",
         "value": "—", "owner": "Teaching Scheduler"},
        {"label": "Classes running",
         "definition": "Classes whose lifecycle is Active (planned classes are counted under enrollment coverage instead).",
         "value": active_classes_count, "owner": "Teaching Scheduler"},
        {"label": "Corrections pending",
         "definition": "Correction requests (invoice or tuition fee) in Requested status.",
         "value": corrections_count, "owner": "Finance Officer"},
    ]

    exception_items = []
    if not deadline_evidence_complete:
        exception_items.append({
            "id": "source:placement-deadlines",
            "person": "Placement deadlines",
            "detail": "Unavailable or incomplete deadline evidence",
            "status": "Unknown",
            "stage": "Deadline source needs verification",
            "stage_definition": (
                "An incomplete list or invalid datetime cannot establish "
                "that no placement sessions are overdue."),
            "next": "Verify placement attempts and their server deadlines.",
            "next_role": "General Manager",
            "waiting_since": None,
        })
    # A bounded oldest-action list is not the whole queue. When the
    # independent native total exceeds that preview (or cannot be read),
    # make the missing coverage explicit to staff rather than implying
    # the visible list exhausts the review/correction backlog.
    for count, preview, name, label, next_role in (
        (review_count, review_waiting, "admission-preview",
         "Admission reviews", "Admission Approver"),
        (corrections_count, corrections, "correction-preview",
         "Finance corrections", "Finance Officer"),
    ):
        if (not isinstance(count, int) or isinstance(count, bool)
                or count > len(preview)):
            exception_items.append({
                "id": f"source:{name}",
                "person": label,
                "detail": "More requests exist or total is unavailable",
                "status": "Partial",
                "stage": "Action queue incomplete",
                "stage_definition": (
                    "This is only a bounded oldest-item preview. Review "
                    "the native full list before claiming the queue is empty."),
                "next": "Open the full source list and work remaining items.",
                "next_role": next_role,
                "waiting_since": None,
            })
    for row in review_waiting:
        exception_items.append({
            "id": row["name"],
            "person": row.get("student_applicant") or "",
            "detail": row.get("program") or "",
            "status": "Review",
            "stage": "Admission waiting in review",
            "stage_definition": "The admission decision has been in review longest; work it or escalate it.",
            "next": "Record the admission outcome.",
            "next_role": "Admission Approver",
            "waiting_since": row.get("modified"),
            "age": _age_label(row.get("modified")),
        })
    for row in overdue_deadlines:
        exception_items.append({
            "id": row["name"],
            "person": row.get("case_name") or "",
            "detail": "Placement attempt",
            "status": row["status"],
            "stage": "Attempt past deadline",
            "stage_definition": "A running placement attempt is past its server-set deadline; the next save seals it as Timeout.",
            "next": "Seal the attempt and continue the marking workflow.",
            "next_role": "Placement Invigilator",
            "waiting_since": row.get("deadline_at"),
            "age": _age_label(row.get("deadline_at")),
        })
    for row in corrections:
        # A correction names whatever it targets: the invoice or the
        # tuition-fee document — never an empty row for the fees leg (D6).
        is_fees = bool(row.get("fees"))
        target = row.get("fees") if is_fees else row.get("sales_invoice")
        reason = row.get("reason") or ""
        exception_items.append({
            "id": row["name"],
            "person": target or row["name"],
            "detail": ("Tuition-fee correction" if is_fees else "Invoice correction")
                      + (f" · {reason}" if reason else ""),
            "status": row["status"],
            "stage": "Correction pending",
            "stage_definition": (
                "A tuition-fee correction request is waiting for the policy-"
                "configured approver." if is_fees else
                "An invoice correction request is waiting for the policy-"
                "configured approver."),
            "next": "Approve or deny the correction.",
            "next_role": "Finance Officer",
            "waiting_since": row.get("modified"),
            "age": _age_label(row.get("modified")),
        })
    return funnel_facts, exception_items


ERROR_LOG = "Error Log"
RQ_JOB = "RQ Job"
RQ_WORKER = "RQ Worker"
SCHEDULED_JOB_TYPE = "Scheduled Job Type"
SCHEDULED_JOB_LOG = "Scheduled Job Log"


RQ_JOB_FAILED_FIELDS = ["name", "job_name", "queue", "status",
                        "started_at", "ended_at"]


def _rq_failed_jobs(limit):
    """Failed background-job rows from the native RQ registries.

    RQ Job is a VIRTUAL doctype on pinned frappe, and its controller
    gates every read on ``frappe.has_permission("RQ Job")`` (rq_job.py
    ``get_custom_queues``), ignoring ``ignore_permissions`` — so the
    sanctioned ``project_rows`` projection 403s for desk audiences. This
    fallback reads the same native facts the controller itself reads
    (queue.failed_job_registry + Job.fetch_many + serialize_job),
    confined to the ("management", "RQ Job") projection allow-list.
    Returns (rows, readable): readable is False when the registries
    cannot be reached at all (unknown, never zero).
    """
    _assert_projection("management", RQ_JOB, RQ_JOB_FAILED_FIELDS)
    try:
        from rq.job import Job

        from frappe.core.doctype.rq_job.rq_job import (
            fetch_job_ids,
            filter_current_site_jobs,
            get_job_status,
            serialize_job,
        )
        from frappe.utils.background_jobs import get_queues, get_redis_conn

        ids = []
        for queue in get_queues():
            ids.extend(fetch_job_ids(queue, "failed"))
        conn = get_redis_conn()
        rows = []
        for job in Job.fetch_many(job_ids=filter_current_site_jobs(ids)[:5000],
                                  connection=conn):
            if job is None or get_job_status(job) != "failed":
                continue
            job_dict = serialize_job(job)
            rows.append({field: job_dict.get(field)
                         for field in RQ_JOB_FAILED_FIELDS})
        known = [row for row in rows if not isinstance(row.get("ended_at"), str)]
        unknown = [row for row in rows if isinstance(row.get("ended_at"), str)]
        known.sort(key=lambda row: row["ended_at"], reverse=True)
        return (known + unknown)[:int(limit)], True
    except Exception:
        return [], False


def _system_health():
    """Native health/worker/failed-job facts + alert conditions.

    Shared by the GM desk and the Owner cockpit (same helper, same numbers).
    Reads native Frappe authorities only, through the management projection
    allow-lists; conditions come from toefl_house.observability and are
    generated, never delivered (no receiver exists — see that module).
    """
    try:
        ping_ok = frappe.ping() == "pong"
    except Exception:
        ping_ok = False
    error_logs = project_rows("management", ERROR_LOG,
                              ["name", "method", "seen", "creation"],
                              filters={"seen": 0},
                              order_by="creation desc", limit=LIMIT_QUEUES)
    try:
        # The virtual controller calls frappe.throw on an expected role
        # denial. Catching that exception still leaves _server_messages in
        # the successful desk response, opening a blocking browser modal.
        # Choose the bounded registry projection before entering that path.
        if not frappe.has_permission(RQ_JOB, "read"):
            raise frappe.PermissionError("Use the bounded failed-job projection")
        failed_jobs = project_rows("management", RQ_JOB,
                                   RQ_JOB_FAILED_FIELDS,
                                   filters={"status": "failed"},
                                   order_by="ended_at desc", limit=LIMIT_QUEUES)
        jobs_readable = True
    except frappe.PermissionError:
        # Virtual-doctype controller gate (see _rq_failed_jobs): the desk
        # audience holds no RQ Job read, so project the same native
        # registry facts without the controller.
        failed_jobs, jobs_readable = _rq_failed_jobs(LIMIT_QUEUES)
    workers = project_rows("management", RQ_WORKER,
                           ["name", "worker_name", "queue", "queue_type", "status",
                            "failed_job_count", "successful_job_count",
                            "last_heartbeat"],
                           order_by="worker_name asc", limit=LIMIT_QUEUES)
    stopped_types = project_rows("management", SCHEDULED_JOB_TYPE,
                                 ["name", "method", "frequency", "stopped",
                                  "last_execution"],
                                 filters={"stopped": 1},
                                 order_by="name asc", limit=LIMIT_QUEUES)
    failed_scheduled = project_rows("management", SCHEDULED_JOB_LOG,
                                    ["name", "scheduled_job_type", "status",
                                     "creation"],
                                    filters={"status": "Failed"},
                                    order_by="creation desc", limit=LIMIT_QUEUES)
    summary = obs.summarize_snapshot({
        "error_logs": error_logs, "failed_jobs": failed_jobs,
        "workers": workers, "stopped_job_types": stopped_types,
        "failed_scheduled_logs": failed_scheduled,
    })
    conditions = obs.evaluate_alert_conditions(summary, ping_ok=ping_ok)
    facts = [
        {"label": "Application answers",
         "definition": "The application's own health ping answered.",
         "value": "Yes" if ping_ok else "No", "owner": None},
        {"label": "Unseen error rows",
         "definition": "Native Error Log rows not yet marked seen. The error text stays on the native form.",
         "value": summary["unseen_error_logs"], "owner": "General Manager"},
        {"label": "Failed background jobs",
         "definition": "Native background jobs in failed status. Tracebacks stay on the native job form. When the native job registry cannot be read at all, this shows Not readable instead of a count.",
         "value": summary["failed_jobs"] if jobs_readable else "Not readable", "owner": "General Manager"},
        {"label": "Workers observed",
         "definition": "Native background workers known to the scheduler, with their verbatim reported state.",
         "value": summary["workers_observed"], "owner": None},
        {"label": "Stopped scheduled job types",
         "definition": "Scheduled job types carrying the native stopped flag.",
         "value": summary["stopped_scheduled_job_types"], "owner": "General Manager"},
        {"label": "Failed scheduled runs",
         "definition": "Scheduled runs that ended in native Failed status.",
         "value": summary["failed_scheduled_logs"], "owner": "General Manager"},
    ]
    items = []
    for row in failed_jobs:
        items.append({
            "id": row["name"],
            "person": row.get("job_name") or row["name"],
            "detail": f"queue {row.get('queue') or '—'}",
            "status": "failed",
            "stage": "Failed background job",
            "stage_definition": "A background task failed. The technical details are on the task record.",
            "next": "Open the background task list, retry the task, or ask for technical support.",
            "next_role": "General Manager",
            "waiting_since": row.get("ended_at") or row.get("started_at"),
        })
    for row in error_logs:
        items.append({
            "id": row["name"],
            "person": row.get("method") or row["name"],
            "detail": "unseen error row",
            "status": "unseen",
            "stage": "Unseen error row",
            "stage_definition": "A system error nobody has reviewed yet. The details are on the error record.",
            "next": "Open the error log and mark the entry as seen once it is understood.",
            "next_role": "General Manager",
            "waiting_since": row.get("creation"),
        })
    for row in stopped_types:
        items.append({
            "id": row["name"],
            "person": row.get("method") or row["name"],
            "detail": f"every {row.get('frequency') or '—'}",
            "status": "stopped",
            "stage": "Stopped scheduled job",
            "stage_definition": "A scheduled task is switched off, so it does not run.",
            "next": "Switch the scheduled task back on, or leave it off on purpose.",
            "next_role": "General Manager",
            "waiting_since": row.get("last_execution"),
        })
    for condition in conditions:
        items.append({
            "id": f"condition:{condition['condition']}",
            "person": condition["condition"].replace("_", " "),
            "detail": condition["detail"],
            "status": "observed",
            "stage": "Alert condition",
            "stage_definition": ("A generated condition over the native facts above. Conditions are "
                               "generated, never delivered: no alert receiver exists in this product."),
            "next": "Resolve the records behind this warning.",
            "next_role": "General Manager",
            "waiting_since": None,
        })
    return facts, items


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """GM desk payload: funnel, exceptions, staffing, links."""
    require_desk_audience(SLUG)
    funnel_facts, exception_items = _funnel_and_exceptions()
    health_facts, health_items = _system_health()

    staff_counts = _staff_counts()
    desks_for_viewer = []
    held = viewer_roles()
    for slug, spec in DESKS.items():
        if slug == SLUG:
            continue
        if set(spec["roles"]) & held:
            desks_for_viewer.append({"slug": slug, "title": spec["title"]})

    ops_analytics = []
    if analytics is not None:
        try:
            enroll = analytics.enrollment_metrics()
            tuit = analytics.tuition_metrics()
            exc = analytics.exception_metrics()
            ops_analytics.append(
                section("ops-overview", "Operational overview (auditable)", "facts",
                        facts=[
                            {"label": "Active enrollments", "value": enroll["total"],
                             "definition": enroll["definition"], "source": enroll["source"], "scope": enroll["scope"], "drill_path": enroll["drill"], "owner": "Enrollment Officer"},
                            {"label": "Outstanding tuition", "value": tuit["fees_outstanding"],
                             "definition": "Submitted tuition fees still owing.", "source": "tuition fees outstanding", "scope": tuit["scope"], "drill_path": "tuition fees list", "owner": "Finance Officer"},
                            {"label": "Overdue fees", "value": tuit["fees_overdue"],
                             "definition": "Outstanding fees with due date before today.", "source": "fees overdue", "scope": tuit["scope"], "drill_path": "tuition fees list", "owner": "Finance Officer"},
                            {"label": "Operational exceptions", "value": exc["corrections_pending"] + exc["admissions_in_review"] + exc["attempts_past_deadline"] + exc["awaiting_release"],
                             "definition": exc["definition"], "source": exc["source"], "scope": exc["scope"], "drill_path": exc["drill"], "owner": "General Manager"},
                        ],
                        empty_title="No operational overview yet", empty_body="Operational metrics appear as soon as placement, admission and enrollment records exist."))
            if enroll.get("by_program"):
                ops_analytics[-1]["comparison"] = {
                    "title": "Enrollments by program",
                    "columns": ["Program", "Enrollments"],
                    "rows": [{"label": k, "value": v} for k, v in sorted(enroll["by_program"].items(), key=lambda x: -x[1])[:10]],
                }
                ops_analytics[-1]["chart"] = {
                    "title": "Enrollments per program",
                    "rows": [{"label": k, "value": v, "tone": "info"} for k, v in sorted(enroll["by_program"].items(), key=lambda x: -x[1])[:8]],
                }
        except Exception:
            # A denied/incomplete accounting or academic source is UNKNOWN,
            # never an absent section that looks like verified zero activity.
            ops_analytics.append(section(
                "ops-overview-unavailable", "Operational overview unavailable",
                "facts", facts=[{
                    "label": "Verified operational totals", "value": "—",
                    "definition": "One or more required sources cannot be fully verified. No partial summary is published.",
                    "source": "source verification incomplete",
                    "scope": "unavailable", "drill_path": "source records list",
                    "owner": "General Manager",
                }],
                empty_title="Operational metrics unavailable",
                empty_body="A failed or partial read is not evidence of zero work."))
    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            *ops_analytics,
            *refund_sections("management"),
            section("funnel", "Operation funnel — today\u2019s state", "facts", facts=funnel_facts,
                    empty_title="Nothing needs attention",
                    empty_body="This list shows the most recent records only. Check the counts above before concluding all work is done."),
            section("exceptions", "Exceptions and oldest waiting work — action queue", "queue",
                    items=exception_items,
                    empty_title="No exceptions",
                    empty_body="This list shows the most recent records only. Check the counts above before concluding there are none."),
            section("progression", "Progression decisions not yet recorded", "queue",
                    items=_progression_items(),
                    empty_title="Every published result has a progression decision",
                    empty_body="Published results appear here until the Academic Manager records Promote, Repeat, Retake or Complete."),
            section("activity", "Recent recorded actions", "queue",
                    items=_recorded_action_items(),
                    empty_title="No recorded actions yet",
                    empty_body="When staff complete an important action, the record appears here. The full trail stays with auditor roles."),
            section("staffing", "Role coverage", "queue", items=_role_items(staff_counts) + _teacher_link_items(),
                    empty_title="No operational roles",
                    empty_body="No shipped operational role is assigned to an enabled user."),
            section("health", "System health (native facts)", "queue", items=health_items,
                    empty_title="No health exceptions",
                    empty_body="The application answers, and no failed job, unseen error row or stopped schedule is recorded. Full counts sit beside the funnel facts."),
            section("health-facts", "System health counts", "facts", facts=health_facts,
                    empty_title="No health facts yet",
                    empty_body="System health counts appear once the system has run its scheduled tasks."),
            section("desks", "Your desks", "links", items=desks_for_viewer,
                    empty_title="No other desks for your account",
                    empty_body="This account holds only the General Manager desk."),
            *report_section(FINANCE_REPORTS + ACADEMIC_REPORTS),
        ],
    }
