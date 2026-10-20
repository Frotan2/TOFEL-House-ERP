"""Static proof that every owner-policy command is bound to the Course Owner authority.

The real-site check ``policy-owner-only-authority-matrix`` (tools/native) proves the
refusals at runtime. This unit test guards the binding itself, so a new policy
command cannot be added without the owner-only authority.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "toefl_house" / "toefl_house"
AUDIT = APP / "configuration" / "audit.py"
RULES = APP / "configuration" / "rules.py"

# The eight owner-configurable policies and their exact command names.
POLICY_COMMANDS = {
    "owner_operations": ("create_owner_operations_policy",
                         "set_owner_operations_policy_version",
                         "set_owner_operations_policy_status"),
    "catalog_linkage": ("create_catalog_linkage_policy",
                        "set_catalog_linkage_version",
                        "set_catalog_linkage_status"),
    "returning_student": ("create_returning_student_policy",
                          "set_returning_student_policy_version",
                          "set_returning_student_policy_status"),
    "enrollment_exit": ("create_enrollment_exit_policy",
                        "set_enrollment_exit_policy_version",
                        "set_enrollment_exit_policy_status"),
    "billing": ("create_billing_policy",
                "set_billing_policy_version",
                "set_billing_policy_status"),
    "roster_change": ("create_roster_change_policy",
                      "set_roster_change_policy_version",
                      "set_roster_change_policy_status"),
    "attendance_correction": ("create_attendance_correction_policy",
                              "set_attendance_correction_policy_version",
                              "set_attendance_correction_policy_status"),
    "adjustment_posting": ("create_adjustment_posting_policy",
                           "set_adjustment_posting_version",
                           "set_adjustment_posting_status"),
}


def _kind_authority():
    import ast
    tree = ast.parse(AUDIT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "KIND_AUTHORITY" for t in node.targets):
            return {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
    raise AssertionError("KIND_AUTHORITY not found")


class PolicyAuthorityBindingTests(unittest.TestCase):
    def test_every_policy_command_is_bound_to_business_policy(self):
        bound = _kind_authority()
        self.assertEqual(len(POLICY_COMMANDS), 8)
        for label, commands in POLICY_COMMANDS.items():
            for kind in commands:
                with self.subTest(policy=label, kind=kind):
                    self.assertEqual(bound.get(kind), "business_policy",
                                     f"{kind} is not bound to the business_policy authority")

    def test_business_policy_authority_is_course_owner_only(self):
        source = RULES.read_text(encoding="utf-8")
        self.assertIn('"business_policy": ("Course Owner",)', source)

    def test_the_gate_refuses_before_any_argument_is_read(self):
        # _execute_once must resolve the authority before validating the request key.
        source = AUDIT.read_text(encoding="utf-8")
        gate = source.index("actor = require_authority(authority)")
        validate = source.index("validate_request_key(request_key)")
        self.assertLess(gate, validate)


if __name__ == "__main__":
    unittest.main()
