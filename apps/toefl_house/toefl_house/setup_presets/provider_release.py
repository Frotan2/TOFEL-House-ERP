"""Narrow the provider release gate to the native first-owner setup hook."""
from pathlib import Path
import sys

def has_verified_factory_release() -> bool:
    activation = Path("/run/activation")
    if not (activation / "customer-release.json").is_file():
        return False
    import frappe

    if frappe.local.site != "toeflhouse.localhost":
        return False
    # These modules are shipped by the read-only application image, not the
    # customer site. Sites without that image retain the normal wizard roles.
    if "/product" not in sys.path:
        sys.path.insert(0, "/product")
    from customer_release import verify
    from update_engine import UpdateError

    try:
        verify(activation)
    except UpdateError:
        return False
    return True


def first_owner_enrollment_allowed() -> bool:
    import frappe

    if not frappe.flags.in_setup_wizard or frappe.session.user != "Administrator":
        return False
    from toefl_house.security import REFUSED, site_mode

    if site_mode() != REFUSED or not has_verified_factory_release():
        return False
    # Serialize the check against another first-owner enrollment. The second
    # query uses a locking read so it sees committed rows after the wait.
    if not frappe.db.get_value("User", "Administrator", "name", for_update=True):
        return False
    return not frappe.db.get_value(
        "Has Role", {"parenttype": "User", "role": "Course Owner"}, "name", for_update=True,
    )
