"""Finance cannot conflate a draft Fees document with a posted receivable.

Existing-draft records block the guarded issue_tuition_fees command.
They must be visible for Finance Manager review rather than disappearing
from the queue or advertising a second bill that the server will refuse.
"""
import unittest
from tests.desk.test_desk_contract import _import_desk


class BillingVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.finance = _import_desk("finance", roles={"Finance Manager"})

    def test_posted_fee_hides_only_its_issued_enrollment(self):
        issued, drafts = self.finance._billing_documents_by_enrollment([
            {"name": "FEE-POSTED", "program_enrollment": "ENR-1", "docstatus": 1},
            {"name": "FEE-CANCELLED", "program_enrollment": "ENR-2", "docstatus": 2},
        ])
        self.assertEqual(issued, {"ENR-1"})
        self.assertEqual(drafts, {})

    def test_draft_is_not_an_issued_bill_but_needs_finance_resolution(self):
        issued, drafts = self.finance._billing_documents_by_enrollment([
            {"name": "FEE-DRAFT", "program_enrollment": "ENR-1", "docstatus": 0},
            {"name": "FEE-DRAFT-B", "program_enrollment": "ENR-1", "docstatus": 0},
        ])
        self.assertEqual(issued, set())
        self.assertEqual(drafts, {"ENR-1": ["FEE-DRAFT", "FEE-DRAFT-B"]})

    def test_draft_blocks_issue_button_and_avoids_false_collectible_debt(self):
        stage, message, role = self.finance._billing_blocker(
            "ENR-A", {"ENR-A": ["FEE-DRAFT-A"]}, True)
        self.assertEqual(stage, "Draft fee needs review")
        self.assertIn("NOT a collectible bill", message)
        self.assertIn("FEE-DRAFT-A", message)
        self.assertEqual(role, "Finance Manager")
        self.assertIsNone(self.finance._billing_blocker("ENR-A", {}, True),
                          "only an entirely read, unbilled enrollment can offer issuance")

    def test_a_draft_alongside_an_issued_bill_must_still_be_visible(self):
        issued, drafts = self.finance._billing_documents_by_enrollment([
            {"name": "FEE-ISSUED", "program_enrollment": "ENR-A", "docstatus": 1},
            {"name": "FEE-ORPHAN-DRAFT", "program_enrollment": "ENR-A", "docstatus": 0},
        ])
        self.assertEqual(issued, {"ENR-A"})
        stage, message, role = self.finance._billing_blocker(
            "ENR-A", drafts, True, has_issued=True)
        self.assertEqual(stage, "Draft fee needs review")
        self.assertIn("separate submitted tuition bill", message)
        self.assertIn("do not charge again", message)
        self.assertEqual(role, "Finance Manager")

    def test_truncated_fee_register_never_offers_issue_even_without_a_match(self):
        stage, message, role = self.finance._billing_blocker(
            "ENR-A", {}, False)
        self.assertEqual(stage, "Billing status needs review")
        self.assertIn("incomplete", message)
        self.assertEqual(role, "Finance Manager")

    def test_mixed_draft_and_issued_preserves_posted_authority(self):
        issued, drafts = self.finance._billing_documents_by_enrollment([
            {"name": "FEE-1", "program_enrollment": "ENR-A", "docstatus": 1},
            {"name": "FEE-2", "program_enrollment": "ENR-A", "docstatus": 0},
            {"name": "FEE-3", "program_enrollment": "ENR-B", "docstatus": 0},
            {"name": "ORPHAN", "program_enrollment": "", "docstatus": 0},
        ])
        self.assertEqual(issued, {"ENR-A"})
        self.assertEqual(drafts, {"ENR-A": ["FEE-2"], "ENR-B": ["FEE-3"]})


if __name__ == "__main__":
    unittest.main()
