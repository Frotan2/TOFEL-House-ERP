"""Reception desk: the front-door answer to "is this person in the system?".

Read-only. Sections and data sources are specified in docs/ROLE-DESKS.md.
All reads go through toefl_house.desk.project_rows / project_count, which
enforce the per-desk field allow-list and bounds.
"""
import unicodedata

import frappe

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_LOOKUP,
    LIMIT_QUEUES,
    guided_action,
    open_cohort_keys,
    project_count,
    project_rows,
    require_desk_audience,
    section,
)
try:
    from toefl_house.desk import analytics
except Exception:
    analytics = None
from toefl_house.desk import lifecycle
from toefl_house.desk.collections import reception_sections

SLUG = "th-reception-desk"

INQUIRY = "TH Reception Inquiry"
INQUIRY_FIELDS = ["name", "person_name", "phone", "program_interest", "th_branch",
                  "status", "notes", "recorded_by", "version", "creation"]

APPLICANT = "Student Applicant"
ADMISSION = "TH Admission Decision"
DECISION = "TH Placement Decision"
ATTEMPT = "TH Placement Attempt"
CASE = "TH Placement Case"
STUDENT = "Student"
ENROLLMENT = "Program Enrollment"
GROUP = "Student Group"
GROUP_COHORT_FIELDS = ["name", "program", "academic_year", "disabled",
                       "th_class_status"]

APPLICANT_FIELDS = ["name", "title", "student_email_id", "program",
                    "academic_year", "application_status", "creation"]
ADMISSION_FIELDS = ["name", "student_applicant", "program", "academic_year",
                    "placement_decision", "status", "accepted", "native_student",
                    "version", "modified"]


def _subject_index(decisions):
    """placement decision name -> placement subject, via attempt -> case.

    Two bounded in-list reads; the subject is the placement candidate's email,
    which is also the applicant email recorded at intake.
    """
    if not decisions:
        return {}
    attempt_names = sorted({row["attempt"] for row in decisions if row.get("attempt")})
    attempts = {}
    if attempt_names:
        for row in project_rows("reception", ATTEMPT, ["name", "case_name", "status"],
                                filters={"name": ("in", attempt_names)},
                                order_by="name", limit=BOUNCE_WINDOW):
            attempts[row["name"]] = row
    case_names = sorted({row["case_name"] for row in attempts.values() if row.get("case_name")})
    cases = {}
    if case_names:
        for row in project_rows("reception", CASE, ["name", "subject", "status"],
                                filters={"name": ("in", case_names)},
                                order_by="name", limit=BOUNCE_WINDOW):
            cases[row["name"]] = row
    index = {}
    for decision in decisions:
        attempt = attempts.get(decision.get("attempt"))
        case = cases.get(attempt.get("case_name")) if attempt else None
        index[decision["name"]] = (case or {}).get("subject") or ""
    return index


def _walkin_item(row):
    """Visitor is NOT yet an Applicant, Student or enrolled fee payer."""
    closed = row.get("status") == "Closed"
    action = None if closed else guided_action(
        "Reception", "toefl_house.reception_intake.update_walkin_inquiry",
        "Update follow-up", {"inquiry": row["name"],
                             "expected_version": row["version"],
                             "status": ("Contacted" if row.get("status") == "New"
                                        else row.get("status")),
                             "notes": row.get("notes") or ""})
    # A short note preview allows staff to see the latest contact instruction
    # without repeatedly opening the editor. Full notes remain on the
    # protected inquiry projection and are escaped by the queue renderer.
    note = (row.get("notes") or "").strip()
    preview = ("Latest note: " + note[:117] + ("…" if len(note) > 117 else "")) if note else ""
    return {
        "id": row["name"],
        "person": row.get("person_name") or "",
        "detail": " · ".join(part for part in
                             (row.get("phone") or "", row.get("program_interest") or "", preview) if part),
        "status": row.get("status") or "New",
        "stage": "Pre-registration",
        "stage_definition": "Reception inquiry only; no candidate account, placement, enrollment or bill was created.",
        "next": ("This inquiry is closed; register a new visit if needed." if closed
                 else "Contact the visitor and arrange the separately authorized placement or admission step."),
        "next_role": None if closed else "Reception",
        "waiting_since": row.get("creation"),
        "action": action,
    }


def _current_release(row, now):
    """Fail closed for missing, malformed or expired release timestamps."""
    if row.get("status") != "Released" or not row.get("expires_at"):
        return False
    try:
        return frappe.utils.get_datetime(row["expires_at"]) > now
    except (TypeError, ValueError, OverflowError):
        return False


