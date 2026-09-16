"""Static validation of the R1 release surface (role-scoped workspaces).
Pure JSON/AST; imports nothing from the app.

The workspaces ship as native module files
(<module>/workspace/<slug>/<slug>.json, the upstream-canonical route used by
ERPNext itself) and import via module sync. This suite guards the invariant
that they are pure native navigation configuration: every role row exists in
the role fixture, every link target is a known native or TH doctype, the
content canvas is valid JSON whose card blocks match Card Break labels,
modules exist in modules.txt, and the files sit at the exact paths module
sync scans. Hosted proof of import + role visibility lives in
tools/placement/native_checks.py (release-* checks).
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
ROLES = APP / "fixtures/role.json"
MODULES = APP / "modules.txt"
HOOKS = APP / "hooks.py"

EXPECTED = {
    "TH Receipts", "TH Finance",
}
# Native module anchors: the pinned visibility model requires a workspace's
# module to hold a doctype the audience can read; TH Finance anchors to the
# native Accounts module (finance officer = Accounts User).
NATIVE_MODULES = {"Accounts"}
KNOWN_REPORTS = {"TH Tuition Billing Register", "TH Placement Billing Register"}
KNOWN_DOCTYPES = {
    # native (education/erpnext) targets used by the workspaces
    "Student Applicant", "Student", "Program Enrollment", "Course Enrollment",
    "Program", "Course", "Academic Year", "Academic Term",
    "Student Group", "Course Schedule", "Student Attendance",
    "Fees", "Fee Structure", "Fee Category", "Sales Invoice", "Payment Entry",
    "Item", "Price List", "Pricing Rule", "Customer", "Company",
    # owned TH doctypes
    "TH Placement Item Revision", "TH Placement Key Revision",
    "TH Placement Blueprint Revision", "TH Placement Policy Revision",
    "TH Placement Course Map Revision", "TH Placement Case",
    "TH Placement Attempt", "TH Placement Form Manifest",
    "TH Placement Response", "TH Placement Score", "TH Placement Decision",
    "TH Placement Operation", "TH Placement Audit Event",
    "TH Admission Decision",
}


class ReleaseFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspaces = []
        for module_file in sorted(APP.glob("*/workspace/*/*.json")):
            cls.workspaces.append(json.loads(module_file.read_text()))
        cls.module_files = sorted(APP.glob("*/workspace/*/*.json"))
        cls.role_names = {r["name"] for r in json.loads(ROLES.read_text())}
        cls.modules = {m.strip() for m in MODULES.read_text().splitlines() if m.strip()}

    def test_expected_workspace_set(self):
        self.assertEqual({w["name"] for w in self.workspaces}, EXPECTED)

    def test_module_file_layout(self):
        # exact paths frappe.model.sync.get_doc_files scans for each module;
        # the shipping folder is an app module from modules.txt (the `module`
        # field may anchor to a native module instead - see NATIVE_MODULES)
        shipping = set()
        for path in self.module_files:
            ws = json.loads(path.read_text())
            slug = ws["name"].lower().replace(" ", "-")
            shipping.add(path.parents[2].name)
            self.assertEqual(path.stem, slug, ws["name"])
            self.assertEqual(path.parent.name, slug, ws["name"])
            self.assertEqual(path.name, f"{slug}.json", ws["name"])
        self.assertTrue(shipping <= {m.lower() for m in self.modules},
                        sorted(shipping - {m.lower() for m in self.modules}))

    def test_app_field_set(self):
        # module sync imports with ignore_validate=True, so the controller's
        # `self.app = get_module_app(self.module)` backfill never runs - the
        # native module-file format must carry the app explicitly.
        for ws in self.workspaces:
            self.assertEqual(ws["app"], "toefl_house", ws["name"])

    def test_roles_exist_and_are_explicit(self):
        for ws in self.workspaces:
            roles = {r["role"] for r in ws["roles"]}
            self.assertTrue(roles, (ws["name"], "empty roles would make the workspace visible to everyone"))
            self.assertTrue(roles <= self.role_names,
                            (ws["name"], sorted(roles - self.role_names)))

    def test_modules_exist(self):
        for ws in self.workspaces:
            self.assertIn(ws["module"], self.modules | NATIVE_MODULES, ws["name"])

    def test_links_resolve_to_known_doctypes(self):
        for ws in self.workspaces:
            for link in ws["links"]:
                if link["type"] == "Link":
                    if link["link_type"] == "DocType":
                        self.assertIn(link["link_to"], KNOWN_DOCTYPES, (ws["name"], link))
                    else:
                        self.assertEqual(link["link_type"], "Report", (ws["name"], link))
                        self.assertIn(link["link_to"], KNOWN_REPORTS, (ws["name"], link))
                        self.assertEqual(link.get("is_query_report"), 1, (ws["name"], link))

    def test_content_canvas_matches_cards(self):
        for ws in self.workspaces:
            cards = {l["label"] for l in ws["links"] if l["type"] == "Card Break"}
            content = json.loads(ws["content"])
            referenced = {b["data"]["card_name"] for b in content if b.get("type") == "card"}
            self.assertTrue(referenced, (ws["name"], "no card blocks"))
            self.assertEqual(referenced, cards, (ws["name"], sorted(referenced ^ cards)))

    def test_public_and_named(self):
        for ws in self.workspaces:
            self.assertEqual(ws["doctype"], "Workspace")
            self.assertEqual(ws["public"], 1, ws["name"])
            self.assertEqual(ws["for_user"], "", ws["name"])
            self.assertEqual(ws["name"], ws["label"], ws["name"])
            self.assertEqual(ws["name"], ws["title"], ws["name"])

    def test_no_duplicate_import_route(self):
        # workspaces must not also be listed as fixtures: the fixture route
        # (data_import=True) would re-import them force=True on every migrate
        # and duplicate the module-sync route.
        text = HOOKS.read_text()
        self.assertNotIn('"dt": "Workspace"', text)
        self.assertFalse((APP / "fixtures/workspace.json").exists())


if __name__ == "__main__":
    unittest.main()
