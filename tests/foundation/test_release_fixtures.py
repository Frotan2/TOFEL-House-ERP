"""Static validation of the R1 release-surface fixture (role-scoped
workspaces). Pure JSON/AST; imports nothing from the app.

Guards the invariant that workspaces are pure native navigation
configuration: every role row exists in the role fixture, every link
target is a known native or TH doctype, the content canvas is valid JSON
whose card blocks match Card Break labels, and modules exist in
modules.txt. Hosted proof of import + role visibility lives in
tools/placement/native_checks.py (release-* checks).
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
WORKSPACES = APP / "fixtures/workspace.json"
ROLES = APP / "fixtures/role.json"
MODULES = APP / "modules.txt"
HOOKS = APP / "hooks.py"

EXPECTED = {
    "TH Placement", "TH Admission", "TH Enrollment",
    "TH Teaching", "TH Finance", "TH Receipts",
}
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
        cls.workspaces = json.loads(WORKSPACES.read_text())
        cls.role_names = {r["name"] for r in json.loads(ROLES.read_text())}
        cls.modules = {m.strip() for m in MODULES.read_text().splitlines() if m.strip()}

    def test_expected_workspace_set(self):
        self.assertEqual({w["name"] for w in self.workspaces}, EXPECTED)

    def test_roles_exist_and_are_explicit(self):
        for ws in self.workspaces:
            roles = {r["role"] for r in ws["roles"]}
            self.assertTrue(roles, (ws["name"], "empty roles would make the workspace visible to everyone"))
            self.assertTrue(roles <= self.role_names,
                            (ws["name"], sorted(roles - self.role_names)))

    def test_modules_exist(self):
        for ws in self.workspaces:
            self.assertIn(ws["module"], self.modules, ws["name"])

    def test_links_resolve_to_known_doctypes(self):
        for ws in self.workspaces:
            for link in ws["links"]:
                if link["type"] == "Link":
                    self.assertEqual(link["link_type"], "DocType", (ws["name"], link))
                    self.assertIn(link["link_to"], KNOWN_DOCTYPES, (ws["name"], link))

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

    def test_hooks_fixture_entry_covers_all(self):
        text = HOOKS.read_text()
        self.assertIn('"dt": "Workspace"', text)
        for name in EXPECTED:
            self.assertIn('"%s"' % name, text, (name, "missing from hooks fixture filter"))


if __name__ == "__main__":
    unittest.main()
