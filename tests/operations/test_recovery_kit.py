"""Recovery kit authorization and portable encrypted recovery checks."""

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
          / "toefl_house" / "operations" / "recovery_kit.py")


def load_module():
    frappe = ModuleType("frappe")
    frappe.whitelist = lambda **kwargs: lambda fn: fn
    frappe.form_dict = {}
    frappe.local = SimpleNamespace(site="toeflhouse.localhost")
    frappe.request = SimpleNamespace(host="127.0.0.1:8000")
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.db = SimpleNamespace(get_value=Mock(return_value="System User"))
    audit = ModuleType("toefl_house.configuration.audit")
    audit.require_authority = Mock(return_value="owner@example.invalid")
    wrappers = ModuleType("werkzeug.wrappers")
    wrappers.Response = lambda data, **kwargs: SimpleNamespace(data=data, **kwargs)
    spec = importlib.util.spec_from_file_location("recovery_kit", SOURCE)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe, "werkzeug.wrappers": wrappers,
                                 "toefl_house.configuration.audit": audit}):
        spec.loader.exec_module(module)
    return module


class RecoveryKitTests(unittest.TestCase):
    def setUp(self):
        self.kit = load_module()
        self.kit._verified_factory_release = Mock(return_value=True)
        self.kit._recovery_policy_exists = Mock(return_value=False)
        self.phrase = "Disposable qualification phrase 74"

    def test_denied_requests_never_generate_or_keep_passphrase_in_form(self):
        for rejection in ("role", "release", "remote", "already-configured", "short"):
            with self.subTest(rejection=rejection):
                self.setUp()
                self.kit._generate_kit = Mock()
                supplied = self.phrase
                if rejection == "role":
                    self.kit.require_authority.side_effect = self.kit.frappe.PermissionError
                elif rejection == "release":
                    self.kit._verified_factory_release.return_value = False
                elif rejection == "remote":
                    self.kit.frappe.request.host = "unknown.example.invalid"
                elif rejection == "already-configured":
                    self.kit._recovery_policy_exists.return_value = True
                else:
                    supplied = "short"
                self.kit.frappe.form_dict["recovery_password"] = supplied
                with self.assertRaises((self.kit.frappe.PermissionError,
                                        self.kit.frappe.ValidationError)):
                    self.kit.create_recovery_kit(supplied)
                self.kit._generate_kit.assert_not_called()
                self.assertNotIn("recovery_password", self.kit.frappe.form_dict)

    def test_response_is_private_and_gpg_diagnostics_are_not_exposed(self):
        data = {"public_key": "TEST", "kit_b64": "TEST", "fingerprint": "TEST"}
        with patch.object(self.kit, "_generate_kit", return_value=data):
            result = self.kit.create_recovery_kit(self.phrase)
        self.assertEqual(json.loads(result.data), {"message": data})
        self.assertEqual(result.headers["Cache-Control"], "no-store, private")
        with patch.object(self.kit, "_generate_kit", side_effect=RuntimeError(self.phrase)):
            with self.assertRaises(self.kit.frappe.ValidationError) as raised:
                self.kit.create_recovery_kit(self.phrase)
        self.assertNotIn(self.phrase, str(raised.exception))

    @unittest.skipUnless(Path("/usr/bin/gpg").is_file() and Path("/usr/bin/gpgconf").is_file(),
                         "Linux image GnuPG is required")
    def test_portable_kit_decrypts_in_an_independent_keyring(self):
        secret = self.phrase.encode("ascii")
        result = self.kit._generate_kit(secret)
        with TemporaryDirectory() as home:
            try:
                gpg = self.kit._gpg
                gpg(home, "--import", data=result["public_key"].encode("ascii"))
                proof = b"Synthetic ERP recovery proof"
                encrypted = gpg(home, "--trust-model", "always", "--recipient",
                                result["fingerprint"], "--encrypt", data=proof)
                gpg(home, "--import", data=base64.b64decode(result["kit_b64"], validate=True))
                artifact = Path(home) / "proof.gpg"
                artifact.write_bytes(encrypted)
                with self.assertRaises(RuntimeError):
                    gpg(home, "--decrypt", str(artifact), secret=b"An incorrect recovery phrase")
                self.assertEqual(gpg(home, "--decrypt", str(artifact), secret=secret), proof)
            finally:
                subprocess.run(["/usr/bin/gpgconf", "--homedir", home, "--kill", "gpg-agent"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
