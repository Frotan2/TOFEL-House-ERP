"""Pure local checks for the D2 teaching-compensation slice.

Covers the pure policy layer (contract validators, window overlap,
payable computation) and the static wiring (command roles, protected
doctypes, read-containment kinds, hooks coverage, doctype JSON shape).
Hosted runtime acceptance lives in tools/placement/native_checks.py.
"""
import ast
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (ADJUSTMENT_TYPES, CLASS_STATUSES, COMPENSATION_MODELS,
                                DELIVERY_MODES, compute_skill_payable,
                                validate_class_status, validate_compensation_model,
                                validate_delivery_mode, validate_effective_window,
                                validate_optional_amount, validate_payable_quantity,
                                validate_positive_amount, validate_skill, windows_overlap)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
SECURITY = APP / "security.py"
HOOKS = APP / "hooks.py"
COMPENSATION = APP / "teaching/compensation.py"
DOCTYPES = {
    "TH Instructor Contract": APP / "teaching/doctype/th_instructor_contract/th_instructor_contract.json",
    "TH Contract Skill Term": APP / "teaching/doctype/th_contract_skill_term/th_contract_skill_term.json",
    "TH Contract Adjustment": APP / "teaching/doctype/th_contract_adjustment/th_contract_adjustment.json",
    "TH Teaching Assignment": APP / "teaching/doctype/th_teaching_assignment/th_teaching_assignment.json",
    "TH Skill": APP / "teaching/doctype/th_skill/th_skill.json",
}
COMMANDS = {
    "create_teaching_contract": "Finance Officer",
    "revise_teaching_contract": "Finance Officer",
    "assign_teaching_skill": "Teaching Scheduler",
    "end_teaching_assignment": "Teaching Scheduler",
    "calculate_teaching_compensation": "Finance Officer",
}


class SkillVocabularyTests(unittest.TestCase):
    """Skill is a configurable TH Skill master (not a hard-coded list).

    The pure validate_skill only bounds the reference as a plausible name;
    Active/Retired lifecycle is enforced at the command layer against the
    database. The canonical three skills are seeded at install (codes SL, WG,
    RV with the legacy titles) so no hard-coded list lives in policy.py.
    """

    def test_validate_skill_bounds_reference(self):
        for good in ("SL", "WG", "RV", "SPEAKING-LISTENING"):
            self.assertEqual(validate_skill(good), good)
        for bad in ("", None, 7, "x" * 141):
            with self.assertRaises(ValueError):
                validate_skill(bad)

    def test_models_and_adjustment_types(self):
        self.assertEqual(COMPENSATION_MODELS, ("Fixed Salary", "Skill-Based", "Hybrid"))
        for model in COMPENSATION_MODELS:
            self.assertEqual(validate_compensation_model(model), model)
        with self.assertRaises(ValueError):
            validate_compensation_model("Per Class")
        self.assertEqual(ADJUSTMENT_TYPES, ("Bonus", "Deduction"))

    def test_delivery_mode_and_class_status_enums(self):
        """Delivery mode is an operational class property, not a separate Program."""
        self.assertEqual(DELIVERY_MODES, ("On-site", "Online", "Hybrid"))
        for mode in DELIVERY_MODES:
            self.assertEqual(validate_delivery_mode(mode), mode)
        with self.assertRaises(ValueError):
            validate_delivery_mode("In-Person")
        self.assertEqual(CLASS_STATUSES, ("Planned", "Active", "Completed", "Cancelled"))
        for status in CLASS_STATUSES:
            self.assertEqual(validate_class_status(status), status)


class AmountTests(unittest.TestCase):
    def test_positive_bounded(self):
        self.assertEqual(validate_positive_amount(100, "Rate"), 100.0)
        self.assertEqual(validate_positive_amount(0.01, "Rate"), 0.01)
        for bad in (0, -1, True, "5", None, 10 ** 10):
            with self.assertRaises(ValueError):
                validate_positive_amount(bad, "Rate")

    def test_optional_amounts(self):
        for empty in (None, "", 0):
            self.assertIsNone(validate_optional_amount(empty, "Minimum"))
        self.assertEqual(validate_optional_amount(250, "Minimum"), 250.0)
        with self.assertRaises(ValueError):
            validate_optional_amount(-3, "Minimum")

    def test_payable_quantity(self):
        self.assertEqual(validate_payable_quantity(1), 1)
        self.assertEqual(validate_payable_quantity(10 ** 6), 10 ** 6)
        for bad in (0, -1, 2.5, True, "4", None, 10 ** 7):
            with self.assertRaises(ValueError):
                validate_payable_quantity(bad)


