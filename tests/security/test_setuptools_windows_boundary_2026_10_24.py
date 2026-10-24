"""Regression for a narrowly scoped Windows-only setuptools advisory disposition."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from tools.foundation.advisory_triage import disposition_for_finding, load_triage
from tools.release.create_customer_package import ALLOWED_FILES


ROOT = Path(__file__).resolve().parents[2]
ADVISORY_ID = "GHSA-xmj3-9gf7-h52w"
DELTA = ROOT / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-24/delta-dispositions.json"


class SetuptoolsWindowsBoundaryTests(unittest.TestCase):
    def test_exact_advisory_scoped_to_linux_runtime(self):
        payload = json.loads(DELTA.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "sec-deps-01-advisory-delta/1")
        self.assertEqual(len(payload["packages"]), 1)
        entry = payload["packages"][0]
        self.assertEqual(entry["package"], "py:setuptools@80.9.0")
        self.assertEqual(len(entry["advisories"]), 1)
        self.assertEqual(entry["advisories"][0]["id"], ADVISORY_ID)
        self.assertEqual(entry["advisories"][0]["runtime_disposition"], "NOT_REACHABLE")
        found = disposition_for_finding(
            load_triage(), package="py:setuptools", advisories=[ADVISORY_ID])
        self.assertIsNotNone(found)
        self.assertEqual(found["runtime_disposition"], "NOT_REACHABLE")

    def test_shipped_python_image_is_linux_not_native_windows(self):
        dockerfile = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?m)^FROM python:\$\{PYTHON_VERSION\}-slim-bookworm AS product-base$")
        self.assertIn("FROM product-base AS runtime", dockerfile)
        # The Windows installer imports the Linux Docker archive; it does not
        # instantiate a host-side Python environment or run pip on Windows.
        windows = ROOT / "product/windows"
        installer = (windows / "Install TOEFL House ERP.cmd").read_text(encoding="utf-8")
        self.assertIn("docker load -i", installer)
        self.assertIn("docker compose up", installer)
        self.assertNotRegex(installer, re.compile(r"(?im)^\s*(?:python(?:\.exe)?|pip(?:\.exe)?|uv(?:\.exe)?)\b"))

    def test_customer_allowlist_contains_no_windows_python_payload(self):
        self.assertTrue(ALLOWED_FILES)
        for relative in ALLOWED_FILES:
            with self.subTest(relative=relative):
                self.assertNotIn(Path(relative).suffix.lower(), {".py", ".pyd", ".whl", ".exe", ".msi"})
                self.assertNotIn("python", Path(relative).name.lower())
                self.assertNotIn("setuptools", Path(relative).name.lower())
        self.assertIn("product/windows/Install TOEFL House ERP.cmd", ALLOWED_FILES)


if __name__ == "__main__":
    unittest.main()
