"""Contract for the first-boot restore rehearsal gate in product-image.yml.

The rehearsal must prove three things on the disposable CI site: the marker
row existed before the restore, the restore removed it, and uploaded files
(public and private) came back byte-for-byte. Every check is fail-closed.

The earlier gate read `bench console` output with an anchored `^False$` match.
IPython prefixes printed values with prompts (`In [2]: False`), so that check
could not be trusted. These tests pin the replacement: marker I/O runs in a
plain python3 process, each gate matches an explicit RESULT/PROBE line, and
the grep patterns are executed against synthetic output so a prompt-decorated
or missing line is shown to fail.

Nothing here touches a real site, database, backup or credential. The synthetic
files live in a temporary directory.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-image.yml"
SITE = "toeflhouse.localhost"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _grep_pattern(text: str, anchor: str) -> str:
    """Return the literal pattern from the workflow's `grep -q '<pattern>' <file>` line."""
    line = next(l for l in text.splitlines() if anchor in l)
    match = re.search(r"grep -q '(\^[^']+)'", line)
    if not match:
        raise AssertionError(f"no grep -q pattern on the line containing {anchor!r}: {line!r}")
    return match.group(1)


class RestoreGateWiringContract(unittest.TestCase):
    def test_no_marker_check_runs_through_bench_console(self):
        # IPython output carries prompts; a console-based boolean is not a valid channel.
        code = "\n".join(l for l in _workflow().splitlines() if not l.lstrip().startswith("#"))
        self.assertIsNone(re.search(r"bench\b[^\n]*\bconsole\b", code),
                          "bench console must not be used for restore marker checks")

    def test_pre_backup_marker_creation_is_checked(self):
        text = _workflow()
        self.assertIn("RESULT marker_created=%s", text)
        self.assertIn("grep -q '^RESULT marker_created=True$' marker-create.txt", text)

    def test_pre_restore_marker_presence_is_a_hard_gate(self):
        text = _workflow()
        gate = "grep -q '^PROBE marker_present_before_restore=True$' restore-gate-probes.txt"
        self.assertIn(gate, text)
        restore_at = text.index("restore \\\n            \"sites/toeflhouse.localhost/private/backups/")
        self.assertLess(text.index(gate), restore_at,
                        "the pre-restore marker gate must run before bench restore")

    def test_post_restore_absence_is_fail_closed_on_a_result_line(self):
        text = _workflow()
        self.assertIn("if ! grep -q '^RESULT marker_after_present=False$' marker-after.txt; then",
                      text)
        block = text[text.index("if ! grep -q '^RESULT marker_after_present=False$'"):]
        self.assertLess(block.index("exit 1"), block.index("fi"))

    def test_file_markers_written_before_backup_and_verified_after_restore(self):
        text = _workflow()
        write_public = text.index("sites/toeflhouse.localhost/public/files/product-image-restore-marker.txt")
        write_private = text.index("sites/toeflhouse.localhost/private/files/product-image-restore-marker.txt")
        backup = text.index("backup --with-files")
        restore = text.index("restore \\\n            \"sites/toeflhouse.localhost/private/backups/")
        verify_public = text.index('cat "sites/toeflhouse.localhost/$scope/files/product-image-restore-marker.txt"')
        self.assertLess(max(write_public, write_private), backup,
                        "uploaded-file markers must exist in the backup")
        self.assertLess(restore, verify_public,
                        "uploaded-file markers must be verified after the restore")
        self.assertIn("for scope in public private; do", text)

    def test_file_marker_mismatch_is_fail_closed(self):
        text = _workflow()
        block = text[text.index("for scope in public private; do"):]
        block = block[:block.index("echo \"::notice title=Restore rehearsal::")]
        self.assertIn('if [ "$restored_file" != "$file_marker" ]; then', block)
        self.assertIn("exit 1", block)


class RestoreGateBehaviourContract(unittest.TestCase):
    """Run the workflow's own grep patterns against synthetic probe output."""

    @classmethod
    def setUpClass(cls):
        cls.text = _workflow()
        cls.after_pattern = _grep_pattern(cls.text, "marker-after.txt; then")
        cls.before_pattern = _grep_pattern(cls.text, "restore-gate-probes.txt; then")
        cls.created_pattern = _grep_pattern(cls.text, "marker-create.txt ||")
        cls.tmp = Path(tempfile.mkdtemp(prefix="restore-gate-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _passes(self, pattern: str, content: str | None) -> bool:
        path = self.tmp / "synthetic.txt"
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(content, encoding="utf-8")
        result = subprocess.run(["grep", "-q", pattern, str(path)], check=False,
                                stderr=subprocess.DEVNULL)
        return result.returncode == 0

    def test_absence_passes_only_on_the_exact_result_line(self):
        self.assertTrue(self._passes(self.after_pattern, "RESULT marker_after_present=False\n"))

    def test_prompt_decorated_false_is_rejected(self):
        # This is the exact shape that made the old console gate ambiguous.
        self.assertFalse(self._passes(self.after_pattern, "In [2]: False\n"))
        self.assertFalse(self._passes(self.after_pattern, "Out[2]: False\n"))

    def test_presence_and_missing_output_are_rejected(self):
        self.assertFalse(self._passes(self.after_pattern, "RESULT marker_after_present=True\n"))
        self.assertFalse(self._passes(self.after_pattern, ""))
        self.assertFalse(self._passes(self.after_pattern, None))

    def test_absence_line_must_not_be_a_substring_match(self):
        self.assertFalse(self._passes(self.after_pattern,
                                      "RESULT marker_after_present=False extra\n"))

    def test_pre_restore_gate_requires_presence(self):
        ok = "PROBE marker_present_before_restore=True\n"
        self.assertTrue(self._passes(self.before_pattern, ok))
        self.assertFalse(self._passes(self.before_pattern,
                                      "PROBE marker_present_before_restore=False\n"))
        self.assertFalse(self._passes(self.before_pattern, "In [1]: True\n"))
        self.assertFalse(self._passes(self.before_pattern, None))

    def test_marker_creation_requires_the_created_result(self):
        self.assertTrue(self._passes(self.created_pattern, "RESULT marker_created=True\n"))
        self.assertFalse(self._passes(self.created_pattern, "RESULT marker_created=False\n"))
        self.assertFalse(self._passes(self.created_pattern, "In [1]: True\n"))


if __name__ == "__main__":
    unittest.main()
