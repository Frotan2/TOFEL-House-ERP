"""Seat truth, actionable waiting lists, authorized capacity overrides.

Capacity is the native ``Student Group.max_strength`` — this module never
introduces a second capacity field. What it adds is the operational truth the
native record cannot express on its own:

* **available seats** = capacity − every roster row − unexpired seat offers.
  Native Frappe counts every roster row (active or not) toward
  ``max_strength``, so the roster count here is the same total; a
  deactivated membership keeps its history and keeps occupying its native
  seat. Offers are this module's reservations: a seat promised to a
  wait-listed student cannot be silently taken by a walk-in.
* **waiting list**: one open entry per student per class, ordered by declared
  priority then request time, with an explicit seat offer that expires.
  Admission re-proves every fact under lock, so a stale offer cannot
  overfill a class.
* **override**: an extra seat granted by the policy-configured role for one
  named student, with a reason, an expiry and a single use. Every admission
  path that exceeds capacity must consume a matching Approved override —
  there is no unchecked bypass.

Reception and Academic staff read the availability projections; only the
Teaching Scheduler admits, and only the configured override role approves
more seats than the class was created with.
"""
from datetime import date, timedelta

import frappe

from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag
from toefl_house.teaching import class_operations

GROUP = "Student Group"
WAITING = "TH Class Waiting List"
OVERRIDE = "TH Capacity Approval"
ENROLLMENT = "Program Enrollment"
STUDENT = "Student"
ROSTER_TABLE = "Student Group Student"

WAITING_STATUSES = ("Waiting", "Offered", "Admitted", "Expired", "Withdrawn")
OPEN_WAITING_STATUSES = ("Waiting", "Offered")
OVERRIDE_STATUSES = ("Approved", "Used", "Revoked", "Expired")
CLASS_TERMINAL = ("Completed", "Cancelled")
REASON_LIMIT = 500
NAME_LIMIT = 140

# Who may read the seat projections. Reception answers "is there room?";
# Academic staff plan intakes; auditors verify; schedulers act.
AVAILABILITY_ROLES = (
    "Reception", "Academic Manager", "Teaching Scheduler", "Teaching Auditor",
    "General Manager", "Course Owner", "Enrollment Officer", "Enrollment Auditor",
)
MAX_CLASSES = 200
MAX_ENTRIES = 200


def _bounded(value, what):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > NAME_LIMIT:
        raise frappe.ValidationError(f"{what} is required")
    return value.strip()


