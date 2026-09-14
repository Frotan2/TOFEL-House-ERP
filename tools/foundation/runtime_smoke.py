"""Synthetic cross-app qualification fixtures; not an installed product app.

Invoked only by Bench on the disposable foundation.localhost site. Uses upstream
Document/controllers with validations intact. No scoring/placement/custom schema.
"""
import hashlib
import json
import os
from pathlib import Path
import time


def run():
    import frappe
    from frappe.utils import nowdate, getdate

    if frappe.local.site not in ("foundation.localhost", "upgrade.localhost") or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Synthetic smoke fixtures are restricted to the disposable Actions site")
    report = {"scope": "Synthetic upstream data and explicitly enumerated assertions", "status": "running",
              "checks": [], "records": {}, "phase2_gate_passed": False}
    records = report["records"]
    destination = Path(os.environ["FOUNDATION_BUSINESS_REPORT"])
    today = nowdate()
    year = getdate(today).year
    start, end = f"{year}-01-01", f"{year}-12-31"

    def create(doctype, **fields):
        return frappe.get_doc(dict(doctype=doctype, **fields)).insert()

    def checked(name, function):
        started = time.monotonic()
        report["active_check"] = name
        value = function()
        frappe.db.commit()
        report["checks"].append({"name": name, "status": "pass", "seconds": round(time.monotonic() - started, 3), "observation": value})
        destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
        return value

    def denied(name, function):
        frappe.db.savepoint("negative_probe")
        try:
            function()
        except (frappe.PermissionError, frappe.MandatoryError, frappe.LinkValidationError, frappe.ValidationError) as exc:
            observation = {"exception": type(exc).__name__, "message": str(exc)}
        else:
            raise AssertionError(name + " was unexpectedly accepted")
        finally:
            frappe.db.rollback(save_point="negative_probe")
        return observation

    try:
        frappe.set_user("Administrator")
        import importlib
        report["app_versions"] = {app: importlib.import_module(app).__version__ for app in frappe.get_installed_apps()}

        def company_setup():
            from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
            # App installation is not onboarding. Use the real upstream wizard
            # stages, including presets, rather than inserting a fake Transit type.
            setup_complete({"language": "English", "timezone": "UTC", "country": "United States",
                            "currency": "USD", "company_name": "Validation Institute", "company_abbr": "VI",
                            "chart_of_accounts": "Standard", "fy_start_date": start, "fy_end_date": end,
                            "enable_telemetry": 0, "setup_demo": 0})
            assert frappe.is_setup_complete()
            assert frappe.db.exists("Warehouse Type", "Transit")
            company = frappe.get_doc("Company", "Validation Institute")
            holiday_date = start if today != start else end
            holidays = create("Holiday List", holiday_list_name=f"Validation Calendar {year}",
                              from_date=start, to_date=end,
                              holidays=[{"holiday_date": holiday_date, "description": "Synthetic institution closure"}])
            company.default_holiday_list = holidays.name
            company.save()
            records.update(holiday_list=holidays.name, holiday_date=holiday_date)
            fiscal = frappe.db.get_value("Fiscal Year", {"year_start_date": start, "year_end_date": end}, "name")
            assert fiscal
            branch = create("Branch", branch="Validation Branch")
            records.update(company=company.name, branch=branch.name, fiscal_year=fiscal)
            return {"setup_complete": True, "company": company.name, "branch": branch.name,
                    "account_count": frappe.db.count("Account", {"company": company.name})}
        checked("company-chart-and-branch", company_setup)

        def academic_setup():
            ay = create("Academic Year", academic_year_name=f"Validation {year}", year_start_date=start, year_end_date=end)
            term = create("Academic Term", academic_year=ay.name, term_name="Validation Term", term_start_date=start, term_end_date=end)
            course = create("Course", course_name="Validation Course")
            program = create("Program", program_name="Validation Program", courses=[{"course": course.name, "required": 1}])
            batch = create("Student Batch Name", batch_name="Validation Batch")
            employee = create("Employee", first_name="Validation", last_name="Instructor", gender="Female",
                              date_of_birth="1990-01-01", date_of_joining=start, company=records["company"],
                              branch=records["branch"], status="Active")
            instructor = create("Instructor", instructor_name="Validation Instructor", employee=employee.name, status="Active")
            room = create("Room", room_name="Validation Room", seating_capacity=20)
            group = create("Student Group", student_group_name="Validation Class", group_based_on="Course",
                           academic_year=ay.name, academic_term=term.name, program=program.name, course=course.name,
                           batch=batch.name, max_strength=20, instructors=[{"instructor": instructor.name}])
            admission = create("Student Admission", title="Validation Admission", academic_year=ay.name,
                               admission_start_date=start, admission_end_date=end, published=0,
                               program_details=[{"program": program.name}])
            records.update(academic_year=ay.name, academic_term=term.name, course=course.name, program=program.name,
                           batch=batch.name, employee=employee.name, instructor=instructor.name, room=room.name,
                           group=group.name, admission=admission.name)
            return {"instructor_employee": instructor.employee, "group": group.name, "student_count": frappe.db.count("Student")}
        checked("academic-context-and-employee-link", academic_setup)

        def plan_setup():
            criterion = create("Assessment Criteria", assessment_criteria="Validation Criterion")
            scale = create("Grading Scale", grading_scale_name="Validation Scale", intervals=[
                {"grade_code": "A", "threshold": 90}, {"grade_code": "B", "threshold": 70}, {"grade_code": "F", "threshold": 0}])
            scale.submit()
            assessment_group = create("Assessment Group", assessment_group_name="Validation Assessments",
                                      parent_assessment_group="All Assessment Groups", is_group=0)
            plan = create("Assessment Plan", student_group=records["group"], course=records["course"],
                          program=records["program"], academic_year=records["academic_year"], academic_term=records["academic_term"],
                          assessment_name="Validation Assessment", assessment_group=assessment_group.name, grading_scale=scale.name,
                          schedule_date=today, from_time="15:00:00", to_time="16:00:00", room=records["room"],
                          examiner=records["instructor"], maximum_assessment_score=100,
                          assessment_criteria=[{"assessment_criteria": criterion.name, "maximum_score": 100}])
            plan.submit()
            records.update(criterion=criterion.name, grading_scale=scale.name, assessment_group=assessment_group.name, assessment_plan=plan.name)
            assert frappe.db.count("Student") == 0
            return {"plan": plan.name, "students_at_plan_creation": 0, "meaning": "A course/group Plan can precede Student creation; not an applicant-owned Result"}
        checked("assessment-plan-before-students", plan_setup)

        def result_fields(student=None):
            return dict(student=student, assessment_plan=records["assessment_plan"], student_group=records["group"],
                        course=records["course"], program=records["program"], grading_scale=records["grading_scale"],
                        assessment_group=records["assessment_group"], maximum_score=100,
                        details=[{"assessment_criteria": records["criterion"], "score": 75}])
        checked("result-without-student-rejected", lambda: denied("Missing Student result", lambda: create("Assessment Result", **result_fields())))

        def enrollments():
            from education.education.api import enroll_student
            students, applicants, enrollments, user_links = [], [], [], []
            for label in ("alpha", "beta"):
                email = f"validation-{label}@example.test"
                create("User", email=email, first_name="Validation " + label, user_type="Website User",
                       send_welcome_email=0, new_password=os.environ["FOUNDATION_TEST_PASSWORD"], roles=[{"role": "Student"}])
                applicant = create("Student Applicant", first_name="Validation " + label, student_email_id=email,
                                   program=records["program"], academic_year=records["academic_year"],
                                   academic_term=records["academic_term"], student_admission=records["admission"], application_status="Approved")
                # This is the supported conversion, not a fake Student made for placement.
                enrollment = enroll_student(applicant.name)
                student = frappe.get_doc("Student", enrollment.student)
                user_links.append({"student": student.name, "automatic_existing_user_link": student.user})
                if student.user != email:
                    student.user = email
                    student.save()  # explicit operator linkage; record rather than claim automatic linking
                enrollment.student_batch_name = records["batch"]
                enrollment.save()
                enrollment.submit()
                student.reload()
                assert student.student_applicant == applicant.name and student.customer
                assert frappe.db.get_value("Student Applicant", applicant.name, "application_status") == "Admitted"
                assert frappe.db.exists("Course Enrollment", {"program_enrollment": enrollment.name, "student": student.name, "course": records["course"]})
                students.append(student.name); applicants.append(applicant.name); enrollments.append(enrollment.name)
            group = frappe.get_doc("Student Group", records["group"])
            for student in students:
                group.append("students", {"student": student, "active": 1})
            group.save()
            records.update(students=students, applicants=applicants, enrollments=enrollments)
            return {"students": students, "applicants": applicants, "enrollments": enrollments, "user_link_observations": user_links}
        checked("applicant-student-customer-enrollment-group", enrollments)
        checked("applicant-cannot-own-academic-result", lambda: denied("Applicant Student link", lambda: create("Assessment Result", **result_fields(records["applicants"][0]))))

        def attendance_assessment():
            schedule = create("Course Schedule", student_group=records["group"], course=records["course"],
                              instructor=records["instructor"], room=records["room"], schedule_date=today,
                              from_time="10:00:00", to_time="11:00:00")
            attendance = create("Student Attendance", student=records["students"][0], student_group=records["group"],
                                course_schedule=schedule.name, date=today, status="Present")
            attendance.submit()
            result = create("Assessment Result", **result_fields(records["students"][0]))
            result.submit()
            assert result.total_score == 75 and result.grade == "B"
            records.update(course_schedule=schedule.name, attendance=attendance.name, assessment_result=result.name)
            return {"attendance": attendance.name, "result": result.name, "score": result.total_score, "grade": result.grade}
        checked("schedule-attendance-submitted-assessment", attendance_assessment)

        def finance():
            from education.education.doctype.fee_schedule.fee_schedule import create_sales_invoice
            from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
            company = frappe.get_doc("Company", records["company"])
            receivable = company.default_receivable_account
            income = company.default_income_account
            cash = frappe.db.get_value("Account", {"company": company.name, "account_type": "Cash", "is_group": 0}, "name")
            assert receivable and income and cash
            category = create("Fee Category", category_name="Validation Tuition", description="Synthetic course fee",
                              item_defaults=[{"company": company.name, "income_account": income, "selling_cost_center": company.cost_center}])
            structure = create("Fee Structure", program=records["program"], academic_year=records["academic_year"],
                               academic_term=records["academic_term"], company=company.name, currency="USD", receivable_account=receivable,
                               cost_center=company.cost_center, components=[{"fees_category": category.name, "item": category.item, "amount": 100, "discount": 10}])
            structure.submit()
            component = structure.components[0]
            schedule = create("Fee Schedule", fee_structure=structure.name, program=records["program"],
                              academic_year=records["academic_year"], academic_term=records["academic_term"],
                              company=company.name, currency="USD", receivable_account=receivable, cost_center=company.cost_center,
                              due_date=today, posting_date=today, student_groups=[{"student_group": records["group"]}],
                              components=[{"fees_category": category.name, "item": component.item, "amount": 100, "discount": 10, "total": 90}])
            schedule.submit()
            invoice = frappe.get_doc("Sales Invoice", create_sales_invoice(schedule.name, records["students"][0]))
            if invoice.docstatus == 0:
                invoice.submit()
            assert float(invoice.grand_total) == 90
            payment = get_payment_entry("Sales Invoice", invoice.name, bank_account=cash)
            payment.reference_no = "VALIDATION-ONLY"
            payment.reference_date = today
            payment.insert(); payment.submit()
            invoice.reload()
            assert float(invoice.outstanding_amount) == 0
            gl = frappe.db.sql("SELECT SUM(debit), SUM(credit), COUNT(*) FROM `tabGL Entry` WHERE voucher_no IN (%s,%s) AND is_cancelled=0", (invoice.name, payment.name))[0]
            assert float(gl[0]) == float(gl[1]) and gl[2] >= 4
            records.update(fee_structure=structure.name, fee_schedule=schedule.name, invoice=invoice.name, payment=payment.name)
            return {"invoice": invoice.name, "payment": payment.name, "discounted_total": invoice.grand_total,
                    "outstanding": invoice.outstanding_amount, "gl_debit": gl[0], "gl_credit": gl[1], "gl_rows": gl[2]}
        checked("fee-invoice-discount-payment-ledger", finance)

        def attachment():
            content = b"Synthetic foundation restore proof. No student PII.\n"
            doc = create("File", file_name="foundation-proof.txt", is_private=1, attached_to_doctype="Student",
                         attached_to_name=records["students"][0], content=content)
            records.update(private_file=doc.name, private_file_url=doc.file_url, private_file_sha256=hashlib.sha256(content).hexdigest())
            assert hashlib.sha256(Path(doc.get_full_path()).read_bytes()).hexdigest() == records["private_file_sha256"]
            public_content = b"Public synthetic validation notice.\n"
            public = create("File", file_name="foundation-public-proof.txt", is_private=0, content=public_content)
            records.update(public_file=public.name, public_file_sha256=hashlib.sha256(public_content).hexdigest())
            return {"file": doc.name, "private": doc.is_private, "sha256": records["private_file_sha256"], "public_file": public.name}
        checked("private-attachment", attachment)
        report["status"] = "pass"
        report["not_tested"] = ["refunds", "legacy Fees duplication", "payroll posting", "authorization", "portal browser UI"]
    except Exception as exc:
        frappe.db.rollback()
        report["status"] = "fail"
        report["failure"] = {"exception": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        frappe.set_user("Administrator")
        destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report


if __name__ == "__main__":
    import sys
    import frappe
    site = sys.argv[1]
    if site != "foundation.localhost":
        raise SystemExit("Unexpected test site")
    frappe.init(site=site, sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        run()
    finally:
        frappe.destroy()
