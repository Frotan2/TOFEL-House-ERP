"""Equivalent row and document restrictions; never grant write via role union."""
import frappe
from toefl_house.policy import can_read
from toefl_house.security import require_operational

KINDS = {
    "TH Placement Item Revision": "item", "TH Placement Key Revision": "key",
    "TH Placement Audit Event": "audit", "TH Placement Operation": "operation",
    "TH Placement Blueprint Revision": "blueprint", "TH Placement Policy Revision": "policy",
    "TH Placement Case": "case", "TH Placement Attempt": "attempt",
    "TH Placement Form Manifest": "manifest", "TH Placement Exposure": "exposure",
    "TH Placement Allocation Guard": "guard",
    "TH Placement Response": "response",
    "TH Placement Score": "score",
    "TH Placement Course Map Revision": "course_map",
    "TH Placement Decision": "decision",
    "TH Admission Decision": "admission_decision",
    "TH Enrollment Exit": "enrollment_exit",
    "TH Instructor Contract": "contract",
    "TH Teaching Assignment": "assignment",
    "TH Correction Policy": "correction_policy",
    "TH Correction Request": "correction_request",
    "TH Attendance Correction Request": "attendance_correction",
}
TABLES = {
    "item": "`tabTH Placement Item Revision`",
    "key": "`tabTH Placement Key Revision`",
    "blueprint": "`tabTH Placement Blueprint Revision`",
    "policy": "`tabTH Placement Policy Revision`",
    "case": "`tabTH Placement Case`",
    "attempt": "`tabTH Placement Attempt`",
    "manifest": "`tabTH Placement Form Manifest`",
    "exposure": "`tabTH Placement Exposure`",
    "guard": "`tabTH Placement Allocation Guard`",
    "response": "`tabTH Placement Response`",
    "score": "`tabTH Placement Score`",
    "course_map": "`tabTH Placement Course Map Revision`",
    "decision": "`tabTH Placement Decision`",
    "admission_decision": "`tabTH Admission Decision`",
    "enrollment_exit": "`tabTH Enrollment Exit`",
    "contract": "`tabTH Instructor Contract`",
    "assignment": "`tabTH Teaching Assignment`",
    "correction_policy": "`tabTH Correction Policy`",
    "correction_request": "`tabTH Correction Request`",
    "attendance_correction": "`tabTH Attendance Correction Request`",
}
LISTED_KINDS = ("item", "blueprint", "policy", "course_map")
STAFF_ONLY_KINDS = ("case", "attempt", "manifest", "exposure", "response", "score", "decision")

# --- Branch isolation (the multi-branch operating rule) ------------------
# A user who carries a native User Permission on Branch is branch-scoped:
# on every surface below they see only the records of their own branch.
# A user WITHOUT a Branch User Permission (HQ roles, Administrator) is
# unrestricted — the native semantics: User Permissions restrict only the
# users who hold them. Records whose branch cannot be resolved are visible
# to unrestricted users only (fail closed for branch-scoped users).
#
# The branch fact lives in two native places the product already maintains:
#   * `tabStudent Group.th_branch` (custom field: class -> branch)
#   * `tabStudent Applicant.th_branch` (custom field: applicant -> branch)
# plus the class roster child table `tabStudent Group Student` (active rows
# tie a Student to a class). Placement content and configuration are
# branch-wide exam/governance infrastructure and are deliberately NOT
# branch-scoped here.
#
# BRANCH_KINDS covers every doctype that carries a resolvable branch:
#   * the four native doctypes get their own hooks below (they are not
#     synthetic-gated and have no role-based query of their own);
#   * the five guarded kinds are folded into the existing query()/has_permission
#     dispatcher so the synthetic guard and the branch rule compose.
BRANCH_KINDS = {
    "Student": "student",
    "Student Group": "student_group",
    "Student Applicant": "student_applicant",
    "Program Enrollment": "program_enrollment",
    "TH Admission Decision": "admission_decision",
    "TH Enrollment Exit": "enrollment_exit",
    "TH Teaching Assignment": "assignment",
    "TH Correction Request": "correction_request",
    "TH Attendance Correction Request": "attendance_correction",
}

# The four native doctypes that gain their OWN hooks for branch isolation
# (they are not synthetic-gated and have no role-based query of their own).
# The exact-coverage assembly test documents them as this separate set.
BRANCH_NATIVE_DOCTYPES = ("Student", "Student Group", "Student Applicant",
                          "Program Enrollment")

# Roster child table: active rows tie a Student to a class (Student Group),
# which carries the branch. The single source for "which branch a student is
# in" used by every branch check below.
_ROSTER_BRANCH_SQL = (
    "SELECT sg.th_branch FROM `tabStudent Group Student` rs "
    "JOIN `tabStudent Group` sg ON sg.name = rs.parent "
    "WHERE rs.active = 1 AND rs.student = %s"
)


