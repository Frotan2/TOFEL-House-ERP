"""D2 contract-driven teaching compensation (owner requirement 2026-09-16).

Separation of responsibilities (owner-mandated):
- Teaching Ops records who actually taught what: TH Teaching Assignment
  rows (class, skill area, instructor, effective window), created by the
  Teaching Scheduler through guarded commands.
- Finance/Payroll owns compensation: TH Instructor Contract terms and the
  single calculation command (Finance Officer). The only payroll artifact
  this module produces is the native HRMS Additional Salary document
  (ref_doctype/ref_docname carry the audit chain). There is no second
  payroll engine and no parallel payable ledger; statutory/tax/slip math
  stays entirely in native Salary Slip / Payroll Entry.

No rate, amount, term or statutory rule is invented here: every value is
owner-entered contract configuration.
"""
import datetime
import json
import frappe
from toefl_house.api import _execute
from toefl_house.policy import (digest, validate_compensation_model, validate_effective_window,
                                validate_optional_amount, validate_payable_quantity,
                                validate_positive_amount, validate_schedule_date, validate_skill,
                                windows_overlap)
from toefl_house.security import record_synthetic_flag

CONTRACT = "TH Instructor Contract"
ASSIGNMENT = "TH Teaching Assignment"
ADJUSTMENT = "TH Contract Adjustment"
ADDITIONAL_SALARY = "Additional Salary"
INSTRUCTOR = "Instructor"
EMPLOYEE = "Employee"
GROUP = "Student Group"
SCHEDULE = "Course Schedule"
MAX_ROWS = 10


def _bounded(value, label, limit=140):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise frappe.ValidationError(f"{label} required")
    return value


def _rows(value, label):
    if isinstance(value, str):
        if len(value) > 20000:
            raise frappe.ValidationError(f"{label} exceeds request limit")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise frappe.ValidationError(f"{label} must be a JSON list") from exc
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise frappe.ValidationError(f"{label} must be a JSON list of at most {MAX_ROWS} rows")
    if not all(isinstance(row, dict) for row in value):
        raise frappe.ValidationError(f"{label} rows must be objects")
    return value


