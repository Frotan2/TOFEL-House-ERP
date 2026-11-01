"""Reception desk: the front-door answer to "is this person in the system?".

Read-only. Sections and data sources are specified in docs/ROLE-DESKS.md.
All reads go through toefl_house.desk.project_rows / project_count, which
enforce the per-desk field allow-list and bounds.
"""
import re
import unicodedata

import frappe

from toefl_house.desk import (
    BOUNCE_WINDOW,
    DESKS,
    LIMIT_LOOKUP,
    LIMIT_QUEUES,
    guided_action,
    cohort_state,
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
ROSTER = "Student Group Student"
SCHEDULE = "Course Schedule"
INSTRUCTOR = "Instructor"
GROUP_COHORT_FIELDS = [
    "name", "student_group_name", "program", "academic_year",
    "academic_term", "th_branch", "disabled", "th_class_status",
]

APPLICANT_FIELDS = ["name", "title", "student_email_id", "th_candidate_ref", "th_reception_inquiry", "program",
                    "academic_year", "application_status", "creation"]
ADMISSION_FIELDS = ["name", "student_applicant", "program", "academic_year",
                    "placement_decision", "status", "accepted", "native_student",
                    "version", "modified"]


def _subject_index(decisions):
    """placement decision name -> placement subject, via attempt -> case.

    Two bounded in-list reads. A production subject is the opaque THV candidate
    reference, not an email address or an authentication credential.
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
        for row in project_rows("reception", CASE, ["name", "subject", "status", "th_branch"],
                                filters={"name": ("in", case_names)},
                                order_by="name", limit=BOUNCE_WINDOW):
            # The projection itself enforces Branch User Permissions. Even
            # HQ viewers never get branchless placement subjects in intake.
            if row.get("th_branch"):
                cases[row["name"]] = row
    index = {}
    for decision in decisions:
        attempt = attempts.get(decision.get("attempt"))
        case = cases.get(attempt.get("case_name")) if attempt else None
        index[decision["name"]] = (case or {}).get("subject") or ""
    return index


def _referral_display_names(subjects):
    """Resolve names only through two branch-scoped reads of verified referrals.

    A candidate reference is an internal identity key, not what Reception
    should call the person. Never use an unbranched/mismatched inquiry as a
    name source or infer identity from a shared telephone number.
    """
    keys = sorted({value for value in subjects if isinstance(value, str)
                   and value.startswith("THV-")})
    if not keys or len(keys) >= BOUNCE_WINDOW:
        return {}
    cases = project_rows(
        "reception", CASE,
        ["name", "subject", "th_branch", "reception_inquiry"],
        filters={"subject": ("in", keys)},
        order_by="creation desc", limit=BOUNCE_WINDOW)
    if len(cases) >= BOUNCE_WINDOW:
        return {}
    inquiries = sorted({row.get("reception_inquiry") for row in cases
                       if row.get("reception_inquiry") and row.get("th_branch")})
    if not inquiries or len(inquiries) >= BOUNCE_WINDOW:
        return {}
    intake = project_rows(
        "reception", INQUIRY, ["name", "person_name", "th_branch"],
        filters={"name": ("in", inquiries)},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(intake) >= BOUNCE_WINDOW:
        return {}
    by_id = {row["name"]: row for row in intake}
    result = {}
    for case in cases:
        visit = by_id.get(case.get("reception_inquiry"))
        if visit and visit.get("th_branch") == case.get("th_branch") and visit.get("person_name"):
            result[case["subject"]] = visit["person_name"]
    return result


def _verified_released_cases(cases):
    """Resolve a current release for the exact Branch-verified placement cases.

    A person lookup does not share the dashboard's first page of placement
    decisions. Search the linked cases' attempts instead; never infer a
    release from the existence of a case, applicant, phone or Student.
    The case list comes from the already scoped Inquiry -> Case chain.
    """
    names = sorted({row["name"] for row in cases if row.get("name")})
    if not names or len(names) >= BOUNCE_WINDOW:
        return set()
    attempts = project_rows(
        "reception", ATTEMPT, ["name", "case_name", "status"],
        filters={"case_name": ("in", names)},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(attempts) >= BOUNCE_WINDOW:
        return set()
    by_attempt = {row["name"]: row.get("case_name") for row in attempts
                  if row.get("case_name") in names}
    if not by_attempt:
        return set()
    now = frappe.utils.now_datetime()
    decisions = project_rows(
        "reception", DECISION, ["name", "attempt", "status", "expires_at"],
        filters={"attempt": ("in", sorted(by_attempt)), "status": "Released",
                 "expires_at": (">", now)},
        order_by="released_at desc", limit=BOUNCE_WINDOW)
    if len(decisions) >= BOUNCE_WINDOW:
        return set()
    return {by_attempt[row["attempt"]] for row in decisions
            if row.get("attempt") in by_attempt and _current_release(row, now)}


def _walkin_progress(inquiries, released_subjects):
    """What happened after this inquiry, using only branch-scoped, verified links.

    No loose name or shared-phone joins; no sensitive grades, keys or invoices.
    Missing/ambiguous/truncated projections NEVER claim an identity match.
    """
    if not inquiries or len(inquiries) >= BOUNCE_WINDOW:
        return {}
    by_inquiry = {row["name"]: row for row in inquiries}
    ids = sorted(by_inquiry)
    cases = project_rows(
        "reception", CASE,
        ["name", "subject", "status", "th_branch", "reception_inquiry"],
        filters={"reception_inquiry": ("in", ids)},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(cases) >= BOUNCE_WINDOW:
        return {}
    case_by_inquiry = {}
    case_conflicts = set()
    for case in cases:
        origin = by_inquiry.get(case.get("reception_inquiry"))
        if origin and case.get("th_branch") and origin.get("th_branch") == case.get("th_branch"):
            if origin["name"] in case_by_inquiry:
                case_conflicts.add(origin["name"])
            else:
                case_by_inquiry[origin["name"]] = case
    if not case_by_inquiry:
        return {}
    applicants = project_rows(
        "reception", APPLICANT,
        ["name", "th_candidate_ref", "th_reception_inquiry",
         "th_branch", "application_status"],
        filters={"th_reception_inquiry": ("in", sorted(case_by_inquiry))},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(applicants) >= BOUNCE_WINDOW:
        return {}
    applicant_by_inquiry = {}
    ambiguous = set()
    for applicant in applicants:
        inquiry_id = applicant.get("th_reception_inquiry")
        case = case_by_inquiry.get(inquiry_id)
        if not case:
            continue
        if applicant.get("th_branch") != case.get("th_branch") or (
                applicant.get("th_candidate_ref") != case.get("subject")):
            ambiguous.add(inquiry_id)
            continue
        if inquiry_id in applicant_by_inquiry:
            ambiguous.add(inquiry_id)
        else:
            applicant_by_inquiry[inquiry_id] = applicant
    for inquiry_id in ambiguous:
        applicant_by_inquiry.pop(inquiry_id, None)
    applicant_names = sorted({a["name"] for a in applicant_by_inquiry.values()})
    students = project_rows(
        "reception", STUDENT, ["name", "student_applicant", "th_candidate_ref", "enabled"],
        filters={"student_applicant": ("in", applicant_names)},
        order_by="name", limit=BOUNCE_WINDOW) if applicant_names else []
    if len(students) >= BOUNCE_WINDOW:
        return {}
    student_by_applicant = {}
    ambiguous_students = set()
    candidate_by_applicant = {
        applicant["name"]: applicant.get("th_candidate_ref")
        for applicant in applicant_by_inquiry.values()}
    for student in students:
        applicant_id = student.get("student_applicant")
        if student.get("th_candidate_ref") != candidate_by_applicant.get(applicant_id):
            ambiguous_students.add(applicant_id)
            continue
        if applicant_id in student_by_applicant:
            ambiguous_students.add(applicant_id)
        else:
            student_by_applicant[applicant_id] = student
    for applicant_id in ambiguous_students:
        student_by_applicant.pop(applicant_id, None)
    student_names = sorted({
        student["name"] for student in student_by_applicant.values()
        if student.get("name")})
    enrolled_rows = project_rows(
        "reception", ENROLLMENT,
        ["name", "student", "program", "academic_year",
         "enrollment_date", "docstatus"],
        filters={"student": ("in", student_names), "docstatus": 1},
        order_by="enrollment_date desc", limit=BOUNCE_WINDOW) if student_names else []
    if len(enrolled_rows) >= BOUNCE_WINDOW:
        return {}
    enrolled = {row.get("student") for row in enrolled_rows
                if row.get("student") and int(row.get("docstatus") or 0) == 1}
    released = set(released_subjects or ())
    # Dashboard releases are intentionally bounded; a targeted lookup must
    # still recognize an older (but valid) release linked to its exact case.
    unresolved_cases = [case for case in case_by_inquiry.values()
                        if case.get("subject") not in released]
    released_cases = _verified_released_cases(unresolved_cases)
    result = {}
    for inquiry_id, case in case_by_inquiry.items():
        applicant = applicant_by_inquiry.get(inquiry_id)
        if inquiry_id in ambiguous or inquiry_id in case_conflicts or (
                applicant and applicant["name"] in ambiguous_students):
            result[inquiry_id] = (
                "Identity review needed",
                "Academic Manager must investigate multiple linked records; do not register another Student.",
                "Academic Manager")
            continue
        student = student_by_applicant.get(applicant["name"]) if applicant else None
        if student and student.get("th_candidate_ref") == case["subject"]:
            if not int(student.get("enabled") or 0):
                result[inquiry_id] = (
                    "Inactive student",
                    "Ask Academic Manager to verify inactive status; do not enroll or reactivate here.",
                    "Academic Manager")
            elif student["name"] in enrolled:
                result[inquiry_id] = (
                    "Enrollment on file",
                    "A submitted Program Enrollment exists for this Student. Verify the exact admission period and assigned class before confirming attendance.",
                    "Academic Manager")
            else:
                result[inquiry_id] = (
                    "Student profile created",
                    "Student record exists. Ask Enrollment Officer to complete Program Enrollment.",
                    "Enrollment Officer")
        elif applicant:
            result[inquiry_id] = (
                "Admission in progress",
                "Applicant exists; Admission Officer must complete the independent decision and Student conversion.",
                "Admission Officer")
        elif case.get("subject") in released or case["name"] in released_cases:
            result[inquiry_id] = (
                "Placement result released",
                "Ask Admission Officer to record the Applicant from this reviewed result.",
                "Admission Officer")
        else:
            result[inquiry_id] = (
                "Placement case opened",
                "Placement team must complete the supervised test and independent result release.",
                "Placement Invigilator")
    return result


def _walkin_item(row, progress=None):
    """Branch-scoped reception handover stage; no change to student's records."""
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
    correction = None if closed or progress else guided_action(
        "Reception", "toefl_house.reception_intake.correct_walkin_inquiry",
        "Correct visitor details",
        {"inquiry": row["name"], "expected_version": row["version"],
         "person_name": row.get("person_name") or "",
         "phone": row.get("phone") or "", "reason": ""})
    note = (row.get("notes") or "").strip()
    preview = ("Latest note: " + note[:117] + ("…" if len(note) > 117 else "")) if note else ""
    if progress:
        stage, next_step, next_role = progress
    elif row.get("status") == "Awaiting Placement":
        stage, next_step, next_role = (
            "Awaiting placement allocation",
            "Give this Inquiry reference to Placement Publisher; do not create a second visitor record.",
            "Placement Publisher")
    else:
        stage, next_step, next_role = (
            "Pre-registration",
            "Contact the visitor and arrange the separately authorized placement or admission step.",
            "Reception")
    return {
        "id": row["name"],
        "person": row.get("person_name") or "",
        "detail": " · ".join(part for part in
                             ("Inquiry reference: " + row["name"], row.get("phone") or "",
                              row.get("program_interest") or "", preview) if part),
        "status": row.get("status") or "New",
        "stage": stage if progress else ("Closed inquiry" if closed else stage),
        "stage_definition": (
            "Verified stage from branch-scoped Candidate and native Student links."
            if progress else "Reception inquiry closed." if closed
            else "Reception inquiry only; no placement, Applicant or Student exists."),
        "next": (next_step if progress
                 else "This inquiry is closed; register a new visit if needed."
                 if closed else next_step),
        "next_role": next_role if progress else (None if closed else next_role),
        "waiting_since": row.get("creation"),
        "action": action,
        "actions": [correction] if correction else [],
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
            "Open the admission decision after the Placement Releaser issues the "
            "candidate's reviewed result. Ask the Academic Manager to check the "
            "internal candidate reference when a result is not visible."
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
    decision = subject_to_decision.get(
        applicant.get("th_candidate_ref") or applicant.get("student_email_id") or "")
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
                and (row.get("th_candidate_ref") or row.get("student_email_id"))]
    if not admitted:
        return {}
    by_name = {row["name"]: row for row in admitted}
    student_rows = project_rows(
        "reception", STUDENT, ["name", "student_applicant", "student_email_id",
                               "th_candidate_ref"],
        filters={"student_applicant": ("in", list(by_name)), "enabled": 1},
        order_by="name", limit=BOUNCE_WINDOW)
    if len(student_rows) >= BOUNCE_WINDOW:
        return {}
    verified = {}
    ambiguous = set()
    for student in student_rows:
        applicant_id = student.get("student_applicant")
        original = by_name.get(applicant_id)
        if not original:
            continue
        candidate_ref = original.get("th_candidate_ref")
        if candidate_ref:
            if student.get("th_candidate_ref") != candidate_ref:
                continue
        elif not original.get("student_email_id") or student.get("student_email_id") != original["student_email_id"]:
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
    referral_names = _referral_display_names(subjects.values())
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
    candidate_subjects = sorted(s for s in subject_to_decision if s.startswith("THV-"))
    email_subjects = sorted(s for s in subject_to_decision if not s.startswith("THV-"))
    existing_candidates = project_rows(
        "reception", APPLICANT, APPLICANT_FIELDS,
        filters={"th_candidate_ref": ("in", candidate_subjects)},
        order_by="creation desc", limit=BOUNCE_WINDOW) if candidate_subjects else []
    existing_emails = project_rows(
        "reception", APPLICANT, APPLICANT_FIELDS,
        filters={"student_email_id": ("in", email_subjects)},
        order_by="creation desc", limit=BOUNCE_WINDOW) if email_subjects else []
    existing = list({row["name"]: row for row in existing_emails + existing_candidates}.values())
    existing_by_subject = {}
    for item in existing:
        key = item.get("th_candidate_ref") or item.get("student_email_id")
        if key:
            existing_by_subject[key] = item
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
        applicant = existing_by_subject.get(subject)
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
                                                        "first_name": referral_names.get(subject, ""), "program": "",
                                                        "academic_year": "", **context})
            next_step = "Record the applicant, then open the admission."
            next_role = "Admission Officer"
        handover.append({
            "id": row["name"], "person": referral_names.get(subject, subject),
            "detail": " · ".join(value for value in
                                 ("Candidate: " + subject,
                                  row.get("course_code") or "", row.get("internal_level") or "") if value),
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
    progress = _walkin_progress(inquiries, subjects.values())
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
                    items=[_walkin_item(row, progress.get(row["name"])) for row in inquiries],
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



def _student_class_information(students, enrollments):
    """Verified individual roster + dated session facts for Reception.

    A Program Enrollment proves admission to the PROGRAM, never membership
    in a particular class. Class membership requires that exact Student's
    active native Student Group Student row, a scoped native Student Group,
    and the same program/year/term as their latest submitted enrollment.
    A Course Schedule is a dated session, NOT a recurring weekly timetable.
    """
    latest = {}
    for entry in enrollments:
        if int(entry.get("docstatus") or 0) == 1 and entry.get("student"):
            latest.setdefault(entry["student"], entry)
    active = sorted({
        row["name"] for row in students
        if int(row.get("enabled") or 0) == 1 and row.get("name") in latest
    })
    if not active:
        return {}
    review = {
        "stage": "Class details require review",
        "next": "Class records exceed the complete permitted read; ask Academic Manager to verify. Do not quote an unverified class or time.",
        "next_role": "Academic Manager", "detail": "",
    }
    roster = project_rows(
        "reception", ROSTER, ["name", "parent", "student", "active"],
        filters={"student": ("in", active), "active": 1},
        order_by="name asc", limit=BOUNCE_WINDOW)
    if len(roster) >= BOUNCE_WINDOW:
        return {name: dict(review) for name in active}
    names = sorted({row.get("parent") for row in roster if row.get("parent")})
    groups = project_rows(
        "reception", GROUP, GROUP_COHORT_FIELDS,
        filters={"name": ("in", names)},
        order_by="name asc", limit=BOUNCE_WINDOW) if names else []
    if len(groups) >= BOUNCE_WINDOW:
        return {name: dict(review) for name in active}
    by_name = {group["name"]: group for group in groups}
    matches = {name: {} for name in active}
    for member in roster:
        student = member.get("student")
        group = by_name.get(member.get("parent"))
        entry = latest.get(student)
        if not entry or not group or not group.get("th_branch") or int(group.get("disabled") or 0):
            continue
        if cohort_state(group) not in ("Planned", "Active"):
            continue
        if (group.get("program"), group.get("academic_year"),
                group.get("academic_term") or "") != (
                entry.get("program"), entry.get("academic_year"),
                entry.get("academic_term") or ""):
            continue
        matches[student][group["name"]] = group

    # Only a unique, individually verified Active class can provide a dated
    # session to this learner. Multiple matching groups are not auto-selected.
    active_groups = sorted({
        next(iter(groups_for_student)) for groups_for_student in matches.values()
        if len(groups_for_student) == 1
        and cohort_state(next(iter(groups_for_student.values()))) == "Active"
    })
    sessions = project_rows(
        "reception", SCHEDULE,
        ["name", "student_group", "instructor", "course", "room",
         "from_time", "to_time", "schedule_date", "th_session_status"],
        filters={"student_group": ("in", active_groups),
                 "schedule_date": (">=", frappe.utils.today()),
                 "th_session_status": "Scheduled"},
        order_by="schedule_date asc, from_time asc, name asc",
        limit=BOUNCE_WINDOW) if active_groups else []
    truncated_sessions = len(sessions) >= BOUNCE_WINDOW
    instructors = {}
    if not truncated_sessions and sessions:
        keys = sorted({row.get("instructor") for row in sessions
                       if row.get("instructor")})
        names_rows = project_rows(
            "reception", INSTRUCTOR, ["name", "instructor_name"],
            filters={"name": ("in", keys)},
            order_by="name asc", limit=BOUNCE_WINDOW) if keys else []
        if len(names_rows) >= BOUNCE_WINDOW:
            truncated_sessions = True
        else:
            instructors = {row["name"]: row.get("instructor_name")
                           for row in names_rows}
    sessions_by_group = {}
    if not truncated_sessions:
        for row in sessions:
            sessions_by_group.setdefault(row.get("student_group"), []).append(row)

    result = {}
    for name in active:
        choices = matches[name]
        if not choices:
            result[name] = {
                "stage": "Enrolled, class not confirmed",
                "next": "Submitted program enrollment exists, but this Student has no verified active roster in a matching planned or active class. Ask Teaching Scheduler to confirm placement.",
                "next_role": "Teaching Scheduler", "detail": "",
            }
            continue
        if len(choices) != 1:
            result[name] = {
                "stage": "Multiple class memberships",
                "next": "Multiple matching class rosters are active for this academic period. Academic Manager must verify the correct class and timetable.",
                "next_role": "Academic Manager", "detail": "",
            }
            continue
        group = next(iter(choices.values()))
        label = group.get("student_group_name") or group["name"]
        detail = "Class: " + label + " (" + group["name"] + ")"
        if cohort_state(group) == "Planned":
            result[name] = {
                "stage": "Class planned",
                "next": "This Student is on a planned class roster. Classes and meeting times are not confirmed until activation and scheduled sessions.",
                "next_role": "Teaching Scheduler", "detail": detail,
            }
        elif truncated_sessions:
            result[name] = {
                "stage": "Class assigned, timetable needs review",
                "next": "Session or teacher lookup is incomplete; ask Teaching Scheduler to verify the timetable before informing the learner.",
                "next_role": "Teaching Scheduler", "detail": detail,
            }
        else:
            upcoming = sessions_by_group.get(group["name"], [])
            if not upcoming:
                result[name] = {
                    "stage": "Class assigned, schedule pending",
                    "next": "An active class roster is verified, but no upcoming Scheduled session is on file. Ask Teaching Scheduler for confirmed dates.",
                    "next_role": "Teaching Scheduler", "detail": detail,
                }
                continue
            previews = []
            for session in upcoming[:3]:
                teacher_id = session.get("instructor")
                teacher = instructors.get(teacher_id)
                parts = [
                    str(session.get("schedule_date") or ""),
                    str(session.get("from_time") or "") + "–" + str(session.get("to_time") or ""),
                    session.get("course") or "",
                    "Room: " + str(session["room"]) if session.get("room") else "Room unassigned",
                    "Session instructor: " + teacher if teacher else "Instructor name unverified",
                ]
                previews.append(" / ".join(part for part in parts if part))
            result[name] = {
                "stage": "Class assigned, sessions scheduled",
                "next": "Next dated session(s): " + "; ".join(previews)
                        + ". This is not a recurring weekly timetable.",
                "next_role": None, "detail": detail,
            }
    return result


@frappe.whitelist(methods=["GET", "POST"])
def lookup(query):
    """Find a person across applicants and students; answer with the stage.

    Bounded server-side reads; the typed text is matched as a contained
    pattern through Frappe's escaped like handling. No wildcard is added by
    the caller and results are capped.
    """
    require_desk_audience(SLUG)
    if not isinstance(query, str):
        frappe.throw("Enter a name, contact or printed reference.", frappe.ValidationError)
    text = query.strip()
    if len(text) < 2:
        frappe.throw("Type at least two characters of a name, reference or contact.",
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
    # Printed Afghan telephone numbers often include spaces or dashes,
    # while intake stores a single canonical contact. Only apply this
    # normalization to a phone-shaped query, never to a person's name.
    phone_query = text
    if re.fullmatch(r"\+?[0-9 ()-]{5,32}", text) and 5 <= sum(
            char.isdigit() for char in text) <= 15:
        phone_query = re.sub(r"[ ()-]", "", text)
    phone_escaped = phone_query.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    phone_like = f"%{phone_escaped}%"

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
    # Candidate references are opaque identifiers, not email addresses.
    # All reads remain through the branch-aware minimal-field projection.
    for row in project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                            filters={"th_candidate_ref": ("like", like)},
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
                                ["name", "student_name", "student_email_id",
                                 "th_candidate_ref", "enabled", "creation"],
                                filters={"student_name": ("like", like), "enabled": ("in", [0, 1])},
                                order_by="creation desc", limit=LIMIT_LOOKUP)
    seen_students = {row["name"] for row in student_rows}
    # Native Student lookup advertised name OR email. Search both with the
    # same restricted projection and bound; keep one row per student.
    for row in project_rows("reception", STUDENT,
                            ["name", "student_name", "student_email_id",
                             "th_candidate_ref", "enabled", "creation"],
                            filters={"student_email_id": ("like", like), "enabled": ("in", [0, 1])},
                            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen_students:
            student_rows.append(row)
            seen_students.add(row["name"])
    for search_field in ("th_candidate_ref", "name"):
        for row in project_rows(
                "reception", STUDENT,
                ["name", "student_name", "student_email_id",
                 "th_candidate_ref", "enabled", "creation"],
                filters={search_field: (text if search_field == "name" else ("like", like)),
                         "enabled": ("in", [0, 1])},
                order_by="creation desc", limit=LIMIT_LOOKUP):
            if row["name"] not in seen_students:
                student_rows.append(row)
                seen_students.add(row["name"])
    student_rows = student_rows[:LIMIT_LOOKUP]
    if student_rows:
        enrollments = project_rows("reception", ENROLLMENT,
                                   ["name", "student", "student_name", "program",
                                    "academic_year", "academic_term",
                                    "enrollment_date", "docstatus"],
                                   filters={"student": ("in", [r["name"] for r in student_rows]),
                                            "docstatus": 1},
                                   order_by="enrollment_date desc, name desc", limit=BOUNCE_WINDOW)
        # Never infer this learner's own class from an unrelated class with
        # the same program/year. Read the verified individual roster instead.
        # Incomplete enrollment reads must not generate a false class claim.
        enrollment_complete = len(enrollments) < BOUNCE_WINDOW
        enrolled = {}
        for entry in enrollments:
            if entry.get("student"):
                enrolled.setdefault(entry["student"], entry)
        classes = (_student_class_information(student_rows, enrollments)
                   if enrollment_complete else {})
        for row in student_rows:
            enrollment = enrolled.get(row["name"])
            class_info = classes.get(row["name"])
            inactive = not bool(int(row.get("enabled", 1) or 0))
            if inactive:
                stage = {
                    "label": "Inactive student",
                    "definition": "This Student record is disabled; enrollment and reactivation are not authorized.",
                    "next": "Ask Academic Manager to verify this person's status and approved reactivation policy.",
                    "role": "Academic Manager",
                }
            else:
                stage = ({"label": "Enrollment records need review",
                          "definition": "The submitted enrollment read is incomplete.",
                          "next": "Ask Academic Manager to verify the program and period before confirming a class.",
                          "role": "Academic Manager"}
                         if not enrollment_complete else
                         {"label": class_info["stage"],
                          "definition": "Verified submitted enrollment and individual class-roster facts.",
                          "next": class_info["next"],
                          "role": class_info["next_role"]}
                         if enrollment and class_info else
                         lifecycle.enrollment_stage(False, False))
            student_items.append({
                "id": row["name"],
                "person": row.get("student_name") or row["name"],
                "detail": " · ".join(x for x in (
                    row.get("th_candidate_ref") or row["name"],
                    (enrollment or {}).get("program") or "",
                    (enrollment or {}).get("academic_year") or "",
                    (enrollment or {}).get("academic_term") or "",
                    (class_info or {}).get("detail") or "") if x),
                "status": "Inactive" if inactive else "Student",
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
                            filters={"phone": ("like", phone_like)},
                            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen_inquiries:
            inquiries.append(row)
            seen_inquiries.add(row["name"])
    # A printed inquiry reference must also be searchable without phone or email.
    for row in project_rows(
            "reception", INQUIRY, INQUIRY_FIELDS,
            filters={"name": text},
            order_by="creation desc", limit=LIMIT_LOOKUP):
        if row["name"] not in seen_inquiries:
            inquiries.append(row)
            seen_inquiries.add(row["name"])
    # Preliminary visitors are NOT yet applicants. Keep them in their own
    # results category so Reception never mistakes a contact for enrollment.
    visible_inquiries = inquiries[:LIMIT_LOOKUP]
    linked_progress = _walkin_progress(visible_inquiries, [])
    visitor_items = [
        _walkin_item(row, linked_progress.get(row["name"]))
        for row in visible_inquiries]
    return {"desk": SLUG, "query": text, "items": items,
            "inquiries": visitor_items, "students": student_items,
            "collection_sections": reception_sections(students=[row["name"] for row in student_rows])}
