"""Audit payout pre-state must come from the locked native request.

Runs the real pay command body against synthetic stubs and checks native
source ordering. No Frappe site, GL write, customer record, or payout.
Real database-backed native CI is a separate release gate.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house" / "toefl_house" / "finance"
COMMANDS = ROOT / "tuition_refund_commands.py"
NATIVE = ROOT / "tuition_refund_native.py"


def function(path, name):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


class LockedPayoutAuditTests(unittest.TestCase):
    def test_native_snapshot_follows_both_locks_and_precedes_mutations(self):
        source = NATIVE.read_text(encoding="utf-8")
        node = function(NATIVE, "post_approved_refund")
        body = ast.get_source_segment(source, node)
        fee_lock = body.index('fee = frappe.get_doc("Fees", fee_name, for_update=True)')
        request_lock = body.index('req = frappe.get_doc(REQUEST, name, for_update=True)')
        snapshot = body.index('before_hash = _audit_hash(req)')
        first_post = body.index('document.insert(ignore_permissions=True)')
        paid = body.index('req.paying_user, req.status = actor, "Paid"')
        self.assertLess(fee_lock, request_lock)
        self.assertLess(request_lock, snapshot)
        self.assertLess(snapshot, first_post)
        self.assertLess(snapshot, paid)
        self.assertIn('currency="AFN"), before_hash', body)

    def test_command_uses_native_locked_prestate_not_unlocked_request(self):
        node = function(COMMANDS, "pay_tuition_refund")
        calls = []
        old = SimpleNamespace(name="SYN-REF-1", status="Approved")
        new = SimpleNamespace(name="SYN-REF-1", status="Paid")
        native_before = "HASH-FROM-LOCKED-APPROVED"
        captured = {}

        def native(name):
            self.assertEqual(name, old.name)
            calls.append("native-lock-and-post")
            return new, {"name": name, "status": "Paid"}, native_before

        def digest(doc):
            calls.append(("hash", doc.status))
            return "HASH-PAID" if doc.status == "Paid" else "HASH-STALE"

        def execute(kind, key, payload, work):
            result, event = work("payer@example.test")
            captured.update(event)
            return result

        namespace = {
            "frappe": SimpleNamespace(
                whitelist=lambda **kwargs: lambda f: f,
                get_doc=lambda *args: self.fail("Unprotected pre-lock request read"),
                ValidationError=ValueError,
            ),
            "REQUEST": "TH Tuition Refund Request",
            "tuition_refunds": SimpleNamespace(PAYER_ROLE="Finance Manager", RefundError=ValueError),
            "_require_role": lambda actor, role: None,
            "_name": lambda value, label: value,
            "_audit_hash": digest,
            "execute_atomic": execute,
            "post_approved_refund": native,
        }
        # The actual function imports these dependencies locally; provide
        # synthetic modules rather than executing any native accounting code.
        import sys
        from unittest.mock import patch
        fake_atomic = SimpleNamespace(execute_atomic=execute)
        fake_native = SimpleNamespace(post_approved_refund=native)
        with patch.dict(sys.modules, {
            "toefl_house": SimpleNamespace(),
            "toefl_house.atomic_commands": fake_atomic,
            "toefl_house.finance": SimpleNamespace(),
            "toefl_house.finance.tuition_refund_native": fake_native,
        }):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(COMMANDS), "exec"), namespace)
            result = namespace["pay_tuition_refund"]("synthetic-key", old.name)

        self.assertEqual(result["status"], "Paid")
        self.assertEqual(captured["before_hash"], native_before)
        self.assertEqual(captured["after_hash"], "HASH-PAID")
        self.assertEqual(calls, ["native-lock-and-post", ("hash", "Paid")])

    def test_failed_native_payout_never_emits_audit_event(self):
        node = function(COMMANDS, "pay_tuition_refund")
        events = []

        def failure(name):
            raise ValueError("synthetic native validation refused")

        def execute(kind, key, payload, work):
            result, event = work("payer@example.test")
            events.append(event)
            return result

        import sys
        from unittest.mock import patch
        namespace = {
            "frappe": SimpleNamespace(whitelist=lambda **kwargs: lambda f: f,
                                      ValidationError=ValueError),
            "tuition_refunds": SimpleNamespace(PAYER_ROLE="Finance Manager", RefundError=ValueError),
            "_require_role": lambda actor, role: None,
            "_name": lambda value, label: value,
            "_audit_hash": lambda req: self.fail("Hash must not run on failure"),
        }
        with patch.dict(sys.modules, {
            "toefl_house": SimpleNamespace(),
            "toefl_house.atomic_commands": SimpleNamespace(execute_atomic=execute),
            "toefl_house.finance": SimpleNamespace(),
            "toefl_house.finance.tuition_refund_native": SimpleNamespace(post_approved_refund=failure),
        }):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(COMMANDS), "exec"), namespace)
            with self.assertRaisesRegex(ValueError, "synthetic native validation"):
                namespace["pay_tuition_refund"]("synthetic-key", "SYN-REF-1")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
