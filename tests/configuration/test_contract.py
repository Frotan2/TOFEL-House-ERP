"""Contract for the Academic Control Plane (docs/product/CONFIGURATION-PLANE.md).

Four layers are pinned here, offline:

1. The PURE RULES — validation, effective-dated duration resolution, the
   monotone version rule, progression integrity, and the business-language
   refusal messages. These functions are the reason "change Starter tuition"
   can never corrupt history: the same (versions, date) pair always resolves
   to the same governing version.
2. The DOCTYPE JSONs — identity fields are set-once, codes are unique, NO
   role holds delete (configuration is retired, never removed), Course Owner
   is the only writer, and native Version audit is on.
3. The COMMANDS — whitelisted, request-key-first, Course-Owner-gated,
   deliberately NOT synthetic-gated (governance precedent), consuming the
   pure rules instead of re-implementing them.
4. The TIES — registry/Page/hooks/projection entries, the modules.txt entry,
   and the hard-coded-policy audit: the owned application must contain no
   program names, level names, fee amounts or discount percentages.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/toefl_house/toefl_house"
ACADEMIC = APP / "academic"
sys.path.insert(0, str(ACADEMIC))

import rules  # noqa: E402  (pure module, no frappe)


def _version(value, unit, effective_from):
    return {"duration_value": value, "duration_unit": unit,
            "effective_from": effective_from}


class CodeValidationTests(unittest.TestCase):
    def test_codes_are_stable_identifiers(self):
        for good in ("GEN-ENG", "PREP-1", "EAP-L3", "AB"):
            self.assertEqual(rules.validate_code(good), good)
        for bad in ("", None, "a", "gen-eng", "-LEAD", "TRAIL-", "DOUB--LE",
                    "WITH SPACE", 7, "X" * 33):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rules.validate_code(bad)

    def test_titles_collapse_whitespace_and_bound_length(self):
        self.assertEqual(rules.validate_title("  General   English  "), "General English")
        with self.assertRaises(ValueError):
            rules.validate_title("   ")
        with self.assertRaises(ValueError):
            rules.validate_title("x" * 141, "Title")

    def test_sequence_bounds(self):
        self.assertEqual(rules.validate_sequence("3"), 3)
        for bad in (0, -1, "abc", None, True, 1000, 2.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rules.validate_sequence(bad)

    def test_duration_rejects_nonpositive_and_typos(self):
        self.assertEqual(rules.validate_duration_value("2", "Month"), 2.0)
        with self.assertRaises(ValueError):
            rules.validate_duration_value(0, "Month")
        with self.assertRaises(ValueError):
            rules.validate_duration_value(-3, "Week")
        # The ceiling is a typo guard, not business policy.
        with self.assertRaises(ValueError):
            rules.validate_duration_value(30, "Month")
        with self.assertRaises(ValueError):
            rules.validate_duration_value(2, "Quarter")

    def test_dates_are_real_calendar_dates(self):
        self.assertEqual(rules.parse_date("2026-07-01"), "2026-07-01")
        for bad in ("2026-13-01", "2026-02-30", "01-07-2026", "", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rules.parse_date(bad)


class DurationVersionTests(unittest.TestCase):
    """The §17 hard rule: configuration changes never rewrite history."""

    VERSIONS = (
        _version(2, "Month", "2026-01-01"),
        _version(3, "Month", "2026-07-01"),
    )

    def test_each_date_resolves_to_exactly_one_version(self):
        self.assertEqual(rules.resolve_duration(self.VERSIONS, "2025-12-31"), None)
        self.assertEqual(rules.resolve_duration(self.VERSIONS, "2026-01-01"),
                         self.VERSIONS[0])
        self.assertEqual(rules.resolve_duration(self.VERSIONS, "2026-06-30"),
                         self.VERSIONS[0])
        self.assertEqual(rules.resolve_duration(self.VERSIONS, "2026-07-01"),
                         self.VERSIONS[1])
        self.assertEqual(rules.resolve_duration(self.VERSIONS, "2030-01-01"),
                         self.VERSIONS[1])

    def test_resolution_is_stable_under_later_appends(self):
        later = self.VERSIONS + (_version(4, "Month", "2027-01-01"),)
        # A date that already resolved keeps resolving to the same version.
        self.assertEqual(rules.resolve_duration(later, "2026-06-30"), self.VERSIONS[0])
        self.assertEqual(rules.resolve_duration(later, "2026-08-01"), self.VERSIONS[1])

    def test_unsorted_input_resolves_identically(self):
        shuffled = (self.VERSIONS[1], self.VERSIONS[0])
        self.assertEqual(rules.resolve_duration(shuffled, "2026-06-30"),
                         self.VERSIONS[0])

    def test_new_versions_must_start_after_the_latest(self):
        with self.assertRaises(ValueError) as ctx:
            rules.check_version_appends(self.VERSIONS, "2026-07-01")
        self.assertIn("after the latest version (2026-07-01)", str(ctx.exception))
        with self.assertRaises(ValueError):
            rules.check_version_appends(self.VERSIONS, "2026-05-01")
        # Strictly later is accepted.
        rules.check_version_appends(self.VERSIONS, "2027-01-01")

    def test_latest_version_and_labels(self):
        self.assertEqual(rules.latest_version(self.VERSIONS), self.VERSIONS[1])
        self.assertEqual(rules.latest_version(()), None)
        self.assertEqual(rules.duration_label(_version(2, "Month", "2026-01-01")),
                         "2 months")
        self.assertEqual(rules.duration_label(_version(1, "Month", "2026-01-01")),
                         "1 month")
        self.assertEqual(rules.duration_label(_version(1.5, "Week", "2026-01-01")),
                         "1.5 weeks")
        self.assertEqual(rules.duration_label(None), "")


class FeeRuleTests(unittest.TestCase):
    def test_fee_amount_bounds(self):
        self.assertEqual(rules.validate_fee_amount("5000"), 5000.0)
        self.assertEqual(rules.validate_fee_amount(1250.5), 1250.5)
        for bad in (0, -1, "abc", None, True, 100_000_001):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rules.validate_fee_amount(bad)

    def test_component_rows_require_unique_nonempty_categories(self):
        rows = rules.validate_component_rows(
            [{"category": "Tuition Fee", "amount": 5000},
             {"category": "ID Card Fee", "amount": "300"}])
        self.assertEqual(rows[1]["amount"], 300.0)
        with self.assertRaises(ValueError, msg="empty"):
            rules.validate_component_rows([])
        with self.assertRaises(ValueError, msg="duplicate"):
            rules.validate_component_rows(
                [{"category": "Tuition Fee", "amount": 1},
                 {"category": " Tuition Fee ", "amount": 2}])
        with self.assertRaises(ValueError, msg="no category"):
            rules.validate_component_rows([{"amount": 5}])

    def test_year_bounds(self):
        start, end = rules.validate_year_bounds("2026-07-01", "2027-06-30")
        self.assertEqual((start, end), ("2026-07-01", "2027-06-30"))
        with self.assertRaises(ValueError):
            rules.validate_year_bounds("2027-06-30", "2026-07-01")


class ProgressionRuleTests(unittest.TestCase):
    LEVELS = {
        "A1": ("GEN", None),
        "A2": ("GEN", "A3"),
        "A3": ("GEN", None),
        "B1": ("EAP", None),
    }

    def family_of(self, code):
        row = self.LEVELS.get(code)
        return row[0] if row else None

    def next_of(self, code):
        row = self.LEVELS.get(code)
        return row[1] if row else None

    def test_next_level_must_exist_same_family_not_self_acyclic(self):
        rules.validate_next_level("A1", "A2", self.family_of, self.next_of)
        with self.assertRaises(ValueError):
            rules.validate_next_level("A1", "A1", self.family_of, self.next_of)
        with self.assertRaises(ValueError, msg="unknown level"):
            rules.validate_next_level("A1", "NOPE", self.family_of, self.next_of)
        with self.assertRaises(ValueError, msg="cross family"):
            rules.validate_next_level("A1", "B1", self.family_of, self.next_of)
        cyclic = dict(self.LEVELS, A3=("GEN", "A1"))
        family = lambda c: (cyclic.get(c) or (None,))[0]  # noqa: E731
        nxt = lambda c: (cyclic.get(c) or (None, None))[1]  # noqa: E731
        with self.assertRaises(ValueError, msg="cycle"):
            rules.validate_next_level("A1", "A2", family, nxt)
        rules.validate_next_level("A1", "", self.family_of, self.next_of)


class RefusalMessageTests(unittest.TestCase):
    def test_deactivation_refusals_carry_the_real_counts(self):
        message = rules.level_in_use_message("STARTER", 84)
        self.assertIn("STARTER", message)
        self.assertIn("84 submitted enrollment", message)
        self.assertIn("cannot be deactivated", message)
        program_message = rules.program_has_levels_message("GEN-ENG", 5)
        self.assertIn("GEN-ENG", program_message)
        self.assertIn("5 active level", program_message)

    def test_integrity_fault_is_surfaced_not_hidden(self):
        self.assertIn("integrity", rules.level_missing_native_message("X1"))


class DoctypeContractTests(unittest.TestCase):
    DOC = APP / "academic/doctype"

    def _load(self, name):
        return json.loads(
            (self.DOC / name / f"{name}.json").read_text(encoding="utf-8"))

    def test_configuration_masters_pin_identity_and_audit(self):
        for name, identity_fields in (
                ("th_academic_program", ("code",)),
                ("th_program_level", ("code", "family", "native_program"))):
            doc = self._load(name)
            self.assertEqual(doc["module"], "Academic")
            self.assertTrue(doc.get("track_changes"),
                            f"{name} must keep native Version audit")
            self.assertEqual(doc["engine"], "InnoDB")
            fields = {field["fieldname"]: field for field in doc["fields"]}
            for identity in identity_fields:
                self.assertTrue(fields[identity].get("set_only_once"),
                                f"{name}.{identity} must be set-once")
            self.assertTrue(fields["code"].get("unique"), f"{name}.code must be unique")

    def test_no_role_may_delete_configuration(self):
        for name in ("th_academic_program", "th_program_level"):
            doc = self._load(name)
            self.assertTrue(doc["permissions"], f"{name} must declare permissions")
            for perm in doc["permissions"]:
                self.assertNotIn("delete", {k for k, v in perm.items() if v == 1},
                                 f"{name}: no role may delete configuration")
                self.assertNotIn("cancel", {k for k, v in perm.items() if v == 1})

    def test_course_owner_is_the_only_writer(self):
        for name in ("th_academic_program", "th_program_level"):
            doc = self._load(name)
            for perm in doc["permissions"]:
                writers = {"write", "create"} & {k for k, v in perm.items() if v == 1}
                if writers:
                    self.assertEqual(perm["role"], "Course Owner",
                                     f"{name}: only Course Owner writes configuration")
            roles = {perm["role"] for perm in doc["permissions"]}
            self.assertEqual(roles, {"Course Owner", "General Manager", "Academic Manager"})

    def test_duration_child_table_has_no_standalone_life(self):
        doc = self._load("th_level_duration")
        self.assertTrue(doc["istable"])
        self.assertEqual(doc["permissions"], [])
        fields = {field["fieldname"]: field for field in doc["fields"]}
        self.assertEqual(fields["duration_unit"]["options"], "Month\nWeek\nDay")
        for field in ("set_by", "set_on", "superseded_on"):
            self.assertTrue(fields[field].get("read_only"), field)


def _module_source(relative):
    return (ACADEMIC / relative).read_text(encoding="utf-8")


class CommandContractTests(unittest.TestCase):
    COMMANDS = (
        "create_program", "create_level", "set_level_duration",
        "set_next_level", "set_program_status", "set_level_status",
        "create_academic_year", "create_fee_type",
        "set_level_fee_component", "remove_level_fee_component",
    )

    def _tree(self):
        return ast.parse(_module_source("__init__.py"))

    def test_commands_are_whitelisted_and_request_key_first(self):
        tree = self._tree()
        source = _module_source("__init__.py")
        functions = {node.name: node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef)}
        for name in self.COMMANDS:
            node = functions[name]
            decorated = any(getattr(dec, "attr", "") == "whitelist"
                            or "whitelist" in ast.unparse(dec)
                            for dec in node.decorator_list)
            self.assertTrue(decorated, f"{name} must be whitelisted")
            args = [a.arg for a in node.args.args]
            self.assertEqual(args[0], "request_key", f"{name} must be idempotent")
            position = source.index(f"def {name}")
            self.assertIn("@frappe.whitelist", source[max(0, position - 200):position])

    def test_gate_is_course_owner_and_never_synthetic(self):
        source = _module_source("__init__.py")
        self.assertIn('"Course Owner" not in set(frappe.get_roles(user))', source)
        self.assertNotIn("require_synthetic", source,
                         "configuration is a governance surface, not a synthetic command")
        self.assertNotIn("ignore_permissions=True) if False", source)
        # Every command opens the gate first.
        tree = self._tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in self.COMMANDS:
                calls = ast.unparse(node)
                self.assertIn("_require_course_owner()", calls,
                              f"{node.name} must gate on Course Owner")

    def test_commands_delegate_to_the_pure_rules(self):
        source = _module_source("__init__.py")
        for rule in ("rules.validate_code", "rules.validate_duration_value",
                     "rules.parse_date", "rules.check_version_appends",
                     "rules.validate_next_level", "rules.level_in_use_message"):
            self.assertIn(rule, source, f"commands must reuse {rule}")

    def test_governed_writes_use_the_guarded_pattern(self):
        source = _module_source("__init__.py")
        self.assertIn("validate_request_key(request_key)", source)
        self.assertIn("for_update=True", source, "mutations must row-lock the target")
        # The configuration write path is insert-inside-the-gate; the rule that
        # no OTHER path exists is enforced by the doctype permissions test.

    def test_refusals_are_business_language_not_raw_exceptions(self):
        source = _module_source("__init__.py")
        for literal in ("already exists", "cannot share one position",
                        "reactivate it before"):
            self.assertIn(literal, source)
        self.assertIn("program_has_levels_message", source)
        self.assertIn("level_in_use_message", source)


class ControlPlaneTieTests(unittest.TestCase):
    def test_desk_registry_page_hooks_and_projection_agree(self):
        init_source = (APP / "desk/__init__.py").read_text(encoding="utf-8")
        self.assertIn('"th-academic-setup"', init_source)
        for literal in ('"roles": ["Course Owner"]',):
            self.assertIn(literal, init_source)
        page = json.loads((APP / "operations/page/th-academic-setup/"
                           "th-academic-setup.json").read_text(encoding="utf-8"))
        self.assertEqual(page["module"], "Operations")
        self.assertEqual(page["title"], "TOEFL House Academic Setup")
        self.assertEqual([row["role"] for row in page["roles"]], ["Course Owner"])
        hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"th-academic-setup"', hooks)
        modules = (APP / "modules.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("Academic", modules)
        for pair in (('("setup", "TH Academic Program")',),
                     ('("setup", "TH Program Level")',),
                     ('("setup", "TH Level Duration")',),
                     ('("setup", "Program Enrollment")',)):
            self.assertIn(pair[0], init_source, f"missing projection allow-list {pair[0]}")

    def test_finance_desk_consumes_the_configured_fee_plans(self):
        """§18: billing guidance resolves the Owner's plan — one source of truth."""
        source = (APP / "desk/finance.py").read_text(encoding="utf-8")
        self.assertIn("Academic Setup", source,
                      "a missing plan must name its owner and where to fix it")
        self.assertIn("billing_guidance", source)
        self.assertIn('"fee_structure": editable[0]["name"]', source,
                      "the configured plan must be the prefill, never a blank field")
        for literal in ("No fee plan is configured", "has no components yet",
                        "More than one editable fee plan"):
            self.assertIn(literal, source)
        init_source = (APP / "desk/__init__.py").read_text(encoding="utf-8")
        for pair in (('("finance", "Fee Structure")',),
                     ('("finance", "Fee Component")',)):
            self.assertIn(pair[0], init_source, f"missing allow-list {pair[0]}")

    def test_setup_desk_consumes_the_pure_rules(self):
        source = (APP / "desk/setup.py").read_text(encoding="utf-8")
        self.assertIn("from toefl_house.academic import rules", source)
        self.assertIn("rules.resolve_duration", source,
                      "the desk must resolve durations from versions, not store them")
        self.assertIn("require_desk_audience(SLUG)", source)