def _admission_item(row, decision):
    stage = lifecycle.admission_stage(
        decision["status"], bool(decision.get("accepted")), bool(decision.get("native_student")))
    item = {
        "id": row["name"],
        "person": row.get("title") or "",
        "detail": row.get("program") or "",
        "status": decision["status"],
        "stage": stage["label"],
        "stage_definition": stage["definition"],
        "next": stage["next"],
        "next_role": stage["role"],
        "waiting_since": row.get("modified"),
    }
    prefills = {
        "review_admission": ("Admission Reviewer", "toefl_house.admission.review_admission",
                             "Send for review", {"name": decision["name"], "expected_version": decision["version"]}),
        "decide_admission": ("Admission Approver", "toefl_house.admission.decide_admission",
                             "Record outcome", {"name": decision["name"], "expected_version": decision["version"]}),
        "accept_offer": ("Admission Officer", "toefl_house.admission.accept_offer",
                         "Accept offer", {"name": decision["name"], "expected_version": decision["version"]}),
        "satisfy_conditions": ("Admission Approver", "toefl_house.admission.satisfy_conditions",
                                "Verify conditions", {"name": decision["name"], "expected_version": decision["version"],
                                                      "evidence": ""}),
        "convert_applicant": ("Admission Approver", "toefl_house.admission.convert_applicant",
                              "Convert to Student", {"name": decision["name"], "expected_version": decision["version"]}),
        "enroll_in_program": ("Enrollment Officer", "toefl_house.enrollment.enroll_in_program",
                              "Enroll in program", {"admission_decision": decision["name"]}),
    }
    if stage["command"] in prefills:
        role, endpoint, label, args = prefills[stage["command"]]
        item["action"] = guided_action(role, endpoint, label, args)
    return item


def _person_item(applicant, decisions_by_applicant, subject_to_decision):
    decision = decisions_by_applicant.get(applicant["name"])
    if decision:
        return _admission_item(applicant, decision)
    stage = {
        "label": "Applicant recorded",
        "definition": "The applicant is on file, but no admission decision has been opened yet.",
        "next": (
            "Open the admission decision once a placement result is released for this "
            "applicant's email. A placement result appears after the Placement Publisher "
            "finalizes the attempt and the Placement Releaser releases it — ask those "
            "roles to publish the result if it is not yet visible."
        ),
        "role": "Admission Officer",
        "command": "create_admission",
    }
    item = {
        "id": applicant["name"],
        "person": applicant.get("title") or applicant.get("student_email_id") or applicant["name"],
        "detail": applicant.get("program") or "",
        "status": applicant.get("application_status") or "Applied",
        "stage": stage["label"],
        "stage_definition": stage["definition"],
        "next": stage["next"],
        "next_role": stage["role"],
        "waiting_since": applicant.get("creation"),
    }
    decision = subject_to_decision.get(applicant.get("student_email_id") or "")
    if decision:
        item["action"] = guided_action("Admission Officer", "toefl_house.admission.create_admission",
                                       "Create admission",
                                       {"student_applicant": applicant["name"],
                                        "placement_decision": decision["name"]})
    return item


