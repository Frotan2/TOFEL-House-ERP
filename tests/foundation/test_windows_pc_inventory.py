"""Real Windows PowerShell preflight with an isolated Docker name inventory."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "product/windows/Check This PC.ps1"


@unittest.skipUnless(os.name == "nt", "Windows PowerShell PC inventory")
class PcInventoryTests(unittest.TestCase):
    def run_check(self, names=(), exit_code=0, credentials=False):
        with tempfile.TemporaryDirectory(prefix="th-pc-inventory-") as temporary:
            root = Path(temporary)
            windows = root / "product/windows"
            windows.mkdir(parents=True)
            script = windows / CHECK.name
            script.write_bytes(CHECK.read_bytes())
            if credentials:
                secret = root / "product/data/secrets/db.env"
                secret.parent.mkdir(parents=True)
                secret.write_text("SYNTHETIC SENTINEL - NOT A PASSWORD")
                site = root / "product/data/sites/toeflhouse.localhost/site_config.json"
                site.parent.mkdir(parents=True)
                site.write_text("{}")
            docker = root / "docker.cmd"
            docker.write_bytes((
                '@echo off\r\nif "%~1"=="info" exit /b 0\r\n'
                'if "%~1 %~2"=="volume ls" goto inventory\r\n'
                'exit /b 99\r\n:inventory\r\n'
                + ''.join(f'echo {name}\r\n' for name in names)
                + f'exit /b {exit_code}\r\n').encode())
            env = dict(os.environ)
            env["PATH"] = str(root) + os.pathsep + env.get("PATH", "")
            native_modules = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules"
            env["PSModulePath"] = str(native_modules) + os.pathsep + env.get("PSModulePath", "")
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if credentials:
                self.assertEqual(secret.read_text(), "SYNTHETIC SENTINEL - NOT A PASSWORD")
            else:
                self.assertFalse((root / "product/data").exists(), "Read-only check created data")
            return result.stdout

    def test_successful_absence_is_not_an_api_failure(self):
        output = self.run_check(names=("unrelated-synthetic-volume",))
        self.assertIn("No credential file or existing site/database observed", output)

    def test_existing_volume_without_credentials_still_blocks(self):
        output = self.run_check(names=("toefl-house-erp_db-data",))
        self.assertIn("BLOCKED: existing site/database but credential file missing", output)

    def test_inventory_failure_never_claims_fresh(self):
        output = self.run_check(exit_code=7)
        self.assertIn("local site or database storage could not be ruled out", output)
        self.assertNotIn("No credential file or existing site/database observed", output)

    def test_successful_absence_with_credentials_still_refuses_start(self):
        output = self.run_check(credentials=True)
        self.assertIn("NOT VERIFIED: credentials exist but the database volume could not be confirmed", output)
