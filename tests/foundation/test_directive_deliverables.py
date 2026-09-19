# -*- coding: utf-8 -*-
"""Pins the 2026-09-19 owner-directive deliverables to reality.

These tests exist so a later edit cannot quietly turn REJECT into PASS, call
an unreadable advisory report clean, claim a restore that was not rehearsed,
or copy the legacy SPA/ledger/payroll architecture back in as if it had been
adopted.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "docs" / "engineering"
MATRIX = ENG / "d8-production-operations-decision-matrix.json"
STAFF = ENG / "STAFF-JOURNEY-AUDIT-2026-09-19.md"
LEGACY = ENG / "LEGACY-EXTRACTION-2026-09-19.md"
REPORT = ENG / "PRODUCTION-READINESS-2026-09-19.md"


class DirectiveDeliverableTests(unittest.TestCase):

    def test_the_three_directive_records_exist(self):
        for path in (STAFF, LEGACY, REPORT):
            self.assertTrue(path.is_file(), path.name)
            self.assertGreater(path.stat().st_size, 1500, path.name)

    def test_the_production_report_does_not_authorize_production(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("**REJECT**", text)
        self.assertIn("NOT YET READY", text)
        self.assertIn("synthetic-only", text.lower())
        # A PASS that is not a warning about not claiming PASS is the failure.
        for line in text.splitlines():
            stripped = line.strip()
            if "do not edit this document to say PASS" in stripped.lower():
                continue
            if re.search(r"production[^\n]{0,40}\bPASS\b", stripped, re.I):
                self.fail(f"production report claims PASS: {stripped}")

    def test_the_report_states_the_same_machine_backup_limit(self):
        text = REPORT.read_text(encoding="utf-8")
        for risk in ("theft", "fire", "site loss", "ransomware"):
            self.assertIn(risk, text)
        self.assertIn("NOT YET BUILT", text)
        self.assertIn("Not executed on the real server", text)

    def test_sec_deps_is_classified_as_a_limitation(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("inspection limitation", text.lower())
        self.assertIn("all-clear", text.lower())
        self.assertEqual(re.findall(r"CVE-\d{4}-\d+", text), [])
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(matrix["security_dependency_state"],
                         "UPSTREAM-BLOCKED / REJECT")
        self.assertEqual(matrix["production_state"], "REJECT")
        self.assertEqual(matrix["local_launch_readiness"]["verdict"],
                         "NOT YET READY")

    def test_legacy_extraction_rejects_the_forbidden_architecture(self):
        text = LEGACY.read_text(encoding="utf-8")
        self.assertIn("## Rejected", text)
        for item in ("React/Vite SPA", "Custom `financial_transactions` ledger",
                     "Custom `teacher_salary_ledger`", "Custom RBAC",
                     "Custom workflow/automation/event bus",
                     "Student / guardian portal", "Payment gateway"):
            self.assertIn(item, text)
        self.assertIn("## Adopted", text)
        self.assertIn("## Adapted", text)
        self.assertNotIn("adopt the SPA", text.lower())

    def test_staff_audit_does_not_claim_a_hosted_walkthrough(self):
        text = STAFF.read_text(encoding="utf-8")
        self.assertIn("not a hosted walkthrough", text.lower())
        self.assertIn("Synthetic-only", text)
        self.assertIn("Attendance Recording command page", text)
        self.assertIn("does not collect money", text)

    def test_finance_desk_tells_staff_it_does_not_collect_money(self):
        source = (ROOT / "apps/toefl_house/toefl_house/desk/finance.py").read_text(
            encoding="utf-8")
        self.assertIn("This desk does not collect money itself.", source)
        self.assertNotIn(
            '"next": "Record the payment against this document."',
            source,
            "the old wording implied a missing desk button; the desk must "
            "say it does not collect money")


if __name__ == "__main__":
    unittest.main()
