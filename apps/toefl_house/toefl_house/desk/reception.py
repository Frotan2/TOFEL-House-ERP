"""Reception desk: the front-door answer to "is this person in the system?".

Read-only. Sections and data sources are specified in docs/product/ROLE-DESKS.md.
All reads go through toefl_house.desk.project_rows / project_count, which
enforce the per-desk field allow-list and bounds.
"""
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
from toefl_house.desk import lifecycle

SLUG = "th-reception-desk"

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
        "next": "Open the admission decision for this applicant.",
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


def _funnel(handover_count):
    return [
        {"label": "Placement sessions running",
         "definition": "Placement attempts from Allocated through Review that are not yet finalized.",
         "value": project_count("reception", ATTEMPT, {
             "status": ("in", [s for s in lifecycle.PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])}),
         "owner": "Placement Invigilator"},
        {"label": "Results awaiting intake",
         "definition": "Released placement decisions with no active admission decision attached.",
         "value": handover_count, "owner": "Admission Officer"},
        {"label": "Admissions drafted",
         "definition": "Admission decisions in Draft.",
         "value": project_count("reception", ADMISSION, {"status": "Draft"}),
         "owner": "Admission Reviewer"},
        {"label": "Admissions in review",
         "definition": "Admission decisions in Review.",
         "value": project_count("reception", ADMISSION, {"status": "Review"}),
         "owner": "Admission Approver"},
        {"label": "Offers to accept",
         "definition": "Approved or Conditional decisions whose offer is not yet accepted.",
         "value": project_count("reception", ADMISSION,
                                {"status": ("in", ["Approved", "Conditional"]), "accepted": 0}),
         "owner": "Admission Officer"},
        {"label": "Active students",
         "definition": "Active learner records in the student register.",
         "value": project_count("reception", STUDENT, {"enabled": 1}), "owner": None},
    ]


@frappe.whitelist(methods=["GET", "POST"])
def work():
    """Reception desk payload: funnel, people in the funnel, hand-over queue."""
    require_desk_audience(SLUG)

    decisions = project_rows("reception", DECISION,
                             ["name", "attempt", "status", "released_at", "expires_at",
                              "course_code", "internal_level"],
                             filters={"status": "Released"},
                             order_by="released_at desc", limit=BOUNCE_WINDOW)
    admissions = project_rows("reception", ADMISSION, ADMISSION_FIELDS,
                              filters={"status": ("in", list(lifecycle.ADMISSION_OPEN_STATUSES))},
                              order_by="modified desc", limit=BOUNCE_WINDOW)
    subjects = _subject_index(decisions)

    claimed = {row["placement_decision"] for row in admissions if row.get("placement_decision")}
    subject_to_decision = {}
    for row in admissions:
        subject = subjects.get(row.get("placement_decision") or "")
        if subject and subject not in subject_to_decision:
            subject_to_decision[subject] = row

    applicants = project_rows("reception", APPLICANT, APPLICANT_FIELDS,
                              filters={"application_status": "Applied"},
                              order_by="creation desc", limit=LIMIT_QUEUES)
    decisions_by_applicant = {row["student_applicant"]: row for row in admissions
                              if row.get("student_applicant")}

    handover = [{
        "id": row["name"],
        "person": subjects.get(row["name"]) or row["name"],
        "detail": row.get("course_code") or "",
        "status": row["status"],
        "stage": "Ready for intake",
        "stage_definition": "Placement result released and still valid; no active admission decision uses it yet.",
        "next": "Record the applicant and open the admission file.",
        "next_role": "Admission Officer",
        "waiting_since": row.get("released_at"),
        "action": guided_action("Admission Officer", "toefl_house.admission.record_applicant",
                                "Record applicant",
                                {"placement_decision": row["name"], "first_name": "",
                                 "program": "", "academic_year": ""}),
    } for row in decisions if row["name"] not in claimed]

    people = [_person_item(row, decisions_by_applicant, subject_to_decision) for row in applicants]

    return {
        "desk": SLUG,
        "title": DESKS[SLUG]["title"],
        "sections": [
            section("funnel", "Applicant funnel", "facts", facts=_funnel(len(handover)),
                    empty_title="The funnel is empty",
                    empty_body="No placement or admission records exist yet. A person enters the funnel when a placement case is created by the Placement Publisher."),
            section("people", "People in the funnel", "queue", items=people,
                    empty_title="No open applicants",
                    empty_body="No applicant is in Applied status right now. New applicants appear here as soon as a released placement result is recorded for them."),
            section("handover", "Ready for admission intake", "queue", items=handover,
                    empty_title="No released result is waiting",
                    empty_body="Every released placement result is already attached to an active admission decision, or nothing has been released yet."),
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
    like = f"%{text}%"

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
        decisions_by_applicant = {row["student_applicant"]: row for row in admissions}
    items = [_person_item(row, decisions_by_applicant, {}) for row in matches]

    student_items = []
    student_rows = project_rows("reception", STUDENT,
                                ["name", "student_name", "student_email_id", "creation"],
                                filters={"student_name": ("like", like), "enabled": 1},
                                order_by="creation desc", limit=LIMIT_LOOKUP)
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

    return {"desk": SLUG, "query": text, "items": items, "students": student_items}
