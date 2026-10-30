"""English-only, single-source customer guidance and delivery contracts.

These offline guards catch a common regression: obsolete historical release
notes becoming current README instructions, a customer being directed to ZIP/
VBS development packaging, or a bilingual updater reappearing in an English
product. They verify source shape; they do not qualify a Windows installer.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
CUSTOMER_PATHS = (
    "README.md",
    "docs/DOCUMENTATION.md",
    "docs/CUSTOMER-DELIVERY.md",
    "docs/CUSTOMER-UPDATES.md",
    "product/windows/OWNER HANDBOOK.txt",
    "product/windows/DAILY USE GUIDE.txt",
    "product/windows/OWNER ACCEPTANCE GUIDE.txt",
)
NON_ENGLISH_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LOCAL_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CustomerDocumentationContractTests(unittest.TestCase):
    def test_customer_documents_have_one_english_operating_language(self):
        for path in CUSTOMER_PATHS:
            with self.subTest(path=path):
                self.assertNotRegex(source(path), NON_ENGLISH_SCRIPT)
        for path in ("README.md", "product/windows/OWNER HANDBOOK.txt",
                     "docs/CUSTOMER-UPDATES.md"):
            with self.subTest(path=path):
                self.assertNotIn("English/Dari", source(path))
                self.assertNotIn("DARI SAFETY SUMMARY", source(path))

    def test_readme_is_not_a_dated_release_diary(self):
        text = source("README.md")
        self.assertIn("docs/DOCUMENTATION.md", text)
        self.assertIn("REJECT / NO-GO", text)
        self.assertIn("single", source("docs/DOCUMENTATION.md").lower())
        self.assertNotIn("Historical engineering package only:", text)
        self.assertNotIn("Extract the complete package, open", text)
        self.assertIn("one verified, offline", text)

    def test_single_offline_installer_is_customer_target(self):
        for path in ("README.md", "docs/DOCUMENTATION.md",
                     "docs/CUSTOMER-DELIVERY.md",
                     "product/windows/OWNER HANDBOOK.txt"):
            with self.subTest(path=path):
                self.assertRegex(source(path), r"(?i)offline.{0,110}(EXE|Setup)")
        delivery = source("docs/CUSTOMER-DELIVERY.md")
        self.assertIn("Engineering-only folder/launcher fallback", delivery)
        handbook = source("product/windows/OWNER HANDBOOK.txt")
        self.assertIn("ENGINEERING", handbook)
        self.assertIn("NOT yet passed", handbook)

    def test_updated_customer_documents_have_no_broken_local_links(self):
        for path in ("README.md", "docs/DOCUMENTATION.md",
                     "docs/CUSTOMER-UPDATES.md"):
            parent = (ROOT / path).parent
            for address in LOCAL_LINK.findall(source(path)):
                address = address.split("#", 1)[0].split("?", 1)[0]
                if not address or re.match(r"^(?:[a-z]+:|//)", address):
                    continue
                with self.subTest(path=path, address=address):
                    self.assertTrue((parent / unquote(address)).is_file(),
                                    f"Broken reference: {path} -> {address}")

    def test_no_customer_records_are_seeded_by_preset(self):
        preset = json.loads(source(
            "apps/toefl_house/toefl_house/setup_presets/"
            "toefl_house_afghanistan_1405.json"))
        self.assertEqual(preset["installation_profile"],
                         "FRESH_SITE_NO_PRIOR_COURSE_HISTORY")
        self.assertFalse(preset["initial_operational_data"][
            "demo_data_in_customer_package"])
        self.assertFalse(preset["initial_operational_data"][
            "legacy_data_import_enabled"])
        for key in ("students", "student_applicants", "enrollments",
                    "classes", "attendance_records", "issued_fees",
                    "payment_entries", "salary_slips", "assessment_results"):
            self.assertEqual(preset["initial_operational_data"][key], 0, key)

    def test_updater_catalog_and_launcher_are_english_only(self):
        catalog = json.loads(source("product/windows/updater-strings.json"))
        self.assertEqual(catalog["language"], "en")
        self.assertEqual(catalog["fallback"], "en")
        for section in ("messages", "launcher", "ui"):
            for key, entry in catalog[section].items():
                with self.subTest(section=section, key=key):
                    self.assertEqual(set(entry), {"en"})
                    self.assertIsInstance(entry["en"], str)
                    self.assertTrue(entry["en"].strip())
                    self.assertNotRegex(entry["en"], NON_ENGLISH_SCRIPT)
        launcher = source("product/windows/Update TOEFL House ERP.ps1")
        self.assertIn("function Write-Message", launcher)
        self.assertIn('$catalog.language -cne "en"', launcher)
        self.assertNotIn("TH_STAGE-FA", launcher)
        self.assertNotIn("Write-Bilingual", launcher)
        self.assertNotIn("$entry.fa", launcher)


if __name__ == "__main__":
    unittest.main()
