"""S2 regression: compensation locking + per-adjustment one-off state.

BUG-PAY-01: calculate_teaching_compensation must serialize overlapping runs
on the covering contract rows (sorted-name order) and re-read postings with
locking reads, so concurrent different-key calculations cannot double-post
on any isolation level.
BUG-PAY-02: the adjustment one-off key is the adjustment ROW (TH Contract
Adjustment name), not the contract: a posted adjustment must not suppress
distinct later adjustments.

Loads the REAL policy/compensation modules against a scripted frappe stub.
Hosted proof (ref convention end-to-end + concurrent-calc race) lives in
tools/placement/native_checks.py and executes on push CI.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"
ACTOR = "finance.officer@example.com"

CONTRACT = "TH Instructor Contract"
ASSIGNMENT = "TH Teaching Assignment"
ADJUSTMENT = "TH Contract Adjustment"
ADDITIONAL_SALARY = "Additional Salary"


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


def _term(skill="SL", quantity=2, rate=100.0):
    return SimpleNamespace(skill=skill, payable_quantity=quantity, rate=rate,
                           minimum_amount=None, maximum_amount=None)


def _adjustment(name, effective_date="2026-09-15", kind="Bonus", amount=50.0):
    return SimpleNamespace(name=name, adjustment_type=kind, amount=amount,
                           effective_date=effective_date)


def _contract(name, adjustments=(), status="Active", start="2026-01-01", end=None):
    return SimpleNamespace(name=name, status=status, effective_start=start,
                           effective_end=end, compensation_model="Skill-Based",
                           employee="EMP-1", skill_terms=[_term()], adjustments=list(adjustments))


def _assignment(name="A-1", instructor="INS-1", contract="C-1"):
    return SimpleNamespace(name=name, student_group="G-1", skill="SL",
                           instructor=instructor, contract=contract,
                           effective_start="2026-09-01", effective_end=None)


class _SalaryDoc:
    _counter = 0

    def __init__(self, payload, posted):
        type(self)._counter += 1
        self.name = f"ADS-{type(self)._counter:04d}"
        self._payload = dict(payload)
        self._posted = posted
        self.flags = SimpleNamespace()

    def insert(self, ignore_permissions=False):
        self._posted.append(self._payload)
        return self


class S2CompensationTests(unittest.TestCase):
    def setUp(self):
        _SalaryDoc._counter = 0
        self.assignments = [_assignment()]
        # get_all(CONTRACT) answers, consumed in call order (initial resolve
        # runs first, then one post-lock re-check per instructor).
        self.contract_lists = [[SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")]]
        self.contract_doc = _contract("C-1", [_adjustment("ADJ-1")])
        self.fresh_doc = None
        self.paid = {}
        self.currency = "USD"
        self.lock_order = []
        self.paid_queries = []
        self.posted = []
        self.get_doc_calls = []
        previous = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(previous)))
        fake = self

        def sql(query, values=(), **kwargs):
            if "tabTH Teaching Assignment" in query:
                return list(fake.assignments)
            if "tabTH Instructor Contract" in query and "for update" in query:
                fake.lock_order.append(values[0])
                return []
            if "tabAdditional Salary" in query:
                assert "for update" in query, "posting re-read must lock"
                fake.paid_queries.append((values[0], values[1]))
                return [(day,) for day in fake.paid.get((values[0], values[1]), [])]
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_all(doctype, filters=None, fields=None, **kwargs):
            if doctype == CONTRACT:
                return list(fake.contract_lists.pop(0))
            raise AssertionError(f"unexpected get_all {doctype}")

        def get_doc(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                payload = dict(doctype)
                assert payload.pop("doctype") == ADDITIONAL_SALARY
                return _SalaryDoc(payload, fake.posted)
            if doctype == CONTRACT:
                fake.get_doc_calls.append((name, for_update))
                if for_update and fake.fresh_doc is not None:
                    return fake.fresh_doc
                return fake.contract_doc
            raise AssertionError(f"unexpected get_doc {doctype}")

        stub = types.ModuleType("frappe")
        stub.session = SimpleNamespace(user=ACTOR)
        stub.conf = {"toefl_house_synthetic_only": 1, "allow_tests": 1}
        stub.local = SimpleNamespace(site="placement-test.localhost")
        stub.PermissionError = _PermissionError
        stub.ValidationError = _ValidationError
        stub.get_roles = lambda user: {"Finance Officer"}
        stub.whitelist = lambda **kwargs: (lambda func: func)
        stub.flags = SimpleNamespace()
        stub.db = SimpleNamespace(
            get_value=lambda doctype, name, field=None, **k: fake.currency,
            exists=lambda doctype, name: True,
            get_all=get_all, sql=sql)
        stub.get_doc = get_doc
        sys.modules["frappe"] = stub

        package = types.ModuleType("toefl_house")
        package.__path__ = [str(APP)]
        sys.modules["toefl_house"] = package
        _load_real("toefl_house.policy", APP / "policy.py")
        security = types.ModuleType("toefl_house.security")
        security.record_synthetic_flag = lambda: 1
        sys.modules["toefl_house.security"] = security
        api = types.ModuleType("toefl_house.api")
        api._execute = lambda kind, key, payload, work: work(ACTOR)[0]
        sys.modules["toefl_house.api"] = api
        self.comp = _load_real("toefl_house.teaching.compensation",
                               APP / "teaching/compensation.py")

    def _calc(self, key="test-key-calc-00000001"):
        return self.comp.calculate_teaching_compensation(
            key, "2026-09-01", "2026-09-30", "SYN Teaching House",
            "SYN Teaching Pay", "SYN Contract Deduction")

    def test_covering_contracts_locked_before_posting(self):
        self.assignments = [_assignment("A-2", "INS-B", "C-ZEBRA"),
                            _assignment("A-1", "INS-A", "C-ALPHA")]
        zebra = _contract("C-ZEBRA", [_adjustment("ADJ-Z")])
        alpha = _contract("C-ALPHA", [_adjustment("ADJ-A")])
        docs = {"C-ZEBRA": zebra, "C-ALPHA": alpha}
        lists = {"INS-A": [SimpleNamespace(name="C-ALPHA", effective_start="2026-01-01",
                                           effective_end=None, compensation_model="Skill-Based")],
                 "INS-B": [SimpleNamespace(name="C-ZEBRA", effective_start="2026-01-01",
                                           effective_end=None, compensation_model="Skill-Based")]}
        def dispatch(doctype, filters=None, fields=None, **kwargs):
            return list(lists[filters["instructor"]])

        self.comp.frappe.db.get_all = dispatch
        real_get_doc = self.comp.frappe.get_doc

        def doc_dispatch(doctype, name=None, for_update=False, **kwargs):
            if isinstance(doctype, dict):
                return real_get_doc(doctype, name, for_update=for_update, **kwargs)
            return docs[name]

        self.comp.frappe.get_doc = doc_dispatch
        self.contract_lists = [[SimpleNamespace(name="C-ALPHA", effective_start="2026-01-01",
                                               effective_end=None, compensation_model="Skill-Based")]]
        result = self._calc()
        # Sorted contract-name order, not instructor order: concurrent runs
        # lock the same sequence and cannot deadlock against each other.
        self.assertEqual(self.lock_order, ["C-ALPHA", "C-ZEBRA"])
        self.assertEqual(len(self.posted), 4)  # 2 assignments + 2 adjustments
        self.assertEqual(result["adjustments_posted"], 2)

    def test_window_closed_during_calculation_fails_closed(self):
        # A contract revised after candidate selection but before the lock
        # is caught by the locking re-fetch: a window that no longer covers
        # the payroll period refuses to pay. Nothing posted.
        self.fresh_doc = _contract("C-1", status="Superseded", end="2026-08-31")
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        with self.assertRaises(_ValidationError):
            self._calc()
        self.assertEqual(self.posted, [])

    def test_superseded_but_covering_contract_pays(self):
        # Historical reproducibility: a Superseded status alone is NOT a
        # refusal. A superseded contract whose window still covers the
        # payroll period pays normally (past payrolls resolve from the
        # revision that covered them). This test fails on the first S2
        # revision, which wrongly refused any non-Active contract.
        self.fresh_doc = _contract("C-1", [_adjustment("ADJ-1")], status="Superseded")
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        result = self._calc()
        self.assertEqual(result["assignments"], 1)
        self.assertEqual(result["adjustments_posted"], 1)
        self.assertEqual(len(self.posted), 2)

    def test_cover_change_during_calculation_fails_closed(self):
        self.contract_lists.append([SimpleNamespace(
            name="C-2", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        with self.assertRaises(_ValidationError):
            self._calc()
        self.assertEqual(self.posted, [])

    def test_per_adjustment_dedup_posts_only_unpaid(self):
        self.contract_doc = _contract("C-1", [_adjustment("ADJ-OLD", "2026-09-10"),
                                             _adjustment("ADJ-NEW", "2026-09-20")])
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        self.paid = {(ADJUSTMENT, "ADJ-OLD"): ["2026-08-31"]}
        result = self._calc()
        refs = {(row["ref_doctype"], row["ref_docname"]) for row in self.posted}
        self.assertIn((ASSIGNMENT, "A-1"), refs)
        self.assertIn((ADJUSTMENT, "ADJ-NEW"), refs)
        self.assertNotIn((ADJUSTMENT, "ADJ-OLD"), refs)
        self.assertEqual(result["adjustments_posted"], 1)
        self.assertEqual(result["already_compensated_prior_period"],
                         {"C-1:ADJ-OLD": ["2026-08-31"]})

    def test_same_period_rerun_skips_without_posting(self):
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        self.paid = {(ASSIGNMENT, "A-1"): ["2026-09-30"],
                     (ADJUSTMENT, "ADJ-1"): ["2026-09-30"]}
        result = self._calc()
        self.assertEqual(result["skipped_existing"], 2)
        self.assertEqual(result["posted"], {})
        self.assertEqual(result["adjustments_posted"], 0)
        self.assertEqual(self.posted, [])

    def test_posting_rereads_lock(self):
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        self._calc()
        # One locking existence re-read per payable reference.
        self.assertEqual(self.paid_queries, [(ASSIGNMENT, "A-1"), (ADJUSTMENT, "ADJ-1")])

    def test_missing_company_currency_fails_closed(self):
        self.currency = None
        with self.assertRaises(_ValidationError):
            self._calc()
        self.assertEqual(self.posted, [])
        self.assertEqual(self.lock_order, [])
