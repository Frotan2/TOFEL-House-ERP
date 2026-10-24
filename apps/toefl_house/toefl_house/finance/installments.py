"""Policy-driven tuition installment plans over the native ``Fees`` authority.

Owner decision (FINANCE-POLICY-APPROVAL.md) fixes the billing authority: a
tuition receivable is always a submitted Education ``Fees`` document built
from a Finance-configured native ``Fee Structure``. This module adds the one
thing that authority does not express by itself — splitting *one* configured
price into an owner-authorized schedule of native ``Fees`` documents.

Rules this module binds, and why they are not configurable here:

- **Nothing is invented.** The money comes from the Fee Structure and the
  Course Owner's discount rules (the same resolver the one-payment command
  uses). The *schedule* comes from the governing ``TH Billing Policy``
  version: whether splitting is allowed, the largest count, and the interval
  between due dates. With installments disabled — the default for every
  version and for every version written before the field existed — this
  command is refused and the ordinary single-document bill is the only route.
- **Exact money.** Each component is split in integer cents; the rounding
  remainder lands on the LAST installment, so the schedule sums to the
  configured price to the cent. No installment can be zero or negative.
- **One plan per enrollment.** A second plan, a second single bill, or a
  re-issue over an existing live plan is refused. A cancelled bill does not
  block a fresh plan; a live one always does, so no student is billed twice.
- **Native posting only.** Each installment is a submitted ``Fees`` document:
  its own GL receivable, its own outstanding amount, native reconciliation
  and native cancellation/correction. There is no parallel schedule table and
  no owned ledger.
"""
from datetime import date, timedelta
import frappe

from toefl_house.api import _execute
from toefl_house.finance import (COMPANY, FEES, FEE_STRUCTURE, PROGRAM_ENROLLMENT,
                                 _name, resolved_billable_components)
from toefl_house.finance import policies as billing_policies
from toefl_house.policy import digest, validate_finance_dates

SINGLE_BILL = 1
MIN_SPLIT = 2


def split_amounts(total, parts):
    """Split ``total`` into ``parts`` amounts that sum exactly to it.

    Integer cents throughout; the remainder goes to the last installment.
    Refuses a schedule that would produce a zero or negative installment,
    because a zero-amount native Fees document is not a receivable and would
    quietly drop money out of the plan.
    """
    if isinstance(parts, bool) or not isinstance(parts, int) or parts < 1:
        raise ValueError("Installment count must be a whole number of at least 1")
    cents = int(round(float(total) * 100))
    if cents < parts:
        raise ValueError(
            "The configured amount is too small to split into that many installments")
    base = cents // parts
    if base < 1:
        raise ValueError(
            "Each installment must carry a positive amount; reduce the count")
    amounts = [base] * parts
    amounts[-1] += cents - base * parts
    return [round(value / 100.0, 2) for value in amounts]


def schedule_due_dates(first_due, count, interval_days):
    """Due dates for a plan: the owner's first date, then the interval.

    The interval is the policy version's term, never a lunar/monthly
    convention invented here: calendar months are not uniform and the owner
    states the spacing in days.
    """
    start = date.fromisoformat(str(first_due))
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Installment count must be a whole number of at least 1")
    if isinstance(interval_days, bool) or not isinstance(interval_days, int) or interval_days < 0:
        raise ValueError("Installment interval must be a whole number of days")
    return [str(start + timedelta(days=interval_days * index))
            for index in range(count)]


def plan_terms(terms, installments, posting, first_due):
    """Judge one requested split against the governing owner terms.

    Returns the validated ``(count, interval_days, due_dates)``. Raises
    ``ValueError`` with the business reason, so the caller surfaces a message
    a Finance Officer can act on rather than a traceback.
    """
    if isinstance(installments, bool) or not isinstance(installments, int):
        raise ValueError("Installment count must be a whole number")
    if not terms:
        raise ValueError("No active billing policy governs this date; "
                         "the Course Owner must set one first")
    if installments < MIN_SPLIT:
        raise ValueError(
            "A tuition plan splits one configured price into at least two "
            "installments; bill a single installment with the ordinary "
            "tuition billing command")
    if not int(terms.get("installments_allowed") or 0):
        raise ValueError(
            "Installments are not authorized by the governing billing policy; "
            "the Course Owner must enable them on an effective version")
    maximum = int(terms.get("max_installments") or 1)
    if installments > maximum:
        raise ValueError(
            f"The governing billing policy allows at most {maximum} installments")
    interval = int(terms.get("installment_interval_days") or 0)
    if interval < 1:
        raise ValueError(
            "The governing billing policy does not state an installment "
            "interval; the Course Owner must set one")
    posted = date.fromisoformat(str(posting))
    first = date.fromisoformat(str(first_due))
    if first < posted:
        raise ValueError("The first installment cannot fall due before the bill is posted")
    return installments, interval, schedule_due_dates(first, installments, interval)


def build_installment_components(fee_components, installments):
    """Split every billable component row across the schedule.

    Returns one row list per installment. The per-installment rows sum to the
    configured (net-of-discount) component amounts, which is what native
    ``Fees`` totals and posts.
    """
    splits = {row["fees_category"]: split_amounts(float(row["amount"]), installments)
              for row in fee_components}
    plan = []
    for index in range(installments):
        rows = []
        for row in fee_components:
            amount = splits[row["fees_category"]][index]
            if amount <= 0:
                raise ValueError(
                    "An installment would carry no amount for a fee component; "
                    "reduce the installment count")
            new_row = dict(row)
            new_row["amount"] = amount
            rows.append(new_row)
        plan.append(rows)
    return plan


