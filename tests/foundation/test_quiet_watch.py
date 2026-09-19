"""The quiet-period watch must actually alarm on silent baseline edits."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/foundation"))
from quiet_watch import LOCK_PATH, LOCKED, build, check  # noqa: E402


class QuietWatchTests(unittest.TestCase):
    def test_no_protected_file_has_drifted(self):
        self.assertEqual(check(), [])

    def test_lock_file_matches_a_fresh_build(self):
        committed = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        fresh = build()
        self.assertEqual(committed["files"], fresh["files"])

    def test_every_locked_file_exists_and_is_nonempty(self):
        self.assertGreaterEqual(len(LOCKED), 5)
        for rel in LOCKED:
            target = ROOT / rel
            self.assertTrue(target.is_file(), rel)
            self.assertGreater(target.stat().st_size, 0, rel)

    def test_check_mode_reports_a_tampered_file(self):
        probe = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'tools/foundation');"
             "import quiet_watch;"
             "quiet_watch.digest = lambda rel: '0' * 64;"
             "alarms = quiet_watch.check();"
             "print(len(alarms)); assert len(alarms) == len(quiet_watch.LOCKED)"],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.strip(), str(len(LOCKED)))
