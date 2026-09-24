"""Safe WeasyPrint wrappers for TOEFL House.

WeasyPrint's `download_pdf` / `get_html` whitelist helpers accept arbitrary
URLs through the print-format builder and have historically been a
callable-of-convenience for SSRF/arbitrary-fetch findings (CVE-2024-32647,
GHSA-qr67-4wpm-xphm, plus the SEC-DEPS-01 bucket pinned for this runtime).

These overrides mirror the gate the beta-builder path already enforces:
WeasyPrint rendering is only enabled through ``print_format_builder_beta``
for users holding the ``print`` permission on the target document, and
only when the caller passes an explicit ``doctype=Print Format`` docname
rather than an arbitrary URL / `?format=pdf` request variable.

No vendor code is patched; these drop-in replacements are wired in via
``hooks.override_whitelisted_methods``.
"""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils.weasyprint import (  # type: ignore[import-not-found]
    download_pdf as _vendor_download_pdf,
    get_html as _vendor_get_html,
)


def _gate(doctype: str | None, docname: str | None) -> None:
    """Fail closed unless the beta-builder print permission gate is satisfied."""
    if doctype != "Print Format" or not docname:
        frappe.throw(
            _("WeasyPrint rendering is only enabled for beta-builder Print Formats"),
            frappe.PermissionError,
        )
    doc = frappe.get_doc(doctype, docname)
    doc.check_permission("print")
    # The beta-builder flag must be enabled on the Print Format record.
    if not getattr(doc, "print_format_builder_beta", False):
        frappe.throw(
            _("WeasyPrint rendering requires print_format_builder_beta"),
            frappe.PermissionError,
        )


def download_pdf(doctype: str | None = None, name: str | None = None,
                 format=None, doc=None, no_letterhead=0, **kwargs):  # noqa: A002
    _gate(doctype, name)
    return _vendor_download_pdf(
        doctype=doctype, name=name, format=format, doc=doc,
        no_letterhead=no_letterhead, **kwargs,
    )


def get_html(doctype: str | None = None, name: str | None = None,
             format=None, doc=None, no_letterhead=0, **kwargs):  # noqa: A002
    _gate(doctype, name)
    return _vendor_get_html(
        doctype=doctype, name=name, format=format, doc=doc,
        no_letterhead=no_letterhead, **kwargs,
    )