def _user_branches(user):
    """The branches a user is scoped to via native User Permissions.

    ``None``  -> the user is NOT branch-scoped: they carry no Branch User
                 Permission (HQ roles, Administrator). Unrestricted — the
                 native User Permission semantics: a permission restricts
                 only the users who hold it.
    non-None  -> the user IS branch-scoped to exactly this list of branches.
                 An EMPTY list is the fail-closed degenerate (scoped, but to
                 no branch): branch-scoped surfaces return nothing for them.
    """
    if user == "Administrator":
        return None
    rows = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Branch", "block": 0},
        pluck="for_value",
        limit_page_length=100,
    )
    if not rows:
        return None  # no Branch User Permission at all -> unrestricted
    seen, branches = set(), []
    for value in rows:
        if value and value not in seen:
            seen.add(value)
            branches.append(value)
    return branches


def _in_branches_sql(branches):
    return ", ".join(frappe.db.escape(branch) for branch in branches)


def _student_branch_condition(student_field, branches):
    """SQL condition: the record's student (via ``student_field``) is rostered
    in one of the user's branches."""
    b = _in_branches_sql(branches)
    return (f"EXISTS (SELECT 1 FROM `tabStudent Group Student` rs "
            f"JOIN `tabStudent Group` sg ON sg.name = rs.parent "
            f"WHERE rs.active = 1 AND rs.student = {student_field} "
            f"AND sg.th_branch IN ({b}))")


def _branch_condition(kind, branches):
    """SQL fragment restricting a row to the user's branches, per kind.

    ``None`` is returned only for kinds that are not branch-scoped. A
    branch-scoped kind whose branch cannot be resolved yields ``1=0``
    (fail closed for branch-scoped users).
    """
    b = _in_branches_sql(branches)
    if kind == "student":
        return _student_branch_condition("`tabStudent`.name", branches)
    if kind == "student_group":
        return f"`tabStudent Group`.th_branch IN ({b})"
    if kind == "student_applicant":
        return f"`tabStudent Applicant`.th_branch IN ({b})"
    if kind == "program_enrollment":
        return _student_branch_condition("`tabProgram Enrollment`.student", branches)
    if kind == "admission_decision":
        t = "`tabTH Admission Decision`"
        return (f"({t}.student_applicant IN (SELECT name FROM `tabStudent Applicant` WHERE th_branch IN ({b})) "
                f"OR {_student_branch_condition(t + '.existing_student', branches)} "
                f"OR {_student_branch_condition(t + '.native_student', branches)})")
    if kind == "enrollment_exit":
        return _student_branch_condition("`tabTH Enrollment Exit`.student", branches)
    if kind == "assignment":
        return (f"`tabTH Teaching Assignment`.student_group IN "
                f"(SELECT name FROM `tabStudent Group` WHERE th_branch IN ({b}))")
    if kind == "correction_request":
        return (f"`tabTH Correction Request`.fees IN (SELECT name FROM `tabFees` "
                f"WHERE {_student_branch_condition('`tabFees`.student', branches)})")
    if kind == "attendance_correction":
        return (f"`tabTH Attendance Correction Request`.course_schedule IN "
                f"(SELECT name FROM `tabCourse Schedule` WHERE student_group IN "
                f"(SELECT name FROM `tabStudent Group` WHERE th_branch IN ({b})))")
    return None


def _student_branches(student):
    """The branches a Student is actively rostered in (a set of names)."""
    if not student:
        return set()
    rows = frappe.db.sql(_ROSTER_BRANCH_SQL, (student,), as_dict=True)
    return {row.th_branch for row in rows if row.th_branch}


def _doc_branches(doc, kind):
    """The branches a concrete document resolves to (a set of names).

    An empty set means the branch is unresolvable: a branch-scoped user
    cannot see the document (fail closed).
    """
    if kind == "student_group" or kind == "student_applicant":
        branch = doc.get("th_branch")
        return {branch} if branch else set()
    if kind == "student":
        return _student_branches(doc.name)
    if kind in ("program_enrollment", "enrollment_exit"):
        return _student_branches(doc.get("student"))
    return set()