class HardCodedPolicyAuditTests(unittest.TestCase):
    """§31: business names and amounts are Owner data, never code literals."""

    BANNED = ("General English", "Pre-Starter", "Prep One", "Prep Two",
              "Prep Three", "EAP", "IELTS", "Conversation Program")
    BANNED_WORDS = ("Starter",)

    def test_no_owned_python_module_contains_program_or_level_names(self):
        offenders = []
        for path in APP.rglob("*.py"):
            if "doctype" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for literal in self.BANNED:
                if literal in text:
                    offenders.append((str(path), literal))
            for word in self.BANNED_WORDS:
                if word in text:
                    offenders.append((str(path), word))
        self.assertEqual(offenders, [],
                         "hard-coded business policy found (move it to configuration "
                         "or, if a technical constant, rename it away from policy words)")

    def test_fee_orchestration_stays_on_native_authority(self):
        source = _module_source("__init__.py")
        # Fee plans are NATIVE Fee Structures keyed on the anchored program;
        # the command must keep them editable (Draft) and consumable.
        self.assertIn('"docstatus": 0', source,
                      "the managed fee structure must be the editable Draft")
        self.assertIn('"naming_series": FEE_STRUCTURE_NAMING', source)
        # Fee types are native Fee Categories; the accounting Item is created
        # by the native controller, and the command must fail closed if the
        # native Item Group fixture is missing.
        self.assertIn('"doctype": FEE_CATEGORY', source)
        self.assertIn("Item Group", source)
        self.assertIn("'Fee Component' item group is missing", source)
        # No parallel money model: no amounts beyond validation, no totals
        # persisted by the control plane.
        self.assertNotIn('"total_amount":', source)

    def test_no_owned_python_module_contains_fee_amounts_or_discounts(self):
        import re
        offenders = []
        pattern = re.compile(
            r"(amount|price|fee|tuition|discount)\s*=\s*[0-9]{3,}", re.IGNORECASE)
        for path in APP.rglob("*.py"):
            if "doctype" in path.parts or "__pycache__" in path.parts:
                continue
            for match in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append((str(path), match.group(0)))
        self.assertEqual(offenders, [], "hard-coded money policy found")


if __name__ == "__main__":
    unittest.main()
