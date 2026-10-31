"""Installment-plan arithmetic and owner-terms judgement (no site needed).

The plan is the one place in the finance slice where an amount is *derived*
(a configured price split across native Fees documents), so the arithmetic is
pinned here: exact cents, remainder on the last installment, no zero
installment, and a schedule that cannot exist without the Course Owner's
enabled policy terms.
"""
import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "apps/toefl_house/toefl_house"


class _ValidationError(Exception):
    pass


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def load_installments():
    """Load the real module against the minimum honest dependency surface."""
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = _ValidationError
    frappe.whitelist = lambda **kwargs: (lambda func: func)
    frappe.db = types.SimpleNamespace()
    frappe.utils = types.SimpleNamespace()
    sys.modules["frappe"] = frappe

    policy = types.ModuleType("toefl_house.policy")
    policy.digest = lambda value: "digest"
    policy.validate_finance_dates = lambda posting, due: (
        str(posting), str(due or posting))
    sys.modules["toefl_house.policy"] = policy

    api = types.ModuleType("toefl_house.api")
    api._execute = lambda kind, key, payload, work: work("officer@example.com")
    sys.modules["toefl_house.api"] = api

    finance = types.ModuleType("toefl_house.finance")
    finance.__path__ = [str(APP / "finance")]
    finance.COMPANY = "TOEFL House"
    finance.FEES = "Fees"
    finance.FEE_STRUCTURE = "Fee Structure"
    finance.PROGRAM_ENROLLMENT = "Program Enrollment"
    finance._name = lambda value, label: value
    finance.resolved_billable_components = lambda pe, fs: ([], [], 0.0)
    sys.modules["toefl_house.finance"] = finance

    policies = types.ModuleType("toefl_house.finance.policies")
    policies.governing_billing_terms = lambda on_date=None: {}
    policies.check_posting_bounds = lambda *args, **kwargs: None
    def validate_cadence(cadence, grace):
        if cadence not in ("Days", "Solar Hijri Month"):
            raise ValueError("Unknown installment cadence")
        if isinstance(grace, bool) or not isinstance(grace, int) or not 0 <= grace <= 15:
            raise ValueError("Invalid payment grace days")
        if cadence == "Days" and grace:
            raise ValueError("Payment grace days require Solar Hijri Month cadence")
        return cadence, grace
    policies.validate_shamsi_cadence = validate_cadence
    def validate_due_day(cadence, due_day):
        # Mirrors policies.validate_due_day: a due day is contractual and is
        # refused rather than clamped when no Solar Hijri month can honour it.
        if isinstance(due_day, bool) or not isinstance(due_day, int):
            raise ValueError("Installment due day must be a whole number")
        if cadence != "Solar Hijri Month":
            if due_day:
                raise ValueError(
                    "An installment due day requires Solar Hijri Month cadence")
            return 0
        if due_day == 0:
            return 1
        if not 1 <= due_day <= 29:
            raise ValueError("Installment due day must be between 1 and 29")
        return due_day
    policies.validate_due_day = validate_due_day
    sys.modules["toefl_house.finance.policies"] = policies

    package = types.ModuleType("toefl_house")
    package.__path__ = [str(APP)]
    sys.modules["toefl_house"] = package
    return _load("toefl_house.finance.installments",
                 APP / "finance" / "installments.py")


class SplitArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.module = load_installments()

    def test_split_sums_exactly_to_the_configured_amount(self):
        for total, parts in ((25000, 2), (25000, 3), (100, 3), (999.99, 7),
                             (0.03, 3), (12345.67, 12)):
            with self.subTest(total=total, parts=parts):
                amounts = self.module.split_amounts(total, parts)
                self.assertEqual(len(amounts), parts)
                self.assertEqual(round(sum(amounts), 2), round(float(total), 2))
                self.assertTrue(all(amount > 0 for amount in amounts))

    def test_remainder_lands_on_the_last_installment(self):
        self.assertEqual(self.module.split_amounts(100, 3), [33.33, 33.33, 33.34])
        self.assertEqual(self.module.split_amounts(0.05, 2), [0.02, 0.03])

    def test_a_schedule_that_would_zero_an_installment_is_refused(self):
        # 2 cents cannot be three positive installments; 1 cent cannot be two.
        for total, parts in ((0.02, 3), (0.01, 2)):
            with self.subTest(total=total, parts=parts):
                with self.assertRaises(ValueError):
                    self.module.split_amounts(total, parts)

    def test_exact_currency_rejects_partial_cent_or_nonfinite_amounts(self):
        for bad in (0.005, "12.345", "NaN", "Infinity", "-Infinity",
                    None, 0, -10):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.module.split_amounts(bad, 2)
        self.assertEqual(self.module.split_amounts("0.30", 2), [0.15, 0.15])
        self.assertEqual(self.module.split_amounts("0.05", 2), [0.02, 0.03])

    def test_bad_count_is_refused(self):
        for parts in (0, -1, True, "3", 2.5):
            with self.subTest(parts=parts):
                with self.assertRaises(ValueError):
                    self.module.split_amounts(100, parts)


