"""The official TOEFL House logo and colours are applied and stored locally.

Covers the desk/sign-in hooks, the colour tokens, the printed letter head
(including the preservation rule for existing installations) and the Windows
launcher, shortcut, installer and package allowlists.
"""
import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
IMAGES = APP / "public/images"
OFFICIAL_RED = "#e40613"
RETIRED = ("#c8102e", "#a00d25", "#b01621", "th_logo.svg")


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class WebBrandTests(unittest.TestCase):
    def test_official_logo_is_stored_locally_and_every_hook_path_exists(self):
        self.assertTrue((ROOT / "docs/brand/toefl-house-logo-official.png").is_file())
        hooks = read("apps/toefl_house/toefl_house/hooks.py")
        paths = re.findall(r'"/assets/toefl_house/(images/[^"]+)"', hooks)
        self.assertGreaterEqual(len(paths), 3)
        for relative in paths:
            with self.subTest(path=relative):
                self.assertTrue((APP / "public" / relative).is_file())
        self.assertIn("toefl_house_logo_square.png", hooks)
        self.assertIn('"favicon"', hooks)
        self.assertIn('"splash_image"', hooks)

    def test_logo_files_are_real_images(self):
        signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".ico": b"\x00\x00\x01\x00"}
        files = [*IMAGES.iterdir(), ROOT / "product/windows/toefl-house.ico",
                 ROOT / "product/windows/toefl-house-logo.png"]
        for path in files:
            with self.subTest(path=path.name):
                self.assertTrue(path.read_bytes().startswith(signatures[path.suffix]))

    def test_official_red_is_the_single_accent_and_old_values_are_gone(self):
        brand = read("apps/toefl_house/toefl_house/public/css/th_brand.css")
        design = read("apps/toefl_house/toefl_house/public/css/th_design_system.css")
        self.assertIn("--th-brand: " + OFFICIAL_RED, brand)
        self.assertIn("--th-accent: " + OFFICIAL_RED, design)
        self.assertIn("--btn-primary: var(--th-brand)", brand)
        for path in ("apps/toefl_house/toefl_house/public/css/th_brand.css",
                     "apps/toefl_house/toefl_house/public/css/th_design_system.css",
                     "apps/toefl_house/toefl_house/hooks.py",
                     "apps/toefl_house/toefl_house/install.py",
                     "product/windows/TOEFL House ERP.ps1"):
            for value in RETIRED:
                with self.subTest(path=path, value=value):
                    self.assertNotIn(value, read(path))

    def test_logo_is_never_stretched_on_the_sign_in_page(self):
        brand = read("apps/toefl_house/toefl_house/public/css/th_brand.css")
        rule = brand.split(".page-card-head img.app-logo {", 1)[1].split("}", 1)[0]
        self.assertIn("width: auto", rule)
        self.assertIn("object-fit: contain", rule)


class LetterHeadTests(unittest.TestCase):
    def load(self, source=None, content=None):
        """``source`` None means no existing header; content None means the seeded text."""
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        state = {"saved": [], "inserted": []}

        class Doc(SimpleNamespace):
            def save(self, ignore_permissions=False):
                state["saved"].append(self.content)

            def insert(self, ignore_permissions=False):
                state["inserted"].append(self.content)

        existing = None
        if source is not None:
            existing = Doc(source=source, content=content)

        def get_doc(arg, name=None):
            if isinstance(arg, dict):
                return Doc(**arg)
            return existing

        stub = types.ModuleType("frappe")
        stub.get_app_path = lambda app, *parts: str(APP.joinpath(*parts))
        stub.get_doc = get_doc
        stub.db = SimpleNamespace(
            exists=lambda doctype, filters=None: existing is not None if filters == "The TOEFL House" else True,
            set_single_value=lambda *args: None,
            get_value=lambda *args: "AFN",
        )
        sys.modules["frappe"] = stub
        spec = importlib.util.spec_from_file_location("toefl_house_install_brand", APP / "install.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if existing is not None and existing.content is None:
            existing.content = module.SEEDED_TEXT_LETTER_HEAD
        return module, state

    def test_header_embeds_the_logo_and_fits_the_default_value_column(self):
        module, _state = self.load()
        html = module.institute_letter_head_html()
        self.assertIn('src="data:image/jpeg;base64,', html)
        self.assertIn("width:auto", html)
        # Frappe copies the default header into a MariaDB TEXT column (64 KB).
        self.assertLess(len(html.encode("utf-8")), 60000)

    def test_unedited_seeded_header_is_upgraded_once(self):
        module, state = self.load("HTML")
        module.upgrade_institute_letter_head()
        self.assertEqual(len(state["saved"]), 1)
        self.assertIn("data:image/jpeg;base64,", state["saved"][0])

    def test_owner_edited_header_is_preserved(self):
        for source, content in (("HTML", "<p>Owner header</p>"), ("Image", None)):
            module, state = self.load(source, content)
            module.upgrade_institute_letter_head()
            self.assertEqual(state["saved"], [])

    def test_upgrade_runs_on_every_migrate(self):
        install = read("apps/toefl_house/toefl_house/install.py")
        after_migrate = install.split("def after_migrate():", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("upgrade_institute_letter_head()", after_migrate)


class WindowsBrandTests(unittest.TestCase):
    def test_brand_files_travel_in_both_package_allowlists(self):
        for path in ("tools/release/create_customer_package.py",
                     "product/windows/Prepare Customer Package.ps1"):
            text = read(path)
            for name in ("product/windows/toefl-house.ico", "product/windows/toefl-house-logo.png"):
                with self.subTest(path=path, name=name):
                    self.assertIn('"' + name + '"', text)

    def test_launcher_shortcut_and_installers_use_the_logo(self):
        launcher = read("product/windows/TOEFL House ERP.ps1")
        self.assertIn("toefl-house.ico", launcher)
        self.assertIn("toefl-house-logo.png", launcher)
        self.assertIn("PictureBoxSizeMode]::Zoom", launcher)
        self.assertIn("FromArgb(228, 6, 19)", launcher)
        self.assertIn("The TOEFL House logo did not load in the launcher.", launcher)
        self.assertIn("IconLocation", read("product/windows/Create ERP Desktop Shortcut.ps1"))
        for path in ("tools/release/Build Customer Installer.ps1", "tools/release/Build Online Installer.ps1"):
            with self.subTest(path=path):
                self.assertIn("/win32icon:", read(path))

    def test_updater_host_allowlist_is_unchanged(self):
        # Branding never widens the signed host-servicing file set.
        engine = read("product/update_engine.py")
        self.assertNotIn("toefl-house.ico", engine)
        self.assertNotIn("toefl-house-logo.png", engine)


if __name__ == "__main__":
    unittest.main()
