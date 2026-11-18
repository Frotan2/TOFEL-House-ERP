import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.foundation import advisory_triage, picomatch_build_boundary as boundary


PARSER = b"fixture: Input length: 5, exceeds maximum allowed length: 4"
ROOT = Path(__file__).resolve().parents[2]


class PicomatchBuildBoundaryTests(unittest.TestCase):
    def setUp(self):
        staging = tempfile.TemporaryDirectory()
        self.addCleanup(staging.cleanup)
        self.apps = Path(staging.name) / "apps"
        self.global_assets = Path(staging.name) / "assets"
        self.global_assets.mkdir()
        self.public = self.apps / "app" / "app" / "public"
        self.public.mkdir(parents=True)
        (self.public / "desk.js").write_text("const ready = true;", encoding="utf-8")
        self.modules = self.apps / "app" / "node_modules"
        self.picomatch = self.modules / "picomatch"
        (self.picomatch / "lib").mkdir(parents=True)
        (self.picomatch / "lib/parse.js").write_bytes(PARSER)
        (self.picomatch / "package.json").write_text(
            json.dumps({"name": "picomatch", "version": "4.0.7"}), encoding="utf-8"
        )
        parser_digest = hashlib.sha256(PARSER).hexdigest()
        hashes = patch.dict(boundary.PARSER_HASHES, {"4.0.7": parser_digest})
        hashes.start()
        self.addCleanup(hashes.stop)

    def test_removes_only_verified_build_dependency_after_asset_checks(self):
        (self.modules / "socket.io").mkdir()
        self.assertEqual(boundary.enforce(self.apps, self.global_assets), (1, 1))
        self.assertFalse(self.picomatch.exists())
        self.assertTrue((self.modules / "socket.io").is_dir())
        self.assertTrue((self.public / "desk.js").is_file())

    def test_refuses_rendered_parser_and_source_map_before_removing_anything(self):
        for name, content in (
            ("bundle.js", PARSER),
            ("bundle.js.map", b'{"sources":["../node_modules/picomatch/lib/parse.js"]}'),
        ):
            with self.subTest(asset=name):
                asset = self.global_assets / name
                asset.write_bytes(content)
                with self.assertRaisesRegex(ValueError, "emitted into a browser asset"):
                    boundary.enforce(self.apps, self.global_assets)
                self.assertTrue(self.picomatch.exists())
                asset.unlink()

    def test_refuses_unreviewed_parser_before_removing_anything(self):
        (self.picomatch / "lib/parse.js").write_bytes(PARSER + b"unexpected change")
        with self.assertRaisesRegex(ValueError, "Unreviewed Picomatch package"):
            boundary.enforce(self.apps, self.global_assets)
        self.assertTrue(self.picomatch.exists())

    def test_reviewed_npm_advisory_has_no_effect_on_unrelated_findings(self):
        advisory = {"id": 1247710, "severity": "high"}
        known = advisory_triage.triage_npm({"picomatch": [advisory]})
        self.assertEqual(known["findings"][0]["disposition"], "BUILD_ONLY")
        self.assertEqual(advisory_triage.overall_status(npm_result=known), "pass")
        unexpected = advisory_triage.triage_npm({
            "another-module": [advisory],
            "picomatch": [{"id": 9999999, "severity": "high"}],
        })
        self.assertEqual(len(unexpected["untriaged"]), 2)
        self.assertEqual(advisory_triage.overall_status(npm_result=unexpected), "fail")

    def test_customer_image_prunes_only_after_build_and_before_runtime_export(self):
        dockerfile = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        enforcement = dockerfile.index("&& python3 /product/picomatch_build_boundary.py")
        self.assertLess(dockerfile.index("&& bench build"), enforcement)
        self.assertLess(enforcement, dockerfile.index("export_prebuilt_assets()"))
        self.assertLess(enforcement, dockerfile.index("FROM product-base AS runtime"))
