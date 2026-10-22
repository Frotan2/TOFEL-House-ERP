"""Regression guards for the Pillow 13 security uplift (2026-10-22)."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/foundation"))
import secure_pillow  # noqa: E402


class PillowOverlayUnitTests(unittest.TestCase):
    def test_reviewed_pyproject_changes_only_the_pillow_requirement(self):
        source = b'[project]\ndependencies = [\n    "Pillow~=12.3.0",\n]\n'
        digest = hashlib.sha256(source).hexdigest()
        with patch.object(secure_pillow, "PINNED_PYPROJECT_SHA256", digest):
            updated = secure_pillow._reviewed_pyproject(source)
        self.assertEqual(
            updated,
            b'[project]\ndependencies = [\n    "Pillow~=13.0.0",\n]\n',
        )

    def test_reviewed_pyproject_refuses_drift_and_duplicate_anchors(self):
        source = b'    "Pillow~=12.3.0",\n'
        with self.assertRaisesRegex(ValueError, "pyproject changed"):
            secure_pillow._reviewed_pyproject(source)
        doubled = source + source
        digest = hashlib.sha256(doubled).hexdigest()
        with patch.object(secure_pillow, "PINNED_PYPROJECT_SHA256", digest):
            with self.assertRaisesRegex(ValueError, "exactly once"):
                secure_pillow._reviewed_pyproject(doubled)


class PillowOverlayWiringTests(unittest.TestCase):
    def test_all_three_install_paths_apply_and_verify_the_overlay(self):
        docker = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        foundation = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        native = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        for source in (docker, foundation, native):
            self.assertIn("secure_pillow.py", source)
            self.assertIn("Pillow==13.0.0", source)
            self.assertIn("--reinstall", source)
            self.assertIn("--editable", source)
            self.assertIn("--verify", source)

    def test_native_final_integrity_allows_only_reviewed_frappe_overlays(self):
        native = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        self.assertIn(
            "['frappe/utils/weasyprint.py', 'pyproject.toml']",
            native,
        )

    def test_product_image_contains_the_security_helper(self):
        docker = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(
            "COPY tools/foundation/secure_pillow.py /product/secure_pillow.py",
            docker,
        )
        self.assertIn("!tools/foundation/secure_pillow.py", ignore)


if __name__ == "__main__":
    unittest.main()
