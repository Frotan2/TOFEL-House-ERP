"""Contract tests for the non-secret hosted whole-stack dependency audit."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[2] / "tools" / "foundation"
sys.path.insert(0, str(TOOLS))
import audit_stack  # noqa: E402


class RuntimeDependencyAuditTests(unittest.TestCase):
    def node_root(self, directory: Path, name: str, version: str) -> Path:
        root = directory / "node_modules"
        package = root / name
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            '{"name": "' + name + '", "version": "' + version + '"}', encoding="utf-8"
        )
        return root

    def test_combined_node_inventory_retains_missing_root_and_merges_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first = self.node_root(directory / "one", "example", "1.0.0")
            empty = directory / "empty" / "node_modules"; empty.mkdir(parents=True)
            second = self.node_root(directory / "two", "example", "2.0.0")
            inventory, roots = audit_stack.combined_node_inventory([first, directory / "absent", empty, second])
        self.assertEqual(inventory, {"example": ["1.0.0", "2.0.0"]})
        self.assertEqual([root["status"] for root in roots], ["collected", "missing", "empty", "collected"])

    def test_osv_rejects_response_not_aligned_to_each_requested_package_version(self):
        with patch.object(audit_stack, "post_json", return_value={"results": []}):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                audit_stack.osv_pypi_advisories({"sample": ["1.0"]})

    def test_report_preserves_advisory_matches_and_scanner_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            node_root = self.node_root(Path(directory), "example", "1.0.0")
            args = argparse.Namespace(
                node_modules=[node_root],
                image=["mariadb=mariadb@sha256:" + "a" * 64],
            )
            npm = {"example": [{"id": 7, "url": "https://example.test/advisory"}]}
            osv = {"endpoint": audit_stack.OSV_BATCH_ENDPOINT, "queries": 1,
                   "findings": [{"package": "sample", "version": "1.0", "id": "PYSEC-1"}]}
            with patch.object(audit_stack, "installed_python_inventory", return_value={"sample": ["1.0"]}), \
                 patch.object(audit_stack, "npm_advisories", return_value=npm), \
                 patch.object(audit_stack, "osv_pypi_advisories", return_value=osv):
                report = audit_stack.report_for(args)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["node"]["advisory_entries"], 1)
        self.assertEqual(report["python"]["osv"]["findings"][0]["id"], "PYSEC-1")
        self.assertEqual(report["containers"]["status"], "inventory_only")

    def test_images_require_digest_pins(self):
        with self.assertRaisesRegex(ValueError, "sha256"):
            audit_stack.parse_images(["redis=redis:latest"])

    def test_runtime_runs_the_audit_after_the_real_asset_build(self):
        runtime = (Path(__file__).resolve().parents[2] / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        self.assertIn('ROOT / "tools/foundation/audit_stack.py"', runtime)
        self.assertIn('"hosted-full-stack-dependency-audit"', runtime)
        self.assertIn('"resolved_stack_dependencies"', runtime)
        self.assertLess(runtime.index('bench("asset-build"'), runtime.index('"hosted-full-stack-dependency-audit"'))
        self.assertIn('components[name]["image_digest"]', runtime)


if __name__ == "__main__":
    unittest.main()
