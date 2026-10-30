"""Pinned native accounting exploration on a NEW, unowned disposable database.

This cannot enable product payout. Owned approval/security checks run separately
on placement-test.localhost; this site isolates upstream GL/PLE behavior without
mocking controllers, reference details, posting, cancellation or outstanding.
"""
import json
import os
from decimal import Decimal
from pathlib import Path


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Hosted disposable accounting probe only")
    import frappe
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    report = {"status": "running", "commit": os.environ["GITHUB_SHA"],
              "scope": "Native accounting mechanism only; NOT product authorization or Owner acceptance", "cases": []}
    output = Path(os.environ["TUITION_PROBE_REPORT"])
    frappe.init(site="refund-probe.localhost", sites_path=str(Path.cwd()))
    frappe.connect()
    try:
        if not (frappe.conf.allow_tests == 1 and frappe.conf.toefl_house_synthetic_only == 1):
            raise RuntimeError("Missing synthetic research-site guards")
        if "toefl_house" in frappe.get_installed_apps() or frappe.db.count("Company"):
            raise RuntimeError("Requires a fresh upstream-only site, never an Owner database")
        frappe.set_user("Administrator")
        today = frappe.utils.today()
        year = int(today[:4])
        from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

        # Run the pinned onboarding stages, including warehouse/party presets.
        # Installing apps alone does not create a usable native company catalog.
        setup_complete({"language": "English", "timezone": "Asia/Kabul", "country": "Afghanistan",
                        "currency": "AFN", "company_name": "SYN Refund Research", "company_abbr": "SRR",
                        "chart_of_accounts": "Standard", "fy_start_date": f"{year}-01-01",
                        "fy_end_date": f"{year}-12-31", "enable_telemetry": 0, "setup_demo": 0})
        assert frappe.is_setup_complete() and frappe.db.exists("Warehouse Type", "Transit")
        if not frappe.db.exists("Party Type", "Student"):
            frappe.get_doc(dict(doctype="Party Type", party_type="Student", account_type="Receivable")).insert()
        company = frappe.get_doc("Company", "SYN Refund Research")
        cash = frappe.db.get_value("Account", {"company": company.name, "account_type": "Cash", "is_group": 0}, "name")
        assert cash and company.default_receivable_account and company.default_income_account and company.cost_center
        # Native setup-wizard catalog scaffolding; no business pricing policy.
        for doctype, name, fields in (
            ("UOM", "Nos", {"uom_name": "Nos"}),
            ("Item Group", "All Item Groups", {"item_group_name": "All Item Groups", "is_group": 1}),
            ("Item Group", "Fee Component", {"item_group_name": "Fee Component", "parent_item_group": "All Item Groups"}),
            ("Customer Group", "All Customer Groups", {"customer_group_name": "All Customer Groups", "is_group": 1}),
            ("Customer Group", "Student", {"customer_group_name": "Student", "parent_customer_group": "All Customer Groups"}),
            ("Territory", "All Territories", {"territory_name": "All Territories", "is_group": 1}),
        ):
            if not frappe.db.exists(doctype, name):
                frappe.get_doc(dict(doctype=doctype, **fields)).insert()
        frappe.get_doc(dict(doctype="Item", item_code="SYN Refund Tuition", item_name="SYN Refund Tuition",
            item_group="Fee Component", stock_uom="Nos", is_stock_item=0, is_sales_item=1)).insert()
        frappe.db.set_single_value("Education Settings", "user_creation_skip", 1)
        student = frappe.get_doc(dict(doctype="Student", first_name="SYN Refund Research",
                                      student_email_id="refund-research@example.test", enabled=1)).insert()
        program = frappe.get_doc(dict(doctype="Program", program_name="SYN Refund Program")).insert()
        academic = frappe.get_doc(dict(doctype="Academic Year", academic_year_name=f"SYN Refund {year}",
                                       year_start_date=f"{year}-01-01", year_end_date=f"{year}-12-31")).insert()
        enrollment = frappe.get_doc(dict(doctype="Program Enrollment", student=student.name,
                                         program=program.name, academic_year=academic.name, enrollment_date=today)).insert()
        enrollment.submit()
        category = frappe.get_doc(dict(doctype="Fee Category", category_name="SYN Refund Tuition")).insert()
        structure = frappe.get_doc(dict(doctype="Fee Structure", program=program.name, academic_year=academic.name,
            company=company.name, receivable_account=company.default_receivable_account,
            income_account=company.default_income_account, cost_center=company.cost_center,
            components=[dict(fees_category=category.name, amount=1000)])).insert()
        frappe.db.commit()  # Only the isolated research-site masters, never Owner policy.

        def amount(value):
            return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))

        def snapshot(fee):
            def balance(account, credit=False):
                value = frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` "
                    "where company=%s and account=%s and is_cancelled=0", (company.name, account))[0][0]
                return amount(-value if credit else value)
            outstanding = frappe.db.get_value("Fees", fee.name, "outstanding_amount")
            gl = frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` where company=%s "
                "and account=%s and party_type='Student' and party=%s and against_voucher_type='Fees' "
                "and against_voucher=%s and is_cancelled=0",
                (company.name, company.default_receivable_account, student.name, fee.name))[0][0]
            assert amount(gl) == amount(outstanding), (gl, outstanding)
            ple = frappe.db.sql("select coalesce(sum(amount_in_account_currency),0) from `tabPayment Ledger Entry` "
                "where company=%s and account=%s and party_type='Student' and party=%s "
                "and against_voucher_type='Fees' and against_voucher_no=%s and delinked=0",
                (company.name, company.default_receivable_account, student.name, fee.name))[0][0]
            assert amount(ple) == amount(outstanding), (ple, outstanding)
            return {"outstanding": amount(outstanding), "cash": balance(cash),
                    "net_income": balance(company.default_income_account, True)}

        def voucher_rows(doc, expected):
            rows = frappe.db.get_all("GL Entry", filters={"voucher_type": doc.doctype,
                "voucher_no": doc.name, "is_cancelled": 0},
                fields=["account", "debit", "credit", "party_type", "party", "against_voucher_type", "against_voucher"])
            assert len(rows) == 2, rows
            actual = {row.account: (amount(row.debit), amount(row.credit)) for row in rows}
            assert actual == expected, (actual, expected)
            party_row = next(row for row in rows if row.account == company.default_receivable_account)
            assert (party_row.party_type, party_row.party) == ("Student", student.name)
            assert (party_row.against_voucher_type, party_row.against_voucher) == ("Fees", doc.references[0].reference_name
                if doc.doctype == "Payment Entry" else doc.accounts[1].reference_name)
            assert sum(Decimal(amount(row.debit))-Decimal(amount(row.credit)) for row in rows) == 0
            return [dict(row) for row in rows]

        for collected in (1000, 600):
            frappe.db.savepoint("refund_native_case")
            try:
                fee = frappe.get_doc(dict(doctype="Fees", naming_series="EDU-FEE-.YYYY.-",
                    student=student.name, program_enrollment=enrollment.name, program=program.name,
                    academic_year=academic.name, company=company.name, currency="AFN",
                    posting_date=today, due_date=today, fee_structure=structure.name,
                    receivable_account=company.default_receivable_account,
                    income_account=company.default_income_account, cost_center=company.cost_center,
                    components=[dict(fees_category=category.name, amount=1000)])).insert()
                fee.submit()
                receive = get_payment_entry("Fees", fee.name, party_amount=collected, bank_account=cash,
                                            party_type="Student", payment_type="Receive")
                receive.reference_no = "SYN-RESEARCH-RECEIPT"
                receive.reference_date = today
                receive.insert()
                receive.submit()
                before = snapshot(fee)
                assert before == {"outstanding": amount(1000-collected), "cash": amount(collected), "net_income": "1000.00"}
                credit = frappe.get_doc(dict(doctype="Journal Entry", voucher_type="Credit Note",
                    company=company.name, posting_date=today, accounts=[
                        dict(account=company.default_income_account, debit_in_account_currency=200, cost_center=company.cost_center),
                        dict(account=company.default_receivable_account, party_type="Student", party=student.name,
                             credit_in_account_currency=200, reference_type="Fees", reference_name=fee.name,
                             cost_center=company.cost_center)])).insert()
                credit.submit()
                credit_gl = voucher_rows(credit, {company.default_income_account: ("200.00", "0.00"),
                    company.default_receivable_account: ("0.00", "200.00")})
                credited = snapshot(fee)
                assert credited == {"outstanding": amount(800-collected), "cash": amount(collected), "net_income": "800.00"}
                payout = get_payment_entry("Fees", fee.name, party_amount=200, bank_account=cash,
                                           party_type="Student", payment_type="Pay")
                payout.reference_no = "SYN-RESEARCH-REFUND"
                payout.reference_date = today
                payout.insert()
                payout.submit()
                payout_gl = voucher_rows(payout, {cash: ("0.00", "200.00"),
                    company.default_receivable_account: ("200.00", "0.00")})
                paid = snapshot(fee)
                assert paid == {"outstanding": amount(1000-collected), "cash": amount(collected-200), "net_income": "800.00"}
                payout.cancel()
                credit.cancel()
                reversed_state = snapshot(fee)
                assert reversed_state == before
                report["cases"].append({"billed": "1000.00", "collected": amount(collected), "refund": "200.00",
                    "before": before, "credit": credited, "paid": paid, "reversed": reversed_state,
                    "credit_gl": credit_gl, "payout_gl": payout_gl,
                    "native_artifacts": {"fees": fee.name, "credit": credit.name, "payout": payout.name}})
            finally:
                frappe.db.rollback(save_point="refund_native_case")
        report["status"] = "pass"
    except Exception as exc:
        report.update(status="fail", failure_type=type(exc).__name__, failure=str(exc)[:800])
        raise
    finally:
        frappe.db.rollback()
        output.write_text(json.dumps(report, indent=2) + "\n")
        frappe.destroy()


if __name__ == "__main__":
    main()
