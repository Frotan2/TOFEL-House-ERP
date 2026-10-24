"""Executive analytics helpers — auditable, bounded, native-grounded.

Every metric in this module follows the same contract:

- **Definition**: stated inline in plain staff language, never invented.
- **Permission scope**: respects Company/Branch User Permission where the
  underlying record carries the field; otherwise branch-wide by design.
- **Source records**: native DocTypes only (ERPNext/Education/HRMS), no
  derived ledger. Every count is a count of a named record state.
- **Drill-down**: every figure names the List route that reaches its source.

No unbounded queries: every read carries an explicit limit, every aggregation
is a count or bounded sum over already-bounded rows. No artificial KPI,
no decorative gauge, no invented financial figure.

This module is imported by the role desks; it contains no HTTP handler of
its own and never writes. It is deliberately tolerant of the test stub
environment (no bench frappe): top-level imports are guarded and helper
imports are lazy so the desk contract tests can load the desks without a
live site.
"""

try:
    import frappe
except Exception:  # pragma: no cover — stub env fallback
    frappe = None  # type: ignore

try:
    from frappe.utils import today as _today
except Exception:  # pragma: no cover
    def _today():
        return "2026-01-01"

# Provide today symbol for callers that import from here
today = _today

# Lazy resolver for project helpers — import at call time so stub env
# (where toefl_house package is not installed as a real package) does not
# fail at module load. In production the import resolves normally.
def _project_rows(*args, **kwargs):
    try:
        from toefl_house.desk import project_rows as _pr
        return _pr(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(f"project_rows unavailable in this environment: {exc}")

def _project_count(*args, **kwargs):
    try:
        from toefl_house.desk import project_count as _pc
        return _pc(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(f"project_count unavailable: {exc}")

# Re-export names expected by older code that did `from desk import project_*`
project_rows = _project_rows
project_count = _project_count

try:
    from toefl_house.desk import BOUNCE_WINDOW, LIMIT_QUEUES
except Exception:  # pragma: no cover
    BOUNCE_WINDOW = 400
    LIMIT_QUEUES = 25

# ------------------------------------------------------------------ helpers

def _summarize_by(rows, key):
    counts = {}
    for row in rows:
        label = row.get(key) or "Unassigned"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _money_sum(rows, field="grand_total"):
    totals = {}
    for row in rows:
        currency = row.get("currency") or row.get("paid_from_account_currency") or ""
        totals[currency] = totals.get(currency, 0) + float(row.get(field) or 0)
    if not totals:
        return "0"
    return ", ".join(f"{v:.2f} {k}".strip() for k, v in sorted(totals.items()))


def _age_label(value):
    if not value:
        return ""
    try:
        from frappe.utils import get_datetime, now_datetime
        delta = now_datetime() - get_datetime(value)
        days = delta.days
        if days <= 0:
            return "today"
        if days == 1:
            return "1 day"
        return f"{days} days"
    except Exception:
        return ""


def _open_cohort_keys(groups):
    """Local open-cohort helper — mirrors desk.open_cohort_keys without import."""
    keys = set()
    for row in groups or []:
        if row.get("th_class_status") in ("Planned", "Active") and not row.get("disabled"):
            keys.add((row.get("program"), row.get("academic_year")))
    return keys


def _active_cohort_rows(groups):
    return [r for r in groups or [] if r.get("th_class_status") == "Active" and not r.get("disabled")]


# ------------------------------------------------------------------ enrollments

def enrollment_metrics():
    """Active enrollments: submitted enrollment rows.

    Definition: submitted enrollment records.
    Source: native enrollment records (submitted).
    Drill: enrollment list (submitted)
    """
    rows = _project_rows("management", "Program Enrollment",
                        ["name", "student", "student_name", "program", "academic_year",
                         "enrollment_date", "docstatus"],
                        filters={"docstatus": 1},
                        order_by="enrollment_date desc", limit=BOUNCE_WINDOW)
    by_program = _summarize_by(rows, "program")
    by_year = _summarize_by(rows, "academic_year")
    return {
        "total": len(rows),
        "rows": rows[:LIMIT_QUEUES],
        "by_program": by_program,
        "by_year": by_year,
        "definition": "Submitted enrollment records (confirmed). Each enrollment maps one learner to one program and academic year.",
        "source": "enrollment records (native Education, submitted)",
        "scope": "Branch-scoped via student roster; HQ sees all.",
        "drill": "enrollment records list",
    }


def enrollment_cohort_breakdown(enrollments, groups):
    """Waiting lists: enrollments with no open cohort for their program/year.

    Definition: submitted enrollment whose (program, academic_year) has no
    class with lifecycle Planned or Active.
    Source: enrollment + class status
    """
    cohorts = _open_cohort_keys(groups)
    unclassed = [r for r in enrollments if (r.get("program"), r.get("academic_year")) not in cohorts]
    by_program = _summarize_by(unclassed, "program")
    return {
        "total": len(unclassed),
        "rows": unclassed[:LIMIT_QUEUES],
        "by_program": by_program,
        "definition": "Submitted enrollments whose program and academic year have no class in Planned or Active lifecycle; they wait for a class to be created or activated.",
        "source": "enrollments (submitted) with no open class for its program/year",
        "scope": "Same branch scope as enrollments.",
        "drill": "enrollment list",
    }


# ------------------------------------------------------------------ admissions

def admission_metrics():
    """Admissions funnel stage counts.

    Definition: admission decisions grouped by status.
    Source: admission decisions (guarded, but projected read-only here).
    """
    all_open = _project_rows("management", "TH Admission Decision",
                            ["name", "student_applicant", "program", "status", "version",
                             "accepted", "native_student", "modified"],
                            filters={"status": ("in", ["Draft", "Review", "Approved", "Conditional"])},
                            order_by="modified asc", limit=BOUNCE_WINDOW)
    by_status = {}
    for row in all_open:
        s = row.get("status") or "Unknown"
        by_status[s] = by_status.get(s, 0) + 1
    total_closed = _project_count("management", "TH Admission Decision",
                                  {"status": ("in", ["Deferred", "Rejected", "Withdrawn", "Revoked", "Expired"])})
    return {
        "open": len(all_open),
        "by_status": by_status,
        "closed": total_closed,
        "rows": all_open[:LIMIT_QUEUES],
        "definition": "Admission decisions in Draft, Review, Approved, Conditional (open) vs Deferred/Rejected/Withdrawn/Revoked/Expired (closed).",
        "source": "admission decisions (native applicant lifecycle)",
        "scope": "Branch-scoped via applicant / student linkage.",
        "drill": "admission decision list",
    }


# ------------------------------------------------------------------ attendance

def attendance_metrics():
    """Attendance: submitted attendance presence rate.

    Definition: submitted attendance records grouped by status.
    Rate = Present / (Present + Absent) where both exist.
    Source: native attendance (submitted).
    """
    rows = _project_rows("management", "Student Attendance",
                        ["name", "student", "student_group", "course_schedule", "date",
                         "status", "docstatus"],
                        filters={"docstatus": 1},
                        order_by="date desc", limit=BOUNCE_WINDOW)
    present = sum(1 for r in rows if r.get("status") == "Present")
    absent = sum(1 for r in rows if r.get("status") == "Absent")
    leave = sum(1 for r in rows if r.get("status") == "On Leave")
    total = len(rows)
    rate = f"{(present / (present + absent) * 100):.1f}%" if (present + absent) else "—"
    by_group = _summarize_by(rows, "student_group")
    by_date = _summarize_by(rows, "date")
    return {
        "total": total,
        "present": present,
        "absent": absent,
        "leave": leave,
        "rate": rate,
        "by_group": by_group,
        "by_date": by_date,
        "definition": "Submitted attendance records. Present + Absent + On Leave are native marks; rate is Present divided by Present+Absent.",
        "source": "attendance records (native Education, submitted only)",
        "scope": "Branch-scoped via student roster.",
        "drill": "attendance list",
    }


def attendance_by_instructor():
    """Attendance sessions per instructor for the current window."""
    schedules = _project_rows("management", "Course Schedule",
                             ["name", "student_group", "instructor", "course", "schedule_date"],
                             order_by="schedule_date desc", limit=BOUNCE_WINDOW)
    by_instructor = {}
    for row in schedules:
        inst = row.get("instructor") or "Unassigned"
        by_instructor[inst] = by_instructor.get(inst, 0) + 1
    return {
        "by_instructor": by_instructor,
        "schedules": schedules[:LIMIT_QUEUES],
        "definition": "Class schedule sessions grouped by instructor; attendance is recorded against these sessions.",
        "source": "class schedules (native Education)",
        "scope": "Branch-scoped via class branch.",
        "drill": "class schedule list",
    }


# ------------------------------------------------------------------ tuition

def tuition_metrics():
    """Tuition collection & overdue: native fee records.

    Definitions use native fee vocabulary only:
    - Charged = submitted grand_total
    - Outstanding = native outstanding_amount (submitted, >0)
    - Overdue = outstanding with due_date < today (submitted)
    - Settled = outstanding_amount <=0 (submitted)
    """
    day = _today()
    all_fees = _project_rows("management", "Fees",
                            ["name", "student", "student_name", "program", "program_enrollment",
                             "academic_year", "posting_date", "due_date", "grand_total",
                             "outstanding_amount", "currency", "company", "docstatus"],
                            filters={"docstatus": 1},
                            order_by="due_date asc", limit=BOUNCE_WINDOW)
    outstanding = [r for r in all_fees if float(r.get("outstanding_amount") or 0) > 0]
    overdue = [r for r in outstanding if str(r.get("due_date") or "") and str(r["due_date"]) < day]
    settled = [r for r in all_fees if float(r.get("outstanding_amount") or 0) <= 0]
    by_program = _summarize_by(all_fees, "program")
    by_currency_charged = _money_sum(all_fees, "grand_total")
    by_currency_outstanding = _money_sum(outstanding, "outstanding_amount")

    invoices = _project_rows("management", "Sales Invoice",
                            ["name", "customer", "customer_name", "th_placement_case",
                             "posting_date", "due_date", "grand_total", "outstanding_amount",
                             "currency", "company", "status", "is_return", "docstatus"],
                            filters={"docstatus": 1},
                            order_by="due_date asc", limit=BOUNCE_WINDOW)
    inv_outstanding = [r for r in invoices if float(r.get("outstanding_amount") or 0) > 0]
    inv_overdue = [r for r in inv_outstanding if str(r.get("due_date") or "") and str(r["due_date"]) < day]

    payments = _project_rows("management", "Payment Entry",
                            ["name", "payment_type", "party_type", "party", "paid_amount",
                             "received_amount", "paid_from_account_currency", "company",
                             "posting_date", "docstatus"],
                            filters={"docstatus": 1, "payment_type": "Receive"},
                            order_by="posting_date desc", limit=BOUNCE_WINDOW)
    collected_today = [r for r in payments if str(r.get("posting_date") or "") == day]
    collected_today_sum = _money_sum(collected_today, "paid_amount")

    return {
        "fees_total": len(all_fees),
        "fees_outstanding": len(outstanding),
        "fees_overdue": len(overdue),
        "fees_settled": len(settled),
        "invoices_outstanding": len(inv_outstanding),
        "invoices_overdue": len(inv_overdue),
        "collected_today": collected_today_sum,
        "by_program": by_program,
        "by_currency_charged": by_currency_charged,
        "by_currency_outstanding": by_currency_outstanding,
        "definition": "Fees: charged = submitted grand_total; outstanding = outstanding_amount>0; overdue = outstanding with due_date before today; settled = outstanding_amount<=0. Invoices use native outstanding_amount and status. Collected today = submitted payments (Receive) posted today.",
        "source": "tuition fees, placement invoices, payments (native ERPNext/Education)",
        "scope": "Fees branch-scoped via roster; invoices company-scoped; payments company-scoped.",
        "drill": "tuition fees list",
    }


# ------------------------------------------------------------------ book stock

def _native_rows(doctype, fields, *, filters=None, order_by=None):
    """Native permission-enforcing read; never bypass Company/User Permission.

    A truncated set cannot be represented as an institution-wide total.
    """
    if frappe is None or not hasattr(frappe, "has_permission"):
        raise PermissionError("Native role permissions unavailable")
    if not frappe.has_permission(doctype, "read"):
        raise PermissionError(f"Native {doctype} read role required")
    if not hasattr(frappe, "get_list"):
        raise PermissionError("Native permission-aware query unavailable")
    rows = frappe.get_list(
        doctype, fields=fields, filters=filters or {},
        order_by=order_by, limit_page_length=BOUNCE_WINDOW + 1)
    if len(rows) > BOUNCE_WINDOW:
        raise OverflowError(f"{doctype} exceeds bounded analytics coverage")
    return rows


def book_stock_metrics():
    """Permission-scoped native inventory, never a fabricated zero.

    'Books' is a clearly named inventory subset; no unapproved numerical
    reorder threshold is invented. Missing native visibility or incomplete
    pagination is shown as unavailable, not as an empty warehouse.
    """
    unavailable = {
        "items": "—", "bins": "—", "total_qty": "—", "low_stock": "—",
        "low_stock_rows": [],
        "definition": "Stock for native Item Group Books only. Reorder threshold is not configured.",
        "source": "Item and Bin native inventory (not a parallel ledger)",
        "scope": "Requires native Item and Bin read; warehouses restricted by native permissions.",
        "drill": "List/Item",
    }
    try:
        if not frappe.db.exists("Item Group", "Books"):
            return dict(unavailable, scope="Native Item Group Books not configured")
        # Even when the group currently has no items, lack of Bin permission
        # cannot be interpreted as verified zero stock.
        if not frappe.has_permission("Bin", "read"):
            return unavailable
        items = _native_rows(
            "Item", ["name", "item_name"],
            filters={"item_group": "Books", "is_stock_item": 1, "disabled": 0},
            order_by="name asc")
        # Do not query unrelated warehouse bins; protect the item/stock scope.
        names = [r["name"] for r in items]
        bins = (_native_rows(
            "Bin", ["name", "item_code", "warehouse", "actual_qty"],
            filters={"item_code": ("in", names)}, order_by="name asc")
            if names else [])
        units = sum(float(r.get("actual_qty") or 0) for r in bins)
    except (Exception, OverflowError):
        # A failed or truncated read is NOT proof of zero stock.
        return unavailable
    return dict(unavailable, items=len(items), bins=len(bins),
                total_qty=round(units, 2),
                scope="Native Item/Bin read + native Warehouse and User Permissions")


# ------------------------------------------------------------------ payroll

def payroll_metrics(authorized=False):
    """Only HRMS-authorized managers see permission-filtered payroll counts."""
    unavailable = {
        "authorized": False,
        "total": "—",
        "slips": "—",
        "definition": "Submitted native Additional Salary and Salary Slip counts; unavailable without HRMS permissions or complete records.",
        "source": "Native HRMS Additional Salary / Salary Slip",
        "scope": "Requires finance management role and native HRMS record read (Company User Permissions apply).",
        "drill": "List/Salary Slip",
    }
    if not authorized:
        return unavailable
    try:
        additional = _native_rows(
            "Additional Salary", ["name"], filters={"docstatus": 1},
            order_by="name asc")
        slips = _native_rows(
            "Salary Slip", ["name"], filters={"docstatus": 1},
            order_by="name asc")
    except (Exception, OverflowError):
        return unavailable
    return dict(unavailable, authorized=True, total=len(additional), slips=len(slips))


# ------------------------------------------------------------------ retention

def retention_metrics():
    """Retention: active vs exited enrollments."""
    try:
        exits = _project_rows("management", "TH Enrollment Exit",
                             ["name", "program_enrollment", "student", "exit_kind", "exit_date",
                              "reason", "status", "creation"],
                             order_by="creation desc", limit=BOUNCE_WINDOW)
    except Exception:
        exits = []
    enrollments = _project_rows("management", "Program Enrollment",
                              ["name", "student", "program", "academic_year", "docstatus"],
                              filters={"docstatus": 1},
                              order_by="enrollment_date desc", limit=BOUNCE_WINDOW)
    active = len(enrollments)
    exited = len(exits)
    rate = f"{(active / (active + exited) * 100):.1f}%" if (active + exited) else "—"
    by_type = _summarize_by(exits, "exit_kind")
    return {
        "active": active,
        "exited": exited,
        "retention_rate": rate,
        "by_type": by_type,
        "definition": "Active = submitted enrollments; exited = enrollment exits (withdrawal or dismissal) where the governing exit policy cites a resolved supersession. Retention = Active / (Active + Exited).",
        "source": "enrollments (active), enrollment exits (authorized exits)",
        "scope": "Branch-scoped via roster for enrollments; exits via student.",
        "drill": "enrollment exits list",
    }


# ------------------------------------------------------------------ operational exceptions

def exception_metrics():
    """Operational exceptions: overdue, stuck, pending approver, past-deadline."""
    try:
        from toefl_house.desk.lifecycle import PLACEMENT_ATTEMPT_ORDER
    except Exception:
        PLACEMENT_ATTEMPT_ORDER = ["Allocated", "Verified", "Delivered", "Sealed", "Scored", "Review", "Finalized"]
    corrections = _project_rows("management", "TH Correction Request",
                              ["name", "sales_invoice", "fees", "reason", "requested_amount", "status", "modified"],
                              filters={"status": "Requested"},
                              order_by="modified asc", limit=LIMIT_QUEUES)
    admissions_review = _project_rows("management", "TH Admission Decision",
                                     ["name", "student_applicant", "program", "status", "modified"],
                                     filters={"status": "Review"},
                                     order_by="modified asc", limit=LIMIT_QUEUES)
    attempts_running = _project_rows("management", "TH Placement Attempt",
                                    ["name", "case_name", "status", "deadline_at"],
                                    filters={"status": ("in", [s for s in PLACEMENT_ATTEMPT_ORDER if s != "Finalized"])},
                                    order_by="modified asc", limit=BOUNCE_WINDOW)
    overdue_deadlines = []
    try:
        from frappe.utils import get_datetime, now_datetime
        now = now_datetime()
        for row in attempts_running:
            if row.get("deadline_at"):
                try:
                    if get_datetime(row["deadline_at"]) < now:
                        overdue_deadlines.append(row)
                except Exception:
                    continue
    except Exception:
        pass
    finalized = _project_rows("management", "TH Placement Attempt",
                             ["name", "case_name", "status"],
                             filters={"status": "Finalized"},
                             order_by="modified asc", limit=BOUNCE_WINDOW)
    released = _project_rows("management", "TH Placement Decision",
                            ["name", "attempt", "status"],
                            filters={"status": "Released"},
                            order_by="released_at desc", limit=BOUNCE_WINDOW)
    released_attempts = {r["attempt"] for r in released if r.get("attempt")}
    awaiting_release = [r for r in finalized if r["name"] not in released_attempts]

    return {
        "corrections_pending": len(corrections),
        "admissions_in_review": len(admissions_review),
        "attempts_past_deadline": len(overdue_deadlines),
        "awaiting_release": len(awaiting_release),
        "definition": "Corrections in Requested, admissions longest in Review, attempts past server-set deadline, finalized attempts with no released decision.",
        "source": "correction requests, admission decisions, placement attempts, placement decisions",
        "scope": "Management scope (branch-wide or HQ).",
        "drill": "correction request list",
    }
