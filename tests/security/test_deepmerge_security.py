import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.foundation.secure_deepmerge import secure, receipt, EDUCATION_WITHOUT_DEEPMERGE

FIXTURE = Path(__file__).parent / "fixtures/deepmerge-4.3.1"


class DeepmergeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "node_modules/deepmerge"
        shutil.copytree(FIXTURE, self.package)

    def test_unpatched_and_empty_verification_refused(self):
        with self.assertRaises(ValueError):
            secure(self.root, verify_only=True)
        with self.assertRaises(ValueError):
            secure(self.root / "absent")

    def test_preflight_rejects_drift_without_partial_writes(self):
        original = (self.package / "index.js").read_bytes()
        (self.package / "dist/umd.js").write_text("drift")
        with self.assertRaises(ValueError):
            secure(self.root)
        self.assertEqual(original, (self.package / "index.js").read_bytes())

    def test_manifest_cannot_redirect_to_unpatched_entrypoint(self):
        manifest = self.package / "package.json"
        data = json.loads(manifest.read_text())
        data["main"] = "evil.js"
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            secure(self.root)

    def test_reinstall_is_detected(self):
        secure(self.root)
        shutil.copyfile(FIXTURE / "dist/cjs.js", self.package / "dist/cjs.js")
        with self.assertRaises(ValueError):
            secure(self.root, verify_only=True)

    def test_expected_consumers_and_reviewed_education_absence(self):
        apps = self.root / "apps"
        hrms = apps / "hrms/frontend/node_modules/deepmerge"
        shutil.copytree(FIXTURE, hrms)
        education = apps / "education/frontend"
        (education / "node_modules").mkdir(parents=True)
        with self.assertRaises(ValueError):
            secure(apps, apps=True)
        reviewed = Path(__file__).resolve().parents[2] / "tools/foundation/education-locks/frontend/yarn.lock"
        shutil.copyfile(reviewed, education / "yarn.lock")
        import hashlib
        self.assertEqual(hashlib.sha256(reviewed.read_bytes()).hexdigest(), EDUCATION_WITHOUT_DEEPMERGE)
        self.assertEqual(secure(apps, apps=True), 1)
        shutil.rmtree(hrms)
        with self.assertRaises(ValueError):
            secure(apps, apps=True)

    def test_linked_consumer_cannot_hide_copy(self):
        outside = self.root / "outside"
        shutil.copytree(FIXTURE, outside / "node_modules/deepmerge")
        try:
            (self.root / "node_modules/hidden").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows account lacks symlink privilege; hosted Linux executes this case")
        with self.assertRaises(ValueError):
            secure(self.root)

    def test_native_public_alias_is_allowed_only_to_the_audited_root(self):
        target = self.root / "frappe/node_modules"
        target.mkdir(parents=True)
        alias = self.root / "frappe/frappe/public/node_modules"
        alias.parent.mkdir(parents=True)
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Windows account lacks symlink privilege; hosted Linux executes this case")
        self.assertEqual(secure(self.root), 1)
        # The canonical target is scanned, rather than trusting the alias.
        shutil.copytree(FIXTURE, target / "deepmerge")
        self.assertEqual(secure(self.root), 2)
        self.assertEqual(secure(self.root, verify_only=True), 2)
        (target / "deepmerge/dist/cjs.js").write_text("tampered")
        with self.assertRaises(ValueError):
            secure(self.root, verify_only=True)
        shutil.copyfile(self.package / "dist/cjs.js", target / "deepmerge/dist/cjs.js")
        alias.unlink()
        alias.symlink_to(self.package.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Linked dependency directory"):
            secure(self.root)

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_receipt_probes_actual_resolved_distributions(self):
        secure(self.root)
        result = receipt(self.root)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["copies"][0]["resolved_main"], "dist/cjs.js")
        with self.assertRaises(ValueError):
            receipt(self.root, assets=True)
        for app in ("education", "hrms"):
            public = self.root / app / app / "public/frontend"
            public.mkdir(parents=True)
            (public / "fixture.js").write_text("// synthetic asset identity fixture")
        assets = receipt(self.root, assets=True)["emitted_asset_sha256"]
        self.assertEqual(set(assets), {"education/frontend", "hrms/frontend"})
        self.assertEqual(len(assets["education/frontend"]["fixture.js"]), 64)

    def test_nested_copy_is_verified_and_later_tampering_refused(self):
        nested = self.root / "node_modules/consumer/node_modules/deepmerge"
        shutil.copytree(self.package, nested)
        self.assertEqual(secure(self.root), 2)
        self.assertEqual(secure(self.root, verify_only=True), 2)
        (nested / "dist/cjs.js").write_text("tampered")
        with self.assertRaises(ValueError):
            secure(self.root, verify_only=True)

    def test_build_paths_apply_before_compilation_and_verify_after(self):
        root = Path(__file__).resolve().parents[2]
        docker = (root / "product/app.Dockerfile").read_text()
        apply = "RUN python3 /product/secure_deepmerge.py /home/frappe/bench/apps"
        self.assertLess(docker.index(apply), docker.index("&& bench build"))
        self.assertGreater(docker.index("apps --apps --verify"), docker.index("&& bench build"))
        context = (root / ".dockerignore").read_text()
        for name in ("secure_deepmerge.py", "deepmerge-hashes.json"):
            self.assertIn("!tools/foundation/" + name, context)

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_real_publisher_entry_points_and_merge_semantics(self):
        subprocess.run(["node", "-e", "const m=require(process.argv[1]); const x=m(JSON.parse('{\"__proto__\":{\"admin\":true}}'),{}); if(x.admin!==true) process.exit(1)", str(self.package / "dist/cjs.js")], check=True)
        # The default npm entry point is cjs; browser bundlers may use umd.
        self.assertEqual(secure(self.root), 1)
        self.assertEqual(secure(self.root), 1)
        self.assertEqual(secure(self.root, verify_only=True), 1)
        script = r'''
const assert = require('node:assert/strict');
for (const path of process.argv.slice(1)) {
  const merge = require(path);
  const poison = JSON.parse('{"__proto__":{"admin":true},"nested":{"x":1}}');
  for (const result of [merge(poison, {}), merge(Object.create(null), poison),
      merge({}, {nested: poison}).nested, merge([], [poison])[0]]) {
    assert.equal(Object.getPrototypeOf(result), Object.prototype);
    assert.equal(result.admin, undefined);
    assert.equal({}.admin, undefined);
  }
  const a = {nested:{a:1}, list:[1]};
  assert.deepEqual(merge(a,{nested:{b:2},list:[2]}),{nested:{a:1,b:2},list:[1,2]});
  assert.deepEqual(a,{nested:{a:1},list:[1]});
  const symbol = Symbol('test');
  assert.equal(merge({}, {[symbol]:3})[symbol],3);
  assert.deepEqual(merge.all([{a:1},{b:2}]),{a:1,b:2});
  const constructor = JSON.parse('{"constructor":{"prototype":{"admin":true}}}');
  assert.equal(merge({}, constructor).admin, undefined);
  assert.equal(Object.prototype.admin, undefined);
  assert.equal(merge({nested:{a:1}},{nested:{b:2}},{customMerge:key=>key==='nested'?()=>({custom:true}):undefined}).nested.custom,true);
}
'''
        # index.js has one tiny publisher dependency; dist files are standalone.
        dep = self.package / "node_modules/is-mergeable-object"
        dep.mkdir(parents=True)
        (dep / "index.js").write_text("module.exports = x => !!x && typeof x === 'object' && !(x instanceof Date) && !(x instanceof RegExp)")
        subprocess.run(["node", "-e", script, *(str(self.package / p) for p in ("index.js", "dist/cjs.js", "dist/umd.js"))], check=True)


if __name__ == "__main__":
    unittest.main()
