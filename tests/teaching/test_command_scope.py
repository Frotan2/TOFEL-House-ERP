"""Branch restrictions apply to mutations, cached receipts and initial rosters."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class CommandScopeTests(unittest.TestCase):
    def setUp(self):
        self.branches = ["A"]
        self.companies = []
        self.documents = {}
        self.student_branches = {}
        self.values = {}
        self.frappe = types.ModuleType("frappe")
        self.frappe.PermissionError = PermissionError
        self.frappe.get_all = Mock(side_effect=lambda *a, **kw:
            self.branches if kw["filters"]["allow"] == "Branch" else self.companies)
        self.frappe.get_doc = Mock(side_effect=lambda dt, name: self.documents[(dt, name)])
        self.frappe.db = types.SimpleNamespace(get_value=lambda *key: self.values.get(key))
        permissions = types.ModuleType("toefl_house.permissions")
        permissions.BRANCH_KINDS = {"Student Group": "group", "Student": "student"}
        permissions.BRANCH_NATIVE_DOCTYPES = ("Student Group", "Student")
        permissions._doc_branches = lambda doc, kind: doc["branches"]
        permissions._student_branches = lambda name: self.student_branches.get(name, set())
        package = types.ModuleType("toefl_house")
        package.permissions = permissions
        modules = {"frappe": self.frappe, "toefl_house": package,
                   "toefl_house.permissions": permissions}
        context = patch.dict(sys.modules, modules)
        context.start()
        self.addCleanup(context.stop)
        path = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house/command_scope.py"
        spec = importlib.util.spec_from_file_location("scope_under_test", path)
        self.scope = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.scope)

    def test_sole_branch_defaults_and_foreign_branch_denied(self):
        self.assertEqual(self.scope.resolve_creation_branch(None, "actor"), "A")
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("create_student_group", {"branch": "B"}, "actor")

    def test_multiple_branches_require_explicit_choice(self):
        self.branches = ["A", "B"]
        with self.assertRaises(PermissionError):
            self.scope.resolve_creation_branch(None, "actor")

    def test_unrestricted_actor_preserves_hq_behavior(self):
        self.branches = []
        self.scope.authorize_command_scope("activate_class", {"student_group": "any"}, "actor")
        self.frappe.get_doc.assert_not_called()

    def test_foreign_unassigned_and_mixed_targets_denied(self):
        for branches in ({"B"}, set(), {"A", "B"}, {None}):
            with self.subTest(branches=branches):
                self.documents[("Student Group", "target")] = {"branches": branches}
                with self.assertRaises(PermissionError):
                    self.scope.authorize_command_scope("activate_class", {"student_group": "target"}, "actor")

    def test_receipt_is_rescoped_after_permission_change(self):
        self.documents[("Student Group", "target")] = {"branches": {"A"}}
        self.scope.authorize_command_scope("create_student_group", {}, "actor", result={"name": "target"})
        self.branches = ["B"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("create_student_group", {}, "actor", result={"name": "target"})

    def test_roster_filters_foreign_and_unassigned_students(self):
        self.student_branches = {"own": {"A"}, "foreign": {"B"}}
        rows = [{"student": name} for name in ("own", "foreign", "intake", "unknown")]
        self.values[("Student", "intake", "student_applicant")] = "applicant"
        self.values[("Student Applicant", "applicant", "th_branch")] = "A"
        self.assertEqual(self.scope.roster_for_branch(rows, "A"), [rows[0], rows[2]])

    def test_current_roster_takes_precedence_over_old_intake(self):
        self.student_branches = {"moved": {"B"}}
        self.values[("Student", "moved", "student_applicant")] = "old"
        self.values[("Student Applicant", "old", "th_branch")] = "A"
        self.assertEqual(self.scope.roster_for_branch([{"student": "moved"}], "A"), [])

    def test_initial_enrollment_uses_intake_before_first_class(self):
        self.documents[("Student", "new")] = {}
        self.values[("Student", "new", "student_applicant")] = "applicant"
        self.values[("Student Applicant", "applicant", "th_branch")] = "A"
        self.scope.authorize_command_scope("enroll", {"student": "new"}, "actor")
        self.values[("Student Applicant", "applicant", "th_branch")] = "B"
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("enroll", {"student": "new"}, "actor")

    def test_company_receipt_denied_even_without_branch_restriction(self):
        self.branches = []
        self.companies = ["Company B"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("reconcile_cashier_day",
                {"company": "Company A"}, "actor", result={"company": "Company A"})

    def test_allowed_company_receipt_and_unrestricted_hq_remain_usable(self):
        self.branches = []
        self.companies = ["Company A"]
        self.scope.authorize_command_scope("reconcile_cashier_day", {"company": "Company A"}, "actor")
        self.companies = []
        self.scope.authorize_command_scope("reconcile_cashier_day", {"company": "Company B"}, "actor")

    def test_result_company_is_checked_when_default_was_implicit(self):
        self.branches = []
        self.companies = ["Company B"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("reconcile_cashier_day", {}, "actor", result={"company": "Company A"})

    def test_cached_placement_invoice_is_rescoped_after_company_change(self):
        # The placement fee payload has case/customer but no explicit Company;
        # its stored result uses sales_invoice (not the generic invoice key).
        self.branches = []
        self.companies = ["Company B"]
        self.values[("Sales Invoice", "past-placement", "company")] = "Company A"
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "issue_placement_fee", {"case": "case", "customer": "customer"},
                "actor", result={"sales_invoice": "past-placement"})

    def test_cached_placement_invoice_remains_accessible_with_current_company_permission(self):
        self.branches = []
        self.companies = ["Company A"]
        self.values[("Sales Invoice", "own-placement", "company")] = "Company A"
        self.scope.authorize_command_scope(
            "issue_placement_fee", {"case": "case", "customer": "customer"},
            "actor", result={"sales_invoice": "own-placement"})
        # HQ has no restrictive native Company User Permission.
        self.companies = []
        self.scope.authorize_command_scope(
            "issue_placement_fee", {"case": "case", "customer": "customer"},
            "actor", result={"sales_invoice": "own-placement"})

    def test_fee_structure_company_is_resolved_before_receipt_replay(self):
        self.branches = []
        self.companies = ["Company A"]
        self.values[("Fee Structure", "foreign", "company")] = "Company B"
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("issue_tuition_fees", {"fee_structure": "foreign"}, "actor")
