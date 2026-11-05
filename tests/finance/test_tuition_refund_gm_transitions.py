"""Exercise the actual General Manager refund command bodies with isolated stubs.

The command functions are compiled from source AST, preserving nested work
closures and their order of locks. No Frappe site, cash, or financial writes.
This complements (not replaces) independent native-site acceptance.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house" /
          "toefl_house" / "finance" / "tuition_refund_commands.py")


class _Request:
    def __init__(self, status="Requested", fees="FEE-1"):
        self.name = "REF-1"
        self.fees = fees
        self.student = "ST-1"
        self.company = "CO-1"
        self.status = status
        self.requested_by = "officer@example.test"
        self.requested_amount = "50.00"
        self.evidence = "Synthetic case evidence"
        self.reason = "Synthetic withdrawal"
        self.approved_by = "prior.manager@example.test"
        self.approved_amount = "50.00"
        self.approval_evidence = "Synthetic approval"
        self.flags = SimpleNamespace(ignore_permissions=False)
        self.saves = 0

    def get(self, field):
        return getattr(self, field, None)

    def as_dict(self):
        return vars(self).copy()

    def save(self, *, ignore_permissions):
        assert ignore_permissions is True
        self.saves += 1


class _DB:
    def __init__(self, case):
        self.case = case

    def get_value(self, doctype, name, fields, *, as_dict=False, for_update=False):
        if doctype == "TH Tuition Refund Request":
            self.case.events.append(("lookup-request-fees", name))
            return self.case.initial_fees
        assert doctype == "Fees" and as_dict and for_update
        assert fields == ["docstatus", "student", "company"]
        self.case.events.append(("verify-fees", name))
        return self.case.fee

    def sql(self, query, params):
        assert query == "select name from `tabFees` where name=%s for update"
        self.case.events.append(("lock-fees", params[0]))
        return [(params[0],)]


class GMTransitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body
                     if isinstance(node, ast.FunctionDef)}
        cls.functions = [functions[name] for name in (
            "_name", "_require_role", "_require_request_fee_identity",
            "approve_tuition_refund", "deny_tuition_refund", "void_tuition_refund")]

    def setUp(self):
        self.events = []
        self.req = _Request()
        self.initial_fees = "FEE-1"
        self.fee = SimpleNamespace(docstatus=1, student="ST-1", company="CO-1")
        self.roles = ["General Manager"]

        class ValidationError(Exception):
            pass

        class PermissionError(Exception):
            pass

        self.ValidationError = ValidationError
        self.PermissionError = PermissionError
        db = _DB(self)

        def approve_request(data, *, approver, approver_roles, evidence):
            return {"approved_amount": data["requested_amount"],
                    "evidence": evidence or data["evidence"]}

        refunds = SimpleNamespace(
            APPROVER_ROLE="General Manager",
            RefundError=ValueError,
            approve_request=approve_request,
            deny_request=lambda *args, **kwargs: None,
            void_approval=lambda request, *, actor, roles, reason: {
                "status": "Voided", "voided_by": actor, "void_reason": reason,
            },
        )
        frappe = SimpleNamespace(
            db=db,
            whitelist=lambda **kwargs: (lambda fn: fn),
            get_roles=lambda user: self.roles,
            ValidationError=ValidationError,
            PermissionError=PermissionError,
            utils=SimpleNamespace(now_datetime=lambda: "2026-11-05 04:00:00"),
        )
        namespace = {
            "frappe": frappe,
            "REQUEST": "TH Tuition Refund Request",
            "FEES": "Fees",
            "tuition_refunds": refunds,
            "_pending_request": self._pending,
            "_require_target_company": lambda fees: self.events.append(("scope", fees)),
            "_audit_hash": lambda req: "synthetic-hash",
            "_execute": lambda action, key, payload, work: work("gm@example.test"),
        }
        exec(compile(ast.Module(body=self.functions, type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        self.api = namespace

    def _pending(self, name):
        self.events.append(("lock-request", name))
        return self.req

    def invoke(self, command):
        if command == "approve":
            return self.api["approve_tuition_refund"]("unique-1", "REF-1", "Approved evidence")
        if command == "deny":
            return self.api["deny_tuition_refund"]("unique-1", "REF-1")
        if command == "void":
            return self.api["void_tuition_refund"]("unique-1", "REF-1", "Reason for void")
        raise AssertionError(command)

    def test_all_gm_actions_lock_fee_first_and_update_only_verified_request(self):
        for command, new_status in (("approve", "Approved"), ("deny", "Denied"),
                                    ("void", "Voided")):
            with self.subTest(command=command):
                self.setUp()
                if command == "void":
                    self.req.status = "Approved"
                output, receipt = self.invoke(command)
                self.assertEqual(output["status"], new_status)
                self.assertEqual(self.req.status, new_status)
                self.assertEqual(self.req.saves, 1)
                self.assertEqual(self.events, [
                    ("lookup-request-fees", "REF-1"),
                    ("lock-fees", "FEE-1"),
                    ("lock-request", "REF-1"),
                    ("verify-fees", "FEE-1"),
                    ("scope", "FEE-1"),
                ])
                self.assertEqual(receipt["target"], "REF-1")

    def test_mismatched_or_unsubmitted_fee_never_mutates_any_gm_action(self):
        for command in ("approve", "deny", "void"):
            for failure in ("missing", "draft", "cancelled", "student", "company"):
                with self.subTest(command=command, failure=failure):
                    self.setUp()
                    if command == "void":
                        self.req.status = "Approved"
                    if failure == "missing":
                        self.fee = None
                    elif failure in ("draft", "cancelled"):
                        self.fee.docstatus = 0 if failure == "draft" else 2
                    else:
                        setattr(self.fee, failure, "OTHER")
                    with self.assertRaisesRegex(self.ValidationError, "does not match"):
                        self.invoke(command)
                    self.assertEqual(self.req.saves, 0)
                    self.assertNotIn(("scope", "FEE-1"), self.events)

    def test_changed_fee_link_after_unlocked_lookup_does_not_lock_second_fee(self):
        for command in ("approve", "deny", "void"):
            with self.subTest(command=command):
                self.setUp()
                self.req.fees = "FEE-2"
                if command == "void":
                    self.req.status = "Approved"
                with self.assertRaisesRegex(self.ValidationError, "link changed"):
                    self.invoke(command)
                self.assertEqual(self.events, [
                    ("lookup-request-fees", "REF-1"),
                    ("lock-fees", "FEE-1"),
                    ("lock-request", "REF-1"),
                ])
                self.assertEqual(self.req.saves, 0)

    def test_without_general_manager_role_all_actions_refuse_before_fee_lookup(self):
        for command in ("approve", "deny", "void"):
            with self.subTest(command=command):
                self.setUp()
                self.roles = ["Receptionist"]
                with self.assertRaises(self.PermissionError):
                    self.invoke(command)
                self.assertEqual(self.events, [])
                self.assertEqual(self.req.saves, 0)


if __name__ == "__main__":
    unittest.main()