class WindowTests(unittest.TestCase):
    def test_effective_window(self):
        self.assertEqual(validate_effective_window("2026-01-01", ""), ("2026-01-01", None))
        self.assertEqual(validate_effective_window("2026-01-01", "2026-06-30"),
                         ("2026-01-01", "2026-06-30"))
        with self.assertRaises(ValueError):
            validate_effective_window("2026-06-30", "2026-01-01")
        with self.assertRaises(ValueError):
            validate_effective_window("01/01/2026", "")

    def test_overlap_truth_table(self):
        self.assertTrue(windows_overlap("2026-01-01", None, "2026-06-01", "2026-06-30"))
        self.assertTrue(windows_overlap("2026-01-01", "2026-12-31", "2026-12-31", None))
        self.assertFalse(windows_overlap("2026-01-01", "2026-06-30", "2026-07-01", None))
        self.assertFalse(windows_overlap("2026-07-01", None, "2026-01-01", "2026-06-30"))
        self.assertTrue(windows_overlap("2026-03-01", None, "2026-01-01", None))


class PayableTests(unittest.TestCase):
    def test_contract_terms_applied(self):
        self.assertEqual(compute_skill_payable(40, 12.5), 500.0)
        self.assertEqual(compute_skill_payable(40, 12.5, minimum=600), 600.0)
        self.assertEqual(compute_skill_payable(40, 12.5, maximum=450), 450.0)
        # two-decimal currency rounding is the only rounding applied
        self.assertEqual(compute_skill_payable(3, 33.333), 100.0)

    def test_bounds_rejected(self):
        with self.assertRaises(ValueError):
            compute_skill_payable(0, 10)
        with self.assertRaises(ValueError):
            compute_skill_payable(10, 0)
        with self.assertRaises(ValueError):
            compute_skill_payable(10, 10, minimum=500, maximum=100)


