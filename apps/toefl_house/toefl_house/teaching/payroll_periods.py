"""Afghan Solar Hijri payroll period and payable tracking over native HRMS.

Payroll periods are worked periods, not disbursement months. This module
never creates, submits or pays Salary Slips or Additional Salary inputs; the
native HRMS Salary Structure Assignment and Finance approvals remain the
authority. Payment evidence must reference a native, posted disbursement
voucher and a submitted Salary Slip. This is an isolated reconciliation
helper; client/API permissions must be enforced before supplying rows.
"""
from decimal import Decimal

from toefl_house.finance.shamsi import (
    month_bounds, month_key, payroll_priority_date,
    payroll_following_month_end,
)
from toefl_house.finance.period_reporting import amount, _iso


def worked_month_payroll(slips, payments, worked_period, as_of):
    """Track earned-month net obligations vs actual native voucher payments.

    `slips`: name,employee,docstatus,start_date,end_date,net_pay.
    `payments`: name,salary_slip,docstatus,posting_date,paid_amount.
    Every included Salary Slip must span EXACTLY the worked Solar month.
    Draft/cancelled slips and vouchers are never counted as paid.
    No wages are marked paid merely because a Salary Slip was submitted.
    """
    from_day, to_day = month_bounds(worked_period)
    cutoff = _iso(as_of, "As-of date")
    priority = payroll_priority_date(worked_period)
    following_end = payroll_following_month_end(worked_period)
    slips_by_id = {}
    for raw in slips:
        if int(raw["docstatus"]) != 1:
            continue
        start = _iso(raw["start_date"], "Salary Slip start")
        end = _iso(raw["end_date"], "Salary Slip end")
        if (start <= to_day and end >= from_day) and (start, end) != (from_day, to_day):
            raise ValueError("A Salary Slip overlaps but does not match the full Solar Hijri worked month")
        if (start, end) != (from_day, to_day):
            continue
        key = str(raw["name"])
        if not key or key in slips_by_id:
            raise ValueError("Duplicate native Salary Slip")
        total = amount(raw["net_pay"])
        if total < 0:
            raise ValueError("Negative payroll needs separately authorized HRMS adjustment")
        slips_by_id[key] = {
            "employee": str(raw["employee"]), "earned": total,
            "paid": Decimal("0.00"), "payment_months": {},
        }
    seen = set()
    for raw in payments:
        if int(raw["docstatus"]) != 1 or _iso(raw["posting_date"], "Payment date") > cutoff:
            continue
        key = str(raw["name"])
        if not key or key in seen:
            raise ValueError("Duplicate native payroll disbursement identity")
        seen.add(key)
        slip_id = str(raw["salary_slip"])
        if slip_id not in slips_by_id:
            raise ValueError("Disbursement references a missing submitted worked-month Salary Slip")
        paid = amount(raw["paid_amount"])
        if paid <= 0:
            raise ValueError("Payroll disbursement must be positive")
        slip = slips_by_id[slip_id]
        slip["paid"] += paid
        paid_period = month_key(raw["posting_date"])
        monthly = slip["payment_months"]
        monthly[paid_period] = monthly.get(paid_period, Decimal("0.00")) + paid
    earned, paid, owed, after_priority = (Decimal("0.00"),) * 4
    rows = []
    for key, slip in sorted(slips_by_id.items()):
        if slip["paid"] > slip["earned"]:
            raise ValueError("Native payroll disbursement exceeds a submitted Salary Slip")
        outstanding = slip["earned"] - slip["paid"]
        earned += slip["earned"]
        paid += slip["paid"]
        owed += outstanding
        if cutoff > priority:
            after_priority += outstanding
        rows.append({
            "salary_slip": key, "employee": slip["employee"],
            "earned": slip["earned"], "paid": slip["paid"],
            "unpaid": outstanding,
            "paid_in_months": dict(slip["payment_months"]),
        })
    return {
        "worked_period": worked_period, "earned_from": str(from_day),
        "earned_to": str(to_day), "priority_payment_by": str(priority),
        "following_month_end": str(following_end),
        "as_of": str(cutoff), "earned_net": earned, "paid": paid,
        "unpaid": owed, "unpaid_after_priority": after_priority,
        "pending_after_following_month": (
            owed if cutoff > following_end else Decimal("0.00")),
        "payment_authorization_assumed": False,
        "salary_slips": rows,
    }
