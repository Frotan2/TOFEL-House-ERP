"""Thin TOEFL House admission commands over native Education Applicant/Student."""
from contextlib import contextmanager
import frappe
from frappe.utils import get_datetime
from toefl_house.admission import policies as returning_policies
from toefl_house.api import ATTEMPT, DECISION, _execute, _now
from toefl_house.policy import ADMISSION_OUTCOMES, digest, validate_admission_text
from toefl_house.security import is_production, record_synthetic_flag

DECISION_DT = "TH Admission Decision"
APPLICANT = "Student Applicant"
STUDENT = "Student"
PROGRAM = "Program"
YEAR = "Academic Year"
TERM = "Academic Term"


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


@contextmanager
def _native_student_write():
    """Insert nested Customer with ignore_permissions; do not touch session.

    Student.on_update Customer.insert() has no ignore_permissions. Do not patch
    frappe.has_permission or call set_user: both persist onto the Approver SID
    and denied later HTTP idempotent replay on the second gunicorn worker.
    """
    from education.education.doctype.student.student import Student as StudentController
    original_create = StudentController.create_customer
    original_update = StudentController.update_linked_customer

    def create_customer(this):
        customer = frappe.get_doc(dict(
            doctype="Customer",
            customer_name=this.student_name,
            customer_group=this.customer_group or "Student",
            customer_type="Individual",
            image=this.get("image"),
        )).insert(ignore_permissions=True)
        frappe.db.set_value("Student", this.name, "customer", customer.name)
        this.customer = customer.name

    def update_linked_customer(this):
        customer = frappe.get_doc("Customer", this.customer)
        if this.customer_group:
            customer.customer_group = this.customer_group
        customer.customer_name = this.student_name
        customer.image = this.get("image")
        customer.save(ignore_permissions=True)

    StudentController.create_customer = create_customer
    StudentController.update_linked_customer = update_linked_customer
    try:
        yield
    finally:
        StudentController.create_customer = original_create
        StudentController.update_linked_customer = original_update


def _open_decision_for_applicant(applicant_name):
    """An open journey on this applicant: an unconsumed active decision.

    Converted Approved decisions stay Approved forever, so bare
    activity never expires; openness (active AND no linked native
    Student) is what blocks a new journey. Native Student Applicant
    email is unique, so one applicant IS one subject — no wider join
    is ever needed.
    """
    return frappe.db.sql(
        "select name from `tabTH Admission Decision` where student_applicant=%s "
        "and status in ('Draft','Review','Approved','Conditional') "
        "and ifnull(native_student,'')='' for update",
        (applicant_name,),
        as_dict=True,
    )


@frappe.whitelist(methods=["POST"])
def deny_enroll_student(source_name=None):
    """A13 containment: native enroll_student is not an Admission API."""
    from toefl_house.security import require_operational
    require_operational()
    raise frappe.PermissionError(
        "Native enroll_student is contained; enrollment is not part of Admission")