def _kind_roles():
    tree = ast.parse(SECURITY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "KIND_ROLES":
            return {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
    raise AssertionError("KIND_ROLES missing")


def _doctypes_set():
    tree = ast.parse(SECURITY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DOCTYPES":
            return {elt.value for elt in node.value.elts}
    raise AssertionError("DOCTYPES missing")


class WiringTests(unittest.TestCase):
    def test_command_roles(self):
        roles = _kind_roles()
        for kind, role in COMMANDS.items():
            self.assertEqual(roles.get(kind), role, kind)

    def test_protected_doctypes(self):
        doctypes = _doctypes_set()
        self.assertIn("TH Instructor Contract", doctypes)
        self.assertIn("TH Teaching Assignment", doctypes)

    def test_read_containment_hooks(self):
        hooks = HOOKS.read_text()
        for doctype in ("TH Instructor Contract", "TH Teaching Assignment"):
            self.assertIn(f'"{doctype}"', hooks)
        self.assertIn('("TH Instructor Contract", "contract")', hooks)
        self.assertIn('("TH Teaching Assignment", "assignment")', hooks)

    def test_commands_are_post_whitelisted_with_request_key(self):
        tree = ast.parse(COMPENSATION.read_text())
        seen = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in COMMANDS:
                decorated = any(
                    isinstance(dec, ast.Call)
                    and getattr(dec.func, "attr", "") == "whitelist"
                    and any(kw.arg == "methods" and [e.value for e in kw.value.elts] == ["POST"]
                            for kw in dec.keywords)
                    for dec in node.decorator_list)
                self.assertTrue(decorated, node.name)
                self.assertEqual(node.args.args[0].arg, "request_key", node.name)
                seen[node.name] = True
        self.assertEqual(set(seen), set(COMMANDS))

    def test_assign_enforces_active_and_effective_contract(self):
        """Regression (run 35060611969): assignment is refused unless the
        contract is Active AND effective for the assignment window."""
        source = COMPENSATION.read_text()
        self.assertIn("Assignments require an active contract", source)
        self.assertIn("Contract is not effective for the assignment window", source)
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "assign_teaching_skill")
        body = ast.dump(fn)
        self.assertIn("windows_overlap", body)
        self.assertIn("status", body)

    def test_calculation_path_is_native_additional_salary_only(self):
        """The only doctypes the module ever creates are the two TH facts and
        the native Additional Salary payroll input — no slip/engine writes."""
        import re
        source = COMPENSATION.read_text()
        self.assertIn('ADDITIONAL_SALARY = "Additional Salary"', source)
        created = set()
        # S2: ref_doctype= references (ASSIGNMENT/ADJUSTMENT audit links) are
        # not creations; only bare doctype= payloads count.
        for match in re.finditer(r"(?<!ref_)doctype=([A-Z_]+|\"[^\"]+\")", source):
            created.add(match.group(1))
        self.assertLessEqual(created, {"ADDITIONAL_SALARY", "CONTRACT", "ASSIGNMENT"})
        self.assertIn("ADDITIONAL_SALARY", created)

    def test_one_off_payable_basis_prevents_cross_period_repay(self):
        """Owner decision D12 (2026-09-19): the flat amount is a ONE-OFF payable.

        ``compute_skill_payable`` returns a flat contract amount and
        ``assign_teaching_skill`` creates open-ended assignments, so every later
        payroll period selects the same assignment again. The Additional Salary
        dedup key includes ``payroll_date``, so same-period dedup cannot catch
        it. The command must therefore look up every payroll date already posted
        for the assignment and post nothing further, reporting the assignment
        under ``already_compensated_prior_period`` rather than skipping it
        silently or paying it twice.
        """
        source = COMPENSATION.read_text()
        self.assertIn("already_compensated_prior_period", source)
        self.assertIn("already_compensated[row.name] = already_paid", source)
        fn = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "calculate_teaching_compensation")
        body = ast.dump(fn)
        self.assertIn("already_paid", body)
        # Adjustments carry the identical flat-amount defect and must be covered
        # by the same one-off rule, not left as a second double-posting path.
        self.assertIn("adjustment_paid", body)
        # S2 (BUG-PAY-02): the one-off key is the adjustment ROW, not the
        # contract — a per-contract key swallowed every later adjustment once
        # any one of them had posted. Pin the per-row key and its audit link.
        self.assertIn('already_compensated[f"{contract.name}:{adjustment.name}"] = adjustment_paid', source)
        self.assertIn("ref_doctype=ADJUSTMENT, ref_docname=adjustment.name", source)
        self.assertNotIn("already_compensated[contract.name] = adjustment_paid", source)
        self.assertIn('"already_compensated_prior_period": already_compensated', source)
        # The superseded hold vocabulary must be gone, so the decided policy
        # cannot silently regress back into the undecided state.
        self.assertNotIn("held_pending_posting_basis", source)
        self.assertIn("D12", fn.body[0].value.value)

    def test_revision_closes_the_predecessor_window_at_the_successor_start(self):
        """Owner decision D12 (2026-09-19): a revision ends the old window.

        Without this the superseded contract kept its open-ended effective_end,
        so the calculation matched two contracts for any later period and
        refused to run at all. Only the window is closed - no rate, term or
        adjustment on the predecessor is rewritten, so historical compensation
        stays reproducible, and the successor never reaches back before its own
        start date.
        """
        source = COMPENSATION.read_text()
        fn = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "revise_teaching_contract")
        body = ast.dump(fn)
        self.assertIn("effective_end", body)
        self.assertIn("timedelta", body)
        self.assertIn("Superseded", body)
        # A successor may never start on or before the contract it replaces.
        self.assertIn("A revised contract must start after the contract it replaces", source)
        self.assertIn("D12", source)


    def test_supersession_may_only_shorten_a_contract_window(self):
        """The D12 window closure must not become a general window edit.

        Contracts are immutable so historical compensation stays reproducible.
        Owner decision D12 permits exactly one window change - supersession
        closing the predecessor - and the controller must keep it directional:
        the end date may be set for the first time or move earlier, never later.
        Every other field, and all terms and adjustments, stay immutable.
        """
        source = (ROOT / "apps/toefl_house/toefl_house/controllers.py").read_text()
        fn = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef) and n.name == "_validate_contract")
        # The directional guard, not a blanket exemption.
        self.assertIn("A superseded contract's window may only be closed, never extended", source)
        self.assertIn("new_end > before_end", source)
        # effective_end is no longer in the blanket-immutable tuple, but
        # effective_start and every identity/term field still is.
        for field in ("instructor", "employee", "compensation_model", "assignment_basis",
                      "payment_frequency", "effective_start", "conditions", "supersedes"):
            self.assertIn(f'"{field}"', ast.get_source_segment(source, fn) or source)
        # Terms and adjustments remain immutable on supersession.
        self.assertIn("Contract terms and adjustments are immutable on supersession", source)
        self.assertIn("Only the contract status may change on supersession", source)


