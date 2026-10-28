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
import json
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
import frappe

from toefl_house.api import _execute
from toefl_house.finance import (COMPANY, FEES, FEE_STRUCTURE, PROGRAM_ENROLLMENT,
                                 _name, resolved_billable_components)
from toefl_house.finance import policies as billing_policies
from toefl_house.finance import shamsi
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
    try:
        value = Decimal(str(total))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Tuition amount must be a finite exact currency value") from exc
    if not value.is_finite():
        raise ValueError("Tuition amount must be finite")
    try:
        precise = value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Tuition amount is outside supported precision") from exc
    if value != precise:
        raise ValueError("Tuition amount must use exact two-decimal currency units")
    cents = int(value * 100)
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


def validate_shares(shares, parts):
    """Exact contractual percentage shares, summing to the whole tuition.

    The Owner approved negotiation of *unequal* installments (e.g. 60/40);
    the shares are percentages of the net tuition and must total exactly
    100%, so the plan can never under- or over-bill the configured price.
    Four decimal places are accepted and no rounding is applied to a
    requested share: a 33.33/33.33/33.34 style split is written as given,
    not silently re-balanced.
    """
    if isinstance(parts, bool) or not isinstance(parts, int) or parts < 1:
        raise ValueError("Installment count must be a whole number of at least 1")
    if not isinstance(shares, (list, tuple)):
        raise ValueError("Installment shares must be a list of percentages")
    if len(shares) != parts:
        raise ValueError(
            f"An installment plan of {parts} needs exactly {parts} shares")
    cleaned = []
    total = Decimal("0")
    for position, share in enumerate(shares, start=1):
        if isinstance(share, bool):
            raise ValueError(f"Share {position} must be a number")
        try:
            value = Decimal(str(share).strip())
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Share {position} must be a number") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError(f"Share {position} must be a positive percentage")
        try:
            precise = value.quantize(Decimal("0.0001"))
        except InvalidOperation as exc:
            raise ValueError(f"Share {position} is outside supported precision") from exc
        if value != precise:
            raise ValueError(
                f"Share {position} must use at most four decimal places")
        cleaned.append(precise)
        total += precise
    if total != Decimal("100"):
        raise ValueError(
            f"Installment shares must total 100%, not {total.normalize():f}%")
    return cleaned


def split_amounts_by_shares(total, shares):
    """Split ``total`` by exact percentages; the cents always add up.

    Every share but the last is rounded *down* to the cent and the last
    carries the remainder, so the schedule totals the configured amount to
    the cent for any approved ratio. A share that would carry no money is
    refused: a zero-amount native Fees document is not a receivable.
    """
    cleaned = validate_shares(shares, len(shares))
    try:
        value = Decimal(str(total))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Tuition amount must be a finite exact currency value") from exc
    if not value.is_finite():
        raise ValueError("Tuition amount must be finite")
    try:
        precise = value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Tuition amount is outside supported precision") from exc
    if value != precise:
        raise ValueError("Tuition amount must use exact two-decimal currency units")
    cents = int(value * 100)
    amounts = []
    allocated = 0
    for index, share in enumerate(cleaned):
        if index == len(cleaned) - 1:
            part = cents - allocated
        else:
            part = int((Decimal(cents) * share / Decimal("100")).to_integral_value(
                rounding=ROUND_DOWN))
        if part < 1:
            raise ValueError(
                "Each installment must carry a positive amount; the shares are "
                "too small for this tuition")
        amounts.append(part)
        allocated += part
    if sum(amounts) != cents:
        raise ValueError("The share split did not total the tuition amount")
    return [round(amount / 100.0, 2) for amount in amounts]


def schedule_due_dates(first_due, count, interval_days,
                       cadence="Days", grace_days=0, due_day=0):
    """Legacy day-spaced plans or exact Afghan Solar Hijri month dues.

    `first_due` is the first *actual* due date (including grace).
    Solar mode fails closed unless that day is exactly the contracted
    Solar Hijri day of the month plus configured grace — the first of the
    month unless ``due_day`` names another day such as the Owner-approved
    25th. An arbitrary date must never silently create a rolling personal
    student semester.
    """
    start = date.fromisoformat(str(first_due))
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Installment count must be a whole number of at least 1")
    if isinstance(interval_days, bool) or not isinstance(interval_days, int) or interval_days < 0:
        raise ValueError("Installment interval must be a whole number of days")
    cadence, grace_days = billing_policies.validate_shamsi_cadence(
        cadence, grace_days)
    # Validated for both cadences: a due day supplied for a day-spaced plan is
    # a contradiction and must be refused, never silently ignored.
    contracted_day = billing_policies.validate_due_day(cadence, due_day)
    if cadence == "Solar Hijri Month":
        first_period = shamsi.month_key(start - timedelta(days=grace_days))
        result = shamsi.monthly_due_dates(first_period, count, grace_days,
                                          contracted_day or 1)
        if result[0] != start:
            raise ValueError(
                "The first Solar Hijri month due date must be day "
                f"{contracted_day} of the month plus the configured grace days")
        return [day.isoformat() for day in result]
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
    cadence, grace = billing_policies.validate_shamsi_cadence(
        terms.get("installment_cadence") or "Days",
        int(terms.get("payment_grace_days") or 0))
    if cadence == "Days" and interval < 1:
        raise ValueError(
            "The governing billing policy does not state an installment "
            "interval; the Course Owner must set one")
    # The contracted day-of-month is the Owner's value (1 by default, or the
    # approved 25th); a plan can never invent its own due day.
    due_day = billing_policies.validate_due_day(
        cadence, int(terms.get("installment_due_day") or 0))
    posted = date.fromisoformat(str(posting))
    first = date.fromisoformat(str(first_due))
    # ``due_day`` is 0 for a day-spaced plan (no contracted day of month) and
    # a real day for Solar cadence; passed through so the validator judges it.
    due_dates = schedule_due_dates(
        first, installments, interval, cadence, grace, due_day)
    if first < posted:
        # Owner-approved late join: the contractual first-of-Shamsi-month
        # due date may already have passed when a learner is enrolled in an
        # active cohort. Keep the real (current) GL posting date, expose that
        # first invoice as outstanding/overdue, and prohibit arbitrary
        # previous-month backbilling by this everyday Finance command.
        # Compare the *contracted* month (grace removed), not the payable
        # date: grace days may legitimately push the due date into the next
        # Gregorian day while the obligation still belongs to its own month.
        contracted_month = shamsi.month_key(first - timedelta(days=grace))
        if (cadence != "Solar Hijri Month"
                or contracted_month != shamsi.month_key(posted)):
            raise ValueError(
                "The first installment cannot fall due before the bill is "
                "posted unless it is the current Solar Hijri month")
    return installments, interval, due_dates


