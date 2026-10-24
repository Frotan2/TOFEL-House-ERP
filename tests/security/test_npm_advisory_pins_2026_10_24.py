"""npm advisory pin regression for the 2026-10-24 Foundation failure (Issues #41/#38).

The seven untriaged npm findings from Foundation run 40074521329 are removed by
upgrading the installed HRMS frontend copies, not by triage labels:

- fast-uri 3.1.8 -> 3.1.9  (npm 1243098/1243101/1243104/1243107)
- serialize-javascript 7.1.2 -> 7.1.3  (npm 1243082)
- undici 6.29.0 -> 6.29.1  (npm 1243079/1243114)

The live end-to-end npm audit evidence lives in
docs/engineering/evidence/sec-deps-01/npm-advisory-remediation-2026-10-24/.
These offline contracts keep the reviewed overlay from silently regressing and
keep every installed copy on the patched release.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "tools" / "foundation" / "hrms-locks"
EVIDENCE = ROOT / "docs" / "engineering" / "evidence" / "sec-deps-01" / "npm-advisory-remediation-2026-10-24"

# package -> (vulnerable installed version, patched resolution, seven npm advisory ids)
PATCHED = {
    "fast-uri": ("3.1.8", "3.1.9", (1243098, 1243101, 1243104, 1243107)),
    "serialize-javascript": ("7.1.2", "7.1.3", (1243082,)),
    "undici": ("6.29.0", "6.29.1", (1243079, 1243114)),
}


class NpmAdvisoryPinTests(unittest.TestCase):
    def test_frontend_resolutions_pin_the_patched_releases(self):
        package = json.loads((LOCKS / "frontend" / "package.json").read_text(encoding="utf-8"))
        for name, (_vulnerable, patched, _ids) in PATCHED.items():
            with self.subTest(package=name):
                self.assertEqual(package["resolutions"][name], patched)

    def test_frontend_lock_resolves_every_consumer_to_the_patched_release(self):
        lock = (LOCKS / "frontend" / "yarn.lock").read_text(encoding="utf-8")
        expected_keys = {
            "fast-uri": "fast-uri@3.1.9, fast-uri@^3.0.1:",
            "serialize-javascript": "serialize-javascript@7.1.3, serialize-javascript@^7.0.3:",
            # The five Firebase packages exact-pin undici 6.19.7; the resolution must coalesce them onto 6.29.1.
            "undici": "undici@6.19.7, undici@6.29.1:",
        }
        for name, (_vulnerable, patched, _ids) in PATCHED.items():
            with self.subTest(package=name):
                self.assertIn(expected_keys[name], lock)
                header = lock.split(expected_keys[name], 1)[1].split("\n\n", 1)[0]
                self.assertIn(f'version "{patched}"', header)
                self.assertIn(f"registry.npmjs.org/{name}/-/{name}-{patched}.tgz", header)
                self.assertNotIn(f'version "{PATCHED[name][0]}"', lock)

    def test_no_vulnerable_copy_remains_in_any_reviewed_lock_overlay(self):
        overlays = [
            LOCKS / "frontend" / "yarn.lock",
            LOCKS / "roster" / "yarn.lock",
            ROOT / "tools" / "foundation" / "education-locks" / "frontend" / "yarn.lock",
            ROOT / "tools" / "foundation" / "banking-locks" / "banking" / "yarn.lock",
            ROOT / "tools" / "foundation" / "realtime-locks" / "yarn.lock",
        ]
        for name, (vulnerable, patched, _ids) in PATCHED.items():
            # Exact registry path segment, so "undici" cannot match the separate undici-types package.
            package_marker = f"/{name}/-/{name}-"
            for overlay in overlays:
                with self.subTest(package=name, overlay=overlay.name):
                    text = overlay.read_text(encoding="utf-8")
                    self.assertNotIn(package_marker + vulnerable + ".tgz", text)
                    if package_marker in text:
                        self.assertIn(package_marker + patched + ".tgz", text)

    def test_roster_overlay_has_no_resolution_for_these_packages(self):
        roster = json.loads((LOCKS / "roster" / "package.json").read_text(encoding="utf-8"))
        for name in PATCHED:
            self.assertNotIn(name, roster.get("resolutions", {}))

    def test_manifest_hashes_match_and_purpose_documents_the_finding_ids(self):
        manifest = json.loads((LOCKS / "manifest.json").read_text(encoding="utf-8"))
        for relative in ("frontend/package.json", "frontend/yarn.lock"):
            digest = hashlib.sha256((LOCKS / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, manifest["files"][relative]["security_sha256"])
        purpose = manifest["purpose"]
        for npm_id in (1243098, 1243101, 1243104, 1243107, 1243082, 1243079, 1243114):
            self.assertIn(str(npm_id), purpose)
        for ghsa in ("GHSA-w74x-v6f9-j3xg", "GHSA-xhq7-xmqj-769h", "GHSA-wjr9-j795-jxcr",
                     "GHSA-333x-w4r6-6crp", "GHSA-m5mm-p8h7-m29v", "GHSA-4qv8-2p9j-2685",
                     "GHSA-xjj6-f33q-929c"):
            self.assertIn(ghsa, purpose)

    def test_evidence_records_exactly_the_seven_removed_findings_and_no_new_ones(self):
        before_after = json.loads((EVIDENCE / "before-after-audit.json").read_text(encoding="utf-8"))
        removed = {tuple(row) for row in before_after["removed_findings"]}
        expected = {(name, npm_id) for name, (_v, _p, ids) in PATCHED.items() for npm_id in ids}
        self.assertEqual(removed, expected)
        self.assertEqual(before_after["added_findings"], [])
        self.assertEqual(before_after["baseline_versions"],
                         {name: [vulnerable] for name, (vulnerable, _p, _ids) in PATCHED.items()})
        self.assertEqual(before_after["patched_versions"],
                         {name: [patched] for name, (_v, patched, _ids) in PATCHED.items()})
        self.assertEqual(before_after["baseline_triage"]["untriaged"], 7)
        self.assertEqual(before_after["patched_triage"]["untriaged"], 0)
        self.assertEqual(before_after["patched_triage"]["open"], 0)

    def test_npm_bulk_evidence_ranges_are_cleared_by_the_pins(self):
        bulk = json.loads((EVIDENCE / "npm-advisory-bulk-vulnerable-versions.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(bulk), sorted(PATCHED))
        for name, (_vulnerable, patched, ids) in PATCHED.items():
            with self.subTest(package=name):
                advisory_ids = {entry["id"] for entry in bulk[name]}
                self.assertEqual(advisory_ids, set(ids))
                # Every recorded vulnerable range excludes the pinned release (upper bound is the patch).
                for entry in bulk[name]:
                    self.assertTrue(entry["vulnerable_versions"].endswith(f"<{patched}"), entry)

    def test_patched_tree_audit_evidence_is_clean_for_the_three_packages(self):
        audit = json.loads((EVIDENCE / "patched-tree-audit.json").read_text(encoding="utf-8"))
        inventory = audit["inventory"]
        for name, (_vulnerable, patched, _ids) in PATCHED.items():
            self.assertEqual(inventory[name], [patched])
        raw = audit["npm_raw"]
        for name in PATCHED:
            self.assertNotIn(name, raw)
        self.assertEqual(audit["triage"]["untriaged"], [])
        self.assertEqual(audit["triage"]["open"], 0)


if __name__ == "__main__":
    unittest.main()
