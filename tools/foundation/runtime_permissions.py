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
        for label, student in zip(("alpha", "beta"), records["students"], strict=True):
            user = f"validation-{label}@example.test"
            doc = frappe.get_doc("Student", student)
            assert doc.user == user and doc.customer
            for allow, value in (("Student", student), ("Customer", doc.customer)):
                permission = frappe.get_doc({"doctype": "User Permission", "user": user,
                                            "allow": allow, "for_value": value, "apply_to_all_doctypes": 1}).insert()
                created.append({"user": user, "allow": allow, "for_value": value, "name": permission.name})
            frappe.clear_cache(user=user)
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
