"""Final hosted acceptance report must not confuse CI success with release."""
import copy
import unittest

from tools.native.final_acceptance_report import (
    MIN_NATIVE_CHECKS, REQUIRED_JOURNEYS, verify_report,
)

COMMIT = "a" * 40


def synthetic_report():
    required = [n for values in REQUIRED_JOURNEYS.values() for n in values]
    checks = [{"name": n, "status": "pass"} for n in required]
    checks.extend(
        {"name": "synthetic-other-%04d" % i, "status": "pass"}
        for i in range(MIN_NATIVE_CHECKS - len(checks))
    )
    return dict(
        commit=COMMIT,
        status="pass",
        runtime_kind="Frappe/MariaDB/Redis/HTTP",
        production="REJECT",
        checks=checks,
    )


class FinalHostedAcceptanceTest(unittest.TestCase):
    def test_complete_synthetic_report_never_approves_real_operation(self):
        summary = verify_report(synthetic_report(), COMMIT)
        self.assertEqual(summary["native_checks_passed"], MIN_NATIVE_CHECKS)
        self.assertEqual(set(summary["journeys"]), set(REQUIRED_JOURNEYS))
        self.assertEqual(summary["production_authorization"], "REJECT")
        self.assertEqual(summary["real_owner_windows"], "NOT_VERIFIED")
        self.assertEqual(summary["owner_backup_restore"], "HOLD")

    def test_missing_journey_is_a_failure_even_when_all_other_checks_pass(self):
        evidence = synthetic_report()
        evidence["checks"][0]["name"] = "synthetic-replacement"
        with self.assertRaisesRegex(ValueError, "Missing executed placement journeys"):
            verify_report(evidence, COMMIT)

    def test_failed_check_is_not_masked_by_a_green_top_level(self):
        evidence = synthetic_report()
        evidence["checks"][10]["status"] = "fail"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            verify_report(evidence, COMMIT)

    def test_wrong_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "different commit"):
            verify_report(synthetic_report(), "b" * 40)

    def test_wrong_runtime_or_release_claim_rejected(self):
        for key, value in (
            ("runtime_kind", "static-tests-only"),
            ("production", "APPROVED"),
            ("status", "running"),
        ):
            evidence = synthetic_report()
            evidence[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_report(evidence, COMMIT)

    def test_duplicate_receipts_rejected(self):
        evidence = synthetic_report()
        evidence["checks"][1] = copy.deepcopy(evidence["checks"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify_report(evidence, COMMIT)

    def test_partial_report_rejected(self):
        evidence = synthetic_report()
        evidence["checks"] = evidence["checks"][:MIN_NATIVE_CHECKS - 1]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify_report(evidence, COMMIT)


if __name__ == "__main__":
    unittest.main()
