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
        raise AssertionError(f"{workflow_name}: missing push path filters")
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

    def test_native_integration_separately_covers_native_checker_changes(self):
        self.assertIn("tools/native/**", push_paths("native-lifecycle.yml"))

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
