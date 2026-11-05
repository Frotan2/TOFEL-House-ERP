"""Group 4 (reporting/integrity): desk facts must never present a bounded
preview length as an exact count.

The finance desk's outstanding/correction/assignment facts and the academic
desk's finalized-awaiting-release fact previously used ``len()`` over lists
capped at LIMIT_QUEUES / BOUNCE_WINDOW. They now go through
``count_or_unknown`` (full scoped count, or "—" when the preview cannot
prove completeness) and the academic awaiting-release difference is only
shown when BOTH of its source reads are proven complete.
"""
import ast
import unittest
from pathlib import Path

from tests.desk.test_desk_contract import _import_desk

ROOT = Path(__file__).resolve().parents[2]
DESK = ROOT / "apps/toefl_house/toefl_house/desk"


class CountOrUnknownTests(unittest.TestCase):
    def setUp(self):
        self.desk = _import_desk("__init__")
        self.calls = []

        def scripted_count(doctype, filters=None):
            self.calls.append((doctype, filters))
            return self.total

        self.desk.frappe.db.count = scripted_count
        # project_count also runs scope resolution against the stub world;
        # replace it with the scripted count so only the helper logic is
        # under test here (the wiring is pinned by the AST tests below).
        self.desk.project_count = lambda desk, doctype, filters=None: (
            scripted_count(doctype, filters))
        self.total = 0

    def test_exact_count_returned_when_it_covers_the_preview(self):
        self.total = 30
        self.assertEqual(
            self.desk.count_or_unknown(
                "finance", "Fees", preview=[{"name": f"F-{i}"} for i in range(25)]),
            30)

    def test_count_smaller_than_preview_is_unknown_not_the_preview_length(self):
        self.total = 3
        self.assertEqual(
            self.desk.count_or_unknown(
                "finance", "Fees", preview=[{"name": f"F-{i}"} for i in range(25)]),
            "—")

    def test_zero_is_a_real_count_when_the_preview_is_empty(self):
        self.total = 0
        self.assertEqual(
            self.desk.count_or_unknown("finance", "Fees", preview=[]), 0)

    def test_denied_or_broken_count_source_is_unknown_never_zero(self):
        self.desk.project_count = lambda *a, **k: (_ for _ in ()).throw(
            Exception("denied"))
        self.assertEqual(
            self.desk.count_or_unknown("finance", "Fees", preview=[]), "—")
        self.desk.project_count = lambda *a, **k: True
        self.assertEqual(
            self.desk.count_or_unknown("finance", "Fees", preview=[]), "—")
        self.desk.project_count = lambda *a, **k: -1
        self.assertEqual(
            self.desk.count_or_unknown("finance", "Fees", preview=[]), "—")


class DeskFactWiringTests(unittest.TestCase):
    """The capped lists must no longer feed a fact value through len()."""

    def test_finance_facts_use_count_or_unknown_or_a_completeness_guard(self):
        source = (DESK / "finance.py").read_text(encoding="utf-8")
        for capped in ("len(outstanding_invoices)", "len(outstanding_fees)",
                       "len(assignments)"):
            self.assertNotIn(capped, source)
        self.assertNotIn(
            "sum(1 for row in corrections if row[\"status\"] == \"Requested\")",
            source)
        self.assertIn("count_or_unknown(", source)
        self.assertIn("len(awaiting_billing) if billing_read_complete else",
                      source)

    def test_academic_awaiting_release_requires_both_reads_complete(self):
        source = (DESK / "academic.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        funnel = [node for node in ast.walk(tree)
                  if isinstance(node, ast.Dict)
                  and any(isinstance(value, ast.Constant)
                          and value.value == "Finalized, awaiting release"
                          for value in node.values)]
        self.assertTrue(funnel, "awaiting-release fact missing")
        self.assertNotIn('"value": len(awaiting_release)', source)
        self.assertIn("awaiting_release_total", source)
        self.assertIn("finalized_total == len(finalized_waiting)", source)
        self.assertIn("released_total == len(released)", source)


if __name__ == "__main__":
    unittest.main()
