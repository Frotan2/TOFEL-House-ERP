"""Apply native Branch/Company scope before guarded writes and receipt replay."""
import frappe


REFERENCES = {
    "student_group": "Student Group", "from_group": "Student Group",
    "to_group": "Student Group", "course_schedule": "Course Schedule",
    "session": "Course Schedule",
    "student": "Student", "student_applicant": "Student Applicant",
    "admission_decision": "TH Admission Decision",
    "program_enrollment": "Program Enrollment", "attendance": "Student Attendance",
    "transfer": "TH Class Transfer", "exit": "TH Enrollment Exit",
    "assignment": "TH Teaching Assignment", "override": "TH Capacity Approval",
    "suspension": "TH Class Suspension", "waiting": "TH Class Waiting List",
}
ADMISSION_NAMES = frozenset({
    "review_admission", "decide_admission", "satisfy_conditions", "accept_offer",
    "withdraw_admission", "revoke_admission", "expire_admission", "convert_applicant",
})
RESULT_NAMES = {
    "create_student_group": "Student Group", "record_applicant": "Student Applicant",
    "create_admission": "TH Admission Decision", "schedule_session": "Course Schedule",
    "assign_teaching_skill": "TH Teaching Assignment",
}
COMPANY_REFERENCES = {
    "payment_entry": "Payment Entry", "counter_account": "Account",
    "fee_structure": "Fee Structure", "fees": "Fees", "invoice": "Sales Invoice",
    "sales_invoice": "Sales Invoice",
    "employee": "Employee", "salary_slip": "Salary Slip", "payroll_entry": "Payroll Entry",
    "contract": "TH Instructor Contract", "supersedes": "TH Instructor Contract",
    "assignment": "TH Teaching Assignment", "credit_note": "Sales Invoice",
}


CORRECTION_COMMANDS = frozenset({
    "approve_invoice_correction", "deny_invoice_correction",
    "approve_fees_correction", "deny_fees_correction",
})


def _reference_company(doctype, name):
    """Resolve Company through the native teaching contract and its employee."""
    if doctype == "TH Teaching Assignment":
        contract = frappe.db.get_value(doctype, name, "contract")
        return _reference_company("TH Instructor Contract", contract) if contract else None
    if doctype == "TH Instructor Contract":
        employee = frappe.db.get_value(doctype, name, "employee")
        return frappe.db.get_value("Employee", employee, "company") if employee else None
    return frappe.db.get_value(doctype, name, "company")


def _authorize_company_scope(kind, payload, actor, result):
    sources = [payload] + ([result] if isinstance(result, dict) else [])
    if kind == "accept_reception_handover" and payload.get("payment_entries"):
        from toefl_house.finance.collection_rules import receipt_names
        try:
            names = receipt_names(payload["payment_entries"])
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        sources += [{"payment_entry": name} for name in names]
    if not (kind in CORRECTION_COMMANDS and payload.get("request")) and not any(
        any(source.get(field) for field in ("company", *COMPANY_REFERENCES))
        for source in sources
    ):
        return
    allowed = frappe.get_all("User Permission", filters={"user": actor, "allow": "Company"},
                             pluck="for_value", limit_page_length=100)
    if not allowed:
        return
    companies = set()
    for source in sources:
        if source.get("company"):
            if not isinstance(source["company"], str) or len(source["company"]) > 140:
                raise frappe.PermissionError("The command company must resolve to a permitted company")
            companies.add(source["company"])
        for field, doctype in COMPANY_REFERENCES.items():
            name = source.get(field)
            if isinstance(name, str) and name:
                company = _reference_company(doctype, name)
                if not company:
                    # A dangling or Company-less native document must never
                    # make a cached financial receipt accessible by default.
                    raise frappe.PermissionError("The referenced document Company cannot be resolved")
                companies.add(company)
    if kind in CORRECTION_COMMANDS:
        request = payload.get("request")
        if not isinstance(request, str) or not request or len(request) > 140:
            raise frappe.PermissionError("A scoped correction request is required")
        invoice = frappe.db.get_value("TH Correction Request", request, "sales_invoice")
        fee = frappe.db.get_value("TH Correction Request", request, "fees")
        if not invoice and not fee:
            raise frappe.PermissionError("The correction Company's source is unavailable")
        for doctype, name in (("Sales Invoice", invoice), ("Fees", fee)):
            if name:
                company = _reference_company(doctype, name)
                if not company:
                    raise frappe.PermissionError("The correction Company cannot be resolved")
                companies.add(company)
    if not companies <= set(allowed):
        raise frappe.PermissionError("The command target is outside this login's permitted companies")


