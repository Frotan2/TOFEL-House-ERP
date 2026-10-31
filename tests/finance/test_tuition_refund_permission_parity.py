"""Execute the shipped refund read/list policy functions without a Frappe site.

The Native lifecycle suite separately proves these same gates against real
Frappe/MariaDB. This regression isolates role precedence and SQL branch scope
and does not treat a unit stub as a database-backed authorization test.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house" / "toefl_house"
ALLOWED = ("Finance Officer", "Finance Auditor", "General Manager", "Finance Manager")


def _functions(path, names, namespace):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    nodes = [node for node in module.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError(f"Missing actual source functions in {path}")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"),
         namespace)
    return namespace


class RefundPermissionParity(unittest.TestCase):
    def setUp(self):
        self.roles = set()
        self.branches = None
        self.operational = True
        def gate():
            if not self.operational:
                raise PermissionError("release hold")
        frappe = SimpleNamespace(
            PermissionError=PermissionError,
            session=SimpleNamespace(user="synthetic@example.test"),
            get_roles=lambda _user: list(self.roles),
            db=SimpleNamespace(escape=lambda s: "'" + s.replace("'", "''") + "'"),
        )
        self.ns = {
            "frappe": frappe,
            "require_operational": gate,
            "TABLES": {"tuition_refund_request": "`tabTH Tuition Refund Request`"},
            "BRANCH_KINDS": {"TH Tuition Refund Request": "tuition_refund_request"},
            "_user_branches": lambda _user: self.branches,
        }
        _functions(APP / "policy.py", {"can_read"}, self.ns)
        _functions(APP / "permissions.py", {
            "_query_role", "query", "_in_branches_sql",
            "_student_branch_condition", "_branch_condition",
        }, self.ns)

    def test_all_four_business_roles_agree_on_read_and_list(self):
        for role in ALLOWED:
            with self.subTest(role=role):
                self.roles = {role}
                self.assertTrue(self.ns["can_read"](
                    "tuition_refund_request", self.roles,
                    "synthetic@example.test", "other@example.test", "Requested"))
                self.assertEqual(self.ns["_query_role"](
                    "tuition_refund_request", "synthetic@example.test"), "1=1")
                self.assertEqual(self.ns["query"](
                    "tuition_refund_request", "synthetic@example.test"), "1=1")

    def test_placement_publisher_and_unrelated_roles_cannot_list(self):
        for roles in (set(), {"Placement Publisher"}, {"Placement Auditor"},
                      {"Reception"}, {"Placement Publisher", "Reception"}):
            with self.subTest(roles=roles):
                self.roles = roles
                self.assertFalse(self.ns["can_read"](
                    "tuition_refund_request", roles,
                    "synthetic@example.test", "other@example.test", "Requested"))
                self.assertEqual(self.ns["_query_role"](
                    "tuition_refund_request", "synthetic@example.test"), "1=0")

    def test_mixed_role_preserves_finance_authority(self):
        self.roles = {"Finance Officer", "Placement Publisher"}
        self.assertEqual(self.ns["_query_role"](
            "tuition_refund_request", "synthetic@example.test"), "1=1")

    def test_branch_scope_is_composed_after_role_gate(self):
        self.roles = {"Finance Officer"}
        self.branches = ["SYN-BRANCH-A"]
        sql = self.ns["query"]("tuition_refund_request", "synthetic@example.test")
        self.assertIn("SYN-BRANCH-A", sql)
        self.assertIn("tabTH Tuition Refund Request", sql)
        self.assertIn("tabFees", sql)
        self.assertIn("tabStudent Group Student", sql)
        self.assertIn(" AND ", sql)
        self.roles = {"Placement Publisher"}
        self.assertIn("(1=0) AND", self.ns["query"](
            "tuition_refund_request", "synthetic@example.test"))
        self.roles = {"Finance Officer"}
        self.branches = []
        self.assertEqual(self.ns["query"](
            "tuition_refund_request", "synthetic@example.test"), "1=0")

    def test_release_hold_rejects_even_authorized_roles(self):
        self.roles = {"General Manager"}
        self.operational = False
        self.assertEqual(self.ns["query"](
            "tuition_refund_request", "synthetic@example.test"), "1=0")
        self.assertEqual(self.ns["_query_role"](
            "tuition_refund_request", "synthetic@example.test"), "1=0")


if __name__ == "__main__":
    unittest.main()
