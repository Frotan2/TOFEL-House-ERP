"""Transaction-private native reference reads for guarded cash posting.

Native Payment Entry calls permission-checked reference readers. These exact
read-only DocShare rows exist only in the posting transaction, are deleted
before commit, and never notify/share with another user. No role, framework
function, identity or global permission flag is changed. A commit guard makes
an unexpected native commit fail before a temporary permission can persist.
"""
from contextlib import contextmanager
from contextvars import ContextVar

import frappe

from toefl_house.security import KIND_ROLES, active_command_kind, authorize

_LEASE = ContextVar("toefl_house_collection_reference_lease", default=None)
READ_COMMANDS = frozenset({"record_reception_collection", "correct_reception_collection", "pay_tuition_refund"})


def _forbid_lease_commit():
    if _LEASE.get() is not None:
        raise frappe.PermissionError("Cash posting cannot commit temporary reference permissions")


@contextmanager
def native_reference_reads(references):
    kind = active_command_kind()
    if kind not in READ_COMMANDS or _LEASE.get() is not None:
        raise frappe.PermissionError("Reference reads require the guarded collection command")
    actor = authorize(KIND_ROLES[kind])
    references = sorted(set(references))
    if kind == "pay_tuition_refund":
        from toefl_house.finance.tuition_refund_native import assert_reference_lease
        assert_reference_lease(references)
    if (not references or len(references) > 4
            or any(dt not in {"Fees", "Student"} or not isinstance(name, str)
                   or not name or len(name) > 140 for dt, name in references)):
        raise frappe.PermissionError("Cash posting references must be exact fees and students")
    from toefl_house.command_scope import authorize_command_scope
    fees = {name for doctype, name in references if doctype == "Fees"}
    students = {name for doctype, name in references if doctype == "Student"}
    expected = {frappe.db.get_value("Fees", name, "student") for name in fees}
    if not fees or None in expected or students != expected:
        raise frappe.PermissionError("Reference students must belong to the selected fees")
    if kind != "pay_tuition_refund":
        for name in fees:
            authorize_command_scope(kind, {"fees": name}, actor)
    # Refunds already rechecked the exact request + Fees + Student above.
    # Its Company-scoped authority requires that context-bound request, so
    # do not replace the complete proof with an incomplete Fees-only payload.
    created = []
    state = {"clean": False}

    def forbid_unclean_commit():
        _forbid_lease_commit()
        if not state["clean"]:
            raise frappe.PermissionError("Temporary reference permission cleanup is incomplete")

    token = _LEASE.set((actor, tuple(references)))
    try:
        frappe.db.before_commit.add(forbid_unclean_commit)
        for doctype, name in references:
            if frappe.db.exists("DocShare", {"user": actor, "share_doctype": doctype,
                                             "share_name": name, "read": 1}):
                continue
            # These are not user-facing shares: controller insert/delete would
            # produce misleading Shared/Unshared comments and notifications.
            # Fixed read-only rows use the native ACL table and same InnoDB
            # transaction as the native posting; other connections cannot see
            # them. Never mutate an existing share or use everyone/write rights.
            row = frappe.get_doc(dict(doctype="DocShare", name=frappe.generate_hash(length=20),
                user=actor, share_doctype=doctype, share_name=name,
                read=1, write=0, submit=0, share=0, everyone=0, notify_by_email=0))
            row.db_insert()
            created.append(row.name)
        yield
    finally:
        try:
            if created:
                frappe.db.delete("DocShare", {"name": ("in", created)})
                if frappe.db.count("DocShare", {"name": ("in", created)}):
                    raise frappe.PermissionError("Temporary reference permissions could not be removed")
            state["clean"] = True
        finally:
            _LEASE.reset(token)