def _doc_branches_guarded(doc, kind):
    """Branch resolution for the five GUARDED kinds (via their link fields)."""
    if kind == "admission_decision":
        branches = set()
        if doc.get("student_applicant"):
            branch = frappe.db.get_value("Student Applicant", doc.student_applicant, "th_branch")
            if branch:
                branches.add(branch)
        branches |= _student_branches(doc.get("existing_student"))
        branches |= _student_branches(doc.get("native_student"))
        return branches
    if kind == "enrollment_exit":
        return _doc_branches(doc, kind)
    if kind == "assignment":
        group = doc.get("student_group")
        if not group:
            return set()
        branch = frappe.db.get_value("Student Group", group, "th_branch")
        return {branch} if branch else set()
    if kind == "correction_request":
        if not doc.get("fees"):
            return set()
        return _student_branches(frappe.db.get_value("Fees", doc.fees, "student"))
    if kind == "attendance_correction":
        branches = set()
        if doc.get("course_schedule"):
            group = frappe.db.get_value("Course Schedule", doc.course_schedule, "student_group")
            if group:
                branch = frappe.db.get_value("Student Group", group, "th_branch")
                if branch:
                    branches.add(branch)
        if doc.get("attendance"):
            group = frappe.db.get_value("Student Attendance", doc.attendance, "student_group")
            if group:
                branch = frappe.db.get_value("Student Group", group, "th_branch")
                if branch:
                    branches.add(branch)
        return branches
    return set()


def branch_has_permission(doc, ptype=None, user=None, **kwargs):
    """Branch gate for the four native doctypes.

    Adds the branch rule ON TOP of the native evaluation: Frappe checks the
    controller hook first, then the role permissions, then User Permissions
    (verified at the pinned frappe commit), so native authority is never
    widened here. A branch-scoped user with an unresolvable branch sees
    nothing (a Student gains its branch when rostered into a class).
    """
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    branches = _user_branches(user)
    if branches is None:
        return True
    if not branches:
        return False
    return bool(_doc_branches(doc, BRANCH_KINDS[doc.doctype]) & set(branches))


def _branch_query(kind, user=None):
    """permission_query_conditions for the four native branch doctypes:
    the branch rule only — native role permissions still gate the list."""
    user = user or frappe.session.user
    if user in (None, "Guest"):
        return "1=0"
    branches = _user_branches(user)
    if branches is None:
        return "1=1"
    if not branches:
        return "1=0"
    return _branch_condition(kind, branches) or "1=0"


def branch_query_student(user=None):
    return _branch_query("student", user)


def branch_query_student_group(user=None):
    return _branch_query("student_group", user)


def branch_query_student_applicant(user=None):
    return _branch_query("student_applicant", user)


def branch_query_program_enrollment(user=None):
    return _branch_query("program_enrollment", user)


CONFIGURATION_READERS = ("Course Owner", "General Manager", "Academic Manager", "Finance Manager", "Finance Officer", "Finance Auditor", "Teaching Scheduler", "Teaching Auditor")

# Governance configuration (the Academic Control Plane): deliberately NOT in
# the synthetic-guarded DOCTYPES world. These records are governance state,
# readable by management roles, mutable only through the guarded
# toefl_house.academic commands (docs/CONFIGURATION-PLANE.md).
# The configuration audit ledger (Operation receipts + Audit Events) is
# governed the same way: it trails the configuration, so it shares the
# configuration's readership (mirroring how native Version rows inherit
# their document's readers) and is read-only for every role.
GOVERNANCE_DOCTYPES = {"TH Academic Program", "TH Program Level", "TH Discount Rule", "TH Skill",
                        "TH Assessment Policy", "TH Returning Student Policy",
                        "TH Roster Change Policy",
                        "TH Attendance Correction Policy",
                        "TH Enrollment Exit Policy",
                        "TH Billing Policy",
                        "TH Catalog Linkage Policy",
                        "TH Adjustment Posting Policy",
                        "TH Alerting Policy",
                        "TH Guardian Lifecycle Policy",
                        "TH Configuration Operation", "TH Configuration Audit Event"}


def configuration_has_permission(doc, ptype=None, user=None, **kwargs):
    """Governance reads for the Academic Control Plane.

    Deliberately NOT synthetic-gated: configuration is governance state, the
    same boundary as toefl_house.administration. Writes never flow through
    native forms-of-convenience: only the guarded toefl_house.academic
    commands (Course Owner gate) and the doctype permissions (no delete for
    anyone) open change paths.
    """
    user = user or frappe.session.user
    if user in (None, "Guest"):
        return False
    if user == "Administrator":
        return True
    return ptype in (None, "read", "select") and bool(
        set(frappe.get_roles(user)) & set(CONFIGURATION_READERS))


def configuration_query(user=None):
    user = user or frappe.session.user
    if user in (None, "Guest"):
        return "1=0"
    if user == "Administrator":
        return "1=1"
    return "1=1" if set(frappe.get_roles(user)) & set(CONFIGURATION_READERS) else "1=0"


