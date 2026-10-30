"""Real concurrent refund commands in a new synthetic Company only.

No mocks, production activation, shared Company edits, existing-user role
changes or deletions. New synthetic fixture records remain as audit evidence.
Each worker has its own real MariaDB connection and transaction.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import secrets
import threading
import time

import frappe


def run():
    from toefl_house.security import SYNTHETIC, command, site_mode
    from toefl_house.finance import tuition_refund_commands as commands

    assert site_mode() == SYNTHETIC and not frappe.conf.get("toefl_house_production_active")
    assert frappe.get_meta("TH Tuition Refund Request").has_field("voided_on")
    site, sites_path = frappe.local.site, str(frappe.local.sites_path)
    suffix = secrets.token_hex(4)
    prefix = "SYN Refund Race " + suffix
    company_name = prefix
    assert not frappe.db.exists("Company", company_name)
    frappe.set_user("Administrator")
    original_companies = {row.name: dict(row) for row in frappe.get_all("Company", fields=["*"], limit_page_length=0)}
    template = frappe.get_doc("Fees", frappe.db.get_value("Fees", {"docstatus": 1}, "name"))
    company = frappe.get_doc(dict(doctype="Company", company_name=company_name, abbr="R" + suffix[:4],
        default_currency="AFN", country="Afghanistan", chart_of_accounts="Standard")).insert()
    company.reload()
    cash = frappe.db.get_value("Account", {"company": company.name, "account_type": "Cash", "is_group": 0}, "name")
    assert cash and company.default_receivable_account and company.default_income_account and company.cost_center
    if company.default_cash_account != cash:
        company.default_cash_account = cash
        company.save()
    year = frappe.utils.getdate().year
    frappe.get_doc(dict(doctype="Fiscal Year", year=prefix + " " + str(year),
        year_start_date=f"{year}-01-01", year_end_date=f"{year}-12-31",
        companies=[dict(company=company.name)])).insert()
    branch = frappe.get_doc(dict(doctype="Branch", branch=prefix)).insert()
    actors = {}
    for label, roles in (("officer", ["Finance Officer"]), ("manager", ["General Manager"]),
                         ("payer", ["Finance Manager"]), ("scheduler", ["Teaching Scheduler"]),
                         ("enrollment", ["Enrollment Officer"])):
        name = "syn-refund-race-" + suffix + "-" + label + "@example.test"
        assert not frappe.db.exists("User", name)
        frappe.get_doc(dict(doctype="User", email=name, first_name=prefix + " " + label,
            enabled=1, send_welcome_email=0, roles=[dict(role=role) for role in roles])).insert()
        actors[label] = name
        for allow, value in (("Company", company.name), ("Branch", branch.name)):
            frappe.get_doc(dict(doctype="User Permission", user=name, allow=allow, for_value=value)).insert()
    assert "Finance Officer" not in frappe.get_roles(actors["payer"])
    category = frappe.get_doc(dict(doctype="Fee Category", category_name=prefix)).insert()
    structure = frappe.get_doc(dict(doctype="Fee Structure", program=template.program,
        academic_year=template.academic_year, company=company.name,
        receivable_account=company.default_receivable_account, income_account=company.default_income_account,
        cost_center=company.cost_center, components=[dict(fees_category=category.name, amount=100)])).insert()
    frappe.db.commit()
    payer_shares_before = [dict(row) for row in frappe.get_all("DocShare", filters={"user": actors["payer"]},
                                                             fields=["*"], order_by="name asc", limit_page_length=0)]

    def call(label, function, *args):
        frappe.set_user(actors[label])
        return function(*args)

    def cash_balance():
        return Decimal(str(frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` "
            "where company=%s and account=%s and is_cancelled=0 for update", (company.name, cash))[0][0]))

    def fixture(label, refund="10.00"):
        frappe.set_user("Administrator")
        student_login = "syn-refund-race-" + suffix + "-" + label + "-student@example.test"
        # Pre-create the synthetic website identity without welcome mail;
        # preserve the existing Education Settings user-creation policy.
        frappe.get_doc(dict(doctype="User", email=student_login, first_name=prefix + " " + label,
            user_type="Website User", enabled=1, send_welcome_email=0)).insert()
        student = frappe.get_doc(dict(doctype="Student", first_name=prefix + " " + label,
            student_email_id=student_login, user=student_login, enabled=1)).insert()
        from toefl_house.enrollment import _native_enrollment_write
        frappe.set_user(actors["enrollment"])
        with command("enroll_in_program", actors["enrollment"]), _native_enrollment_write():
            enrollment = frappe.get_doc(dict(doctype="Program Enrollment", student=student.name,
                program=template.program, academic_year=template.academic_year, enrollment_date=frappe.utils.today()))
            enrollment.insert(ignore_permissions=True)
            enrollment.flags.ignore_permissions = True
            enrollment.submit()
        # Trusted synthetic class scaffolding through the actual native
        # controller and its required server command; not an academic UI test.
        frappe.set_user(actors["scheduler"])
        with command("create_student_group", actors["scheduler"]):
            group = frappe.get_doc(dict(doctype="Student Group", student_group_name=prefix + " " + label,
                group_based_on="Batch", program=template.program, academic_year=template.academic_year,
                max_strength=5, th_branch=branch.name, th_class_status="Planned",
                th_class_start_date=frappe.utils.today(), th_class_end_date=frappe.utils.add_days(frappe.utils.today(), 30),
                th_delivery_mode="On-site",
                students=[dict(student=student.name, student_name=student.student_name, active=1)]))
            group.insert(ignore_permissions=True)
        frappe.set_user(actors["officer"])
        today = frappe.utils.today()
        with command("issue_tuition_fees", actors["officer"]):
            fee = frappe.get_doc(dict(doctype="Fees", student=student.name, company=company.name, program_enrollment=enrollment.name,
                posting_date=today, due_date=today, program=template.program, academic_year=template.academic_year,
                fee_structure=structure.name, currency="AFN", receivable_account=company.default_receivable_account,
                income_account=company.default_income_account, cost_center=company.cost_center,
                components=[dict(fees_category=category.name, amount=100)]))
            fee.insert(ignore_permissions=True)
            fee.flags.ignore_permissions = True
            fee.submit()
        frappe.set_user("Administrator")  # Native receipt fixture, restricted by the synthetic-site guard.
        receipt = frappe.get_doc(dict(doctype="Payment Entry", payment_type="Receive", company=company.name,
            posting_date=today, party_type="Student", party=student.name,
            paid_from=fee.receivable_account, paid_to=cash, paid_from_account_currency="AFN",
            paid_to_account_currency="AFN", source_exchange_rate=1, target_exchange_rate=1,
            paid_amount=50, received_amount=50, reference_no=prefix, reference_date=today,
            references=[dict(reference_doctype="Fees", reference_name=fee.name, allocated_amount=50)]))
        receipt.insert(ignore_permissions=True)
        receipt.flags.ignore_permissions = True
        receipt.submit()
        assert Decimal(str(frappe.db.get_value("Fees", fee.name, "outstanding_amount", for_update=True))) == 50, "Native receipt fixture did not leave 50 outstanding"
        opened = call("officer", commands.request_tuition_refund, "race_req_" + suffix + label,
            student.name, company.name, fee.name, refund, "SYN concurrent command qualification", prefix)
        call("manager", commands.approve_tuition_refund, "race_approve_" + suffix + label,
             opened["name"], "SYN independent approval " + prefix)
        frappe.db.commit()
        return dict(request=opened["name"], fees=fee.name, outstanding="50", amount=refund)

    def counts():
        return {dt: frappe.db.count(dt, {"company": company.name}) for dt in ("Journal Entry", "Payment Entry", "GL Entry")}

    def race(specs):
        barrier = threading.Barrier(2)

        def worker(spec):
            import frappe as worker_frappe
            worker_frappe.init(site=site, sites_path=sites_path)
            worker_frappe.connect()
            worker_frappe.local.doc_events_hooks = worker_frappe._load_app_hooks()["doc_events"]
            try:
                assert site_mode() == SYNTHETIC and not worker_frappe.conf.get("toefl_house_production_active")
                worker_frappe.set_user(actors[spec[0]])
                connection = worker_frappe.db.sql("select connection_id()")[0][0]
                barrier.wait(timeout=30)
                started = time.monotonic()
                try:
                    result = getattr(commands, spec[1])(*spec[2])
                    worker_frappe.db.commit()
                    return dict(status="success", result=result, connection=connection,
                                started=started, finished=time.monotonic())
                except worker_frappe.ValidationError as error:
                    worker_frappe.db.rollback()
                    return dict(status="refused", message=str(error), connection=connection,
                                started=started, finished=time.monotonic())
            finally:
                worker_frappe.db.rollback()
                worker_frappe.destroy()

        frappe.db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, spec) for spec in specs]
            outcomes = [future.result(timeout=90) for future in futures]
        assert len({row["connection"] for row in outcomes}) == 2, outcomes
        assert max(row["started"] for row in outcomes) < min(row["finished"] for row in outcomes), outcomes
        frappe.db.rollback()  # Discard the observer's old repeatable-read snapshot.
        return outcomes

    proof = dict(company=company.name, branch=branch.name, payer_has_no_finance_officer=True, cases=[])
    run.last_proof = proof
    same = fixture("same")
    before = counts()
    key = "race_same_" + suffix
    outcomes = race([("payer", "pay_tuition_refund", (key, same["request"]))] * 2)
    assert all(row["status"] == "success" for row in outcomes) and outcomes[0]["result"] == outcomes[1]["result"], outcomes
    assert counts() == {dt: count + {"Journal Entry": 1, "Payment Entry": 1, "GL Entry": 4}[dt] for dt, count in before.items()}
    proof["cases"].append(dict(case="same-key", outcomes=outcomes, one_pair_only=True))

    different = fixture("different")
    before = counts()
    outcomes = race([("payer", "pay_tuition_refund", ("race_different_" + suffix + str(i), different["request"])) for i in (1, 2)])
    assert sorted(row["status"] for row in outcomes) == ["refused", "success"], outcomes
    assert counts() == {dt: count + {"Journal Entry": 1, "Payment Entry": 1, "GL Entry": 4}[dt] for dt, count in before.items()}
    proof["cases"].append(dict(case="different-key-same-case", outcomes=outcomes, one_pair_only=True))

    withdrawal = fixture("withdrawal")
    before = counts()
    outcomes = race([("payer", "pay_tuition_refund", ("race_pay_void_" + suffix, withdrawal["request"])),
        ("manager", "void_tuition_refund", ("race_void_pay_" + suffix, withdrawal["request"], "SYN concurrent approval withdrawal"))])
    assert sorted(row["status"] for row in outcomes) == ["refused", "success"], outcomes
    status = frappe.db.get_value("TH Tuition Refund Request", withdrawal["request"], "status", for_update=True)
    assert status in {"Paid", "Voided"}
    posted = status == "Paid"
    assert counts() == {dt: count + ({"Journal Entry": 1, "Payment Entry": 1, "GL Entry": 4}[dt] if posted else 0) for dt, count in before.items()}
    proof["cases"].append(dict(case="payout-versus-withdrawal", outcomes=outcomes, final_status=status))

    cash_cases = [fixture("cash" + str(i), "40.00") for i in (1, 2)]
    frappe.set_user("Administrator")
    balance = cash_balance()
    assert balance > 60
    parent = frappe.db.get_value("Account", cash, "parent_account")
    other = frappe.get_doc(dict(doctype="Account", account_name=prefix + " reserve", company=company.name,
        parent_account=parent, account_type="Cash", account_currency="AFN", is_group=0)).insert()
    transfer = frappe.get_doc(dict(doctype="Payment Entry", payment_type="Internal Transfer", company=company.name,
        posting_date=frappe.utils.today(), paid_from=cash, paid_to=other.name,
        paid_from_account_currency="AFN", paid_to_account_currency="AFN", source_exchange_rate=1,
        target_exchange_rate=1, paid_amount=float(balance-60), received_amount=float(balance-60)))
    transfer.insert(ignore_permissions=True)
    transfer.flags.ignore_permissions = True
    transfer.submit()
    frappe.db.commit()
    assert cash_balance() == 60
    before = counts()
    outcomes = race([("payer", "pay_tuition_refund", ("race_cash_" + suffix + str(i), row["request"])) for i, row in enumerate(cash_cases)])
    assert sorted(row["status"] for row in outcomes) == ["refused", "success"], outcomes
    assert any(row["status"] == "refused" and "insufficient verified funds" in row["message"] for row in outcomes), outcomes
    assert cash_balance() == 20
    assert counts() == {dt: count + {"Journal Entry": 1, "Payment Entry": 1, "GL Entry": 4}[dt] for dt, count in before.items()}
    proof["cases"].append(dict(case="different-fees-shared-cash", outcomes=outcomes,
                               before_cash="60", each_proposal="40", after_cash="20", no_overdraft=True))
    for row in (same, different, withdrawal, *cash_cases):
        actual = Decimal(str(frappe.db.get_value("Fees", row["fees"], "outstanding_amount", for_update=True)))
        assert actual == Decimal(row["outstanding"]), dict(fees=row["fees"], expected=row["outstanding"], actual=str(actual))
    assert [dict(row) for row in frappe.get_all("DocShare", filters={"user": actors["payer"]}, fields=["*"],
                                               order_by="name asc", limit_page_length=0)] == payer_shares_before
    for name, row in original_companies.items():
        assert dict(frappe.get_all("Company", filters={"name": name}, fields=["*"], limit_page_length=1)[0]) == row
    frappe.db.commit()
    proof.update(status="pass", overlapping_independent_database_transactions=True,
                 all_original_outstanding_preserved=True, temporary_reference_permissions_removed=True,
                 existing_companies_unchanged=True, new_synthetic_evidence_preserved=True)
    return proof
