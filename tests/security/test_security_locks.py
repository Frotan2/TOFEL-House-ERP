"""Exact dependency overlay, fail-closed preflight, and deployment wiring."""
from pathlib import Path
import hashlib
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.foundation import secure_hrms

ROOT = Path(__file__).resolve().parents[2]


class SecurityLocksTests(unittest.TestCase):
    def test_lock_integrity_registry_and_reviewed_editor_versions(self):
        for kind in ("hrms", "banking"):
            root = ROOT / "tools/foundation" / (kind + "-locks")
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual(manifest["yarn_version"], "1.22.22")
            for name, hashes in manifest["files"].items():
                data = (root / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), hashes["security_sha256"])
                self.assertNotIn(b"\r", data)
                if name.endswith("yarn.lock"):
                    self.assertIn(b"# yarn lockfile v1", data)
                    for line in data.decode().splitlines():
                        if line.strip().startswith("resolved "):
                            self.assertTrue(line.strip().startswith('resolved "https://registry.npmjs.org/'), line)
            if kind == "hrms":
                for tree in ("frontend", "roster"):
                    package = json.loads((root / tree / "package.json").read_text())
                    for name, (version, _) in secure_hrms.PATCHES.items():
                        self.assertEqual(package["resolutions"][name], version)
                    self.assertEqual(package["dependencies"]["frappe-ui"], "0.1.105")

    def test_installed_manifest_drift_fails_before_install_or_any_write(self):
        for banking in (False, True):
            with self.subTest(banking=banking), tempfile.TemporaryDirectory() as tmp:
                root = ROOT / "tools/foundation" / ("banking-locks" if banking else "hrms-locks")
                target = Path(tmp) / "app"
                shutil.copytree(root, target)
                manifest = json.loads((target / "manifest.json").read_text())
                with patch.object(secure_hrms.subprocess, "check_output", return_value="1.22.22\n"):
                    secure_hrms.security_lock_files(target, verify_only=True, banking=banking)
                    filename = next(iter(manifest["files"]))
                    (target / filename).write_text("unreviewed graph")
                    before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
                    with patch.object(secure_hrms.subprocess, "run") as install:
                        with self.assertRaisesRegex(ValueError, "manifests drifted"):
                            secure_hrms.security_lock_files(target, banking=banking)
                        install.assert_not_called()
                    self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_markdown_patch_is_hash_bound_idempotent_and_required_at_boot(self):
        fixture = ROOT / "tests/security/fixtures/frappe_ui_text_editor_0_1_105.vue"
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), secure_hrms.EDITOR_ORIGINAL_SHA256)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for tree in ("frontend", "roster"):
                folder = root / tree / "node_modules/frappe-ui"
                target = folder / secure_hrms.EDITOR_PATH
                target.parent.mkdir(parents=True)
                (folder / "package.json").write_text('{"name":"frappe-ui","version":"0.1.105"}')
                target.write_bytes(fixture.read_bytes())
            with self.assertRaisesRegex(ValueError, "Unverified"):
                secure_hrms.secure_markdown_paste(root, verify_only=True)
            secure_hrms.secure_markdown_paste(root)
            secure_hrms.secure_markdown_paste(root)
            secure_hrms.secure_markdown_paste(root, verify_only=True)
            target = root / "frontend/node_modules/frappe-ui" / secure_hrms.EDITOR_PATH
            self.assertIn("new window.DOMParser().parseFromString", target.read_text())
            self.assertNotIn("dom.innerHTML = markdownToHTML", target.read_text())
            target.write_bytes(fixture.read_bytes())
            with self.assertRaisesRegex(ValueError, "Unverified"):
                secure_hrms.secure_markdown_paste(root, verify_only=True)
            target.write_text("unreviewed parser")
            with self.assertRaisesRegex(ValueError, "Unverified"):
                secure_hrms.secure_markdown_paste(root)
        bootstrap = (ROOT / "product/bootstrap.py").read_text()
        self.assertIn("secure_markdown_paste(hrms_dir, verify_only=True)", bootstrap)
        browser = (ROOT / "tools/foundation/hrms_editor_security.mjs").read_text()
        self.assertIn("clipboardData.setData('text/plain', '**Markdown**", browser)
        self.assertIn("window.__executed", browser)

    def test_wrong_yarn_version_rejected(self):
        with patch.object(secure_hrms.subprocess, "check_output", return_value="4.0.0\n"):
            with self.assertRaisesRegex(ValueError, "pinned Yarn"):
                secure_hrms.security_lock_files(Path("unused"))

    def test_all_installers_ship_and_verify_both_security_overlays(self):
        docker = (ROOT / "product/app.Dockerfile").read_text()
        context = (ROOT / ".dockerignore").read_text()
        for kind in ("hrms", "banking"):
            self.assertIn(f"COPY tools/foundation/{kind}-locks /product/{kind}-locks", docker)
            self.assertIn(f"!tools/foundation/{kind}-locks/**", context)
        for file in ("tools/foundation/runtime_install.py", "tools/native/run_native.py", "product/app.Dockerfile"):
            self.assertIn("--banking", (ROOT / file).read_text())
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text()
        self.assertIn('"verify-banking-after-build"', runtime)
        self.assertIn('"built-hrms-editor-security"', runtime)


if __name__ == "__main__":
    unittest.main()
