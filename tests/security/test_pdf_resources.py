"""Offline resource-policy regressions and installed-renderer wiring."""
from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pdf_resources", ROOT / "apps/toefl_house/toefl_house/pdf_resources.py")
pdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


class PDFResourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.asset = self.root / "assets"
        self.asset.mkdir()
        (self.asset / "print.css").write_text("p { color: navy }")
        self.calls = []
        def reader(path):
            self.calls.append(path)
            return PNG
        self.policy = pdf.ResourcePolicy(base_url="https://erp.example.test", assets={"/assets/app/": self.asset},
                                         attachment_reader=reader)

    def test_local_assets_and_authorized_images_without_network(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS must not be called")):
            self.assertEqual(self.policy("https://erp.example.test/assets/app/print.css?v=123")["mime_type"], "text/css")
            self.assertEqual(self.policy("https://erp.example.test/private/files/test.png")["string"], PNG)
            self.assertEqual(self.policy("data:image/png;base64," + base64.b64encode(PNG).decode())["string"], PNG)
        self.assertEqual(self.calls, ["/private/files/test.png"])
        self.policy.check()

    def test_deny_network_local_files_protocol_confusion_and_traversal(self):
        urls = [
            "file:///etc/passwd", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/", "http://2130706433/", "http://localhost/", "https://remote.example.test/logo.png",
            "ftp://erp.example.test/file", "https://erp.example.test/api/method/secret",
            "https://erp.example.test@evil.test/assets/app/print.css", "//erp.example.test/assets/app/print.css",
            "https://erp.example.test/assets/app/../secret.css", "https://erp.example.test/assets/app/%2e%2e/secret.css",
            "https://erp.example.test/assets/app/%252e%252e/secret.css", "https://erp.example.test/assets/app/%2fsecret.css",
            "https://erp.example.test/assets/app/%5csecret.css", "https://erp.example.test/assets/app/%00secret.css",
            "https://erp.example.test/assets/app/print.css\n", "https://erp.example.test/files/payload.svg",
            "data:image/svg+xml;base64,PHN2Zy8+", "data:text/html;base64,PHAvPg==",
            "data:image/png;base64," + base64.b64encode(b"%!PS EPS disguised as PNG").decode(),
            "https://erp.example.test/private/files/site_config.json", "https://erp.example.test/assets/app/secret.py",
        ]
        with patch("socket.getaddrinfo", side_effect=AssertionError("Network attempted")):
            for url in urls:
                with self.subTest(url=url), self.assertRaises(pdf.PDFResourceDenied):
                    self.policy(url)
        self.assertEqual(self.calls, [])
        with self.assertRaises(pdf.PDFResourceDenied):
            self.policy.check()

    def test_unresolved_bundle_path_denied_and_poisons_whole_pdf(self):
        # Regression for hosted Native run 38498528739: with --skip-assets and
        # an empty asset manifest, Frappe's print template emits the fallback
        # stylesheet link "/print_format.bundle.css". That is not a packaged
        # asset URL, so the policy must deny it and check() must refuse the
        # PDF rather than returning it without its stylesheet.
        with self.assertRaises(pdf.PDFResourceDenied):
            self.policy("https://erp.example.test/print_format.bundle.css")
        with self.assertRaises(pdf.PDFResourceDenied):
            self.policy.check()

    def test_nested_packaged_bundle_font_and_svg_assets_allowed(self):
        # A built bundle lives in a nested dist/css directory and its CSS can
        # in turn reference packaged fonts; packaged SVG images are also
        # legitimate. Every nested fetch goes through the same policy.
        bundle = self.asset / "dist" / "css"
        bundle.mkdir(parents=True)
        (bundle / "print_format.bundle.abcd1234.css").write_text("p { color: navy }")
        fonts = self.asset / "css" / "fonts"
        fonts.mkdir(parents=True)
        (fonts / "Synthetic.woff2").write_bytes(b"wOF2 synthetic font bytes")
        (self.asset / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS must not be called")):
            self.assertEqual(
                self.policy("https://erp.example.test/assets/app/dist/css/print_format.bundle.abcd1234.css")["mime_type"],
                "text/css")
            self.assertEqual(
                self.policy("https://erp.example.test/assets/app/css/fonts/Synthetic.woff2")["mime_type"],
                "font/woff2")
            self.assertEqual(
                self.policy("https://erp.example.test/assets/app/logo.svg")["mime_type"],
                "image/svg+xml")
        self.policy.check()

    def test_native_acceptance_maps_bundle_to_a_packaged_stylesheet(self):
        # The Native harness must not regress to an empty asset manifest: the
        # real renderer needs a packaged stylesheet to fetch in its
        # --skip-assets bench, and a legitimate packaged-asset PDF render
        # (stylesheet/font/SVG) must stay in the acceptance.
        source = (ROOT / "tools/native/security_acceptance.py").read_text()
        self.assertIn('"print_format.bundle.css": "/assets/frappe/css/tree.css"', source)
        self.assertNotIn('patch("frappe.utils.get_assets_json", return_value={})', source)
        self.assertIn("/assets/frappe/css/fonts/inter/inter.css", source)
        self.assertIn("/assets/frappe/images/frappe-framework-logo.svg", source)

    def test_symlink_file_and_directory_and_missing_resource_fail_closed(self):
        outside = self.root / "secret.css"
        outside.write_text("sensitive")
        (self.asset / "link.css").symlink_to(outside)
        (self.asset / "directory").symlink_to(self.root, target_is_directory=True)
        for name in ("link.css", "directory/secret.css", "missing.css"):
            with self.subTest(name=name), self.assertRaises(pdf.PDFResourceDenied):
                self.policy("https://erp.example.test/assets/app/" + name)
        with self.assertRaises(pdf.PDFResourceDenied):
            self.policy.check()

    def test_resource_count_and_byte_budgets(self):
        with patch.object(pdf, "MAX_RESOURCES", 1):
            self.policy("https://erp.example.test/assets/app/print.css")
            with self.assertRaises(pdf.PDFResourceDenied):
                self.policy("https://erp.example.test/assets/app/print.css")
        with patch.object(pdf, "MAX_RESOURCE_BYTES", 1):
            with self.assertRaises(pdf.PDFResourceDenied):
                self.policy("https://erp.example.test/assets/app/print.css")
        with patch.object(pdf, "MAX_TOTAL_BYTES", 1):
            with self.assertRaises(pdf.PDFResourceDenied):
                self.policy("https://erp.example.test/assets/app/print.css")

    def test_permission_denial_has_no_sensitive_error(self):
        def denied(path):
            raise PermissionError("synthetic-sensitive-value")
        self.policy.attachment_reader = denied
        with self.assertRaises(pdf.PDFResourceDenied) as caught:
            self.policy("https://erp.example.test/files/test.png")
        self.assertNotIn("synthetic-sensitive-value", str(caught.exception))
        self.assertNotIn("test.png", str(caught.exception))

    def test_production_factory_binds_attachments_to_target_and_checks_file_permission(self):
        private = self.root / "private"
        private.mkdir()
        (private / "test.png").write_bytes(PNG)
        doc = types.SimpleNamespace(doctype="ToDo", name="synthetic-target")
        permissions = []
        attachment = types.SimpleNamespace(is_private=1, check_permission=lambda action: permissions.append(action))
        queries = []
        def lookup(doctype, **kwargs):
            queries.append((doctype, kwargs))
            return ["synthetic-file"]
        frappe = types.SimpleNamespace(
            get_installed_apps=lambda: [], get_all=lookup,
            get_doc=lambda *args: attachment,
            has_permission=lambda *args: True,
            get_site_path=lambda *args: str(private),
        )
        with patch.dict(sys.modules, {"frappe": frappe}):
            policy = pdf.resource_policy(doc, "https://erp.example.test")
            self.assertEqual(policy("https://erp.example.test/private/files/test.png")["string"], PNG)
            self.assertEqual(permissions, ["read"])
            self.assertEqual(queries[0][1]["filters"], {
                "file_url": "/private/files/test.png", "attached_to_doctype": "ToDo",
                "attached_to_name": "synthetic-target",
            })
            for result in ([], ["duplicate-one", "duplicate-two"]):
                with patch.object(frappe, "get_all", return_value=result), patch.object(pdf, "_read_beneath") as read:
                    with self.assertRaises(pdf.PDFResourceDenied):
                        policy("https://erp.example.test/private/files/test.png")
                    read.assert_not_called()
            with patch.object(frappe, "has_permission", return_value=False), patch.object(pdf, "_read_beneath") as read:
                with self.assertRaises(pdf.PDFResourceDenied):
                    policy("https://erp.example.test/private/files/test.png")
                read.assert_not_called()
            attachment.is_private = 0
            with patch.object(pdf, "_read_beneath") as read:
                with self.assertRaises(pdf.PDFResourceDenied):
                    policy("https://erp.example.test/private/files/test.png")
                read.assert_not_called()

    def test_every_vendor_html_constructor_and_final_output_guarded(self):
        from tools.foundation.secure_weasyprint import apply_guard
        import ast
        source = self.root / "weasyprint.py"
        source.write_bytes((ROOT / "tests/security/fixtures/frappe_weasyprint_988e54f3.py").read_bytes())
        apply_guard(source)
        tree = ast.parse(source.read_text())
        html = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "HTML"]
        self.assertEqual(len(html), 2)
        for call in html:
            self.assertIn("url_fetcher", [kw.arg for kw in call.keywords])
        self.assertIn("self.resource_policy.check()\n\t\treturn pdf", source.read_text())


if __name__ == "__main__":
    unittest.main()