def _reason(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > REASON_LIMIT:
        raise frappe.ValidationError(
            f"A reason is required (at most {REASON_LIMIT} characters)")
    return value.strip()


def _int(value, what, low, high):
    if isinstance(value, bool):
        raise frappe.ValidationError(f"{what} must be a whole number")
    if isinstance(value, str) and value.strip():
        try:
            value = int(value.strip())
        except (TypeError, ValueError) as exc:
            raise frappe.ValidationError(f"{what} must be a whole number") from exc
    if not isinstance(value, int) or not low <= value <= high:
        raise frappe.ValidationError(
            f"{what} must be a whole number between {low} and {high}")
    return value


def _today():
    return str(frappe.utils.today())


def available_seats(capacity, rostered, reserved):
    """Seats a walk-in may take right now (never negative)."""
    return max(0, int(capacity or 0) - int(rostered or 0) - int(reserved or 0))


def unexpired(offer_expires_on, on_date=None):
    """An offer is live through its expiry date, inclusive."""
    if not offer_expires_on:
        return False
    return str(offer_expires_on) >= str(on_date or _today())


def _lock(doctype, name):
    frappe.db.sql(
        f"select name from `tab{doctype}` where name=%s for update", (name,))


def _group_facts(group_name, for_update=False):
    if for_update:
        _lock(GROUP, group_name)
    facts = frappe.db.get_value(
        GROUP, group_name,
        ["name", "program", "academic_year", "academic_term", "max_strength",
         "disabled", "th_class_status", "th_delivery_mode", "th_branch",
         "th_class_start_date", "th_class_end_date"], as_dict=True)
    if facts is None:
        raise frappe.ValidationError(f"Unknown student group: {group_name}")
    return facts


def _require_open_class(group_name, facts):
    if int(facts.disabled or 0):
        raise frappe.ValidationError(f"Student group {group_name} is disabled")
    if facts.th_class_status in CLASS_TERMINAL:
        raise frappe.ValidationError(
            f"Student group {group_name} is {facts.th_class_status}; seats apply "
            "to Planned or Active classes only")


def _require_active_student(student):
    if not frappe.db.exists(STUDENT, student):
        raise frappe.ValidationError(f"Unknown student: {student}")
    if not frappe.db.get_value(STUDENT, student, "enabled"):
        raise frappe.ValidationError(
            f"Student {student} is disabled and cannot take a seat")


def require_matching_enrollment(student, facts, group_name):
    """The student must hold a submitted enrollment for the class intake.

    Identical semantics to the roster commands: program and year must match,
    and when the class names a term the enrollment must name the same term.
    """
    params = [student, facts.program, facts.academic_year]
    condition = ""
    if facts.academic_term:
        condition = " and academic_term=%s"
        params.append(facts.academic_term)
    rows = frappe.db.sql(
        "select name from `tabProgram Enrollment` where student=%s "
        "and program=%s and academic_year=%s and docstatus=1" + condition,
        tuple(params))
    if not rows:
        intake = f"{facts.program} {facts.academic_year}"
        if facts.academic_term:
            intake += f" {facts.academic_term}"
        raise frappe.ValidationError(
            f"Student {student} is not enrolled in {intake}; only enrolled "
            f"students can take a seat in {group_name}")
    return rows[0][0] if isinstance(rows[0], (list, tuple)) else rows[0].get("name")


def _roster_status(group_name, student):
    rows = frappe.db.sql(
        "select active from `tabStudent Group Student` where parent=%s and student=%s",
        (group_name, student), as_dict=True)
    if not rows:
        return None
    return int(rows[0].get("active") or 0)


def _open_entries(group_name, statuses=OPEN_WAITING_STATUSES):
    rows = frappe.get_all(
        WAITING, filters={"student_group": group_name, "status": ("in", list(statuses))},
        fields=["name", "student", "status", "offer_expires_on", "priority"],
        limit_page_length=MAX_ENTRIES)
    return rows


def reserved_offers(group_name, on_date=None, exclude_entry=None):
    """Unexpired offers on a class; the seats they hold are not free.

    ``exclude_entry`` is the entry being admitted right now: the seat it is
    holding is exactly the seat being granted, so it must not be counted as a
    competing reservation for its own admission.
    """
    return len([row for row in _open_entries(group_name, ("Offered",))
                if unexpired(row.get("offer_expires_on"), on_date)
                and row.get("name") != exclude_entry])


def seat_facts(group_name, for_update=False, on_date=None, exclude_entry=None):
    """Everything the seat decision needs, computed from native facts."""
    facts = _group_facts(group_name, for_update=for_update)
    rostered = int(frappe.db.count(ROSTER_TABLE, {"parent": group_name}))
    reserved = reserved_offers(group_name, on_date, exclude_entry)
    capacity = int(facts.max_strength or 0)
    return {
        "student_group": group_name, "capacity": capacity,
        "rostered": rostered, "reserved": reserved,
        "available": available_seats(capacity, rostered, reserved),
        "program": facts.program, "academic_year": facts.academic_year,
        "academic_term": facts.academic_term or "",
        "class_status": facts.th_class_status, "branch": facts.th_branch or "",
        "delivery_mode": facts.th_delivery_mode or "",
        "class_start_date": str(facts.th_class_start_date or ""),
        "class_end_date": str(facts.th_class_end_date or ""),
        "facts": facts,
    }


def _override_row(name, for_update=False):
    if for_update:
        _lock(OVERRIDE, name)
    row = frappe.db.get_value(
        OVERRIDE, name,
        ["name", "student_group", "student", "seats", "status", "reason",
         "approved_by", "approved_on", "expires_on", "used_on",
         "policy_effective_from"], as_dict=True)
    if row is None:
        raise frappe.ValidationError(f"Unknown capacity override: {name}")
    return row


def usable_override(override_name, group_name, student, on_date=None):
    """A matching Approved, unexpired override for this student and class."""
    row = _override_row(override_name)
    if row.get("status") != "Approved":
        raise frappe.ValidationError(
            f"Capacity override {override_name} is {row.get('status')}; only an "
            "Approved override can admit a student")
    if row.get("student_group") != group_name:
        raise frappe.ValidationError("The override names a different class")
    if row.get("student") != student:
        raise frappe.ValidationError("The override names a different student")
    if row.get("expires_on") and not unexpired(row.get("expires_on"), on_date):
        raise frappe.ValidationError(
            f"Capacity override {override_name} expired on {row.get('expires_on')}")
    if int(row.get("seats") or 0) < 1:
        raise frappe.ValidationError("The override grants no seat")
    return row


def consume_override(override_name, actor, on_date=None, group_name="",
                     student=""):
    """Mark an override Used exactly once (inside the admitting command).

    ``group_name`` / ``student`` are the admission actually being granted; the
    override must name exactly those, so an approval for one learner can never
    admit another.
    """
    row = _override_row(override_name, for_update=True)
    usable_override(override_name,
                    group_name or row.get("student_group"),
                    student or row.get("student"), on_date=on_date)
    doc = frappe.get_doc(OVERRIDE, row["name"])
    doc.flags.ignore_permissions = True
    doc.status = "Used"
    doc.used_on = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    return {"override": doc.name, "seats": int(doc.seats), "approved_by": doc.approved_by}


def row_target(override_name):
    row = _override_row(override_name)
    return row.get("student_group"), row.get("student")


def assert_seat_available(group_name, student, override="", on_date=None,
                          exclude_entry=None):
    """Refuse when no seat is free and no matching override admits the student.

    Returns the seat facts plus the consumed override (when one was used).
    The caller adds the roster row inside the same transaction; the override
    is marked Used here so a replay or a second admission cannot reuse it.
    ``exclude_entry`` lets the waiting-list admission count the seat its own
    offer holds as available, without letting any other offer be taken.
    """
    facts = seat_facts(group_name, on_date=on_date, exclude_entry=exclude_entry)
    _require_open_class(group_name, facts["facts"])
    if facts["available"] >= 1:
        return {"seats": facts, "override": None}
    if not override:
        raise frappe.ValidationError(
            f"Student group {group_name} is full "
            f"({facts['rostered']}/{facts['capacity']} seats, "
            f"{facts['reserved']} reserved); use the waiting list or an approved "
            "capacity override")
    consumed = consume_override(override, None, on_date=on_date,
                                group_name=group_name, student=student)
    return {"seats": facts, "override": consumed}


def assert_direct_move_allowed():
    """A governing policy may require transfers to go through their workflow."""
    terms = class_operations.governing_operations()
    if terms and not terms.get("direct_moves_allowed"):
        raise frappe.ValidationError(
            "Direct roster moves are disabled by the class-operations policy; "
            "use the class-transfer workflow")
    return terms


def assert_remove_allowed():
    """The governing policy may switch class-member removal off."""
    terms = class_operations.governing_operations()
    if terms and not terms.get("remove_member_allowed"):
        raise frappe.ValidationError(
            "Removing a class member is disabled by the class-operations policy")
    return terms


def _override_expiry(terms, expires_on):
    today = date.fromisoformat(_today())
    limit = (today + timedelta(days=terms["capacity_override_expiry_days"])).isoformat()
    if not expires_on:
        return limit
    try:
        clean = date.fromisoformat(str(expires_on)).isoformat()
    except ValueError as exc:
        raise frappe.ValidationError("Override expiry must be a date (YYYY-MM-DD)") from exc
    if clean <= today.isoformat():
        raise frappe.ValidationError("Override expiry must be in the future")
    if clean > limit:
        raise frappe.ValidationError(
            f"Override expiry may not exceed {limit} "
            f"({terms['capacity_override_expiry_days']} days)")
    return clean


def _offer_expiry(terms, expires_on):
    today = date.fromisoformat(_today())
    limit = (today + timedelta(days=terms["waiting_offer_valid_days"])).isoformat()
    if not expires_on:
        return limit
    try:
        clean = date.fromisoformat(str(expires_on)).isoformat()
    except ValueError as exc:
        raise frappe.ValidationError("Offer expiry must be a date (YYYY-MM-DD)") from exc
    if clean < today.isoformat():
        raise frappe.ValidationError("An offer cannot expire in the past")
    if clean > limit:
        raise frappe.ValidationError(
            f"An offer may not be held beyond {limit} "
            f"({terms['waiting_offer_valid_days']} days)")
    return clean


def _waiting_row(entry, for_update=True):
    if for_update:
        _lock(WAITING, entry)
    row = frappe.db.get_value(
        WAITING, entry,
        ["name", "student", "student_group", "status", "priority",
         "requested_by", "requested_on", "offered_by", "offered_on",
         "offer_expires_on", "admitted_on", "policy_effective_from",
         "note"], as_dict=True)
    if row is None:
        raise frappe.ValidationError(f"Unknown waiting-list entry: {entry}")
    return row


def _queue_position(entry, row):
    ahead = frappe.get_all(
        WAITING, filters={"student_group": row["student_group"],
                          "status": ("in", list(OPEN_WAITING_STATUSES))},
        fields=["name", "priority", "requested_on"], limit_page_length=MAX_ENTRIES)
    ordered = sorted(ahead, key=lambda item: (
        -int(item.get("priority") or 0), str(item.get("requested_on") or ""),
        str(item.get("name") or "")))
    for index, item in enumerate(ordered, 1):
        if item.get("name") == entry:
            return index
    return 0


@frappe.whitelist(methods=["POST"])
def join_waiting_list(request_key, student_group, student, note=""):
    """Queue an enrolled student for a seat the class does not have yet."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="waiting_list_enabled",
            message="The waiting list is not enabled by the governing "
                    "class-operations policy")
        group_name = _bounded(student_group, "Student group")
        student_name = _bounded(student, "Student")
        _require_active_student(student_name)
        facts = _group_facts(group_name, for_update=True)
        _require_open_class(group_name, facts)
        require_matching_enrollment(student_name, facts, group_name)
        if _roster_status(group_name, student_name) == 1:
            raise frappe.ValidationError(
                f"Student {student_name} is already an active member of {group_name}")
        for row in _open_entries(group_name):
            if row.get("student") == student_name:
                raise frappe.ValidationError(
                    f"Student {student_name} already has an open waiting-list entry "
                    f"({row.get('name')})")
        seats = seat_facts(group_name)
        if seats["available"] >= 1:
            raise frappe.ValidationError(
                f"{group_name} has {seats['available']} free seat(s); add the "
                "student to the class instead of the waiting list")
        doc = frappe.get_doc({
            "doctype": WAITING, "student": student_name,
            "student_group": group_name, "status": "Waiting", "priority": 0,
            "note": (note or "").strip()[:REASON_LIMIT] or None,
            "requested_by": actor, "requested_on": frappe.utils.now_datetime(),
            "policy_effective_from": terms.get("effective_from", ""),
            "synthetic": record_synthetic_flag(),
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        result = {
            "name": doc.name, "student": student_name,
            "student_group": group_name, "status": "Waiting",
            "position": _queue_position(doc.name, {"student_group": group_name}),
            "seats": {"capacity": seats["capacity"], "rostered": seats["rostered"],
                      "reserved": seats["reserved"], "available": seats["available"]},
            "policy_effective_from": terms.get("effective_from", ""),
        }
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, group_name, student_name,
                                               "Waiting"]))

    return _execute("join_waiting_list", request_key,
                    {"student_group": student_group, "student": student,
                     "note": note}, work)


@frappe.whitelist(methods=["POST"])
def leave_waiting_list(request_key, entry, reason):
    """Withdraw a waiting-list entry (the student no longer wants the seat)."""
    from toefl_house.api import _execute

    def work(actor):
        row = _waiting_row(_bounded(entry, "Waiting-list entry"))
        if row["status"] not in OPEN_WAITING_STATUSES:
            raise frappe.ValidationError(
                f"Waiting-list entry {entry} is {row['status']}")
        clean_reason = _reason(reason)
        doc = frappe.get_doc(WAITING, row["name"])
        doc.flags.ignore_permissions = True
        doc.status = "Withdrawn"
        doc.note = clean_reason
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Withdrawn",
                  "student_group": row["student_group"]}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Withdrawn", clean_reason]))

    return _execute("leave_waiting_list", request_key,
                    {"entry": entry, "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def offer_waiting_list_seat(request_key, entry, expires_on=""):
    """Offer the next free seat to one waiting entry, held until it expires."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="waiting_list_enabled",
            message="The waiting list is not enabled by the governing "
                    "class-operations policy")
        row = _waiting_row(_bounded(entry, "Waiting-list entry"))
        if row["status"] != "Waiting":
            raise frappe.ValidationError(
                f"Waiting-list entry {entry} is {row['status']}; only a Waiting "
                "entry can be offered a seat")
        group_name = row["student_group"]
        facts = _group_facts(group_name, for_update=True)
        _require_open_class(group_name, facts)
        require_matching_enrollment(row["student"], facts, group_name)
        seats = seat_facts(group_name)
        if seats["available"] < 1:
            raise frappe.ValidationError(
                f"{group_name} has no free seat to offer "
                f"({seats['rostered']}/{seats['capacity']} seats, "
                f"{seats['reserved']} reserved)")
        expiry = _offer_expiry(terms, expires_on)
        doc = frappe.get_doc(WAITING, row["name"])
        doc.flags.ignore_permissions = True
        doc.status = "Offered"
        doc.offered_by = actor
        doc.offered_on = frappe.utils.now_datetime()
        doc.offer_expires_on = expiry
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Offered",
                  "student_group": group_name, "student": row["student"],
                  "offer_expires_on": expiry,
                  "seats": {"capacity": seats["capacity"],
                            "rostered": seats["rostered"],
                            "reserved": seats["reserved"],
                            "available": seats["available"] - 1},
                  "policy_effective_from": terms.get("effective_from", "")}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Offered", group_name, expiry]))

    return _execute("offer_waiting_list_seat", request_key,
                    {"entry": entry, "expires_on": expires_on}, work)


