"""Thin TOEFL House admission commands over native Education Applicant/Student."""
import frappe
from frappe.utils import get_datetime
from toefl_house.api import ATTEMPT, DECISION, _execute, _now
from toefl_house.policy import ADMISSION_OUTCOMES, digest, validate_admission_text

DECISION_DT = "TH Admission Decision"
APPLICANT = "Student Applicant"
STUDENT = "Student"
PROGRAM = "Program"
YEAR = "Academic Year"


def _iso(value):
    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"{label} required")
    return value


def _result(doc):
    return {
        "name": doc.name,
        "student_applicant": doc.student_applicant,
        "program": doc.program,
        "academic_year": doc.academic_year,
        "placement_decision": doc.placement_decision,
        "status": doc.status,
        "version": doc.version,
        "accepted": int(doc.accepted or 0),
        "native_student": doc.native_student or "",
        "existing_student": doc.existing_student or "",
        "conditions": doc.conditions or "",
    }


def _advance(doc, status=None, **fields):
    if status is not None:
        doc.status = status
    doc.version += 1
    for field, value in fields.items():
        doc.set(field, value)
    doc.save(ignore_permissions=True)


def _locked_decision(name, expected_version):
    if not isinstance(name, str) or not name or len(name) > 140 or type(expected_version) is not int:
        raise frappe.ValidationError("Decision name and integer expected_version required")
    applicant = frappe.db.get_value(DECISION_DT, name, "student_applicant")
    if not applicant:
        raise frappe.ValidationError("Admission decision not found")
    frappe.db.sql("select name from `tabStudent Applicant` where name=%s for update", (applicant,))
    try:
        doc = frappe.get_doc(DECISION_DT, name, for_update=True)
    except frappe.DoesNotExistError as exc:
        raise frappe.ValidationError("Admission decision not found") from exc
    if doc.version != expected_version:
        raise frappe.ValidationError("Stale admission revision")
    return doc


def _placement_row(name):
    name = _name(name, "Placement decision")
    row = frappe.db.get_value(
        DECISION, name,
        ["name", "status", "attempt", "released_at", "expires_at", "course_code", "internal_level"],
        as_dict=True,
    )
    if not row:
        raise frappe.ValidationError("Released placement decision required")
    if row.status != "Released":
        raise frappe.ValidationError("Only a released internal placement decision can support admission")
    return row


def _placement_subject(row):
    subject = frappe.db.get_value(ATTEMPT, row.attempt, "subject")
    if not subject:
        raise frappe.ValidationError("Placement decision is missing its attempt subject")
    return subject


def _unexpired(row, now=None):
    now = now or _now()
    if get_datetime(row.expires_at) <= now:
        raise frappe.ValidationError("Placement decision has expired")


def _active_duplicate(applicant_name):
    return frappe.db.sql(
        "select name from `tabTH Admission Decision` where student_applicant=%s "
        "and status in ('Draft','Review','Approved','Conditional') for update",
        (applicant_name,),
        as_dict=True,
    )


@frappe.whitelist(methods=["POST"])
def deny_enroll_student(source_name=None):
    """A13 containment: native enroll_student is not an Admission API."""
    from toefl_house.security import require_synthetic
    require_synthetic()
    raise frappe.PermissionError(
        "Native enroll_student is contained; enrollment is not part of Admission")


def deny_program_enrollment(doc, method=None):
    from toefl_house.security import require_synthetic
    require_synthetic()
    raise frappe.ValidationError("Program Enrollment is not part of the Admission domain")


def deny_course_enrollment(doc, method=None):
    from toefl_house.security import require_synthetic
    require_synthetic()
    raise frappe.ValidationError("Course Enrollment is not part of the Admission domain")


def deny_premature_invoice(doc, method=None):
    from toefl_house.security import require_synthetic
    require_synthetic()
    customer = getattr(doc, "customer", None)
    if not customer:
        return
    students = frappe.get_all(STUDENT, filters={"customer": customer}, pluck="name")
    if students and frappe.db.exists(DECISION_DT, {"native_student": ["in", students]}):
        raise frappe.ValidationError("Premature billing is denied for admission-converted students")