@frappe.whitelist(methods=["POST"])
def record_applicant(request_key, placement_decision, first_name, program, academic_year):
    def work(actor):
        row = _placement_row(placement_decision)
        _unexpired(row)
        subject = _placement_subject(row)
        first = _name(first_name, "First name")
        # D16 mirror: synthetic sites accept only marked fixture names;
        # production accepts real bounded names and refuses test markers.
        if is_production():
            if first.startswith("SYN-") or first.startswith("SYNTHETIC"):
                raise frappe.ValidationError("Test-fixture applicant names are not accepted on the production site")
        elif not first.startswith("SYNTHETIC"):
            raise frappe.ValidationError("Only explicitly synthetic applicant names are accepted")
        program_name = _name(program, "Program")
        year_name = _name(academic_year, "Academic Year")
        if not frappe.db.exists(PROGRAM, program_name):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, year_name):
            raise frappe.ValidationError("Unknown academic year")
        # BUG-ADM-01: serialize concurrent intake on the placement case row.
        # The subject is unique per case, so same-subject contenders always
        # share this row even across different decisions; the locking probe
        # then observes the winner's applicant on every isolation level.
        case_name = frappe.db.get_value(ATTEMPT, row.attempt, "case_name")
        if not case_name:
            raise frappe.ValidationError("Placement decision is missing its attempt case")
        frappe.db.sql("select name from `tabTH Placement Case` where name=%s for update",
                      (case_name,))
        prior = frappe.db.sql("select name from `tabStudent Applicant` "
                               "where student_email_id=%s for update", (subject,),
                               as_dict=True)
        if prior:
            # OD-NEW-01/B: native applicant email is unique, so a
            # returning student re-sitting placement REUSES their one
            # applicant row; the new decision (not a new applicant) is
            # the per-journey vehicle. Fail-closed three ways — no
            # policy, no governing version, retired policy — plus a
            # fourth: the previous journey must be consumed
            # (converted), never mid-flight. All of this runs under the
            # BUG-ADM-01 case-row lock above.
            if returning_policies.governing_returning_mode() != "placement_per_term":
                raise frappe.ValidationError(
                    "Applicant already exists for this placement subject")
            if _open_decision_for_applicant(prior[0]["name"]):
                raise frappe.ValidationError(
                    "This subject has an open admission journey; a returning "
                    "journey starts only after the previous journey converts")
            applicant = frappe.get_doc(APPLICANT, prior[0]["name"])
            if int(applicant.paid or 0):
                raise frappe.ValidationError("Paid applicants are not an admission substitute")
            result = {
                "name": applicant.name,
                "student_email_id": subject,
                "program": applicant.program,
                "academic_year": applicant.academic_year,
                "application_status": applicant.application_status or "Applied",
                "paid": int(applicant.paid or 0),
                "placement_decision": row.name,
                "reused": True,
            }
            return result, dict(target=applicant.name,
                                after_hash=digest([applicant.name, subject, row.name]))
        applicant = frappe.get_doc(dict(
            doctype=APPLICANT,
            first_name=first,
            last_name="Applicant",
            student_email_id=subject,
            program=program_name,
            academic_year=year_name,
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
            "program": program_name,
            "academic_year": year_name,
            "application_status": applicant.application_status or "Applied",
            "paid": int(applicant.paid or 0),
            "placement_decision": row.name,
            "reused": False,
        }
        return result, dict(target=applicant.name, after_hash=digest([applicant.name, subject, program_name]))

    return _execute("record_applicant", request_key,
                    {"placement_decision": placement_decision, "first_name": first_name,
                     "program": program, "academic_year": academic_year}, work)


@frappe.whitelist(methods=["POST"])
def create_admission(request_key, student_applicant, placement_decision, existing_student="",
                     program="", academic_year="", academic_term=""):
    def work(actor):
        applicant_name = _name(student_applicant, "Student Applicant")
        frappe.db.sql("select name from `tabStudent Applicant` where name=%s for update",
                      (applicant_name,))
        try:
            applicant = frappe.get_doc(APPLICANT, applicant_name)
        except frappe.DoesNotExistError as exc:
            raise frappe.ValidationError("Student Applicant not found") from exc
        native_status = applicant.application_status or "Applied"
        if native_status == "Admitted" and not existing_student:
            raise frappe.ValidationError(
                "Admitted applicants convert through their existing Student; "
                "declare it to open a returning journey")
        if native_status not in ("Applied", "Admitted"):
            raise frappe.ValidationError("Applicant is not in Applied status")
        if int(applicant.paid or 0):
            raise frappe.ValidationError("Paid applicants are not an admission substitute")
        if (program or academic_year or academic_term) and not existing_student:
            raise frappe.ValidationError(
                "Journey program is declared only for returning admissions")
        journey_program = _name(program, "Program") if program else applicant.program
        journey_year = _name(academic_year, "Academic Year") if academic_year else applicant.academic_year
        journey_term = _name(academic_term, "Academic Term") if academic_term else (applicant.get("academic_term") or "")
        if not frappe.db.exists(PROGRAM, journey_program):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, journey_year):
            raise frappe.ValidationError("Unknown academic year")
        if journey_term and not frappe.db.exists(TERM, journey_term):
            raise frappe.ValidationError("Unknown academic term")
        row = _placement_row(placement_decision)
        _unexpired(row)
        subject = _placement_subject(row)
        if (applicant.student_email_id or "") != subject:
            raise frappe.ValidationError("Placement subject does not match the native applicant")
        returning = None
        if existing_student:
            returning = _name(existing_student, "Existing Student")
            linked_email = frappe.db.get_value(STUDENT, returning, "student_email_id")
            if linked_email is None:
                raise frappe.ValidationError("Existing Student not found")
            if (linked_email or "") != (applicant.student_email_id or ""):
                raise frappe.ValidationError(
                    "Existing Student does not belong to this applicant")
        if _open_decision_for_applicant(applicant_name):
            raise frappe.ValidationError("Applicant already has an open admission decision")
        linked = frappe.db.sql(
            "select name from `tabTH Admission Decision` where placement_decision=%s "
            "and status in ('Draft','Review','Approved','Conditional') for update",
            (row.name,), as_dict=True)
        if linked:
            raise frappe.ValidationError("Placement decision is already attached to an active admission")
        doc = frappe.get_doc(dict(
            doctype=DECISION_DT, student_applicant=applicant_name,
            program=journey_program, academic_year=journey_year,
            academic_term=journey_term or None,
            placement_decision=row.name, existing_student=returning,
            status="Draft", version=1, drafted_by=actor, accepted=0, synthetic=record_synthetic_flag(),
        ))
        doc.insert(ignore_permissions=True)
        result = _result(doc)
        return result, dict(target=doc.name, after_hash=digest([doc.name, applicant_name, row.name]))

    return _execute("create_admission", request_key,
                    {"student_applicant": student_applicant,
                     "placement_decision": placement_decision,
                     "existing_student": existing_student or "",
                     "program": program or "",
                     "academic_year": academic_year or "",
                     "academic_term": academic_term or ""}, work)


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
            outcome_reason = validate_admission_text(reason, "reason")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        recorded_conditions = ""
        if outcome == "Conditional":
            try:
                recorded_conditions = validate_admission_text(conditions, "conditions")
            except ValueError as exc:
                raise frappe.ValidationError(str(exc)) from exc
        elif conditions not in ("", None):
            raise frappe.ValidationError("Conditions are only recorded for Conditional outcomes")
        if outcome in ("Approved", "Conditional"):
            row = _placement_row(doc.placement_decision)
            _unexpired(row)
        decided_at = _now()
        _advance(doc, outcome, decided_by=actor, decided_at=decided_at,
                 outcome_reason=outcome_reason, conditions=recorded_conditions)
        result = _result(doc)
        result["decided_by"] = actor
        result["decided_at"] = _iso(decided_at)
        result["outcome_reason"] = outcome_reason
        return result, dict(target=doc.name, after_hash=digest([doc.name, outcome, actor]))

    return _execute("decide_admission", request_key,
                    {"name": name, "expected_version": expected_version,
                     "outcome": outcome, "reason": reason,
                     "conditions": conditions or ""}, work)


