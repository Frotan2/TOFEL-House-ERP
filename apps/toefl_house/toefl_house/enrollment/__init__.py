"""Thin enrollment commands over native Education Program Enrollment.

Native Program Enrollment is the registration ledger. This module does not
own a TH Enrollment Request, roster, invoice, attendance or payroll record.
"""
from contextlib import contextmanager
import frappe
from toefl_house.admission import (
    DECISION_DT, PROGRAM, STUDENT, YEAR, _name, _placement_row, _unexpired,
)
from toefl_house.api import _execute
from toefl_house.policy import digest, enrollment_is_eligible
from toefl_house.security import enrollment_command_active, finance_command_active, require_operational

PE = "Program Enrollment"
CE = "Course Enrollment"


@contextmanager
def _native_enrollment_write():
    """Course Enrollment.save during PE submit has no ignore_permissions.

    Do not patch frappe.has_permission or call set_user: both persist onto the
    Enrollment Officer SID on gunicorn workers.
    """
    from education.education.doctype.course_enrollment.course_enrollment import (
        CourseEnrollment,
    )
    original_save = CourseEnrollment.save

    def save(this, *args, **kwargs):
        this.flags.ignore_permissions = True
        this.flags.ignore_links = True
        kwargs["ignore_permissions"] = True
        return original_save(this, *args, **kwargs)

    CourseEnrollment.save = save
    try:
        yield
    finally:
        CourseEnrollment.save = original_save


def guard_program_enrollment(doc, method=None):
    require_operational()
    if enrollment_command_active():
        return
    raise frappe.ValidationError("Program Enrollment requires an authorized enrollment command")


def guard_course_enrollment(doc, method=None):
    require_operational()
    if enrollment_command_active():
        return
    raise frappe.ValidationError("Course Enrollment requires an authorized enrollment command")


def deny_premature_invoice(doc, method=None):
    require_operational()
    if finance_command_active("Sales Invoice"):
        # Governed finance commands (issue_placement_fee and the invoice-correction
        # approval that posts the credit note) carry their own billing validations;
        # the guard blocks out-of-band invoices only. Without this exemption no
        # converted student could ever be billed or corrected (BUG-INV-01).
        return
    customer = getattr(doc, "customer", None)
    if not customer:
        return
    students = frappe.get_all(STUDENT, filters={"customer": customer}, pluck="name")
    if students and frappe.db.exists(DECISION_DT, {"native_student": ["in", students]}):
        raise frappe.ValidationError("Premature billing is denied for admission-converted students")


def _locked_admission(name):
    applicant = frappe.db.get_value(DECISION_DT, name, "student_applicant")
    if not applicant:
        raise frappe.ValidationError("Admission decision not found")
    frappe.db.sql("select name from `tabStudent Applicant` where name=%s for update", (applicant,))
    frappe.db.sql("select name from `tabTH Admission Decision` where name=%s for update", (name,))
    row = frappe.db.get_value(
        DECISION_DT, name,
        ["name", "student_applicant", "program", "academic_year", "academic_term",
         "placement_decision", "existing_student", "status", "accepted", "conditions",
         "native_student", "drafted_by", "reviewed_by", "decided_by"],
        as_dict=True,
    )
    if not row:
        raise frappe.ValidationError("Admission decision not found")
    return row


def _existing_enrollment(student, program, year, term):
    return frappe.db.sql(
        "select name from `tabProgram Enrollment` where student=%s and program=%s "
        "and academic_year=%s and ifnull(academic_term,'')=%s and docstatus<2 for update",
        (student, program, year, term or ""),
        as_dict=True,
    )


@frappe.whitelist(methods=["POST"])
def enroll_in_program(request_key, admission_decision):
    def work(actor):
        name = _name(admission_decision, "Admission decision")
        row = _locked_admission(name)
        try:
            enrollment_is_eligible(
                row.status, row.accepted, row.native_student,
                row.existing_student or "", row.conditions or "",
            )
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if actor in {row.drafted_by, row.reviewed_by, row.decided_by}:
            raise frappe.PermissionError("Admission actors cannot enroll this student")
        placement = _placement_row(row.placement_decision)
        _unexpired(placement)
        student = row.native_student
        frappe.db.sql("select name from `tabStudent` where name=%s for update", (student,))
        linked = frappe.db.get_value(STUDENT, student, ["name", "student_applicant", "customer"], as_dict=True)
        if not linked:
            raise frappe.ValidationError("Native Student not found")
        if row.existing_student:
            # Returning lane: the Student keeps its ORIGINAL applicant
            # link (native history is never rewritten); identity was
            # proven at convert by email match, so here the linkage
            # itself is verified instead.
            if linked.name != row.existing_student:
                raise frappe.ValidationError("Student does not match the returning admission")
        elif (linked.student_applicant or "") != row.student_applicant:
            raise frappe.ValidationError("Student does not match the admission applicant")
        if not frappe.db.exists(PROGRAM, row.program):
            raise frappe.ValidationError("Unknown program")
        if not frappe.db.exists(YEAR, row.academic_year):
            raise frappe.ValidationError("Unknown academic year")
        from toefl_house.academic import catalog_linkage as linkage
        try:
            linkage.check_intake_open(row.program)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if _existing_enrollment(student, row.program, row.academic_year, row.academic_term):
            raise frappe.ValidationError("Student is already enrolled")
        customer = linked.customer or frappe.db.get_value(STUDENT, student, "customer")
        # BUG-ENR-02: snapshot before the native submit so only invoices CREATED
        # by this enrollment are refused; a linked customer with older history
        # (e.g. a unified walk-in payer record) must not block enrollment.
        billed_before = set(frappe.get_all(
            "Sales Invoice", filters={"customer": customer}, pluck="name")) if customer else set()
        pe = frappe.get_doc(dict(
            doctype=PE,
            student=student,
            program=row.program,
            academic_year=row.academic_year,
            academic_term=row.academic_term or None,
            enrollment_date=frappe.utils.today(),
        ))
        pe.flags.ignore_permissions = True
        pe.flags.ignore_links = True
        pe.insert(ignore_permissions=True)
        pe.flags.ignore_permissions = True
        pe.flags.ignore_links = True
        with _native_enrollment_write():
            pe.submit()
        if int(pe.docstatus or 0) != 1:
            raise frappe.ValidationError("Program Enrollment must be submitted")
        if customer:
            billed_after = set(frappe.get_all(
                "Sales Invoice", filters={"customer": customer}, pluck="name"))
            if billed_after - billed_before:
                raise frappe.ValidationError("Enrollment must not create a Sales Invoice")
        course_count = frappe.db.count(CE, {"program_enrollment": pe.name})
        result = {
            "admission_decision": name,
            "student": student,
            "program": row.program,
            "academic_year": row.academic_year,
            "program_enrollment": pe.name,
            "docstatus": int(pe.docstatus),
            "course_enrollments": int(course_count),
            "sales_invoice": 0,
        }
        return result, dict(target=pe.name, after_hash=digest([pe.name, student, row.program]))

    return _execute("enroll_in_program", request_key,
                    {"admission_decision": admission_decision}, work)
