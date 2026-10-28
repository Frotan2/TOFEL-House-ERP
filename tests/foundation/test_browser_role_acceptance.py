"""Keep the synthetic browser fixture from mutating a local/operational site."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.native import browser_role_acceptance as browser


class BrowserFixtureBoundary(unittest.TestCase):
    def test_prepare_refuses_outside_hosted_ci_before_importing_frappe(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "hosted CI"):
                browser.prepare()

    def test_prepare_refuses_a_different_site_root(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "CI": "1"}, clear=True):
            with patch.object(Path, "cwd", return_value=Path("/some/operational/sites")):
                with self.assertRaisesRegex(RuntimeError, "fixture path"):
                    browser.prepare()

    def test_browser_refuses_network_endpoint_before_launching(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "CI": "1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "loopback"):
                browser.qualify("https://erp.example.test", Path("unused"))


if __name__ == "__main__":
    unittest.main()
