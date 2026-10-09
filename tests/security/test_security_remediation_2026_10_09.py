"""Executable regressions for the installed security seams (no live site)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/foundation"))
import secure_hrms  # noqa: E402
import secure_weasyprint  # noqa: E402


class CoverageWiringTests(unittest.TestCase):
    def test_public_lock_replay_records_open_findings_without_waiver(self):
        report = json.loads((ROOT / "docs/engineering/evidence/sec-deps-01/"
                             "audit-expansion-replay-2026-10-09.json").read_text())
        self.assertEqual(report["untriaged"], len(report["open_matches"]))
        self.assertEqual(report["unique_open_ghsa"], len({r["ghsa"] for r in report["open_matches"]}))
        self.assertEqual(report["total_matches_union"],
                         report["closed_by_existing_triage"] + report["untriaged"])
        for row in report["open_matches"]:
            self.assertTrue(row["versions"])
            self.assertTrue(row["ghsa"].startswith("GHSA-"))

    def test_every_shipped_nested_tree_enters_the_fail_closed_gate(self):
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text()
        for app, tree in (("education", "frontend"), ("hrms", "frontend"),
                          ("hrms", "roster"), ("erpnext", "banking")):
            self.assertIn(f'("{app}", "{tree}")', runtime)
        self.assertIn('Missing required built frontend dependency tree:', runtime)
        self.assertIn('if stack_audit["status"] != "pass":', runtime)

    def test_production_remains_rejected_and_login_override_wired(self):
        self.assertEqual(json.loads((ROOT / "docs/owner-decisions.json").read_text())["production_state"], "REJECT")
        hooks = (ROOT / "apps/toefl_house/toefl_house/hooks.py").read_text()
        self.assertIn('"frappe.integrations.oauth2_logins.login_via_office365": '
                      '"toefl_house.social_login.login_via_office365"', hooks)


class HrmsEditorTests(unittest.TestCase):
    def tree(self, base):
        for tree in ("frontend", "roster"):
            for name, version in (("prosemirror-view", "1.31.3"), ("prosemirror-model", "1.19.1")):
                folder = base / tree / "node_modules" / name
                folder.mkdir(parents=True)
                (folder / "package.json").write_text(json.dumps({"name": name, "version": version}))
        nested = base / "frontend/node_modules/example/node_modules/prosemirror-view"
        nested.mkdir(parents=True)
        (nested / "package.json").write_text(json.dumps({"name": "prosemirror-view", "version": "1.31.3"}))
        return nested

    def test_rejects_old_nested_copy_and_missing_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.tree(base)
            with self.assertRaisesRegex(ValueError, "Vulnerable prosemirror-view"):
                secure_hrms.verify(base)
            import shutil
            shutil.rmtree(base / "roster/node_modules")
            with self.assertRaisesRegex(ValueError, "Missing HRMS dependency root"):
                secure_hrms.verify(base)

    def test_integrity_pinned_replacement_including_nested_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            nested = self.tree(base)
            self.assertEqual(secure_hrms.patch(base), {"prosemirror-view": 3, "prosemirror-model": 2})
            self.assertEqual(secure_hrms.verify(base)["prosemirror-view"], 3)
            manifest = json.loads((nested / "package.json").read_text())
            self.assertEqual(manifest["version"], "1.42.3")
            self.assertIn("^1.25.8", manifest["dependencies"]["prosemirror-model"])
            (nested / "dist/index.js").write_text("tampered editor implementation")
            with self.assertRaisesRegex(ValueError, "code differs"):
                secure_hrms.verify(base)
            (nested / "package.json").write_text(json.dumps({"name": "prosemirror-view", "version": "1.31.3"}))
            with self.assertRaisesRegex(ValueError, "Vulnerable prosemirror-view"):
                secure_hrms.verify(base)

    def test_rejects_tampered_tarball_before_removing_old_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.tree(base)
            with patch.object(secure_hrms, "urlopen") as request:
                request.return_value.__enter__.return_value.read.return_value = b"tampered"
                request.return_value.read.return_value = b"tampered"
                with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
                    secure_hrms.patch(base)
            self.assertEqual(json.loads((base / "frontend/node_modules/prosemirror-view/package.json").read_text())["version"], "1.31.3")


class WeasyPrintTests(unittest.TestCase):
    def test_guard_requires_exact_pinned_source_and_instruments_constructor(self):
        source = ROOT / "tests/security/fixtures/frappe_weasyprint_988e54f3.py"
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "weasyprint.py"
            dest.write_bytes(source.read_bytes())
            secure_weasyprint.apply_guard(dest)
            secure_weasyprint.verify_guard(dest)
            body = dest.read_text()
            self.assertIn("authorize_weasyprint(print_format, doc)", body)
            self.assertLess(body.index("authorize_weasyprint(print_format, doc)"), body.index("self.base_url ="))
            frappe = types.ModuleType("frappe")
            frappe._ = lambda text: text
            frappe.whitelist = lambda **kwargs: lambda fn: fn
            utils = types.ModuleType("frappe.utils")
            frappe.utils = utils
            click = types.ModuleType("click")
            owned = types.ModuleType("toefl_house")
            printing = types.ModuleType("toefl_house.printing")
            calls = []
            def deny(fmt, doc):
                calls.append((fmt, doc))
                raise PermissionError("print denied")
            printing.authorize_weasyprint = deny
            with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils,
                                          "click": click, "toefl_house": owned,
                                          "toefl_house.printing": printing}):
                spec = importlib.util.spec_from_file_location("patched_vendor", dest)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                target = object()
                with self.assertRaisesRegex(PermissionError, "print denied"):
                    module.PrintFormatGenerator("beta", target)
                self.assertEqual(calls, [("beta", target)])
            with self.assertRaisesRegex(ValueError, "source changed"):
                secure_weasyprint.apply_guard(dest)
            dest.write_text("class PrintFormatGenerator: pass")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                secure_weasyprint.verify_guard(dest)
            with self.assertRaisesRegex(ValueError, "source changed"):
                secure_weasyprint.apply_guard(dest)

    def test_gate_and_vendor_signatures(self):
        class Document:
            doctype = "Expense Claim"
            def __init__(self, allowed=True):
                self.allowed = allowed
            def check_permission(self, action):
                if not self.allowed:
                    raise PermissionError(action)

        formats = {"beta": {"print_format_builder_beta": True, "doc_type": "Expense Claim"},
                   "other": {"print_format_builder_beta": False, "doc_type": "Expense Claim"},
                   "wrong": {"print_format_builder_beta": True, "doc_type": "User"}}
        frappe = types.ModuleType("frappe")
        frappe.PermissionError = PermissionError
        frappe.get_doc = lambda doctype, name: formats[name]
        frappe.has_permission = lambda doctype, action, doc: getattr(doc, "role_allowed", True)
        frappe.throw = lambda message, cls: (_ for _ in ()).throw(cls(message))
        frappe._ = lambda message: message
        utils = types.ModuleType("frappe.utils")
        vendor = types.ModuleType("frappe.utils.weasyprint")
        calls = []
        vendor.download_pdf = lambda *args: calls.append(args)
        vendor.get_html = lambda *args: calls.append(args)
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils,
                                      "frappe.utils.weasyprint": vendor}):
            spec = importlib.util.spec_from_file_location("tested_printing", ROOT / "apps/toefl_house/toefl_house/printing.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.authorize_weasyprint("beta", Document())
            for name in ("other", "wrong"):
                with self.assertRaises(PermissionError):
                    module.authorize_weasyprint(name, Document())
            with self.assertRaises(PermissionError):
                module.authorize_weasyprint("beta", Document(False))
            flagged = Document()
            flagged.role_allowed = False  # doc.check_permission alone would pass
            with self.assertRaises(PermissionError):
                module.authorize_weasyprint("beta", flagged)
            module.download_pdf("Expense Claim", "EC-1", "beta")
            module.get_html("Expense Claim", "EC-1", "beta", "L")
        self.assertEqual(calls, [("Expense Claim", "EC-1", "beta", None),
                                 ("Expense Claim", "EC-1", "beta", "L")])


class Office365Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import jwt
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError as exc:
            raise unittest.SkipTest("PyJWT[crypto] needed for cryptographic tests") from exc
        cls.jwt = jwt
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        frappe = types.ModuleType("frappe")
        frappe.whitelist = lambda **kwargs: lambda fn: fn
        frappe.PermissionError = PermissionError
        frappe.throw = lambda message, cls: (_ for _ in ()).throw(cls(message))
        frappe._ = lambda message: message
        with patch.dict(sys.modules, {"frappe": frappe}):
            spec = importlib.util.spec_from_file_location("tested_social_login", ROOT / "apps/toefl_house/toefl_house/social_login.py")
            cls.login = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.login)

    def signed(self, **overrides):
        import time
        tid = "12345678-1234-1234-1234-123456789abc"
        claims = {"tid": tid, "iss": f"https://sts.windows.net/{tid}/",
                  "aud": "app-client", "iat": int(time.time()), "exp": int(time.time()) + 300,
                  "email": "owner@example.test"}
        claims.update(overrides)
        return self.jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test-key"})

    def check(self, token):
        with patch.object(self.jwt, "PyJWKClient") as client:
            client.return_value.get_signing_key_from_jwt.return_value.key = self.key.public_key()
            return self.login.verify_office365_id_token(token, "app-client")

    def test_signed_claims_accepted(self):
        self.assertEqual(self.check(self.signed())["email"], "owner@example.test")

    def test_tampering_wrong_key_audience_issuer_expiry_and_tenant_rejected(self):
        good = self.signed()
        parts = good.split(".")
        tampered = self.jwt.utils.base64url_encode(b'{"aud":"app-client","tid":"12345678-1234-1234-1234-123456789abc"}').decode()
        failures = [parts[0] + "." + tampered + "." + parts[2],
                    self.jwt.encode({"aud": "app-client"}, self.other, algorithm="RS256"),
                    self.signed(aud="other"), self.signed(iss="https://attacker.invalid/"),
                    self.signed(exp=1), self.signed(tid="common")]
        for token in failures:
            with self.subTest(token=failures.index(token)):
                with self.assertRaises(Exception):
                    self.check(token)

    def test_callback_only_authenticates_after_verification_and_preserves_state(self):
        frappe = sys.modules.get("frappe") or types.ModuleType("frappe")
        frappe.PermissionError = PermissionError
        frappe.throw = lambda message, cls: (_ for _ in ()).throw(cls(message))
        frappe._ = lambda message: message
        oauth = types.ModuleType("frappe.utils.oauth")
        oauth.get_oauth2_flow = lambda provider: types.SimpleNamespace(
            get_auth_session=lambda **kwargs: types.SimpleNamespace(
                access_token_response=types.SimpleNamespace(text=json.dumps({"id_token": "token"}))))
        oauth.get_redirect_uri = lambda provider: "https://example.test/callback"
        oauth.get_oauth_keys = lambda provider: {"client_id": "app-client"}
        oauth.get_email = lambda info: info.get("email")
        oauth.login_oauth_user = lambda *args, **kwargs: log.append((args, kwargs))
        utils = types.ModuleType("frappe.utils")
        utils.oauth = oauth
        integrations = types.ModuleType("frappe.integrations")
        handlers = types.ModuleType("frappe.integrations.oauth2_logins")
        handlers.decoder_compat = lambda data: data
        log = []
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils,
                                      "frappe.utils.oauth": oauth, "frappe.integrations": integrations,
                                      "frappe.integrations.oauth2_logins": handlers}):
            with patch.object(self.login, "verify_office365_id_token", return_value={"email": "owner@example.test"}) as check:
                self.login.login_via_office365("authorization-code", "single-use-state")
                check.assert_called_once_with("token", "app-client")
            self.assertEqual(log, [(({"email": "owner@example.test"},),
                                    {"provider": "office_365", "state": "single-use-state"})])
            with patch.object(self.login, "verify_office365_id_token", side_effect=ValueError("sensitive data")):
                with self.assertRaisesRegex(PermissionError, "identity verification failed") as denied:
                    self.login.login_via_office365("authorization-code", "single-use-state")
                self.assertNotIn("sensitive data", str(denied.exception))
            self.assertEqual(len(log), 1, "a rejected token must not establish a login")

    def test_none_algorithm_and_untrusted_key_url_rejected(self):
        token = self.jwt.encode({"aud": "app-client"}, key="", algorithm="none")
        with patch.object(self.jwt, "PyJWKClient") as client:
            with self.assertRaisesRegex(ValueError, "algorithm"):
                self.login.verify_office365_id_token(token, "app-client")
            client.assert_not_called()
        with patch.object(self.jwt, "PyJWKClient") as client:
            client.return_value.get_signing_key_from_jwt.return_value.key = self.key.public_key()
            self.login.verify_office365_id_token(self.signed(), "app-client")
            client.assert_called_once_with(self.login.MICROSOFT_JWKS, timeout=10)
