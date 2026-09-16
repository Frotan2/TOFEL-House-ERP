"""Pure local checks for the D3 correction framework.

Covers the policy validator and the static wiring (command roles,
protected doctypes, read-containment kinds, hooks coverage, doctype
JSON shape, native-only credit-note path). Hosted runtime acceptance
lives in tools/placement/native_checks.py.
"""
import ast
import json
import re
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (CORRECTION_POLICY_STATUSES, CORRECTION_REQUEST_STATUSES,
                                validate_correction_window_days)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SECURITY = APP / "security.py"
HOOKS = APP / "hooks.py"
CORRECTIONS = APP / "finance/corrections.py"
DOCTYPES = {
    "TH Correction Policy": APP / "finance/doctype/th_correction_policy/th_correction_policy.json",
    "TH Correction Request": APP / "finance/doctype/th_correction_request/th_correction_request.json",
}
COMMANDS = {
    "configure_correction_policy": "Finance Officer",
    "request_invoice_correction": "Finance Officer",
    "approve_invoice_correction": "Finance Officer",
    "deny_invoice_correction": "Finance Officer",
}


class WindowValidatorTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(validate_correction_window_days(0), 0)
        self.assertEqual(validate_correction_window_days(30), 30)
        self.assertEqual(validate_correction_window_days(3650), 3650)
        for bad in (-1, 3651, 2.5, True, "30", None):
            with self.assertRaises(ValueError):
                validate_correction_window_days(bad)

    def test_status_vocabularies(self):
        self.assertEqual(CORRECTION_POLICY_STATUSES, ("Active", "Retired"))
        self.assertEqual(CORRECTION_REQUEST_STATUSES, ("Requested", "Posted", "Denied"))


def _assign(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return node.value
    raise AssertionError(name + " missing")


class WiringTests(unittest.TestCase):
    def test_command_roles(self):
        roles = {k.value: v.value for k, v in zip(
            _assign(ast.parse(SECURITY.read_text()), "KIND_ROLES").keys,
            _assign(ast.parse(SECURITY.read_text()), "KIND_ROLES").values)}
        for kind, role in COMMANDS.items():
            self.assertEqual(roles.get(kind), role, kind)

    def test_credit_note_posts_inside_guarded_context(self):
        src = SECURITY.read_text()
        tree = ast.parse(src)
        fin = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FINANCE_COMMANDS":
                fin = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
        self.assertEqual(fin.get("approve_invoice_correction"), "Sales Invoice")

    def test_protected_doctypes_and_hooks(self):
        doctypes = {elt.value for elt in _assign(ast.parse(SECURITY.read_text()), "DOCTYPES").elts}
        self.assertIn("TH Correction Policy", doctypes)
        self.assertIn("TH Correction Request", doctypes)
        hooks = HOOKS.read_text()
        self.assertIn('("TH Correction Policy", "correction_policy")', hooks)
        self.assertIn('("TH Correction Request", "correction_request")', hooks)

    def test_commands_are_post_whitelisted_with_request_key(self):
        tree = ast.parse(CORRECTIONS.read_text())
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in COMMANDS:
                decorated = any(
                    isinstance(dec, ast.Call)
                    and getattr(dec.func, "attr", "") == "whitelist"
                    and any(kw.arg == "methods" and [e.value for e in kw.value.elts] == ["POST"]
                            for kw in dec.keywords)
                    for dec in node.decorator_list)
                self.assertTrue(decorated, node.name)
                self.assertEqual(node.args.args[0].arg, "request_key", node.name)
                seen.add(node.name)
        self.assertEqual(seen, set(COMMANDS))

    def test_fail_closed_and_dual_key_present(self):
        source = CORRECTIONS.read_text()
        self.assertIn("fail closed until one is configured", source)
        self.assertIn("policy-configured approver role", source)
        self.assertIn("Partial corrections await owner-defined terms", source)

    def test_credit_note_path_is_native_only(self):
        """The only money artifact comes from erpnext make_sales_return; the
        module itself creates only the two TH framework doctypes."""
        source = CORRECTIONS.read_text()
        self.assertIn("from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return",
                      source)
        created = {m.group(1) for m in re.finditer(r"doctype=([A-Z_]+|\"[^\"]+\")", source)}
        self.assertLessEqual(created, {"POLICY", "REQUEST"})

    def test_controller_invariants_wired(self):
        controllers = (APP / "controllers.py").read_text()
        self.assertIn('self.doctype == "TH Correction Policy"', controllers)
        self.assertIn('self.doctype == "TH Correction Request"', controllers)


class DocTypeShapeTests(unittest.TestCase):
    def test_json_shape(self):
        for name, path in DOCTYPES.items():
            data = json.loads(path.read_text())
            self.assertEqual(data["name"], name)
            self.assertEqual(data["module"], "Finance")
            self.assertEqual(data["autoname"], "hash")
            for row in data["permissions"]:
                granted = {k for k, v in row.items() if v == 1 and k != "role"}
                self.assertLessEqual(granted, {"read", "select"},
                                     "no role may hold direct write")
            fields = {f["fieldname"] for f in data["fields"]}
            if name == "TH Correction Policy":
                self.assertLessEqual({"approver_role", "correction_window_days",
                                      "status", "synthetic"}, fields)
            if name == "TH Correction Request":
                self.assertLessEqual({"sales_invoice", "reason", "requested_amount",
                                      "status", "approved_by", "credit_note",
                                      "synthetic"}, fields)


if __name__ == "__main__":
    unittest.main()
