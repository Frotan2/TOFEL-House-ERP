"""Cash queues retain ownership, branch filtering and explicit batch identity."""
import types
import unittest
from unittest.mock import Mock, patch

from tests.desk.test_desk_contract import _import_desk


class CashQueueTests(unittest.TestCase):
    def setUp(self):
        self.module = _import_desk("collections", roles={"Reception", "Finance Officer", "Course Owner"})
        self.module.collection_schema_ready = lambda: True
        self.scope = types.ModuleType("toefl_house.command_scope")
        self.scope.authorize_command_scope = Mock()
        self.native = types.ModuleType("toefl_house.finance.collections")
        self.native.counter_for = Mock()
        self.context = patch.dict("sys.modules", {
            "toefl_house.command_scope": self.scope, "toefl_house.finance.collections": self.native})
        self.context.start()
        self.addCleanup(self.context.stop)

    def receipt(self, name="PAY-1", **changes):
        row = dict(name=name, party="STUDENT", received_amount=100, paid_to="COUNTER",
            paid_to_account_currency="AFN", company="COMPANY", posting_date="2026-10-27",
            docstatus=1, th_reception_collector="reception@example.test", th_collection_fees="FEE",
            th_collection_handover=None)
        row.update(changes)
        return row

    def test_own_history_is_explicitly_collector_filtered(self):
        self.module.project_rows = Mock(return_value=[])
        self.module._receipts("reception", own=True)
        query = self.module.project_rows.call_args.kwargs
        self.assertEqual(query["filters"]["th_reception_collector"], self.module.frappe.session.user)
        self.assertEqual(query["limit"], self.module.LIMIT_QUEUES)

    def test_foreign_student_branch_is_removed_before_projection(self):
        self.module.project_rows = Mock(return_value=[self.receipt()])
        self.scope.authorize_command_scope.side_effect = self.module.frappe.PermissionError("foreign branch")
        self.assertEqual(self.module._receipts("reception", own=True), [])

    def test_finance_batch_lists_exact_receipts_and_never_defaults_count(self):
        self.module.project_rows = Mock(return_value=[self.receipt("PAY-2"), self.receipt("PAY-1")])
        item = self.module.finance_sections()[0]["items"][0]
        args = item["action"]["args"]
        self.assertEqual(args["payment_entries"], '["PAY-1", "PAY-2"]')
        self.assertEqual(args["expected_amount"], 200)
        self.assertNotIn("counted_amount", args)

    def test_student_search_does_not_return_an_unrelated_general_queue(self):
        self.module.project_rows = Mock(return_value=[])
        self.module.reception_sections(students=["SELECTED"])
        call = self.module.project_rows.call_args
        self.assertEqual(call.args[1], "Fees")
        self.assertEqual(call.kwargs["filters"]["student"], ("in", ["SELECTED"]))
        self.assertEqual(self.module.project_rows.call_count, 1)

    def test_unmigrated_site_exposes_no_cash_actions(self):
        self.module.collection_schema_ready = lambda: False
        self.module.project_rows = Mock()
        self.assertEqual(self.module.reception_sections(), [])
        self.assertEqual(self.module.finance_sections(), [])
        self.module.project_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