class ApprovedShareSplitTests(unittest.TestCase):
    """Owner-approved unequal contractual installments (e.g. 60/40).

    The shares are percentages of the net tuition and must total exactly
    100%; the native documents must still add up to the configured price to
    the cent, and a share that would carry no money is refused rather than
    dropped.
    """

    def setUp(self):
        self.module = load_installments()

    def test_approved_ratios_split_exactly(self):
        cases = (
            (25000, [50, 50], [12500.0, 12500.0]),
            (25000, [60, 40], [15000.0, 10000.0]),
            (25000, ["60.0000", "40.0000"], [15000.0, 10000.0]),
            (20000, [70, 20, 10], [14000.0, 4000.0, 2000.0]),
        )
        for total, shares, expected in cases:
            with self.subTest(total=total, shares=shares):
                amounts = self.module.split_amounts_by_shares(total, shares)
                self.assertEqual(amounts, expected)
                self.assertEqual(round(sum(amounts), 2), round(float(total), 2))

    def test_remainder_keeps_the_schedule_exact_to_the_cent(self):
        for total, shares in ((100, [60, 40]), (0.07, [50, 50]),
                              (999.99, [33, 33, 34]), (12345.67, [25, 25, 50])):
            with self.subTest(total=total, shares=shares):
                amounts = self.module.split_amounts_by_shares(total, shares)
                self.assertEqual(len(amounts), len(shares))
                self.assertEqual(round(sum(amounts), 2), round(float(total), 2))
                self.assertTrue(all(amount > 0 for amount in amounts))

    def test_shares_must_total_exactly_one_hundred_percent(self):
        for shares in ([60, 39], [60, 41], [50, 50, 1], [99.9999, 0.0001][::-1][:1]):
            with self.subTest(shares=shares):
                with self.assertRaises(ValueError):
                    self.module.split_amounts_by_shares(1000, shares)

    def test_unapproved_share_shapes_are_refused(self):
        for shares in ([], [0, 100], [-10, 110], [True, 99],
                       [33.33333, 66.66667], ["sixty", 40], None, 60,
                       [100, 0]):
            with self.subTest(shares=shares):
                with self.assertRaises((ValueError, TypeError)):
                    self.module.split_amounts_by_shares(1000, shares)

    def test_a_share_too_small_to_carry_money_is_refused(self):
        # 1% of 0.50 is half a cent: it cannot become a receivable.
        with self.assertRaisesRegex(ValueError, "positive amount"):
            self.module.split_amounts_by_shares(0.02, [50, 25, 25])

    def test_component_plan_with_shares_totals_the_configured_price(self):
        rows = [{"fees_category": "SYN-Tuition", "amount": 25000.0,
                 "discount": None},
                {"fees_category": "SYN-Books", "amount": 5000.0,
                 "discount": None}]
        plan = self.module.build_installment_components(rows, 2, [60, 40])
        self.assertEqual([self.module._plan_total(part) for part in plan],
                         [18000.0, 12000.0])
        self.assertEqual(
            round(sum(self.module._plan_total(part) for part in plan), 2),
            30000.0)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.module = load_installments()

    def test_interval_spacing_is_the_owners_number_of_days(self):
        self.assertEqual(
            self.module.schedule_due_dates("2026-10-24", 3, 30),
            ["2026-10-24", "2026-11-23", "2026-12-23"])

    def test_negative_interval_refused(self):
        with self.assertRaises(ValueError):
            self.module.schedule_due_dates("2026-10-24", 2, -1)

    def test_real_solar_months_and_grace_from_owner_policy(self):
        self.assertEqual(self.module.schedule_due_dates(
            "2026-09-23", 3, 0, "Solar Hijri Month", 0),
            ["2026-09-23", "2026-10-23", "2026-11-22"])
        self.assertEqual(self.module.schedule_due_dates(
            "2026-09-26", 2, 0, "Solar Hijri Month", 3),
            ["2026-09-26", "2026-10-26"])

    def test_owner_selected_solar_due_day_is_honoured(self):
        # The Owner-approved alternative to the month's first day: the 25th
        # of each starting Afghan month, with the configured grace on top.
        # Aqrab 1405 starts 2026-10-23, so its 25th is 2026-11-16 and Qaws
        # 1405 starts 2026-11-22, so its 25th is 2026-12-16.
        self.assertEqual(self.module.schedule_due_dates(
            "2026-11-16", 2, 0, "Solar Hijri Month", 0, 25),
            ["2026-11-16", "2026-12-16"])
        # The configured grace applies on top of the contracted day.
        self.assertEqual(self.module.schedule_due_dates(
            "2026-11-20", 2, 0, "Solar Hijri Month", 4, 25),
            ["2026-11-20", "2026-12-20"])
        # A first due date that is not the contracted day is still refused.
        with self.assertRaisesRegex(ValueError, "day 25"):
            self.module.schedule_due_dates(
                "2026-10-28", 2, 0, "Solar Hijri Month", 3, 25)

    def test_due_day_never_exists_beyond_the_shortest_month(self):
        # Hoot has 29 days in a common year, so 30 could not be honoured in
        # every month of a plan. It is refused, never silently clamped.
        for day in (0, 30, 31, -1, True, "25"):
            with self.subTest(day=day):
                with self.assertRaises((ValueError, TypeError)):
                    self.module.schedule_due_dates(
                        "2026-10-25", 2, 0, "Solar Hijri Month", 0, day)

    def test_due_day_requires_the_solar_cadence(self):
        with self.assertRaisesRegex(ValueError, "Solar Hijri Month"):
            self.module.schedule_due_dates("2026-10-24", 2, 30, "Days", 0, 25)

    def test_unaligned_first_solar_due_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "first Solar Hijri"):
            self.module.schedule_due_dates(
                "2026-09-25", 2, 0, "Solar Hijri Month", 3)
        with self.assertRaisesRegex(ValueError, "Unknown installment cadence"):
            self.module.schedule_due_dates(
                "2026-09-23", 2, 0, "Lunar", 0)