@frappe.whitelist(methods=["POST"])
def admit_from_waiting_list(request_key, entry, override=""):
    """Admit one waiting (or offered) student, consuming the offered seat.

    The seat, the enrollment and the class state are all re-proven under
    lock; an expired offer is refused, and a full class needs a matching
    Approved override — exactly as a direct roster addition does.
    """
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations(
            feature="waiting_list_enabled",
            message="The waiting list is not enabled by the governing "
                    "class-operations policy")
        row = _waiting_row(_bounded(entry, "Waiting-list entry"))
        if row["status"] not in OPEN_WAITING_STATUSES:
            raise frappe.ValidationError(
                f"Waiting-list entry {entry} is {row['status']}")
        if row["status"] == "Offered" and not unexpired(row.get("offer_expires_on")):
            raise frappe.ValidationError(
                f"The seat offer expired on {row.get('offer_expires_on')}; "
                "offer the seat again if it is still free")
        group_name = row["student_group"]
        student = row["student"]
        facts = _group_facts(group_name, for_update=True)
        _require_open_class(group_name, facts)
        _require_active_student(student)
        require_matching_enrollment(student, facts, group_name)
        previous = _roster_status(group_name, student)
        if previous == 1:
            raise frappe.ValidationError(
                f"Student {student} is already an active member of {group_name}")
        seat = assert_seat_available(group_name, student, override,
                                     exclude_entry=row["name"])
        from toefl_house.teaching import _set_membership
        label = frappe.db.get_value(STUDENT, student, "student_name")
        _set_membership(group_name, student, label, True)
        doc = frappe.get_doc(WAITING, row["name"])
        doc.flags.ignore_permissions = True
        doc.status = "Admitted"
        doc.admitted_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        after = seat_facts(group_name)
        result = {
            "name": doc.name, "status": "Admitted", "student": student,
            "student_group": group_name,
            "reactivated": previous == 0,
            "override": seat["override"],
            "seats": {"capacity": after["capacity"], "rostered": after["rostered"],
                      "reserved": after["reserved"], "available": after["available"]},
            "policy_effective_from": terms.get("effective_from", ""),
        }
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Admitted", group_name,
                                               student]))

    return _execute("admit_from_waiting_list", request_key,
                    {"entry": entry, "override": override}, work)


