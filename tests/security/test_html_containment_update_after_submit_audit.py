"""Static audit (NEW-13): no HTML-capable field is editable post-submit.

Proof recorded 2026-11-05 on main@4b14adf8 + batch-2 base 5032608d and
re-verified independently 2026-11-06 on both 5032608d and 64aee8c1 with
a separate walk over every ``*.json`` under ``apps/`` (not just the
doctype JSONs + 2 fixture files): 64 HTML-capable fields, same single
``allow_on_submit=1`` Link field, same single submittable HTML field.
``contain_html_fields`` (foundation_security) runs only on the ``validate``
doc event. Pinned Frappe (988e54f3c4c2, ``frappe/model/document.py``
``run_before_save_methods``) fires ``validate`` only for save/submit;
post-submit edits run ``before_update_after_submit`` WITHOUT ``validate``,
and Frappe's own ``_sanitize_content`` sanitizes a submitted document
only for ``allow_on_submit`` fields. A bypass therefore needs an
HTML-capable field with ``allow_on_submit=1``. This test pins that none
exists in the schema this repository owns:

- Every DocType JSON under ``apps/`` plus the ``Custom Field`` and
  ``Property Setter`` fixtures were walked (64 HTML-capable fields found:
  ``Text Editor`` / ``Text`` / ``Small Text`` / ``Markdown Editor``).
  None has ``allow_on_submit`` set. The full list is asserted indirectly
  by the exact ``allow_on_submit=1`` set below plus the submittable
  check; the count guard keeps the walk honest.
- The ONLY ``allow_on_submit=1`` field in the whole repo-owned schema is
  ``Payment Entry.th_collection_handover``, fieldtype ``Link`` — not
  HTML-capable, so it cannot carry a stored-HTML payload.
- The only submittable doctype defined in this repo is ``TH Cashier Day``;
  its only HTML-capable field (``notes``, Small Text) has
  ``allow_on_submit`` unset, so ``update_after_submit`` cannot edit it.
- No app code calls ``update_after_submit(``; the only
  ``frappe.db.set_value`` writes the ``customer`` Link field on Student
  (``admission/__init__.py``); no ``UPDATE``/``INSERT``/``DELETE`` is
  issued through ``frappe.db.sql`` (all calls are ``SELECT ... FOR
  UPDATE`` row locks or ``SET SESSION``); no app code calls ``db_set``;
  the only ``frappe.db.delete`` removes ``DocShare`` rows (placement
  records deny it outright in ``controllers.py``). The two ``db.sql``
  calls whose first argument is a named constant are both ``SELECT``
  constants (``permissions.py``).
- No ``ignore_xss_filter`` field is set anywhere in the repo-owned
  schema, so containment's skip rule never hides a field.

Scope boundary: native Frappe/ERPNext/Education doctypes are vendor
schema, not defined in this repository, so their ``allow_on_submit``
fields cannot be audited from this checkout. Containment on ``validate``
still covers their normal save path. The ``frappe.db.set_value`` /
``db_set`` / raw-SQL paths skip ALL document events by framework design
and are already recorded as residual exposure 2 in
``docs/engineering/evidence/sec-deps-01/containment-real-sanitizer-2026-10-16/README.md``;
pinning containment on ``before_update_after_submit`` would not cover
them either. No speculative hook was added: there is no post-submit
HTML edit path in the owned schema to pin it to. Closing the vendor
remainder needs the pinned vendor sources themselves (Frappe 988e54f3,
Education 93bc7075): check out those commits, walk their doctype JSONs
for ``allow_on_submit`` on HTML-capable fields, and run the hosted
save-path check -- none of that is possible from this checkout.

Pure static test; imports nothing from the app.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"

HTML_FIELDTYPES = frozenset(
    ("Text Editor", "Text", "Small Text", "Markdown Editor"))

# The complete allow_on_submit=1 set in the repo-owned schema. Any
# addition must be reviewed here deliberately: an HTML-capable entry
# would be a NEW-13 bypass.
EXPECTED_ALLOW_ON_SUBMIT = {
    ("Payment Entry", "th_collection_handover", "Link"),
}

# The exact HTML-capable field count in the repo-owned schema, pinned:
# a schema change must update this number deliberately, with the
# allow_on_submit set above re-reviewed at the same time.
EXPECTED_HTML_FIELD_COUNT = 64

# db.sql calls whose first argument is a named constant, not a string
# literal. Both are SELECT constants; any addition must be reviewed
# here deliberately.
EXPECTED_NON_LITERAL_SQL = {
    ("toefl_house/toefl_house/permissions.py", "INSTRUCTOR_GROUPS_SQL"),
    ("toefl_house/toefl_house/permissions.py", "_ROSTER_BRANCH_SQL"),
}

# The only doctypes frappe.db.delete ever removes rows from. DocShare
# rows carry no HTML fields.
EXPECTED_DB_DELETE_TARGETS = {"DocShare"}


def _iter_doctype_jsons():
    for path in sorted(APPS.rglob("doctype/*/*.json")):
        yield path


def _iter_fixture_jsons():
    fixtures = APPS / "toefl_house" / "toefl_house" / "fixtures"
    for name in ("custom_field.json", "property_setter.json"):
        path = fixtures / name
        if path.exists():
            yield path


class UpdateAfterSubmitHtmlAuditTests(unittest.TestCase):
    def _collect(self):
        allow_on_submit = set()
        html_fields = []
        submittable_html = []
        property_setter_allow = []
        ignore_xss = []
        for path in list(_iter_doctype_jsons()) + list(_iter_fixture_jsons()):
            data = json.loads(path.read_text(encoding="utf-8"))
            docs = data if isinstance(data, list) else [data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("doctype")
                if kind == "DocType":
                    name = doc.get("name")
                    submittable = bool(doc.get("is_submittable"))
                    for field in doc.get("fields") or []:
                        fieldname = field.get("fieldname")
                        fieldtype = field.get("fieldtype")
                        if field.get("allow_on_submit"):
                            allow_on_submit.add(
                                (name, fieldname, fieldtype))
                        if fieldtype in HTML_FIELDTYPES:
                            html_fields.append((name, fieldname, fieldtype))
                            if submittable:
                                submittable_html.append(
                                    (name, fieldname, fieldtype,
                                     field.get("allow_on_submit")))
                        if field.get("ignore_xss_filter"):
                            ignore_xss.append((name, fieldname))
                elif kind == "Custom Field":
                    dt = doc.get("dt")
                    fieldname = doc.get("fieldname")
                    fieldtype = doc.get("fieldtype")
                    if doc.get("allow_on_submit"):
                        allow_on_submit.add((dt, fieldname, fieldtype))
                    if fieldtype in HTML_FIELDTYPES:
                        html_fields.append((dt, fieldname, fieldtype))
                    if doc.get("ignore_xss_filter"):
                        ignore_xss.append((dt, fieldname))
                elif kind == "Property Setter":
                    if doc.get("property") == "allow_on_submit":
                        property_setter_allow.append(
                            (doc.get("doc_type"), doc.get("field_name"),
                             doc.get("value")))
        return allow_on_submit, html_fields, submittable_html, \
            property_setter_allow, ignore_xss

    def test_no_html_capable_field_is_editable_after_submit(self):
        (allow_on_submit, html_fields, submittable_html,
         property_setter_allow, ignore_xss) = self._collect()
        # The walk must actually see the schema; a silent empty walk
        # would pass vacuously. The count is pinned exactly: a schema
        # change must update it deliberately, with the
        # allow_on_submit set re-reviewed at the same time.
        self.assertEqual(
            len(html_fields), EXPECTED_HTML_FIELD_COUNT,
            "HTML-capable field count changed; review deliberately -- "
            "the audit walk may be broken, or the schema gained/lost "
            "an HTML-capable field")
        self.assertEqual(
            allow_on_submit, EXPECTED_ALLOW_ON_SUBMIT,
            "allow_on_submit=1 set changed; review deliberately — an "
            "HTML-capable entry here is a stored-HTML bypass of "
            "validate-only containment (NEW-13)")
        html_allow = [entry for entry in allow_on_submit
                      if entry[2] in HTML_FIELDTYPES]
        self.assertEqual(html_allow, [],
                         "an HTML-capable field is editable after submit")
        self.assertEqual(property_setter_allow, [],
                         "a Property Setter enables allow_on_submit")
        self.assertEqual(ignore_xss, [],
                         "an ignore_xss_filter field hides from containment")

    def test_submittable_doctype_html_field_is_not_allow_on_submit(self):
        (_, _, submittable_html, _, _) = self._collect()
        # Only TH Cashier Day is submittable in the repo-owned schema.
        self.assertEqual(
            [(name, field, ftype) for name, field, ftype, _ in submittable_html],
            [("TH Cashier Day", "notes", "Small Text")])
        for name, field, ftype, allow in submittable_html:
            self.assertFalse(allow, (name, field, ftype))

    def test_no_app_code_path_writes_html_fields_skipping_validate(self):
        sources = [p for p in sorted(APPS.rglob("*.py"))
                   if "__pycache__" not in p.parts]
        self.assertTrue(sources, "no app Python sources found")
        update_after_submit_calls = []
        db_set_calls = []
        set_value_targets = []
        write_sql = []
        non_literal_sql = []
        db_delete_targets = []
        for path in sources:
            text = path.read_text(encoding="utf-8")
            if ".update_after_submit(" in text:
                update_after_submit_calls.append(str(path))
            if re.search(r"\.db_set\s*\(", text):
                db_set_calls.append(str(path))
            for match in re.finditer(
                    r"frappe\.db\.set_value\(\s*\"([^\"]+)\"\s*,\s*[^,]+,\s*\"([^\"]+)\"",
                    text):
                set_value_targets.append((match.group(1), match.group(2)))
            # A write statement can hide behind an f-string or a
            # triple-quoted literal with a leading newline, not just a
            # plain quoted literal at the call start.
            for match in re.finditer(
                    r"frappe\.db\.sql\(\s*f?(?:\"\"\"|\"|')\s*"
                    r"(update|insert|delete|replace|truncate|alter|drop|create)\b",
                    text, re.IGNORECASE):
                write_sql.append((str(path), match.group(1)))
            # A query passed as a named constant is not visible to the
            # literal scan above: the only permitted ones are the two
            # known SELECT constants. (The negative lookahead excludes
            # f-string literals, which the write-SQL scan above covers.)
            for match in re.finditer(
                    r"(?:frappe\.db\.sql|db\.sql)\s*\(\s*(?!f?[\"'])"
                    r"([A-Za-z_][A-Za-z0-9_]*)",
                    text):
                rel = str(path.relative_to(APPS))
                non_literal_sql.append((rel, match.group(1)))
            for match in re.finditer(
                    r"frappe\.db\.delete\(\s*\"([^\"]+)\"", text):
                db_delete_targets.append(match.group(1))
        self.assertEqual(update_after_submit_calls, [],
                         "app code calls update_after_submit directly")
        self.assertEqual(db_set_calls, [],
                         "app code calls db_set (skips validate)")
        # The single set_value writes a Link field, not an HTML field.
        self.assertEqual(set_value_targets, [("Student", "customer")])
        self.assertEqual(write_sql, [],
                         "app code issues write SQL (skips validate)")
        self.assertEqual(set(non_literal_sql), EXPECTED_NON_LITERAL_SQL,
                         "a db.sql call passes a non-literal query; review "
                         "deliberately -- it is invisible to the write-SQL scan")
        self.assertEqual(set(db_delete_targets), EXPECTED_DB_DELETE_TARGETS,
                         "frappe.db.delete removes rows from an unexpected "
                         "doctype; review deliberately")


if __name__ == "__main__":
    unittest.main()
