"""Keep patched Python advisory dependencies aligned in the shipped image and hosted audit.

These contracts do not replace native integration or the full-stack advisory
audit: they only prevent a stale source pin in one of the two environments.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
REMEDIATED_PINS = ("filelock==4.2.1", "setuptools==84.1.0")


class PythonAdvisoryPinTests(unittest.TestCase):
    def test_patched_pins_are_present_in_both_install_paths(self):
        dockerfile = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        hosted = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        for pin in REMEDIATED_PINS:
            with self.subTest(pin=pin):
                self.assertIn('"' + pin + '"', dockerfile)
                self.assertIn('"' + pin + '"', hosted)

    def test_no_global_python_dependency_override(self):
        dockerfile = (ROOT / "product/app.Dockerfile").read_text(encoding="utf-8")
        # Keep upgrades inside the isolated Frappe bench venv, not the host
        # or product-base build-tool environment.
        for pin in REMEDIATED_PINS:
            with self.subTest(pin=pin):
                self.assertNotIn("pip install --global " + pin, dockerfile)
        self.assertIn("--python /home/frappe/bench/env/bin/python --no-deps --upgrade", dockerfile)


if __name__ == "__main__":
    unittest.main()
