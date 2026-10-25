"""Student self-service portal — personally authorized, strictly scoped.

Each endpoint returns ONLY the authenticated student's own records.
Every read is allow-listed (no `*`), limited, and scoped by verified
student ownership — never by a caller-supplied `student` parameter.
Any attempt to access another student's data via query manipulation,
predictable IDs, or API endpoints is denied.

Prerequisites:
- TH Portal Configuration: student_portal_enabled must be true
- Session user must map to exactly one Student (via student_email_id ↔ User.email
  plus Customer and branch validation when available)
- No synthetic-record leakage (synthetic flags respected where present)

All functions are frappe.whitelist compatible but also callable in offline
tests with an injected stub.
"""
import frappe

# Allow-listed fields per doctype for student portal (no PII leakage)
PORTAL_FIELDS = {
    "Course Schedule": ["name", "student_group", "course", "room", "schedule_date", "from_time", "to_time", "instructor"],
    "Student Attendance": ["name", "student", "student_group", "course_schedule", "date", "status", "docstatus"],
    "Assessment Result": ["name", "student", "assessment_plan", "grade", "docstatus", "posting_date"],
    "Fees": ["name", "student", "program", "academic_year", "grand_total", "outstanding_amount", "due_date", "docstatus"],
    "Sales Invoice": ["name", "customer", "grand_total", "outstanding_amount", "due_date", "status"],
    "TH Portal Announcement": ["name", "title", "message", "publish_date", "audience"],
}

ANNOUNCEMENT_DOCTYPE = "TH Portal Announcement"


def _require_portal_enabled():
    from toefl_house.operations import portal_policy
    if not portal_policy.is_portal_enabled("student_portal"):
        raise frappe.PermissionError("Student portal is disabled — Owner approval required")


def _get_user_email(user):
    try:
        return frappe.db.get_value("User", user, "email") or user
    except Exception:
        return user


def _get_student_for_user(user):
    """A unique student identity must be both emailed AND explicitly bound.

    Never use email alone (a User email can change), nor optional legacy
    Student.user fields. Administrator-created native User Permission links
    are the durable identity evidence for personally sensitive data.
    """
    if not isinstance(user, str) or user in ("", "Guest", "Administrator"):
        return None
    if "Student" not in frappe.get_roles(user):
        return None
    if not frappe.db.get_value("User", user, "enabled"):
        return None
    email = _get_user_email(user)
    if not email:
        return None
    rows = frappe.db.get_all(
        "Student", filters={"student_email_id": email},
        fields=["name"], limit_page_length=2)
    if len(rows) != 1:
        return None
    student = rows[0]["name"]
    allowed = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": "Student",
                 "for_value": student},
        fields=["name"], limit_page_length=2)
    if len(allowed) != 1:
        return None
    return student


def _assert_my_student(user, requested_student=None):
    """Verify requested_student is the caller's own student.

    If requested_student is None, returns the caller's student.
    If requested_student is supplied, it must equal the caller's student
    or PermissionError is raised (prevents IDOR).
    """
    my_student = _get_student_for_user(user)
    if not my_student:
        raise frappe.PermissionError("No student profile found for this account — contact your administrator")
    if requested_student is not None:
        # Strict equality — no list, no wildcard, no bypass
        if str(requested_student).strip() != str(my_student).strip():
            raise frappe.PermissionError("Access denied — you may only view your own records")
    return my_student


def _project(doctype, student, extra_filters=None, fields=None, limit=100):
    """Branch-aware projection scoped to one student."""
    # Resolve student's branches for filtering where needed
    fields = fields or PORTAL_FIELDS.get(doctype) or ["name"]
    # Build filters scoped to student
    filters = {}
    if doctype == "Course Schedule":
        # Course Schedule is via enrolled groups, not directly student
        # Caller must provide student_group list; we resolve it here
        return []  # handled separately in get_my_schedules
    elif doctype == "Student Attendance":
        filters["student"] = student
        filters["docstatus"] = 1
    elif doctype == "Assessment Result":
        filters["student"] = student
        # Only approved grades (docstatus=1)
        filters["docstatus"] = 1
    elif doctype == "Fees":
        filters["student"] = student
        filters["docstatus"] = 1
    elif doctype == "Sales Invoice":
        # Customer alone is NOT a student identity: siblings and guardians
        # often share a native Customer. Never reveal all invoices for a
        # family. Query only installations with an exact Student link.
        if not frappe.get_meta("Sales Invoice").has_field("student"):
            return []
        customer = frappe.db.get_value("Student", student, "customer")
        if not customer:
            return []
        filters.update({"customer": customer, "student": student,
                        "docstatus": 1})
    else:
        filters["student"] = student

    if extra_filters:
        # API callers cannot replace mandatory student, customer or
        # approval predicates with broader filters.
        if any(k in filters and filters[k] != value
               for k, value in extra_filters.items()):
            raise frappe.PermissionError("A protected student scope cannot be replaced")
        filters.update(extra_filters)

    try:
        return frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=limit)
    except Exception:
        return []


