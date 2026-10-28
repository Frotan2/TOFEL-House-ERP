"""Authorized assessment marks, approval and publication (Mission B04).

Native Education remains the assessment authority: the class is a native
``Student Group``, the scheduled instance is a native ``Assessment Plan``,
grade boundaries are the native ``Grading Scale`` intervals, and the
authoritative per-student score record published alongside a result is the
native ``Assessment Result``. This module adds only what the native apps
lack — an *authorized, reviewable, policy-pinned* path from instructor marks
to a published, auditable result:

    open (academic staff)            TH Assessment Book, policy version pinned
      -> record marks (assigned instructor only)
      -> submit            (instructor; no silent blanks)
      -> review / return   (academic staff; corrections are logged)
      -> approve           (academic staff; author cannot approve own book)
      -> publish           -> TH Academic Result (digest-pinned snapshot)
                           -> native Assessment Result (when a plan is named)

Every step is a receipted, role-gated command in the existing
``toefl_house.api._execute`` pattern (idempotency key, operation receipt,
hash-chained audit event, one transaction). No academic value is invented
here: components, weights, pass rules, retakes and progression come from the
Course Owner's effective-dated policy version; grade codes come from the
native Grading Scale; attendance comes from native ``Student Attendance``.
An unconfigured policy is an explicit refusal, never a default.
"""
import frappe

from toefl_house.academic import grading, rules
from toefl_house.api import _execute
from toefl_house.configuration import rules as configuration_rules
from toefl_house.policy import digest
from toefl_house.security import record_synthetic_flag, require_operational

BOOK = "TH Assessment Book"
DECISION = "TH Progression Decision"
MARK = "TH Assessment Book Mark"
CORRECTION = "TH Assessment Book Correction"
RESULT = "TH Academic Result"
RESULT_COMPONENT = "TH Academic Result Component"
POLICY = "TH Assessment Policy"
LEVEL = "TH Program Level"
GROUP = "Student Group"
ROSTER = "Student Group Student"
SCALE = "Grading Scale"
INTERVAL = "Grading Scale Interval"
PLAN = "Assessment Plan"
ATTENDANCE = "Student Attendance"
NATIVE_RESULT = "Assessment Result"
ASSIGNMENT = "TH Teaching Assignment"
EMPLOYEE = "Employee"
INSTRUCTOR = "Instructor"

BOOK_STATUSES = ("Open", "Submitted", "Reviewed", "Returned", "Approved",
                 "Published")
MAX_ROWS = 2000
STATUS_ORDER = {"Open": 1, "Returned": 2, "Submitted": 3, "Reviewed": 4,
                "Approved": 5, "Published": 6}


def _text(value, what, maximum=140):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise frappe.ValidationError(f"{what} is required (at most {maximum} characters)")
    return value.strip()


