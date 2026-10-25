"""GM/Owner shared funnel must not manufacture totals from capped previews.

No live learner or accounting records; tests execute the actual source functions
with permission-scoped read/count stubs.
"""

import ast
from datetime import datetime
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = (Path(__file__).resolve().parents[2]
          / "apps/toefl_house/toefl_house/desk/operations.py")


def load_funnel(records=None, *, deny=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"_funnel_and_exceptions", "_scoped_count_or_unknown"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    data = records or {}
    calls = []

    def match(row, filters):
        for key, requested in (filters or {}).items():
            if isinstance(requested, tuple) and requested[0] == "in":
                if row.get(key) not in requested[1]:
                    return False
            elif row.get(key) != requested:
                return False
        return True

    def project_rows(desk, doctype, fields, filters=None, limit=25, **kwargs):
        assert desk == "management"
        calls.append(("rows", doctype, dict(filters or {}), limit))
        return [dict(row) for row in data.get(doctype, [])
                if match(row, filters)][:limit]

    def project_count(desk, doctype, filters=None):
        assert desk == "management"
        calls.append(("count", doctype, dict(filters or {}), None))
        if doctype == deny:
            raise PermissionError("count denied")
        return sum(1 for row in data.get(doctype, [])
                   if match(row, filters))

    scope = {
        "ADMISSION": "TH Admission Decision",
        "ATTEMPT": "TH Placement Attempt",
        "DECISION": "TH Placement Decision",
        "CORRECTION": "TH Correction Request",
        "GROUP": "Student Group",
        "BOUNCE_WINDOW": 400,
        "LIMIT_QUEUES": 25,
        "project_rows": project_rows,
        "project_count": project_count,
        "now_datetime": lambda: datetime(2026, 10, 25, 12),
        "_age_label": lambda value: "",
        "lifecycle": SimpleNamespace(
            ADMISSION_OPEN_STATUSES=["Draft", "Review", "Approved", "Conditional"],
            PLACEMENT_ATTEMPT_ORDER=["Allocated", "Finalized"]),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 str(SOURCE), "exec"), scope)
    return scope["_funnel_and_exceptions"], calls


def facts_by_label(payload):
    return {row["label"]: row["value"] for row in payload[0]}


class GeneralManagerFunnelCoverage(unittest.TestCase):
    def test_26_active_classes_and_corrections_are_full_counts(self):
        funnel, calls = load_funnel({
            "Student Group": [
                {"name": str(i), "disabled": 0, "th_class_status": "Active"}
                for i in range(26)],
            "TH Correction Request": [
                {"name": "C" + str(i), "status": "Requested"}
                for i in range(26)],
        })
        result = funnel()
        facts = facts_by_label(result)
        self.assertEqual(facts["Classes running"], 26)
        self.assertEqual(facts["Corrections pending"], 26)
        self.assertEqual(sum(item["stage"] == "Correction pending"
                             for item in result[1]), 25)
        self.assertEqual(facts["Enrollments awaiting a class"], "—")
        self.assertTrue(any(kind == "count" and doctype == "Student Group"
                            for kind, doctype, _, _ in calls))

    def test_401_review_admissions_are_not_misreported_as_400(self):
        funnel, _ = load_funnel({
            "TH Admission Decision": [
                {"name": str(i), "status": "Review", "student_applicant": str(i)}
                for i in range(401)],
        })
        result = funnel()
        self.assertEqual(facts_by_label(result)["Admissions in review"], 401)
        self.assertEqual(sum(item["stage"] == "Admission waiting in review"
                             for item in result[1]), 400)

    def test_denied_count_is_unknown_never_zero(self):
        funnel, _ = load_funnel(deny="Student Group")
        self.assertEqual(facts_by_label(funnel())["Classes running"], "—")

    def test_401_attempts_never_prove_zero_overdue(self):
        funnel, _ = load_funnel({
            "TH Placement Attempt": [
                {"name": str(i), "status": "Allocated",
                 "deadline_at": "2026-10-24"}
                for i in range(401)],
        })
        result = funnel()
        self.assertEqual(facts_by_label(result)["Placement deadlines overdue"], "—")
        self.assertTrue(any(item["id"] == "source:placement-deadlines"
                            for item in result[1]))

    def test_malformed_deadline_is_unknown_in_both_fact_and_queue(self):
        funnel, _ = load_funnel({
            "TH Placement Attempt": [
                {"name": "A1", "status": "Allocated",
                 "deadline_at": "not-a-date"}],
        })
        utils = ModuleType("frappe.utils")
        def invalid_datetime(_):
            raise ValueError("malformed")
        utils.get_datetime = invalid_datetime
        with patch.dict(sys.modules, {"frappe.utils": utils}):
            result = funnel()
        self.assertEqual(facts_by_label(result)["Placement deadlines overdue"], "—")
        self.assertTrue(any(item["id"] == "source:placement-deadlines"
                            for item in result[1]))

    def test_valid_empty_attempt_population_has_verified_zero(self):
        funnel, _ = load_funnel()
        self.assertEqual(facts_by_label(funnel())["Placement deadlines overdue"], 0)


if __name__ == "__main__":
    unittest.main()
