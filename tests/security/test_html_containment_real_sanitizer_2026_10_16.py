"""Containment with Frappe's REAL sanitizer (GHSA-vhrc-hgrq-x75r, 2026-10-16).

The 2026-10-15 containment tests use a model sanitizer. These tests load the unmodified
pinned Frappe `sanitize_html` (frappe/utils/html_utils.py at 988e54f3, vendored under
tests/security/fixtures and SHA-256 checked) and run it with its real nh3, bleach_allowlist
and bs4 dependencies. Only the `frappe` package itself is stubbed, and only for helpers
(`escape_html`, `as_unicode`, `is_image`) that the sanitize path never calls.

Payload rule: an exploit payload must be a stored value that is valid JSON, that the
`is_json` short-circuit lets through, and whose RAW form already contains an active element
(an event-handler attribute or a javascript: scheme). Each payload is checked for that first,
so a passing test cannot come from a payload that was never dangerous.

This is a unit-level runtime check of the sanitizer. It is NOT the hosted save path, so it
does not by itself reinstate GHSA-vhrc (the hosted runtime check is still required).

Missing nh3 or bs4 must fail this module, not skip it (the owned suite installs them hash-pinned).
"""
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import sys
import types
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/security/fixtures/frappe-988e54f3/html_utils.py"
CONTAINMENT = ROOT / "apps/foundation_security/foundation_security/html_containment.py"
PINNED_SHA256 = "9997c4d8f2782ca3a5ad08ecf047a4bce798ba67cea1092a861826702545fd15"
DANGEROUS_SCHEMES = {"javascript", "vbscript", "data"}


