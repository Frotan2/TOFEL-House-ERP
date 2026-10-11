"""Native security checks run only on a disposable site, never locally."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/native/security_acceptance.py"


class SecuritySiteAcceptanceWiring(TestCase):
    def test_runner_invokes_installed_seams_after_site_creation(self):
        runner = (ROOT / "tools/native/run_native.py").read_text()
        self.assertIn("run('security-site-acceptance',", runner)
        self.assertIn("ROOT/'tools/native/security_acceptance.py'", runner)
        self.assertLess(runner.index("bench('migrate-replay-"),
                        runner.index("run('security-site-acceptance',"))
        source = SCRIPT.read_text()
        for path in ("get_html(\"ToDo\"", "download_pdf(\"ToDo\"",
                     "PrintFormatGenerator(fmt.name, todo)",
                     "verify_office365_id_token(wrong", "login_via_office365(",
                     "frappe.db.rollback()"):
            self.assertIn(path, source)
        # Native uses --skip-assets: include_style() calls .get() on a missing
        # manifest unless this synthetic-only fixture is set before preview.
        self.assertIn('patch("frappe.utils.get_assets_json", return_value={})', source)
        self.assertLess(source.index('patch("frappe.utils.get_assets_json"'),
                        source.index('preview = get_html("ToDo"'))
        self.assertIn("SECURITY-SITE-ACCEPTANCE-FAILED", source)

    def test_refuses_local_or_non_disposable_site_before_importing_frappe(self):
        spec = importlib.util.spec_from_file_location("native_security_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "CI": "1"}):
            with self.assertRaisesRegex(RuntimeError, "Hosted synthetic runner only"):
                module.main()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "CI": "1",
                                  "RUNNER_TEMP": "/tmp/never-a-real-site"}):
            with self.assertRaisesRegex(RuntimeError, "Refusing non-disposable site path"):
                module.main()