def _verified_returning_students(applicants):
    """Find the one native Student for each admitted applicant, within desk scope.

    Never infer identity from name or a shared phone. A Student must carry the
    exact native applicant link AND the same verified email, be enabled, and
    remain visible through the normal branch-scoped Reception projection.
    Missing, ambiguous or truncated lookups produce no automatic action.
    """
    admitted = [row for row in applicants if row.get("application_status") == "Admitted"
                and row.get("student_email_id")]
    if not admitted:
        return {}
    by_name = {row["name"]: row for row in admitted}
    student_rows = project_rows(
        "reception", STUDENT, ["name", "student_applicant", "student_email_id"],
        filters={"student_applicant": ("in", list(by_name)), "enabled": 1},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(student_rows) >= BOUNCE_WINDOW:
        return {}
    verified = {}
    ambiguous = set()
    for student in student_rows:
        applicant_id = student.get("student_applicant")
        original = by_name.get(applicant_id)
        if not original or student.get("student_email_id") != original["student_email_id"]:
            continue
        if applicant_id in verified:
            ambiguous.add(applicant_id)
        else:
            verified[applicant_id] = student["name"]
    return {name: student for name, student in verified.items() if name not in ambiguous}


def _funnel(handover_count):
    return [
        {"label": "Placement sessions running",
         "definition": "Placement attempts from Allocated through Review that are not yet finalized.",
         "value": project_count("reception", ATTEMPT, {
             "status": ("in", [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])}),
         "owner": "Placement Invigilator", "source": "placement attempts (non-finalized)", "scope": "Branch-wide", "drill_path": "placement attempt list"},
        {"label": "Results awaiting intake (visible)",
         "definition": "Released placement decisions with no active admission decision attached.",
         "value": handover_count, "owner": "Admission Officer", "source": "released placement outcomes", "scope": "Branch-wide", "drill_path": "placement decision list"},
        {"label": "Admissions drafted",
         "definition": "Admission decisions in Draft — waiting for review.",
         "value": project_count("reception", ADMISSION, {"status": "Draft"}),
         "owner": "Admission Reviewer", "source": "admission decisions in Draft", "scope": "Branch via applicant linkage", "drill_path": "admission decision list"},
        {"label": "Admissions in review",
         "definition": "Admission decisions in Review — oldest first is action priority.",
         "value": project_count("reception", ADMISSION, {"status": "Review"}),
         "owner": "Admission Approver", "source": "admission decisions in Review", "scope": "Branch via applicant linkage", "drill_path": "admission decision list"},
        {"label": "Offers to accept",
         "definition": "Approved or Conditional decisions whose offer is not yet accepted.",
         "value": project_count("reception", ADMISSION,
                                {"status": ("in", ["Approved", "Conditional"]), "accepted": 0}),
         "owner": "Admission Officer", "source": "admission decisions awaiting acceptance", "scope": "Branch via applicant linkage", "drill_path": "admission decision list"},
        {"label": "Active students",
         "definition": "Active learner records in the student register.",
         "value": project_count("reception", STUDENT, {"enabled": 1}), "owner": None, "source": "active learners (native register)", "scope": "Branch via roster or HQ unrestricted", "drill_path": "student list"},
    ]


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Reception desk payload: funnel, people in the funnel, hand-over queue."""
    require_desk_audience(SLUG)

    # Apply expiry before the bounded read: otherwise hundreds of expired
    # decisions can occupy the first page and hide valid, older results.
    now = frappe.utils.now_datetime()
    decisions = project_rows("reception", DECISION,
                             ["name", "attempt", "status", "released_at", "expires_at",
                              "course_code", "internal_level"],
                             filters={"status": "Released", "expires_at": (">", now)},
                             order_by="released_at desc", limit=BOUNCE_WINDOW)
    # A missing/malformed value is still refused defensively.
    decisions = [row for row in decisions if _current_release(row, now)]
    admissions = project_rows("reception", ADMISSION, ADMISSION_FIELDS,
                              filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                              order_by="modified desc", limit=BOUNCE_WINDOW)
    subjects = _subject_index(decisions)
    claimed = {row["placement_decision"] for row in admissions if row.get("placement_decision")}
    # A different released attempt must not offer a second admission while
    # this applicant still has an unconverted active admission.
    unconverted_subjects = {subjects.get(row.get("placement_decision") or "")
                            for row in admissions if not row.get("native_student")}
    ready = [row for row in decisions
             if row["name"] not in claimed
             and subjects.get(row["name"]) not in unconverted_subjects
             and subjects.get(row["name"])]

    # Use the released placement SUBJECT, not an already-created admission,
    # to locate the next decision for a person with no admission yet.
    subject_to_decision = {}
    for row in ready:
        subject_to_decision.setdefault(subjects[row["name"]], row)

    applicants = project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                              filters={"application_status": "Applied"},
                              order_by="creation desc", limit=LIMIT_QUEUES)
    # Include returning learners whose native Applicant is already Admitted.
    existing = project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                            filters={"student_email_id": ("in", list(subject_to_decision))},
                            order_by="creation desc", limit=BOUNCE_WINDOW) if subject_to_decision else []
    existing_by_email = {row["student_email_id"]: row for row in existing
                         if row.get("student_email_id")}
    returning_students = _verified_returning_students(existing)
    decisions_by_applicant = {}
    for row in admissions:
        # Rows are newest-first. Never overwrite the latest with older state.
        if row.get("student_applicant"):
            decisions_by_applicant.setdefault(row["student_applicant"], row)

    handover = []
    pending_applicants = {r.get("student_applicant") for r in admissions
                          if not r.get("native_student")}
    for row in ready:
        subject = subjects[row["name"]]
        applicant = existing_by_email.get(subject)
        if applicant and applicant["name"] in pending_applicants:
            continue
        context = {
            "placement_course_code": row.get("course_code") or "",
            "placement_level": row.get("internal_level") or "",
        }
        if applicant and applicant.get("application_status") == "Admitted":
            existing_student = returning_students.get(applicant["name"])
            if existing_student:
                action = guided_action("Admission Officer", "toefl_house.admission.create_admission",
                                       "Open returning admission", {
                                           "student_applicant": applicant["name"],
                                           "placement_decision": row["name"],
                                           "existing_student": existing_student, **context})
                next_step = "Confirm the new program and academic period before opening the returning admission."
                next_role = "Admission Officer"
            else:
                # The native admission command requires a linked existing Student.
                # A misleading button would fail; never guess an identity here.
                action = None
                next_step = ("Ask Academic Manager to verify the previous Student record and branch. "
                             "Do not create a duplicate applicant or Student.")
                next_role = "Academic Manager"
        elif applicant:
            action = guided_action("Admission Officer", "toefl_house.admission.create_admission",
                                   "Open admission", {"student_applicant": applicant["name"],
                                                      "placement_decision": row["name"], **context})
            next_step = "Open the admission for the existing applicant."
            next_role = "Admission Officer"
        else:
            action = guided_action("Admission Officer", "toefl_house.admission.record_applicant",
                                   "Record applicant", {"placement_decision": row["name"],
                                                        "first_name": "", "program": "",
                                                        "academic_year": "", **context})
            next_step = "Record the applicant, then open the admission."
            next_role = "Admission Officer"
        handover.append({
            "id": row["name"], "person": subject,
            "detail": " · ".join(value for value in
                                 (row.get("course_code") or "", row.get("internal_level") or "") if value),
            "status": row["status"], "stage": "Ready for intake",
            "stage_definition": "Valid released placement with no unconsumed admission.",
            "next": next_step, "next_role": next_role,
            "waiting_since": row.get("released_at"), "action": action,
        })

    people = [_person_item(row, decisions_by_applicant, subject_to_decision) for row in applicants]

    open_statuses = {"status": ("in", ["New", "Contacted", "Awaiting Placement"])}
    inquiry_count = project_count("reception", INQUIRY, open_statuses)
    inquiries = project_rows("reception", INQUIRY, INQUIRY_FIELDS,
                             filters=open_statuses,
                             order_by="creation desc", limit=LIMIT_QUEUES)
    register = guided_action("Reception", "toefl_house.reception_intake.create_walkin_inquiry",
                             "Register a new visitor",
                             {"person_name": "", "phone": "", "program_interest": "",
                              "branch": "", "notes": ""})

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "primary_action": register,
        "sections": [
            section("walkins", f"New visitors and follow-ups ({inquiry_count})", "queue",
                    items=[_walkin_item(row) for row in inquiries],
                    empty_title="No open reception inquiries",
                    empty_body="Register a visitor before placement or any student account exists.",
                    notes=(f"Showing the newest {len(inquiries)} of {inquiry_count} open visits. "
                           "Use the search box above for older visitors."
                           if inquiry_count > len(inquiries) else ""),
                    actions=[register] if register else []),
            section("handover", "Ready for admission intake", "queue", items=handover,
                    empty_title="No released result is waiting",
                    empty_body="A released valid placement decision will appear here when ready."),
            section("people", "People in the admission process", "queue", items=people,
                    empty_title="No applications awaiting a decision",
                    empty_body="Visitors can be registered above before any placement result exists."),
            *reception_sections(),
            section("funnel", "Applicant funnel", "facts", facts=_funnel(len(handover)),
                    empty_title="The funnel is empty",
                    empty_body="No placement or admission records exist yet. A person enters the funnel when a placement case is created by the Placement Publisher."),
        ],
    }


@frappe.whitelist(methods=["GET", "POST"])
def lookup(query):
    """Find a person across applicants and students; answer with the stage.

    Bounded server-side reads; the typed text is matched as a contained
    pattern through Frappe's escaped like handling. No wildcard is added by
    the caller and results are capped.
    """
    require_desk_audience(SLUG)
    text = (query or "").strip()
    if len(text) < 2:
        frappe.throw("Type at least two characters of a name or email.",
                     frappe.ValidationError)
    if len(text) > 120:
        text = text[:120]
    # Match a phone number regardless of whether Reception types Afghan
    # Dari/Persian or Latin decimal digits in the search box.
    text = "".join(
        str(unicodedata.decimal(char)) if char.isdecimal() else char
        for char in text)
    # Treat percent and underscore from staff input as literal search text.
    escaped = text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    like = f"%{escaped}%"

    matches = project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                           filters={"title": ("like", like)},
                           order_by="creation desc", limit=LIMIT_LOOKUP)
    seen = {row["name"] for row in matches}
    for row in project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                            filters={"student_email_id": ("like", like)},
                            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen:
            matches.append(row)
            seen.add(row["name"])
    matches = matches[:LIMIT_LOOKUP]

    decisions_by_applicant = {}
    if matches:
        admissions = project_rows("reception", ADMISSION, ADMISSION_FIELDS,
                                  filters={"student_applicant": ("in", [r["name"] for r in matches])},
                                  order_by="modified desc", limit=BOUNCE_WINDOW)
        # Newest-first admission rows must retain the most recent journey.
        for row in admissions:
            if row.get("student_applicant"):
                decisions_by_applicant.setdefault(row["student_applicant"], row)
    items = [_person_item(row, decisions_by_applicant, {}) for row in matches]

    student_items = []
    student_rows = project_rows("reception", STUDENT,
                                ["name", "student_name", "student_email_id", "creation"],
                                filters={"student_name": ("like", like), "enabled": 1},
                                order_by="creation desc", limit=LIMIT_LOOKUP)
    seen_students = {row["name"] for row in student_rows}
    # Native Student lookup advertised name OR email. Search both with the
    # same restricted projection and bound; keep one row per student.
    for row in project_rows("reception", STUDENT,
                            ["name", "student_name", "student_email_id", "creation"],
                            filters={"student_email_id": ("like", like), "enabled": 1},
                            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen_students:
            student_rows.append(row)
            seen_students.add(row["name"])
    student_rows = student_rows[:LIMIT_LOOKUP]
    if student_rows:
        enrollments = project_rows("reception", ENROLLMENT,
                                   ["name", "student", "student_name", "program",
                                    "academic_year", "enrollment_date", "docstatus"],
                                   filters={"student": ("in", [r["name"] for r in student_rows]),
                                            "docstatus": 1},
                                   order_by="enrollment_date desc", limit=BOUNCE_WINDOW)
        enrolled = {row["student"]: row for row in enrollments}
        # Cohort truth is the class lifecycle (planned or active), derived
        # from the same governed fact every other surface uses — never a
        # flag this desk would have to maintain itself.
        group_rows = project_rows("reception", GROUP, GROUP_COHORT_FIELDS,
                                  filters={"disabled": 0},
                                  order_by="name asc", limit=BOUNCE_WINDOW)
        open_cohorts = open_cohort_keys(group_rows)
        for row in student_rows:
            enrollment = enrolled.get(row["name"])
            has_cohort = bool(enrollment) and (
                enrollment.get("program"), enrollment.get("academic_year")
            ) in open_cohorts
            stage = lifecycle.enrollment_stage(bool(enrollment), has_cohort)
            student_items.append({
                "id": row["name"],
                "person": row.get("student_name") or row["name"],
                "detail": (enrollment or {}).get("program") or "",
                "status": "Student",
                "stage": stage["label"],
                "stage_definition": stage["definition"],
                "next": stage["next"],
                "next_role": stage["role"],
                "waiting_since": (enrollment or row).get("enrollment_date") or row.get("creation"),
            })

    inquiries = project_rows("reception", INQUIRY, INQUIRY_FIELDS,
                             filters={"person_name": ("like", like)},
                             order_by="creation desc", limit=LIMIT_LOOKUP)
    seen_inquiries = {row["name"] for row in inquiries}
    for row in project_rows("reception", INQUIRY, INQUIRY_FIELDS,
                            filters={"phone": ("like", like)},
                            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen_inquiries:
            inquiries.append(row)
            seen_inquiries.add(row["name"])
    # Preliminary visitors are NOT yet applicants. Keep them in their own
    # results category so Reception never mistakes a contact for enrollment.
    visitor_items = [_walkin_item(row) for row in inquiries[:LIMIT_LOOKUP]]
    return {"desk": SLUG, "query": text, "items": items,
            "inquiries": visitor_items, "students": student_items,
            "collection_sections": reception_sections(students=[row["name"] for row in student_rows])}
