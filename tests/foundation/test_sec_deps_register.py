"""The readable SEC-DEPS-01 register must equal the retained finding set exactly.

Readability enrichment may transcribe public advisory detail, but it may
neither invent a finding nor drop one: the PyPI record ids and npm advisory
ids must match the retained resolved-stack evidence one-for-one. The committed
JSON must also equal a fresh generator build, so it cannot drift by hand-edit.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RETAINED = ROOT / "docs/engineering/evidence/phase-2/resolved-stack-advisory-2026-09-16.json"
REGISTER = ROOT / "docs/engineering/evidence/sec-deps-01/readable-register-2026-09-19.json"

spec = importlib.util.spec_from_file_location(
    "sec_deps_register", ROOT / "tools/foundation/sec_deps_register.py")
register_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(register_tool)


class SecDepsRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retained = json.loads(RETAINED.read_text(encoding="utf-8"))
        cls.register = json.loads(REGISTER.read_text(encoding="utf-8"))

    def test_pypi_record_set_matches_retained_evidence_exactly(self):
        retained_ids = sorted(entry["id"] for entry in self.retained["pypi_osv_findings"])
        register_ids = sorted(record for vuln in self.register["pypi_vulnerabilities"]
                              for record in vuln["records"])
        self.assertEqual(register_ids, retained_ids)
        self.assertEqual(len(register_ids), 14)

    def test_npm_advisory_set_matches_retained_evidence_exactly(self):
        retained_ids = sorted(entry["id"] for entry in self.retained["npm_findings"])
        register_ids = sorted(advisory["id"]
                              for package in self.register["npm_rollup_by_package"]
                              for advisory in package["advisories"])
        self.assertEqual(register_ids, retained_ids)
        self.assertEqual(len(register_ids), 97)

    def test_enrichment_covers_each_retained_pypi_package_and_version(self):
        for entry in self.retained["pypi_osv_findings"]:
            vuln = next(item for item in self.register["pypi_vulnerabilities"]
                        if entry["id"] in item["records"])
            self.assertEqual(vuln["package"], entry["package"])
            self.assertEqual(vuln["installed_version"], entry["version"])

    def test_every_pypi_vulnerability_is_fully_readable(self):
        for vuln in self.register["pypi_vulnerabilities"]:
            for field in ("summary", "severity", "cvss", "cve", "fix_status",
                          "detail", "deployment_note"):
                self.assertTrue(vuln[field], f"{vuln['vuln_key']}.{field} is empty")
            self.assertTrue(vuln["records"], vuln["vuln_key"])
            self.assertTrue(vuln["cwe"], vuln["vuln_key"])
            self.assertEqual(len(vuln["osv_urls"]), len(vuln["records"]))
            if vuln["fixed_version"] is None:
                self.assertIn("NO FIX", vuln["fix_status"].upper(),
                              f"{vuln['vuln_key']} hides an unfixed state")

    def test_counts_match_the_retained_evidence(self):
        counts = self.register["counts"]
        self.assertEqual(counts["pypi_records"], 14)
        self.assertEqual(counts["pypi_unique_vulnerabilities"], 7)
        self.assertEqual(counts["pypi_packages"], 4)
        self.assertEqual(counts["npm_entries"], 97)
        self.assertEqual(counts["npm_packages"], 36)
        self.assertEqual(counts["npm_severity"],
                         {"moderate": 39, "low": 7, "high": 49, "critical": 2})

    def test_provenance_pins_the_retained_source(self):
        source = self.register["finding_source"]
        actual = hashlib.sha256(RETAINED.read_bytes()).hexdigest()
        self.assertEqual(source["retained_sha256"], actual)
        self.assertEqual(source["hosted_run"], "35084695840")
        self.assertEqual(source["hosted_check"], "104762158723")
        self.assertEqual(source["hosted_commit"], "955e4cd5eedc34b90f4fbfce047339e18558f1f2")

    def test_committed_register_equals_a_fresh_build(self):
        fresh = register_tool.build_register(self.retained)
        self.assertEqual(self.register, fresh)

    def test_register_disclaims_any_gate_change(self):
        effect = self.register["gate_effect"]
        self.assertIn("UPSTREAM-BLOCKED / REJECT", effect)
        self.assertIn("NOT established", effect)


if __name__ == "__main__":
    unittest.main()
