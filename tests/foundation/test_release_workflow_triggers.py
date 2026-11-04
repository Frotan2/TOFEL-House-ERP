"""Verify release-critical finance changes actually trigger image qualification.

GitHub's path-filtered workflows do not run at all if a change is omitted from
an on.push.paths list. CI's exact-SHA release gate then cannot qualify that
revision, even when its standalone Native and Owned suites pass.

This is intentionally a source-level trigger contract, not evidence that an
image has been built or authorized for customer deployment.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def push_paths(workflow_name: str) -> set[str]:
    """Return on.push.paths entries without matching explanatory comments."""
    text = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
    # All these workflows declare workflow_dispatch after the push section.
    push_section = text.partition("  workflow_dispatch:")[0]
    self_section = push_section.partition("    paths:")[2]
    if not self_section:
        # Running on every push to both release branches covers every path,
        # including advisory inputs; it is stronger than a path allowlist.
        if ("on:\n  push:\n" in push_section
                and "    branches:\n" in push_section
                and "      - main\n" in push_section
                and "      - work\n" in push_section
                and "    paths-ignore:" not in push_section):
            return {"**"}
        raise AssertionError(f"{workflow_name}: missing safe release push trigger")
    return {
        match.group(1).strip('"\'')
        for line in self_section.splitlines()
        if (match := re.fullmatch(r"      - ([^#\s]+)", line))
    }


class ReleaseImageTriggerContract(unittest.TestCase):
    def test_finance_runtime_and_regression_changes_trigger_image_qualification(self):
        paths = push_paths("product-image.yml")
        self.assertIn("tools/native/native_checks.py", paths)
        self.assertIn("tests/finance/**", paths)

    def test_owner_setup_policy_regressions_trigger_product_image(self):
        paths = push_paths("product-image.yml")
        self.assertIn("tests/setup/**", paths)
        self.assertIn("docs/owner-decisions.json", paths)
        self.assertIn("tests/foundation/test_release_workflow_triggers.py", paths)
        self.assertIn("tests/foundation/test_windows_update_path.py", paths)

    def test_release_critical_fix_branches_and_observer_probe_are_qualified(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        self.assertIn("- 'fix/**'", workflow)
        self.assertIn("      - work", workflow)
        self.assertIn("tools/foundation/runtime_install.py", push_paths("product-image.yml"))
        self.assertIn("tests/foundation/test_foundation_disposable_restore.py", push_paths("product-image.yml"))
        self.assertIn("if: success() && startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn("tools/native/product_update_host_probe.py", push_paths("product-image.yml"))
        self.assertIn("docs/CUSTOMER-UPDATES.md", push_paths("product-image.yml"))
        self.assertIn("docs/engineering/SAFE-UPDATES.md", push_paths("product-image.yml"))
        self.assertIn("/probe.py:ro", workflow)
        self.assertIn("target=/run/th-update-docker.sock,readonly", workflow)

    def test_native_integration_separately_covers_native_checker_changes(self):
        self.assertIn("tools/native/**", push_paths("native-lifecycle.yml"))

    def test_advisory_changes_trigger_full_release_qualification(self):
        patterns = ("docs/engineering/evidence/sec-deps-01/**", "tests/security/**")
        names = ("foundation-runtime.yml", "native-lifecycle.yml",
                 "product-image.yml", "windows-customer-package.yml")
        for name in names:
            with self.subTest(workflow=name):
                watched = push_paths(name)
                self.assertTrue("**" in watched or set(patterns).issubset(watched),
                                f"{name}: advisory changes cannot reach this gate")

    def test_windows_receipt_and_installer_regressions_trigger_exact_image_gate(self):
        paths = push_paths("product-image.yml")
        self.assertIn("tests/foundation/test_online_installer.ps1", paths)
        self.assertIn("tests/foundation/test_windows_identity_receipt.ps1", paths)
        self.assertIn("product/**", paths)
        windows_workflow = (WORKFLOWS / "windows-customer-package.yml").read_text(encoding="utf-8")
        self.assertIn("test_windows_identity_receipt.ps1", windows_workflow)
        self.assertIn("test_online_installer.ps1", windows_workflow)

    def test_windows_only_package_manifest_suite_has_a_windows_runner(self):
        workflow = (WORKFLOWS / "windows-customer-package.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertIn(
            "python -m unittest tests.foundation.test_customer_package_manifest -v",
            workflow,
        )

    def test_qualified_source_builds_are_not_cancelled_by_unrelated_new_commits(self):
        for name in ("product-image.yml", "native-lifecycle.yml", "foundation-runtime.yml", "owned-suite.yml"):
            with self.subTest(workflow=name):
                workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
                group = next(line for line in workflow.splitlines() if line.startswith("  group: "))
                self.assertIn("${{ github.ref }}", group)
                self.assertIn("${{ github.sha }}", group)

    def test_product_image_keeps_exact_sha_release_gates(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tools/release/verify_ci_gates.py --ensure-started", workflow)
        self.assertIn("python3 tools/release/verify_ci_gates.py --timeout 3600", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertIn("workflow_dispatch:", workflow)

    def test_customer_package_contains_the_exact_sha_gate_receipt(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        self.assertIn('verify_ci_gates.py --timeout 3600 --scope-ref "$GITHUB_REF" --output "$RUNNER_TEMP/toefl-house-ci-gates.json"', workflow)
        self.assertIn('--gate-evidence "$RUNNER_TEMP/toefl-house-ci-gates.json"', workflow)
        self.assertIn("/product/release/ci-gates.json", workflow)

    def test_product_image_reclaims_disposable_docker_storage_before_export(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        prepare = workflow.split(
            "      - name: Reclaim disposable Docker storage before image export", 1
        )[1].split("      - name: Assemble verified customer package", 1)[0]
        self.assertIn("docker compose -f product/docker-compose.yml down --volumes --remove-orphans", prepare)
        self.assertIn("sudo rm -rf -- product/data /tmp/win-worktree", prepare)
        self.assertIn("image_id=$(docker image inspect --format '{{.Id}}' toefl-house-erp-app:ci)", prepare)
        self.assertIn("docker create --name toefl-house-image-export-pin toefl-house-erp-app:ci", prepare)
        self.assertIn("docker builder prune --all --force", prepare)
        self.assertIn("docker volume prune --force", prepare)
        self.assertIn("docker image prune --all --force", prepare)
        self.assertIn('docker image inspect "$image_id" >/dev/null', prepare)
        self.assertIn('docker tag "$image_id" toefl-house-erp-app:ci', prepare)
        self.assertIn("org.toefl-house.source-revision", prepare)
        self.assertIn("DockerRootDir", prepare)
        self.assertIn("required_bytes", prepare)
        self.assertLess(prepare.index("docker create"), prepare.index("docker image prune"))
        self.assertLess(prepare.index("docker image prune"), prepare.index('docker tag "$image_id"'))
        self.assertLess(prepare.index('docker tag "$image_id"'), prepare.index("image_revision="))

        assembly = workflow.split(
            "      - name: Assemble verified customer package", 1
        )[1].split("      - name: Export pinned offline database", 1)[0]
        self.assertLess(assembly.index("docker save"), assembly.index("docker image rm"))
        self.assertIn("docker rm toefl-house-image-export-pin", assembly)
        self.assertIn("docker image rm toefl-house-erp-app:ci", assembly)
        self.assertIn("docker image rm toefl-house-erp-app:local", assembly)
        self.assertIn("sha256sum -c toefl-house-erp-app.tar.sha256", assembly)
        self.assertLess(assembly.index("sha256sum -c"), assembly.index('rm -f -- "$image_archive"'))
        self.assertIn('test ! -e "$image_archive"', assembly)

        self.assertLess(
            workflow.index("Require release checks on the same source revision"),
            workflow.index("Reclaim disposable Docker storage before image export"),
        )
        self.assertIn("toefl-house-product-image-compose.log", workflow)

    def test_actions_customer_download_does_not_wrap_another_zip(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        artifact = workflow.split("      - name: Publish customer package artifact", 1)[1].split(
            "      - name:", 1
        )[0]
        self.assertIn("/TOEFL-House-ERP-Customer-${{ env.TOEFL_HOUSE_RELEASE_VERSION }}/", artifact)
        self.assertNotIn("*.zip", artifact)
        self.assertNotIn("/product/release/", artifact)

    def test_tagged_release_uses_versioned_notes_and_exact_build_references(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        self.assertIn("cp docs/engineering/RELEASE-CANDIDATE.md", workflow)
        self.assertIn("printf -- '- Full source SHA: `%s`\\n' \"$GITHUB_SHA\"", workflow)
        self.assertIn('"$GITHUB_RUN_ID"', workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("--prerelease", workflow)
        self.assertIn('--notes-file "$notes"', workflow)

    def test_release_qualification_stays_non_authorizing(self):
        workflow = (WORKFLOWS / "product-image.yml").read_text(encoding="utf-8")
        self.assertIn("This is not production authorization", workflow)
        self.assertIn("Production authorization: REJECT", workflow)


if __name__ == "__main__":
    unittest.main()
