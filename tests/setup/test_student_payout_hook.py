"""Execute the real native Payment Entry event handler against synthetic docs.

Unlike source-only inspections, these tests compile and invoke the exact
guard_payment_entry body with narrowly stubbed Frappe imports. They cannot
post a native accounting document and are not a substitute for Windows UAT.
"""
import ast
import builtins
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
sys.path.insert(0, str(APP))
# D2: same stub-package load as test_student_payout_hold — the guard
# module is pure, but the finance package __init__ imports frappe.
_previous = {name: sys.modules.get(name)
             for name in ("toefl_house", "toefl_house.finance")}
_root = types.ModuleType("toefl_house")
_root.__path__ = [str(APP / "toefl_house")]
_finance = types.ModuleType("toefl_house.finance")
_finance.__path__ = [str(APP / "toefl_house" / "finance")]
sys.modules["toefl_house"] = _root
sys.modules["toefl_house.finance"] = _finance
from toefl_house.finance.student_payout_policy import (  # noqa: E402
    student_pay_write_allowed,
)
for _name, _old in _previous.items():
    if _old is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _old

GUARD_SOURCE = APP / "toefl_house" / "finance" / "refunds.py"


class Blocked(Exception):
    pass


class NativeDoc:
    def __init__(self, payment_type, party_type):
        self.payment_type = payment_type
        self.party_type = party_type

    def get_doc_before_save(self):
        return None


def real_hook():
    tree = ast.parse(GUARD_SOURCE.read_text(encoding="utf-8"))
    found = [x for x in tree.body if isinstance(x, ast.FunctionDef)
             and x.name == "guard_payment_entry"]
    if len(found) != 1:
        raise AssertionError("Expected exactly one native guard")
    source = compile(ast.Module(body=found, type_ignores=[]),
                     str(GUARD_SOURCE), "exec")
    require_calls = []
    native_calls = []
    security = types.ModuleType("toefl_house.security")
    security.require_operational = lambda: require_calls.append("operational")
    payout = types.ModuleType("toefl_house.finance.student_payout_policy")
    payout.student_pay_write_allowed = student_pay_write_allowed
    # D2: since the native pair landed, guard_payment_entry also
    # imports tuition_refund_native.guard_payment. A synthetic
    # NativeDoc is by construction not a pair document, and the real
    # guard_payment returns False for non-pair documents (after
    # frappe.db checks this harness cannot run), so stub it as False
    # and let the policy check decide — the pair path itself is
    # covered by the finance native tests, not by this hook test.
    native = types.ModuleType("toefl_house.finance.tuition_refund_native")
    native.guard_payment = lambda doc, method=None: False

    def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "toefl_house.security":
            return security
        if name == "toefl_house.finance.student_payout_policy":
            return payout
        if name == "toefl_house.finance.tuition_refund_native":
            return native
        raise AssertionError(f"Unexpected dynamic import in finance guard: {name}")

    env = {
        "__builtins__": {**vars(builtins), "__import__": restricted_import},
        "frappe": types.SimpleNamespace(ValidationError=Blocked),
        "refund_permitted": lambda doc, **kwargs: native_calls.append(
            (doc.payment_type, doc.party_type)) or True,
    }
    exec(source, env)
    return env["guard_payment_entry"], require_calls, native_calls


class ActualNativeGuardTests(unittest.TestCase):
    def test_block_direct_student_payout_before_accounting_path(self):
        guard, require_calls, native_calls = real_hook()
        with self.assertRaisesRegex(Blocked, "Direct Student Pay is denied"):
            guard(NativeDoc("Pay", "Student"), method="validate")
        self.assertEqual(require_calls, ["operational"])
        self.assertEqual(native_calls, [])

    def test_post_submit_student_payout_edit_is_blocked(self):
        guard, _, native_calls = real_hook()
        with self.assertRaisesRegex(Blocked, "Direct Student Pay is denied"):
            guard(NativeDoc("Pay", "Student"),
                  method="before_update_after_submit")
        self.assertEqual(native_calls, [])

    def test_legacy_student_pay_cancellation_may_reach_native_validation(self):
        guard, _, native_calls = real_hook()
        guard(NativeDoc("Pay", "Student"), method="before_cancel")
        self.assertEqual(native_calls, [("Pay", "Student")])

    def test_student_tuition_receipt_still_works(self):
        guard, _, native_calls = real_hook()
        guard(NativeDoc("Receive", "Student"), method="validate")
        self.assertEqual(native_calls, [("Receive", "Student")])

    def test_customer_book_refund_and_supplier_pay_unaffected(self):
        guard, _, native_calls = real_hook()
        guard(NativeDoc("Pay", "Customer"), method="validate")
        guard(NativeDoc("Pay", "Supplier"), method="validate")
        self.assertEqual(native_calls, [("Pay", "Customer"), ("Pay", "Supplier")])


if __name__ == "__main__":
    unittest.main()
