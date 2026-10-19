"""GHSA-vhrc-hgrq-x75r: Education frontend TipTap overlay, fail-closed checks, and wiring.

The Education frontend (frappe/education@93bc7075) pins frappe-ui 0.1.31, which
resolves @tiptap/* 2.2.3. @tiptap/extension-link < 2.10.4 is vulnerable. The
overlay pins every @tiptap/* package to 2.27.3 with a frozen lockfile.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.foundation import secure_education

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "tools/foundation/education-locks"
PATCHED = "2.27.3"
PATCHED_MINIMUM = (2, 10, 4)

# Upstream bytes at frappe/education@93bc7075, recorded when the overlay was made.
UPSTREAM_PACKAGE_SHA256 = "c44548c1e7e9f3b6c75209710d0e12018be3a00945167df8f70c45fd537e7cd9"
UPSTREAM_LOCK_SHA256 = "10618b30bd7dfd48d6fc5e85d56af3d07562c2c11f62efe0b746a8f95f328072"


# frappe/education@93bc7075 frontend/package.json, as parsed from the pinned bytes.
UPSTREAM_PACKAGE = {'name': 'frappe-ui-frontend',
 'private': True,
 'version': '0.0.0',
 'scripts': {'dev': 'vite',
             'build': 'vite build --base=/assets/education/frontend/ && yarn copy-html-entry',
             'preview': 'vite preview',
             'copy-html-entry': 'cp ../education/public/frontend/index.html '
                                '../education/www/edu-portal.html'},
 'dependencies': {'dayjs': '^1.11.10',
                  'feather-icons': '^4.28.0',
                  'frappe-ui': '^0.1.17',
                  'lucide-vue-next': '^0.259.0',
                  'pinia': '^2.1.7',
                  'qalendar': '^3.6.1',
                  'vue': '^3.2.25',
                  'tailwindcss': '^3.3.3',
                  'vue-router': '^4.0.12',
                  'vite': '^2.7.2',
                  '@vitejs/plugin-vue': '^2.0.0',
                  'autoprefixer': '^10.4.2',
                  'postcss': '^8.4.5'},
 'devDependencies': {'@vitejs/plugin-vue': '^2.0.0',
                     'autoprefixer': '^10.4.2',
                     'postcss': '^8.4.5',
                     'vite': '^2.7.2'}}

def _tuple(version: str) -> tuple:
    return tuple(int(part) for part in version.split("-", 1)[0].split("."))


class EducationOverlayIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_pins_upstream_commit_yarn_and_hashes(self):
        self.assertEqual(self.manifest["upstream_commit"], "93bc7075753369457919720690f80c6d2207b5f2")
        self.assertEqual(self.manifest["yarn_version"], "1.22.22")
        files = self.manifest["files"]
        self.assertEqual(set(files), {"frontend/package.json", "frontend/yarn.lock"})
        self.assertEqual(files["frontend/package.json"]["upstream_sha256"], UPSTREAM_PACKAGE_SHA256)
        self.assertEqual(files["frontend/yarn.lock"]["upstream_sha256"], UPSTREAM_LOCK_SHA256)

    def test_committed_overlay_bytes_match_security_hashes_and_are_lf(self):
        for relative, hashes in self.manifest["files"].items():
            data = (OVERLAY / relative).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), hashes["security_sha256"], relative)
            self.assertNotIn(b"\r", data, relative)

    def test_lock_resolves_only_registry_npmjs_urls(self):
        lock = (OVERLAY / "frontend/yarn.lock").read_text(encoding="utf-8")
        self.assertIn("# yarn lockfile v1", lock)
        resolved = [line.strip() for line in lock.splitlines() if line.strip().startswith("resolved ")]
        self.assertTrue(resolved)
        for line in resolved:
            self.assertTrue(line.startswith('resolved "https://registry.npmjs.org/'), line)


class EducationOverlayPinTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads((OVERLAY / "frontend/package.json").read_text(encoding="utf-8"))
        self.lock = (OVERLAY / "frontend/yarn.lock").read_text(encoding="utf-8")

    def _lock_tiptap_versions(self):
        """Map @tiptap/<name> -> set of resolved versions in the lock."""
        found = {}
        header = None
        for line in self.lock.splitlines():
            if line and not line.startswith((" ", "#")) and line.endswith(":"):
                header = line[:-1]
                continue
            match = re.match(r'^  version "([^"]+)"', line)
            if match and header:
                first = header.split(", ")[0].strip('"')
                if first.startswith("@tiptap/"):
                    name = "@" + first[1:].rsplit("@", 1)[0]
                    found.setdefault(name, set()).add(match.group(1))
        return found

    def test_every_tiptap_package_in_lock_is_pinned_to_patched_version(self):
        versions = self._lock_tiptap_versions()
        self.assertGreaterEqual(len(versions), 30)
        for name, found in versions.items():
            self.assertEqual(found, {PATCHED}, name)

    def test_resolutions_cover_every_tiptap_package_at_patched_version(self):
        names = set(self._lock_tiptap_versions())
        tiptap = {k: v for k, v in self.package["resolutions"].items() if k.startswith("@tiptap/")}
        self.assertEqual(set(tiptap), names)
        self.assertEqual(set(tiptap.values()), {PATCHED})

    def test_markdown_it_and_linkify_it_are_pinned_to_patched_versions(self):
        # 2026-10-18 advisories: markdown-it < 14.1.1 (GHSA-38c4-r59v-3vqw); markdown-it <= 14.1.1
        # (GHSA-6v5v-wf23-fmfq, first patched 14.2.0) and < 14.3.1 (GHSA-253c-mchw-3w2r, first patched 14.3.1);
        # linkify-it <= 5.0.1 (GHSA-22p9-wv53-3rq4) and <= 5.0.1 (GHSA-v245-v573-v5vm, first patched 5.0.2).
        # 14.3.3 is the newest 14.x and has no advisory on the GitHub Advisory API (affects=markdown-it@14.3.3).
        self.assertEqual(self.package["resolutions"]["markdown-it"], "14.3.3")
        self.assertEqual(self.package["resolutions"]["linkify-it"], "5.0.2")
        lock = (OVERLAY / "frontend/yarn.lock").read_text(encoding="utf-8")
        self.assertIn("markdown-it@14.3.3, markdown-it@^14.0.0:", lock)
        self.assertIn("linkify-it@5.0.2, linkify-it@^5.0.2:", lock)
        self.assertNotIn('version "14.1.1"', lock.split("markdown-it@14.3.3")[1].split("\n\n")[0])

    def test_socket_io_parser_and_ws_are_pinned_to_patched_versions(self):
        # 2026-10-19 advisories, verified on the GitHub Advisory API:
        # socket.io-parser < 4.2.7 (GHSA-2m8v-j782-fhvr, first patched 4.2.7; GHSA-677m-j7p3-52f9, 4.2.6);
        # ws < 8.21.0 (GHSA-96hv-2xvq-fx4p, 8.21.0), ws < 8.20.1 (GHSA-58qx-3vcg-4xpx), ws < 8.17.1 (GHSA-3h5v-q93c-6h6q).
        self.assertEqual(self.package["resolutions"]["socket.io-parser"], "4.2.7")
        self.assertEqual(self.package["resolutions"]["ws"], "8.21.3")
        lock = (OVERLAY / "frontend/yarn.lock").read_text(encoding="utf-8")
        self.assertIn("socket.io-parser@4.2.7, socket.io-parser@~4.2.4:", lock)
        self.assertIn("ws@8.21.3, ws@~8.11.0:", lock)
        self.assertNotIn('version "4.2.4"', lock.split("socket.io-parser@4.2.7")[1].split("\n\n")[0])
        self.assertNotIn('version "8.11.0"', lock.split("ws@8.21.3")[1].split("\n\n")[0])

    def test_patched_link_version_meets_advisory_minimum(self):
        self.assertGreaterEqual(_tuple(PATCHED), PATCHED_MINIMUM)
        self.assertEqual(self._lock_tiptap_versions()["@tiptap/extension-link"], {PATCHED})

    def test_overlay_differs_from_upstream_only_by_resolutions(self):
        overlay = dict(self.package)
        self.assertEqual(set(overlay.pop("resolutions")) & set(UPSTREAM_PACKAGE), set())
        self.assertEqual(overlay, UPSTREAM_PACKAGE)
        self.assertEqual(self.package["dependencies"]["frappe-ui"], "^0.1.17")


class EducationOverlayFailClosedTests(unittest.TestCase):
    def test_drifted_target_refuses_before_any_write_or_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            education = Path(tmp) / "education"
            (education / "frontend").mkdir(parents=True)
            (education / "frontend/package.json").write_text("unreviewed graph")
            (education / "frontend/yarn.lock").write_text("unreviewed lock")
            before = {p: p.read_bytes() for p in education.rglob("*") if p.is_file()}
            with patch.object(secure_education.subprocess, "check_output", return_value="1.22.22\n"), \
                    patch.object(secure_education.subprocess, "run") as install:
                with self.assertRaisesRegex(ValueError, "manifests drifted"):
                    secure_education.security_lock_files(education)
                install.assert_not_called()
            self.assertEqual(before, {p: p.read_bytes() for p in education.rglob("*") if p.is_file()})

    def test_wrong_yarn_version_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(secure_education.subprocess, "check_output", return_value="1.22.19\n"):
                with self.assertRaisesRegex(ValueError, "pinned Yarn"):
                    secure_education.security_lock_files(Path(tmp))

    def test_tampered_overlay_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay = Path(tmp) / "overlay"
            shutil.copytree(OVERLAY, overlay)
            (overlay / "frontend/yarn.lock").write_text("tampered", encoding="utf-8")
            education = Path(tmp) / "education"
            (education / "frontend").mkdir(parents=True)
            with patch.object(secure_education, "ROOT", overlay), \
                    patch.object(secure_education.subprocess, "check_output", return_value="1.22.22\n"), \
                    patch.object(secure_education.subprocess, "run") as install:
                with self.assertRaisesRegex(ValueError, "integrity failure"):
                    secure_education.security_lock_files(education)
                install.assert_not_called()

    def test_apply_writes_overlay_then_frozen_install_then_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay = Path(tmp) / "overlay"
            shutil.copytree(OVERLAY, overlay)
            manifest_path = overlay / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            education = Path(tmp) / "education"
            (education / "frontend").mkdir(parents=True)
            # Simulated upstream: each target starts as bytes whose hash is recorded in the manifest.
            for relative, hashes in manifest["files"].items():
                upstream = (relative + " upstream fixture").encode()
                hashes["upstream_sha256"] = hashlib.sha256(upstream).hexdigest()
                (education / relative).write_bytes(upstream)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(secure_education, "ROOT", overlay), \
                    patch.object(secure_education.subprocess, "check_output", return_value="1.22.22\n"), \
                    patch.object(secure_education.subprocess, "run") as install:
                secure_education.security_lock_files(education)
            install.assert_called_once()
            args, kwargs = install.call_args
            self.assertEqual(args[0], ["yarn", "install", "--frozen-lockfile", "--non-interactive"])
            self.assertEqual(kwargs["cwd"], education / "frontend")
            for relative, hashes in manifest["files"].items():
                self.assertEqual(hashlib.sha256((education / relative).read_bytes()).hexdigest(),
                                 hashes["security_sha256"], relative)


class InstalledLinkVerificationTests(unittest.TestCase):
    def _tree(self, tmp, versions):
        education = Path(tmp) / "education"
        for index, version in enumerate(versions):
            folder = education / "frontend/node_modules" / ("nested%d" % index if index else "") / "@tiptap/extension-link"
            folder.mkdir(parents=True)
            (folder / "package.json").write_text(json.dumps({"name": "@tiptap/extension-link", "version": version}))
        return education

    def test_vulnerable_installed_copy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            education = self._tree(tmp, ["2.2.3"])
            with self.assertRaisesRegex(ValueError, "Vulnerable @tiptap/extension-link remains"):
                secure_education.verify_installed_link(education)

    def test_any_vulnerable_nested_copy_fails_even_if_top_level_is_patched(self):
        with tempfile.TemporaryDirectory() as tmp:
            education = self._tree(tmp, ["2.27.3", "2.2.3"])
            with self.assertRaisesRegex(ValueError, "Vulnerable @tiptap/extension-link remains"):
                secure_education.verify_installed_link(education)

    def test_missing_link_extension_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            education = Path(tmp) / "education"
            (education / "frontend/node_modules").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "No installed @tiptap/extension-link"):
                secure_education.verify_installed_link(education)

    def test_patched_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            education = self._tree(tmp, ["2.27.3"])
            result = secure_education.verify_installed_link(education)
            self.assertEqual(list(result["extension_link_copies"].values()), ["2.27.3"])


class EducationOverlayWiringTests(unittest.TestCase):
    def setUp(self):
        self.install = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")

    def test_overlay_applies_after_source_check_and_before_asset_build(self):
        apply_at = self.install.index('run("patch-education-frontend-dependencies"')
        source_check = self.install.index("Upstream input modified during install")
        build_at = self.install.index('bench("asset-build"')
        self.assertLess(source_check, apply_at)
        self.assertLess(apply_at, build_at)

    def test_overlay_is_verified_after_asset_build(self):
        build_at = self.install.index('bench("asset-build"')
        verify_at = self.install.index('run("verify-education-after-build"')
        self.assertLess(build_at, verify_at)
        self.assertIn('"--verify"', self.install[verify_at:verify_at + 300])

    def test_regression_module_runs_in_the_hosted_security_suite(self):
        self.assertIn("tests.security.test_education_locks_2026_10_17", self.install)


if __name__ == "__main__":
    unittest.main()
