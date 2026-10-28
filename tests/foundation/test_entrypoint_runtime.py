"""Execute the production shell entrypoint with fake system binaries.

An earlier image successfully built but all services failed on first boot:
POSIX sh cannot `exec` a shell function, so `exec run_frappe` exited 127.
These tests exercise the actual shell instead of only checking source strings.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[2] / "product" / "entrypoint.sh"


@unittest.skipUnless(shutil.which("sh"), "requires a POSIX shell")
class EntrypointRuntimeTests(unittest.TestCase):
    def test_every_service_invokes_non_root_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            for name, content in (
                ("su", "#!/bin/sh\\nprintf 'INVOKED_SU %s\\n' \"$*\"\\n"),
                ("chown", "#!/bin/sh\\nexit 0\\n"),
            ):
                program = tools / name
                program.write_text(content.replace("\\n", "\n"), encoding="utf-8")
                program.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")

            for service in ("bootstrap", "web", "worker", "scheduler", "socketio"):
                with self.subTest(service=service):
                    result = subprocess.run(
                        ["sh", str(ENTRYPOINT), service],
                        env=env, capture_output=True, text=True, timeout=15,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        result.stdout.count("INVOKED_SU "),
                        3 if service == "web" else 1,
                        result.stdout,
                    )
                    self.assertIn("-s /bin/sh frappe -c ", result.stdout)

    def test_unknown_service_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            chown = Path(directory) / "chown"
            chown.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            chown.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            result = subprocess.run(
                ["sh", str(ENTRYPOINT), "unexpected-service"],
                env=env, capture_output=True, text=True, timeout=15,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unknown service:", result.stderr)
