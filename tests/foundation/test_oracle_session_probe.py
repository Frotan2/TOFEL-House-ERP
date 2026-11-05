"""Frappe v16 authenticated logout must keep the CSRF protection enabled.

Pure tests only: no Frappe site or network calls. The native ARM64 Compose
qualification separately exercises login, realtime and logout over TLS.
"""
import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "oracle" / "session_probe.py"
spec = importlib.util.spec_from_file_location("oracle_session_probe_under_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OracleSessionProbeTest(unittest.TestCase):
    def test_extract_real_desk_form_and_refuse_ambiguous_or_missing_token(self):
        token = b"1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d"
        html = b'<script>frappe.csrf_token = "' + token + b'";</script>'
        self.assertEqual(module.extract_desk_csrf_token(html), token.decode())
        for invalid in (
                b"",
                b'<script>frappe.csrf_token = "";</script>',
                html + html,
                b'<script>frappe.csrf_token = "malformed token";</script>',
                b'<script>frappe.csrf_token = "abc";</script>',
                b'x' * (2 * 1024 * 1024 + 1)):
            with self.subTest(invalid_length=len(invalid)):
                with self.assertRaises(ValueError):
                    module.extract_desk_csrf_token(invalid)

    def test_logout_uses_cookie_authenticated_post_with_csrf_and_guest_check(self):
        source = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        probe = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "probe")
        code = ast.get_source_segment(source, probe)
        self.assertIn('browser.open(base + "/app"', code)
        self.assertIn('csrf_token = extract_desk_csrf_token(desk)', code)
        self.assertIn('Request(base + "/api/method/logout", method="POST", data=b""', code)
        self.assertIn('"X-Frappe-CSRF-Token": csrf_token', code)
        self.assertNotIn('browser.open(base + "/api/method/logout"', code)
        self.assertIn('json.load(reply).get("message") != "Guest"', code)
        self.assertNotIn('ignore_csrf', source)
        self.assertNotIn('allowed_referrers', source)


if __name__ == "__main__":
    unittest.main()
