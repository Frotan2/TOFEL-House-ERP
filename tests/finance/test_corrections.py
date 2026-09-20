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
    "set_correction_policy_status": "Finance Officer",
    "validate_correction_policy": "Finance Officer",
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
            by_name = {f["fieldname"]: f for f in data["fields"]}
            # The readable order is the readable contract: every stored
            # field is ordered exactly once.
            self.assertEqual(sorted(data["field_order"]), sorted(fields))
            if name == "TH Correction Policy":
                self.assertLessEqual({"approver_role", "correction_window_days",
                                      "effective_from", "reason", "set_by",
                                      "set_on", "superseded_on", "status",
                                      "synthetic"}, fields)
                # Versions are effective-dated and unique-dated: the unique
                # date is the serialization backstop against concurrent
                # same-date appends.
                self.assertEqual(by_name["effective_from"].get("reqd"), 1)
                self.assertEqual(by_name["effective_from"].get("unique"), 1)
                self.assertEqual(by_name["reason"].get("reqd"), 1)
                for stamp in ("set_by", "set_on", "superseded_on"):
                    self.assertEqual(by_name[stamp].get("read_only"), 1, stamp)
            if name == "TH Correction Request":
                self.assertLessEqual({"sales_invoice", "fees", "correction_policy",
                                      "reason", "requested_amount",
                                      "status", "approved_by", "credit_note",
                                      "synthetic"}, fields)
                # The pin is mandatory and command-written: requests always
                # resolve the version that governed their creation.
                self.assertEqual(by_name["correction_policy"].get("reqd"), 1)
                self.assertEqual(by_name["correction_policy"].get("read_only"), 1)


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


def _correction_function_body(name):
    source = CORRECTIONS.read_text()
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(source, fn) or ""


class PolicyVersioningTests(unittest.TestCase):
    """Correction policy terms are append-only effective-dated versions.

    Configuring NEVER rewrites: a new version starts strictly after the
    latest one, every previous Active version is superseded (closed with
    the new effective date), and the unique effective date refuses a
    concurrent same-date append in business language. The audit stream is
    the singleton policy behind a stable target, so the hash chain spans
    versions; status changes and validation commit to the exact version
    snapshot.
    """

    def test_configure_appends_a_version_with_reason(self):
        tree = ast.parse(CORRECTIONS.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "configure_correction_policy")
        params = [arg.arg for arg in fn.args.args]
        self.assertEqual(params, ["request_key", "approver_role",
                                  "correction_window_days",
                                  "effective_from", "reason"])
        body = _correction_function_body("configure_correction_policy")
        self.assertIn("validate_schedule_date", body)
        self.assertIn("validate_change_reason", body)
        self.assertIn("check_appends", body)
        self.assertIn("superseded_on", body)
        self.assertIn("DuplicateEntryError", body)
        self.assertIn("snapshot_digest", body)
        self.assertIn("POLICY_STREAM", body)
        # No version is ever edited in place: the only writes are the
        # retire-and-close stamp on predecessors and the new-row insert.
        self.assertNotIn(".approver_role =", body)
        self.assertNotIn(".correction_window_days =", body)
        self.assertNotIn(".effective_from =", body)

    def test_status_command_only_retires_or_reactivates_latest(self):
        body = _correction_function_body("set_correction_policy_status")
        self.assertIn("CORRECTION_POLICY_STATUSES", body)
        self.assertIn("latest_version", body)
        self.assertIn("is already", body)
        self.assertIn("snapshot_digest", body)
        self.assertIn("POLICY_STREAM", body)

    def test_validate_commits_to_the_exact_snapshot(self):
        body = _correction_function_body("validate_correction_policy")
        self.assertIn("assert_no_ambiguous_versions", body)
        self.assertIn("Two correction policy versions are Active", body)
        self.assertIn("no longer exists", body)
        self.assertIn("compute_readiness", body)
        self.assertIn("latest_effective_from", body)
        self.assertIn("POLICY_STREAM", body)

    def test_no_business_default_terms(self):
        """No command carries a default: every term arrives as an
        owner-supplied argument, never as a literal in the code."""
        tree = ast.parse(CORRECTIONS.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in COMMANDS:
                self.assertEqual(node.args.defaults, [], node.name)
                self.assertEqual(node.args.kw_defaults, [], node.name)

    def test_window_bound_is_a_named_typo_guard(self):
        """The 0-3650 window bound is input hygiene, not a policy term: the
        literal lives once at the named constant and the validator only
        references the constant."""
        from toefl_house.policy import CORRECTION_WINDOW_MAX_DAYS
        self.assertEqual(CORRECTION_WINDOW_MAX_DAYS, 3650)
        source = (APP / "policy.py").read_text()
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "validate_correction_window_days")
        body = ast.get_source_segment(source, fn) or ""
        self.assertIn("CORRECTION_WINDOW_MAX_DAYS", body)
        self.assertNotIn("3650", body)

    def test_controller_guards_the_version_chain(self):
        controllers = (APP / "controllers.py").read_text()
        tree = ast.parse(controllers)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_validate_correction_policy")
        body = ast.get_source_segment(controllers, fn) or ""
        self.assertIn("Only one correction policy version may be Active", body)
        self.assertIn("Only the latest correction policy version may be Active", body)
        self.assertIn("A closed version stays closed", body)
        self.assertIn("superseded_on", body)
        req = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef)
                   and n.name == "_validate_correction_request")
        req_body = ast.get_source_segment(controllers, req) or ""
        self.assertIn("correction_policy", req_body)


class PolicyPinningTests(unittest.TestCase):
    """Requests pin the governing version; decisions judge the pin.

    Policy edits never reinterpret a raised request: each request stores
    the version governing its creation date, and every decision (approve
    or deny, invoice or fees) resolves the approver role and the window
    from that pinned version - while live document facts are still
    re-proven against the live document.
    """

    def test_requests_pin_the_governing_version(self):
        for name in ("request_invoice_correction",
                     "request_fees_correction"):
            body = _correction_function_body(name)
            self.assertIn("_governing_policy", body, name)
            self.assertIn('correction_policy=governing["name"]', body, name)
            self.assertIn('"correction_policy": governing["name"]', body, name)

    def test_decisions_judge_the_pin_before_the_role(self):
        for name in ("approve_invoice_correction",
                     "deny_invoice_correction",
                     "approve_fees_correction",
                     "deny_fees_correction"):
            body = _correction_function_body(name)
            self.assertIn("_pinned_policy", body, name)
            self.assertLess(body.index("_pinned_policy"),
                            body.index("_require_approver"),
                            f"{name}: pinned terms resolve before the role is judged")
            self.assertNotIn("_governing_policy", body, name)
            self.assertNotIn("_active_policy", body, name)

    def test_approval_windows_come_from_pinned_terms(self):
        for name in ("approve_invoice_correction",
                     "approve_fees_correction"):
            body = _correction_function_body(name)
            self.assertIn("terms.correction_window_days", body, name)


if __name__ == "__main__":
    unittest.main()
