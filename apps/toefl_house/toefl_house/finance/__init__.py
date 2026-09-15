"""Thin finance operations over native ERPNext/Education money authorities.

Recorded owner policy (FINANCE-POLICY-APPROVAL.md, R05/B07 resolved at
framework level): tuition is billed through the native Education ``Fees``
authority from a submitted Program Enrollment and a Finance-configured
native ``Fee Structure``; the placement fee is configuration-driven through
a native ``Item`` price in a native selling ``Price List`` and, when
configured chargeable, a native ``Sales Invoice`` against a native
``Customer``. This module owns no money master, ledger, price, tax or
refund rule; rates always come from Finance-configured native records, never
from code. Payroll (A09) and academic assessment (B04/B05) remain outside
this slice.
"""
import frappe
from toefl_house.api import _execute
from toefl_house.policy import digest, validate_finance_dates
from toefl_house.security import finance_command_active, require_synthetic
from toefl_house.enrollment import deny_premature_invoice

FEES = "Fees"
INVOICE = "Sales Invoice"
FEE_STRUCTURE = "Fee Structure"
CUSTOMER = "Customer"
PROGRAM_ENROLLMENT = "Program Enrollment"
COMPANY = "TOEFL House"
PRICE_LIST = "TOEFL House Standard"
PLACEMENT_FEE_ITEM = "SYN-PLACEMENT-FEE"


def guard_fees(doc, method=None):
    require_synthetic()
    if finance_command_active(FEES):
        return
    raise frappe.ValidationError("Fees requires an authorized finance command")


def guard_sales_invoice(doc, method=None):
    # The enrollment slice's premature-billing guard stays in force unchanged;
    # the finance containment guard is chained after it (one handler per
    # doctype/method per app).
    deny_premature_invoice(doc, method)
    require_synthetic()
    if finance_command_active(INVOICE):
        return
    raise frappe.ValidationError("Sales Invoice requires an authorized finance command")


