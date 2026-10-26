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
tools/native/native_checks.py and executes on push CI.
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
        self.company_permissions = []  # HQ unrestricted unless explicitly scoped
        self.lock_order = []
        self.paid_queries = []
        self.paid_sql_queries = []
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
                fake.paid_sql_queries.append(query)
                fake.paid_queries.append((values[0], values[1]))
                return [(day,) for day in fake.paid.get((values[0], values[1]), [])]
            raise AssertionError(f"unexpected sql {query[:80]}")

        def get_all(doctype, filters=None, fields=None, **kwargs):
            if doctype == "User Permission":
                return list(fake.company_permissions)
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
        def get_value(doctype, name, field=None, **kwargs):
            if doctype == "Salary Component" and field == "type":
                return "Deduction" if name == "SYN Contract Deduction" else "Earning"
            return fake.currency

        stub.db = SimpleNamespace(
            get_value=get_value,
            exists=lambda doctype, name: True,
            get_all=get_all, sql=sql)
        stub.get_all = get_all
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
        # S13: the calculation judges the adjustment posting policy. This
        # harness stands in for a skip-mode policy over fixtures with no
        # orphans — the posted counts below keep proving the locking and
        # one-off semantics they were written for.
        teaching_pkg = types.ModuleType("toefl_house.teaching")
        teaching_pkg.__path__ = []
        sys.modules["toefl_house.teaching"] = teaching_pkg
        posting = types.ModuleType("toefl_house.teaching.adjustment_posting")
        posting.POST = "post"
        posting.SKIP = "skip"
        posting.governing_posting_terms = lambda: {
            "effective_from": "2026-01-01", "orphan_posting": "skip"}
        posting.collect_orphan_contracts = lambda start, end, assigned: {}
        sys.modules["toefl_house.teaching.adjustment_posting"] = posting
        finance_pkg = types.ModuleType("toefl_house.finance")
        finance_pkg.__path__ = [str(APP / "finance")]
        sys.modules["toefl_house.finance"] = finance_pkg
        # A previously imported module must not retain another test's frappe
        # object when this scripted runtime installs its own Frappe stub.
        sys.modules.pop("toefl_house.finance.company_scope", None)
        _load_real("toefl_house.finance.shamsi", APP / "finance/shamsi.py")
        self.comp = _load_real("toefl_house.teaching.compensation",
                               APP / "teaching/compensation.py")

    def _calc(self, key="test-key-calc-00000001"):
        return self.comp.calculate_teaching_compensation(
            key, "2026-09-01", "2026-09-30", "SYN Teaching House",
            "SYN Teaching Pay", "SYN Contract Deduction")

    def test_scoped_finance_officer_cannot_post_another_companys_payroll(self):
        self.company_permissions = ["Other School"]
        with self.assertRaisesRegex(
                _PermissionError, "no finance authority for the selected company"):
            self._calc()
        self.assertEqual(self.posted, [])
        self.assertEqual(self.lock_order, [])

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

    def test_component_types_fail_closed_before_creating_payroll_inputs(self):
        with self.assertRaisesRegex(_ValidationError, "requires an Earning"):
            self.comp.calculate_teaching_compensation(
                "invalid-earning", "2026-09-01", "2026-09-30",
                "SYN Teaching House", "SYN Contract Deduction", "")
        with self.assertRaisesRegex(_ValidationError, "require a Deduction"):
            self.comp.calculate_teaching_compensation(
                "invalid-deduction", "2026-09-01", "2026-09-30",
                "SYN Teaching House", "SYN Teaching Pay", "SYN Teaching Pay")
        self.assertEqual(self.posted, [])

    def test_teaching_and_adjustment_inputs_never_overwrite_salary_structure(self):
        # Multiple one-off teaching facts for one employee/month/component
        # must be additive HRMS inputs. Otherwise native Additional Salary
        # refuses the second Submit as a duplicate overwrite.
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        self._calc()
        self.assertEqual(len(self.posted), 2)
        self.assertEqual({(item["ref_doctype"], item["ref_docname"]) for item in self.posted},
                         {(ASSIGNMENT, "A-1"), (ADJUSTMENT, "ADJ-1")})
        for item in self.posted:
            self.assertEqual(item["overwrite_salary_structure_amount"], 0)
            self.assertEqual(item["is_recurring"], 0)
            # HRMS filters on Additional Salary.type during slip generation.
            self.assertEqual(item["type"], "Earning")

    def test_deduction_adjustments_reach_native_deduction_component(self):
        self.contract_doc = _contract("C-1", [_adjustment("ADJ-D", kind="Deduction")])
        self.contract_lists.append([SimpleNamespace(
            name="C-1", effective_start="2026-01-01", effective_end=None,
            compensation_model="Skill-Based")])
        self._calc()
        self.assertEqual(len(self.posted), 2)
        salary = next(item for item in self.posted
                      if item["ref_doctype"] == ASSIGNMENT)
        deduction = next(item for item in self.posted
                         if item["ref_doctype"] == ADJUSTMENT)
        self.assertEqual(salary["type"], "Earning")
        self.assertEqual(deduction["type"], "Deduction")
        self.assertEqual(deduction["salary_component"], "SYN Contract Deduction")
        self.assertEqual(deduction["overwrite_salary_structure_amount"], 0)

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

    def _monthly_calc(self, start, end, paid=()):
        self.contract_doc.earning_basis = "Solar Hijri Monthly"
        self.contract_doc.adjustments = []
        self.contract_lists = [self.contract_lists[0][:], self.contract_lists[0][:]]
        self.paid = {(ASSIGNMENT, "A-1"): list(paid)}
        return self.comp.calculate_teaching_compensation(
            "monthly-native-input", start, end, "SYN Teaching House", "SYN Teaching Pay")

    def test_monthly_contract_pays_next_shamsi_month_after_previous_payment(self):
        result = self._monthly_calc("2026-10-23", "2026-11-21", ["2026-10-22"])
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.posted[0]["amount"], 200)
        self.assertEqual(self.posted[0]["payroll_date"], "2026-11-21")
        self.assertEqual(self.posted[0]["is_recurring"], 0)
        self.assertEqual(result["already_compensated_prior_period"], {})

    def test_monthly_contract_never_duplicates_payment_in_same_shamsi_month(self):
        result = self._monthly_calc("2026-10-23", "2026-11-21", ["2026-11-05"])
        self.assertEqual(self.posted, [])
        self.assertEqual(result["skipped_existing"], 1)

    def test_cancelled_or_disabled_inputs_do_not_block_monthly_replacement(self):
        # The isolated SQL stub returns only rows selected by the production
        # query. Assert that cancelled (docstatus 2) and disabled rows cannot
        # enter that result, then verify an otherwise eligible month posts.
        result = self._monthly_calc("2026-10-23", "2026-11-21")
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(result["posted"]["INS-1"][0]["amount"], 200)
        self.assertTrue(self.paid_sql_queries)
        for query in self.paid_sql_queries:
            self.assertIn("disabled=0", query)
            self.assertIn("docstatus<2", query)

    def test_monthly_contract_refuses_gregorian_and_partial_month_windows(self):
        with self.assertRaisesRegex(_ValidationError, "full Solar Hijri month"):
            self._monthly_calc("2026-10-01", "2026-10-31")
        self.assertEqual(self.posted, [])

    def test_monthly_contract_refuses_unapproved_partial_assignment_proration(self):
        self.assignments[0].effective_start = "2026-10-25"
        with self.assertRaisesRegex(_ValidationError, "partial-month terms"):
            self._monthly_calc("2026-10-23", "2026-11-21")
        self.assertEqual(self.posted, [])

    def test_monthly_contract_must_cover_full_month_after_revision(self):
        self.contract_doc.effective_end = "2026-11-10"
        with self.assertRaisesRegex(_ValidationError, "partial-month terms"):
            self._monthly_calc("2026-10-23", "2026-11-21")
        self.assertEqual(self.posted, [])

    def test_legacy_contract_still_pays_assignment_only_once(self):
        self.contract_lists.append(self.contract_lists[0][:])
        self.paid = {(ASSIGNMENT, "A-1"): ["2026-08-31"]}
        result = self._calc()
        self.assertEqual(result["already_compensated_prior_period"], {"A-1": ["2026-08-31"]})
        self.assertFalse(any(row["ref_doctype"] == ASSIGNMENT for row in self.posted))

    def test_unknown_earning_basis_is_refused(self):
        self.contract_doc.earning_basis = "Every day"
        self.contract_lists.append(self.contract_lists[0][:])
        with self.assertRaisesRegex(_ValidationError, "Earning basis"):
            self._calc()
        self.assertEqual(self.posted, [])
