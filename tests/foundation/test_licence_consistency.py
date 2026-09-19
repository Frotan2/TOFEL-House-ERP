"""The three licence surfaces must agree.

Owner decision D11 (2026-09-19) selected MIT. Before that decision the
repository contradicted itself three ways: both hooks.py files declared
``app_license = "MIT"``, the README stated that no licence was selected, and no
LICENSE file existed. A licence is a legal grant, so a silent drift between what
the metadata declares and what the repository actually grants is a real defect,
not a documentation nit. These checks make the agreement mechanical.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = (ROOT / "apps/toefl_house/toefl_house/hooks.py",
         ROOT / "apps/foundation_security/foundation_security/hooks.py")


class LicenceConsistencyTests(unittest.TestCase):
    def test_a_licence_file_exists_and_is_mit(self):
        licence = ROOT / "LICENSE"
        self.assertTrue(licence.is_file(), "no LICENSE file in the repository")
        text = licence.read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn("TOEFL House", text, "the copyright holder must be named")

    def test_every_app_declares_the_same_licence_as_the_licence_file(self):
        for hooks in HOOKS:
            with self.subTest(app=hooks.parent.name):
                source = hooks.read_text(encoding="utf-8")
                self.assertIn('app_license = "MIT"', source,
                              f"{hooks} does not declare MIT")

    def test_the_readme_states_the_selected_licence(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Product license: MIT", readme)
        self.assertNotIn("No product license has been selected", readme,
                         "the README still claims no licence is selected")

    def test_d11_is_recorded_as_decided(self):
        record = (ROOT / "docs/engineering/canonical-owner-decision-record.json")
        self.assertIn('"D11"', record.read_text(encoding="utf-8"))
