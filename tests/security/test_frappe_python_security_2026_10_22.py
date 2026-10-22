"""Regression guards for the reviewed Frappe Python security uplift (2026-10-22)."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/foundation"))
import secure_frappe_python as security  # noqa: E402


class FrappePythonSecurityOverlayUnitTests(unittest.TestCase):
    def test_reviewed_pyproject_changes_only_the_four_reviewed_requirements(self):
        source = (
            b'[project]\ndependencies = [\n'
            b'    "GitPython~=3.1.45",\n'
            b'    "Pillow~=12.3.0",\n'
            b'    "PyJWT~=2.13.0",\n'
            b'    "pypdf==6.15.0",\n'
            b']\n'
        )
        digest = hashlib.sha256(source).hexdigest()
        with patch.object(security, "PINNED_PYPROJECT_SHA256", digest):
            updated = security._reviewed_pyproject(source)
        self.assertEqual(
            updated,
            (
                b'[project]\ndependencies = [\n'
                b'    "GitPython~=3.2.1",\n'
                b'    "Pillow~=13.0.0",\n'
                b'    "PyJWT~=2.15.1",\n'
                b'    "pypdf==6.21.2",\n'
                b']\n'
            ),
        )

    def test_reviewed_pyproject_refuses_drift_and_duplicate_anchors(self):
        source = b'    "GitPython~=3.1.45",\n'
        with self.assertRaisesRegex(ValueError, "pyproject changed"):
            security._reviewed_pyproject(source)
        full = b"".join(old for old, _new in security.REQUIREMENT_UPGRADES)
        doubled = full + security.REQUIREMENT_UPGRADES[0][0]
        digest = hashlib.sha256(doubled).hexdigest()
        with patch.object(security, "PINNED_PYPROJECT_SHA256", digest):
            with self.assertRaisesRegex(ValueError, "exactly once"):
                security._reviewed_pyproject(doubled)

    def test_runtime_versions_are_exact_reviewed_releases(self):
        self.assertEqual(
            security.REQUIRED_RUNTIME_VERSIONS,
            {
                "GitPython": "3.2.1",
                "Pillow": "13.0.0",
                "PyJWT": "2.15.1",
                "pypdf": "6.21.2",
            },
        )


class FrappePythonSecurityOverlayWiringTests(unittest.TestCase):
    def test_all_three_install_paths_apply_install_refresh_and_verify(self):
        docker = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        foundation = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        native = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        for source in (docker, foundation, native):
            self.assertIn("secure_frappe_python.py", source)
            for package in (
                "GitPython==3.2.1",
                "Pillow==13.0.0",
                "PyJWT==2.15.1",
                "pypdf==6.21.2",
            ):
                self.assertIn(package, source)
            self.assertIn("--reinstall", source)
            self.assertIn("--editable", source)
            self.assertIn("--verify", source)

    def test_native_final_integrity_allows_only_reviewed_frappe_overlays(self):
        native = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        self.assertIn(
            "['frappe/utils/weasyprint.py', 'pyproject.toml']",
            native,
        )
        self.assertIn("verify-final-frappe-python-security", native)

    def test_product_image_contains_only_the_current_security_helper(self):
        docker = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(
            "COPY tools/foundation/secure_frappe_python.py /product/secure_frappe_python.py",
            docker,
        )
        self.assertIn("!tools/foundation/secure_frappe_python.py", ignore)
        self.assertNotIn("secure_pillow.py", docker)
        self.assertNotIn("secure_pillow.py", ignore)


if __name__ == "__main__":
    unittest.main()
