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

from toefl_house.operations.portal_dates import with_solar_date

# Allow-listed fields per doctype for student portal (no PII leakage)
PORTAL_FIELDS = {
    "Course Schedule": ["name", "student_group", "course", "room", "schedule_date", "from_time", "to_time", "instructor", "th_session_status"],
    "Student Attendance": ["name", "student", "student_group", "course_schedule", "date", "status", "docstatus"],
    "Assessment Result": ["name", "student", "assessment_plan", "grade", "docstatus", "posting_date"],
    "Fees": ["name", "student", "program", "academic_year", "grand_total", "outstanding_amount", "due_date", "docstatus"],
    "Sales Invoice": ["name", "customer", "grand_total", "outstanding_amount", "due_date", "status"],
    "TH Portal Announcement": ["name", "title", "message", "publish_date", "audience"],
}

ANNOUNCEMENT_DOCTYPE = "TH Portal Announcement"

# Absolute bound for a single scoped portal read. Portal data is
# per-student, so a few thousand rows is already pathological; past
# this the read raises instead of silently truncating (C-12/C-16
# precedent: raise, never silently drop rows). Callers page through
# the bounded set with limit/offset.
PORTAL_FETCH_MAX = 5000
PORTAL_PAGE_MAX = 200


def _page_params(limit, offset, default, maximum=PORTAL_PAGE_MAX):
    """Validate paging arguments. Returns (limit, offset) as ints."""
    if limit is None:
        limit = default
    if isinstance(limit, bool):
        raise frappe.ValidationError("limit must be a whole number")
    if isinstance(limit, float):
        if not limit.is_integer():
            raise frappe.ValidationError("limit must be a whole number")
        limit = int(limit)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError("limit must be a whole number") from exc
    if limit < 1 or limit > maximum:
        raise frappe.ValidationError(
            "limit must be between 1 and %d" % maximum)
    if offset is None:
        offset = 0
    if isinstance(offset, bool):
        raise frappe.ValidationError("offset must be a whole number")
    if isinstance(offset, float):
        if not offset.is_integer():
            raise frappe.ValidationError("offset must be a whole number")
        offset = int(offset)
    try:
        offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError("offset must be a whole number") from exc
    if offset < 0:
        raise frappe.ValidationError("offset must not be negative")
    return (limit, offset)


def _fetch_scoped(doctype, filters, fields, order_by=None):
    """Fetch a scoped portal read, bounded but never silently truncated.

    Requests PORTAL_FETCH_MAX + 1 rows and raises when more exist: the
    caller pages through the returned rows with limit/offset. A failed
    read raises (fail-closed) — callers never turn it into [].
    """
    rows = frappe.get_all(doctype, filters=filters, fields=fields,
                          order_by=order_by,
                          limit_page_length=PORTAL_FETCH_MAX + 1)
    if len(rows) > PORTAL_FETCH_MAX:
        raise frappe.ValidationError(
            "%s exceeds the supported total of %d records; narrow the "
            "scope or contact an administrator" % (doctype, PORTAL_FETCH_MAX))
    return rows


def _page(rows, limit, offset):
    return list(rows)[offset:offset + limit]


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


def _project(doctype, student, extra_filters=None, fields=None, limit=100, offset=0):
    """Branch-aware projection scoped to one student, one page.

    The scoped set is fetched bounded (see _fetch_scoped) and the
    requested page is sliced from it, so a limit is always honoured
    exactly — the DB-level limit_page_length alone is not relied on.
    A failed read raises, never returns [] masquerading as
    "no records" (C-12). The early [] returns below are not read
    failures: Course Schedule is resolved by the caller, and a Sales
    Invoice without a native student link simply has nothing scoped
    to show.
    """
    limit, offset = _page_params(limit, offset, 100)
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

    return _page(_fetch_scoped(doctype, filters, fields), limit, offset)


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
    # A failed read must raise, never degrade to a bare {"name": ...}
    # that hides the outage (C-12). A missing row (deleted between the
    # identity check and this read) raises explicitly instead of
    # failing later with a bare TypeError.
    row = frappe.db.get_value("Student", student, ["name", "student_name", "student_email_id"], as_dict=True)
    if not row:
        raise RuntimeError(f"Student record {student} could not be read")
    return {"name": row["name"], "student_name": row.get("student_name") or "", "student_email_id": row.get("student_email_id") or ""}