@frappe.whitelist(methods=["POST"])
def create_capacity_override(request_key, student_group, student, seats, reason,
                             expires_on=""):
    """Approve extra seats above the class capacity for one named student."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations()
        if not terms.get("capacity_override_role"):
            raise frappe.ValidationError(
                "Capacity overrides are not configured; the class-operations "
                "policy names no override role")
        if terms["capacity_override_role"] not in frappe.get_roles(actor):
            raise frappe.PermissionError(
                "Capacity overrides require the policy-configured role: "
                + terms["capacity_override_role"])
        group_name = _bounded(student_group, "Student group")
        student_name = _bounded(student, "Student")
        clean_seats = _int(seats, "Override seats", 1,
                           terms["capacity_override_max_seats"])
        clean_reason = _reason(reason)
        facts = _group_facts(group_name)
        _require_open_class(group_name, facts)
        _require_active_student(student_name)
        expiry = _override_expiry(terms, expires_on)
        doc = frappe.get_doc({
            "doctype": OVERRIDE, "student_group": group_name,
            "student": student_name, "seats": clean_seats,
            "status": "Approved", "reason": clean_reason,
            "approved_by": actor, "approved_on": frappe.utils.now_datetime(),
            "expires_on": expiry,
            "policy_effective_from": terms.get("effective_from", ""),
            "synthetic": record_synthetic_flag(),
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        result = {"name": doc.name, "student_group": group_name,
                  "student": student_name, "seats": clean_seats,
                  "status": "Approved", "expires_on": expiry,
                  "policy_effective_from": terms.get("effective_from", "")}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, group_name, student_name,
                                               clean_seats, expiry]))

    return _execute("create_capacity_override", request_key,
                    {"student_group": student_group, "student": student,
                     "seats": seats, "reason": reason, "expires_on": expires_on},
                    work)


@frappe.whitelist(methods=["POST"])
def revoke_capacity_override(request_key, override, reason):
    """Revoke an unused override; a used or revoked one cannot be re-opened."""
    from toefl_house.api import _execute

    def work(actor):
        terms = class_operations.require_operations()
        if not terms.get("capacity_override_role"):
            raise frappe.ValidationError(
                "Capacity overrides are not configured")
        if terms["capacity_override_role"] not in frappe.get_roles(actor):
            raise frappe.PermissionError(
                "Capacity overrides require the policy-configured role: "
                + terms["capacity_override_role"])
        clean_reason = _reason(reason)
        row = _override_row(_bounded(override, "Capacity override"), for_update=True)
        if row["status"] != "Approved":
            raise frappe.ValidationError(
                f"Capacity override {override} is {row['status']}")
        doc = frappe.get_doc(OVERRIDE, row["name"])
        doc.flags.ignore_permissions = True
        doc.status = "Revoked"
        doc.revoked_on = frappe.utils.now_datetime()
        doc.revocation_reason = clean_reason
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Revoked", "reason": clean_reason}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Revoked", clean_reason]))

    return _execute("revoke_capacity_override", request_key,
                    {"override": override, "reason": reason}, work)


def _require_availability_reader():
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if not roles & set(AVAILABILITY_ROLES):
        raise frappe.PermissionError(
            "Seat availability is available to Reception and Academic staff only")
    return user


def _availability_branch_scope():
    """Constrain both availability and waiting-list reads at the server.

    A Reception login always needs an explicit Branch User Permission. Other
    permitted academic roles can be HQ-wide only when they have no Branch
    restrictions. A supplied browser Branch or Student Group is never
    authority to escape the actual viewer's allowed branches.
    """
    user = _require_availability_reader()
    rows = frappe.get_all(
        "User Permission", filters={"user": user, "allow": "Branch"},
        fields=["for_value"], limit_page_length=101)
    if len(rows) >= 101:
        raise frappe.ValidationError(
            "Branch permissions exceed the complete read; ask an administrator")
    branches = sorted({row.get("for_value") for row in rows if row.get("for_value")})
    if "Reception" in set(frappe.get_roles(user)) and not branches:
        raise frappe.PermissionError(
            "Reception seat and waiting-list reads require an explicitly assigned Branch")
    return branches or None


@frappe.whitelist(methods=["GET", "POST"])
def class_availability(student_group="", program="", academic_year="",
                       branch=""):
    """Seat truth per class, plus the intake projection for planning.

    Read-only. ``available`` counts what a walk-in can take now: capacity
    minus every roster row (native counting) minus unexpired offers. The
    intake block answers the planning question — how much live demand is
    waiting and when the current classes end, so the next cohort can be
    planned — without inventing a date or a seat.
    """
    branches = _availability_branch_scope()
    if branch and branches is not None and branch not in branches:
        raise frappe.PermissionError("The selected branch is not assigned to this login")
    filters = {"disabled": 0}
    if student_group:
        filters["name"] = student_group
    else:
        if program:
            filters["program"] = program
        if academic_year:
            filters["academic_year"] = academic_year
    if branches is not None:
        filters["th_branch"] = branch if branch else ("in", branches)
    elif branch:
        filters["th_branch"] = branch
    rows = frappe.get_all(
        GROUP, filters=filters,
        fields=["name", "student_group_name", "program", "academic_year",
                "academic_term", "max_strength", "th_class_status",
                "th_delivery_mode", "th_branch", "th_class_start_date",
                "th_class_end_date"],
        order_by="student_group_name asc", limit_page_length=MAX_CLASSES)
    names = [row["name"] for row in rows]
    waiting_counts = {}
    if names:
        for entry in frappe.get_all(
                WAITING, filters={"student_group": ("in", names),
                                  "status": ("in", list(OPEN_WAITING_STATUSES))},
                fields=["student_group", "status"], limit_page_length=MAX_CLASSES * 4):
            waiting_counts[entry["student_group"]] = waiting_counts.get(
                entry["student_group"], 0) + 1
    classes = []
    intake = {}
    for row in rows:
        seats = seat_facts(row["name"])
        waiting = waiting_counts.get(row["name"], 0)
        item = {
            "student_group": row["name"],
            "name": row.get("student_group_name") or row["name"],
            "program": row.get("program") or "",
            "academic_year": row.get("academic_year") or "",
            "academic_term": row.get("academic_term") or "",
            "class_status": row.get("th_class_status") or "",
            "delivery_mode": row.get("th_delivery_mode") or "",
            "branch": row.get("th_branch") or "",
            "class_start_date": str(row.get("th_class_start_date") or ""),
            "class_end_date": str(row.get("th_class_end_date") or ""),
            "capacity": seats["capacity"], "rostered": seats["rostered"],
            "reserved": seats["reserved"], "available": seats["available"],
            "waiting": waiting,
            "full": seats["available"] < 1,
        }
        classes.append(item)
        key = (item["program"], item["academic_year"])
        bucket = intake.setdefault(key, {
            "program": key[0], "academic_year": key[1], "seats_available": 0,
            "waiting": 0, "classes": 0, "next_class_end": ""})
        bucket["seats_available"] += item["available"]
        bucket["waiting"] += waiting
        bucket["classes"] += 1
        if item["class_end_date"] and (
                not bucket["next_class_end"]
                or item["class_end_date"] < bucket["next_class_end"]):
            bucket["next_class_end"] = item["class_end_date"]
    for bucket in intake.values():
        bucket["projected_unmet_demand"] = max(
            0, bucket["waiting"] - bucket["seats_available"])
    return {
        "as_of": _today(), "classes": classes,
        "intake": sorted(intake.values(),
                         key=lambda item: (item["program"], item["academic_year"])),
        "definitions": {
            "available": "capacity minus every roster row (native counting) "
                         "minus unexpired seat offers",
            "reserved": "unexpired waiting-list offers holding a seat",
            "waiting": "open waiting-list entries (Waiting or Offered)",
        },
    }


@frappe.whitelist(methods=["GET", "POST"])
def waiting_list_board(student_group=""):
    """The actionable waiting queue: who is next, and what to do for them.

    Every row carries the ONE next step for the viewer's operation and the
    role responsible, so Reception and the Academic desk act on the list
    rather than merely reading it. Offers past their expiry are surfaced as
    an explicit action instead of silently holding a seat.
    """
    branches = _availability_branch_scope()
    filters = {"status": ("in", list(OPEN_WAITING_STATUSES))}
    if branches is not None:
        # Restrict the waiting queue BEFORE reading any student identifiers.
        # For a direct class query, both name and branch must match; for the
        # board, collect only classes the viewer is authorized to see.
        group_filters = {"th_branch": ("in", branches)}
        if student_group:
            group_filters["name"] = student_group
        group_rows = frappe.get_all(
            GROUP, filters=group_filters, fields=["name"],
            order_by="name asc", limit_page_length=MAX_CLASSES + 1)
        if len(group_rows) > MAX_CLASSES:
            raise frappe.ValidationError(
                "Class branch scope exceeds the complete board read; narrow the search")
        permitted = sorted({row["name"] for row in group_rows})
        if student_group and student_group not in permitted:
            raise frappe.PermissionError("The selected class is outside assigned Branch scope")
        if not permitted:
            return {"as_of": _today(), "entries": [], "count": 0}
        filters["student_group"] = ("in", permitted)
    elif student_group:
        filters["student_group"] = student_group
    rows = frappe.get_all(
        WAITING, filters=filters,
        fields=["name", "student", "student_group", "status", "priority",
                "requested_on", "offer_expires_on", "requested_by"],
        order_by="requested_on asc", limit_page_length=MAX_ENTRIES)
    groups = {}
    for row in rows:
        groups.setdefault(row["student_group"], []).append(row)
    board = []
    for group_name, entries in groups.items():
        try:
            seats = seat_facts(group_name)
        except frappe.ValidationError:
            seats = {"capacity": 0, "rostered": 0, "reserved": 0, "available": 0}
        ordered = sorted(entries, key=lambda item: (
            -int(item.get("priority") or 0), str(item.get("requested_on") or ""),
            str(item.get("name") or "")))
        for index, entry in enumerate(ordered, 1):
            offered = entry["status"] == "Offered"
            live = offered and unexpired(entry.get("offer_expires_on"))
            if offered and not live:
                next_step = "The seat offer expired; offer a seat again or withdraw the entry."
                action = "offer_waiting_list_seat"
            elif offered and live:
                next_step = "The student holds a seat offer; admit or let it expire."
                action = "admit_from_waiting_list"
            elif seats["available"] >= 1:
                next_step = "A seat is free; offer it to this entry."
                action = "offer_waiting_list_seat"
            else:
                next_step = "No seat yet; the entry holds its place in the queue."
                action = ""
            board.append({
                "entry": entry["name"], "student": entry["student"],
                "student_group": group_name, "status": entry["status"],
                "position": index, "priority": int(entry.get("priority") or 0),
                "waiting_since": str(entry.get("requested_on") or ""),
                "offer_expires_on": str(entry.get("offer_expires_on") or ""),
                "seats_available": seats["available"],
                "next": next_step,
                "next_role": "Teaching Scheduler",
                "next_command": action,
            })
    return {"as_of": _today(), "entries": board,
            "count": len(board)}


__all__ = ["WAITING", "OVERRIDE", "WAITING_STATUSES", "OVERRIDE_STATUSES",
           "AVAILABILITY_ROLES", "available_seats", "unexpired",
           "seat_facts", "assert_seat_available", "consume_override",
           "assert_direct_move_allowed", "class_availability",
           "waiting_list_board", "join_waiting_list", "leave_waiting_list",
           "offer_waiting_list_seat", "admit_from_waiting_list",
           "create_capacity_override", "revoke_capacity_override"]