def has_permission(doc, ptype=None, user=None, **kwargs):
    # D16: the same role rules govern reads on the synthetic qualification
    # sites and on the activated production site; refused sites read nothing.
    try:
        require_operational()
    except frappe.PermissionError:
        return False
    user = user or frappe.session.user
    if not (ptype in (None, "read", "select")
            and can_read(KINDS[doc.doctype], frappe.get_roles(user), user, doc.owner, doc.get("status"))):
        return False
    kind = KINDS[doc.doctype]
    if kind not in BRANCH_KINDS.values():
        return True
    branches = _user_branches(user)
    if branches is None:
        return True
    if not branches:
        return False
    return bool(_doc_branches_guarded(doc, kind) & set(branches))


def query(kind, user=None):
    """Role condition composed with the branch rule (when the kind is
    branch-scoped and the user is branch-scoped). Refused sites read nothing,
    as before."""
    try:
        require_operational()
    except frappe.PermissionError:
        return "1=0"
    base = _query_role(kind, user)
    if kind not in BRANCH_KINDS.values():
        return base
    user = user or frappe.session.user
    branches = _user_branches(user)
    if branches is None:
        return base
    if not branches:
        return "1=0"
    return f"({base}) AND {_branch_condition(kind, branches) or '1=0'}"


def _query_role(kind, user=None):
    try:
        require_operational()
    except frappe.PermissionError:
        return "1=0"
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if kind == "guard":
        return "1=0"
    if kind == "admission_decision":
        return "1=1" if roles & {"Admission Officer", "Admission Reviewer",
                                 "Admission Approver", "Admission Auditor"} else "1=0"
    if kind in ("audit", "operation"):
        return "1=1" if roles & {"Placement Auditor", "Admission Auditor", "Enrollment Auditor",
                                 "Teaching Auditor", "Finance Auditor"} else "1=0"
    # D2 compensation records are finance-sensitive: evaluated before the
    # Placement Publisher fall-through so placement breadth never reaches them.
    if kind == "contract":
        return "1=1" if roles & {"Finance Officer", "Finance Auditor"} else "1=0"
    if kind == "assignment":
        return "1=1" if roles & {"Teaching Scheduler", "Teaching Auditor",
                                 "Finance Officer", "Finance Auditor"} else "1=0"
    if kind in ("correction_policy", "correction_request"):
        return "1=1" if roles & {"Finance Officer", "Finance Auditor"} else "1=0"
    if kind == "attendance_correction":
        return "1=1" if roles & {"Attendance Recorder", "Teaching Auditor"} else "1=0"
    if kind == "enrollment_exit":
        return "1=1" if roles & {"Enrollment Officer", "Enrollment Auditor"} else "1=0"
    if "Placement Publisher" in roles:
        return "1=1"
    if kind in ("case", "attempt", "exposure", "response") and "Placement Invigilator" in roles:
        return "1=1"
    if kind in ("case", "attempt", "response", "score") and "Placement Assessor" in roles:
        return "1=1"
    if kind in ("case", "attempt", "response", "score") and "Placement Reviewer" in roles:
        return "1=1"
    if kind in ("case", "attempt", "response", "score", "decision") and "Placement Releaser" in roles:
        return "1=1"
    if kind in STAFF_ONLY_KINDS:
        return "1=1" if "Placement Auditor" in roles else "1=0"
    table = TABLES[kind]
    conditions = []
    if "Placement Author" in roles:
        conditions.append(f"{table}.owner = {frappe.db.escape(user)}")
    if kind in LISTED_KINDS and roles & {"Placement Author", "Placement Auditor"}:
        conditions.append(f"{table}.status = 'Published'")
    return "(" + " OR ".join(conditions) + ")" if conditions else "1=0"


def query_item(user=None): return query("item", user)
def query_key(user=None): return query("key", user)
def query_audit(user=None): return query("audit", user)
def query_operation(user=None): return query("operation", user)
def query_blueprint(user=None): return query("blueprint", user)
def query_policy(user=None): return query("policy", user)
def query_case(user=None): return query("case", user)
def query_attempt(user=None): return query("attempt", user)
def query_manifest(user=None): return query("manifest", user)
def query_exposure(user=None): return query("exposure", user)
def query_guard(user=None): return query("guard", user)
def query_response(user=None): return query("response", user)
def query_score(user=None): return query("score", user)
def query_course_map(user=None): return query("course_map", user)
def query_decision(user=None): return query("decision", user)
def query_admission_decision(user=None): return query("admission_decision", user)
def query_contract(user=None): return query("contract", user)
def query_assignment(user=None): return query("assignment", user)
def query_correction_policy(user=None): return query("correction_policy", user)
def query_correction_request(user=None): return query("correction_request", user)
def query_attendance_correction(user=None): return query("attendance_correction", user)
def query_enrollment_exit(user=None): return query("enrollment_exit", user)
