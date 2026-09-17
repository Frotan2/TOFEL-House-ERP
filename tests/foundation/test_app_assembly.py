"""App-assembly consistency for the owned Frappe application.

Frappe resolves these wiring tables at import/migrate time and fails late and
obscurely when they disagree, so a mismatch between `hooks.py`,
`permissions.py`, `policy.can_read` and the DocType JSON files would ship
silently and only surface on a live site. The 2026-09-17 review verified this
surface by hand and found it consistent; these checks make that a permanent
invariant instead of a one-off audit.

Pure file parsing: no Frappe import, no site, no database.
"""
import ast
from pathlib import Path
import json
import re
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SECURITY = APP / "security.py"
PERMISSIONS = APP / "permissions.py"
POLICY = APP / "policy.py"


def load_hooks():
    """hooks.py is declarative data with no imports, so it can be executed safely."""
    namespace = {}
    exec(compile((APP / "hooks.py").read_text(encoding="utf-8"), "hooks.py", "exec"), namespace)
    return namespace


def load_security_constants():
    """Execute only the constant block of security.py, with frappe stubbed out."""
    source = SECURITY.read_text(encoding="utf-8").split("def require_synthetic")[0]
    frappe_stub = types.ModuleType("frappe")
    frappe_stub.PermissionError = type("PermissionError", (Exception,), {})
    previous = sys.modules.get("frappe")
    sys.modules["frappe"] = frappe_stub
    try:
        namespace = {}
        exec(compile(source, "security.py", "exec"), namespace)
        return namespace
    finally:
        if previous is None:
            del sys.modules["frappe"]
        else:
            sys.modules["frappe"] = previous


class AppAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hooks = load_hooks()
        cls.security = load_security_constants()
        cls.doctypes = {}
        for path in APP.glob("*/doctype/*/*.json"):
            definition = json.loads(path.read_text(encoding="utf-8"))
            cls.doctypes[definition["name"]] = definition
        cls.roles = {row["name"] for row in
                     json.loads((APP / "fixtures/role.json").read_text(encoding="utf-8"))}
        cls.modules = {line.strip() for line in
                       (APP / "modules.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
        cls.permissions_source = PERMISSIONS.read_text(encoding="utf-8")
        cls.policy_source = POLICY.read_text(encoding="utf-8")

    # --- DocType files -------------------------------------------------
    def test_every_doctype_directory_is_complete(self):
        directories = [p for p in APP.glob("*/doctype/*/") if p.is_dir()]
        self.assertTrue(directories, "no DocType directories found")
        for directory in directories:
            slug = directory.name
            for expected in (directory / f"{slug}.json", directory / f"{slug}.py",
                             directory / "__init__.py"):
                self.assertTrue(expected.exists(), f"missing {expected}")

    def test_every_doctype_lives_in_a_declared_module(self):
        for name, definition in self.doctypes.items():
            self.assertIn(definition["module"], self.modules,
                          f"{name} declares module {definition['module']} which is not in modules.txt")

    # --- hooks <-> permissions wiring ---------------------------------
    def test_permission_hooks_and_query_conditions_cover_exactly_the_command_doctypes(self):
        has_permission = set(self.hooks["has_permission"])
        query_conditions = set(self.hooks["permission_query_conditions"])
        guarded = set(self.security["DOCTYPES"])
        self.assertEqual(has_permission, query_conditions,
                         "has_permission and permission_query_conditions disagree")
        self.assertEqual(has_permission, guarded,
                         "hooks permission hooks and security.DOCTYPES disagree")

    def test_child_tables_are_deliberately_unguarded(self):
        children = {name for name, definition in self.doctypes.items()
                    if definition.get("istable")}
        self.assertTrue(children, "expected child tables in the app")
        self.assertEqual(children, set(self.doctypes) - set(self.hooks["has_permission"]),
                         "exactly the child tables may be absent from the permission hooks")

    def test_every_query_condition_target_exists(self):
        for doctype, target in self.hooks["permission_query_conditions"].items():
            self.assertEqual(target, f"toefl_house.permissions.query_{self.kind_of(doctype)}",
                             f"{doctype} points at an unexpected query function")
            suffix = target.rsplit("query_", 1)[1]
            self.assertIn(f"def query_{suffix}(", self.permissions_source,
                          f"{target} has no definition in permissions.py")

    def kind_of(self, doctype):
        kinds = ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        return kinds[doctype]

    def test_every_kind_has_a_row_and_query_condition_function(self):
        kinds = ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        tables = ast.literal_eval(
            re.search(r"^TABLES = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1))
        self.assertEqual(set(kinds), set(self.security["DOCTYPES"]))
        for doctype, kind in kinds.items():
            expected_table = f"`tab{doctype}`"
            if kind in ("audit", "operation"):
                continue  # audit/operation are row-level only, no query surface
            self.assertEqual(tables.get(kind), expected_table,
                             f"kind {kind} has no TABLES row for {doctype}")

    def test_can_read_covers_every_kind(self):
        """A new kind with no can_read branch would silently deny or leak."""
        kinds = set(ast.literal_eval(
            re.search(r"^KINDS = (\{.*?^\})", self.permissions_source, re.S | re.M).group(1)).values())
        body = self.policy_source.split("def can_read(")[1].split("\ndef ")[0]
        for kind in kinds:
            self.assertIn(f'"{kind}"', body,
                          f"policy.can_read has no branch for kind '{kind}'")

    # --- roles and pages ----------------------------------------------
    def test_every_command_role_is_a_shipped_fixture(self):
        for command, role in self.security["KIND_ROLES"].items():
            self.assertIn(role, self.roles, f"command {command} requires unfixed role {role}")

    def test_command_pages_exist_and_are_role_gated(self):
        pages = self.hooks["page_js"]
        self.assertTrue(pages, "no command pages are wired")
        slugs = {p.parent.name.replace("_", "-") for p in APP.glob("*/page/*/*.json")}
        for slug in pages:
            self.assertIn(slug, slugs, f"page_js references {slug} which has no Page file")
        for path in APP.glob("*/page/*/*.json"):
            page = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(page["doctype"], "Page", path.name)
            self.assertTrue(page.get("roles"), f"{path.name} has no Has Role rows")
            for row in page["roles"]:
                self.assertIn(row["role"], self.roles,
                              f"{path.name} grants Page access to unfixed role {row['role']}")

    def test_page_assets_exist(self):
        for slug, asset in self.hooks["page_js"].items():
            self.assertTrue((APP / asset).exists(), f"{slug} references missing asset {asset}")

    # --- guard seams ---------------------------------------------------
    def test_every_guarded_doctype_pins_all_three_lifecycle_seams(self):
        """A13 containment: pinned frappe fires `validate` only on save/submit."""
        events = self.hooks["doc_events"]
        seams = ("validate", "before_cancel", "before_update_after_submit")
        guarded_native = {dt for dt, handlers in events.items()
                          if any(handler.startswith("toefl_house.") for handler in handlers.values())}
        self.assertTrue(guarded_native, "no native DocType carries an owned guard")
        for doctype, handlers in events.items():
            if doctype not in guarded_native:
                continue
            for seam in seams:
                self.assertIn(seam, handlers, f"{doctype} is missing the {seam} seam")
            self.assertEqual(len({handlers[s] for s in seams}), 1,
                             f"{doctype} pins a different guard per seam")


if __name__ == "__main__":
    unittest.main()
