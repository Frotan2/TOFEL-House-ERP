"""Unit tests for the evidence collector, NOT tests of ERP functionality."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", ROOT / "tools/foundation/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_missing_binary_is_not_pass(self):
        with patch.object(preflight.shutil, "which", return_value=None):
            self.assertEqual(preflight.inspect_command(["bench", "--version"])["status"], "missing")

    def test_wrong_patch_version_fails_exact_pin(self):
        result = subprocess.CompletedProcess([], 0, "v24.14.0\n", "")
        with patch.object(preflight.shutil, "which", return_value="/tool"), patch.object(preflight.subprocess, "run", return_value=result):
            self.assertEqual(preflight.inspect_command(["node"], "24.21.0")["status"], "version_mismatch")

    def test_error_with_version_text_does_not_pass(self):
        result = subprocess.CompletedProcess([], 1, "24.21.0", "private diagnostic")
        with patch.object(preflight.shutil, "which", return_value="/tool"), patch.object(preflight.subprocess, "run", return_value=result):
            report = preflight.inspect_command(["node"], "24.21.0")
            self.assertEqual(report["status"], "error")
            self.assertNotIn("private diagnostic", json.dumps(report))

    def test_timeout_is_recorded_not_hidden(self):
        with patch.object(preflight.shutil, "which", return_value="/tool"), patch.object(preflight.subprocess, "run", side_effect=subprocess.TimeoutExpired("tool", 20)):
            self.assertEqual(preflight.inspect_command(["tool"])["error_type"], "TimeoutExpired")

    def test_tool_success_never_certifies_erp(self):
        matrix = json.loads(preflight.MATRIX.read_text())
        with patch.object(preflight, "inspect_command", return_value={"status": "pass"}):
            report = preflight.collect("python3", matrix)
        self.assertTrue(report["native_tool_versions_match"])
        self.assertTrue(report["docker_daemon_and_compose_available"])
        self.assertFalse(report["foundation_runtime_validated"])


if __name__ == "__main__":
    unittest.main()
