"""Fresh/repaired customer assets come from the provider, without compilers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product import bootstrap


class PrebuiltProductAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build_sites = self.root / "build-sites"
        self.apps = self.root / "apps"
        self.public = self.apps / "education" / "education" / "public"
        (self.public / "dist").mkdir(parents=True)
        (self.public / "dist" / "lesson.js").write_text("provider compiled bundle", encoding="utf-8")
        assets = self.build_sites / "assets"
        (assets / "js").mkdir(parents=True)
        (assets / "css").mkdir()
        (assets / "js" / "language.js").write_text("provider language", encoding="utf-8")
        self.manifest = {"lesson.js": "/assets/education/dist/lesson.js"}
        (assets / "assets.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.build_sites / "private-owner-config.json").write_text("must never enter asset seed", encoding="utf-8")
        self.seed = self.root / "prebuilt"
        bootstrap.export_prebuilt_assets(self.build_sites, self.apps, self.seed)

    def test_provider_seed_excludes_site_files_and_duplicate_app_trees(self):
        self.assertEqual(sorted(path.name for path in self.seed.iterdir()), ["assets.json", "css", "js"])
        self.assertFalse((self.seed / "education").exists())
        self.assertFalse((self.seed / "private-owner-config.json").exists())

    def test_fresh_boot_and_interrupted_assets_recover_without_compilation(self):
        sites = self.root / "customer-sites"
        private = sites / "owner.localhost" / "private"
        private.mkdir(parents=True)
        (private / "credentials.txt").write_text("existing credentials", encoding="utf-8")
        with patch.object(bootstrap, "run_bench", side_effect=AssertionError("customer compilation forbidden")):
            for _ in range(2):
                bootstrap.restore_prebuilt_assets(sites, self.seed, self.apps)
                bootstrap.ensure_built_assets(sites, self.apps)
                self.assertEqual(bootstrap.manifest_assets_missing(sites), [])
                bundle = sites / "assets" / "education" / "dist" / "lesson.js"
                self.assertEqual(bundle.read_text(encoding="utf-8"), "provider compiled bundle")
                # Interrupt only a copied global asset, never an alias into
                # the provider's immutable app bundle.
                (sites / "assets" / "js" / "language.js").unlink()
        self.assertEqual((private / "credentials.txt").read_text(encoding="utf-8"), "existing credentials")

    def test_update_refreshes_manifest_and_preserves_unrelated_site_data(self):
        sites = self.root / "customer-sites"
        (sites / "assets").mkdir(parents=True)
        (sites / "assets" / "assets.json").write_text('{"old":"/assets/missing.js"}', encoding="utf-8")
        (sites / "site_config.json").write_text("owner settings", encoding="utf-8")
        bootstrap.restore_prebuilt_assets(sites, self.seed)
        bootstrap.ensure_built_assets(sites, self.apps)
        self.assertEqual(json.loads((sites / "assets" / "assets.json").read_text()), self.manifest)
        self.assertEqual((sites / "site_config.json").read_text(), "owner settings")

    def test_physical_asset_update_refreshes_same_name_and_stat_contents_only(self):
        sites = self.root / "customer-sites"
        # Model installations made before app aliases: a complete physical tree
        # whose manifest and bundle names do not change in the provider update.
        served = sites / "assets" / "education"
        shutil.copytree(self.public, served)
        stylesheet = self.public / "css" / "style.css"
        stylesheet.parent.mkdir()
        stylesheet.write_bytes(b"old css")
        served_css = served / "css" / "style.css"
        served_css.parent.mkdir()
        shutil.copy2(stylesheet, served_css)
        preserved = {
            sites / "owner.localhost/site_config.json": b"owner site configuration",
            sites / "owner.localhost/private/credentials.txt": b"private credentials",
            sites / "owner.localhost/public/files/student.txt": b"student file",
            sites.parent / "secrets/db.env": b"database secret",
            served / "unrelated.txt": b"preserve unrelated asset",
        }
        for path, data in preserved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        original_stat = stylesheet.stat()
        for content in (b"new css", b"NEW CSS"):
            with self.subTest(content=content):
                stylesheet.write_bytes(content)
                os.utime(stylesheet, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                # copy2 kept identical size/mtime on the target, so a shallow or
                # cached stat comparison cannot distinguish these updates.
                self.assertEqual(stylesheet.stat().st_size, served_css.stat().st_size)
                self.assertEqual(stylesheet.stat().st_mtime_ns, served_css.stat().st_mtime_ns)
                bootstrap.restore_prebuilt_assets(sites, self.seed, self.apps)
                self.assertFalse(served.is_symlink())
                self.assertEqual(bootstrap.ensure_built_assets(sites, self.apps), ["education"])
                self.assertEqual(served_css.read_bytes(), content)
                self.assertEqual(bootstrap.manifest_assets_missing(sites), [])
                self.assertEqual(json.loads((sites / "assets/assets.json").read_text()), self.manifest)
                for path, data in preserved.items():
                    self.assertEqual(path.read_bytes(), data)
                with patch.object(bootstrap.shutil, "copytree") as copy:
                    self.assertEqual(bootstrap.ensure_built_assets(sites, self.apps), [])
                    copy.assert_not_called()

    def test_provider_public_alias_never_compares_or_copies_onto_itself(self):
        sites = self.root / "customer-sites"
        served = sites / "assets" / "education"
        served.parent.mkdir(parents=True)
        try:
            served.symlink_to(self.public, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlinks are unavailable on this host")
            # A directory junction exercises the same samefile fast path on
            # Windows without requiring the symbolic-link privilege.
            self.assertTrue(served.resolve().is_relative_to(self.root.resolve()))
            self.assertTrue(self.public.resolve().is_relative_to(self.root.resolve()))
            # Pass CMD's quoted command line intact; list2cmdline escaping of
            # embedded quotes is not CMD's /c quoting convention.
            command = f'"{os.environ["COMSPEC"]}" /d /c mklink /J "{served}" "{self.public}"'
            result = subprocess.run(command,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with patch.object(bootstrap, "_asset_content_matches", side_effect=AssertionError("alias needs no byte scan")), \
                patch.object(bootstrap.shutil, "copytree") as copy:
            self.assertEqual(bootstrap.sync_built_assets(sites, self.apps), [])
            copy.assert_not_called()
        self.assertEqual((self.public / "dist/lesson.js").read_text(), "provider compiled bundle")

    def test_incomplete_provider_seed_refuses_without_build_fallback(self):
        missing = self.root / "missing-seed"
        with patch.object(bootstrap, "run_bench") as command:
            with self.assertRaisesRegex(RuntimeError, "complete provider image"):
                bootstrap.restore_prebuilt_assets(self.root / "customer-sites", missing)
            command.assert_not_called()
        self.assertFalse((self.root / "customer-sites").exists())

    def test_export_fails_if_provider_manifest_bundle_is_missing(self):
        (self.public / "dist" / "lesson.js").unlink()
        (self.build_sites / "assets" / "education" / "dist" / "lesson.js").unlink()
        with self.assertRaisesRegex(RuntimeError, "manifest URLs missing"):
            bootstrap.export_prebuilt_assets(self.build_sites, self.apps, self.root / "incomplete-export")

    def test_runtime_stage_copies_only_audited_installed_trees(self):
        dockerfile = (Path(__file__).resolve().parents[2] / "product" / "app.Dockerfile").read_text()
        runtime = dockerfile.split("FROM product-base AS runtime\n", 1)[1]
        copies = re.findall(r"(?m)^COPY --from=builder(?: --chown=frappe:frappe)? (\S+) (\S+)$", runtime)
        self.assertEqual(copies, [
            ("/home/frappe/bench", "/home/frappe/bench"),
            ("/product", "/product"),
            ("/build/sites-seed", "/build/sites-seed"),
            ("/build/assets-seed", "/build/assets-seed"),
        ])
        self.assertNotIn("bench build", runtime)
        self.assertIn("bench build", dockerfile.split("FROM product-base AS runtime\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
