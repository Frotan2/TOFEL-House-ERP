import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/finance/collection_rules.py"
spec = importlib.util.spec_from_file_location("cash_collection_rules", SOURCE)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class CollectionInputTests(unittest.TestCase):
    def test_money_is_exact_and_positive(self):
        self.assertEqual(str(rules.money("500.20")), "500.20")
        self.assertEqual(str(rules.money(500)), "500.00")

    def test_invalid_money_is_not_rounded_or_silently_coerced(self):
        for value in (None, True, False, 0, -1, "NaN", "Infinity", "-Infinity", "1e999",
                      "500.005", {}, [], "not money"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rules.money(value)

    def test_batch_references_are_bounded_unique_and_stably_locked(self):
        self.assertEqual(rules.receipt_names('["PE-B", "PE-A"]'), ["PE-A", "PE-B"])
        for value in ([], ["PE-A", "PE-A"], [None], [" PE-A"], ["PE\x00A"],
                      ["X" * 141], [str(i) for i in range(101)], {}, '"PE-A"', "bad json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rules.receipt_names(value)

    def test_names_and_reasons_do_not_accept_control_characters(self):
        self.assertEqual(rules.bounded_text(" Counter A ", "counter"), "Counter A")
        for value in (None, "", "x\ny", "a" * 301):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rules.bounded_text(value, "reason", 300)