class DocTypeShapeTests(unittest.TestCase):
    def test_json_shape(self):
        for name, path in DOCTYPES.items():
            data = json.loads(path.read_text())
            self.assertEqual(data["name"], name)
            self.assertEqual(data["module"], "Teaching")
            child = name in ("TH Contract Skill Term", "TH Contract Adjustment")
            self.assertEqual(bool(data.get("istable")), child, name)
            if child:
                self.assertEqual(data["permissions"], [])
            elif name == "TH Skill":
                # Configuration master: Course Owner may create/update; operational
                # roles only read. Delete is forbidden for everyone (asserted separately).
                self.assertEqual(data["autoname"], "field:code")
                roles_with_write = {row["role"] for row in data["permissions"] if row.get("write")}
                self.assertEqual(roles_with_write, {"Course Owner"})
                for row in data["permissions"]:
                    self.assertFalse(row.get("delete"), "no role may delete a skill")
            else:
                # Operational TH records are command-only — no direct write via Desk.
                self.assertEqual(data["autoname"], "hash")
                for row in data["permissions"]:
                    self.assertNotIn("write", {k for k, v in row.items() if v == 1 and k != "role"},
                                     f"no role may hold direct write on {name}")
            fields = {f["fieldname"] for f in data["fields"]}
            if name == "TH Instructor Contract":
                self.assertLessEqual(
                    {"instructor", "employee", "compensation_model", "assignment_basis",
                     "payment_frequency", "effective_start", "effective_end", "conditions",
                     "supersedes", "status", "skill_terms", "adjustments", "synthetic"}, fields)
            if name == "TH Teaching Assignment":
                self.assertLessEqual(
                    {"student_group", "skill", "instructor", "contract", "course_schedule",
                     "effective_start", "effective_end", "synthetic"}, fields)
            if name == "TH Contract Skill Term":
                self.assertLessEqual(
                    {"skill", "unit_of_payment", "rate", "payable_quantity",
                     "minimum_amount", "maximum_amount"}, fields)
            if name == "TH Contract Adjustment":
                self.assertLessEqual(
                    {"adjustment_type", "amount", "effective_date", "approver", "reason"}, fields)

    def test_skill_fields_are_links_to_th_skill_master(self):
        """Skill is a configurable master, not a hard-coded Select list."""
        for name in ("TH Contract Skill Term", "TH Teaching Assignment"):
            data = json.loads(DOCTYPES[name].read_text())
            skill = next(f for f in data["fields"] if f["fieldname"] == "skill")
            self.assertEqual(skill["fieldtype"], "Link", f"{name} skill must be a Link")
            self.assertEqual(skill["options"], "TH Skill", f"{name} skill must link to TH Skill")
            self.assertTrue(skill.get("reqd"))

    def test_th_skill_master_shape(self):
        """TH Skill is a configuration master with stable code identity and Active/Retired lifecycle."""
        data = json.loads(DOCTYPES["TH Skill"].read_text())
        self.assertEqual(data["name"], "TH Skill")
        self.assertEqual(data["module"], "Teaching")
        self.assertFalse(data.get("istable"))
        fields = {f["fieldname"]: f for f in data["fields"]}
        self.assertEqual(fields["code"]["fieldtype"], "Data")
        self.assertTrue(fields["code"].get("unique"))
        self.assertTrue(fields["code"].get("set_only_once"))
        self.assertEqual(fields["status"]["fieldtype"], "Select")
        self.assertIn("Active", fields["status"]["options"])
        self.assertIn("Retired", fields["status"]["options"])
        # No role may delete configuration (track_changes on, no delete perm).
        self.assertTrue(data.get("track_changes"))
        for row in data["permissions"]:
            self.assertNotIn("delete", {k for k, v in row.items() if v == 1 and k != "role"},
                             "no role may delete a skill")

    def test_controller_invariants_wired(self):
        controllers = (APP / "controllers.py").read_text()
        self.assertIn('self.doctype == "TH Instructor Contract"', controllers)
        self.assertIn('self.doctype == "TH Teaching Assignment"', controllers)
        for doctype in ("TH Instructor Contract", "TH Teaching Assignment"):
            py = DOCTYPES[doctype].with_suffix("").with_name(
                DOCTYPES[doctype].stem + ".py").read_text()
            self.assertIn("ProtectedRecord", py)


if __name__ == "__main__":
    unittest.main()