class PlanTermsTests(unittest.TestCase):
    """Only the owner's enabled policy can authorize a split."""

    def setUp(self):
        self.module = load_installments()
        self.enabled = {
            "installments_allowed": 1, "max_installments": 3,
            "installment_interval_days": 30,
        }

    def test_no_policy_refuses(self):
        with self.assertRaisesRegex(ValueError, "billing policy"):
            self.module.plan_terms({}, 2, "2026-10-24", "2026-10-24")

    def test_installments_disabled_refuses(self):
        terms = dict(self.enabled, installments_allowed=0)
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.module.plan_terms(terms, 2, "2026-10-24", "2026-10-24")

    def test_one_installment_is_not_a_plan(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.module.plan_terms(self.enabled, 1, "2026-10-24", "2026-10-24")

    def test_count_above_the_owner_bound_refused(self):
        with self.assertRaisesRegex(ValueError, "at most 3"):
            self.module.plan_terms(self.enabled, 4, "2026-10-24", "2026-10-24")

    def test_missing_interval_refuses(self):
        terms = dict(self.enabled, installment_interval_days=0)
        with self.assertRaisesRegex(ValueError, "interval"):
            self.module.plan_terms(terms, 2, "2026-10-24", "2026-10-24")

    def test_first_due_before_posting_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot fall due before"):
            self.module.plan_terms(self.enabled, 2, "2026-10-24", "2026-10-01")

    def test_enabled_terms_produce_the_schedule(self):
        count, interval, dates = self.module.plan_terms(
            self.enabled, 3, "2026-10-24", "2026-10-24")
        self.assertEqual((count, interval), (3, 30))
        self.assertEqual(dates[-1], "2026-12-23")

    def test_late_join_in_current_solar_month_keeps_real_posting_date(self):
        terms = dict(self.enabled, installment_interval_days=0,
                     installment_cadence="Solar Hijri Month",
                     payment_grace_days=0)
        count, interval, dates = self.module.plan_terms(
            terms, 2, "2026-10-26", "2026-10-23")
        self.assertEqual((count, interval), (2, 0))
        self.assertEqual(dates, ["2026-10-23", "2026-11-22"])

    def test_previous_solar_month_backbilling_requires_separate_approval(self):
        terms = dict(self.enabled, installment_interval_days=0,
                     installment_cadence="Solar Hijri Month",
                     payment_grace_days=0)
        with self.assertRaisesRegex(ValueError, "current Solar Hijri"):
            self.module.plan_terms(terms, 2, "2026-11-23", "2026-10-23")
        with self.assertRaisesRegex(ValueError, "first Solar Hijri"):
            self.module.plan_terms(terms, 2, "2026-10-26", "2026-10-24")

    def test_policy_contracted_due_day_drives_the_schedule(self):
        # The Owner's 25th-of-the-month choice is a policy value, so a plan
        # scheduled from those terms must bill on the 25th of each month.
        terms = dict(self.enabled, installment_interval_days=0,
                     installment_cadence="Solar Hijri Month",
                     payment_grace_days=0, installment_due_day=25)
        count, interval, dates = self.module.plan_terms(
            terms, 2, "2026-11-16", "2026-11-16")
        self.assertEqual((count, interval), (2, 0))
        self.assertEqual(dates, ["2026-11-16", "2026-12-16"])
        # The month's first day is no longer the contracted day here.
        with self.assertRaisesRegex(ValueError, "day 25"):
            self.module.plan_terms(terms, 2, "2026-11-16", "2026-11-01")

    def test_unspecified_due_day_keeps_the_first_of_the_month(self):
        terms = dict(self.enabled, installment_interval_days=0,
                     installment_cadence="Solar Hijri Month",
                     payment_grace_days=0)
        # Aqrab 1405 begins 2026-10-23; Qaws 1405 begins 2026-11-22.
        _count, _interval, dates = self.module.plan_terms(
            terms, 2, "2026-10-26", "2026-10-23")
        self.assertEqual(dates, ["2026-10-23", "2026-11-22"])

    def test_fixed_day_mode_still_disallows_overdue_first_due(self):
        with self.assertRaisesRegex(ValueError, "cannot fall due"):
            self.module.plan_terms(self.enabled, 2, "2026-10-26", "2026-10-23")

    def test_solar_month_policy_does_not_need_fictitious_thirty_days(self):
        terms = dict(self.enabled, installment_interval_days=0,
                     installment_cadence="Solar Hijri Month",
                     payment_grace_days=3)
        count, interval, dates = self.module.plan_terms(
            terms, 2, "2026-09-25", "2026-09-26")
        self.assertEqual((count, interval), (2, 0))
        self.assertEqual(dates, ["2026-09-26", "2026-10-26"])


class ShareInputTests(unittest.TestCase):
    """The desk form, a JSON string and an array must mean the same plan."""

    def setUp(self):
        self.module = load_installments()

    def test_absent_shares_keep_the_equal_split(self):
        for value in (None, "", "   ", []):
            with self.subTest(value=value):
                self.assertIsNone(self.module._shares(value, 2))

    def test_equivalent_forms_normalize_to_the_same_list(self):
        self.assertEqual(self.module._shares("60,40", 2), ["60", "40"])
        self.assertEqual(self.module._shares("60; 40", 2), ["60", " 40"])
        self.assertEqual(self.module._shares("[60, 40]", 2), [60, 40])
        self.assertEqual(self.module._shares([60, 40], 2), [60, 40])
        self.assertEqual(self.module._shares((60, 40), 2), [60, 40])

    def test_a_scalar_is_not_a_share_list(self):
        for value in (60, 40.0, True, {"shares": [60, 40]}):
            with self.subTest(value=value):
                with self.assertRaises(_ValidationError):
                    self.module._shares(value, 2)


class ComponentSplitTests(unittest.TestCase):
    def setUp(self):
        self.module = load_installments()

    def test_each_component_splits_within_the_installment_total(self):
        rows = [{"fees_category": "SYN-Tuition", "amount": 25000.0,
                 "discount": None},
                {"fees_category": "SYN-Books", "amount": 5000.0,
                 "discount": None}]
        plan = self.module.build_installment_components(rows, 3)
        self.assertEqual(len(plan), 3)
        self.assertEqual(round(sum(self.module._plan_total(item) for item in plan), 2),
                         30000.0)
        for installment in plan:
            self.assertEqual({row["fees_category"] for row in installment},
                             {"SYN-Tuition", "SYN-Books"})
            self.assertTrue(all(row["amount"] > 0 for row in installment))

    def test_duplicate_fee_category_rows_keep_their_individual_amounts(self):
        rows = [{"fees_category": "SYN-Tuition", "amount": "100.00"},
                {"fees_category": "SYN-Tuition", "amount": "33.33"}]
        plan = self.module.build_installment_components(rows, 2)
        self.assertEqual([[line["amount"] for line in part] for part in plan],
                         [[50.0, 16.66], [50.0, 16.67]])
        self.assertEqual(round(sum(self.module._plan_total(part) for part in plan), 2),
                         133.33)

    def test_a_discount_row_survives_the_split(self):
        rows = [{"fees_category": "SYN-Tuition", "amount": 17500.0,
                 "discount": 30.0}]
        plan = self.module.build_installment_components(rows, 2)
        self.assertEqual([row["discount"] for row in plan[0]], [30.0])
        self.assertEqual(round(sum(self.module._plan_total(item) for item in plan), 2),
                         17500.0)


class ReceiptWiringTests(unittest.TestCase):
    """The command is a receipted Finance Officer command, not a bare write."""

    @classmethod
    def setUpClass(cls):
        cls.security = (APP / "security.py").read_text(encoding="utf-8")
        cls.hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        cls.installments = (APP / "finance" / "installments.py").read_text(encoding="utf-8")

    def test_command_is_role_gated_and_receipted(self):
        self.assertIn('"issue_tuition_installment_plan": "Finance Officer"',
                      self.security)
        self.assertIn('_execute("issue_tuition_installment_plan", request_key',
                      self.installments)

    def test_both_billing_paths_lock_and_check_all_live_fees_for_enrollment(self):
        # Distinct Fee Structures must never bypass the *same enrollment's*
        # duplicate-tuition protection. This is a money-loss prevention
        # backstop and protects the path where one Officer issues a single
        # Fees while another tries the two-month installment command.
        for path, command in (
            (APP / "finance" / "__init__.py", "issue_tuition_fees"),
            (APP / "finance" / "installments.py", "issue_tuition_installment_plan"),
        ):
            with self.subTest(command=command):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                node = next(n for n in ast.walk(tree)
                            if isinstance(n, ast.FunctionDef) and n.name == command)
                code = ast.unparse(node)
                self.assertIn("for update", code)
                fees_exists = [
                    x for x in ast.walk(node)
                    if isinstance(x, ast.Call)
                    and ast.unparse(x.func) == "frappe.db.exists"
                    and x.args and ast.unparse(x.args[0]) == "FEES"
                    and len(x.args) >= 2 and isinstance(x.args[1], ast.Dict)
                ]
                self.assertEqual(len(fees_exists), 1, code)
                keys = [k.value for k in fees_exists[0].args[1].keys
                        if isinstance(k, ast.Constant)]
                self.assertEqual(set(keys), {"program_enrollment", "docstatus"})

    def test_fees_guard_still_gates_the_write(self):
        # The plan writes native Fees rows; the Fees containment guard is the
        # only reason that is legal, so it must stay wired on every seam.
        self.assertEqual(self.hooks.count("toefl_house.finance.guard_fees"), 3)

    def test_installment_fields_are_declared_read_only(self):
        import json
        rows = json.loads((APP / "fixtures/custom_field.json").read_text())
        fields = {row["fieldname"]: row for row in rows if row["dt"] == "Fees"}
        for name in ("th_installment_sequence", "th_installment_count"):
            self.assertIn(name, fields)
            self.assertEqual(fields[name]["read_only"], 1)


def tearDownModule():
    """Drop the stubs this module installed so later suites load fresh."""
    for name in ("frappe", "toefl_house", "toefl_house.policy", "toefl_house.api", "toefl_house.security", "toefl_house.finance", "toefl_house.finance.policies", "toefl_house.finance.cashier", "toefl_house.finance.taxes", "toefl_house.finance.refunds", "toefl_house.finance.installments",):
        sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
