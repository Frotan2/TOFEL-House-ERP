"""Refuse a second submitted Salary Slip for one employee, one worked period.

U-09 (2026-11-05) was fixed only in worked-month reporting
(``teaching/payroll_periods.py``: ``worked_month_payroll`` raises on a
second submitted slip for the same employee in the same worked period),
and no production code calls that function: it takes caller-supplied rows
and is exercised only by tests/teaching/test_shamsi_payroll_periods.py.
Native HRMS owns Salary Slip creation and submission, and this app
registered no doc_event for "Salary Slip" (hooks.py), so a duplicate slip
could be submitted natively and the reporting function would only notice
afterwards, if anyone ran it.

This module is the owned boundary that closes that gap: a doc_event guard
(hooks.py: "Salary Slip", ``validate`` + ``before_submit`` +
``before_cancel`` + ``before_update_after_submit``) enforcing per-employee
+ exact-period uniqueness at the submission boundary itself. It uses Frappe's own
doc_events mechanism on a native doctype, exactly as this app already does
for "User" (identity_links) and "Program Enrollment" (enrollment guard);
no hook point is invented. The ``before_cancel`` seam is pinned to the
same function (A13 three-seam rule) but is a no-op inside it: cancelling
can only remove a duplicate, and refusing a cancel would strand
pre-existing legacy duplicates (see the function docstring).

Scope, deliberately narrow (mirrors the U-09 reporting rule):
- Refuses only an exact duplicate: same employee, same ``start_date``,
  same ``end_date``, the other slip submitted (``docstatus=1``).
- Overlapping-but-different periods stay legitimate native cases
  (partial-month slips, corrections) and remain flagged at reconciliation
  by ``worked_month_payroll``.
- A cancelled slip (``docstatus=2``) does not block its replacement.

Concurrency: concurrent submissions for the same employee serialize on
the Employee row lock (``SELECT ... FOR UPDATE``). The duplicate re-read
runs after the lock wait, so a duplicate that commits first is visible to
the waiter. The duplicate rows themselves are also read ``FOR UPDATE``,
so a concurrent cancellation of the duplicate commits first and the
re-read then sees no submitted duplicate. A lock-order deadlock between
two concurrent Payroll Entry runs fails closed (one transaction aborts
and must retry); no duplicate can commit through it.

Residual (not closed here): enforcement is application-level. There is
no database-level unique constraint on
``(employee, start_date, end_date)`` for Salary Slip, because that would
be a schema change on a native HRMS table; a writer that bypasses
Frappe's document layer entirely (direct SQL) is outside this guard, as
it is outside every doc_event guard in this app.
"""
import frappe

SALARY_SLIP = "Salary Slip"


def refuse_duplicate_worked_month_slip(doc, method=None):
    """Refuse a Salary Slip that duplicates an already-submitted one.

    Runs on ``validate`` (earliest refusal, including draft creation while
    a submitted duplicate exists), ``before_submit`` (re-check at submit
    time, covering a duplicate submitted after this draft was saved), and
    ``before_update_after_submit`` (a post-submit date edit must not
    create a duplicate either). Read-only: it never writes a slip.

    ``before_cancel`` is pinned to the same function (the A13 three-seam
    rule in tests/foundation/test_app_assembly.py requires one guard on
    all three seams) but is a deliberate no-op here: cancelling a slip
    can only *remove* a duplicate, never create one. Refusing a cancel
    when another submitted duplicate exists would strand pre-existing
    legacy duplicates — neither slip of the pair could ever be cancelled,
    which is exactly the remediation a duplicate needs. This matches the
    codebase's own pattern (finance guards exempt cancellation the same
    way, e.g. collections.py and student_payout_policy.py).
    """
    if method == "before_cancel":
        return
    employee = doc.get("employee") or ""
    start = doc.get("start_date") or ""
    end = doc.get("end_date") or ""
    name = doc.get("name") or ""
    if not employee or not start or not end:
        # A slip without its identifying fields cannot be submitted:
        # native mandatory validation refuses it. This guard owns
        # duplicates, not completeness, so it stays silent here and lets
        # native validation speak.
        return
    locked = frappe.db.sql(
        "select name from `tabEmployee` where name=%s for update",
        (employee,))
    if not locked:
        raise frappe.ValidationError(
            "Unknown employee for Salary Slip; resolve the employee "
            "before submitting")
    duplicates = frappe.db.sql(
        "select name from `tabSalary Slip` "
        "where employee=%s and start_date=%s and end_date=%s "
        "and docstatus=1 and name!=%s for update",
        (employee, str(start), str(end), name))
    if duplicates:
        raise frappe.ValidationError(
            "A submitted Salary Slip already exists for this employee for "
            f"the same period ({start} to {end}); resolve the duplicate "
            "slip before submitting")
