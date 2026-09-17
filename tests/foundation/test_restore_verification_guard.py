"""A restore verification must fail closed when it would verify nothing.

``tools/foundation/runtime_restore.py`` verifies that a restored site still holds
the synthetic business records by zipping ``students``, ``applicants`` and
``enrollments`` positionally and asserting each link. Until this guard existed the
zip had no ``strict=`` and no length check, so a shorter or empty list made
``zip()`` stop at the shortest sequence: the loop body never executed, and the
check immediately after the loop still appended ``status: "pass"``.

That is the worst kind of failure for an evidence-producing gate. The published
report from a verification that checked zero records is indistinguishable from
one that checked all of them, so a silently truncated restore would have been
recorded as proven. These tests pin the guard, including the vacuous-pass case
that ``strict=True`` alone would not have caught.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "tools" / "foundation" / "runtime_restore.py"


def load_helper():
    """Import the module without executing main() - it needs no Frappe at import."""
    spec = importlib.util.spec_from_file_location("foundation_runtime_restore", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helper = load_helper()


class PositionalRecordGuardTests(unittest.TestCase):
    def test_matching_non_empty_lists_return_the_record_count(self):
        expected = {"students": ["S1", "S2", "S3"],
                    "applicants": ["A1", "A2", "A3"],
                    "enrollments": ["E1", "E2", "E3"]}
        self.assertEqual(helper.positional_record_count(expected), 3)

    def test_a_single_record_is_accepted(self):
        expected = {"students": ["S1"], "applicants": ["A1"], "enrollments": ["E1"]}
        self.assertEqual(helper.positional_record_count(expected), 1)

    def test_disagreeing_lengths_are_rejected(self):
        for lengths in ((3, 3, 2), (3, 2, 3), (2, 3, 3), (3, 1, 1), (1, 3, 3)):
            with self.subTest(lengths=lengths):
                expected = {"students": [f"S{i}" for i in range(lengths[0])],
                            "applicants": [f"A{i}" for i in range(lengths[1])],
                            "enrollments": [f"E{i}" for i in range(lengths[2])]}
                with self.assertRaises(AssertionError) as caught:
                    helper.positional_record_count(expected)
                self.assertIn("disagree in length", str(caught.exception))

    def test_all_empty_lists_are_rejected_rather_than_vacuously_passing(self):
        """The case strict=True alone would not catch: zip([], [], []) never raises."""
        expected = {"students": [], "applicants": [], "enrollments": []}
        with self.assertRaises(AssertionError) as caught:
            helper.positional_record_count(expected)
        self.assertIn("empty", str(caught.exception))
        # Confirm the premise: a bare strict zip over empty inputs is silent.
        self.assertEqual(list(zip([], [], [], strict=True)), [])

    def test_a_missing_list_is_treated_as_empty_and_rejected(self):
        for missing in helper.POSITIONAL_RECORD_LISTS:
            with self.subTest(missing=missing):
                expected = {name: ["X"] for name in helper.POSITIONAL_RECORD_LISTS}
                del expected[missing]
                with self.assertRaises(AssertionError):
                    helper.positional_record_count(expected)

    def test_a_null_list_is_treated_as_empty_and_rejected(self):
        expected = {"students": ["S1"], "applicants": None, "enrollments": ["E1"]}
        with self.assertRaises(AssertionError):
            helper.positional_record_count(expected)

    def test_the_error_names_the_offending_counts(self):
        """The message has to be diagnosable from the published report alone."""
        expected = {"students": ["S1", "S2"], "applicants": ["A1"], "enrollments": ["E1", "E2"]}
        with self.assertRaises(AssertionError) as caught:
            helper.positional_record_count(expected)
        message = str(caught.exception)
        for name in helper.POSITIONAL_RECORD_LISTS:
            self.assertIn(name, message)
        self.assertIn('"students": 2', message)
        self.assertIn('"applicants": 1', message)


class RestoreVerificationContractTests(unittest.TestCase):
    """The call site must actually use the guard and a strict zip."""

    def setUp(self):
        self.source = HELPER_PATH.read_text(encoding="utf-8")

    def test_the_record_loop_uses_a_strict_zip(self):
        self.assertIn('zip(expected["students"], expected["applicants"],\n'
                      '                                                  expected["enrollments"], strict=True)',
                      self.source,
                      "the positional record loop lost strict=True and can truncate silently")

    def test_the_guard_runs_before_the_record_loop(self):
        """Match the *call*, not the def: `positional_record_count(expected)` also
        appears in the signature, and indexing the first occurrence would make this
        assertion true no matter where the call sat."""
        call = self.source.index("= positional_record_count(expected)")
        loop = self.source.index('zip(expected["students"]')
        self.assertLess(call, loop, "the guard must run before the loop it protects")
        # And it must be reached at all, not merely defined.
        self.assertIn("expected_records = positional_record_count(expected)", self.source)

    def test_the_verified_count_is_reconciled_and_published(self):
        self.assertIn("verified_records += 1", self.source)
        self.assertIn("assert verified_records == expected_records", self.source)
        self.assertIn('"records_verified": verified_records', self.source,
                      "the evidence must say how many records were verified")

    def test_the_module_stays_importable_without_frappe(self):
        """The guard is only useful if it can be tested off-runner."""
        self.assertNotIn("frappe", self.source.split("def main()")[0],
                         "a module-level Frappe dependency would make the guard untestable")
        self.assertTrue(hasattr(helper, "positional_record_count"))


if __name__ == "__main__":
    unittest.main()
