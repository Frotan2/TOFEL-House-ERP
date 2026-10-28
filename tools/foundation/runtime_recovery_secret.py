"""Exercise native encrypted-credential backup recovery without exposing secrets."""
import os
from pathlib import Path
import sys


def main():
    import frappe
    from frappe.utils.password import get_decrypted_password, set_encrypted_password
    allowed = (["prepare", "foundation.localhost"], ["verify", "recovery.localhost"])
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.argv[1:] not in allowed:
        raise SystemExit("Disposable source/recovery sites only")
    frappe.init(site=sys.argv[2], sites_path=str(Path.cwd()))
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        # No API key is generated or enabled. This is an encrypted Password-field
        # fixture using an already masked synthetic secret, not a real credential.
        secret = os.environ["FOUNDATION_TEST_PASSWORD"]
        if sys.argv[1] == "prepare":
            assert not frappe.db.get_value("User", "Administrator", "api_key")
            set_encrypted_password("User", "Administrator", secret, "api_secret")
            frappe.db.commit()
        assert get_decrypted_password("User", "Administrator", "api_secret") == secret
        print("Native encrypted Password field verified; secret omitted")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
