"""Regression guard for the active preservation/restore release hold.

These checks prevent the Owner-facing entry points from accidentally
instructing someone to mutate policies or run backup/restore while the hold
is active. They are documentation contracts, not runtime authorization.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReleaseHoldContract(unittest.TestCase):
    def test_readme_prominently_states_the_active_hold(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("NOT APPROVED FOR PRODUCTION", text)
        self.assertIn("Production authorization: REJECT / NO-GO", text)
        self.assertIn("TEST PACKAGE — NO REAL DATA", text)
        self.assertIn("Preserve the existing Frappe site", text)
        self.assertIn("activate production on that computer", text)

    def test_handover_does_not_authorize_policy_mutation_during_hold(self):
        text = (ROOT / "docs/engineering/HANDOVER-2026-10-20.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Current preservation/restore hold overrides setup steps below", text)
        self.assertIn("Do not create, edit, version, validate or activate owner policies", text)
        self.assertIn("only Owner actions permitted during the preservation/restore hold", text)
        self.assertIn("Do not configure or validate the backup policy", text)

    def test_windows_validation_and_runbook_keep_restore_prohibited(self):
        validation = (ROOT / "product/windows/VALIDATION.md").read_text(
            encoding="utf-8"
        )
        runbook = (ROOT / "docs/engineering/LAUNCH-RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("PRESERVATION / RESTORE HOLD", validation)
        self.assertIn("No backup or restore action is authorized", validation)
        self.assertIn("Restore and recovery — HOLD", runbook)
        self.assertIn("Do not run `product/restore.py`", runbook)


if __name__ == "__main__":
    unittest.main()
