"""Exercise release and clean-site fail-closed guards without importing Frappe."""
import ast
import types
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
INSTALLER = APP_ROOT / "toefl_house" / "setup_presets" / "installer.py"


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


def isolated_guard(name, frappe):
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
    context = {"frappe": frappe, "_NO_LIVE_RECORDS": ast.literal_eval(original_guard)}
    exec(code, context)
    return context[name]


class FakeDatabase:
    def __init__(self, counts=None, backup_enabled=0, companies=None,
                 receivable="Receivable - TH", fee_group=True):
        self.counts = counts or {}
        self.backup_enabled = backup_enabled
        self.companies = companies if companies is not None else [types.SimpleNamespace(name="TH")]
        self.receivable = receivable
        self.fee_group = fee_group

    def count(self, doctype):
        return self.counts.get(doctype, 0)

    def get_single_value(self, doctype, field):
        assert (doctype, field) == ("TH Backup Control", "enabled")
        return self.backup_enabled

    def exists(self, doctype, name):
        return bool(self.fee_group) if (doctype, name) == ("Item Group", "Fee Component") else False

    def get_all(self, doctype, fields=None, limit=None):
        assert doctype == "Company"
        return self.companies

    def get_value(self, doctype, name, field):
        return self.receivable if (doctype, field) == ("Company", "default_receivable_account") else None


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

    def test_native_accounting_preconditions(self):
        for database in (FakeDatabase(fee_group=False),
                         FakeDatabase(companies=[]),
                         FakeDatabase(companies=[types.SimpleNamespace(name="A"),
                                                 types.SimpleNamespace(name="B")]),
                         FakeDatabase(receivable="")):
            with self.subTest(db=database), self.assertRaises(Invalid):
                isolated_guard("_finance_preconditions",
                               self.frappe(True, True, database))()
        isolated_guard("_finance_preconditions", self.frappe(True, True))()

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
