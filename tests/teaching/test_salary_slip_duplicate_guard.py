"""Refinement of U-09: duplicate-payment protection at the HRMS submission
boundary, not only in worked-month reporting.

Reproduction (before the fix):
- ``worked_month_payroll`` (teaching/payroll_periods.py) is the ONLY owned
  code that refuses a second submitted Salary Slip for the same employee in
  the same worked period, and no production code calls it: it takes
  caller-supplied rows and is exercised only by
  tests/teaching/test_shamsi_payroll_periods.py.
- Native HRMS owns Salary Slip creation/submission. The app registers no
  doc_event for "Salary Slip" or "Additional Salary" in hooks.py, so a
  second slip for the same employee and the same exact period can be
  submitted natively and nothing owned refuses it; the reporting function
  only notices if someone feeds it the duplicate afterwards.
- ``calculate_teaching_compensation`` (teaching/compensation.py) already
  refuses to post a second Additional Salary for the same reference and
  payroll date (``_paid_dates`` + payment-state machine, covered by
  test_compensation_guards.py), so the remaining unguarded boundary is
  Salary Slip submission itself.

Fix under test: a ``before_submit`` (+ ``validate`` +
``before_update_after_submit``) doc_event guard on
"Salary Slip" that refuses submission when another submitted slip already
covers the same employee for the same exact (start_date, end_date),
serialised on the Employee row lock. ``before_cancel`` is pinned to the
same function per the A13 three-seam rule but is a no-op inside it:
cancelling can only remove a duplicate. Exact-period duplicates only:
overlapping-but-different periods stay legitimate native cases (partial
months, corrections) and remain flagged at reconciliation by
``worked_month_payroll``.
"""
import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
HOOKS = APP / "hooks.py"
GUARD_MODULE = APP / "teaching" / "salary_slip_guards.py"
GUARD_PATH = "toefl_house.teaching.salary_slip_guards.refuse_duplicate_worked_month_slip"


class _ValidationError(Exception):
    pass


class _SlipDoc:
    """Minimal Salary Slip shape: attribute access plus ``.get``."""

    def __init__(self, name, employee, start_date, end_date):
        self.name = name
        self.employee = employee
        self.start_date = start_date
        self.end_date = end_date

    def get(self, field, default=None):
        return getattr(self, field, default)


class _StubDB:
    """Models submitted Salary Slips plus Employee rows for the guard."""

    def __init__(self, submitted, employees):
        # submitted: list of dicts name/employee/start_date/end_date/docstatus
        self.submitted = list(submitted)
        self.employees = set(employees)
        self.queries = []

    def sql(self, query, values=(), **kwargs):
        self.queries.append((query, tuple(values)))
        if "tabEmployee" in query:
            assert "for update" in query, "employee serialization must lock"
            return [(values[0],)] if values[0] in self.employees else []
        if "tabSalary Slip" in query:
            assert "for update" in query, "duplicate re-read must lock"
            assert "docstatus=1" in query or "docstatus" in query
            employee, start, end, name = values
            return [(row["name"],) for row in self.submitted
                    if row["employee"] == employee
                    and row["start_date"] == start
                    and row["end_date"] == end
                    and row["docstatus"] == 1
                    and row["name"] != name]
        raise AssertionError(f"unexpected sql {query[:80]}")


