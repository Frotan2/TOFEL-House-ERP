"""The frontend candidate comparison must be diagnosable from the job log.

The comparison used to record its only diagnosis in ``result.json``, inside an
artifact that EOFs from the review environment. A red step therefore reported
"Process completed with exit code 1" with no way to tell which of the twenty-
odd checks broke, and the failure sat unexplained across a branch rotation.

These tests pin the remedy: every check logs its exit code as it runs, a check
that fails logs the tail of its own output, and any failure - whether an
exception or the gate's own verdict - reaches the log as a ``::error::``
annotation that names the last failed check.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import frontend_experiment  # noqa: E402
from session_branch import ACTIVE_REF  # noqa: E402


class FailureAnnotationTests(unittest.TestCase):
    """Annotations are the only hosted diagnostic that survives, so their
    shape is pinned: one per line, no embedded newline, never unbounded."""

    def test_annotations_name_the_last_failed_check(self):
        lines = frontend_experiment.failure_annotations("yarn install exploded",
                                                        "candidate-install")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line.startswith("::error "), line)
            self.assertNotIn("\n", line)
        self.assertIn("last failed check: candidate-install", lines[0])
        self.assertIn("yarn install exploded", lines[1])

    def test_a_multiline_failure_collapses_to_one_annotation_line(self):
        lines = frontend_experiment.failure_annotations("one\ntwo\nthree", None)
        self.assertEqual(len(lines), 1)
        self.assertIn("one two three", lines[0])
        self.assertNotIn("\n", lines[0])

    def test_an_unbounded_failure_is_truncated_not_dropped(self):
        text = "x" * 5000
        lines = frontend_experiment.failure_annotations(text, "baseline-build")
        self.assertLessEqual(len(lines[1]),
                             len("::error file=tools/foundation/frontend_experiment.py::")
                             + frontend_experiment.ANNOTATION_TEXT_LIMIT)
        self.assertTrue(lines[1].endswith("..."))

    def test_a_failure_with_no_recorded_exception_still_reports(self):
        lines = frontend_experiment.failure_annotations(None, None)
        self.assertEqual(len(lines), 1)
        self.assertIn("failed without a recorded exception", lines[0])

    def test_no_failed_check_produces_no_check_line(self):
        lines = frontend_experiment.failure_annotations("gate verdict", None)
        self.assertTrue(all("last failed check" not in line for line in lines))


class ExecutedFailurePathTests(unittest.TestCase):
    """Drive the real ``main()`` with a stubbed subprocess so the wiring
    between a failing check, the log and the annotation is actually
    exercised rather than merely asserted to exist."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": ACTIVE_REF,
            "RUNNER_TEMP": str(self.tmp),
            "GITHUB_RUN_ID": "1",
            "GITHUB_SHA": "0" * 40,
            "PATH": "/usr/bin:/bin",
        }
        self.original_run = frontend_experiment.subprocess.run
        self.original_environ = frontend_experiment.os.environ

    def _run_main(self, result):
        frontend_experiment.os.environ = self.env
        frontend_experiment.subprocess.run = lambda *a, **k: result
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                code = frontend_experiment.main()
        finally:
            frontend_experiment.subprocess.run = self.original_run
            frontend_experiment.os.environ = self.original_environ
        return code, buffer.getvalue()

    def test_a_failing_check_reaches_the_log_and_names_itself(self):
        result = subprocess.CompletedProcess(args=[], returncode=1,
                                             stdout="boom out", stderr="boom err")
        code, log = self._run_main(result)
        self.assertEqual(code, 1)
        self.assertIn("[check:node-version] exit=1", log)
        self.assertIn("boom out", log)
        self.assertIn("boom err", log)
        self.assertIn("last failed check: node-version", log)

    def test_the_failure_is_recorded_in_the_report_as_well(self):
        result = subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="")
        code, log = self._run_main(result)
        self.assertEqual(code, 1)
        report = json.loads(
            (ROOT / ".foundation/frontend-experiment-evidence/result.json").read_text())
        self.assertEqual(report["status"], "fail")
        self.assertIn("node-version failed: 7", report["failure"])
        self.assertEqual(report["checks"][0]["status"], "fail")

    def test_a_passing_check_logs_its_exit_code_without_annotating(self):
        """Progress must be visible while the step runs, silently on success."""
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command[0])
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        frontend_experiment.os.environ = self.env
        frontend_experiment.subprocess.run = fake_run
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                frontend_experiment.main()
        finally:
            frontend_experiment.subprocess.run = self.original_run
            frontend_experiment.os.environ = self.original_environ
        log = buffer.getvalue()
        self.assertIn("[check:node-version] exit=0", log)
        # A passing check never names itself as a failure.
        self.assertNotIn("last failed check: node-version", log)
