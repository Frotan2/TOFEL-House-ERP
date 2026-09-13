"""Native permission-configuration experiment after a retained baseline failure.

Synthetic users/sites only. Does not change roles, DocPerms, core code or validators.
"""
import json
import os
from pathlib import Path
import sys


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.argv[1:] != ["foundation.localhost"]:
        raise SystemExit("Restricted to the disposable Actions foundation site")
    import frappe
    records = json.loads(Path(os.environ["FOUNDATION_BUSINESS_REPORT"]).read_text())["records"]
    frappe.init(site=sys.argv[1], sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        created = []
        # Close uncontrolled activation and document-sharing paths using native
        # settings. No role is activated by this validation-only script.
        for doctype, fields in (("Website Settings", {"disable_signup": 1}),
                                ("Education Settings", {"user_creation_skip": 1}),
                                ("System Settings", {"apply_strict_user_permissions": 1, "disable_document_sharing": 1})):
            settings = frappe.get_single(doctype)
            settings.update(fields)
            settings.save()
        for label, student in zip(("alpha", "beta"), records["students"], strict=True):
            user = f"validation-{label}@example.test"
            doc = frappe.get_doc("Student", student)
            assert doc.user == user and doc.customer
            for allow, value in (("Student", student), ("Customer", doc.customer)):
                permission = frappe.get_doc({"doctype": "User Permission", "user": user,
                                            "allow": allow, "for_value": value, "apply_to_all_doctypes": 1}).insert()
                created.append({"user": user, "allow": allow, "for_value": value, "name": permission.name})
            frappe.clear_cache(user=user)
        # With auto-creation off, a new Student must not silently receive a
        # portal account/role before policy assignment.
        pending_email = "validation-unprovisioned@example.test"
        pending = frappe.get_doc({"doctype": "Student", "first_name": "Validation Pending",
                                  "student_email_id": pending_email}).insert()
        assert not frappe.db.exists("User", pending_email)
        records["unprovisioned_student"] = pending.name
        records["unprovisioned_email"] = pending_email
        marker = frappe.get_doc({"doctype": "ToDo", "description": "Source-only site isolation marker"}).insert()
        records["source_only_todo"] = marker.name
        business_path = Path(os.environ["FOUNDATION_BUSINESS_REPORT"])
        business = json.loads(business_path.read_text())
        business["records"] = records
        frappe.db.commit()
        business_path.write_text(json.dumps(business, indent=2) + "\n")
        print(json.dumps({"native_user_permissions": created, "scope": "Configuration experiment; not automatic provisioning or full authorization proof"}))
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
