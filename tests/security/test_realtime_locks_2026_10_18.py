"""Frappe realtime (Socket.IO) lock overlay: content, fail-closed checks, and wiring.

Advisories covered by the overlay (see tools/foundation/realtime-locks/manifest.json):
ws 8.11.0 (GHSA-3h5v, GHSA-96hv, GHSA-58qx), socket.io-parser 4.2.4 (GHSA-2m8v,
GHSA-677m), engine.io 6.5.4 (GHSA-gr94, GHSA-r635). Every test here uses synthetic
trees under a temp directory. No network, no real site, no credentials.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.foundation import secure_realtime

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "tools/foundation/realtime-locks"
MANIFEST = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
FIXED = {"engine.io": (6, 6, 7), "ws": (8, 21, 0), "socket.io-parser": (4, 2, 7)}


def _tuple(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lock_entries(text: str) -> list[tuple[str, str]]:
    """(header, version) pairs from a Yarn v1 lockfile."""
    out = []
    for block in re.split(r"\n\n+", text):
        lines = block.strip("\n").splitlines()
        if not lines or lines[0].startswith((" ", "#")) or not lines[0].endswith(":"):
            continue
        version = next((re.match(r'\s+version "([^"]+)"', line).group(1)
                        for line in lines if re.match(r'\s+version "', line)), None)
        out.append((lines[0][:-1], version))
    return out


class OverlayContentTests(unittest.TestCase):
    def test_manifest_security_digests_match_overlay_files(self):
        for relative, hashes in MANIFEST["files"].items():
            self.assertEqual(_sha(OVERLAY / relative), hashes["security_sha256"], relative)

    def test_manifest_records_upstream_digests_and_blob_ids(self):
        for relative, hashes in MANIFEST["files"].items():
            self.assertRegex(hashes["upstream_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(hashes["upstream_git_blob"], r"^[0-9a-f]{40}$")
        self.assertEqual(MANIFEST["upstream_commit"], "988e54f3")
        self.assertEqual(MANIFEST["yarn_version"], "1.22.22")

    def test_package_json_pins_fixed_resolutions_and_socket_io_4_8(self):
        package = json.loads((OVERLAY / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["dependencies"]["socket.io"], "^4.8.4")
        self.assertEqual(package.get("resolutions"), {
            "engine.io": "6.6.11", "socket.io-parser": "4.2.7", "ws": "8.21.3"})
        for name, minimum in MANIFEST["fixed_minimums"].items():
            self.assertGreaterEqual(_tuple(package["resolutions"][name]), _tuple(minimum), name)

    def test_lockfile_resolves_only_fixed_realtime_versions(self):
        entries = _lock_entries((OVERLAY / "yarn.lock").read_text(encoding="utf-8"))
        versions: dict[str, set[str]] = {}
        for header, version in entries:
            name = header.split(", ")[0].strip('"')
            name = name[: name.rfind("@")] if name.rfind("@") > 0 else name
            if version:
                versions.setdefault(name, set()).add(version)
        for name, minimum in FIXED.items():
            self.assertTrue(versions.get(name), name + " missing from lock")
            for version in versions[name]:
                self.assertGreaterEqual(_tuple(version), minimum, f"{name} {version} is vulnerable")
        self.assertEqual(versions["socket.io"], {"4.8.4"})

    def test_lockfile_keeps_upstream_registry_host(self):
        text = (OVERLAY / "yarn.lock").read_text(encoding="utf-8")
        self.assertNotIn("registry.npmjs.org", text)
        self.assertIn("https://registry.yarnpkg.com/ws/-/ws-8.21.3.tgz", text)

class OverlayFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="realtime-test-"))
        self.frappe = self.tmp / "frappe"
        self.frappe.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.yarn = patch.object(secure_realtime.subprocess, "check_output", return_value="1.22.22\n")
        self.yarn.start()
        self.addCleanup(self.yarn.stop)

    def _write_upstream(self):
        upstream_pkg = b"upstream-package-placeholder\n"
        upstream_lock = b"upstream-lock-placeholder\n"
        (self.frappe / "package.json").write_bytes(upstream_pkg)
        (self.frappe / "yarn.lock").write_bytes(upstream_lock)
        return upstream_pkg, upstream_lock

    def test_unknown_upstream_bytes_are_refused_before_any_install(self):
        self._write_upstream()
        with patch.object(secure_realtime.subprocess, "run") as install:
            with self.assertRaisesRegex(ValueError, "drifted"):
                secure_realtime.security_lock_files(self.frappe)
            install.assert_not_called()

    def test_tampered_overlay_source_is_refused(self):
        tampered = self.tmp / "overlay"
        shutil.copytree(OVERLAY, tampered)
        (tampered / "yarn.lock").write_text((tampered / "yarn.lock").read_text() + "\n# x\n")
        with patch.object(secure_realtime, "ROOT", tampered):
            with patch.object(secure_realtime.subprocess, "run") as install:
                with self.assertRaisesRegex(ValueError, "integrity failure"):
                    secure_realtime.security_lock_files(self.frappe)
                install.assert_not_called()

    def test_verify_mode_refuses_missing_reviewed_files(self):
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            secure_realtime.security_lock_files(self.frappe, verify_only=True)

    def test_verify_mode_accepts_reviewed_files_and_refuses_when_no_install(self):
        for relative in ("package.json", "yarn.lock"):
            shutil.copyfile(OVERLAY / relative, self.frappe / relative)
        # The reviewed files match, so the drift gate passes; the missing node_modules must fail.
        with self.assertRaisesRegex(ValueError, "did not materialize"):
            secure_realtime.verify_installed_realtime(self.frappe)

    def _fake_package(self, base: Path, name: str, version: str):
        pkg = base / "node_modules" / name
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "package.json").write_text(json.dumps({"name": name, "version": version}))

    def test_installed_vulnerable_ws_is_refused(self):
        self._fake_package(self.frappe, "engine.io", "6.6.11")
        self._fake_package(self.frappe, "socket.io-parser", "4.2.7")
        self._fake_package(self.frappe, "ws", "8.11.0")
        with self.assertRaisesRegex(ValueError, "Vulnerable ws 8.11.0"):
            secure_realtime.verify_installed_realtime(self.frappe)

    def test_installed_vulnerable_engine_io_nested_copy_is_refused(self):
        self._fake_package(self.frappe, "engine.io", "6.6.11")
        self._fake_package(self.frappe, "socket.io-parser", "4.2.7")
        self._fake_package(self.frappe, "ws", "8.21.3")
        nested = self.frappe / "node_modules" / "some-client" / "node_modules" / "engine.io"
        nested.mkdir(parents=True)
        (nested / "package.json").write_text(json.dumps({"name": "engine.io", "version": "6.5.4"}))
        with self.assertRaisesRegex(ValueError, "Vulnerable engine.io 6.5.4"):
            secure_realtime.verify_installed_realtime(self.frappe)

    def test_fixture_copies_inside_other_packages_do_not_satisfy_the_gate(self):
        self._fake_package(self.frappe, "engine.io", "6.6.11")
        self._fake_package(self.frappe, "socket.io-parser", "4.2.7")
        self._fake_package(self.frappe, "ws", "8.21.3")
        fixture = self.frappe / "node_modules" / "other" / "test" / "fixtures" / "engine.io"
        fixture.mkdir(parents=True)
        (fixture / "package.json").write_text(json.dumps({"name": "engine.io", "version": "1.0.0"}))
        report = secure_realtime.verify_installed_realtime(self.frappe)
        self.assertEqual(report["installed"]["engine.io"], {"node_modules/engine.io/package.json": "6.6.11"})

    def test_all_fixed_copies_pass_and_report_versions(self):
        self._fake_package(self.frappe, "engine.io", "6.6.11")
        self._fake_package(self.frappe, "socket.io-parser", "4.2.7")
        self._fake_package(self.frappe, "ws", "8.21.3")
        report = secure_realtime.verify_installed_realtime(self.frappe)
        self.assertEqual(report["installed"]["ws"], {"node_modules/ws/package.json": "8.21.3"})
        self.assertEqual(report["fixed_minimums"]["ws"], "8.21.0")


class WiringTests(unittest.TestCase):
    def test_product_image_copies_and_applies_realtime_overlay_after_get_app(self):
        text = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY tools/foundation/secure_realtime.py /product/secure_realtime.py", text)
        self.assertIn("COPY tools/foundation/realtime-locks /product/realtime-locks", text)
        apply = text.index("RUN python3 /product/secure_realtime.py /home/frappe/bench/apps/frappe")
        self.assertLess(text.index("bench get-app --skip-assets"), apply)
        self.assertLess(text.index("secure_weasyprint.py /home/frappe/bench/apps/frappe"), apply)
        self.assertLess(apply, text.index("ENV BENCH_DIR=/home/frappe/bench"))

    def test_product_image_does_not_silently_apply_education_overlay(self):
        # Education has its own owner decision (separate from the realtime overlay).
        text = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("secure_education.py", text)

    def test_dockerignore_allowlists_realtime_overlay_inputs(self):
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for pattern in ("!tools/foundation/secure_realtime.py", "!tools/foundation/realtime-locks/",
                        "!tools/foundation/realtime-locks/**"):
            self.assertIn(pattern, text.splitlines())

    def test_native_installer_applies_before_build_and_verifies_after_build(self):
        text = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        apply = text.index('run("patch-frappe-realtime-dependencies"')
        self.assertLess(text.index('run("patch-education-frontend-dependencies"'), apply)
        self.assertLess(apply, text.index('bench("asset-build"'))
        verify = text.index('run("verify-frappe-realtime-after-build"')
        self.assertLess(text.index('bench("asset-build"'), verify)
        self.assertIn('"--verify"', text[verify:verify + 200])


if __name__ == "__main__":
    unittest.main()