@frappe.whitelist(methods=["POST"])
def record_applicant(request_key, placement_decision, first_name, program, academic_year):
    def work(actor):
        row = _placement_row(placement_decision)
        _unexpired(row)
        subject = _placement_subject(row)
        first = _name(first_name, "First name")
        if not first.startswith("SYNTHETIC"):
            raise frappe.ValidationError("Only explicitly synthetic applicant names are accepted")
        program = _name(program, "Program")
        academic_year = _name(academic_year, "Academic Year")
        if not frappe.db.exists(PROGRAM, program):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, academic_year):
            raise frappe.ValidationError("Unknown academic year")
        if frappe.db.exists(APPLICANT, {"student_email_id": subject}):
            raise frappe.ValidationError("Applicant already exists for this placement subject")
        applicant = frappe.get_doc(dict(
            doctype=APPLICANT,
            first_name=first,
            last_name="Applicant",
            student_email_id=subject,
            program=program,
            academic_year=academic_year,
            naming_series="EDU-APP-.YYYY.-",
            paid=0,
        ))
        applicant.insert(ignore_permissions=True)
        if applicant.application_status not in (None, "", "Applied"):
            raise frappe.ValidationError("Native applicant status must remain Applied until Student conversion")
        if int(applicant.paid or 0):
            raise frappe.ValidationError("Admission must not mark the native applicant paid")
        result = {
            "name": applicant.name,
            "student_email_id": subject,
            "program": program,
            "academic_year": academic_year,
            "application_status": applicant.application_status or "Applied",
            "paid": int(applicant.paid or 0),
            "placement_decision": row.name,
        }
        return result, dict(target=applicant.name, after_hash=digest([applicant.name, subject, program]))

    return _execute("record_applicant", request_key,
                    {"placement_decision": placement_decision, "first_name": first_name,
                     "program": program, "academic_year": academic_year}, work)


@frappe.whitelist(methods=["POST"])
def create_admission(request_key, student_applicant, placement_decision, existing_student=""):
    def work(actor):
        applicant_name = _name(student_applicant, "Student Applicant")
        frappe.db.sql("select name from `tabStudent Applicant` where name=%s for update",
                      (applicant_name,))
        try:
            applicant = frappe.get_doc(APPLICANT, applicant_name)
        except frappe.DoesNotExistError as exc:
            raise frappe.ValidationError("Student Applicant not found") from exc
        if (applicant.application_status or "Applied") != "Applied":
            raise frappe.ValidationError("Applicant is not in Applied status")
        if int(applicant.paid or 0):
            raise frappe.ValidationError("Paid applicants are not an admission substitute")
        if not frappe.db.exists(PROGRAM, applicant.program):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, applicant.academic_year):
            raise frappe.ValidationError("Unknown academic year")
        row = _placement_row(placement_decision)
        _unexpired(row)
        subject = _placement_subject(row)
        if (applicant.student_email_id or "") != subject:
            raise frappe.ValidationError("Placement subject does not match the native applicant")
        if existing_student:
            existing_student = _name(existing_student, "Existing Student")
            if not frappe.db.exists(STUDENT, existing_student):
                raise frappe.ValidationError("Existing Student not found")
        else:
            existing_student = None
        if _active_duplicate(applicant_name):
            raise frappe.ValidationError("Applicant already has an active admission decision")
        linked = frappe.db.sql(
            "select name from `tabTH Admission Decision` where placement_decision=%s "
            "and status in ('Draft','Review','Approved','Conditional') for update",
            (row.name,), as_dict=True)
        if linked:
            raise frappe.ValidationError("Placement decision is already attached to an active admission")
        doc = frappe.get_doc(dict(
            doctype=DECISION_DT, student_applicant=applicant_name,
            program=applicant.program, academic_year=applicant.academic_year,
            academic_term=applicant.get("academic_term") or None,
            placement_decision=row.name, existing_student=existing_student,
            status="Draft", version=1, drafted_by=actor, accepted=0, synthetic=1,
        ))
        doc.insert(ignore_permissions=True)
        result = _result(doc)
        return result, dict(target=doc.name, after_hash=digest([doc.name, applicant_name, row.name]))

    return _execute("create_admission", request_key,
                    {"student_applicant": student_applicant,
                     "placement_decision": placement_decision,
                     "existing_student": existing_student or ""}, work)