def _reason(value, what, maximum=300):
    if not isinstance(value, str) or not value.strip():
        raise frappe.ValidationError(f"{what} is required")
    text = value.strip()
    if len(text) > maximum:
        raise frappe.ValidationError(f"{what} must be at most {maximum} characters")
    return text


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise frappe.ValidationError(f"{what} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError(f"{what} must be a number") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise frappe.ValidationError(f"{what} must be a finite number")
    return number


# --- Policy resolution (fail closed, never a default) ----------------------
def policy_versions(policy_code):
    """The version rows of one assessment policy, oldest first."""
    name = frappe.db.get_value(POLICY, {"code": policy_code}, "name")
    if not name:
        raise frappe.ValidationError(f"Unknown assessment policy: {policy_code}")
    doc = frappe.get_doc(POLICY, name)
    return doc, [row.as_dict() for row in (doc.get("versions") or [])]


def governing_version(policy_code, on_date):
    """The policy version governing ``on_date``, or an explicit refusal."""
    doc, rows = policy_versions(policy_code)
    if doc.status != "Active":
        raise frappe.ValidationError(
            f"Assessment policy {policy_code} is retired; no version governs new assessment")
    version = configuration_rules.resolve_governing(rows, str(on_date))
    if not version:
        raise frappe.ValidationError(
            f"Assessment policy {policy_code} has no version effective on {on_date}; "
            "the Course Owner must configure one before marks can be taken")
    return doc, version


def pinned_version(policy_code, effective_from):
    """One exact policy version by effective date (the historical pin)."""
    doc, rows = policy_versions(policy_code)
    for row in rows:
        if str(row.get("effective_from")) == str(effective_from):
            return doc, row
    raise frappe.ValidationError(
        f"Assessment policy {policy_code} has no version effective {effective_from}; "
        "history is ambiguous until the configuration is repaired")


def version_facets(version):
    """Parsed facets of one stored version row (integrity-checked)."""
    try:
        return grading.parse_facets(
            {name: version.get(name) for name in rules.ASSESSMENT_FACETS})
    except ValueError as exc:
        raise frappe.ValidationError(
            f"The pinned assessment policy version is not readable: {exc}") from exc


def scale_intervals(scale):
    """Native Grading Scale intervals, or an explicit refusal."""
    if not scale or not frappe.db.exists(SCALE, scale):
        raise frappe.ValidationError(
            "The pinned policy version names no native Grading Scale; grades "
            "cannot be produced until the Course Owner links one")
    rows = frappe.get_all(INTERVAL, filters={"parent": scale},
                          fields=["grade_code", "threshold"], order_by="threshold desc")
    if not rows:
        raise frappe.ValidationError(
            f"Native Grading Scale {scale} has no intervals; grade codes cannot be produced")
    return [{"grade_code": row["grade_code"], "threshold": row["threshold"]} for row in rows]


def _level_for_program(program):
    if not program:
        return None
    return frappe.db.get_value(LEVEL, {"native_program": program}, ["name", "code", "next_level"],
                               as_dict=True)


def roster(student_group):
    """Active roster of the native class (native Student Group Student)."""
    if not frappe.db.exists(GROUP, student_group):
        raise frappe.ValidationError(f"Unknown student group: {student_group}")
    rows = frappe.get_all(ROSTER, filters={"parent": student_group, "active": 1},
                          fields=["student"], order_by="student asc")
    return [row["student"] for row in rows]


def _attendance_percent(student, student_group):
    rows = frappe.get_all(ATTENDANCE,
                          filters={"student": student, "student_group": student_group,
                                   "docstatus": 1},
                          fields=["status"])
    if not rows:
        return None
    attended = sum(1 for row in rows if row.get("status") == "Present")
    return round(attended * 100.0 / len(rows), 4)


# --- Instructor authorization --------------------------------------------
def instructor_of(user):
    """The Instructor natively linked to this login (Employee.user_id), or None."""
    employee = frappe.db.get_value(EMPLOYEE, {"user_id": user, "status": "Active"},
                                   ["name"], as_dict=True)
    if not employee:
        return None
    return frappe.db.get_value(INSTRUCTOR, {"employee": employee.name}, "name")


def _assigned_instructor(actor, student_group):
    """Only an instructor assigned to this class may record its marks."""
    instructor = instructor_of(actor)
    if not instructor:
        raise frappe.PermissionError(
            "Your login is not linked to an instructor record; marks for this "
            "class can only be entered by its assigned instructor")
    if not frappe.db.exists(ASSIGNMENT, {"student_group": student_group,
                                         "instructor": instructor}):
        raise frappe.PermissionError(
            "You are not assigned to this class; only its assigned instructor "
            "may record its marks")
    return instructor


# --- Book commands --------------------------------------------------------
def _book_doc(name, for_update=False):
    if not frappe.db.exists(BOOK, name):
        raise frappe.ValidationError("Unknown assessment book")
    if for_update:
        frappe.db.sql("select name from `tabTH Assessment Book` where name=%s for update",
                      (name,))
    return frappe.get_doc(BOOK, name)


def _book_result(book, extra=None):
    result = {
        "name": book.name,
        "student_group": book.student_group,
        "level": book.get("level") or "",
        "policy": book.policy,
        "policy_effective_from": str(book.policy_effective_from),
        "status": book.status,
        "attempt": book.attempt,
        "mark_count": len(book.get("marks") or []),
    }
    if extra:
        result.update(extra)
    return result


def _attempt_rows(student_group, level_name):
    # Ordinals belong to the class and academic level, never the pinned
    # assessment policy. Changing policy must not reset retake consumption.
    return frappe.get_all(BOOK, filters={"student_group": student_group,
                                         "level": level_name},
                          fields=["name", "attempt"], order_by="attempt desc")


def _lock_assessment_group(student_group):
    """Serialize book opening/publication for this class in native MariaDB."""
    frappe.db.sql("select name from `tabStudent Group` where name=%s for update",
                  (student_group,))


# --- Retake authorization for further books --------------------------------
# A book is class-wide, but a retake is per student: a further book for a
# class that already has published results is authorized only when at least
# one roster student holds a live, unconsumed retake authorization (see
# below). The gate runs at open time AND at publish time, so a book opened
# before the first publication (or under a different policy, whose attempt
# ordinal restarts) cannot be published as an unauthorized further attempt.
# An unpublished book is not an attempt: attempt counting in the codebase
# counts published results, so opening a second book while the first is
# still unpublished is existing behaviour, not a retake — but publishing it
# after the first book's results exist is gated.
def _current_published_by_student(student_group, level_name):
    """Current Published result per (student, attempt), highest revision wins."""
    rows = frappe.get_all(RESULT,
                          filters={"student_group": student_group,
                                   "level": level_name, "status": "Published"},
                          fields=["name", "student", "level", "book", "attempt",
                                  "revision", "outcome", "published_on",
                                  "policy", "policy_effective_from"])
    current = {}
    for row in rows:
        key = (row.get("student"), int(row.get("attempt") or 1))
        previous = current.get(key)
        if previous is None or int(row.get("revision") or 1) > int(previous.get("revision") or 1):
            current[key] = row
    return current


def _retake_authorization(student_group, level_name, on_date, *,
                          next_attempt, exclude_book=None):
    """Is a further book for this class+level authorized, and by whom?

    Returns (True, student_name) for the first eligible retaker found, or
    (False, reason). A student authorizes a further book when ALL hold:
      (i) an Approved Retake decision exists for some result (any revision)
          of that student at this level with the same attempt ordinal;
      (ii) the student's current Published result for that attempt is Fail;
      (iii) the wait has elapsed from that result's own publication date,
          under its pinned retakes facet bounded by the mission's 7-day
          floor (grading.wait_until_for_retake);
      (iv) no Published retake result exists for the student at this level
          with a higher attempt ordinal;
      (v) no other in-progress (unpublished) book exists for this
          class+level with a higher attempt ordinal — a Retake decision is
          consumed exactly once, by the one retake book it authorizes.
    The check is per student, so one student's authorization never launders
    a retake for another student; the book itself is class-wide, so the
    authorized book publishes retake results for the roster as a whole.
    """
    members = set(roster(student_group))
    current = _current_published_by_student(student_group, level_name)
    if not current:
        return False, "No published result exists for this class and level"
    books = frappe.get_all(BOOK, filters={"student_group": student_group,
                                          "level": level_name},
                           fields=["name", "attempt", "status"])
    blockers = []
    by_student_attempt = {}
    for (student, attempt), row in current.items():
        by_student_attempt.setdefault(student, {})[attempt] = row
    for student in sorted(by_student_attempt):
        if student not in members:
            continue
        for attempt in sorted(by_student_attempt[student]):
            row = by_student_attempt[student][attempt]
            names = [item.get("name") for item in frappe.get_all(
                RESULT, filters={"student": student, "level": level_name,
                                 "attempt": attempt}, fields=["name"])]
            decisions = frappe.get_all(
                DECISION, filters={"academic_result": ["in", names],
                                   "decision": "Retake", "status": "Approved"},
                fields=["name"]) if names else []
            if not decisions:
                blockers.append(f"{student} attempt {attempt}: no approved Retake decision")
                continue
            if row.get("outcome") != "Fail":
                blockers.append(
                    f"{student} attempt {attempt}: outcome is {row.get('outcome')}, "
                    "not Fail")
                continue
            try:
                policy_code = frappe.db.get_value(POLICY, row.get("policy"), "code")
                _doc, version = pinned_version(policy_code,
                                               row.get("policy_effective_from"))
                retakes = version_facets(version).get("retakes")
            except Exception:
                retakes = None
            if not retakes:
                blockers.append(
                    f"{student} attempt {attempt}: no retake rules are configured")
                continue
            effective = grading.effective_retake_rules(retakes)
            if (attempt >= effective["max_attempts"]
                    or int(next_attempt) != attempt + 1):
                blockers.append(
                    f"{student} attempt {attempt}: retake ordinal or total-attempt "
                    "limit does not match the next assessment book")
                continue
            wait_until = grading.wait_until_for_retake(
                retakes.get("wait_days"), row.get("published_on") or "")
            if str(on_date) < wait_until:
                blockers.append(
                    f"{student} attempt {attempt}: the retake wait ends on {wait_until}")
                continue
            if any(int(other.get("attempt") or 0) > attempt
                   for (other_student, _), other in current.items()
                   if other_student == student):
                blockers.append(
                    f"{student} attempt {attempt}: a retake attempt already exists")
                continue
            in_progress = [book for book in books
                           if book.get("name") != exclude_book
                           and int(book.get("attempt") or 0) > attempt
                           and book.get("status") != "Published"]
            if in_progress:
                blockers.append(
                    f"{student} attempt {attempt}: a retake book is already in progress")
                continue
            return True, student
    detail = "; ".join(blockers[:3])
    return False, ("No approved retake authorizes a further book for this class"
                   + (f": {detail}" if detail else ""))


@frappe.whitelist(methods=["POST"])
def open_assessment_book(request_key, student_group, policy, effective_from="",
                         assessment_plan=""):
    """Open one class's mark book against the governing policy version.

    Academic staff open the book; the governing version is pinned (effective
    date + facet digest) so a later policy change can never re-grade marks
    taken under this one. The policy must govern this class's level, and the
    book's attempt ordinal is derived from prior books — never chosen freely.
    """
    def work(actor):
        group_name = _text(student_group, "Student group")
        policy_code = _text(policy, "Assessment policy")
        roster(group_name)
        _lock_assessment_group(group_name)
        group = frappe.db.get_value(GROUP, group_name, ["program", "academic_year"],
                                    as_dict=True)
        level = _level_for_program(group.program if group else None)
        if not level:
            raise frappe.ValidationError(
                "This class's native program is not mapped to a program level; "
                "assessment requires a configured level (Academic Setup)")
        today = frappe.utils.today()
        on_date = str(effective_from or today)
        _doc, version = governing_version(policy_code, on_date)
        facets = version_facets(version)
        mapping = (facets.get("level_mapping") or {}).get("levels") or []
        if not mapping:
            raise frappe.ValidationError(
                "The governing policy version configures no level mapping; it "
                "governs no level until the Course Owner defines one")
        if level.code not in mapping:
            raise frappe.ValidationError(
                f"Assessment policy {policy_code} does not govern level {level.code}")
        state = grading.policy_state(facets, scale_intervals(version.get("grading_scale")))
        if not state["configured"]:
            raise frappe.ValidationError("; ".join(state["explanations"]))
        plan = ""
        if assessment_plan:
            plan = _text(assessment_plan, "Native assessment plan")
            if not frappe.db.exists(PLAN, plan):
                raise frappe.ValidationError("Unknown native assessment plan")
        existing = _attempt_rows(group_name, level.name)
        next_attempt = (max(int(row["attempt"] or 0) for row in existing) + 1
                        if existing else 1)
        # A further book for a class+level that already has published
        # results is a retake: it needs a live retake authorization, not
        # just an academic role. A second book while nothing is published
        # yet is not a retake (see _retake_authorization), and the publish
        # gate below closes the pre-opened-book path.
        if _current_published_by_student(group_name, level.name):
            allowed, reason = _retake_authorization(
                group_name, level.name, today, next_attempt=next_attempt)
            if not allowed:
                raise frappe.ValidationError(reason)
        policy_digest = digest({
            "policy": policy_code,
            "effective_from": str(version.get("effective_from")),
            "grading_scale": version.get("grading_scale") or "",
            "facets": facets,
        })
        book = frappe.get_doc({
            "doctype": BOOK,
            "student_group": group_name,
            "level": level.name,
            "policy": _doc.name,
            "policy_effective_from": str(version.get("effective_from")),
            "policy_digest": policy_digest,
            "grading_scale": version.get("grading_scale") or "",
            "assessment_plan": plan,
            "attempt": next_attempt,
            "status": "Open",
            "opened_by": actor,
            "opened_on": frappe.utils.now_datetime(),
            "synthetic": record_synthetic_flag(),
        })
        book.insert(ignore_permissions=True)
        return _book_result(book), {
            "target": book.name,
            "before_hash": "",
            "after_hash": digest([book.name, "Open", policy_code,
                                  str(version.get("effective_from")), policy_digest]),
        }

    return _execute("open_assessment_book", request_key,
                    {"student_group": student_group, "policy": policy,
                     "effective_from": effective_from,
                     "assessment_plan": assessment_plan}, work)


@frappe.whitelist(methods=["POST"])
def record_assessment_marks(request_key, book, marks):
    """Record an authorized instructor's marks for a class book.

    The book must be Open or Returned, the actor must be an instructor
    assigned to the class, every student must be on the class's active native
    roster, and every component must exist on the pinned policy version. A
    component may be recorded without a mark only with a missing reason: a
    blank is never read as a zero. Existing (student, component) rows are
    refused here — an academic correction goes through its own command.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status not in ("Open", "Returned"):
            raise frappe.ValidationError(
                f"Marks cannot be recorded while the book is {doc.status}; "
                "an academic correction needs its own command")
        _assigned_instructor(actor, doc.student_group)
        rows = _mark_rows(marks)
        members = set(roster(doc.student_group))
        if not members:
            raise frappe.ValidationError("The class has no active students on its roster")
        _doc, version = pinned_version(
            frappe.db.get_value(POLICY, doc.policy, "code"), doc.policy_effective_from)
        facets = version_facets(version)
        components = {row["code"]: row for row in facets.get("components") or []}
        if not components:
            raise frappe.ValidationError(
                "The pinned policy version configures no components; marks cannot be recorded")
        existing = {(row.get("student"), row.get("component")): row
                    for row in (doc.get("marks") or [])}
        seen = set(existing)
        recorded = []
        for entry in rows:
            student = entry["student"]
            component = entry["component"]
            if student not in members:
                raise frappe.ValidationError(
                    f"Student {student} is not on this class's active roster")
            if component not in components:
                raise frappe.ValidationError(
                    f"Component {component} is not part of the pinned policy version")
            maximum = float(components[component]["maximum_score"])
            mark = entry.get("mark")
            missing_reason = entry.get("missing_reason") or ""
            if mark is None and not missing_reason:
                raise frappe.ValidationError(
                    f"Record a mark or a missing reason for {student} / {component}")
            if mark is not None and missing_reason:
                raise frappe.ValidationError(
                    f"Record either a mark or a missing reason for {student} / {component}")
            if mark is not None:
                value = _number(mark, "Mark")
                if value < 0 or value > maximum:
                    raise frappe.ValidationError(
                        f"Mark for {student} / {component} must be between 0 and {maximum:g}")
            if (student, component) in seen and doc.status != "Returned":
                # A re-entered mark is a correction, and corrections belong to
                # academic staff. A book an academic reviewer *returned* to the
                # instructor is the one exception: that return exists to let the
                # instructor fix its marks, so the change is logged with the
                # previous value and the reviewer's note as its reason.
                raise frappe.ValidationError(
                    f"A mark for {student} / {component} already exists; use the "
                    "academic correction command to change it")
            if (student, component) in seen:
                previous = existing[(student, component)]
                doc.append("corrections", {
                    "student": student, "component": component,
                    "previous_mark": previous.get("mark"),
                    "new_mark": mark if mark is None else float(mark),
                    "reason": doc.get("review_note") or "Instructor corrected a "
                                                       "returned book",
                    "corrected_by": actor,
                    "corrected_on": frappe.utils.now_datetime(),
                })
                target = existing[(student, component)]
                target.mark = mark if mark is None else float(mark)
                target.missing_reason = missing_reason
                target.entered_by = actor
                target.entered_on = frappe.utils.now_datetime()
                recorded.append([student, component])
                continue
            seen.add((student, component))
            doc.append("marks", {
                "student": student, "component": component,
                "maximum_score": maximum,
                "mark": mark if mark is None else float(mark),
                "missing_reason": missing_reason,
                "entered_by": actor,
                "entered_on": frappe.utils.now_datetime(),
            })
            recorded.append([student, component])
        doc.save(ignore_permissions=True)
        result = _book_result(doc, {"recorded": len(recorded)})
        return result, {
            "target": doc.name,
            "before_hash": digest([doc.name, doc.status, len(seen) - len(recorded)]),
            "after_hash": digest([doc.name, doc.status, sorted(recorded)]),
        }

    return _execute("record_assessment_marks", request_key,
                    {"book": book, "marks": marks}, work)


def _mark_rows(marks):
    if not isinstance(marks, list) or not marks:
        raise frappe.ValidationError("At least one mark row is required")
    if len(marks) > MAX_ROWS:
        raise frappe.ValidationError("Too many mark rows in one request")
    cleaned = []
    for entry in marks:
        if not isinstance(entry, dict):
            raise frappe.ValidationError("Each mark row must be an object")
        unknown = set(entry) - {"student", "component", "mark", "missing_reason"}
        if unknown:
            raise frappe.ValidationError(
                "Unknown mark row keys: " + ", ".join(sorted(unknown)))
        cleaned.append({
            "student": _text(entry.get("student"), "Student"),
            "component": _text(entry.get("component"), "Component", 32),
            "mark": entry.get("mark"),
            "missing_reason": entry.get("missing_reason") or "",
        })
    return cleaned


@frappe.whitelist(methods=["POST"])
def submit_assessment_book(request_key, book):
    """The assigned instructor submits the book for academic review.

    Submission is refused while any roster student lacks a row for any
    component: an unreported student is an explicit gap, never an implicit
    zero. Every row itself must carry a mark or a missing reason.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status not in ("Open", "Returned"):
            raise frappe.ValidationError(f"A book that is {doc.status} cannot be submitted")
        _assigned_instructor(actor, doc.student_group)
        members = roster(doc.student_group)
        _doc, version = pinned_version(
            frappe.db.get_value(POLICY, doc.policy, "code"), doc.policy_effective_from)
        components = [row["code"] for row in version_facets(version).get("components") or []]
        if not components:
            raise frappe.ValidationError("The pinned policy version configures no components")
        recorded = {}
        for row in doc.get("marks") or []:
            if row.get("mark") is None and not row.get("missing_reason"):
                raise frappe.ValidationError(
                    f"Row {row.get('student')} / {row.get('component')} carries neither "
                    "a mark nor a missing reason")
            recorded[(row.get("student"), row.get("component"))] = True
        gaps = [[student, component] for student in members
                for component in components if (student, component) not in recorded]
        if gaps:
            raise frappe.ValidationError(
                "Marks are incomplete: " + "; ".join(f"{s} / {c}" for s, c in gaps[:10])
                + (" (and more)" if len(gaps) > 10 else ""))
        doc.status = "Submitted"
        doc.submitted_by = actor
        doc.submitted_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        return _book_result(doc), {
            "target": doc.name,
            "before_hash": digest([doc.name, "Open"]),
            "after_hash": digest([doc.name, "Submitted", actor, len(recorded)]),
        }

    return _execute("submit_assessment_book", request_key, {"book": book}, work)


@frappe.whitelist(methods=["POST"])
def review_assessment_book(request_key, book, action, note=""):
    """Academic staff review a submitted book, or return it to the instructor.

    ``action`` is ``Review`` (accept for approval) or ``Return`` (send back
    for corrected marks, with a mandatory note). The instructor who submitted
    a book can never review it, even if the same login holds both roles.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status != "Submitted":
            raise frappe.ValidationError(
                f"Only a submitted book can be reviewed; this one is {doc.status}")
        if action not in ("Review", "Return"):
            raise frappe.ValidationError("Review action must be Review or Return")
        if doc.submitted_by and doc.submitted_by == actor:
            raise frappe.PermissionError(
                "The instructor who submitted a book cannot review the same book")
        clean_note = note.strip() if isinstance(note, str) else ""
        if action == "Review":
            documents = [row for row in doc.get("marks") or [] if row.get("mark") is not None]
            if not documents:
                raise frappe.ValidationError(
                    "A book with no recorded mark cannot be reviewed")
            doc.status = "Reviewed"
        else:
            if not clean_note:
                raise frappe.ValidationError("Returning a book requires a note")
            doc.status = "Returned"
        doc.reviewed_by = actor
        doc.reviewed_on = frappe.utils.now_datetime()
        doc.review_note = clean_note
        doc.save(ignore_permissions=True)
        return _book_result(doc), {
            "target": doc.name,
            "before_hash": digest([doc.name, "Submitted"]),
            "after_hash": digest([doc.name, doc.status, actor, clean_note]),
        }

    return _execute("review_assessment_book", request_key,
                    {"book": book, "action": action, "note": note}, work)


@frappe.whitelist(methods=["POST"])
def correct_assessment_mark(request_key, book, student, component, mark,
                            missing_reason="", reason=""):
    """Academic staff correct one recorded mark before approval.

    The change is applied to the live row *and* appended to the book's
    correction log with its previous value, the reason and the actor, so the
    original entry stays visible. Corrections after publication are their own
    command (they create a new published revision).
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status not in ("Submitted", "Reviewed"):
            raise frappe.ValidationError(
                f"A {doc.status} book cannot be corrected; corrections apply "
                "between submission and approval")
        clean_reason = _reason(reason, "Correction reason")
        clean_student = _text(student, "Student")
        clean_component = _text(component, "Component", 32)
        row = None
        for candidate in doc.get("marks") or []:
            if (candidate.get("student") == clean_student
                    and candidate.get("component") == clean_component):
                row = candidate
                break
        if row is None:
            raise frappe.ValidationError(
                f"No recorded mark for {clean_student} / {clean_component}")
        missing_reason_clean = missing_reason or ""
        if mark is None and not missing_reason_clean:
            raise frappe.ValidationError("Correct to a mark or to a missing reason")
        if mark is not None and missing_reason_clean:
            raise frappe.ValidationError("Correct to either a mark or a missing reason")
        if mark is not None:
            value = _number(mark, "Mark")
            if value < 0 or value > float(row.maximum_score or 0):
                raise frappe.ValidationError(
                    f"Mark must be between 0 and {float(row.maximum_score or 0):g}")
        previous = row.get("mark")
        row.mark = mark if mark is None else float(mark)
        row.missing_reason = missing_reason_clean
        row.entered_by = actor
        row.entered_on = frappe.utils.now_datetime()
        doc.append("corrections", {
            "student": clean_student, "component": clean_component,
            "previous_mark": previous,
            "new_mark": mark if mark is None else float(mark),
            "reason": clean_reason, "corrected_by": actor,
            "corrected_on": frappe.utils.now_datetime(),
        })
        doc.save(ignore_permissions=True)
        return _book_result(doc, {"corrected": [clean_student, clean_component]}), {
            "target": doc.name,
            "before_hash": digest([doc.name, clean_student, clean_component, previous]),
            "after_hash": digest([doc.name, clean_student, clean_component, mark,
                                  clean_reason]),
        }

    return _execute("correct_assessment_mark", request_key,
                    {"book": book, "student": student, "component": component,
                     "mark": mark, "missing_reason": missing_reason,
                     "reason": reason}, work)


@frappe.whitelist(methods=["POST"])
def approve_assessment_book(request_key, book, note=""):
    """Academic staff approve a reviewed book: the gate before publication.

    Approval requires a completed review (no approving a book that was never
    reviewed), and the submitting instructor can never approve their own
    book. Approval does not publish anything: publication is a separate
    authorized step so no result appears early.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status != "Reviewed":
            raise frappe.ValidationError(
                f"Only a reviewed book can be approved; this one is {doc.status}")
        if doc.submitted_by and doc.submitted_by == actor:
            raise frappe.PermissionError(
                "The instructor who submitted a book cannot approve the same book")
        doc.status = "Approved"
        doc.approved_by = actor
        doc.approved_on = frappe.utils.now_datetime()
        if isinstance(note, str) and note.strip():
            doc.review_note = note.strip()
        doc.save(ignore_permissions=True)
        return _book_result(doc), {
            "target": doc.name,
            "before_hash": digest([doc.name, "Reviewed"]),
            "after_hash": digest([doc.name, "Approved", actor]),
        }

    return _execute("approve_assessment_book", request_key, {"book": book, "note": note}, work)


# --- Publication ----------------------------------------------------------
def _student_marks(doc, student, components):
    marks = {}
    for row in doc.get("marks") or []:
        if row.get("student") == student:
            marks[row.get("component")] = {
                "mark": row.get("mark"),
                "missing_reason": row.get("missing_reason") or "",
            }
    return {code: marks.get(code, {"mark": None, "missing_reason": ""})
            for code in components}


def _plan_criteria(plan_name):
    """Native Assessment Plan criteria keyed by normalized title.

    The native plan is the scheduled instance and owns its criteria; our
    policy components are matched to those criteria by title. A component
    with no matching native criteria is refused rather than guessed.
    """
    plan = frappe.get_doc(PLAN, plan_name)
    criteria = {}
    for row in plan.get("assessment_criteria") or []:
        title = str(row.get("assessment_criteria") or "")
        if title:
            criteria[" ".join(title.lower().split())] = row
    return plan, criteria


def _native_result(doc, student, snapshot, plan_name):
    """Write the native Education Assessment Result for one published result."""
    plan, criteria = _plan_criteria(plan_name)
    maximum = plan.get("maximum_assessment_score")
    if not maximum:
        raise frappe.ValidationError(
            f"Native assessment plan {plan_name} has no maximum assessment score; "
            "the native result cannot be graded")
    details = []
    for row in snapshot["components"]:
        key = " ".join(str(row["title"]).lower().split())
        match = criteria.get(key)
        if not match:
            raise frappe.ValidationError(
                f"Component {row['component']} ({row['title']}) has no matching "
                f"Assessment Criteria on native plan {plan_name}; align the plan "
                "or the policy before publishing")
        if row["missing"]:
            raise frappe.ValidationError(
                "A missing mark cannot be published to the native assessment "
                f"plan; complete {row['component']} for this student first")
        if float(row["mark"]) > float(match.get("maximum_score") or 0):
            raise frappe.ValidationError(
                f"Mark for {row['component']} exceeds the native criteria maximum "
                f"on plan {plan_name}")
        details.append({"assessment_criteria": match.get("assessment_criteria"),
                        "score": float(row["mark"])})
    native = frappe.get_doc({
        "doctype": NATIVE_RESULT,
        "assessment_plan": plan_name,
        "program": plan.get("program"),
        "course": plan.get("course"),
        "academic_year": plan.get("academic_year"),
        "academic_term": plan.get("academic_term"),
        "student": student,
        "student_group": doc.student_group,
        "assessment_group": plan.get("assessment_group"),
        "maximum_score": float(maximum),
        "details": details,
        "comment": f"Published from assessment book {doc.name}",
    })
    native.flags.ignore_permissions = True
    native.flags.ignore_links = True
    native.insert(ignore_permissions=True)
    native.flags.ignore_permissions = True
    native.flags.ignore_links = True
    native.submit()
    if int(native.docstatus or 0) != 1:
        raise frappe.ValidationError("The native Assessment Result was not submitted")
    return native.name


def _snapshot(doc, student, facets, intervals, revision):
    """The transparent, digestible calculation snapshot for one student."""
    components = [row["code"] for row in facets.get("components") or []]
    marks = _student_marks(doc, student, components)
    snapshot = grading.compute_result(facets, marks, intervals)
    return dict(snapshot, policy={
        "policy": frappe.db.get_value(POLICY, doc.policy, "code"),
        "effective_from": str(doc.policy_effective_from),
        "digest": doc.policy_digest,
        "grading_scale": doc.get("grading_scale") or "",
    }, student=student, book=doc.name, attempt=doc.attempt, revision=revision)


def _record_result(doc, actor, version, facets, intervals, student, revision=1,
                   supersedes=None, native=""):
    """Insert the published result row for one student (already computed)."""
    snapshot = _snapshot(doc, student, facets, intervals, revision)
    attendance = _attendance_percent(student, doc.student_group)
    rule_of = {}
    for check in snapshot["checks"]:
        if check["scope"] != "overall":
            rule_of[check["scope"]] = check
    result = frappe.get_doc({
        "doctype": RESULT,
        "student": student,
        "student_group": doc.student_group,
        "level": doc.get("level") or "",
        "book": doc.name,
        "attempt": doc.attempt,
        "revision": revision,
        "status": "Published",
        "policy": doc.policy,
        "policy_effective_from": str(doc.policy_effective_from),
        "policy_digest": doc.policy_digest,
        "grading_scale": doc.get("grading_scale") or "",
        "overall_percent": snapshot["overall_percent"],
        "grade_code": snapshot["grade_code"],
        "outcome": snapshot["outcome"],
        "passed": 1 if snapshot["passed"] else 0,
        "attendance_percent": attendance,
        "snapshot_json": grading.snapshot_json(snapshot),
        "snapshot_digest": grading.snapshot_digest(snapshot),
        "supersedes": supersedes,
        "native_assessment_result": native,
        "published_by": actor,
        "published_on": frappe.utils.now_datetime(),
        "synthetic": record_synthetic_flag(),
        "components": [{
            "component": row["component"],
            "title": row["title"],
            "maximum_score": row["maximum_score"],
            "mark": row["mark"],
            "percent": row["percent"],
            "weight": row["weight"],
            "weighted_percent": row["weighted_percent"],
            "pass_rule": rule_of.get(row["component"], {}).get("target", ""),
            "pass_met": 1 if rule_of.get(row["component"], {}).get("met") else 0,
            "missing": 1 if row["missing"] else 0,
            "missing_reason": row["missing_reason"],
        } for row in snapshot["components"]],
    })
    result.insert(ignore_permissions=True)
    return result, snapshot


@frappe.whitelist(methods=["POST"])
def publish_assessment_results(request_key, book):
    """Publish an approved book: one digest-pinned result per roster student.

    Publication is refused unless the book is approved, the pinned policy
    version is still complete, every roster student has exactly the pinned
    components, and no result was already published for this book. Each
    result carries the transparent calculation snapshot (inputs, weights,
    pass rules, rounding and explanations) and, when the book names a native
    Assessment Plan, the matching native Assessment Result.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status == "Published":
            raise frappe.ValidationError(
                "Results are already published for this book; a change is an "
                "academic correction, not a second publication")
        if doc.status != "Approved":
            raise frappe.ValidationError(
                f"Results cannot be published from a {doc.status} book; "
                "approval is required first")
        if not doc.approved_by:
            raise frappe.ValidationError("Publication requires a recorded approval")
        _lock_assessment_group(doc.student_group)
        if doc.submitted_by and doc.submitted_by == doc.approved_by:
            raise frappe.PermissionError(
                "The submitting instructor cannot be the approving actor")
        policy_code = frappe.db.get_value(POLICY, doc.policy, "code")
        _doc, version = pinned_version(policy_code, doc.policy_effective_from)
        facets = version_facets(version)
        intervals = scale_intervals(doc.get("grading_scale"))
        state = grading.policy_state(facets, intervals)
        if not state["configured"]:
            raise frappe.ValidationError("; ".join(state["explanations"]))
        members = roster(doc.student_group)
        if not members:
            raise frappe.ValidationError("The class has no active students on its roster")
        published = frappe.get_all(RESULT,
                                   filters={"book": doc.name, "status": "Published"},
                                   fields=["name", "student"])
        if published:
            raise frappe.ValidationError(
                "Results are already published for this book; a change is an "
                "academic correction, not a second publication")
        # Publish-time re-check: a book opened before the first results
        # were published (or under a different policy, whose ordinal
        # restarts) must not become an unauthorized further attempt. The
        # book's own in-progress status does not count against itself.
        others = _current_published_by_student(doc.student_group,
                                               doc.get("level") or "")
        if any(row.get("book") != doc.name for row in others.values()):
            # Historical/policy-migrated books cannot reuse an old ordinal.
            highest = max(int(row.get("attempt") or 0) for row in others.values())
            if int(doc.attempt or 0) != highest + 1:
                raise frappe.ValidationError(
                    "An assessment book uses a repeated or out-of-order attempt "
                    "number for this class and level")
            allowed, reason = _retake_authorization(
                doc.student_group, doc.get("level") or "",
                frappe.utils.today(), next_attempt=int(doc.attempt),
                exclude_book=doc.name)
            if not allowed:
                raise frappe.ValidationError(reason)
        recorded = {}
        results = []
        outcomes = {"Pass": 0, "Fail": 0, "Incomplete": 0}
        for student in members:
            native = ""
            if doc.get("assessment_plan"):
                # The native Education record is written first so the link is
                # part of the published row itself; one transaction covers both.
                native = _native_result(doc, student,
                                        _snapshot(doc, student, facets, intervals, 1),
                                        doc.assessment_plan)
            result, snapshot = _record_result(doc, actor, version, facets, intervals,
                                              student, native=native)
            outcomes[snapshot["outcome"]] = outcomes.get(snapshot["outcome"], 0) + 1
            recorded[student] = result.name
            results.append({"student": student, "result": result.name,
                            "outcome": snapshot["outcome"],
                            "overall_percent": snapshot["overall_percent"],
                            "grade_code": snapshot["grade_code"],
                            "native_assessment_result": native})
        doc.status = "Published"
        doc.published_by = actor
        doc.published_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        return _book_result(doc, {"results": results, "outcomes": outcomes,
                                  "published": len(results)}), {
            "target": doc.name,
            "before_hash": digest([doc.name, "Approved"]),
            "after_hash": digest([doc.name, "Published", actor, sorted(recorded.items())]),
        }

    return _execute("publish_assessment_results", request_key, {"book": book}, work)


@frappe.whitelist(methods=["POST"])
def correct_published_result(request_key, book, student, reason, marks=None):
    """Publish a corrected revision of one student's result.

    Used after publication when a mark is found to be wrong. ``marks`` may
    carry the corrected ``{"component": ..., "mark": ...}`` rows (a missing
    mark is corrected with ``{"component": ..., "missing_reason": ...}``);
    each change is logged against the previous value with the reason. A new
    result revision is published that supersedes the previous one, and the
    previous result keeps every value it published (status ``Superseded``)
    together with the native Assessment Result it created (cancelled, never
    deleted). History therefore shows both versions and why they differ.
    """
    def work(actor):
        doc = _book_doc(_text(book, "Assessment book"), for_update=True)
        if doc.status != "Published":
            raise frappe.ValidationError(
                "Only a published book has published results to correct")
        clean_reason = _reason(reason, "Correction reason")
        clean_student = _text(student, "Student")
        if clean_student not in set(roster(doc.student_group)):
            raise frappe.ValidationError("Student is not on this class's active roster")
        current = frappe.db.get_value(RESULT,
                                      {"book": doc.name, "student": clean_student,
                                       "status": "Published"},
                                      ["name", "revision", "native_assessment_result",
                                       "attempt"], as_dict=True)
        if not current:
            raise frappe.ValidationError("No published result exists for this student")
        policy_code = frappe.db.get_value(POLICY, doc.policy, "code")
        _doc, version = pinned_version(policy_code, doc.policy_effective_from)
        facets = version_facets(version)
        intervals = scale_intervals(doc.get("grading_scale"))
        state = grading.policy_state(facets, intervals)
        if not state["configured"]:
            raise frappe.ValidationError("; ".join(state["explanations"]))
        components = {row["code"]: row for row in facets.get("components") or []}
        # The marks this student's superseded result published: every changed
        # component is logged against them, so the record shows what moved.
        before = {}
        for row in (frappe.get_doc(RESULT, current.name).get("components") or []):
            before[row.get("component")] = row.get("mark")
        logged = _apply_published_corrections(doc, actor, clean_student, components,
                                              marks, clean_reason)
        changed = [row.get("component") for row in doc.get("marks") or []
                   if row.get("student") == clean_student
                   and (row.get("mark") != before.get(row.get("component"))
                        or row.get("missing_reason"))]
        if not changed:
            raise frappe.ValidationError(
                "The correction changes no published mark; record the corrected "
                "mark with this command, or there is nothing to revise")
        revision = int(current.revision or 1) + 1
        native = ""
        if doc.get("assessment_plan"):
            native = _native_result(
                doc, clean_student,
                _snapshot(doc, clean_student, facets, intervals, revision),
                doc.assessment_plan)
        result, snapshot = _record_result(
            doc, actor, version, facets, intervals, clean_student,
            revision=revision, supersedes=current.name, native=native)
        for row in doc.get("marks") or []:
            if row.get("student") != clean_student:
                continue
            if row.get("component") in logged:
                continue
            previous = before.get(row.get("component"))
            if previous == row.get("mark"):
                continue
            doc.append("corrections", {
                "student": clean_student, "component": row.get("component"),
                "previous_mark": previous, "new_mark": row.get("mark"),
                "reason": clean_reason, "corrected_by": actor,
                "corrected_on": frappe.utils.now_datetime(),
            })
        doc.save(ignore_permissions=True)
        previous_result = frappe.get_doc(RESULT, current.name)
        previous_result.status = "Superseded"
        previous_result.superseded_by = result.name
        previous_result.save(ignore_permissions=True)
        if current.native_assessment_result:
            cancelled = frappe.get_doc(NATIVE_RESULT, current.native_assessment_result)
            cancelled.flags.ignore_permissions = True
            cancelled.cancel()
            if int(cancelled.docstatus or 0) != 2:
                raise frappe.ValidationError(
                    "The superseded native Assessment Result was not cancelled")
        return {"name": result.name, "student": clean_student,
                "revision": int(current.revision or 1) + 1,
                "supersedes": current.name, "outcome": snapshot["outcome"],
                "overall_percent": snapshot["overall_percent"],
                "grade_code": snapshot["grade_code"],
                "native_assessment_result": native}, {
            "target": result.name,
            "before_hash": digest([current.name, "Published"]),
            "after_hash": digest([result.name, "Published", current.name, clean_reason]),
        }

    return _execute("correct_published_result", request_key,
                    {"book": book, "student": student, "reason": reason,
                     "marks": marks}, work)


def _apply_published_corrections(doc, actor, student, components, marks, reason):
    """Apply the corrected marks of one student to a published book."""
    if marks in (None, []):
        return set()
    if not isinstance(marks, list) or len(marks) > MAX_ROWS:
        raise frappe.ValidationError("Corrected marks must be a list of rows")
    rows = {(row.get("student"), row.get("component")): row
            for row in doc.get("marks") or []}
    logged = set()
    for entry in marks:
        if not isinstance(entry, dict):
            raise frappe.ValidationError("Each corrected mark row must be an object")
        unknown = set(entry) - {"component", "mark", "missing_reason"}
        if unknown:
            raise frappe.ValidationError(
                "Unknown corrected mark keys: " + ", ".join(sorted(unknown)))
        component = _text(entry.get("component"), "Component", 32)
        if component not in components:
            raise frappe.ValidationError(
                f"Component {component} is not part of the pinned policy version")
        row = rows.get((student, component))
        if row is None:
            raise frappe.ValidationError(
                f"No recorded mark for {student} / {component}")
        missing_reason = entry.get("missing_reason") or ""
        mark = entry.get("mark")
        if mark is None and not missing_reason:
            raise frappe.ValidationError(
                f"Correct {student} / {component} to a mark or to a missing reason")
        if mark is not None and missing_reason:
            raise frappe.ValidationError(
                f"Correct {student} / {component} to either a mark or a missing "
                "reason")
        maximum = float(components[component]["maximum_score"])
        if mark is not None:
            value = _number(mark, "Mark")
            if value < 0 or value > maximum:
                raise frappe.ValidationError(
                    f"Mark for {student} / {component} must be between 0 and "
                    f"{maximum:g}")
        previous = row.get("mark")
        row.mark = mark if mark is None else float(mark)
        row.missing_reason = missing_reason
        row.entered_by = actor
        row.entered_on = frappe.utils.now_datetime()
        doc.append("corrections", {
            "student": student, "component": component,
            "previous_mark": previous,
            "new_mark": mark if mark is None else float(mark),
            "reason": reason, "corrected_by": actor,
            "corrected_on": frappe.utils.now_datetime(),
        })
        logged.add(component)
    return logged


# --- Read models ---------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def assessment_state(book):
    """Read-only projection of one book and the results it published."""
    require_operational()
    name = _text(book, "Assessment book")
    if not frappe.db.exists(BOOK, name):
        raise frappe.ValidationError("Unknown assessment book")
    if not frappe.has_permission(BOOK, "read", name):
        raise frappe.PermissionError("Assessment books are not available to your role")
    doc = frappe.get_doc(BOOK, name)
    results = frappe.get_all(RESULT, filters={"book": doc.name},
                             fields=["name", "student", "status", "outcome",
                                     "overall_percent", "grade_code", "revision"],
                             order_by="student asc")
    return {
        **_book_result(doc),
        "results": results,
        "marks": [{"student": row.get("student"), "component": row.get("component"),
                   "maximum_score": row.get("maximum_score"), "mark": row.get("mark"),
                   "missing_reason": row.get("missing_reason") or ""}
                  for row in doc.get("marks") or []],
    }