def actor_branches(actor):
    rows = frappe.get_all("User Permission", filters={"user": actor, "allow": "Branch"},
                          pluck="for_value", limit_page_length=100)
    return set(rows) if rows else None


def resolve_creation_branch(branch, actor):
    allowed = actor_branches(actor)
    if allowed is None:
        return branch or ""
    if not branch and len(allowed) == 1:
        return next(iter(allowed))
    if not branch or branch not in allowed:
        raise frappe.PermissionError("Choose a branch permitted for this login")
    return branch


def _require_document(doctype, name, allowed):
    if not isinstance(name, str) or not name or len(name) > 140:
        raise frappe.PermissionError("The command target must resolve to a permitted branch")
    doc = frappe.get_doc(doctype, name)
    from toefl_house import permissions
    if doctype in ("Student", "Program Enrollment"):
        student = name if doctype == "Student" else doc.get("student")
        branches = _effective_student_branches(student)
    elif doctype in ("Course Schedule", "Student Attendance"):
        group = doc.get("student_group")
        branches = {frappe.db.get_value("Student Group", group, "th_branch")} if group else set()
    else:
        kind = permissions.BRANCH_KINDS[doctype]
        branches = (permissions._doc_branches(doc, kind)
                    if doctype in permissions.BRANCH_NATIVE_DOCTYPES
                    else permissions._doc_branches_guarded(doc, kind))
    if not branches or None in branches or not branches <= allowed:
        raise frappe.PermissionError("The command target is outside this login's permitted branches")


def _effective_student_branches(student):
    from toefl_house.permissions import _student_branches
    branches = _student_branches(student)
    if not branches:
        # Intake is the explicit authority before first placement. Once
        # rostered, current class membership remains authoritative.
        applicant = frappe.db.get_value("Student", student, "student_applicant")
        intake = frappe.db.get_value("Student Applicant", applicant, "th_branch") if applicant else None
        branches = {intake} if intake else set()
    return branches


def roster_for_branch(rows, branch):
    if not branch:
        return rows
    eligible = []
    for row in rows:
        student = row["student"]
        branches = _effective_student_branches(student)
        if branch in branches:
            eligible.append(row)
    return eligible


def authorize_command_scope(kind, payload, actor, *, result=None):
    _authorize_company_scope(kind, payload, actor, result)
    allowed = actor_branches(actor)
    if allowed is None:
        return
    if "branch" in payload:
        resolve_creation_branch(payload.get("branch"), actor)
    for field, doctype in REFERENCES.items():
        if payload.get(field):
            _require_document(doctype, payload[field], allowed)
    if kind in ADMISSION_NAMES and payload.get("name"):
        _require_document("TH Admission Decision", payload["name"], allowed)
    if kind in {"approve_attendance_correction", "deny_attendance_correction"} and payload.get("request"):
        _require_document("TH Attendance Correction Request", payload["request"], allowed)
    if kind in {"approve_fees_correction", "deny_fees_correction"} and payload.get("request"):
        _require_document("TH Correction Request", payload["request"], allowed)
    if kind in {"request_fees_correction", "record_reception_collection", "correct_reception_collection"} and payload.get("fees"):
        student = frappe.db.get_value("Fees", payload["fees"], "student")
        _require_document("Student", student, allowed)
    payments = [payload["payment_entry"]] if payload.get("payment_entry") else []
    if kind == "accept_reception_handover" and payload.get("payment_entries"):
        from toefl_house.finance.collection_rules import receipt_names
        try:
            payments += receipt_names(payload["payment_entries"])
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
    for name in payments:
        payment = frappe.get_doc("Payment Entry", name)
        if payment.party_type != "Student" or not payment.party:
            raise frappe.PermissionError("The receipt student branch cannot be resolved")
        _require_document("Student", payment.party, allowed)
    # Defaults can resolve differently after a User Permission changes. The
    # stored command result must be scoped again, even for a valid old key.
    if isinstance(result, dict):
        if kind in RESULT_NAMES and result.get("name"):
            _require_document(RESULT_NAMES[kind], result["name"], allowed)