def _load_real_sanitizer():
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    if digest != PINNED_SHA256:
        raise AssertionError(f"vendored sanitizer changed: {digest}")
    frappe = types.ModuleType("frappe")
    frappe.as_unicode = str
    utils = types.ModuleType("frappe.utils")
    data = types.ModuleType("frappe.utils.data")
    data.escape_html = html.escape
    utils.data = data
    utils.is_image = lambda *_args, **_kwargs: False
    frappe.utils = utils
    sys.modules.setdefault("frappe", frappe)
    sys.modules.setdefault("frappe.utils", utils)
    sys.modules.setdefault("frappe.utils.data", data)
    spec = importlib.util.spec_from_file_location("frappe_real_html_utils", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_containment():
    spec = importlib.util.spec_from_file_location("html_containment_under_test", CONTAINMENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REAL = _load_real_sanitizer()
CONTAIN = _load_containment()


def effective_scheme(url: str):
    """Scheme a browser would use for an href/src (WHATWG URL parsing, simplified)."""
    value = html.unescape(url)
    value = value.strip("".join(chr(c) for c in range(0x21)))
    value = re.sub(r"[\t\n\r]", "", value)
    match = re.match(r"([A-Za-z][A-Za-z0-9+.\-]*):", value)
    return match.group(1).lower() if match else None


def active_elements(markup: str):
    """Return (event-handler attributes, dangerous-scheme URLs) present in parsed markup."""
    soup = BeautifulSoup(markup, "html.parser")
    handlers, urls = [], []
    for tag in soup.find_all(True):
        for name, value in tag.attrs.items():
            if name.lower().startswith("on"):
                handlers.append((tag.name, name))
            if name.lower() in ("href", "src", "xlink:href", "formaction"):
                scheme = effective_scheme(value if isinstance(value, str) else " ".join(value))
                if scheme in DANGEROUS_SCHEMES:
                    urls.append((tag.name, name, scheme))
    return handlers, urls


# Raw stored values. Each is valid JSON with no inner quotes, so the is_json short-circuit
# returns it unchanged in Frappe's own pass.
HANDLER_PAYLOAD = '"<img src=x onerror=alert(1)>"'
JS_HREF_PAYLOAD = '"<a href=javascript:alert(1)>x</a>"'
SCRIPT_ARRAY_PAYLOAD = '["<script>alert(1)</script><p>hi</p>"]'


class Field:
    def __init__(self, fieldname, fieldtype, **extra):
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self._extra = extra

    def get(self, key, default=None):
        return self._extra.get(key, default)


class Meta:
    def __init__(self, fields):
        self.fields = fields


class Holder:
    def __init__(self, meta, values, children=()):
        self.meta = meta
        self.values = dict(values)
        self._children = list(children)

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def get_all_children(self):
        return list(self._children)


def contain(value):
    return CONTAIN.contain_value(value, linkify=True, sanitize=REAL.sanitize_html,
                                 is_json_fn=REAL.is_json)


class PayloadsAreRealTests(unittest.TestCase):
    """The payloads must be genuinely dangerous before any containment result counts."""

    def test_handler_payload_is_json_and_active_in_raw_form(self):
        self.assertTrue(REAL.is_json(HANDLER_PAYLOAD))
        handlers, _ = active_elements(json.loads(HANDLER_PAYLOAD))
        self.assertIn(("img", "onerror"), handlers)

    def test_js_href_payload_is_json_and_active_in_raw_form(self):
        self.assertTrue(REAL.is_json(JS_HREF_PAYLOAD))
        _, urls = active_elements(json.loads(JS_HREF_PAYLOAD))
        self.assertIn(("a", "href", "javascript"), urls)

    def test_script_array_payload_is_json_and_contains_script(self):
        self.assertTrue(REAL.is_json(SCRIPT_ARRAY_PAYLOAD))
        self.assertIn("<script", json.loads(SCRIPT_ARRAY_PAYLOAD)[0])


class RealSanitizerBypassTests(unittest.TestCase):
    def test_frappe_short_circuit_returns_handler_payload_unchanged(self):
        # The defect: Frappe's pass does not touch this value on save.
        self.assertEqual(REAL.sanitize_html(HANDLER_PAYLOAD), HANDLER_PAYLOAD)

    def test_containment_removes_event_handler(self):
        out = contain(HANDLER_PAYLOAD)
        self.assertNotEqual(out, HANDLER_PAYLOAD)
        self.assertEqual(active_elements(out)[0], [])

    def test_containment_removes_javascript_scheme(self):
        out = contain(JS_HREF_PAYLOAD)
        self.assertEqual(active_elements(out)[1], [])

    def test_containment_removes_script_from_json_array(self):
        out = contain(SCRIPT_ARRAY_PAYLOAD)
        self.assertNotIn("<script", out.lower())
        self.assertIn("<p>hi</p>", out)


class FrappePassStillSanitizesNonJsonTests(unittest.TestCase):
    def test_frappe_own_pass_sanitizes_plain_hostile_html(self):
        out = REAL.sanitize_html('<img src=x onerror="alert(1)"><p>ok</p>')
        self.assertEqual(active_elements(out)[0], [])
        self.assertIn("<p>ok</p>", out)

    def test_plain_javascript_href_is_stripped_by_frappe(self):
        out = REAL.sanitize_html('<a href="javascript:alert(1)">x</a>')
        self.assertEqual(active_elements(out)[1], [])

    def test_containment_leaves_non_json_values_to_frappe(self):
        plain = '<img src=x onerror=alert(1)>'
        self.assertFalse(REAL.is_json(plain))
        self.assertEqual(contain(plain), plain)


class LegitimateFormattingPreservedTests(unittest.TestCase):
    LEGIT = ('<p><strong>Bold</strong> <em>it</em> <u>under</u></p>'
             '<ul><li>one</li><li>two</li></ul>'
             '<a href="https://example.com/course" rel="noopener">course</a>')

    def _assert_formatting(self, markup):
        soup = BeautifulSoup(markup, "html.parser")
        self.assertIsNotNone(soup.find("strong"))
        self.assertEqual(soup.find("strong").get_text(), "Bold")
        self.assertIsNotNone(soup.find("em"))
        self.assertIsNotNone(soup.find("u"))
        self.assertEqual([li.get_text() for li in soup.find_all("li")], ["one", "two"])
        self.assertEqual(soup.find("a")["href"], "https://example.com/course")

    def test_plain_legitimate_html_is_unchanged_by_containment(self):
        self.assertEqual(contain(self.LEGIT), self.LEGIT)

    def test_json_wrapped_legitimate_formatting_survives_containment(self):
        # Only a value that is itself quoted HTML is affected. nh3 keeps the wrapping quote
        # characters as text, so the output is sanitized HTML and no longer valid JSON. That
        # is a deliberate, cosmetic change for a case Frappe already passed through raw.
        # Unquoted attribute so the JSON string needs no inner-quote escaping. A quoted href
        # inside json.dumps would carry literal backslashes in the RAW value too (not a containment effect).
        stored = json.dumps(self.LEGIT.replace('href="https://example.com/course" rel="noopener"', 'href=https://example.com/course rel=noopener'))
        out = contain(stored)
        self._assert_formatting(out)
        self.assertEqual(active_elements(out), ([], []))

    def test_ordinary_text_without_markup_is_unchanged(self):
        self.assertEqual(contain("plain text 1 & 2"), "plain text 1 & 2")

    def test_containment_is_idempotent(self):
        once = contain(HANDLER_PAYLOAD)
        self.assertEqual(contain(once), once)


class DocumentLevelTests(unittest.TestCase):
    def test_text_editor_child_row_is_contained_and_untouched_fields_are_not(self):
        child = Holder(Meta([Field("content", "Text Editor")]), {"content": HANDLER_PAYLOAD})
        doc = Holder(
            Meta([
                Field("body", "Text Editor"),
                Field("title", "Data"),  # not HTML-capable: never altered
                Field("raw_note", "Text", ignore_xss_filter=1),  # explicit opt-out
            ]),
            {"body": JS_HREF_PAYLOAD, "title": HANDLER_PAYLOAD, "raw_note": HANDLER_PAYLOAD},
            children=[child],
        )

        changed = CONTAIN.contain_document(doc, sanitize=REAL.sanitize_html, is_json_fn=REAL.is_json)

        self.assertIn("body", changed)
        self.assertIn("content", changed)
        self.assertEqual(active_elements(doc.get("body"))[1], [])
        self.assertEqual(active_elements(child.get("content"))[0], [])
        self.assertEqual(doc.get("title"), HANDLER_PAYLOAD)
        self.assertEqual(doc.get("raw_note"), HANDLER_PAYLOAD)


class RequirementsPinTests(unittest.TestCase):
    """The packages this module imports must stay hash-pinned in the owned-suite venv."""

    def test_sanitizer_dependencies_are_pinned_with_hashes(self):
        pins = (ROOT / "tests/security/requirements-ci.txt").read_text(encoding="utf-8")
        lines = {line.split("==")[0].lower(): line for line in pins.splitlines()
                 if "==" in line and not line.startswith("#")}
        expected = {
            "nh3": "0.3.7",
            "bleach-allowlist": "1.0.3",
            "beautifulsoup4": "4.13.5",
            "soupsieve": "2.10",
            "typing-extensions": "4.16.0",
        }
        for name, version in expected.items():
            self.assertIn(name, lines, name)
            self.assertTrue(lines[name].startswith(f"{name}=={version} "), lines[name][:80])
            self.assertIn("--hash=sha256:", lines[name])
        # Resolved, reviewed wheel for the sandbox platform (cp311 linux), and the pure wheels.
        self.assertIn("--hash=sha256:70f5ac8626e899a4bab0ef74ca2f5bd602f49c7b739e6e5026b4afc6d63dac42", lines["nh3"])
        self.assertIn("--hash=sha256:6427a3ac0baddf549703f1003ea53f411f3d7888524c94c00eb6ef1deb378899", lines["bleach-allowlist"])
        self.assertIn("--hash=sha256:642085eaa22233aceadff9c69651bc51e8bf3f874fb6d7104ece2beb24b47c4a", lines["beautifulsoup4"])
        self.assertIn("--hash=sha256:8596eb8967d744174820280fa62b4542a2e955bfaccca73ed8a13c6eb8e9b502", lines["soupsieve"])
        self.assertIn("--hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8", lines["typing-extensions"])


if __name__ == "__main__":
    unittest.main()
