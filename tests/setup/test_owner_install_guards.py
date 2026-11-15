"""Exercise release and clean-site fail-closed guards without importing Frappe."""
import ast
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
INSTALLER = APP_ROOT / "toefl_house" / "setup_presets" / "installer.py"


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


def isolated_guard(name, frappe, **dependencies):
    """Compile the real individual function without executing site imports."""
    source = INSTALLER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    body = [node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(body) == 1
    body[0].decorator_list = []
    code = compile(ast.Module(body=body, type_ignores=[]), str(INSTALLER), "exec")
    original_guard = next(
        n.value for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_NO_LIVE_RECORDS"
                for target in n.targets))
    context = {"frappe": frappe, "_NO_LIVE_RECORDS": ast.literal_eval(original_guard),
               **dependencies}
    exec(code, context)
    return context[name]


class FakeDatabase:
    def __init__(self, counts=None, backup_enabled=0, companies=None,
                 receivable="Receivable - TH", fee_group=True,
                 currency="AFN", receivable_company="TH", account_type="Receivable",
                 account_currency="AFN", is_group=0, disabled=0,
                 income="Income - TH", income_company="TH", income_root="Income",
                 cost_center="Main - TH", center_company="TH", center_is_group=0,
                 center_disabled=0):
        self.counts = counts or {}
        self.backup_enabled = backup_enabled
        self.companies = companies if companies is not None else [types.SimpleNamespace(name="TH")]
        self.receivable = receivable
        self.income = income
        self.cost_center = cost_center
        self.fee_group = fee_group
        self.currency = currency
        self.account = types.SimpleNamespace(
            company=receivable_company, root_type="Asset", account_type=account_type,
            account_currency=account_currency, is_group=is_group, disabled=disabled)
        self.income_ledger = types.SimpleNamespace(
            company=income_company, root_type=income_root, account_type="",
            account_currency="AFN", is_group=0, disabled=0)
        self.center = types.SimpleNamespace(
            company=center_company, is_group=center_is_group, disabled=center_disabled)
        self.locks = []

    def count(self, doctype):
        return self.counts.get(doctype, 0)

    def get_single_value(self, doctype, field):
        assert (doctype, field) == ("TH Backup Control", "enabled")
        return self.backup_enabled

    def exists(self, doctype, name):
        return bool(self.fee_group) if (doctype, name) == ("Item Group", "Fee Component") else False

    def get_all(self, doctype, fields=None, limit_page_length=None):
        assert doctype == "Company" and limit_page_length == 2
        return self.companies

    def get_value(self, doctype, name, fields, *, as_dict=False, for_update=False):
        if (doctype, name, fields) == ("Item Group", "Fee Component", "is_group"):
            return self.fee_group
        if for_update:
            self.locks.append((doctype, name))
        if doctype == "Company" and as_dict:
            return types.SimpleNamespace(
                default_currency=self.currency, default_receivable_account=self.receivable,
                default_income_account=self.income, cost_center=self.cost_center)
        if (doctype, name) == ("Account", self.receivable) and as_dict:
            return self.account
        if (doctype, name) == ("Account", self.income) and as_dict:
            return self.income_ledger
        if (doctype, name) == ("Cost Center", self.cost_center) and as_dict:
            return self.center
        raise AssertionError(f"Unexpected database lookup: {doctype}, {name}, {fields}")


