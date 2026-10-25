"""Full-population Owner analytics: never mistake a bounded page for a total.

Uses real function bodies with mocked, scoped projections; no live school data.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/toefl_house/toefl_house/desk/analytics.py"
OWNER = ROOT / "apps/toefl_house/toefl_house/desk/owner.py"
FUNCTIONS = {
    "_complete_project_rows", "_checked_project_count", "_summarize_by", "_money_sum",
    "enrollment_metrics", "admission_metrics", "attendance_metrics",
    "attendance_by_instructor", "tuition_metrics", "exception_metrics",
}


def load_analytics(*, rows=None, counts=None, error=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in FUNCTIONS]
    assert {n.name for n in nodes} == FUNCTIONS
    seen = []
    data = rows or {}
    totals = counts or {}

    def projection(desk, doctype, fields, **kwargs):
        seen.append(("rows", desk, doctype, dict(kwargs.get("filters") or {})))
        if error == ("rows", doctype):
            raise PermissionError("source denied")
        return list(data.get(doctype, []))[:kwargs.get("limit", 400)]

    def counted(desk, doctype, filters=None):
        seen.append(("count", desk, doctype, dict(filters or {})))
        if error == ("count", doctype):
            raise PermissionError("count denied")
        if doctype in totals:
            return totals[doctype]
        return len(data.get(doctype, []))

    scope = {
        "BOUNCE_WINDOW": 400, "LIMIT_QUEUES": 25,
        "_project_rows": projection, "_project_count": counted,
        "_today": lambda: "2026-10-25",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
         scope)
    return scope, seen


class VerifiedCoverageTests(unittest.TestCase):
    def test_exact_scoped_count_and_filters_used_for_same_population(self):
        ns, calls = load_analytics(
            rows={"Program Enrollment": [{"name": "E1"}]})
        result = ns["_complete_project_rows"](
            "management", "Program Enrollment", ["name"],
            filters={"docstatus": 1}, order_by="name")
        self.assertEqual(result, [{"name": "E1"}])
        self.assertEqual(calls, [
            ("rows", "management", "Program Enrollment", {"docstatus": 1}),
            ("count", "management", "Program Enrollment", {"docstatus": 1}),
        ])

    def test_zero_and_exactly_400_are_supported(self):
        ns, _ = load_analytics()
        self.assertEqual(ns["_complete_project_rows"](
            "management", "Program Enrollment", ["name"]), [])
        sample = [{"name": str(i)} for i in range(400)]
        ns, _ = load_analytics(rows={"Program Enrollment": sample})
        self.assertEqual(len(ns["_complete_project_rows"](
            "management", "Program Enrollment", ["name"])), 400)

    def test_401st_record_never_silently_disappears(self):
        sample = [{"name": str(i)} for i in range(401)]
        ns, _ = load_analytics(rows={"Program Enrollment": sample})
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            ns["_complete_project_rows"](
                "management", "Program Enrollment", ["name"])

    def test_denied_or_missing_count_is_not_a_zero(self):
        for bad in (-1, None, False, 2, "1"):
            with self.subTest(count=bad):
                ns, _ = load_analytics(
                    rows={"Program Enrollment": [{"name": "E1"}]},
                    counts={"Program Enrollment": bad})
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    ns["_complete_project_rows"](
                        "management", "Program Enrollment", ["name"])
        for phase in ("rows", "count"):
            ns, _ = load_analytics(error=(phase, "Program Enrollment"))
            with self.assertRaises(PermissionError):
                ns["_complete_project_rows"](
                    "management", "Program Enrollment", ["name"])

    def test_aggregate_limit_is_explicit_not_unbounded(self):
        ns, _ = load_analytics()
        for limit in (0, 401, -1, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ns["_complete_project_rows"](
                    "management", "Program Enrollment", ["name"], limit=limit)

    def test_owner_enrollment_and_open_admissions_reject_401(self):
        for function, name in (
                ("enrollment_metrics", "Program Enrollment"),
                ("admission_metrics", "TH Admission Decision")):
            with self.subTest(function=function):
                ns, _ = load_analytics(
                    rows={name: [{"name": str(i)} for i in range(401)]})
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    ns[function]()

    def test_attendance_cannot_publish_rate_from_400_of_401(self):
        values = ([{"name": str(i), "status": "Present"} for i in range(400)]
                  + [{"name": "401", "status": "Absent"}])
        ns, _ = load_analytics(rows={"Student Attendance": values})
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            ns["attendance_metrics"]()

    def test_finance_counts_and_currency_sums_require_all_sources(self):
        for doctype in ("Fees", "Sales Invoice", "Payment Entry"):
            with self.subTest(doctype=doctype):
                rows = [{"name": str(i), "grand_total": 1,
                         "outstanding_amount": 1, "paid_amount": 1,
                         "posting_date": "2026-10-25", "currency": "AFN"}
                        for i in range(401)]
                ns, _ = load_analytics(rows={doctype: rows})
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    ns["tuition_metrics"]()

    def test_instructor_and_exception_counts_reject_bounded_queue(self):
        ns, _ = load_analytics(
            rows={"Course Schedule": [{"name": str(i)}
                                      for i in range(401)]})
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            ns["attendance_by_instructor"]()
        for doctype, n in (
                ("TH Placement Attempt", 401),
                ("TH Placement Decision", 401)):
            with self.subTest(doctype=doctype):
                ns, _ = load_analytics(
                    rows={doctype: [{"name": str(i)} for i in range(n)]})
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    ns["exception_metrics"]()

    def test_queue_total_uses_full_count_even_when_26_or_more_pending(self):
        ns, calls = load_analytics(rows={
            "TH Correction Request": [{"name": str(i)} for i in range(26)],
            "TH Admission Decision": [{"name": str(i)} for i in range(26)],
        })
        result = ns["exception_metrics"]()
        self.assertEqual(result["corrections_pending"], 26)
        self.assertEqual(result["admissions_in_review"], 26)
        self.assertFalse(any(
            phase == "rows" and dt in ("TH Correction Request",
                                        "TH Admission Decision")
            for phase, _, dt, _ in calls))
        self.assertIn(("count", "management", "TH Correction Request",
                       {"status": "Requested"}), calls)
        self.assertIn(("count", "management", "TH Admission Decision",
                       {"status": "Review"}), calls)

    def test_denied_correction_count_is_unavailable_not_zero(self):
        ns, _ = load_analytics(error=("count", "TH Correction Request"))
        with self.assertRaises(PermissionError):
            ns["exception_metrics"]()

    def test_closed_admission_count_must_be_validated(self):
        ns, _ = load_analytics()
        original_count = ns["_project_count"]

        def count(desk, doctype, filters=None):
            if doctype == "TH Admission Decision" and filters and (
                    filters.get("status") == (
                        "in", ["Deferred", "Rejected", "Withdrawn", "Revoked", "Expired"])):
                return None
            return original_count(desk, doctype, filters=filters)

        ns["_project_count"] = count
        with self.assertRaisesRegex(RuntimeError, "count unavailable"):
            ns["admission_metrics"]()

    def test_d7_attendance_uses_verified_raw_counts_without_derived_rate(self):
        ns, _ = load_analytics(rows={
            "Student Attendance": [
                {"name": "A1", "status": "Present", "student_group": "Class 1"},
                {"name": "A2", "status": "Absent", "student_group": "Class 1"},
            ],
        })
        result = ns["attendance_metrics"]()
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["present"], 1)
        self.assertEqual(result["absent"], 1)
        self.assertEqual(result["rate"], "—")
        self.assertEqual(result["rate_status"], "DEFERRED")
        # Both hero and attendance facts must label withheld data explicitly.
        self.assertEqual(OWNER.read_text(encoding="utf-8").count(
            '"label": "Attendance rate (D7 deferred)"'), 2)

    def test_malformed_placement_deadline_fails_closed_not_zero(self):
        from datetime import datetime
        from types import ModuleType
        from unittest.mock import patch
        import sys

        ns, _ = load_analytics(rows={
            "TH Placement Attempt": [
                {"name": "T1", "deadline_at": "not-a-date", "status": "Allocated"}
            ],
        })
        module = ModuleType("frappe.utils")
        module.now_datetime = lambda: datetime(2026, 10, 25, 12, 0)
        def invalid_datetime(_):
            raise ValueError("invalid date")
        module.get_datetime = invalid_datetime
        with patch.dict(sys.modules, {"frappe.utils": module}):
            with self.assertRaisesRegex(RuntimeError, "deadline source incomplete"):
                ns["exception_metrics"]()

    def test_missing_placement_clock_fails_closed_not_zero(self):
        from unittest.mock import patch
        import sys

        ns, _ = load_analytics(rows={
            "TH Placement Attempt": [
                {"name": "T1", "deadline_at": "2026-10-25", "status": "Allocated"}
            ],
        })
        with patch.dict(sys.modules, {"frappe.utils": None}):
            with self.assertRaisesRegex(RuntimeError, "deadline source incomplete"):
                ns["exception_metrics"]()

    def test_valid_finance_totals_remain_real_numbers(self):
        ns, _ = load_analytics(rows={
            "Fees": [
                {"name": "F1", "grand_total": 100, "outstanding_amount": 20,
                 "currency": "AFN", "due_date": "2026-10-01"},
                {"name": "F2", "grand_total": 30, "outstanding_amount": 0,
                 "currency": "USD", "due_date": "2026-11-01"}],
            "Payment Entry": [
                {"name": "P1", "posting_date": "2026-10-25", "paid_amount": 10,
                 "paid_from_account_currency": "AFN"}],
        })
        result = ns["tuition_metrics"]()
        self.assertEqual(result["fees_total"], 2)
        self.assertEqual(result["fees_outstanding"], 1)
        self.assertEqual(result["fees_overdue"], 1)
        self.assertIn("AFN", result["by_currency_charged"])
        self.assertIn("USD", result["by_currency_charged"])
        self.assertIn("10.00 AFN", result["collected_today"])
        self.assertIn(("count", "management", "Payment Entry",
                       {"docstatus": 1, "payment_type": "Receive",
                        "posting_date": "2026-10-25"}), _)



def run_owner_cockpit(*, deny_counts=False):
    """Exercise the actual Owner endpoint body without a live bench."""
    import types

    tree = ast.parse(OWNER.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "cockpit")
    # The imported frappe.whitelist decorator is not part of the read logic.
    fn.decorator_list = []
    calls = []
    admissions = [
        {"name": str(i), "status": "Review", "student_applicant": "A",
         "program": "P", "accepted": False, "native_student": None,
         "modified": "2026-10-20"}
        for i in range(400)
    ]

    def rows(desk, doctype, fields, **kwargs):
        calls.append(("rows", doctype, kwargs.get("filters")))
        return admissions if doctype == "TH Admission Decision" else []

    def count(desk, doctype, filters=None):
        calls.append(("count", doctype, filters))
        if deny_counts and doctype in ("TH Admission Decision", "Student Group"):
            raise PermissionError("count denied")
        return {"TH Admission Decision": 401, "Student Group": 26}.get(doctype, 0)

    def section(sid, title, kind, **kwargs):
        return dict(id=sid, title=title, kind=kind, **kwargs)

    scope = {
        "SLUG": "th-owner-cockpit",
        "ATTEMPT": "TH Placement Attempt",
        "ADMISSION": "TH Admission Decision",
        "DECISION": "TH Placement Decision",
        "STUDENT": "Student",
        "GROUP": "Student Group",
        "DESKS": {"th-owner-cockpit": {"title": "Owner", "roles": ["Course Owner"]}},
        "RELEASE_POSTURE": [],
        "BOUNCE_WINDOW": 400, "LIMIT_QUEUES": 25,
        "require_desk_audience": lambda slug: None,
        "project_rows": rows, "project_count": count,
        "lifecycle": types.SimpleNamespace(
            ADMISSION_OPEN_STATUSES=["Draft", "Review", "Approved", "Conditional"],
            PLACEMENT_ATTEMPT_ORDER=["Allocated", "Finalized"],
            admission_stage=lambda *args: {"next": "Review", "role": "Approver"}),
        "_funnel_and_exceptions": lambda: ([], []),
        "_system_health": lambda: ([], []),
        "_role_items": lambda _: [],
        "_staff_counts": lambda: [],
        "_recorded_action_items": lambda: [],
        "_executive_analytics_sections": lambda: [],
        "_site_mode": lambda: "REFUSED",
        "_age_label": lambda x: "",
        "viewer_roles": lambda: [],
        "section": section,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(OWNER), "exec"), scope)
    return scope["cockpit"](), calls


class OwnerCockpitCoverageContracts(unittest.TestCase):
    def test_owner_summary_counts_scoped_records_not_bounded_previews(self):
        tree = ast.parse(OWNER.read_text(encoding="utf-8"))
        cockpit = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == "cockpit")
        calls = [n for n in ast.walk(cockpit) if isinstance(n, ast.Call)]
        self.assertFalse(any(
            isinstance(n.func, ast.Name) and n.func.id == "active_cohort_rows"
            for n in calls), "25 class previews cannot be institution totals")
        # len(admissions_open) is permitted only as a sanity check against
        # the full count, never as the reported business metric.
        self.assertIn("admissions_count < len(admissions_open)",
                      OWNER.read_text())
        self.assertIn("classes_running = project_count", OWNER.read_text())
        self.assertIn("admissions_count = project_count", OWNER.read_text())

    def test_26_classes_and_401_open_admissions_are_counted_fully(self):
        result, calls = run_owner_cockpit()
        items = next(x for x in result["sections"]
                     if x["id"] == "business")["facts"]
        facts = {x["label"]: x["value"] for x in items}
        self.assertEqual(facts["Classes running"], 26)
        self.assertEqual(facts["Admissions in flight"], 401)
        self.assertIn(("count", "Student Group",
                       {"disabled": 0, "th_class_status": "Active"}), calls)
        self.assertEqual(sum(
            1 for kind, dt, _ in calls
            if kind == "rows" and dt == "Student Group"), 0)

    def test_denied_owner_count_does_not_claim_no_classes(self):
        result, _ = run_owner_cockpit(deny_counts=True)
        facts = {x["label"]: x["value"]
                 for x in next(x for x in result["sections"]
                               if x["id"] == "business")["facts"]}
        self.assertEqual(facts["Classes running"], "—")
        self.assertEqual(facts["Admissions in flight"], "—")

    def test_errors_render_unavailable_not_empty_or_zero(self):
        content = OWNER.read_text(encoding="utf-8")
        self.assertIn('"executive-unavailable"', content)
        self.assertIn('"corrections_pending": "—"', content)
        self.assertIn('classes_running = "—"', content)
        self.assertIn('admissions_count = "—"', content)
        self.assertNotIn("No open admission is waiting and no exception is recorded.", content)


if __name__ == "__main__":
    unittest.main()
