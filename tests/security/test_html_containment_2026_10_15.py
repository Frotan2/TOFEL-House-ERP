"""Regression for the JSON short-circuit in Frappe's HTML sanitizer (2026-10-15).

Frappe 988e54f3 ``sanitize_html`` returns its input unchanged when ``is_json(value)`` is
true. ``"<img src=x onerror=...>"`` (quotes included) is a valid JSON string, so it skips
nh3. These tests exercise the containment in ``foundation_security.html_containment``.

Scope: unit-level. They use the pinned contract (is_json short-circuit, nh3 cleaning
otherwise) as an injected model, not a live Frappe site. Runtime proof against a real
bench is recorded as pending in the evidence README.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace as Obj
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/foundation_security/foundation_security/html_containment.py"

spec = importlib.util.spec_from_file_location("html_containment", MODULE)
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)

PAYLOAD = '"<img src=x onerror=alert(document.domain)>"'
PLAIN_HTML = "<p>Hello <b>world</b></p>"


def model_sanitize(value, *, linkify=False, always_sanitize=False):
    """Model of the pinned contract: JSON short-circuit unless always_sanitize, then strip handlers and javascript: URLs."""
    if not always_sanitize and hc.is_json_shape(value):
        return value
    cleaned = re.sub(r"\s+on\w+\s*=\s*\"[^\"]*\"|\s+on\w+\s*=\s*[^\s>]+", "", value, flags=re.I)
    cleaned = re.sub(r"javascript:", "", cleaned, flags=re.I)
    return cleaned


def frappe_unfixed_pass(value, *, linkify=False):
    """What Frappe's own _sanitize_content does for one value (no containment)."""
    return model_sanitize(value, linkify=linkify, always_sanitize=False)


class ShortCircuitDefectTests(unittest.TestCase):
    def test_payload_is_valid_json_and_skips_the_unfixed_pass(self):
        self.assertTrue(hc.is_json_shape(PAYLOAD))
        self.assertEqual(frappe_unfixed_pass(PAYLOAD), PAYLOAD)  # the defect
        self.assertIn("onerror", frappe_unfixed_pass(PAYLOAD))

    def test_quoted_payload_decodes_to_live_markup(self):
        self.assertEqual(json.loads(PAYLOAD), "<img src=x onerror=alert(document.domain)>")


class ContainValueTests(unittest.TestCase):
    def test_bypass_shape_is_sanitized_with_always_sanitize(self):
        calls = []

        def sanitize(value, *, linkify=False, always_sanitize=False):
            calls.append((value, linkify, always_sanitize))
            return model_sanitize(value, linkify=linkify, always_sanitize=always_sanitize)

        out = hc.contain_value(PAYLOAD, linkify=True, sanitize=sanitize)
        self.assertNotIn("onerror", out)
        self.assertEqual(calls, [(PAYLOAD, True, True)])

    def test_ordinary_html_is_not_rewritten_by_containment(self):
        calls = []

        def sanitize(value, **kwargs):
            calls.append(value)
            return value

        self.assertIs(hc.contain_value(PLAIN_HTML, linkify=True, sanitize=sanitize), PLAIN_HTML)
        self.assertEqual(calls, [])  # Frappe's own pass handles non-JSON values

    def test_plain_text_and_non_strings_are_untouched(self):
        def sanitize(value, **kwargs):
            raise AssertionError("must not be called")

        for value in ("", None, 0, 12, "no markup here", "[1, 2]"):
            self.assertEqual(hc.contain_value(value, linkify=False, sanitize=sanitize), value)

    def test_json_without_markup_is_untouched(self):
        def sanitize(value, **kwargs):
            raise AssertionError("must not be called")

        self.assertEqual(hc.contain_value('"plain quoted text"', linkify=False, sanitize=sanitize),
                         '"plain quoted text"')


class FakeField(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, key, default=None):
        return dict.get(self, key, default)


class FakeDoc:
    """Minimal stand-in for a Frappe Document: fields, values, and child rows."""

    def __init__(self, fields, values, children=()):
        self.meta = Obj(fields=[FakeField(f) for f in fields])
        self._values = dict(values)
        self._children = list(children)

    def get(self, name, default=None):
        return self._values.get(name, default)

    def set(self, name, value):
        self._values[name] = value

    def get_all_children(self):
        return list(self._children)


class ContainDocumentTests(unittest.TestCase):
    def _build(self):
        child = FakeDoc(
            fields=[{"fieldname": "body", "fieldtype": "Text Editor"}],
            values={"body": PAYLOAD},
        )
        parent = FakeDoc(
            fields=[
                {"fieldname": "notes", "fieldtype": "Text Editor"},
                {"fieldname": "title", "fieldtype": "Data"},
                {"fieldname": "code", "fieldtype": "Code"},
                {"fieldname": "trusted", "fieldtype": "Text Editor", "ignore_xss_filter": 1},
            ],
            values={"notes": PAYLOAD, "title": "<b>not html-typed</b>", "code": PAYLOAD,
                    "trusted": PAYLOAD},
            children=[child],
        )
        return parent, child

    def test_containment_covers_parent_and_child_html_fields_only(self):
        parent, child = self._build()
        sanitize = lambda v, **kw: model_sanitize(v, always_sanitize=True)  # noqa: E731
        changed = hc.contain_document(parent, sanitize=sanitize, is_json_fn=hc.is_json_shape)
        self.assertEqual(changed, ["notes", "body"])  # parent field, then the child row in the same pass
        self.assertNotIn("onerror", parent.get("notes"))
        self.assertEqual(parent.get("title"), "<b>not html-typed</b>")  # Data is not an HTML field
        self.assertEqual(parent.get("code"), PAYLOAD)  # Code is never sanitized by Frappe either
        self.assertEqual(parent.get("trusted"), PAYLOAD)  # ignore_xss_filter is an explicit owner setting

    def test_child_rows_are_contained_too(self):
        parent, child = self._build()
        sanitize = lambda v, **kw: model_sanitize(v, always_sanitize=True)  # noqa: E731
        hc.contain_document(parent, sanitize=sanitize, is_json_fn=hc.is_json_shape)
        self.assertNotIn("onerror", child.get("body"))  # the child row is covered by the parent event

    def test_containment_is_idempotent(self):
        parent, _ = self._build()
        sanitize = lambda v, **kw: model_sanitize(v, always_sanitize=True)  # noqa: E731
        hc.contain_document(parent, sanitize=sanitize, is_json_fn=hc.is_json_shape)
        first = parent.get("notes")
        self.assertEqual(hc.contain_document(parent, sanitize=sanitize, is_json_fn=hc.is_json_shape), [])
        self.assertEqual(parent.get("notes"), first)


class WiringTests(unittest.TestCase):
    def test_hook_is_registered_for_every_doctype(self):
        hooks = (ROOT / "apps/foundation_security/foundation_security/hooks.py").read_text()
        self.assertIn('doc_events = {"*": {"validate": '
                      '"foundation_security.html_containment.contain_html_fields"}}', hooks)

    def test_event_handler_resolves_frappe_sanitizer_at_call_time(self):
        source = MODULE.read_text()
        self.assertIn("from frappe.utils.html_utils import is_json, sanitize_html", source)
        self.assertIn("always_sanitize=True", source)


if __name__ == "__main__":
    unittest.main()