def _plan_total(rows):
    return round(sum(float(row["amount"]) for row in rows), 2)


@frappe.whitelist(methods=["POST"])
def issue_tuition_installment_plan(request_key, program_enrollment, fee_structure,
                                   posting_date, first_due_date, installments):
    """Bill one submitted enrollment as an owner-authorized native schedule.

    Produces N submitted ``Fees`` documents, one per installment, each posting
    its own receivable. The plan exists only as those native documents plus
    their installment sequence fields; cancelling one installment is an
    ordinary native cancellation and is corrected through the correction
    framework, never by silently rewriting the schedule.
    """
    def work(actor):
        pe_name = _name(program_enrollment, "Program enrollment")
        fs_name = _name(fee_structure, "Fee structure")
        try:
            posting, due = validate_finance_dates(posting_date, first_due_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists(PROGRAM_ENROLLMENT, pe_name):
            raise frappe.ValidationError("Unknown program enrollment")
        terms = billing_policies.governing_billing_terms()
        try:
            if not terms:
                raise ValueError("No active billing policy governs this date; "
                                 "the Course Owner must set one first")
            billing_policies.check_posting_bounds(
                posting, frappe.utils.today(),
                terms["max_backdate_days"], terms["max_future_days"])
            count, interval, due_dates = plan_terms(
                terms, installments, posting, due)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc

        # Anchor lock on the enrollment: two officers billing the same
        # enrollment concurrently must serialize, not both pass the
        # duplicate check below.
        frappe.db.sql("select name from `tabProgram Enrollment` where name=%s for update",
                      (pe_name,))
        pe = frappe.db.get_value(PROGRAM_ENROLLMENT, pe_name,
                                 ["student", "program", "academic_year", "docstatus"],
                                 as_dict=True)
        if not pe:
            raise frappe.ValidationError("Unknown program enrollment")
        if int(pe.docstatus or 0) != 1:
            raise frappe.ValidationError("Program enrollment must be submitted")
        fs = frappe.db.get_value(FEE_STRUCTURE, fs_name,
                                 ["program", "academic_year", "receivable_account",
                                  "cost_center", "company"], as_dict=True)
        if not fs:
            raise frappe.ValidationError("Unknown fee structure")
        if fs.program != pe.program or fs.academic_year != pe.academic_year:
            raise frappe.ValidationError(
                "Fee structure does not match the enrollment program/year")
        if frappe.db.exists(FEES, {"program_enrollment": pe_name,
                                   "fee_structure": fs_name,
                                   "docstatus": ("!=", 2)}):
            raise frappe.ValidationError(
                "Tuition is already billed for this enrollment on this fee plan")

        fee_components, applied_discounts, gross_total = \
            resolved_billable_components(pe, fs_name)
        plan = build_installment_components(fee_components, count)
        net_total = round(sum(_plan_total(rows) for rows in plan), 2)
        if applied_discounts and round(gross_total - net_total, 2) <= 0:
            raise frappe.ValidationError(
                "The discount was not applied to the plan; refuse rather than bill the gross price")

        company = fs.company or COMPANY
        company_currency = frappe.get_cached_value(
            "Company", company, "default_currency")
        student_name = frappe.db.get_value("Student", pe.student, "student_name")
        issued = []
        for index, rows in enumerate(plan, start=1):
            expected = _plan_total(rows)
            fees = frappe.get_doc(dict(
                doctype=FEES, naming_series="EDU-FEE-.YYYY.-",
                student=pe.student, student_name=student_name or pe.student,
                program_enrollment=pe_name, program=pe.program,
                academic_year=pe.academic_year,
                company=company, currency=company_currency,
                posting_date=posting, due_date=due_dates[index - 1],
                fee_structure=fs_name, receivable_account=fs.receivable_account,
                th_installment_sequence=index, th_installment_count=count,
                components=rows))
            fees.flags.ignore_permissions = True
            fees.insert(ignore_permissions=True)
            fees.flags.ignore_permissions = True
            fees.submit()
            row = frappe.db.get_value(
                FEES, fees.name,
                ["docstatus", "grand_total", "outstanding_amount", "currency",
                 "due_date"], as_dict=True)
            if int(row.docstatus or 0) != 1:
                raise frappe.ValidationError("Fees must be submitted")
            if round(float(row.grand_total), 2) != expected:
                raise frappe.ValidationError(
                    "A native fees document does not carry the planned installment amount")
            issued.append({
                "fees": fees.name, "sequence": index,
                "due_date": str(row.due_date), "grand_total": expected,
                "outstanding_amount": float(row.outstanding_amount),
                "currency": row.currency,
            })

        result = {
            "program_enrollment": pe_name, "student": pe.student,
            "fee_structure": fs_name, "installments": count,
            "interval_days": interval, "posting_date": posting,
            "installment_total": net_total, "gross_total": gross_total,
            "installments_issued": issued,
        }
        if applied_discounts:
            result["discounts_applied"] = applied_discounts
            result["discount_amount"] = round(gross_total - net_total, 2)
        if len(issued) != count:
            raise frappe.ValidationError(
                "The plan did not produce every installment; nothing is billed")
        return result, dict(
            target=issued[0]["fees"],
            after_hash=digest([pe_name, fs_name, posting, count, interval,
                               [row["fees"] for row in issued],
                               [row["grand_total"] for row in issued],
                               applied_discounts]))

    return _execute("issue_tuition_installment_plan", request_key,
                    {"program_enrollment": program_enrollment,
                     "fee_structure": fee_structure,
                     "posting_date": posting_date,
                     "first_due_date": first_due_date,
                     "installments": installments}, work)
