"""Verify an actual restore of synthetic records/files in a distinct clean site."""
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    import frappe
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.argv[1] not in ("restore.localhost", "recovery.localhost"):
        raise SystemExit("Restore verification is restricted to the isolated Actions restore site")
    expected = json.loads(Path(os.environ["FOUNDATION_BUSINESS_REPORT"]).read_text())["records"]
    output = Path(os.environ["FOUNDATION_RESTORE_REPORT"])
    report = {"scope": "Actual restored synthetic site; no production data", "status": "running", "checks": []}
    frappe.init(site=sys.argv[1], sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        for student, applicant, enrollment in zip(expected["students"], expected["applicants"], expected["enrollments"]):
            doc = frappe.get_doc("Student", student)
            assert doc.student_applicant == applicant and doc.customer
            assert frappe.db.exists("Customer", doc.customer)
            en = frappe.get_doc("Program Enrollment", enrollment)
            assert en.docstatus == 1 and en.student == student
            assert frappe.db.exists("Course Enrollment", {"program_enrollment": enrollment, "course": expected["course"]})
        report["checks"].append({"name": "student-applicant-customer-enrollment-links", "status": "pass"})
        result = frappe.get_doc("Assessment Result", expected["assessment_result"])
        assert result.docstatus == 1 and result.grade == "B" and result.total_score == 75
        attendance = frappe.get_doc("Student Attendance", expected["attendance"])
        assert attendance.docstatus == 1 and attendance.status == "Present"
        invoice = frappe.get_doc("Sales Invoice", expected["invoice"])
        assert invoice.docstatus == 1 and float(invoice.outstanding_amount) == 0
        payment = frappe.get_doc("Payment Entry", expected["payment"])
        assert payment.docstatus == 1
        report["checks"].append({"name": "submitted-attendance-grade-invoice-payment", "status": "pass"})
        for label in ("private", "public"):
            doc = frappe.get_doc("File", expected[label + "_file"])
            actual = hashlib.sha256(Path(doc.get_full_path()).read_bytes()).hexdigest()
            assert actual == expected[label + "_file_sha256"]
            report["checks"].append({"name": label + "-file-restored", "status": "pass", "sha256": actual})
        if sys.argv[1] == "recovery.localhost":
            from frappe.sessions import clear_all_sessions
            captured = json.loads(Path(os.environ["FOUNDATION_CAPTURED_SESSION"]).read_text())["sid"]
            # Sessions is a framework SQL table, not a DocType, and has no name
            # column. db.exists() selects name and can return a false negative.
            # Check the native sid column directly, with a bound parameter.
            def captured_session_count():
                return frappe.db.sql("SELECT COUNT(*) FROM `tabSessions` WHERE sid = %s", (captured,))[0][0]
            assert captured_session_count() == 1, "Backup did not contain exactly one captured live source session"
            clear_all_sessions(reason="Revoke copied sessions during isolated security recovery")
            assert captured_session_count() == 0
            report["checks"].append({"name": "copied-live-session-found-and-revoked-with-native-session-api", "status": "pass"})
            assert "foundation_security" in frappe.get_installed_apps()
            for dt, field in (("Website Settings", "disable_signup"), ("Education Settings", "user_creation_skip"),
                              ("System Settings", "apply_strict_user_permissions"), ("System Settings", "disable_document_sharing")):
                assert frappe.db.get_single_value(dt, field) == 1
            from foundation_security.guards import validate_student_scope
            for label in ("alpha", "beta"):
                frappe.set_user(f"validation-{label}@example.test")
                validate_student_scope()
            frappe.set_user("Administrator")
            report["checks"].append({"name": "security-app-settings-and-native-permission-scopes-restored", "status": "pass"})
        report["database"] = frappe.db.sql("SELECT VERSION(), @@character_set_server, @@collation_server")[0]
        report["schema"] = {}
        for doctype in ("Student", "Student Applicant", "Program Enrollment", "Course Enrollment", "Assessment Result", "Sales Invoice", "Payment Entry", "Employee", "Salary Slip", "Payroll Entry"):
            columns = frappe.db.get_table_columns(doctype)
            assert "name" in columns and "owner" in columns and "modified" in columns
            indexes = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}`", as_dict=True)
            report["schema"][doctype] = {"column_count": len(columns), "audit_fields": [x for x in ("owner", "creation", "modified", "modified_by", "docstatus") if x in columns],
                                         "indexes": [{"name": row.Key_name, "column": row.Column_name, "non_unique": row.Non_unique} for row in indexes]}
        frappe.db.savepoint("deletion_probe")
        try:
            frappe.delete_doc("Student", expected["students"][0])
        except frappe.LinkExistsError as exc:
            report["checks"].append({"name": "referenced-student-deletion-rejected", "status": "pass", "exception": type(exc).__name__})
        else:
            raise AssertionError("Referenced student was unexpectedly deletable")
        finally:
            frappe.db.rollback(save_point="deletion_probe")
        report["status"] = "pass"
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = {"exception": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        output.write_text(json.dumps(report, indent=2, default=str) + "\n")
        frappe.destroy()


if __name__ == "__main__":
    main()
