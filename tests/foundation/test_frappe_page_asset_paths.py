"""Guard Frappe Page runtime asset paths against dash-versus-underscore drift.

The real Frappe Page.load_assets() calls scrub(self.name) to construct both
page/<scrub(name)>/ and scrub(name).js; it also lists that directory. A
hyphenated source directory therefore raises FileNotFoundError during getpage,
even when desk endpoint tests and the installed Page record both pass.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "toefl_house" / "toefl_house"
DESKS = (
    "th-reception-desk", "th-academic-desk", "th-finance-desk",
    "th-operations-desk", "th-owner-cockpit", "th-academic-setup",
    "th-teacher-desk", "th-configuration",
)


class FrappePageAssetPathTests(unittest.TestCase):
    def test_all_standard_pages_use_scrubbed_asset_directories_and_json_names(self):
        pages = sorted(APP.glob("*/page/*/*.json"))
        self.assertGreaterEqual(len(pages), 22, "Missing standard Page fixtures")
        found = set()
        for file in pages:
            with self.subTest(path=file.relative_to(ROOT)):
                payload = json.loads(file.read_text(encoding="utf-8"))
                self.assertEqual(payload["doctype"], "Page")
                self.assertEqual(payload["standard"], "Yes")
                name = payload["name"]
                expected = name.lower().replace("-", "_").replace(" ", "_")
                # Frappe core Page.load_assets derives *both* from scrub(name).
                self.assertEqual(file.parent.name, expected)
                self.assertEqual(file.name, expected + ".json")
                self.assertEqual(payload["page_name"], name)
                self.assertEqual(file.parent.parent.name, "page")
                self.assertEqual(file.parent.parent.parent.name.lower(), payload["module"].lower().replace(" ", "_"))
                self.assertNotIn(name, found, "Duplicate Page source name")
                found.add(name)
        self.assertTrue(set(DESKS).issubset(found))

    def test_role_desks_remain_hyphenated_routes_with_scrubbed_source_paths(self):
        hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        client = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")
        registry = (APP / "desk/__init__.py").read_text(encoding="utf-8")
        self.assertIn('page_js.update({name: "public/js/th_role_desks.js" for name in _DESK_PAGES})', hooks)
        for slug in DESKS:
            with self.subTest(page=slug):
                source = APP / "operations" / "page" / slug.replace("-", "_") / (slug.replace("-", "_") + ".json")
                self.assertTrue(source.is_file(), "Page.getpage would fail before hooks could load")
                data = json.loads(source.read_text(encoding="utf-8"))
                self.assertEqual(data["name"], slug)
                self.assertIn('"' + slug + '"', hooks)
                self.assertIn('"' + slug + '"', registry)
                self.assertIn('"' + slug + '"', client)
                self.assertEqual(data["roles"][0]["role"],
                                 {"th-reception-desk": "Reception", "th-academic-desk": "Academic Manager",
                                  "th-finance-desk": "Finance Manager", "th-operations-desk": "General Manager",
                                  "th-owner-cockpit": "Course Owner", "th-academic-setup": "Course Owner",
                                  "th-teacher-desk": "Instructor", "th-configuration": "Course Owner"}[slug])


if __name__ == "__main__":
    unittest.main()