@frappe.whitelist(methods=["POST"])
def satisfy_conditions(request_key, name, expected_version, evidence):
    """Declare a Conditional decision's conditions met (S6, OD-NEW-02).

    Conditional → Approved with the conditions cleared, so the normal
    accept/convert path proceeds. The lattice rule is independent
    verification: the satisfier must be an Admission Approver OTHER than
    the deciding approver (mirroring reviewer≠decider and
    officer≠converter), and the evidence note is mandatory — no format is
    imposed on it. The placement decision must still be unexpired, as at
    every forward step. History is preserved: the audit event chains the
    transition and the satisfied_by/at/evidence fields record the act.
    """
    def work(actor):
        doc = _locked_decision(name, expected_version)
        if doc.status != "Conditional":
            raise frappe.ValidationError(
                "Only Conditional decisions can have their conditions satisfied")
        if actor == doc.decided_by:
            raise frappe.PermissionError(
                "The deciding approver cannot verify their own conditions; "
                "ask another Admission Approver")
        try:
            clean_evidence = validate_admission_text(evidence, "evidence")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        row = _placement_row(doc.placement_decision)
        _unexpired(row)
        satisfied_at = _now()
        _advance(doc, "Approved", satisfied_by=actor,
                 satisfied_at=satisfied_at,
                 satisfaction_evidence=clean_evidence, conditions="")
        result = _result(doc)
        result["satisfied_by"] = actor
        result["satisfied_at"] = _iso(satisfied_at)
        result["satisfaction_evidence"] = clean_evidence
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Approved", actor]))

    return _execute("satisfy_conditions", request_key,
                    {"name": name, "expected_version": expected_version,
                     "evidence": evidence}, work)


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
            recorded_reason = validate_admission_text(reason, "reason")
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        _advance(doc, "Withdrawn", outcome_reason=recorded_reason)
        result = _result(doc)
        result["outcome_reason"] = recorded_reason
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
        returning = doc.existing_student or ""
        if actor == doc.drafted_by:
            raise frappe.PermissionError("Officer cannot convert their own draft")
        if actor == doc.reviewed_by:
            raise frappe.PermissionError("Reviewer cannot convert this admission")
        row = _placement_row(doc.placement_decision)
        _unexpired(row)
        applicant = frappe.db.get_value(
            APPLICANT, doc.student_applicant,
            ["name", "first_name", "last_name", "student_email_id", "application_status"],
            as_dict=True,
        )
        if not applicant:
            raise frappe.ValidationError("Student Applicant not found")
        convert_status = applicant.application_status or "Applied"
        if convert_status == "Admitted" and not returning:
            raise frappe.ValidationError(
                "Admitted applicants convert through their existing Student; "
                "declare it to open a returning journey")
        if convert_status not in ("Applied", "Admitted"):
            raise frappe.ValidationError("Applicant is not in Applied status")
        if returning:
            # Returning lane: LINK the existing Student — one already
            # exists for this applicant BY CONSTRUCTION (it was created
            # by the previous journey and the officer declared it), so
            # the duplicate-Student guard below must not run here. The
            # branch itself verifies the link (existence, enabled,
            # email match) and refuses same-intake double enrollment.
            # Returning lane: LINK the existing Student, never create one.
            # Native Student.student_email_id is unique, so a second
            # Student for this person cannot exist; the email match below
            # proves the officer-linked Student IS this applicant, and the
            # existing Customer (with its invoice history) carries over
            # structurally — no new Customer row is created.
            linked = frappe.db.get_value(
                STUDENT, returning,
                ["name", "student_email_id", "enabled", "customer"],
                as_dict=True,
            )
            if not linked:
                raise frappe.ValidationError("Existing Student not found")
            if not int(linked.enabled or 0):
                raise frappe.ValidationError("Existing Student is disabled")
            if (linked.student_email_id or "") != (applicant.student_email_id or ""):
                raise frappe.ValidationError(
                    "Existing Student does not belong to this applicant")
            if frappe.db.sql(
                    "select name from `tabProgram Enrollment` where student=%s "
                    "and program=%s and academic_year=%s "
                    "and ifnull(academic_term,'')=%s and docstatus<2",
                    (linked.name, doc.program, doc.academic_year,
                     doc.academic_term or "")):
                raise frappe.ValidationError("Student is already enrolled")
            student_name = linked.name
            customer = linked.customer or frappe.db.get_value(STUDENT, student_name, "customer")
        else:
            # First-time lane only: no Student may already point at this
            # applicant, otherwise this would double-convert one person.
            if frappe.db.exists(STUDENT, {"student_applicant": applicant.name}):
                raise frappe.ValidationError("A native Student already exists for this applicant")
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
            student.flags.ignore_permissions = True
            student.flags.ignore_links = True
            with _native_student_write():
                student.insert(ignore_permissions=True)
            if frappe.db.exists("Program Enrollment", {"student": student.name}):
                raise frappe.ValidationError("Student conversion must not create Program Enrollment")
            student_name = student.name
            customer = student.customer or frappe.db.get_value(STUDENT, student.name, "customer")
            if customer and frappe.db.exists("Sales Invoice", {"customer": customer}):
                raise frappe.ValidationError("Student conversion must not create a Sales Invoice")
        converted_at = _now()
        _advance(doc, native_student=student_name, converted_at=converted_at)
        native_status = frappe.db.get_value(APPLICANT, applicant.name, "application_status")
        result = _result(doc)
        result["native_student"] = student_name
        result["native_application_status"] = native_status
        result["customer"] = customer or ""
        result["returning"] = bool(returning)
        result["program_enrollment"] = 0
        result["converted_at"] = _iso(converted_at)
        return result, dict(target=doc.name, after_hash=digest([doc.name, student_name]))

    return _execute("convert_applicant", request_key,
                    {"name": name, "expected_version": expected_version}, work)