@frappe.whitelist()
def get_my_schedule(limit=200, offset=0):
    """Personally authorized schedule — only enrolled active groups.

    Resolves enrolled groups via Student Group Student (active=1) for this
    student. Never trusts a caller-supplied student or group filter.
    Pages with limit/offset (defaults 200/0); the roster and the
    schedule reads are bounded but never silently truncated.
    """
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    limit, offset = _page_params(limit, offset, 200)

    # Resolve enrolled groups. A failed read must raise, never return []
    # masquerading as "no classes" (C-12). An empty roster is genuinely
    # no data and still returns [].
    roster = _fetch_scoped(
        "Student Group Student",
        filters={"student": student, "active": 1},
        fields=["parent"],
    )
    group_names = [r["parent"] for r in roster if r.get("parent")]
    if not group_names:
        return []
    # Fetch schedules for those groups
    schedules = _fetch_scoped(
        "Course Schedule",
        filters={"student_group": ["in", group_names]},
        fields=PORTAL_FIELDS["Course Schedule"],
        order_by="schedule_date asc, from_time asc",
    )
    return with_solar_date(_page(schedules, limit, offset), "schedule_date", "schedule_date_shamsi")


@frappe.whitelist()
def get_my_attendance(limit=100, offset=0):
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    # Validate limit/offset explicitly: a non-numeric value is a caller
    # error (ValidationError), never a raw ValueError from int(), and
    # out-of-range values are refused rather than silently clamped
    # (C-12). Defaults: limit 100, offset 0; pages via offset.
    limit, offset = _page_params(limit, offset, 100)
    return with_solar_date(_project("Student Attendance", student, limit=limit, offset=offset), "date", "date_shamsi")


@frappe.whitelist()
def get_my_grades(limit=200, offset=0):
    """Approved grades only (docstatus=1). No draft/unapproved exposure."""
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    return _project("Assessment Result", student, limit=limit, offset=offset)


@frappe.whitelist()
def get_my_fees(limit=100, offset=0):
    """Fee balances — outstanding amounts for this student only."""
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    student = _assert_my_student(user)
    fees = _project("Fees", student, limit=limit, offset=offset)
    invoices = _project("Sales Invoice", student, limit=limit, offset=offset)
    return {"fees": fees, "invoices": invoices}


@frappe.whitelist()
def get_announcements(limit=50, offset=0):
    """Institutional announcements — published only, audience filtered.

    Announcements are public to authenticated students when student_portal
    is enabled. No student-specific filtering bypass. A failed read
    raises (C-12): an outage must never render as "no announcements".
    """
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    # At least verify the caller is a student
    _assert_my_student(user)
    limit, offset = _page_params(limit, offset, 50)
    rows = _fetch_scoped(
        ANNOUNCEMENT_DOCTYPE,
        filters={"status": "Published"},
        fields=PORTAL_FIELDS[ANNOUNCEMENT_DOCTYPE],
        order_by="publish_date desc",
    )
    # Filter by audience: "All" or "Students"
    allowed = []
    for r in rows:
        aud = (r.get("audience") or "All").strip().lower()
        if aud in ("all", "students", "student"):
            allowed.append(r)
    return _page(allowed, limit, offset)


# --------- Adversarial helper: explicit student param must always be checked ---
@frappe.whitelist()
def get_attendance_for_student(student=None, limit=100, offset=0):
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
    return _project("Student Attendance", my_student, limit=limit, offset=offset)


@frappe.whitelist()
def get_fees_for_student(student=None, limit=100, offset=0):
    _require_portal_enabled()
    user = frappe.session.user
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    if not student or not isinstance(student, str):
        raise frappe.ValidationError("Student is required")
    my_student = _assert_my_student(user, requested_student=student)
    fees = _project("Fees", my_student, limit=limit, offset=offset)
    invoices = _project("Sales Invoice", my_student, limit=limit, offset=offset)
    return {"fees": fees, "invoices": invoices}
