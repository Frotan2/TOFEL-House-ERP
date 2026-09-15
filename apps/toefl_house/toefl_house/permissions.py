"""Equivalent row and document restrictions; never grant write via role union."""
import frappe
from toefl_house.policy import can_read
from toefl_house.security import require_synthetic

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
}
LISTED_KINDS = ("item", "blueprint", "policy", "course_map")
STAFF_ONLY_KINDS = ("case", "attempt", "manifest", "exposure", "response", "score", "decision")


def has_permission(doc, ptype=None, user=None, **kwargs):
    try:
        require_synthetic()
    except frappe.PermissionError:
        return False
    user = user or frappe.session.user
    return ptype in (None, "read", "select") and can_read(KINDS[doc.doctype], frappe.get_roles(user), user, doc.owner, doc.get("status"))


def query(kind, user=None):
    try:
        require_synthetic()
    except frappe.PermissionError:
        return "1=0"
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if kind == "guard":
        return "1=0"
    if kind in ("audit", "operation"):
        return "1=1" if "Placement Auditor" in roles else "1=0"
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
