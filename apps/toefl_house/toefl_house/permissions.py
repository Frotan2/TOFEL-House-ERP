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


CONFIGURATION_READERS = ("Course Owner", "General Manager", "Academic Manager", "Finance Manager", "Finance Officer", "Finance Auditor", "Teaching Scheduler", "Teaching Auditor")

# Governance configuration (the Academic Control Plane): deliberately NOT in
# the synthetic-guarded DOCTYPES world. These records are governance state,
# readable by management roles, mutable only through the guarded
# toefl_house.academic commands (docs/product/CONFIGURATION-PLANE.md).
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
                        "TH Metric Stewardship Policy",
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
    return ptype in (None, "read", "select") and can_read(KINDS[doc.doctype], frappe.get_roles(user), user, doc.owner, doc.get("status"))


def query(kind, user=None):
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
