"""Repair the native Education root invariant without replacing catalog data."""
import frappe


def ensure_fee_component_root():
    """A Fee Component root must be a group before native defaults are editable.

    Education may create its leaf before the ERPNext wizard seeds item groups.
    The wizard then uses that existing root as the parent of its presets, but
    does not update its is_group flag. Preserve all names, links and defaults;
    native save validates and maintains the tree and records the change.
    """
    if frappe.session.user != "Administrator":
        raise frappe.PermissionError("Native catalog repair requires the installation administrator")
    if not frappe.db.exists("Item Group", "Fee Component"):
        return False
    doc = frappe.get_doc("Item Group", "Fee Component", for_update=True)
    if doc.parent_item_group or doc.is_group:
        return False
    roots = frappe.get_all("Item Group", filters={"parent_item_group": ["is", "not set"]},
                           pluck="name", limit_page_length=2)
    if roots != [doc.name]:
        raise frappe.ValidationError("Item Group has ambiguous roots; review the native catalog tree")
    doc.is_group = 1
    doc.save()
    return True


def setup_wizard_success(args):
    if not frappe.flags.in_setup_wizard or frappe.session.user != "Administrator":
        raise frappe.PermissionError("Catalog setup qualification requires the native setup wizard")
    ensure_fee_component_root()
