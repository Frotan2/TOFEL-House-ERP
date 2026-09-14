"""Equivalent row and document restrictions; never grant write via role union."""
import frappe
from toefl_house.policy import can_read
from toefl_house.security import require_synthetic

KINDS = {"TH Placement Item Revision": "item", "TH Placement Key Revision": "key",
         "TH Placement Audit Event": "audit", "TH Placement Operation": "operation"}


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
    if kind in ("audit", "operation"):
        return "1=1" if "Placement Auditor" in roles else "1=0"
    if "Placement Publisher" in roles:
        return "1=1"
    table = "`tabTH Placement Item Revision`" if kind == "item" else "`tabTH Placement Key Revision`"
    conditions = []
    if "Placement Author" in roles:
        conditions.append(f"{table}.owner = {frappe.db.escape(user)}")
    if kind == "item" and roles & {"Placement Author", "Placement Auditor"}:
        conditions.append(f"{table}.status = 'Published'")
    return "(" + " OR ".join(conditions) + ")" if conditions else "1=0"


def query_item(user=None): return query("item", user)
def query_key(user=None): return query("key", user)
def query_audit(user=None): return query("audit", user)
def query_operation(user=None): return query("operation", user)