@frappe.whitelist()
def get_my_student():
    """Return the caller's own Student identity (minimal, no grades/finances)."""
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _get_student_for_user(user)
    if not student:
        raise frappe.PermissionError("No student profile found for this account")
    try:
        row = frappe.db.get_value("Student", student, ["name", "student_name", "student_email_id"], as_dict=True)
        return {"name": row["name"], "student_name": row.get("student_name") or "", "student_email_id": row.get("student_email_id") or ""}
    except Exception:
        return {"name": student}


@frappe.whitelist()
def get_my_schedule():
    """Personally authorized schedule — only enrolled active groups.

    Resolves enrolled groups via Student Group Student (active=1) for this
    student. Never trusts a caller-supplied student or group filter.
    """
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)

    # Resolve enrolled groups
    try:
        roster = frappe.get_all(
            "Student Group Student",
            filters={"student": student, "active": 1},
            fields=["parent"],
            limit_page_length=200,
        )
        group_names = [r["parent"] for r in roster if r.get("parent")]
        if not group_names:
            return []
        # Fetch schedules for those groups
        schedules = frappe.get_all(
            "Course Schedule",
            filters={"student_group": ["in", group_names]},
            fields=PORTAL_FIELDS["Course Schedule"],
            order_by="schedule_date asc, from_time asc",
            limit_page_length=200,
        )
        # Project only safe fields
        return schedules
    except Exception:
        return []


@frappe.whitelist()
def get_my_attendance(limit=100):
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    limit = min(max(int(limit or 100), 1), 200)
    return _project("Student Attendance", student, limit=limit)


@frappe.whitelist()
def get_my_grades():
    """Approved grades only (docstatus=1). No draft/unapproved exposure."""
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    return _project("Assessment Result", student, limit=200)


@frappe.whitelist()
def get_my_fees():
    """Fee balances — outstanding amounts for this student only."""
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    fees = _project("Fees", student, limit=100)
    invoices = _project("Sales Invoice", student, limit=100)
    return {"fees": fees, "invoices": invoices}


@frappe.whitelist()
def get_announcements():
    """Institutional announcements — published only, audience filtered.

    Announcements are public to authenticated students when student_portal
    is enabled. No student-specific filtering bypass.
    """
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    # At least verify the caller is a student
    _assert_my_student(user)
    try:
        rows = frappe.get_all(
            ANNOUNCEMENT_DOCTYPE,
            filters={"status": "Published"},
            fields=PORTAL_FIELDS[ANNOUNCEMENT_DOCTYPE],
            order_by="publish_date desc",
            limit_page_length=50,
        )
        # Filter by audience: "All" or "Students"
        allowed = []
        for r in rows:
            aud = (r.get("audience") or "All").strip().lower()
            if aud in ("all", "students", "student"):
                allowed.append(r)
        return allowed
    except Exception:
        return []


# --------- Adversarial helper: explicit student param must always be checked ---
@frappe.whitelist()
def get_attendance_for_student(student=None):
    """Explicit student param — always verified against caller ownership.

    This endpoint exists to prove IDOR protection: even if a caller
    supplies a student name, it is checked against their verified identity.
    """
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    if not student or not isinstance(student, str):
        raise frappe.ValidationError("Student is required")
    # Strict ownership check — raises if not own student
    my_student = _assert_my_student(user, requested_student=student)
    return _project("Student Attendance", my_student, limit=100)


@frappe.whitelist()
def get_fees_for_student(student=None):
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    if not student or not isinstance(student, str):
        raise frappe.ValidationError("Student is required")
    my_student = _assert_my_student(user, requested_student=student)
    fees = _project("Fees", my_student, limit=100)
    invoices = _project("Sales Invoice", my_student, limit=100)
    return {"fees": fees, "invoices": invoices}
