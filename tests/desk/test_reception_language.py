"""English-only authored text guard for the Reception and admission workflow.

The guard checks shipped source and UI resources, not end-user data. Names,
contacts and incoming Unicode decimal numerals remain accepted and are never
transliterated or discarded by this language-only test.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_FILES = (
    "apps/toefl_house/toefl_house/reception_intake.py",
    "apps/toefl_house/toefl_house/desk/reception.py",
    "apps/toefl_house/toefl_house/desk/lifecycle.py",
    "apps/toefl_house/toefl_house/admission/__init__.py",
    "apps/toefl_house/toefl_house/public/js/th_role_desks.js",
    "apps/toefl_house/toefl_house/public/js/th_command_pages.js",
    "apps/toefl_house/toefl_house/public/css/th_design_system.css",
    "apps/toefl_house/toefl_house/operations/doctype/th_reception_inquiry/th_reception_inquiry.json",
    "docs/RECEPTION-DAILY-REGISTRATION.md",
)
ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")


class ReceptionEnglishSourceTests(unittest.TestCase):
    def test_reception_and_admission_authored_resources_use_english(self):
        for relative in PRODUCTION_FILES:
            with self.subTest(resource=relative):
                content = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIsNone(
                    ARABIC_SCRIPT.search(content),
                    "Authored reception and admission resources must be English; "
                    "real customer names and Unicode keyboard input remain valid.")

    def test_reception_intake_is_directionally_ltr(self):
        js = (ROOT / "apps/toefl_house/toefl_house/public/js/th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn('.attr("lang", "en").attr("dir", "ltr")', js)
        self.assertIn('"th-reception-desk": {', js)


if __name__ == "__main__":
    unittest.main()
