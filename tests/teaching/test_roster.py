"""S8 regression: mid-term roster commands (OD-NEW-05 mechanism).

add_class_member / move_class_member execute inside an open
roster-change window only; both refuse fail-closed on unconfigured or
expired cutoffs, non-enrolled students, terminal/disabled classes, and
full rosters. Moves lock both groups in name order and deactivate the
source row instead of deleting it. Loads the REAL teaching module
against a scripted frappe stub; hosted CI proves the roster journey.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "teaching.scheduler@example.com"


class _PermissionError(Exception):
    pass


class _ValidationError(Exception):
    pass


def _load_real(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


class _Row(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def as_dict(self):
        return dict(self)


class _GroupDoc:
    def __init__(self, name, students):
        self.name = name
        self._students = [_Row(s) for s in students]
        self.flags = SimpleNamespace()
        self.saved = False
        self.appended = []

    def get(self, field):
        if field == "students":
            return self._students
        return None

    def append(self, field, row):
        assert field == "students"
        fresh = _Row(row)
        self._students.append(fresh)
        self.appended.append(fresh)
        return fresh

    def save(self, ignore_permissions=False):
        self.saved = True
        return self


class RosterCommandTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.today = "2026-09-22"
        self.cutoff = "2026-10-15"
        self.students = {"STU-1": {"enabled": 1, "student_name": "Roster Probe"}}
        self.groups = {
            "GRP-A": {"program": "TH-PROG", "academic_year": "2026-27",
                      "academic_term": "Fall", "max_strength": 30,
                      "disabled": 0, "th_class_status": "Active"},
            "GRP-B": {"program": "TH-PROG", "academic_year": "2026-27",
                      "academic_term": "Fall", "max_strength": 30,
                      "disabled": 0, "th_class_status": "Active"},
        }
        self.roster = {}
        self.counts = {}
        self.enrollments = [{"name": "ENR-1"}]
        self.group_docs = {}
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def sql(query, values=(), **kwargs):
            fake.calls.append((query, tuple(values)))
            if "tabStudent Group Student" in query:
                if "count(*)" in query:
                    return [(fake.counts.get(values[0], 0),)]
                key = (values[0], values[1])
                if key in fake.roster:
                    return [SimpleNamespace(student=values[1],
                                            active=fake.roster[key])]
                return []
            if "tabProgram Enrollment" in query:
                assert "for update" in query
                return list(fake.enrollments)
            if "tabStudent Group" in query:
                assert "for update" in query
                return [(values[0],)]
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_value(doctype, name_or_filters, fieldname=None, **kwargs):
            if doctype == "Student":
                assert name_or_filters in fake.students
                return fake.students[name_or_filters][fieldname]
            if doctype == "Student Group":
                return SimpleNamespace(
                    **fake.groups[name_or_filters])
            raise AssertionError(f"unexpected get_value {doctype} {fieldname}")

        def exists(doctype, name):
            if doctype == "Student":
                return name in fake.students
            if doctype == "Student Group":
                return name in fake.groups
            raise AssertionError(f"unexpected exists {doctype}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.utils = SimpleNamespace(today=lambda: fake.today)
        stub.db = SimpleNamespace(get_value=get_value, sql=sql, exists=exists)

        def get_doc(doctype, name=None, **kwargs):
            assert doctype == "Student Group"
            if name not in fake.group_docs:
                rows = [{"student": student, "active": active}
                        for (group, student), active in fake.roster.items()
                        if group == name]
                fake.group_docs[name] = _GroupDoc(name, rows)
            return fake.group_docs[name]

        stub.get_doc = get_doc
        sys.modules["frappe"] = stub
        sys.modules["frappe.utils"] = stub.utils

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        _load_real("toefl_house.policy", APP / "policy.py")
        security = types.ModuleType("toefl_house.security")
        security.active_command_kind = lambda: None
        security.is_production = lambda: False
        security.require_operational = lambda: None
        security.teaching_command_active = lambda doctype: True
        sys.modules["toefl_house.security"] = security
        api = types.ModuleType("toefl_house.api")
        api._execute = lambda kind, key, payload, work: work(ACTOR)[0]
        sys.modules["toefl_house.api"] = api
        rules = types.ModuleType("toefl_house.academic.rules")
        rules.resolve_duration = lambda *a, **k: None
        sys.modules["toefl_house.academic.rules"] = rules
        roster_policies = types.ModuleType("toefl_house.teaching.policies")
        roster_policies.governing_cutoff_date = (
            lambda on_date=None: fake.cutoff)
        sys.modules["toefl_house.teaching.policies"] = roster_policies
        self.teaching = _load_real("toefl_house.teaching",
                                   APP / "teaching/__init__.py")

    # --- add_class_member ------------------------------------------------

    def test_add_appends_a_new_row_and_records_the_cutoff(self):
        result = self.teaching.add_class_member(
            "test-key-roster-add0001", "GRP-A", "STU-1")
        self.assertEqual(result["student_group"], "GRP-A")
        self.assertEqual(result["student"], "STU-1")
        self.assertFalse(result["reactivated"])
        self.assertEqual(result["cutoff"], "2026-10-15")
        doc = self.group_docs["GRP-A"]
        self.assertTrue(doc.saved)
        self.assertEqual(len(doc.appended), 1)
        self.assertEqual(doc.appended[0]["student"], "STU-1")
        self.assertEqual(doc.appended[0]["active"], 1)

    def test_add_locks_group_before_probing_enrollment(self):
        self.teaching.add_class_member(
            "test-key-roster-add0002", "GRP-A", "STU-1")
        kinds = []
        for query, _values in self.calls:
            if "tabProgram Enrollment" in query:
                kinds.append("enrollment")
            elif "tabStudent Group Student" in query:
                kinds.append("roster")
            elif "tabStudent Group" in query:
                kinds.append("group")
        self.assertEqual(kinds[0], "group")
        self.assertLess(kinds.index("group"), kinds.index("enrollment"))

    def test_add_refused_without_a_policy_cutoff(self):
        self.cutoff = ""
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0003", "GRP-A", "STU-1")
        self.assertIn("not enabled", str(ctx.exception))

    def test_add_refused_after_the_cutoff(self):
        self.cutoff = "2026-09-20"
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0004", "GRP-A", "STU-1")
        self.assertIn("closed after 2026-09-20", str(ctx.exception))

    def test_add_refused_for_unknown_or_disabled_students(self):
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0005", "GRP-A", "STU-9")
        self.assertIn("Unknown student", str(ctx.exception))
        self.students["STU-1"]["enabled"] = 0
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0006", "GRP-A", "STU-1")
        self.assertIn("disabled", str(ctx.exception))

    def test_add_refused_for_disabled_or_terminal_classes(self):
        self.groups["GRP-A"]["disabled"] = 1
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0007", "GRP-A", "STU-1")
        self.assertIn("disabled", str(ctx.exception))
        self.groups["GRP-A"]["disabled"] = 0
        self.groups["GRP-A"]["th_class_status"] = "Completed"
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0008", "GRP-A", "STU-1")
        self.assertIn("Planned or Active", str(ctx.exception))

    def test_add_refused_without_a_matching_enrollment(self):
        self.enrollments = []
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0009", "GRP-A", "STU-1")
        self.assertIn("not enrolled", str(ctx.exception))

    def test_add_refused_for_an_active_member(self):
        self.roster[("GRP-A", "STU-1")] = 1
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0010", "GRP-A", "STU-1")
        self.assertIn("already an active member", str(ctx.exception))

    def test_add_reactivates_a_deactivated_row(self):
        self.roster[("GRP-A", "STU-1")] = 0
        result = self.teaching.add_class_member(
            "test-key-roster-add0011", "GRP-A", "STU-1")
        self.assertTrue(result["reactivated"])
        doc = self.group_docs["GRP-A"]
        self.assertTrue(doc.saved)
        self.assertEqual(doc.appended, [])
        self.assertEqual(doc.get("students")[0]["active"], 1)
        # Reactivation keeps the row count: no capacity probe runs.
        self.assertNotIn("count(*)", " ".join(q for q, _ in self.calls))

    def test_add_refused_when_the_group_is_full(self):
        self.counts["GRP-A"] = 30
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.add_class_member(
                "test-key-roster-add0012", "GRP-A", "STU-1")
        self.assertIn("is full", str(ctx.exception))

    # --- move_class_member -----------------------------------------------

    def test_move_deactivates_source_and_appends_target(self):
        self.roster[("GRP-A", "STU-1")] = 1
        result = self.teaching.move_class_member(
            "test-key-roster-move0001", "GRP-A", "STU-1", "GRP-B")
        self.assertEqual(result["from_group"], "GRP-A")
        self.assertEqual(result["to_group"], "GRP-B")
        self.assertFalse(result["reactivated"])
        self.assertEqual(result["cutoff"], "2026-10-15")
        source = self.group_docs["GRP-A"]
        target = self.group_docs["GRP-B"]
        self.assertTrue(source.saved)
        self.assertTrue(target.saved)
        self.assertEqual(source.get("students")[0]["active"], 0)
        self.assertEqual(len(target.appended), 1)

    def test_move_locks_both_groups_in_name_order(self):
        self.roster[("GRP-B", "STU-1")] = 1
        # Source sorts after target: locks must still run A-then-B.
        self.teaching.move_class_member(
            "test-key-roster-move0002", "GRP-B", "STU-1", "GRP-A")
        locks = [values[0] for query, values in self.calls
                 if "tabStudent Group" in query
                 and "Student Group Student" not in query]
        self.assertEqual(locks, ["GRP-A", "GRP-B"])

    def test_move_refused_when_source_and_target_match(self):
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0003", "GRP-A", "STU-1", "GRP-A")
        self.assertIn("must differ", str(ctx.exception))

    def test_move_refused_for_a_non_member_source(self):
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0004", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("not an active member", str(ctx.exception))

    def test_move_refused_without_target_intake_enrollment(self):
        self.roster[("GRP-A", "STU-1")] = 1
        self.enrollments = []
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0005", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("not enrolled", str(ctx.exception))

    def test_move_refused_when_already_active_in_target(self):
        self.roster[("GRP-A", "STU-1")] = 1
        self.roster[("GRP-B", "STU-1")] = 1
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0006", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("already an active member of GRP-B", str(ctx.exception))

    def test_move_reactivates_a_deactivated_target_row(self):
        self.roster[("GRP-A", "STU-1")] = 1
        self.roster[("GRP-B", "STU-1")] = 0
        result = self.teaching.move_class_member(
            "test-key-roster-move0007", "GRP-A", "STU-1", "GRP-B")
        self.assertTrue(result["reactivated"])
        target = self.group_docs["GRP-B"]
        self.assertEqual(target.appended, [])
        self.assertEqual(target.get("students")[0]["active"], 1)

    def test_move_refused_for_a_terminal_target(self):
        self.roster[("GRP-A", "STU-1")] = 1
        self.groups["GRP-B"]["th_class_status"] = "Cancelled"
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0008", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("Planned or Active", str(ctx.exception))

    def test_move_refused_after_the_cutoff(self):
        self.roster[("GRP-A", "STU-1")] = 1
        self.cutoff = "2026-09-20"
        with self.assertRaises(_ValidationError) as ctx:
            self.teaching.move_class_member(
                "test-key-roster-move0009", "GRP-A", "STU-1", "GRP-B")
        self.assertIn("closed after", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
