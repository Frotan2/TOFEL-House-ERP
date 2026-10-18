"""Read-only stored-HTML audit (GHSA-VHRC residual 1). Synthetic rows only."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools/foundation") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools/foundation"))

import audit_stored_html as audit  # noqa: E402

SCRIPT = (ROOT / "tools/foundation/audit_stored_html.py").read_text(encoding="utf-8")


def fake_sanitize(value, *, linkify, always_sanitize=False):
    # Synthetic stand-in: any change is visible. The real sanitizer is covered elsewhere.
    return "SANITIZED"


def _json_shape(value):
    try:
        json.loads(value)
    except ValueError:
        return False
    return True


class ClassifierTests(unittest.TestCase):
    def classify(self, rows, linkify=True):
        return audit.classify_rows(rows, sanitize=fake_sanitize, is_json_fn=_json_shape, linkify=linkify)

    def test_plain_markup_outside_json_is_not_changed_by_containment(self):
        result = self.classify([("ROW-1", "<p>plain <strong>text</strong></p>")])
        self.assertEqual(result["counts"], {"scanned": 1})
        self.assertEqual(result["record_names"]["would_change"], [])

    def test_json_wrapped_handler_takes_the_short_circuit_and_would_change(self):
        payload = '"<img src=x onerror=alert(1)>"'
        result = self.classify([("ROW-2", payload)])
        self.assertEqual(result["counts"]["json_shaped"], 1)
        self.assertEqual(result["counts"]["would_change"], 1)
        self.assertEqual(result["counts"]["scheme_or_handler"], 1)
        self.assertEqual(result["record_names"]["would_change"], ["ROW-2"])

    def test_javascript_scheme_outside_json_is_counted_but_left_to_frappe(self):
        payload = '<p><a href="javascript:alert(1)">x</a></p>'
        result = self.classify([("ROW-3", payload)])
        self.assertEqual(result["counts"]["scheme_or_handler"], 1)
        self.assertNotIn("would_change", result["counts"])

    def test_empty_none_and_non_string_values_are_scanned_but_never_flagged(self):
        result = self.classify([("A", None), ("B", ""), ("C", 7), ("D", "no markup")])
        self.assertEqual(result["counts"], {"scanned": 4})

    def test_names_are_sorted_and_deduplicated(self):
        payload = '"<b onclick=x()>"'
        result = self.classify([("Z", payload), ("A", payload), ("Z", payload)])
        self.assertEqual(result["record_names"]["would_change"], ["A", "Z"])

    def test_output_contains_record_names_and_counts_but_never_stored_content(self):
        secret = "PRIVATE-SENTINEL-7d1f"
        payload = '"<img src=x onerror=alert(1)>' + secret + '"'
        result = self.classify([("ROW-4", payload)])
        rendered = json.dumps(result)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("onerror", rendered)


REAL_CONTAINMENT_TEST = ROOT / "tests/security/test_html_containment_real_sanitizer_2026_10_16.py"


def _real_sanitizer():
    """Pinned, hash-checked Frappe sanitize_html (same loader as the 2026-10-16 real-sanitizer suite).

    Loaded by path; any missing dependency or changed fixture raises, it never skips.
    """
    spec = importlib.util.spec_from_file_location("real_sanitizer_loader", REAL_CONTAINMENT_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._load_real_sanitizer().sanitize_html


class RealSanitizerTests(unittest.TestCase):
    def test_json_wrapped_handler_is_active_raw_and_inert_after_real_containment(self):
        raw = '"<img src=x onerror=alert(1)>"'
        # Rule from the 2026-10-16 suite: the RAW stored form must already be dangerous.
        self.assertTrue(_json_shape(raw))
        self.assertRegex(raw, r"\bonerror\s*=")
        sanitize = _real_sanitizer()
        result = self.classify_with(sanitize, [("ROW-R1", raw)])
        self.assertEqual(result["counts"]["would_change"], 1)
        contained = audit.contain_value(raw, linkify=False, sanitize=sanitize, is_json_fn=_json_shape)
        self.assertNotIn("onerror", contained.lower())
        self.assertNotIn("alert(1)", contained)

    def test_legitimate_formatting_outside_json_is_untouched_by_real_containment(self):
        text = "<p>Lesson <strong>one</strong></p>"
        result = self.classify_with(_real_sanitizer(), [("ROW-R2", text)])
        self.assertEqual(result["record_names"]["would_change"], [])

    def classify_with(self, sanitize, rows):
        return audit.classify_rows(rows, sanitize=sanitize, is_json_fn=_json_shape, linkify=False)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeDb:
    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def sql(self, query, *args):
        self.queries.append(query)
        table = query.split("from `", 1)[1].split("`", 1)[0]
        assert table.startswith("tab"), table  # real bench tables are tab<Doctype>
        table = table[3:]
        field = query.split("select name, `", 1)[1].split("`", 1)[0]
        if table not in self.tables:
            raise RuntimeError("no such table")
        return [(name, value) for name, value in self.tables[table].get(field, [])]


class FakeFrappe:
    def __init__(self, doc_fields, custom_fields, tables):
        self._doc_fields = doc_fields
        self._custom_fields = custom_fields
        self.db = FakeDb(tables)

    def get_all(self, doctype, filters=None, fields=None):
        if doctype == "DocField":
            return [_Row(parent=p, fieldname=f, fieldtype=t, ignore_xss_filter=x)
                    for p, f, t, x in self._doc_fields]
        if doctype == "Custom Field":
            return [_Row(dt=p, fieldname=f, fieldtype=t, ignore_xss_filter=x)
                    for p, f, t, x in self._custom_fields]
        raise AssertionError(doctype)


class SiteWalkTests(unittest.TestCase):
    def run_walk(self, frappe_obj):
        return audit.audit_site(frappe_obj, fake_sanitize, _json_shape)

    def test_custom_fields_are_scanned_and_flagged_fields_are_not_skipped(self):
        fake = FakeFrappe(
            doc_fields=[("Course Lesson", "content", "Text Editor", 0)],
            custom_fields=[("Course Lesson", "notes_html", "Text", 1)],
            tables={
                "Course Lesson": {
                    "content": [("L-1", "<p>ok</p>")],
                    "notes_html": [("L-2", '"<img src=x onerror=alert(1)>"')],
                }
            },
        )
        report = self.run_walk(fake)
        by_field = {item["fieldname"]: item for item in report["fields"]}
        self.assertEqual(set(by_field), {"content", "notes_html"})
        self.assertTrue(by_field["notes_html"]["ignore_xss_filter"])
        self.assertFalse(by_field["content"]["ignore_xss_filter"])
        self.assertEqual(by_field["notes_html"]["record_names"]["would_change"], ["L-2"])

    def test_no_literal_like_prefilter_so_json_escaped_markup_is_still_classified(self):
        escaped = '"\\u003cimg src=x onerror=alert(1)\\u003e"'
        fake = FakeFrappe(
            doc_fields=[("Course Lesson", "content", "Text Editor", 0)],
            custom_fields=[],
            tables={"Course Lesson": {"content": [("L-3", escaped)]}},
        )
        report = self.run_walk(fake)
        self.assertNotIn("like", fake.db.queries[0].lower())
        self.assertEqual(report["fields"][0]["counts"]["scanned"], 1)

    def test_unsafe_identifiers_are_skipped_and_reported_not_queried(self):
        fake = FakeFrappe(
            doc_fields=[("Bad;Doc", "content", "Text", 0), ("Course", "x`y", "Text", 0)],
            custom_fields=[],
            tables={},
        )
        report = self.run_walk(fake)
        self.assertEqual(fake.db.queries, [])
        self.assertEqual(report["fields"], [])
        self.assertEqual(len(report["skipped"]), 2)

    def test_duplicate_field_rows_are_scanned_once(self):
        fake = FakeFrappe(
            doc_fields=[("Course Lesson", "content", "Text", 0)],
            custom_fields=[("Course Lesson", "content", "Text", 0)],
            tables={"Course Lesson": {"content": [("L-4", "plain")]}},
        )
        report = self.run_walk(fake)
        self.assertEqual(len(report["fields"]), 1)
        self.assertEqual(len(fake.db.queries), 1)


class IdentifierTests(unittest.TestCase):
    def test_fieldname_and_doctype_patterns_reject_injection_shapes(self):
        for bad in ("name; drop table x", "a`b", "", "x" * 141, "Field-Name"):
            self.assertIsNone(audit.FIELDNAME.fullmatch(bad), bad)
        for bad in ("Doc;type", "Doc`type", "", "x" * 141):
            self.assertIsNone(audit.DOCTYPE.fullmatch(bad), bad)
        self.assertIsNotNone(audit.FIELDNAME.fullmatch("description_html"))
        self.assertIsNotNone(audit.DOCTYPE.fullmatch("Course Lesson"))


class ReadOnlyTests(unittest.TestCase):
    def test_audit_module_contains_no_write_statements(self):
        code = re.sub(r'"""(?:.|\n)*?"""', "", SCRIPT)
        for pattern in (r"db\.commit\(", r"db_set\(", r"set_value\(", r"\.save\(", r"\.delete\(",
                        r"\bdelete from\b", r"\bupdate\s+`?tab", r"\binsert into\b", r"\.set\("):
            self.assertIsNone(re.search(pattern, code, re.IGNORECASE), pattern)

    def test_only_select_is_issued_against_tables(self):
        self.assertIn("select name,", SCRIPT)
        self.assertEqual(len(re.findall(r"frappe\.db\.sql\(", SCRIPT)), 1)


if __name__ == "__main__":
    unittest.main()
