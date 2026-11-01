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
        def get_all(doctype, **kw):
            filters = kw["filters"]
            if doctype == "Student Group Student":
                return [{"parent": f"group:{branch}"}
                        for branch in self.student_branches.get(filters["student"], set())]
            if doctype == "Student Group":
                return [{"name": parent, "th_branch": None if parent == "group:None" else parent[6:]}
                        for parent in filters["name"][1]]
            return self.branches if filters["allow"] == "Branch" else self.companies
        self.frappe.get_all = Mock(side_effect=get_all)
        self.frappe.get_doc = Mock(side_effect=lambda dt, name: self.documents[(dt, name)])
        self.frappe.db = types.SimpleNamespace(get_value=lambda *key: self.values.get(key))
        permissions = types.ModuleType("toefl_house.permissions")
        permissions.BRANCH_KINDS = {"Student Group": "group", "Student": "student",
                                    "TH Reception Inquiry": "reception_inquiry"}
        permissions.BRANCH_NATIVE_DOCTYPES = ("Student Group", "Student")
        permissions._doc_branches = lambda doc, kind: doc["branches"]
        permissions._doc_branches_guarded = lambda doc, kind: doc["branches"]
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

    def test_placement_case_cannot_move_between_scoped_branches(self):
        self.documents[("TH Placement Case", "CASE-A")] = {"th_branch": "A"}
        self.scope.authorize_command_scope("allocate_attempt", {"case": "CASE-A"}, "actor")
        self.scope.authorize_command_scope(
            "create_case", {"branch": "A"}, "actor", result={"name": "CASE-A"})
        self.branches = ["B"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("allocate_attempt", {"case": "CASE-A"}, "actor")
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "create_case", {"branch": "B"}, "actor", result={"name": "CASE-A"})

    def test_branchless_placement_case_fails_closed_for_scoped_staff(self):
        self.documents[("TH Placement Case", "CASE-NONE")] = {"th_branch": None}
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("allocate_attempt", {"case": "CASE-NONE"}, "actor")

    def test_reception_inquiry_followup_and_cached_receipt_recheck_branch(self):
        self.documents[("TH Reception Inquiry", "INQ-ALPHA")] = {
            "branches": {"A"}}
        self.scope.authorize_command_scope(
            "update_walkin_inquiry", {"inquiry": "INQ-ALPHA"}, "actor")
        self.scope.authorize_command_scope(
            "create_walkin_inquiry", {"branch": "A"}, "actor",
            result={"name": "INQ-ALPHA"})
        self.branches = ["B"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "update_walkin_inquiry", {"inquiry": "INQ-ALPHA"}, "actor")
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "create_walkin_inquiry", {"branch": "B"}, "actor",
                result={"name": "INQ-ALPHA"})

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
        self.student_branches = {"own": {"A"}, "foreign": {"B"}, "mixed": {"A", "B"},
                                 "missing": {"A", None}, "branchless": {None}}
        rows = [{"student": name} for name in
                ("own", "foreign", "intake", "unknown", "mixed", "missing", "branchless")]
        self.values[("Student", "intake", "student_applicant")] = "applicant"
        self.values[("Student Applicant", "applicant", "th_branch")] = "A"
        self.assertEqual(self.scope.roster_for_branch(rows, "A"), [rows[0], rows[2]])

    def test_class_receipt_is_rescoped_when_a_roster_student_moves(self):
        self.documents[("Student Group", "class-a")] = {"branches": {"A"}}
        self.documents[("Student", "learner")] = {}
        self.student_branches = {"learner": {"A"}}
        result = {"name": "class-a", "roster": ["learner"]}
        self.scope.authorize_command_scope("create_student_group", {}, "actor", result=result)
        self.student_branches["learner"] = {"B"}
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("create_student_group", {}, "actor", result=result)

    def test_instructor_receipt_rechecks_ownership_even_without_branch_restriction(self):
        self.branches = []
        row = types.SimpleNamespace(student_group="class-a", instructor="teacher-a", schedule_date="2026-10-01")
        self.frappe.db.get_value = Mock(return_value=row)
        teaching = types.ModuleType("toefl_house.teaching")
        teaching._require_own_instructor_session = Mock()
        with patch.dict(sys.modules, {"toefl_house.teaching": teaching}):
            payload = {"course_schedule": "session-a"}
            self.scope.authorize_command_scope("record_instructor_attendance", payload, "actor", result={"records": {}})
            teaching._require_own_instructor_session.assert_called_once_with("actor", row, "session-a")
            teaching._require_own_instructor_session.side_effect = PermissionError("assignment revoked")
            with self.assertRaises(PermissionError):
                self.scope.authorize_command_scope("record_instructor_attendance", payload, "actor", result={"records": {}})
            self.frappe.db.get_value.return_value = None
            with self.assertRaises(PermissionError):
                self.scope.authorize_command_scope("record_instructor_attendance", payload, "actor", result={"records": {}})

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

    def test_missing_invoice_company_denies_cached_receipt(self):
        self.branches = []
        self.companies = ["Company A"]
        # If a saved result still refers to a deleted/Company-less invoice,
        # never return its historical monetary/customer values to a scoped user.
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "issue_placement_fee", {"case": "case", "customer": "customer"},
                "actor", result={"sales_invoice": "missing", "grand_total": 500.0})
        self.companies = []
        self.scope.authorize_command_scope(
            "issue_placement_fee", {"case": "case", "customer": "customer"},
            "actor", result={"sales_invoice": "missing", "grand_total": 500.0})

    def test_companyless_native_fee_and_employee_are_denied(self):
        self.branches = []
        self.companies = ["Company A"]
        for kind, payload in (
            ("request_fees_correction", {"fees": "orphan"}),
            ("create_teaching_contract", {"employee": "orphan"}),
        ):
            with self.subTest(kind=kind), self.assertRaises(PermissionError):
                self.scope.authorize_command_scope(kind, payload, "actor")

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

    def test_cached_assignment_replay_obeys_changed_company(self):
        self.branches = []
        self.companies = ["Company B"]
        self.values[("TH Teaching Assignment", "assignment-a", "contract")] = "contract-a"
        self.values[("TH Instructor Contract", "contract-a", "employee")] = "employee-a"
        self.values[("Employee", "employee-a", "company")] = "Company A"
        payload = {"assignment": "assignment-a"}
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "end_teaching_assignment", payload, "actor",
                result={"name": "assignment-a", "effective_end": "2026-10-27"})
        self.companies = ["Company A"]
        self.scope.authorize_command_scope(
            "end_teaching_assignment", payload, "actor",
            result={"name": "assignment-a", "effective_end": "2026-10-27"})

    def test_assignment_without_contract_fails_closed_for_scoped_actor(self):
        self.branches = []
        self.companies = ["Company A"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "end_teaching_assignment", {"assignment": "missing"}, "actor")

    def test_cached_contract_revision_obeys_changed_company(self):
        self.branches = []
        self.companies = ["Company B"]
        self.values[("TH Instructor Contract", "old-contract", "employee")] = "employee-a"
        self.values[("Employee", "employee-a", "company")] = "Company A"
        payload = {"contract": "old-contract"}
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "revise_teaching_contract", payload, "actor",
                result={"name": "new-contract", "supersedes": "old-contract"})
        self.companies = ["Company A"]
        self.scope.authorize_command_scope(
            "revise_teaching_contract", payload, "actor",
            result={"name": "new-contract", "supersedes": "old-contract"})

    def test_cached_invoice_correction_obeys_changed_company(self):
        self.branches = []
        self.companies = ["Company B"]
        self.values[("TH Correction Request", "req", "sales_invoice")] = "inv-a"
        self.values[("Sales Invoice", "inv-a", "company")] = "Company A"
        for command in ("approve_invoice_correction", "deny_invoice_correction"):
            with self.subTest(command=command), self.assertRaises(PermissionError):
                self.scope.authorize_command_scope(
                    command, {"request": "req"}, "actor",
                    result={"name": "req", "status": "Denied"})
        self.companies = ["Company A"]
        self.scope.authorize_command_scope(
            "deny_invoice_correction", {"request": "req"}, "actor",
            result={"name": "req", "status": "Denied"})

    def test_cached_fees_correction_obeys_changed_company(self):
        self.branches = []
        self.companies = ["Company B"]
        self.values[("TH Correction Request", "fee-req", "fees")] = "fees-a"
        self.values[("Fees", "fees-a", "company")] = "Company A"
        for command in ("approve_fees_correction", "deny_fees_correction"):
            with self.subTest(command=command), self.assertRaises(PermissionError):
                self.scope.authorize_command_scope(
                    command, {"request": "fee-req"}, "actor",
                    result={"name": "fee-req", "status": "Denied"})
        self.companies = []
        self.scope.authorize_command_scope(
            "approve_fees_correction", {"request": "fee-req"}, "actor",
            result={"name": "fee-req", "fees": "fees-a"})

    def test_missing_contract_or_correction_scope_fails_closed(self):
        self.branches = []
        self.companies = ["Company A"]
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "revise_teaching_contract", {"contract": "missing"}, "actor")
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope(
                "approve_invoice_correction", {"request": "missing"}, "actor")

    def test_fee_structure_company_is_resolved_before_receipt_replay(self):
        self.branches = []
        self.companies = ["Company A"]
        self.values[("Fee Structure", "foreign", "company")] = "Company B"
        with self.assertRaises(PermissionError):
            self.scope.authorize_command_scope("issue_tuition_fees", {"fee_structure": "foreign"}, "actor")