def issue_tuition_fees(request_key, program_enrollment, fee_structure,
                       posting_date, due_date):
    """Bill one submitted Program Enrollment from a configured Fee Structure.

    Native Fees stays the receivable authority: enrollment/student match,
    component amounts, GL posting and outstanding balance are all native.
    Duplicate billing for the same enrollment and fee structure is denied.
    """
    def work(actor):
        pe_name = _name(program_enrollment, "Program enrollment")
        fs_name = _name(fee_structure, "Fee structure")
        try:
            posting, due = validate_finance_dates(posting_date, due_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
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
            raise frappe.ValidationError("Fee structure does not match the enrollment program/year")
        components = frappe.db.get_all("Fee Component",
                                       filters={"parent": fs_name, "parenttype": FEE_STRUCTURE},
                                       fields=["fees_category", "amount"], order_by="idx")
        if not components:
            raise frappe.ValidationError("Fee structure has no configured components")
        if frappe.db.exists(FEES, {"program_enrollment": pe_name,
                                   "fee_structure": fs_name, "docstatus": ("!=", 2)}):
            raise frappe.ValidationError("Tuition is already billed for this enrollment")
        student_name = frappe.db.get_value("Student", pe.student, "student_name")
        fees = frappe.get_doc(dict(
            doctype=FEES, naming_series="EDU-FEE-.YYYY.-",
            student=pe.student, student_name=student_name or pe.student,
            program_enrollment=pe_name, program=pe.program,
            academic_year=pe.academic_year,
            company=fs.company or COMPANY, posting_date=posting, due_date=due,
            fee_structure=fs_name, receivable_account=fs.receivable_account,
            components=[dict(fees_category=c.fees_category, amount=c.amount)
                        for c in components]))
        fees.flags.ignore_permissions = True
        fees.insert(ignore_permissions=True)
        fees.flags.ignore_permissions = True
        fees.submit()
        row = frappe.db.get_value(FEES, fees.name,
                                  ["docstatus", "grand_total", "outstanding_amount",
                                   "currency"], as_dict=True)
        if int(row.docstatus or 0) != 1:
            raise frappe.ValidationError("Fees must be submitted")
        result = {
            "fees": fees.name, "program_enrollment": pe_name, "student": pe.student,
            "fee_structure": fs_name, "grand_total": float(row.grand_total),
            "outstanding_amount": float(row.outstanding_amount), "currency": row.currency,
            "posting_date": posting, "due_date": due,
        }
        return result, dict(target=fees.name,
                            after_hash=digest([fees.name, pe_name, fs_name, posting, due,
                                               {c.fees_category: float(c.amount)
                                                for c in components}]))

    return _execute("issue_tuition_fees", request_key,
                    {"program_enrollment": program_enrollment,
                     "fee_structure": fee_structure,
                     "posting_date": posting_date, "due_date": due_date}, work)


def issue_placement_fee(request_key, case, customer, posting_date, due_date):
    """Bill a placement case only when Finance has configured a charge.

    Chargeability is decided by the configured native price-list rate for the
    placement fee item: absent or zero means not billable and the command is
    denied; a positive configured rate produces a native Sales Invoice whose
    pricing, waiver (Pricing Rule) and tax behavior stay native. One active
    invoice per case; the case link is a Custom Field on Sales Invoice.
    """
    def work(actor):
        case_name = _name(case, "Placement case")
        customer_name = _name(customer, "Customer")
        try:
            posting, due = validate_finance_dates(posting_date, due_date)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        if not frappe.db.exists("TH Placement Case", case_name):
            raise frappe.ValidationError("Unknown placement case")
        if not frappe.db.exists(CUSTOMER, customer_name):
            raise frappe.ValidationError("Unknown customer")
        rate = frappe.db.get_value("Item Price",
                                   {"item_code": PLACEMENT_FEE_ITEM,
                                    "price_list": PRICE_LIST, "selling": 1},
                                   "price_list_rate")
        if not rate or float(rate) <= 0:
            raise frappe.ValidationError(
                "Placement fee is not configured as chargeable")
        if frappe.db.exists(INVOICE, {"th_placement_case": case_name,
                                      "docstatus": ("!=", 2)}):
            raise frappe.ValidationError("Placement fee is already billed for this case")
        invoice = frappe.get_doc(dict(
            doctype=INVOICE, customer=customer_name, company=COMPANY,
            posting_date=posting, due_date=due, set_posting_time=0,
            is_pos=0, th_placement_case=case_name,
            items=[dict(item_code=PLACEMENT_FEE_ITEM, qty=1)]))
        invoice.flags.ignore_permissions = True
        invoice.insert(ignore_permissions=True)
        invoice.flags.ignore_permissions = True
        invoice.submit()
        row = frappe.db.get_value(INVOICE, invoice.name,
                                  ["docstatus", "grand_total", "outstanding_amount",
                                   "currency", "net_total", "discount_amount"],
                                  as_dict=True)
        if int(row.docstatus or 0) != 1:
            raise frappe.ValidationError("Sales Invoice must be submitted")
        result = {
            "sales_invoice": invoice.name, "case": case_name, "customer": customer_name,
            "configured_rate": float(rate), "grand_total": float(row.grand_total),
            "net_total": float(row.net_total),
            "discount_amount": float(row.discount_amount or 0),
            "outstanding_amount": float(row.outstanding_amount), "currency": row.currency,
            "posting_date": posting, "due_date": due,
        }
        return result, dict(target=invoice.name,
                            after_hash=digest([invoice.name, case_name, customer_name,
                                               posting, due, float(row.grand_total)]))

    return _execute("issue_placement_fee", request_key,
                    {"case": case, "customer": customer,
                     "posting_date": posting_date, "due_date": due_date}, work)


def _name(value, label):
    if not isinstance(value, str) or not value or len(value) > 140:
        raise frappe.ValidationError(f"Invalid {label.lower()} reference")
    return value
