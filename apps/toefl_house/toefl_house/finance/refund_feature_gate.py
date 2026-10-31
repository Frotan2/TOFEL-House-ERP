"""Owner-directed release boundary: deferred paid-refund recovery is unavailable.

The experimental implementation is preserved outside the shipping app. Old
clients also hit this unconditional server refusal before any database access.
No site setting, client flag or staff role can activate it in this release.
"""
import frappe


@frappe.whitelist(methods=["POST"])
def disabled_paid_recovery(**kwargs):
    raise frappe.PermissionError(
        "Paid refund recovery is not available in this release. "
        "Original refund entries cannot be cancelled separately.")
