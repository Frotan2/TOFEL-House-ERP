"""Adversarial stock and payroll analytics safety contracts.

These execute the actual function bodies with a fake native permission engine:
missing roles and incomplete pagination must never become reported zero totals.
"""
import ast
from pathlib import Path
import types
import unittest


SOURCE = (Path(__file__).resolve().parents[2]
          / "apps/toefl_house/toefl_house/desk/analytics.py")


def load_metrics(allowed=(), *, exists=True, rows=None, size_limit=400):
    script = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(script)
    names = {"_native_rows", "book_stock_metrics", "payroll_metrics"}
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    seen = set()
    calls = []

    def get_list(doctype, **kwargs):
        calls.append((doctype, kwargs))
        return list((rows or {}).get(doctype, []))

    def has_permission(doctype, action):
        seen.add((doctype, action))
        return doctype in allowed and action == "read"

    frappe = types.SimpleNamespace(
        db=types.SimpleNamespace(exists=lambda dt, name: exists),
        has_permission=has_permission, get_list=get_list)
    ns = {"frappe": frappe, "BOUNCE_WINDOW": size_limit}
    exec(compile(ast.Module(body=selected, type_ignores=[]),
                 str(SOURCE), "exec"), ns)
    return ns, seen, calls


class ExecutiveMetricPrivacyTests(unittest.TestCase):
    def test_book_inventory_requires_native_read_permissions(self):
        ns, seen, calls = load_metrics(allowed={"Item"})
        state = ns["book_stock_metrics"]()
        self.assertEqual(state["items"], "—")
        self.assertEqual(state["total_qty"], "—")
        self.assertEqual(calls, [])
        self.assertIn(("Bin", "read"), seen)

    def test_absent_book_group_cannot_be_reported_as_empty_stock(self):
        ns, _, calls = load_metrics(allowed={"Item", "Bin"}, exists=False)
        state = ns["book_stock_metrics"]()
        self.assertEqual(state["items"], "—")
        self.assertEqual(calls, [])

    def test_native_permission_scope_filters_only_book_bins(self):
        ns, _, calls = load_metrics(
            allowed={"Item", "Bin"},
            rows={"Item": [{"name": "BOOK-1"}],
                  "Bin": [{"name": "BIN-1", "actual_qty": 8}]})
        state = ns["book_stock_metrics"]()
        self.assertEqual(state["items"], 1)
        self.assertEqual(state["total_qty"], 8)
        self.assertEqual(calls[0][1]["filters"]["item_group"], "Books")
        self.assertEqual(calls[1][1]["filters"]["item_code"], ("in", ["BOOK-1"]))
        self.assertEqual(state["low_stock"], "—")

    def test_truncated_stock_and_payroll_never_show_false_zero(self):
        ns, _, _ = load_metrics(
            allowed={"Item", "Bin", "Additional Salary", "Salary Slip"},
            rows={"Item": [{"name": "B1"}, {"name": "B2"}],
                  "Additional Salary": [{"name": "A1"}, {"name": "A2"}]},
            size_limit=1)
        self.assertEqual(ns["book_stock_metrics"]()["items"], "—")
        self.assertEqual(ns["payroll_metrics"](authorized=True)["total"], "—")

    def test_payroll_owner_role_alone_cannot_grant_hrms_access(self):
        ns, _, calls = load_metrics(allowed={"Additional Salary"})
        state = ns["payroll_metrics"](authorized=True)
        self.assertFalse(state["authorized"])
        self.assertEqual(state["total"], "—")
        self.assertEqual([doctype for doctype, _ in calls], ["Additional Salary"])

    def test_authorized_payroll_counts_native_permission_filtered_records(self):
        ns, _, calls = load_metrics(
            allowed={"Additional Salary", "Salary Slip"},
            rows={"Additional Salary": [{"name": "A"}], "Salary Slip": []})
        self.assertEqual(ns["payroll_metrics"](authorized=False)["total"], "—")
        state = ns["payroll_metrics"](authorized=True)
        self.assertTrue(state["authorized"])
        self.assertEqual(state["total"], 1)
        self.assertEqual(state["slips"], 0)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
