"""Execute the actual tuition refund audit snapshot with a deterministic digest.

The hosted Native suite must also submit the audit events through Frappe:
this isolated regression cannot substitute for DocType mandatory checks.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / "apps/toefl_house/toefl_house/finance/tuition_refund_commands.py"


class RefundRow(dict):
    def __getattr__(self, name):
        return self[name]


class TuitionRefundAuditEvents(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(COMMANDS.read_text(encoding="utf-8"))
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_audit_hash")
        def digest(value):
            return hashlib.sha256(
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        ns = {"digest": digest}
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     str(COMMANDS), "exec"), ns)
        self.hash = ns["_audit_hash"]
        self.row = RefundRow(
            name="SYN-REFUND-1", student="SYN-STUDENT",
            company="SYN-COMPANY", fees="SYN-FEE", requested_amount=50.0,
            approved_amount=None, reason="Synthetic case",
            evidence="Synthetic evidence", approval_evidence=None,
            status="Requested", requested_by="finance@example.test",
            approved_by=None, paying_user=None, payment_entry=None,
        )

    def test_creation_hash_is_nonempty_stable_and_does_not_expose_evidence(self):
        h = self.hash(self.row)
        self.assertEqual(len(h), 64)
        self.assertEqual(h, self.hash(self.row))
        self.assertNotIn(self.row["evidence"], h)
        self.assertNotIn(self.row["student"], h)

    def test_approval_and_denial_produce_distinct_state_hashes(self):
        original = self.hash(self.row)
        self.row.update(status="Approved", approved_amount=50.0,
                        approved_by="general.manager@example.test",
                        approval_evidence="Approved by separate actor")
        approved = self.hash(self.row)
        self.assertNotEqual(original, approved)
        self.row.update(status="Denied", approved_amount=None,
                        approval_evidence="")
        self.assertNotEqual(original, self.hash(self.row))
        self.assertNotEqual(approved, self.hash(self.row))

    def test_mutating_request_identity_or_evidence_changes_audit_hash(self):
        original = self.hash(self.row)
        for field, changed in (
            ("company", "OTHER-COMPANY"), ("fees", "OTHER-FEE"),
            ("requested_amount", 51.0), ("reason", "Different reason"),
            ("evidence", "Different evidence"), ("requested_by", "other@example.test"),
        ):
            with self.subTest(field=field):
                copy = RefundRow(self.row, **{field: changed})
                self.assertNotEqual(original, self.hash(copy))


if __name__ == "__main__":
    unittest.main()
