"""D5/D7 safety: no false-zero analytics and no unapproved derived KPIs."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "apps/toefl_house/toefl_house/desk/analytics.py"
OWNER = ROOT / "apps/toefl_house/toefl_house/desk/owner.py"
TRANSFERS = ROOT / "apps/toefl_house/toefl_house/teaching/transfers.py"


def load_retention(*, exits=None, enrollments=None, count_exits=None,
                   count_enrollments=None, error=None):
    tree = ast.parse(ANALYTICS.read_text(encoding="utf-8"))
    selected = [x for x in tree.body if isinstance(x, ast.FunctionDef)
                and x.name == "retention_metrics"]
    if len(selected) != 1:
        raise AssertionError("Retention function missing")

    calls = []

    def rows(desk, doctype, fields, **kwargs):
        calls.append(("rows", doctype))
        if error == doctype:
            raise PermissionError("Native source denied or missing")
        return list(exits if doctype == "TH Enrollment Exit" else enrollments)

    def count(desk, doctype, **kwargs):
        calls.append(("count", doctype))
        if error == doctype:
            raise PermissionError("Native count denied or missing")
        if doctype == "TH Enrollment Exit":
            return count_exits if count_exits is not None else len(exits)
        return count_enrollments if count_enrollments is not None else len(enrollments)

    ns = {
        "BOUNCE_WINDOW": 400,
        "_project_rows": rows,
        "_project_count": count,
        "_summarize_by": lambda rows, key: {
            "withdrawn": len(rows)} if rows else {},
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]),
                 str(ANALYTICS), "exec"), ns)
    return ns["retention_metrics"], calls


class RetentionD7Tests(unittest.TestCase):
    def test_approved_business_rows_cannot_enable_derived_rate(self):
        metric, calls = load_retention(
            exits=[{"exit_kind": "withdrawn"}],
            enrollments=[{"name": "ENR-1"}])
        result = metric()
        self.assertEqual(result["exited"], 1)
        self.assertEqual(result["active"], 1)
        self.assertEqual(result["retention_rate"], "—")
        self.assertEqual(result["status"], "DEFERRED")
        self.assertIn("D7", result["definition"])
        self.assertEqual([c[0] for c in calls], ["rows", "rows", "count", "count"])

    def test_denied_exit_source_cannot_be_reported_as_zero(self):
        metric, _ = load_retention(
            exits=[], enrollments=[{"name": "ENR-1"}],
            error="TH Enrollment Exit")
        with self.assertRaises(PermissionError):
            metric()

    def test_denied_enrollment_source_cannot_be_reported_as_zero(self):
        metric, _ = load_retention(
            exits=[], enrollments=[], error="Program Enrollment")
        with self.assertRaises(PermissionError):
            metric()

    def test_incomplete_exit_and_enrollment_source_fail_closed(self):
        for incomplete in ("exit", "enrollment"):
            with self.subTest(incomplete=incomplete):
                metric, _ = load_retention(
                    exits=[{"name": "X1"}],
                    enrollments=[{"name": "ENR1"}],
                    count_exits=2 if incomplete == "exit" else 1,
                    count_enrollments=2 if incomplete == "enrollment" else 1)
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    metric()

    def test_over_400_rows_never_yield_a_percent_or_zero(self):
        metric, _ = load_retention(
            exits=[{"name": str(i)} for i in range(400)],
            enrollments=[{"name": "ENR1"}], count_exits=401)
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            metric()


class OwnerNoFalseZeroContracts(unittest.TestCase):
    def test_owner_never_substitutes_zero_on_exception(self):
        source = OWNER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        section_fn = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_executive_analytics_sections")
        # D7's derived waiting calculation is not executed from owner desk.
        invoked = [node.func.attr for node in ast.walk(section_fn)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Attribute)]
        self.assertNotIn("enrollment_cohort_breakdown", invoked)
        self.assertIn("project_count", [
            node.func.id for node in ast.walk(section_fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)])
        self.assertIn('"total": "—"', source)
        self.assertNotIn('"total": 0, "by_program": {}', source)
        self.assertIn("Waiting metric deferred", source)
        self.assertIn('"exited": "—"', source)

    def test_transfer_release_gate_is_separate_from_business_toggle(self):
        source = TRANSFERS.read_text(encoding="utf-8")
        tree = ast.parse(source)
        gate = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "_transfer_scope_authorized")
        self.assertIsInstance(gate.body[-1], ast.Return)
        self.assertIs(gate.body[-1].value.value, False)
        for name in ("request_class_transfer", "approve_class_transfer"):
            fn = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertIn("_require_transfer_scope",
                          [n.func.id for n in ast.walk(fn)
                           if isinstance(n, ast.Call)
                           and isinstance(n.func, ast.Name)])


if __name__ == "__main__":
    unittest.main()
