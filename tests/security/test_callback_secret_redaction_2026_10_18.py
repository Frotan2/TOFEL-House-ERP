"""A11: the Office 365 callback must redact code and state from the request form (2026-10-18).

Local unit level, with a fake frappe module (the same loading pattern as the 2026-10-09
remediation tests). The real-site proof is in tools/native/security_acceptance.py, which
writes a real Error Log snapshot and reads it back in CI.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/toefl_house/toefl_house/social_login.py"


def _fake_frappe():
    frappe = types.ModuleType("frappe")
    frappe.conf = {}
    frappe.local = types.SimpleNamespace(form_dict={})
    frappe.whitelist = lambda **kwargs: (lambda fn: fn)
    frappe._ = lambda text, *args: text

    class PermissionError(Exception):  # noqa: A001 - mirrors frappe.PermissionError
        pass

    def throw(message, exc=None):
        raise (exc or Exception)(message)

    frappe.PermissionError = PermissionError
    frappe.throw = throw
    frappe.logger = lambda name: types.SimpleNamespace(warning=lambda *a, **k: None)
    frappe.get_all = lambda *a, **k: []
    frappe.get_doc = lambda *a, **k: None
    return frappe


class CallbackRedactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frappe = _fake_frappe()
        with patch.dict(sys.modules, {"frappe": cls.frappe}):
            spec = importlib.util.spec_from_file_location("tested_social_login_a11", MODULE)
            cls.login = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.login)

    def setUp(self):
        self.frappe.local.form_dict = {}

    def test_helper_redacts_code_and_state_and_nothing_else(self):
        self.frappe.local.form_dict = {"code": "SYNTH-CODE", "state": "SYNTH-STATE", "cmd": "x", "other": "keep"}
        self.login.redact_callback_form()
        self.assertEqual(self.frappe.local.form_dict["code"], "********")
        self.assertEqual(self.frappe.local.form_dict["state"], "********")
        self.assertEqual(self.frappe.local.form_dict["cmd"], "x")
        self.assertEqual(self.frappe.local.form_dict["other"], "keep")

    def test_helper_tolerates_missing_or_non_dict_form(self):
        self.frappe.local = types.SimpleNamespace()
        self.login.redact_callback_form()  # no attribute: must not raise
        self.frappe.local = types.SimpleNamespace(form_dict=None)
        self.login.redact_callback_form()
        self.frappe.local = types.SimpleNamespace(form_dict={"state": "S"})
        self.login.redact_callback_form()
        self.assertEqual(self.frappe.local.form_dict, {"state": "********"})

    def test_wrapper_redacts_before_a_denial_can_be_snapshotted(self):
        self.frappe.local.form_dict = {"code": "SYNTH-CODE", "state": "SYNTH-STATE"}
        oauth = types.ModuleType("frappe.utils.oauth")

        def failing_flow(provider):
            # Whatever the provider does, the form must already be redacted at this point.
            self.assertEqual(self.frappe.local.form_dict["code"], "********")
            self.assertEqual(self.frappe.local.form_dict["state"], "********")
            raise RuntimeError("synthetic provider failure")

        oauth.get_oauth2_flow = failing_flow
        utils = types.ModuleType("frappe.utils")
        utils.oauth = oauth
        handlers = types.ModuleType("frappe.integrations.oauth2_logins")
        handlers.decoder_compat = lambda data: data
        with patch.dict(sys.modules, {"frappe.utils": utils, "frappe.utils.oauth": oauth,
                                      "frappe.integrations.oauth2_logins": handlers}):
            with self.assertRaises(self.frappe.PermissionError):
                self.login.login_via_office365("SYNTH-CODE", "SYNTH-STATE")
        self.assertNotIn("SYNTH-CODE", repr(self.frappe.local.form_dict))
        self.assertNotIn("SYNTH-STATE", repr(self.frappe.local.form_dict))

    def test_wrapper_still_receives_the_real_values_as_arguments(self):
        # Redaction must not change what the sign-in itself uses.
        seen = {}
        oauth = types.ModuleType("frappe.utils.oauth")

        def capture_flow(provider):
            seen["flow_provider"] = provider
            raise RuntimeError("stop after capture")

        oauth.get_oauth2_flow = capture_flow
        utils = types.ModuleType("frappe.utils")
        utils.oauth = oauth
        handlers = types.ModuleType("frappe.integrations.oauth2_logins")
        handlers.decoder_compat = lambda data: data
        self.frappe.local.form_dict = {"code": "SYNTH-CODE", "state": "SYNTH-STATE"}
        with patch.dict(sys.modules, {"frappe.utils": utils, "frappe.utils.oauth": oauth,
                                      "frappe.integrations.oauth2_logins": handlers}):
            with self.assertRaises(self.frappe.PermissionError):
                self.login.login_via_office365("SYNTH-CODE", "SYNTH-STATE")
        self.assertEqual(seen["flow_provider"], "office_365")

    def test_wrapper_calls_redaction_before_anything_else(self):
        source = MODULE.read_text(encoding="utf-8")
        body = source.split("def login_via_office365(code: str, state: str):", 1)[1]
        self.assertIn("redact_callback_form()", body)
        self.assertLess(body.index("redact_callback_form()"), body.index("from frappe.utils import oauth"),
                        "redaction must precede the provider flow")


if __name__ == "__main__":
    unittest.main()
