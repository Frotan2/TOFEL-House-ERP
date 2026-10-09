"""SEC-DEPS-01 regression checks for the 2026-10-09 advisory delta.

The delta closes the eight matches that failed the STACK-ADVISORY-UNTRIAGED gate
(seven unique advisories). These tests keep that closure honest:

* the delta resolves exactly the reported untriaged set, through the same loader
  the gate uses, and every closed disposition carries evidence and a fix path;
* the offline replay snapshot (npm bulk + PyPI per-release data, captured
  2026-10-09) evaluates to zero untriaged findings under the current loader and
  its counts are self-consistent;
* the upgrade-blocker evidence stays bound to the pinned Frappe pyproject hash in
  the version matrix, so a pin change forces re-triage;
* the Ghostscript guard that closes the WeasyPrint RCE precondition is present
  after the last install step and its shell logic is executed here.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
import advisory_triage as t  # noqa: E402

DELTA_DIR = ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-09"
DELTA = json.loads((DELTA_DIR / "delta-dispositions.json").read_text())
SNAPSHOT = json.loads((DELTA_DIR / "replay-snapshot.json").read_text())
MATRIX = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
DOCKERFILE = (ROOT / "product" / "app.Dockerfile").read_text()
PINS = (DELTA_DIR / "python-pins-replay.txt").read_text()

DELTA_NAME = "advisory-delta-2026-10-09"
CLOSED = {"MITIGATED", "NOT_REACHABLE", "BUILD_ONLY", "DEV_ONLY", "INSTALL_ONLY", "BROWSER_SELF_DENIAL"}

# The eight matches the Foundation runtime gate reported as untriaged (run 37902411810).
CI_UNTRIAGED = [
    ("py:pyjwt", "GHSA-x33g-cr3x-6449"),
    ("py:pyjwt", "PYSEC-2026-4183"),
    ("py:weasyprint", "GHSA-r543-q48m-4c9j"),
    ("py:werkzeug", "GHSA-g6x2-hccm-hh4m"),
    ("npm:@vue/server-renderer", "1241259"),
    ("npm:postcss-selector-parser", "1241232"),
    ("npm:prosemirror-view", "1241270"),
    ("npm:source-map-js", "1241209"),
]
UNIQUE_DELTA_ADVISORIES = {
    "GHSA-x33g-cr3x-6449", "GHSA-r543-q48m-4c9j", "GHSA-g6x2-hccm-hh4m", "GHSA-g2v6-rqmx-r4w6",
    "GHSA-rj75-hqrm-r3gf", "GHSA-c8x8-7fp4-3x9w", "GHSA-68fv-2mgg-jv7q",
}


def _delta_records():
    for pkg in DELTA["packages"]:
        for adv in pkg["advisories"]:
            yield pkg["package"], adv


class DeltaCoverageTests(unittest.TestCase):
    def setUp(self):
        self.triage = t.load_triage()

    def test_loader_loads_this_delta(self):
        self.assertIn(DELTA_NAME, self.triage["deltas"])

    def test_delta_resolves_exact_ci_untriaged_set_to_closed_dispositions(self):
        for package, identifier in CI_UNTRIAGED:
            with self.subTest(package=package, identifier=identifier):
                record = self.triage["by_id"].get(t._norm(identifier))
                self.assertIsNotNone(record, f"{identifier} not covered by any triage source")
                self.assertEqual(record.get("source_delta"), DELTA_NAME,
                                 f"{identifier} must be covered by this delta, not an earlier source")
                self.assertIn(record["runtime_disposition"], CLOSED)

    def test_delta_holds_exactly_the_seven_unique_advisories(self):
        ids = {adv["id"] for _pkg, adv in _delta_records()}
        self.assertEqual(ids, UNIQUE_DELTA_ADVISORIES)

    def test_every_delta_advisory_has_evidence_and_fix_path(self):
        for package, adv in _delta_records():
            with self.subTest(package=package, advisory=adv["id"]):
                self.assertIn(adv["runtime_disposition"], CLOSED)
                self.assertGreaterEqual(len(adv["runtime_disposition_evidence"]), 300)
                self.assertGreaterEqual(len(adv["fix_path"]), 80)
                self.assertRegex(adv["published"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
                self.assertTrue(adv["first_patched"])
                self.assertIn(adv["severity"], {"critical", "high", "medium", "moderate", "low"})

    def test_delta_contains_no_suppression_states(self):
        for package, adv in _delta_records():
            with self.subTest(package=package, advisory=adv["id"]):
                self.assertNotIn(adv["runtime_disposition"], {"OWNER_DECISION_REQUIRED", "BLOCKED", "ACCEPTED", "IGNORED"})


class ReplaySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.triage = t.load_triage()

    def test_replay_has_zero_untriaged_under_current_loader(self):
        npm_input = {}
        for entry in SNAPSHOT["npm_entries"]:
            url = f"https://github.com/advisories/{entry['ghsa']}" if entry["ghsa"] else ""
            npm_input.setdefault(entry["package"], []).append(
                {"id": entry["numeric_id"], "url": url, "title": entry["title"], "severity": entry["severity"]})
        npm_result = t.triage_npm(npm_input, self.triage)
        self.assertEqual(len(npm_result["findings"]), len(SNAPSHOT["npm_entries"]))
        self.assertEqual(npm_result["untriaged"], [])
        self.assertEqual(npm_result["open"], 0)

        py_findings = []
        for record in SNAPSHOT["pypi_records"]:
            py_findings.append({"package": {"ecosystem": "PyPI", "name": record["package"]},
                                "version": record["version"], "id": record["id"], "aliases": record["aliases"]})
        py_result = t.triage_python(py_findings, self.triage)
        self.assertEqual(len(py_result["findings"]), len(SNAPSHOT["pypi_records"]))
        self.assertEqual(py_result["untriaged"], [])
        self.assertEqual(py_result["open"], 0)

    def test_replay_counts_are_self_consistent(self):
        npm_entries = SNAPSHOT["npm_entries"]
        counts = SNAPSHOT["counts"]
        self.assertEqual(counts["npm_bulk_entries_raw"], len(npm_entries))
        self.assertEqual(counts["groups_npm_packages"], len({e["package"] for e in npm_entries}))
        self.assertEqual(counts["groups_npm_packages"], 40)
        self.assertEqual(counts["npm_unique_ghsa_ids"], len({e["ghsa"] for e in npm_entries if e["ghsa"]}))
        self.assertEqual(counts["npm_unique_ghsa_ids"], 91)
        self.assertEqual(counts["pypi_records_raw"], len(SNAPSHOT["pypi_records"]))
        self.assertEqual(counts["pypi_records_raw"], 62)
        self.assertEqual(counts["groups_python_package_versions"], 7)
        self.assertEqual(counts["ci_reported_matches"], 160)
        self.assertEqual(counts["ci_reported_groups"], 47)
        self.assertEqual(counts["groups_npm_packages"] + counts["groups_python_package_versions"], counts["ci_reported_groups"])

    def test_python_unique_advisories_by_alias_closure(self):
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for record in SNAPSHOT["pypi_records"]:
            ids = [record["id"]] + list(record["aliases"])
            for other in ids[1:]:
                parent[find(ids[0])] = find(other)
            find(ids[0])
        clusters = {find(x) for x in parent}
        self.assertEqual(len(clusters), SNAPSHOT["counts"]["python_unique_advisories_alias_merged"])
        self.assertEqual(len(clusters), 32)

    def test_snapshot_pins_the_annotated_python_versions(self):
        for pin in ("oauthlib==3.3.1", "pdfkit==1.0.0", "pypdf==6.15.0", "pyjwt==2.13.0",
                    "setuptools==80.9.0", "weasyprint==68.0", "werkzeug==3.1.6"):
            with self.subTest(pin=pin):
                self.assertRegex(PINS, rf"(?m)^{re.escape(pin)}$")


class UpgradeBlockerTests(unittest.TestCase):
    def test_blockers_are_bound_to_the_matrix_frappe_pyproject_hash(self):
        frappe = [c for c in MATRIX["components"] if c["name"] == "frappe"][0]
        self.assertEqual(DELTA["pinned_upstream_evidence"]["frappe_pyproject_sha256"],
                         frappe["source_file_sha256"]["pyproject.toml"],
                         "Frappe pins changed: re-triage the upgrade-blocked advisories in this delta")
        self.assertEqual(DELTA["pinned_upstream_evidence"]["frappe_commit"], frappe["commit"])

    def test_python_blockers_are_incompatible_with_frappe_pins(self):
        blockers = {b["package"]: b for b in DELTA["upgrade_blockers"]}
        for name in ("pyjwt", "werkzeug", "weasyprint"):
            with self.subTest(package=name):
                self.assertFalse(blockers[name]["compatible"])
                self.assertIn("frappe@", blockers[name]["declared_by"].lower())


class GhostscriptGuardTests(unittest.TestCase):
    GUARD_PREFIX = "RUN if command -v gs"

    def _guard_line(self):
        lines = [ln for ln in DOCKERFILE.splitlines() if ln.startswith(self.GUARD_PREFIX)]
        self.assertEqual(len(lines), 1, "exactly one Ghostscript guard RUN must exist")
        return lines[0]

    def test_guard_follows_last_install_step_and_precedes_env(self):
        guard_at = DOCKERFILE.index(self._guard_line())
        last_install = DOCKERFILE.index("bench get-app --skip-assets /build/owned/toefl_house")
        env_at = DOCKERFILE.index("ENV BENCH_DIR=")
        self.assertLess(last_install, guard_at)
        self.assertLess(guard_at, env_at)

    def test_no_dockerfile_line_installs_ghostscript(self):
        for line in DOCKERFILE.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "apt-get" in line or "apt " in line:
                self.assertNotIn("ghostscript", line.lower())

    def test_guard_command_passes_without_gs_and_fails_with_gs(self):
        command = self._guard_line()[len("RUN "):]
        with tempfile.TemporaryDirectory() as empty_dir:
            clean = subprocess.run(["/bin/sh", "-c", command], env={"PATH": empty_dir},
                                   capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stderr)
        with tempfile.TemporaryDirectory() as stub_dir:
            stub = Path(stub_dir) / "gs"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            present = subprocess.run(["/bin/sh", "-c", command], env={"PATH": stub_dir},
                                     capture_output=True, text=True)
            self.assertEqual(present.returncode, 1)
            self.assertIn("GHSA-r543-q48m-4c9j", present.stderr)


class WeasyPrintOverrideWiringTests(unittest.TestCase):
    """Static checks for the WeasyPrint whitelist override that the 2026-09-23
    register cites for its MITIGATED WeasyPrint dispositions. The register's
    cited test file does not exist on main; these checks keep the mechanism
    itself from silently changing. They do not prove the override covers every
    call path (printview and attach_print call the vendor code directly)."""

    def setUp(self):
        self.hooks = (ROOT / "apps/toefl_house/toefl_house/hooks.py").read_text()
        self.printing = (ROOT / "apps/toefl_house/toefl_house/printing.py").read_text()

    def test_whitelisted_weasyprint_methods_are_overridden(self):
        self.assertIn('"frappe.utils.weasyprint.download_pdf": "toefl_house.printing.download_pdf"', self.hooks)
        self.assertIn('"frappe.utils.weasyprint.get_html": "toefl_house.printing.get_html"', self.hooks)

    def test_override_gate_requires_beta_flag_and_print_permission(self):
        self.assertIn('doctype != "Print Format"', self.printing)
        self.assertIn('doc.check_permission("print")', self.printing)
        self.assertIn('getattr(doc, "print_format_builder_beta", False)', self.printing)


if __name__ == "__main__":
    unittest.main()