def build_installment_components(fee_components, installments, shares=None):
    """Split every billable component row across the schedule.

    Returns one row list per installment. The per-installment rows sum to the
    configured (net-of-discount) component amounts, which is what native
    ``Fees`` totals and posts. ``shares`` are the Owner-authorized
    contractual percentages (e.g. 60/40); omitted means an equal split.
    """
    # Fee Category is not a unique row identifier: two native component
    # lines may legitimately share a category but differ in amount. Keeping
    # splits per *row*, and never converting money to float before splitting,
    # prevents one line silently inheriting another line's distribution.
    if shares is None:
        splits = [split_amounts(row["amount"], installments)
                  for row in fee_components]
    else:
        exact_shares = validate_shares(shares, installments)
        splits = [split_amounts_by_shares(row["amount"], exact_shares)
                  for row in fee_components]
    plan = []
    for index in range(installments):
        rows = []
        for row, amounts in zip(fee_components, splits):
            amount = amounts[index]
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


def _shares(value, installments):
    """Read the optional contractual shares from a desk form or API call.

    Nothing is inferred: an absent value keeps the equal split, and any
    supplied value must be an explicit list of percentages that the policy
    layer then authorizes and the arithmetic validates exactly.
    """
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            value = [part for part in text.replace(";", ",").split(",")]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise frappe.ValidationError(
        "Installment shares must be a list of percentages")


@frappe.whitelist(methods=["POST"])
def issue_tuition_installment_plan(request_key, program_enrollment, fee_structure,
                                   posting_date, first_due_date, installments,
                                   shares=None):
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
            # Validate BOTH date strings strictly, without conflating a
            # contractual due date with the *actual* GL posting date.
            # plan_terms judges whether a past due day is justified by the
            # explicit Owner's Solar-month late-join rule.
            posting, _ = validate_finance_dates(posting_date, posting_date)
            due, _ = validate_finance_dates(first_due_date, first_due_date)
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
            requested_shares = _shares(shares, count)
            if requested_shares is not None:
                if not int(terms.get("allow_unequal_installments") or 0):
                    raise ValueError(
                        "The governing billing policy does not authorize "
                        "unequal installment shares; the Course Owner must "
                        "enable them on an effective version")
                requested_shares = validate_shares(requested_shares, count)
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
        # Same enrollment, not the selected structure, is the financial
        # uniqueness anchor: changing the Fee Structure must not allow a
        # second semester's tuition to be sold for the same enrollment.
        if frappe.db.exists(FEES, {"program_enrollment": pe_name,
                                   "docstatus": ("!=", 2)}):
            raise frappe.ValidationError(
                "Tuition is already billed for this enrollment; "
                "Finance must use the audited correction process")

        fee_components, applied_discounts, gross_total = \
            resolved_billable_components(pe, fs_name)
        plan = build_installment_components(fee_components, count,
                                            requested_shares)
        net_total = round(sum(_plan_total(rows) for rows in plan), 2)
        if applied_discounts and round(gross_total - net_total, 2) <= 0:
            raise frappe.ValidationError(
                "The discount was not applied to the plan; refuse rather than bill the gross price")

        company = fs.company or COMPANY
        from toefl_house.finance.company_scope import require_finance_company
        require_finance_company(company)
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
            "installment_cadence": terms.get("installment_cadence") or "Days",
            "payment_grace_days": int(terms.get("payment_grace_days") or 0),
            "installment_due_day": int(terms.get("installment_due_day") or 0),
            "installment_shares": ([float(share) for share in requested_shares]
                                   if requested_shares is not None else []),
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
                               result["installment_cadence"],
                               result["payment_grace_days"],
                               result["installment_due_day"],
                               result["installment_shares"],
                               [row["fees"] for row in issued],
                               [row["grand_total"] for row in issued],
                               applied_discounts]))

    return _execute("issue_tuition_installment_plan", request_key,
                    {"program_enrollment": program_enrollment,
                     "fee_structure": fee_structure,
                     "posting_date": posting_date,
                     "first_due_date": first_due_date,
                     "installments": installments,
                     # Normalized so the same logical request replays under
                     # its idempotency key whether the shares arrived as a
                     # JSON string, a comma list or an array.
                     "shares": _shares(shares, installments)}, work)