def _policy(fn, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _assert_active_skill(skill_code):
    """Runtime check (inside command context) that the TH Skill exists and is Active.

    Pure validate_skill (policy.validate_skill) only bounds the name; the
    existence/lifecycle check requires the database and lives here. Retired
    skills remain valid for historical reference on existing contracts/assignments
    but cannot be added to new ones.
    """
    if not frappe.db.exists("TH Skill", skill_code):
        raise frappe.ValidationError(f"Unknown skill: {skill_code}")
    status = frappe.db.get_value("TH Skill", skill_code, "status")
    if status != "Active":
        raise frappe.ValidationError(
            f"Skill {skill_code} is retired; only Active skills can be used in new contracts or assignments")
    return skill_code


def _parse_terms(rows):
    terms, seen = [], set()
    for row in rows:
        skill = _policy(validate_skill, row.get("skill"))
        _assert_active_skill(skill)
        if skill in seen:
            raise frappe.ValidationError("Duplicate skill term in contract")
        seen.add(skill)
        minimum = _policy(validate_optional_amount, row.get("minimum_amount"), "Minimum amount")
        maximum = _policy(validate_optional_amount, row.get("maximum_amount"), "Maximum amount")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise frappe.ValidationError("Contract minimum exceeds contract maximum")
        terms.append(dict(skill=skill,
                          unit_of_payment=_bounded(row.get("unit_of_payment"), "Unit of payment", 60),
                          rate=_policy(validate_positive_amount, row.get("rate"), "Rate"),
                          payable_quantity=_policy(validate_payable_quantity, row.get("payable_quantity")),
                          minimum_amount=minimum, maximum_amount=maximum))
    return terms


def _parse_adjustments(rows):
    adjustments = []
    for row in rows:
        adjustment_type = row.get("adjustment_type")
        if adjustment_type not in ("Bonus", "Deduction"):
            raise frappe.ValidationError("Adjustment type must be Bonus or Deduction")
        approver = _bounded(row.get("approver"), "Approver")
        if not frappe.db.exists("User", approver) or not frappe.db.get_value("User", approver, "enabled"):
            raise frappe.ValidationError("Adjustment approver must be an enabled user")
        adjustments.append(dict(adjustment_type=adjustment_type,
                                amount=_policy(validate_positive_amount, row.get("amount"), "Adjustment amount"),
                                effective_date=_policy(validate_schedule_date, row.get("effective_date")),
                                approver=approver,
                                reason=_bounded(row.get("reason"), "Reason", 300)))
    return adjustments


def _reject_overlapping_contract(instructor, start, end, exclude=None):
    for row in frappe.db.get_all(CONTRACT, filters={"instructor": instructor, "status": "Active"},
                                 fields=["name", "effective_start", "effective_end"]):
        if row.name == exclude:
            continue
        if windows_overlap(start, end, str(row.effective_start),
                           str(row.effective_end) if row.effective_end else None):
            raise frappe.ValidationError("Instructor already has an active contract for this window")


def _contract_payload(actor, instructor, employee, model, basis, frequency,
                      start, end, conditions, terms, adjustments, supersedes=""):
    return dict(doctype=CONTRACT, instructor=instructor, employee=employee,
                compensation_model=model, assignment_basis=basis,
                payment_frequency=frequency, effective_start=start, effective_end=end,
                conditions=conditions, supersedes=supersedes, status="Active",
                skill_terms=terms, adjustments=adjustments, synthetic=record_synthetic_flag())


@frappe.whitelist(methods=["POST"])
def create_teaching_contract(request_key, instructor, employee, compensation_model,
                             assignment_basis, payment_frequency, effective_start,
                             effective_end="", conditions="", skill_terms="[]",
                             adjustments="[]"):
    """Record an explicit instructor compensation contract (contract authority).

    Fixed-salary contracts carry no skill terms (their payroll runs through
    the native Salary Structure Assignment mechanism); Skill-Based and
    Hybrid contracts must declare per-skill terms. Windows of active
    contracts for one instructor may never overlap, which keeps the
    contract applicable to any payroll period unique.
    """
    def work(actor):
        instructor_name = _bounded(instructor, "Instructor")
        employee_name = _bounded(employee, "Employee")
        model = _policy(validate_compensation_model, compensation_model)
        basis = _bounded(assignment_basis, "Assignment basis", 300)
        frequency = _bounded(payment_frequency, "Payment frequency", 60)
        start, end = _policy(validate_effective_window, effective_start, effective_end or "")
        if isinstance(conditions, str) and len(conditions) > 2000:
            raise frappe.ValidationError("Conditions exceed request limit")
        terms = _parse_terms(_rows(skill_terms, "Skill terms"))
        adjustment_rows = _parse_adjustments(_rows(adjustments, "Adjustments"))
        if not frappe.db.exists(INSTRUCTOR, instructor_name):
            raise frappe.ValidationError("Unknown instructor")
        if not frappe.db.exists(EMPLOYEE, employee_name):
            raise frappe.ValidationError("Unknown employee")
        # Native Education Instructor carries an employee link; we require
        # it to match for payroll integrity (Additional Salary is created
        # against the employee, so a mismatch would pay the wrong person).
        instructor_employee = frappe.db.get_value(INSTRUCTOR, instructor_name, "employee")
        if instructor_employee != employee_name:
            raise frappe.ValidationError(
                "Employee does not match the instructor's HRMS employee record")
        if frappe.db.get_value(EMPLOYEE, employee_name, "status") != "Active":
            raise frappe.ValidationError("Only active employees can hold teaching contracts")
        if model == "Fixed Salary" and terms:
            raise frappe.ValidationError("Fixed-salary contracts carry no skill terms; native salary structure applies")
        if model in ("Skill-Based", "Hybrid") and not terms:
            raise frappe.ValidationError("Skill-based and hybrid contracts must declare skill terms")
        _reject_overlapping_contract(instructor_name, start, end)
        contract = frappe.get_doc(_contract_payload(
            actor, instructor_name, employee_name, model, basis, frequency,
            start, end, conditions, terms, adjustment_rows))
        contract.flags.ignore_permissions = True
        contract.flags.ignore_links = True
        contract.insert(ignore_permissions=True)
        result = {"name": contract.name, "instructor": instructor_name,
                  "employee": employee_name, "compensation_model": model,
                  "effective_start": start, "effective_end": end or "",
                  "status": "Active", "skill_terms": len(terms),
                  "adjustments": len(adjustment_rows)}
        return result, dict(target=contract.name,
                            after_hash=digest([contract.name, instructor_name, model,
                                               start, end or "", terms, adjustment_rows]))

    return _execute("create_teaching_contract", request_key,
                    {"instructor": instructor, "employee": employee,
                     "compensation_model": compensation_model,
                     "assignment_basis": assignment_basis,
                     "payment_frequency": payment_frequency,
                     "effective_start": effective_start, "effective_end": effective_end or "",
                     "conditions": conditions, "skill_terms": skill_terms,
                     "adjustments": adjustments}, work)


@frappe.whitelist(methods=["POST"])
def revise_teaching_contract(request_key, contract, compensation_model, assignment_basis,
                             payment_frequency, effective_start, effective_end="",
                             conditions="", skill_terms="[]", adjustments="[]"):
    """Supersede an active contract with a new effective-dated revision.

    The old contract is never rewritten (historical reproducibility): it
    transitions Active -> Superseded and the successor references it, so
    the compensation applicable to any past period remains resolvable.
    """
    def work(actor):
        contract_name = _bounded(contract, "Contract")
        model = _policy(validate_compensation_model, compensation_model)
        basis = _bounded(assignment_basis, "Assignment basis", 300)
        frequency = _bounded(payment_frequency, "Payment frequency", 60)
        start, end = _policy(validate_effective_window, effective_start, effective_end or "")
        if isinstance(conditions, str) and len(conditions) > 2000:
            raise frappe.ValidationError("Conditions exceed request limit")
        terms = _parse_terms(_rows(skill_terms, "Skill terms"))
        adjustment_rows = _parse_adjustments(_rows(adjustments, "Adjustments"))
        if not frappe.db.exists(CONTRACT, contract_name):
            raise frappe.ValidationError("Unknown contract")
        frappe.db.sql("select name from `tabTH Instructor Contract` where name=%s for update",
                      (contract_name,))
        old = frappe.get_doc(CONTRACT, contract_name)
        if old.status != "Active":
            raise frappe.ValidationError("Only an active contract can be superseded")
        if model == "Fixed Salary" and terms:
            raise frappe.ValidationError("Fixed-salary contracts carry no skill terms; native salary structure applies")
        if model in ("Skill-Based", "Hybrid") and not terms:
            raise frappe.ValidationError("Skill-based and hybrid contracts must declare skill terms")
        _reject_overlapping_contract(old.instructor, start, end, exclude=contract_name)
        successor = frappe.get_doc(_contract_payload(
            actor, old.instructor, old.employee, model, basis, frequency,
            start, end, conditions, terms, adjustment_rows, supersedes=contract_name))
        successor.flags.ignore_permissions = True
        successor.flags.ignore_links = True
        successor.insert(ignore_permissions=True)
        old.flags.ignore_permissions = True
        # Owner decision D12 (2026-09-19): a revision closes the predecessor's
        # window the day before the successor starts. Without this the
        # superseded contract kept its open-ended effective_end, so the
        # calculation found two contracts covering any later period and refused
        # to run at all. Closing the window makes exactly one contract cover
        # every period, applies the successor rate from its own start date, and
        # reaches back into nothing: periods already compensated stay exactly as
        # they were posted. Only the window is closed - no rate, term, quantity
        # or adjustment on the predecessor is ever rewritten, so historical
        # compensation remains reproducible from it.
        successor_start = datetime.date.fromisoformat(str(start))
        predecessor_start = datetime.date.fromisoformat(str(old.effective_start))
        if successor_start <= predecessor_start:
            raise frappe.ValidationError(
                "A revised contract must start after the contract it replaces")
        closing = (successor_start - datetime.timedelta(days=1)).isoformat()
        window_was_closed = (not old.effective_end
                             or str(old.effective_end) > closing)
        if window_was_closed:
            old.effective_end = closing
        old.status = "Superseded"
        old.save(ignore_permissions=True)
        result = {"name": successor.name, "supersedes": contract_name,
                  "instructor": old.instructor, "compensation_model": model,
                  "effective_start": start, "effective_end": end or "",
                  "status": "Active", "skill_terms": len(terms),
                  "adjustments": len(adjustment_rows)}
        return result, dict(target=contract_name,
                            after_hash=digest([successor.name, contract_name, model,
                                               start, end or "", terms, adjustment_rows]))

    return _execute("revise_teaching_contract", request_key,
                    {"contract": contract, "compensation_model": compensation_model,
                     "assignment_basis": assignment_basis,
                     "payment_frequency": payment_frequency,
                     "effective_start": effective_start, "effective_end": effective_end or "",
                     "conditions": conditions, "skill_terms": skill_terms,
                     "adjustments": adjustments}, work)


@frappe.whitelist(methods=["POST"])
def assign_teaching_skill(request_key, student_group, skill, instructor, contract,
                          effective_start, effective_end="", course_schedule=""):
    """Record who actually teaches which skill area for which class (teaching ops).

    One instructor holds a skill area for a class at a time; a class holds
    at most the three skill areas; an instructor may hold many skills and
    classes. The assignment references the contract that compensates it.
    """
    def work(actor):
        group_name = _bounded(student_group, "Student Group")
        skill_name = _policy(validate_skill, skill)
        _assert_active_skill(skill_name)
        instructor_name = _bounded(instructor, "Instructor")
        contract_name = _bounded(contract, "Contract")
        start, end = _policy(validate_effective_window, effective_start, effective_end or "")
        schedule_name = _bounded(course_schedule, "Course Schedule") if course_schedule else ""
        if not frappe.db.exists(GROUP, group_name):
            raise frappe.ValidationError("Unknown student group")
        if not frappe.db.exists(INSTRUCTOR, instructor_name):
            raise frappe.ValidationError("Unknown instructor")
        if not frappe.db.exists(CONTRACT, contract_name):
            raise frappe.ValidationError("Unknown contract")
        if schedule_name:
            row = frappe.db.get_value(SCHEDULE, schedule_name, ["name", "student_group"], as_dict=True)
            if not row or row.student_group != group_name:
                raise frappe.ValidationError("Course schedule does not belong to the assigned class")
        terms = frappe.db.get_value(CONTRACT, contract_name,
                                    ["instructor", "status", "compensation_model",
                                     "effective_start", "effective_end"], as_dict=True)
        if terms.instructor != instructor_name:
            raise frappe.ValidationError("Contract does not belong to the assigned instructor")
        if terms.status != "Active":
            raise frappe.ValidationError("Assignments require an active contract")
        if not windows_overlap(start, end, str(terms.effective_start),
                               str(terms.effective_end) if terms.effective_end else None):
            raise frappe.ValidationError("Contract is not effective for the assignment window")
        if terms.compensation_model == "Fixed Salary":
            raise frappe.ValidationError("Fixed-salary contracts are not assigned per skill")
        frappe.db.sql("select name from `tabTH Teaching Assignment` "
                      "where student_group=%s and skill=%s for update", (group_name, skill_name))
        for row in frappe.db.get_all(ASSIGNMENT, filters={"student_group": group_name, "skill": skill_name},
                                     fields=["name", "effective_start", "effective_end"]):
            if windows_overlap(start, end, str(row.effective_start),
                               str(row.effective_end) if row.effective_end else None):
                raise frappe.ValidationError("Another instructor already holds this skill area for the window")
        assignment = frappe.get_doc(dict(
            doctype=ASSIGNMENT, student_group=group_name, skill=skill_name,
            instructor=instructor_name, contract=contract_name,
            course_schedule=schedule_name or None, effective_start=start,
            effective_end=end, synthetic=record_synthetic_flag()))
        assignment.flags.ignore_permissions = True
        assignment.flags.ignore_links = True
        assignment.insert(ignore_permissions=True)
        result = {"name": assignment.name, "student_group": group_name,
                  "skill": skill_name, "instructor": instructor_name,
                  "contract": contract_name, "effective_start": start,
                  "effective_end": end or ""}
        return result, dict(target=assignment.name,
                            after_hash=digest([assignment.name, group_name, skill_name,
                                               instructor_name, contract_name, start, end or ""]))

    return _execute("assign_teaching_skill", request_key,
                    {"student_group": student_group, "skill": skill,
                     "instructor": instructor, "contract": contract,
                     "effective_start": effective_start, "effective_end": effective_end or "",
                     "course_schedule": course_schedule or ""}, work)


@frappe.whitelist(methods=["POST"])
def end_teaching_assignment(request_key, assignment, effective_end):
    """Close an assignment by recording its end date once; facts are never rewritten."""
    def work(actor):
        assignment_name = _bounded(assignment, "Assignment")
        end = _policy(validate_schedule_date, effective_end)
        if not frappe.db.exists(ASSIGNMENT, assignment_name):
            raise frappe.ValidationError("Unknown assignment")
        frappe.db.sql("select name from `tabTH Teaching Assignment` where name=%s for update",
                      (assignment_name,))
        doc = frappe.get_doc(ASSIGNMENT, assignment_name)
        if doc.effective_end:
            raise frappe.ValidationError("Assignment already carries a recorded end date")
        if end < str(doc.effective_start):
            raise frappe.ValidationError("End date precedes assignment start")
        doc.flags.ignore_permissions = True
        doc.effective_end = end
        doc.save(ignore_permissions=True)
        result = {"name": assignment_name, "effective_end": end}
        return result, dict(target=assignment_name,
                            before_hash=digest([assignment_name, ""]),
                            after_hash=digest([assignment_name, end]))

    return _execute("end_teaching_assignment", request_key,
                    {"assignment": assignment, "effective_end": effective_end}, work)


def _paid_dates(ref_doctype, ref_docname):
    """Payroll dates already posted for one payable reference.

    A locking read: concurrent calculations serialize on the contract rows
    first (see below), and this re-read runs after the lock wait, so it
    observes the winner's post on every isolation level. Without it two
    overlapping calculations could both read "unpaid" and double-post
    (BUG-PAY-01). Served by the th_ads_ref index (install.py).
    """
    return sorted({str(payroll_date) for (payroll_date,) in frappe.db.sql(
        "select payroll_date from `tabAdditional Salary` where ref_doctype=%s "
        "and ref_docname=%s and disabled=0 for update", (ref_doctype, ref_docname))})


def _covering_contract_name(instructor, start, end):
    """The single contract covering an instructor's payroll period, or refuse."""
    matches = frappe.db.get_all(
        CONTRACT, filters={"instructor": instructor},
        fields=["name", "effective_start", "effective_end", "compensation_model"])
    overlapping = [m for m in matches
                   if windows_overlap(start, end, str(m.effective_start),
                                      str(m.effective_end) if m.effective_end else None)]
    if len(overlapping) != 1:
        raise frappe.ValidationError(
            "Exactly one contract must cover the period for instructor "
            + instructor + f" (found {len(overlapping)}); use a narrower period or revise contracts")
    return overlapping[0].name


def _lock_covering_contracts(contracts, start, end):
    """Serialize overlapping calculations on the covering contract rows.

    Contract names are locked in sorted order so concurrent calculations
    cannot deadlock against each other. After the locks are held each
    contract is re-fetched with a locking read (current terms and status on
    every isolation level): a contract revised while this calculation waited
    fails closed with a retry instead of paying under superseded terms, and
    the exactly-one rule is re-checked against post-lock state.
    """
    for name in sorted({contract.name for contract in contracts.values()}):
        frappe.db.sql("select name from `tabTH Instructor Contract` where name=%s for update",
                      (name,))
    for instructor in sorted(contracts):
        fresh = frappe.get_doc(CONTRACT, contracts[instructor].name, for_update=True)
        if fresh.status != "Active":
            raise frappe.ValidationError(
                f"Contract {fresh.name} is no longer active; recalculation required")
        if not windows_overlap(start, end, str(fresh.effective_start),
                               str(fresh.effective_end) if fresh.effective_end else None):
            raise frappe.ValidationError(
                f"Contract {fresh.name} no longer covers the period; recalculation required")
        if _covering_contract_name(instructor, start, end) != fresh.name:
            raise frappe.ValidationError(
                f"Contract cover for {instructor} changed during calculation; recalculation required")
        contracts[instructor] = fresh
    return contracts


def _payable_for(contract, assignment):
    for term in contract.skill_terms or []:
        if term.skill == assignment.skill:
            from toefl_house.policy import compute_skill_payable
            return _policy(compute_skill_payable, term.payable_quantity, float(term.rate),
                           float(term.minimum_amount) if term.minimum_amount else None,
                           float(term.maximum_amount) if term.maximum_amount else None)
    raise frappe.ValidationError("Active contract does not cover the assigned skill")


@frappe.whitelist(methods=["POST"])
def calculate_teaching_compensation(request_key, period_start, period_end, company,
                                    salary_component, deduction_component=""):
    """Project contract terms over actual teaching facts into native payroll inputs.

    Single controlled input path: one native Additional Salary (Earning) per
    assignment, plus one per due contract adjustment, each linked back via
    ref_doctype/ref_docname (assignments reference the assignment; adjustments
    reference the TH Contract Adjustment row, so distinct adjustments post
    independently). Idempotent within a period: an existing enabled
    Additional Salary for the same reference and payroll date is never
    duplicated, and the command itself is guarded by the standard request-key
    receipt. Overlapping calculations serialize on the covering contract rows
    (locked in sorted-name order) and re-read postings with locking reads, so
    concurrent runs cannot double-post on any isolation level. No statutory,
    tax or slip math happens here (native Salary Slip owns it); fixed-salary
    instructors are skipped (native Salary Structure path).

    **One-off payable (owner decision D12, 2026-09-19).** The payable is a flat
    contract amount, not a per-period or pro-rated figure, and
    `assign_teaching_skill` creates open-ended assignments that overlap every
    later period. The owner selected the one-off basis: an assignment is
    compensated once, in the first payroll period that covers it. A later
    overlapping period therefore posts nothing for it and reports it under
    `already_compensated_prior_period`, so the reason is visible in the audit
    trail instead of being a silent skip or a second payment.

    Native preconditions (enforced by HRMS, not re-implemented here): the
    employee is Active and holds a submitted Salary Structure Assignment
    effective on or before the payroll date. Native Salary Slip classifies
    rows by the salary component's own type, so deduction adjustments
    require an owner-provided deduction-type component.
    """
    def work(actor):
        start = _policy(validate_schedule_date, period_start)
        end = _policy(validate_schedule_date, period_end)
        if end < start:
            raise frappe.ValidationError("Payroll period end precedes period start")
        company_name = _bounded(company, "Company")
        component = _bounded(salary_component, "Salary Component")
        deduction = _bounded(deduction_component, "Deduction Component") if deduction_component else ""
        if not frappe.db.exists("Company", company_name):
            raise frappe.ValidationError("Unknown company")
        if not frappe.db.exists("Salary Component", component):
            raise frappe.ValidationError("Unknown salary component")
        if deduction and not frappe.db.exists("Salary Component", deduction):
            raise frappe.ValidationError("Unknown deduction salary component")
        currency = frappe.db.get_value("Company", company_name, "default_currency")
        if not currency:
            raise frappe.ValidationError(
                f"Company {company_name} has no default currency; payroll input cannot be priced")
        rows = frappe.db.sql(
            "select name, student_group, skill, instructor, contract, effective_start, effective_end "
            "from `tabTH Teaching Assignment` where effective_start <= %s "
            "and (effective_end is null or effective_end >= %s)", (end, start), as_dict=True)
        posted, skipped_fixed, skipped_existing, adjustments_posted = {}, [], 0, 0
        already_compensated = {}
        contracts = {}
        for instructor in sorted({row.instructor for row in rows}):
            contracts[instructor] = frappe.get_doc(
                CONTRACT, _covering_contract_name(instructor, start, end))
        _lock_covering_contracts(contracts, start, end)
        for row in rows:
            contract = contracts[row.instructor]
            if contract.compensation_model == "Fixed Salary":
                if contract.name not in skipped_fixed:
                    skipped_fixed.append(contract.name)
                continue
            already_paid = _paid_dates(ASSIGNMENT, row.name)
            if end in already_paid:
                skipped_existing += 1
                continue
            if already_paid:
                # Owner decision D12 (2026-09-19): the flat contract amount is a
                # ONE-OFF payable. An assignment is compensated once, in the
                # first payroll period that covers it; a later period that also
                # overlaps the same open-ended assignment is not a second
                # payable. Reported rather than skipped silently, so the audit
                # trail shows why nothing was posted.
                already_compensated[row.name] = already_paid
                continue
            amount = _payable_for(contract, row)
            salary = frappe.get_doc(dict(
                doctype=ADDITIONAL_SALARY, employee=contract.employee,
                salary_component=component, amount=amount, payroll_date=end,
                company=company_name, currency=currency,
                ref_doctype=ASSIGNMENT, ref_docname=row.name))
            salary.flags.ignore_permissions = True
            salary.flags.ignore_links = True
            salary.insert(ignore_permissions=True)
            posted.setdefault(row.instructor, []).append(
                {"name": salary.name, "assignment": row.name, "amount": amount})
        for instructor, contract in sorted(contracts.items()):
            if contract.compensation_model == "Fixed Salary":
                continue
            due = [a for a in (contract.adjustments or [])
                   if start <= str(a.effective_date) <= end]
            if not due:
                continue
            if any(a.adjustment_type == "Deduction" for a in due) and not deduction:
                raise frappe.ValidationError(
                    "Deduction adjustments require an explicit deduction salary component")
            # BUG-PAY-02: the one-off key is the adjustment ROW, not the
            # contract. A per-contract key swallowed every later adjustment
            # once any one of them had posted. Each due adjustment carries its
            # own audit link (TH Contract Adjustment row name) and its own
            # one-off state, exactly like the assignment path above.
            for adjustment in due:
                adjustment_paid = _paid_dates(ADJUSTMENT, adjustment.name)
                if end in adjustment_paid:
                    skipped_existing += 1
                    continue
                if adjustment_paid:
                    already_compensated[f"{contract.name}:{adjustment.name}"] = adjustment_paid
                    continue
                salary = frappe.get_doc(dict(
                    doctype=ADDITIONAL_SALARY, employee=contract.employee,
                    salary_component=(deduction if adjustment.adjustment_type == "Deduction"
                                      else component),
                    amount=float(adjustment.amount),
                    payroll_date=end, company=company_name, currency=currency,
                    type="Earning" if adjustment.adjustment_type == "Bonus" else "Deduction",
                    ref_doctype=ADJUSTMENT, ref_docname=adjustment.name))
                salary.flags.ignore_permissions = True
                salary.flags.ignore_links = True
                salary.insert(ignore_permissions=True)
                posted.setdefault(instructor, []).append(
                    {"name": salary.name, "adjustment": adjustment.adjustment_type,
                     "amount": float(adjustment.amount)})
                adjustments_posted += 1
        result = {"period": [start, end], "company": company_name,
                  "salary_component": component, "deduction_component": deduction,
                  "assignments": len(rows),
                  "posted": posted, "skipped_fixed_salary_contracts": sorted(skipped_fixed),
                  "skipped_existing": skipped_existing,
                  "adjustments_posted": adjustments_posted,
                  "already_compensated_prior_period": already_compensated}
        return result, dict(target=digest([start, end, company_name, component]),
                            after_hash=digest(result))

    return _execute("calculate_teaching_compensation", request_key,
                    {"period_start": period_start, "period_end": period_end,
                     "company": company, "salary_component": salary_component,
                     "deduction_component": deduction_component or ""}, work)
