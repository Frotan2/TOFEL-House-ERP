"""Containment for the JSON short-circuit in Frappe's HTML sanitizer (GHSA-vhrc-hgrq-x75r exposure).

Frappe's ``sanitize_html`` (frappe/utils/html_utils.py, pinned at 988e54f3) returns its
input unchanged when ``is_json(value)`` is true, before nh3 runs. A stored value such as
``"<img src=x onerror=...>"`` (double quotes included) is a valid JSON string literal, so it
skips the sanitizer and is later rendered as HTML in other users' browsers. The
``javascript:`` link injection in @tiptap/extension-link therefore reaches other users
through that path, which contradicts a self-only disposition.

This module runs on Frappe's ``validate`` document event. Frappe fires that event before
its own ``_sanitize_content`` pass. For each HTML-capable value that is valid JSON and
contains markup characters, it re-runs ``sanitize_html`` with ``always_sanitize=True``, so
nh3 cleans the value before Frappe's own pass sees it. Values that Frappe would already
sanitize are not changed, so ordinary content keeps its current behavior.
"""
from __future__ import annotations

import json

# Fieldtypes that Frappe sanitizes on save and that are rendered as HTML somewhere in the desk.
HTML_FIELDTYPES = frozenset(("Text Editor", "Text", "Small Text", "Markdown Editor"))
MARKUP_CHARACTERS = ("<", ">")


def _sanitizer_callables():
    from frappe.utils.html_utils import is_json, sanitize_html

    return sanitize_html, is_json


def is_json_shape(value: str) -> bool:
    try:
        json.loads(value)
    except ValueError:
        return False
    return True


def contain_value(value, *, linkify: bool, sanitize, is_json_fn=is_json_shape):
    """Return the value to store: sanitized only when Frappe's JSON short-circuit would skip it."""
    if not isinstance(value, str) or not value:
        return value
    if not any(char in value for char in MARKUP_CHARACTERS):
        return value
    if not is_json_fn(value):
        return value  # Frappe's own pass sanitizes this value
    return sanitize(value, linkify=linkify, always_sanitize=True)


def contain_document(doc, *, sanitize, is_json_fn=is_json_shape) -> list[str]:
    """Contain every HTML-capable field on ``doc`` and its child rows. Returns the changed field names."""
    changed: list[str] = []
    holders = [doc, *doc.get_all_children()] if hasattr(doc, "get_all_children") else [doc]
    for holder in holders:
        meta = getattr(holder, "meta", None)
        if meta is None:
            continue
        for df in meta.fields:
            if df.fieldtype not in HTML_FIELDTYPES or df.get("ignore_xss_filter"):
                continue
            current = holder.get(df.fieldname)
            contained = contain_value(current, linkify=df.fieldtype == "Text Editor",
                                      sanitize=sanitize, is_json_fn=is_json_fn)
            if contained != current:
                holder.set(df.fieldname, contained)
                changed.append(df.fieldname)
    return changed


def contain_html_fields(doc, method=None) -> None:
    """Frappe ``validate`` doc event (wired in hooks.py for every doctype)."""
    sanitize, is_json_fn = _sanitizer_callables()
    contain_document(doc, sanitize=sanitize, is_json_fn=is_json_fn)
