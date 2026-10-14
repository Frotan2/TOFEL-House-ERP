"""Permission boundary for all WeasyPrint beta Print Format rendering.

The pinned Frappe PrintFormatGenerator is guarded at construction by the
hash-verified installation patch in tools/foundation/secure_weasyprint.py.
That seam covers printview, attach_print, Print Format methods, and both
whitelisted helpers, including non-HTTP jobs. No arbitrary HTML or URL is
passed to the renderer by these wrappers.
"""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils.weasyprint import download_pdf as _vendor_download_pdf
from frappe.utils.weasyprint import get_html as _vendor_get_html


def authorize_weasyprint(print_format: str, doc) -> None:
    """Require a matching beta format and target document print permission."""
    if not print_format or not getattr(doc, "doctype", None):
        frappe.throw(_("A target document and beta Print Format are required"), frappe.PermissionError)
    doc.check_permission("print")
    # Document flags can bypass check_permission in internal jobs; do not let
    # a caller-supplied ignore_permissions flag bypass the actual role/record
    # authorization at this shared constructor seam.
    if not frappe.has_permission(doc.doctype, "print", doc):
        frappe.throw(_("Print permission is required for WeasyPrint"), frappe.PermissionError)
    fmt = frappe.get_doc("Print Format", print_format)
    if (not fmt.get("print_format_builder_beta")
            or fmt.get("doc_type") != doc.doctype):
        frappe.throw(_("A matching beta Print Format is required"), frappe.PermissionError)


# Match the pinned vendor signatures exactly. The constructor above repeats
# the check for every path, including calls that bypass the whitelisted hooks.
def download_pdf(doctype: str, name: str, print_format: str, letterhead: str | None = None):
    return _vendor_download_pdf(doctype, name, print_format, letterhead)


def get_html(doctype: str, name: str, print_format: str, letterhead: str | None = None):
    return _vendor_get_html(doctype, name, print_format, letterhead)
