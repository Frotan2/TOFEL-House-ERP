"""Desk markdown cap for showdown GHSA-rmmh-p597-ppvv (SEC-DEPS-01, 2026-10-19).

Exercises tools/foundation/secure_markdown.py on a copy of the pinned frappe tools.js fixture.
"""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.foundation import secure_markdown as sm

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/security/fixtures/frappe-988e54f3/frappe_public_js_utils_tools.js"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MarkdownCapTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.frappe = Path(self._tmp.name) / "frappe"
        target = self.frappe / sm.TARGET
        target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURE, target)
        self.target = target

    def tearDown(self):
        self._tmp.cleanup()

    def test_fixture_is_the_pinned_upstream_file(self):
        self.assertEqual(_digest(FIXTURE), sm.UPSTREAM_SHA256)

    def test_apply_produces_the_reviewed_output_and_guards_before_parsing(self):
        self.assertEqual(sm.secure_markdown(self.frappe), "applied")
        self.assertEqual(_digest(self.target), sm.REVIEWED_SHA256)
        text = self.target.read_text(encoding="utf-8")
        guard = text.index("if (txt.length > %d)" % sm.MAX_CHARS)
        parse = text.index("return sanitize_markdown_html(frappe.md2html.makeHtml(txt));")
        self.assertLess(guard, parse, "the length guard must run before showdown parses")
        self.assertIn("plain.textContent = txt;", text)

    def test_apply_is_idempotent(self):
        sm.secure_markdown(self.frappe)
        self.assertEqual(sm.secure_markdown(self.frappe), "already-applied")
        self.assertEqual(_digest(self.target), sm.REVIEWED_SHA256)

    def test_verify_only_never_writes(self):
        with self.assertRaisesRegex(ValueError, "not applied"):
            sm.secure_markdown(self.frappe, verify_only=True)
        self.assertEqual(_digest(self.target), sm.UPSTREAM_SHA256)
        sm.secure_markdown(self.frappe)
        self.assertEqual(sm.secure_markdown(self.frappe, verify_only=True), "verified")

    def test_unreviewed_content_is_refused_and_left_untouched(self):
        self.target.write_text("// unreviewed\n", encoding="utf-8")
        before = _digest(self.target)
        with self.assertRaisesRegex(ValueError, "refused"):
            sm.secure_markdown(self.frappe)
        self.assertEqual(_digest(self.target), before)

    def test_missing_anchor_is_refused(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(sm.BEFORE, "\treturn 0;\n")
        self.target.write_text(text, encoding="utf-8")
        with self.assertRaises(ValueError):
            sm.secure_markdown(self.frappe)

    def test_symlink_target_is_refused(self):
        real = Path(self._tmp.name) / "real.js"
        shutil.copyfile(FIXTURE, real)
        self.target.unlink()
        try:
            self.target.symlink_to(real)
        except OSError:
            self.skipTest("symlinks not supported here")
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            sm.secure_markdown(self.frappe)

    def test_patched_file_is_valid_javascript(self):
        sm.secure_markdown(self.frappe)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not available")
        result = subprocess.run([node, "--check", str(self.target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cap_value_matches_the_measurement_record(self):
        # docs/engineering/evidence/sec-deps-01/markdown-cap-2026-10-19/README.md cites 2000 characters.
        self.assertEqual(sm.MAX_CHARS, 2000)
        record = (ROOT / "docs/engineering/evidence/sec-deps-01/markdown-cap-2026-10-19/README.md").read_text(encoding="utf-8")
        self.assertIn("2000", record)


if __name__ == "__main__":
    unittest.main()