@frappe.whitelist(methods=["POST"])
def review_admission(request_key, name, expected_version):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status != "Draft":
            raise frappe.ValidationError("Only drafts can be reviewed")
        if actor == doc.drafted_by:
            raise frappe.PermissionError("Officer cannot review their own draft")
        reviewed_at = _now()
        _advance(doc, "Review", reviewed_by=actor, reviewed_at=reviewed_at)
        result = _result(doc)
        result["reviewed_by"] = actor
        result["reviewed_at"] = _iso(reviewed_at)
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Review", actor]))

    return _execute("review_admission", request_key,
                    {"name": name, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def decide_admission(request_key, name, expected_version, outcome, reason, conditions=""):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status != "Review":
            raise frappe.ValidationError("Only reviewed decisions can be decided")
        if actor == doc.drafted_by:
            raise frappe.PermissionError("Officer cannot approve their own draft")
        if actor == doc.reviewed_by:
            raise frappe.PermissionError("Reviewer cannot independently decide this admission")
        if outcome not in ADMISSION_OUTCOMES:
            raise frappe.ValidationError("Unsupported admission outcome")
        try:
            reason = validate_admission_text(reason, "reason")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if outcome == "Conditional":
            try:
                conditions = validate_admission_text(conditions, "conditions")
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        else:
            if conditions not in ("", None):
                raise frappe.ValidationError("Conditions are only recorded for Conditional outcomes")
            conditions = ""
        if outcome in ("Approved", "Conditional"):
            row = _placement_row(doc.placement_decision)
            _unexpired(row)
        decided_at = _now()
        _advance(doc, outcome, decided_by=actor, decided_at=decided_at,
                 outcome_reason=reason, conditions=conditions)
        result = _result(doc)
        result["decided_by"] = actor
        result["decided_at"] = _iso(decided_at)
        result["outcome_reason"] = reason
        return result, dict(target=doc.name, after_hash=digest([doc.name, outcome, actor]))

    return _execute("decide_admission", request_key,
                    {"name": name, "expected_version": expected_version,
                     "outcome": outcome, "reason": reason,
                     "conditions": conditions or ""}, work)


@frappe.whitelist(methods=["POST"])
def accept_offer(request_key, name, expected_version):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status not in ("Approved", "Conditional"):
            raise frappe.ValidationError("Only Approved or Conditional offers can be accepted")
        if doc.accepted:
            raise frappe.ValidationError("Offer is already accepted")
        if actor == doc.decided_by:
            raise frappe.PermissionError("Approver cannot record their own offer acceptance")
        row = _placement_row(doc.placement_decision)
        _unexpired(row)
        accepted_at = _now()
        _advance(doc, accepted=1, accepted_by=actor, accepted_at=accepted_at)
        result = _result(doc)
        result["accepted_by"] = actor
        result["accepted_at"] = _iso(accepted_at)
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Accepted", actor]))

    return _execute("accept_offer", request_key,
                    {"name": name, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def withdraw_admission(request_key, name, expected_version, reason):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status not in ("Draft", "Review"):
            raise frappe.ValidationError("Only Draft or Review decisions can be withdrawn")
        if actor != doc.drafted_by:
            raise frappe.PermissionError("Only the drafting officer may withdraw")
        try:
            reason = validate_admission_text(reason, "reason")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        _advance(doc, "Withdrawn", outcome_reason=reason)
        result = _result(doc)
        result["outcome_reason"] = reason
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Withdrawn", actor]))

    return _execute("withdraw_admission", request_key,
                    {"name": name, "expected_version": expected_version, "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def revoke_admission(request_key, name, expected_version, reason):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status not in ("Approved", "Conditional"):
            raise frappe.ValidationError("Only Approved or Conditional decisions can be revoked")
        if doc.native_student:
            raise frappe.ValidationError("Converted decisions cannot be revoked in this slice")
        if actor == doc.drafted_by:
            raise frappe.PermissionError("Officer cannot revoke their own draft")
        try:
            validate_admission_text(reason, "reason")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        revoked_at = _now()
        _advance(doc, "Revoked", revoked_by=actor, revoked_at=revoked_at)
        result = _result(doc)
        result["revoked_by"] = actor
        result["revoked_at"] = _iso(revoked_at)
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Revoked", actor]))

    return _execute("revoke_admission", request_key,
                    {"name": name, "expected_version": expected_version, "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def expire_admission(request_key, name, expected_version):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status not in ("Approved", "Conditional"):
            raise frappe.ValidationError("Only Approved or Conditional offers can expire")
        if doc.native_student:
            raise frappe.ValidationError("Converted decisions cannot expire")
        row = _placement_row(doc.placement_decision)
        if get_datetime(row.expires_at) > _now():
            raise frappe.ValidationError("Placement decision has not expired")
        _advance(doc, "Expired")
        return _result(doc), dict(target=doc.name, after_hash=digest([doc.name, "Expired", actor]))

    return _execute("expire_admission", request_key,
                    {"name": name, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def convert_applicant(request_key, name, expected_version):
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status != "Approved":
            raise frappe.ValidationError("Only an Approved decision can convert a native Student")
        if doc.conditions:
            raise frappe.ValidationError("Conditional admission is not permission to create a Student")
        if not doc.accepted:
            raise frappe.ValidationError("Offer acceptance is required before Student conversion")
        if doc.native_student:
            raise frappe.ValidationError("Applicant already has a converted Student")
        if doc.existing_student:
            raise frappe.ValidationError("Returning-student conversion is not part of this slice")
        if actor == doc.drafted_by:
            raise frappe.PermissionError("Officer cannot convert their own draft")
        if actor == doc.reviewed_by:
            raise frappe.PermissionError("Reviewer cannot convert this admission")
        row = _placement_row(doc.placement_decision)
        _unexpired(row)
        applicant = frappe.get_doc(APPLICANT, doc.student_applicant)
        if (applicant.application_status or "Applied") != "Applied":
            raise frappe.ValidationError("Applicant is not in Applied status")
        if frappe.db.exists(STUDENT, {"student_applicant": applicant.name}):
            raise frappe.ValidationError("A native Student already exists for this applicant")
        try:
            frappe.db.set_single_value("Education Settings", "user_creation_skip", 1)
        except Exception:
            pass
        student = frappe.get_doc(dict(
            doctype=STUDENT,
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            student_email_id=applicant.student_email_id,
            student_applicant=applicant.name,
            joining_date=frappe.utils.today(),
            naming_series="EDU-STU-.YYYY.-",
            enabled=1,
        ))
        student.insert(ignore_permissions=True)
        if frappe.db.exists("Program Enrollment", {"student": student.name}):
            raise frappe.ValidationError("Student conversion must not create Program Enrollment")
        customer = student.customer or frappe.db.get_value(STUDENT, student.name, "customer")
        if customer and frappe.db.exists("Sales Invoice", {"customer": customer}):
            raise frappe.ValidationError("Student conversion must not create a Sales Invoice")
        converted_at = _now()
        _advance(doc, native_student=student.name, converted_at=converted_at)
        native_status = frappe.db.get_value(APPLICANT, applicant.name, "application_status")
        result = _result(doc)
        result["native_student"] = student.name
        result["native_application_status"] = native_status
        result["customer"] = customer or ""
        result["program_enrollment"] = 0
        result["converted_at"] = _iso(converted_at)
        return result, dict(target=doc.name, after_hash=digest([doc.name, student.name]))

    return _execute("convert_applicant", request_key,
                    {"name": name, "expected_version": expected_version}, work)
