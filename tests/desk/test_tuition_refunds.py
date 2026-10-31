"""Refund case projections retain native ACLs and independent acting authority.

Hosted Native tests separately prove real Company/Branch read/list behavior.
These unit checks catch accidental elevated reads and misleading action offers.
"""
import unittest
import types
from unittest.mock import Mock, patch

from tests.desk.test_desk_contract import _import_desk


class RefundCaseReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope = types.ModuleType("toefl_house.command_scope")
        self.scope.authorize_command_scope = Mock()
        context = patch.dict("sys.modules", {"toefl_house.command_scope": self.scope})
        context.start()
        self.addCleanup(context.stop)

    def helper(self, roles=("Finance Manager",)):
        helper = _import_desk("__init__", roles=roles)
        helper.frappe.db.has_column = Mock(return_value=True)
        helper.frappe.get_list = Mock(return_value=[])
        helper.frappe.get_all = Mock(side_effect=AssertionError("Elevated refund read"))
        return helper

    def test_query_uses_native_permission_authority_and_bounded_fields(self):
        helper = self.helper()
        fields = ["name", "student", "company", "credit_journal"]
        self.assertEqual(helper.refund_case_rows("finance", fields), [])
        helper.frappe.get_list.assert_called_once_with("TH Tuition Refund Request", fields=fields,
            order_by="modified desc, name desc", limit_page_length=26)
        helper.frappe.get_all.assert_not_called()

    def test_current_command_scope_refusal_removes_case_before_evidence_projection(self):
        helper = self.helper()
        helper.frappe.get_list.return_value = [{"name": "FOREIGN", "reason": "Private evidence"}]
        self.scope.authorize_command_scope.side_effect = helper.frappe.PermissionError("Foreign branch")
        self.assertEqual(helper.refund_case_rows("finance", ["name", "reason"]), [])
        self.scope.authorize_command_scope.assert_called_once_with("approve_tuition_refund",
            {"request": "FOREIGN"}, helper.frappe.session.user)

    def test_wrong_audience_is_refused_before_any_case_read(self):
        for roles, desk in ((["Finance Officer"], "finance"), (["Course Owner"], "management"),
                            (["Finance Manager"], "management"), (["Instructor"], "finance")):
            with self.subTest(roles=roles, desk=desk):
                helper = self.helper(roles)
                with self.assertRaises(helper.frappe.PermissionError):
                    helper.refund_case_rows(desk, ["name"])
                helper.frappe.get_list.assert_not_called()

    def test_missing_migration_and_forbidden_fields_do_not_query_cases(self):
        helper = self.helper()
        helper.frappe.db.has_column.return_value = False
        self.assertIsNone(helper.refund_case_rows("finance", ["name"]))
        with self.assertRaises(helper.frappe.ValidationError):
            helper.refund_case_rows("finance", ["password"])
        helper.frappe.get_list.assert_not_called()


class RefundActionsTests(unittest.TestCase):
    def view(self, status, roles, **changes):
        module = _import_desk("tuition_refunds", roles=roles)
        row = dict(name="CASE", student="STUDENT", company="COMPANY", fees="FEE", requested_amount=50,
            approved_amount=50, reason="Case reason", evidence="Original evidence", approval_evidence="GM evidence",
            status=status, requested_by="requester@example.test", approved_by="gm@example.test",
            paying_user="finance@example.test", credit_journal="CREDIT", payment_entry="PAYOUT", modified="2026-10-30")
        row.update(changes)
        module.refund_case_rows = Mock(return_value=[row])
        return module, module.refund_sections("finance")[0]["items"][-1]

    def test_finance_cannot_offer_approval_without_general_manager_role(self):
        _, item = self.view("Requested", ["Finance Manager", "Finance Officer"])
        self.assertIsNone(item.get("action"))
        self.assertNotIn("actions", item)

    def test_requester_cannot_offer_their_own_approval(self):
        module, _ = self.view("Requested", ["General Manager"])
        _, item = self.view("Requested", ["General Manager"], requested_by=module.frappe.session.user)
        self.assertNotIn("action", item)
        self.assertEqual(item["actions"][0]["endpoint"].split(".")[-1], "deny_tuition_refund")

    def test_approver_with_payer_role_cannot_offer_their_own_payout(self):
        module, _ = self.view("Approved", ["General Manager", "Finance Manager"])
        _, item = self.view("Approved", ["General Manager", "Finance Manager"], approved_by=module.frappe.session.user)
        self.assertNotIn("action", item)
        self.assertIn("Another Finance Manager", item["next"])

    def test_independent_payout_displays_exact_recipient_amount_and_approval_context(self):
        _, item = self.view("Approved", ["Finance Manager"])
        action = item["action"]
        self.assertEqual(action["endpoint"].split(".")[-1], "pay_tuition_refund")
        self.assertEqual(action["args"]["recipient"], "STUDENT")
        self.assertEqual(action["args"]["refund_amount"], 50)
        self.assertEqual(action["args"]["approval_evidence"], "GM evidence")

    def test_paid_row_retains_both_native_links_without_offering_individual_cancel(self):
        _, item = self.view("Paid", ["Finance Manager", "General Manager"])
        self.assertIn("CREDIT", item["detail"])
        self.assertIn("PAYOUT", item["detail"])
        self.assertNotIn("action", item)
        self.assertNotIn("actions", item)


if __name__ == "__main__":
    unittest.main()
