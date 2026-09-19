"""Bind the §5-verified headline counts to the committed evidence archives.

Every number the D8 matrix and the 09-17 closure cite from the
reconciliation runs must stay re-observable from files in this repository.
If an archive is edited, these tests name the broken claim.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs/engineering/evidence/production-like-execution"


def archive(name):
    return json.loads((EV / name).read_text(encoding="utf-8"))


def passed_of(report, key="checks"):
    entries = report[key]
    return sum(1 for x in entries if x.get("status") == "pass"), len(entries)


class EvidenceArchiveTests(unittest.TestCase):
    def test_archives_carry_verifiable_provenance(self):
        for name in (
            "checks-api-105208726304-placement-native.json",
            "checks-api-105208729385-placement-runner.json",
            "checks-api-105205384326-runner-evidence.json",
            "checks-api-105205441744-frontend-evidence.json",
            "checks-api-105222593207-runtime-evidence.json",
            "checks-api-105222597982-remaining-gates.json",
            "checks-api-105193158969-recovery-target.json",
            "checks-api-105191267035-durability.json",
            "checks-api-105191973507-tls-edge.json",
        ):
            with self.subTest(name=name):
                prov = archive(name)["retrieval_provenance"]
                self.assertTrue(prov["digest_verified"], name)
                self.assertEqual(prov["retrieved_at_utc"][:10], "2026-09-19")

    def test_key_operator_archive_states_its_digest_limitation(self):
        prov = archive("checks-api-105215912617-key-operator.json")["retrieval_provenance"]
        self.assertFalse(prov["digest_verified"])
        self.assertIn("parse_note", prov)
        self.assertIn("original_transport_text",
                      archive("checks-api-105215912617-key-operator.json"))

    def test_placement_counts(self):
        native = archive("checks-api-105208726304-placement-native.json")["report"]
        self.assertEqual(passed_of(native), (542, 542))
        runner = archive("checks-api-105208729385-placement-runner.json")["report"]
        entries = runner["checks"]
        self.assertEqual(len(entries), 101)
        self.assertTrue(all(x["exit_code"] == 0 for x in entries))

    def test_runtime_is_119_of_121_with_only_the_audit_checks_failing(self):
        report = archive("checks-api-105222593207-runtime-evidence.json")["report"]
        self.assertEqual(passed_of(report), (119, 121))
        failed = sorted(x["name"] for x in report["checks"] if x.get("status") != "pass")
        self.assertEqual(failed, ["hosted-frontend-advisory-audit",
                                  "hosted-full-stack-dependency-audit"])

    def test_remaining_gate_sections(self):
        report = archive("checks-api-105222597982-remaining-gates.json")["report"]
        for section, want in (("realtime", (4, 4)), ("guardian_browser", (6, 6)),
                              ("upgrade", (33, 33)), ("readiness", (54, 54))):
            with self.subTest(section=section):
                self.assertEqual(passed_of(report[section]), want)

    def test_recovery_durability_tls_and_runner_counts(self):
        self.assertEqual(passed_of(
            archive("checks-api-105193158969-recovery-target.json")["report"]), (31, 31))
        self.assertEqual(passed_of(
            archive("checks-api-105191267035-durability.json")["report"]), (20, 20))
        self.assertEqual(passed_of(
            archive("checks-api-105191973507-tls-edge.json")["report"]), (38, 38))
        self.assertEqual(passed_of(
            archive("checks-api-105205384326-runner-evidence.json")["report"]), (18, 18))

    def test_frontend_advisory_finding(self):
        report = archive("checks-api-105205441744-frontend-evidence.json")["report"]
        self.assertEqual(passed_of(report), (20, 22))
        failed = [x for x in report["checks"] if x.get("status") != "pass"]
        self.assertEqual(len(failed), 2)
        self.assertTrue(all(x["exit_code"] == 1 for x in failed))
        self.assertFalse(report["production_pins_changed"])
        self.assertEqual(len(report["introduced_advisories"]), 1)
        self.assertEqual(len(report["removed_advisories"]), 35)

    def test_key_operator_infrastructure_failure_content(self):
        report = archive("checks-api-105215912617-key-operator.json")["report"]
        self.assertEqual(passed_of(report), (18, 19))
        failed = [x for x in report["checks"] if x.get("status") != "pass"]
        self.assertEqual([(x["name"], x["exit_code"]) for x in failed],
                         [("bench-init", 167)])
        self.assertIn("503", failed[0]["output_tail"])
        retrieved = report["key_retrieval"]["retrieved"]
        matched = [k for k, v in retrieved.items()
                   if isinstance(v, dict) and v.get("matches_custody_manifest") is True]
        self.assertEqual(len(matched), 4)
        for key in matched:
            self.assertTrue(retrieved[key]["native_fernet_format"]["valid"])
        self.assertIn("channel_a_alone", json.dumps(report["custody_negative_controls_before_use"]))