class InstallerGateTests(unittest.TestCase):
    def frappe(self, qualified=False, enabled=False, db=None):
        return types.SimpleNamespace(
            conf={"toefl_house_customer_release_approved": qualified,
                  "toefl_house_owner_catalog_install_enabled": enabled},
            PermissionError=Denied, ValidationError=Invalid,
            db=db or FakeDatabase())

    def test_no_flags_refused(self):
        with self.assertRaises(Denied):
            isolated_guard("_qualified_site", self.frappe())()

    def test_only_one_flag_refused(self):
        for args in ({"qualified": True}, {"enabled": True}):
            with self.subTest(args=args), self.assertRaises(Denied):
                isolated_guard("_qualified_site", self.frappe(**args))()

    def test_existing_live_record_refused(self):
        for kind in ("Student", "Fees", "Payment Entry", "Salary Slip",
                     "Student Group", "Course Schedule", "Student Attendance",
                     "TH Assessment Book", "TH Academic Result",
                     "TH Tuition Refund Request", "Payroll Entry"):
            with self.subTest(kind=kind), self.assertRaisesRegex(Invalid, "preserve"):
                guard = isolated_guard("_qualified_site", self.frappe(
                    True, True, FakeDatabase(counts={kind: 1})))
                guard()

    def test_backup_on_refused(self):
        with self.assertRaisesRegex(Invalid, "Backup Control"):
            isolated_guard("_qualified_site", self.frappe(
                True, True, FakeDatabase(backup_enabled=1)))()

    def test_clean_verified_site_passes_guard(self):
        isolated_guard("_qualified_site", self.frappe(True, True))()

    def test_internal_approval_is_site_bound_requires_production_and_keeps_backup(self):
        production_site = "toeflhouse.localhost"
        cases = (
            (production_site, True, 1, {}, None),
            (production_site, True, 0, {}, Invalid),
            (production_site, False, 1, {}, Denied),
            ("another.localhost", True, 1, {}, Denied),
            (production_site, True, 1, {"Student": 1}, Invalid),
            (True, True, 1, {}, Denied),
        )
        for marker, production, backup, counts, failure in cases:
            with self.subTest(marker=marker, production=production, backup=backup, counts=counts):
                frappe = self.frappe(db=FakeDatabase(counts=counts, backup_enabled=backup))
                frappe.conf["toefl_house_internal_catalog_site"] = marker
                frappe.local = types.SimpleNamespace(site=production_site)
                security = types.SimpleNamespace(is_production=lambda: production)
                guard = isolated_guard("_qualified_site", frappe)
                with patch.dict(sys.modules, {"toefl_house.security": security}):
                    if failure:
                        with self.assertRaises(failure):
                            guard()
                    else:
                        guard()

    def test_native_accounting_preconditions(self):
        for database in (FakeDatabase(fee_group=False),
                         FakeDatabase(companies=[]),
                         FakeDatabase(companies=[types.SimpleNamespace(name="A"),
                                                 types.SimpleNamespace(name="B")]),
                         FakeDatabase(receivable=""),
                         FakeDatabase(currency="USD"),
                         FakeDatabase(receivable_company="Other Company"),
                         FakeDatabase(account_type="Payable"),
                         FakeDatabase(account_currency="USD"),
                         FakeDatabase(is_group=1),
                         FakeDatabase(disabled=1),
                         FakeDatabase(income=""),
                         FakeDatabase(income_company="Other Company"),
                         FakeDatabase(income_root="Expense"),
                         FakeDatabase(cost_center=""),
                         FakeDatabase(center_company="Other Company"),
                         FakeDatabase(center_is_group=1),
                         FakeDatabase(center_disabled=1)):
            with self.subTest(db=database), self.assertRaises(Invalid):
                isolated_guard("_finance_preconditions",
                               self.frappe(True, True, database))()
        db = FakeDatabase()
        guard = isolated_guard("_finance_preconditions", self.frappe(db=db))
        self.assertEqual(guard(), {"company": "TH", "receivable_account": "Receivable - TH",
                                  "income_account": "Income - TH", "cost_center": "Main - TH",
                                  "currency": "AFN"})
        self.assertEqual(db.locks, [])
        guard(lock=True)
        self.assertEqual(db.locks, [("Company", "TH"), ("Account", "Receivable - TH"),
                                    ("Account", "Income - TH"), ("Cost Center", "Main - TH")])

    def test_owner_confirmation_binds_company_and_finance_defaults(self):
        plan = {"preset_id": "A", "actions": [{"operation": "set_level_fee_component"}],
                "preview": {"counts": {"review": 0}}}
        digest = isolated_guard("preview_digest", self.frappe(), digest=lambda data: data)
        original = {"company": "TH", "receivable_account": "Receivable - TH",
                    "income_account": "Income - TH", "cost_center": "Main - TH", "currency": "AFN"}
        for change in ({"company": "Other Company"}, {"receivable_account": "New receivable - TH"},
                       {"income_account": "New income - TH"}, {"cost_center": "New center - TH"}):
            with self.subTest(change=change):
                self.assertNotEqual(digest(plan, original), digest(plan, {**original, **change}))

    def test_stale_ledger_confirmation_refuses_before_any_catalog_writes(self):
        db = FakeDatabase(receivable="Replacement receivable - TH")
        frappe = self.frappe(db=db)
        snapshot = {"unchanged": True}
        plan = {"preset_id": "A", "actions": [{"operation": "set_level_fee_component"}],
                "preview": {"counts": {"review": 0}}}
        digest = isolated_guard("preview_digest", frappe, digest=lambda data: json.dumps(data, sort_keys=True))
        old_signature = digest(plan, {
            "company": "TH", "receivable_account": "Receivable - TH",
            "income_account": "Income - TH", "cost_center": "Main - TH", "currency": "AFN"})
        calls = []
        lock_doc_type = db.get_value

        def get_value(doctype, name, fields, **kwargs):
            if doctype == "DocType":
                calls.append((doctype, name, kwargs.get("for_update")))
                return name
            return lock_doc_type(doctype, name, fields, **kwargs)

        with patch.object(db, "get_value", side_effect=get_value):
            initialize = isolated_guard(
                "initialize_owner_catalog", frappe, _owner=lambda: None,
                _qualified_site=lambda: None, _snapshot=lambda: snapshot,
                prepare_catalog_plan=lambda _: plan, preview_digest=digest,
                _finance_preconditions=isolated_guard("_finance_preconditions", frappe),
                _ALLOWED={"set_level_fee_component": lambda **_: self.fail("stale draft was written")})
            with self.assertRaisesRegex(Invalid, "refresh the preview"):
                initialize(old_signature, "APPLY_TO_NEW_COURSE_SITE")
        self.assertEqual(calls, [("DocType", "TH Academic Program", True)])
        self.assertIn(("Account", "Replacement receivable - TH"), db.locks)

    def test_first_run_serializes_and_rechecks_after_native_lock(self):
        source = INSTALLER.read_text(encoding="utf-8")
        begin = source.index("def initialize_owner_catalog(")
        command = source[begin:]
        lock = command.index('frappe.db.get_value("DocType", "TH Academic Program", "name", for_update=True)')
        post_lock_guard = command.index("_qualified_site()", lock)
        snapshot = command.index("snapshot = _snapshot()", post_lock_guard)
        planning = command.index("plan = prepare_catalog_plan(snapshot)", snapshot)
        self.assertLess(lock, post_lock_guard)
        self.assertLess(post_lock_guard, snapshot)
        self.assertLess(snapshot, planning)
        self.assertLess(planning, command.index("for action in plan[\"actions\"]"))

    def test_post_only_and_no_manual_commits(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('@frappe.whitelist(methods=["POST"])', source)
        self.assertIn('def initialize_owner_catalog(expected_plan_hash, confirmation):', source)
        self.assertIn('"APPLY_TO_NEW_COURSE_SITE"', source)
        self.assertIn("_owner()", source)
        self.assertNotIn("frappe.db.commit(", source)
        self.assertNotIn("ignore_permissions=True", source)
        self.assertNotIn("frappe.db.sql(", source)


if __name__ == "__main__":
    unittest.main()
