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
    "request_fees_correction": "Finance Officer",
    "approve_fees_correction": "Finance Officer",
    "deny_fees_correction": "Finance Officer",
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
        self.assertEqual(fin.get("approve_fees_correction"), "Fees")

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
                self.assertLessEqual({"sales_invoice", "fees", "reason", "requested_amount",
                                      "status", "approved_by", "credit_note",
                                      "synthetic"}, fields)


class ApprovalRevalidationTests(unittest.TestCase):
    """Approval must re-prove the request-time invariants, not assume them.

    Requesting and approving a correction are separate commands that can be
    separated by any interval. The request proves, under a row lock, that the
    document is submitted, that its total equals the requested amount (v1 is
    full-amount only), and that the correction window is open. If approval
    trusted those facts it would reverse a document whose total had since
    changed while still reporting the stale amount - an inaccurate financial
    record. The same re-proof is required for Fees and for placement invoices.
    """

    def test_approval_revalidates_the_fee_under_lock(self):
        source = CORRECTIONS.read_text()
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "approve_fees_correction")
        body = ast.get_source_segment(source, fn) or ""
        # The fee row is locked and re-read before the native cancellation.
        self.assertIn("for update", body)
        self.assertIn("grand_total", body)
        self.assertIn("posting_date", body)
        self.assertLess(body.index("for update"), body.index("fee_doc.cancel()"),
                        "the fee must be locked and re-read before it is cancelled")
        # Each request-time invariant is re-asserted at approval time.
        self.assertIn("The fee is no longer submitted", body)
        self.assertIn("The fee total changed after this request was raised", body)
        self.assertIn("Correction window for this fee has closed", body)
        self.assertIn("no longer exists", body)

    def test_invoice_approval_revalidates_the_invoice_under_lock(self):
        """The invoice path had the same TOCTOU the fee path already closed."""
        source = CORRECTIONS.read_text()
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "approve_invoice_correction")
        body = ast.get_source_segment(source, fn) or ""
        self.assertIn("for update", body)
        self.assertIn("grand_total", body)
        self.assertIn("posting_date", body)
        self.assertLess(body.index("for update"), body.index("note = make_sales_return"),
                        "the invoice must be locked and re-read before a credit note is posted")
        self.assertIn("Correction request is not for an invoice", body)
        self.assertIn("The invoice is no longer submitted", body)
        self.assertIn("The invoice total changed after this request was raised", body)
        self.assertIn("Correction window for this invoice has closed", body)
        self.assertIn("no longer exists", body)


if __name__ == "__main__":
    unittest.main()