def _load_guard(stub_db):
    previous = dict(sys.modules)
    stub = types.ModuleType("frappe")
    stub.ValidationError = _ValidationError
    stub.db = SimpleNamespace(sql=stub_db.sql)
    sys.modules["frappe"] = stub
    try:
        spec = importlib.util.spec_from_file_location(
            "toefl_house.teaching.salary_slip_guards", GUARD_MODULE)
        module = importlib.util.module_from_spec(spec)
        sys.modules["toefl_house.teaching.salary_slip_guards"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.clear()
        sys.modules.update(previous)


def _hook_events():
    tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "doc_events" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("doc_events assignment not found in hooks.py")


class SalarySlipDuplicateGuardTests(unittest.TestCase):
    def _guard(self, submitted, employees=("EMP-1", "EMP-2")):
        self.db = _StubDB(submitted, employees)
        module = _load_guard(self.db)
        return module.refuse_duplicate_worked_month_slip

    def test_hooks_register_the_guard_on_submit_and_validate(self):
        events = _hook_events()
        self.assertIn("Salary Slip", events)
        self.assertEqual(events["Salary Slip"].get("before_submit"), GUARD_PATH)
        self.assertEqual(events["Salary Slip"].get("validate"), GUARD_PATH)
        # A13 seam discipline: post-submit edits run
        # before_update_after_submit WITHOUT validate, so a date edit that
        # would create a duplicate must be refused on that seam too.
        self.assertEqual(
            events["Salary Slip"].get("before_update_after_submit"), GUARD_PATH)
        # The A13 three-seam rule (tests/foundation/test_app_assembly.py)
        # requires before_cancel pinned to the same guard; the guard
        # itself is a no-op on that seam (see the cancel test below).
        self.assertEqual(events["Salary Slip"].get("before_cancel"), GUARD_PATH)

    def test_cancelling_a_duplicate_is_allowed(self):
        # Cancelling can only remove a duplicate. If the guard refused a
        # cancel while another submitted duplicate existed, a pre-existing
        # legacy duplicate pair could never be resolved: neither slip
        # could be cancelled. So before_cancel is a deliberate no-op.
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 1}])
        guard(_SlipDoc("SAL-002", "EMP-1", "2026-09-23", "2026-10-22"),
              "before_cancel")
        self.assertEqual(self.db.queries, [])

    def test_second_submitted_slip_for_same_employee_and_period_is_refused(self):
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 1}])
        duplicate = _SlipDoc("SAL-002", "EMP-1", "2026-09-23", "2026-10-22")
        with self.assertRaisesRegex(_ValidationError, "already exists|duplicate"):
            guard(duplicate, "before_submit")
        # The Employee row lock runs before the duplicate re-read, so a
        # concurrent submission for the same employee serializes on it.
        self.assertTrue(any("tabEmployee" in q for q, _ in self.db.queries))
        self.assertTrue(any("tabSalary Slip" in q for q, _ in self.db.queries))

    def test_first_slip_for_the_period_submits(self):
        guard = self._guard([])
        guard(_SlipDoc("SAL-001", "EMP-1", "2026-09-23", "2026-10-22"),
              "before_submit")

    def test_same_period_for_a_different_employee_submits(self):
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 1}])
        guard(_SlipDoc("SAL-009", "EMP-2", "2026-09-23", "2026-10-22"),
              "before_submit")

    def test_different_period_for_the_same_employee_submits(self):
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 1}])
        # A later worked month (or a partial-month correction slip) is a
        # distinct native payable, not a duplicate of the first slip.
        guard(_SlipDoc("SAL-002", "EMP-1", "2026-10-23", "2026-11-21"),
              "before_submit")

    def test_cancelled_slip_does_not_block_a_replacement(self):
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 2}])
        guard(_SlipDoc("SAL-002", "EMP-1", "2026-09-23", "2026-10-22"),
              "before_submit")

    def test_unknown_employee_fails_closed(self):
        guard = self._guard([], employees=())
        with self.assertRaises(_ValidationError):
            guard(_SlipDoc("SAL-001", "EMP-GHOST", "2026-09-23", "2026-10-22"),
                  "before_submit")

    def test_resubmitting_the_same_slip_is_not_a_duplicate_of_itself(self):
        # Re-running the guard on the already-submitted slip itself (same
        # name) must not refuse: the duplicate query excludes its own name.
        guard = self._guard([{"name": "SAL-001", "employee": "EMP-1",
                              "start_date": "2026-09-23", "end_date": "2026-10-22",
                              "docstatus": 1}])
        guard(_SlipDoc("SAL-001", "EMP-1", "2026-09-23", "2026-10-22"),
              "validate")


if __name__ == "__main__":
    unittest.main()
