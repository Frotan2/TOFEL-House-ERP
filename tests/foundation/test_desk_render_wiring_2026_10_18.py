"""Desk rendering check for a stored hostile HRMS value is wired and cannot pass blind (2026-10-18).

Static tests. The browser run itself happens only in the Foundation runtime workflow (Actions
runner, real Chromium, real Desk). These tests pin the properties that make a green run meaningful:
the step is a hard failure, the detector has a positive control, the browser script refuses to run
outside Actions, and the fixture creates one dedicated user and never edits an existing one.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "tools/foundation/runtime_install.py"
FIXTURE = ROOT / "tools/foundation/runtime_desk_render.py"
BROWSER = ROOT / "tools/foundation/desk_render_check.mjs"


class DeskRenderWiringTests(unittest.TestCase):
    def test_step_is_a_hard_failure_not_a_diagnostic(self):
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn('run("browser-desk-hrms-stored-html"', text)
        # The browser step must not sit inside a try block that appends to diagnostic_failures.
        block = text[text.index('run("browser-desk-hrms-stored-html"') - 400:
                     text.index('run("browser-desk-hrms-stored-html"')]
        self.assertNotIn("diagnostic_failures", block)
        self.assertIn('run("desk-render-fixture"', text)

    def test_browser_check_has_positive_control_before_any_negative_claim(self):
        text = BROWSER.read_text(encoding="utf-8")
        control = text.index("detector-positive-control")
        for negative in ("'first-open'", "'reload'"):
            self.assertLess(control, text.index(negative))
        self.assertIn("window.__synthetic_control=1", text)
        self.assertIn("the check is blind", text)

    def test_browser_check_refuses_to_run_outside_actions_and_checks_each_claim(self):
        text = BROWSER.read_text(encoding="utf-8")
        self.assertIn("process.env.GITHUB_ACTIONS !== 'true'", text)
        for claim in ("executed", "inline_handlers", "javascript_links", "srcdoc_frames",
                      "formatting_rendered", "dialogs"):
            self.assertIn(claim, text)
        self.assertIn("process.exitCode = 1", text)

    def test_markup_checks_are_scoped_to_the_description_field_and_require_it(self):
        text = BROWSER.read_text(encoding="utf-8")
        self.assertIn(r"""const fieldSelector = '[data-fieldname="description"]';""", text)
        self.assertIn("requireCondition(state.field_found,", text)
        self.assertIn("field_javascript_links", text)
        self.assertIn("page_wide_javascript_links", text)

    def test_fixture_creates_one_dedicated_user_and_never_edits_existing_roles(self):
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertIn('USER = "validation-hr-render@example.test"', text)
        self.assertEqual(len(re.findall(r'"doctype": "User"', text)), 1)
        self.assertNotIn("roles.append", text)
        self.assertNotIn("set_value(\"User\"", text)
        # Stored-value markers are refused before the browser step runs.
        for marker in ("onerror", "onload", "javascript:", "<script", "srcdoc", "<iframe"):
            self.assertIn(f'"{marker}"', text)


if __name__ == "__main__":
    unittest.main()
