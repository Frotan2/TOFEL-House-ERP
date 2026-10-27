"""Run the dependency-free portal DOM contract in the normal owned suite."""
import shutil
import subprocess
import unittest
from pathlib import Path


class PortalViewContract(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for the portal DOM contract")
    def test_portal_dom_and_child_switch_races(self):
        script = Path(__file__).with_suffix(".cjs")
        result = subprocess.run([shutil.which("node"), str(script)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Portal DOM/promise contracts OK", result.stdout)
