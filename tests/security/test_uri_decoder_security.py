"""CommonJS compatibility, hostile-input and fail-closed backport tests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.foundation.secure_uri_decoder import secure, receipt, HASHES, DATA
from tools.foundation import advisory_triage

FIXTURE = Path(__file__).parent / "fixtures/decode-uri-component-0.2.2"


class DecoderSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / "frappe/node_modules/decode-uri-component"
        shutil.copytree(FIXTURE, self.package)

    def test_real_resolved_cjs_and_both_hostile_inputs(self):
        found = secure(self.root)
        self.assertEqual(receipt(self.root, found)["status"], "pass")
        self.assertEqual(secure(self.root, verify=True), found)
        self.assertEqual(secure(self.root), found)

    def test_compatible_valid_unicode_and_plus_decoding(self):
        # Compare public behavior to the unmodified publisher for ordinary
        # source-map URLs and all Unicode scalar values in this corpus.
        secure(self.root)
        probe = r"""
const assert = require('node:assert/strict');
const old = require(process.argv[1]), next = require(process.argv[2]);
const inputs = ['a+b%2Bc', 'file%3A%2F%2Ftest%20map.css', '%FE%FF', '%C2', '%ZZ', '%', 'x'];
for (const point of [0, 1, 32, 127, 128, 255, 0x627, 0x20ac, 0x1f600, 0x10ffff]) inputs.push(encodeURIComponent(String.fromCodePoint(point)));
for (const input of inputs) assert.equal(next(input), old(input), input);
"""
        subprocess.run(["node", "-e", probe, str(FIXTURE.resolve()), str(self.package)],
                       check=True, capture_output=True, timeout=10)

    def test_unknown_nested_copy_prevents_every_write(self):
        nested = self.root / "hrms/node_modules/tool/node_modules/decode-uri-component"
        shutil.copytree(FIXTURE, nested)
        (nested / "index.js").write_text("unreviewed")
        with self.assertRaises(ValueError):
            secure(self.root)
        self.assertEqual(hashlib.sha256((self.package / "index.js").read_bytes()).hexdigest(),
                         HASHES["original_0_2_2_sha256"])

    def test_manifest_cannot_redirect_to_unpatched_code(self):
        manifest = self.package / "package.json"
        value = json.loads(manifest.read_text())
        value["main"] = "alternate.js"
        manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            secure(self.root)

    def test_verify_refuses_old_or_tampered_sources(self):
        with self.assertRaises(ValueError):
            secure(self.root, verify=True)
        secure(self.root)
        (self.package / "index.js").write_text("tampered")
        with self.assertRaises(ValueError):
            secure(self.root, verify=True)

    def test_payload_retains_exact_upstream_decoder_body(self):
        patched = (DATA / "decode-uri-component-0.5.1.cjs").read_bytes()
        body = patched.split(b"\n// Preserve the pinned 0.2.2 CommonJS API", 1)[0]
        original = body.replace(b"function decodeUriComponent(", b"export default function decodeUriComponent(", 1)
        self.assertEqual(hashlib.sha256(original).hexdigest(), HASHES["upstream_0_5_1_sha256"])

    def test_receipt_is_stable_across_build_and_runtime_traversal(self):
        second = self.root / "hrms/node_modules/tool/node_modules/decode-uri-component"
        shutil.copytree(FIXTURE, second)
        found = secure(self.root)
        self.assertEqual(receipt(self.root, found), receipt(self.root, list(reversed(found))))

    def test_every_real_build_qualifies_and_ships_the_backport(self):
        repo = Path(__file__).resolve().parents[2]
        docker = (repo / "product/app.Dockerfile").read_text()
        apply = "RUN python3 /product/secure_uri_decoder.py /home/frappe/bench/apps"
        self.assertLess(docker.index(apply), docker.index("bench build"))
        self.assertIn("secure_uri_decoder.py /home/frappe/bench/apps --verify --report /build/uri-decoder-distribution.json", docker)
        self.assertIn("COPY --from=builder /build/uri-decoder-distribution.json /build/uri-decoder-distribution.json", docker)
        foundation = (repo / "tools/foundation/runtime_install.py").read_text()
        self.assertLess(foundation.index('run("secure-uri-decoder-before-build"'), foundation.index('bench("asset-build"'))
        self.assertIn('run("verify-uri-decoder-after-build"', foundation)
        native = (repo / "tools/native/run_native.py").read_text()
        self.assertIn("run('secure-uri-decoder-installed-sources'", native)
        self.assertIn("run('verify-final-uri-decoder-sources'", native)
        image = (repo / ".github/workflows/product-image.yml").read_text()
        self.assertIn("actual = receipt(root, secure(root, verify=True))", image)
        self.assertIn("assert actual == expected", image)
        normalizer = (repo / "product/windows/Normalize Product Sources.ps1").read_text()
        self.assertIn('".cjs"', normalizer)

    def test_new_advisory_is_narrow_and_future_findings_still_fail(self):
        loaded = advisory_triage.load_triage()
        for aid in (1243857, "GHSA-qr28-fpjm-wq7f", "CVE-2026-118664"):
            result = advisory_triage.triage_npm({"decode-uri-component": [{"id": aid}]}, loaded)
            self.assertEqual(result["closed"], 1)
            self.assertEqual(result["findings"][0]["disposition"], "MITIGATED")
            unrelated = advisory_triage.triage_npm({"unrelated": [{"id": aid}]}, loaded)
            self.assertEqual(unrelated["open"], 1)
        future = advisory_triage.triage_npm({"decode-uri-component": [{"id": "GHSA-zzzz-zzzz-zzzz"}]}, loaded)
        self.assertEqual(future["open"], 1)
        self.assertEqual(len(future["untriaged"]), 1)


if __name__ == "__main__":
    unittest.main()
