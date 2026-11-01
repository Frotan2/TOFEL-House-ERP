"""Static guard: every command-only doctype pins its guard on all three
lifecycle seams.

Pinned frappe (988e54f3c4c2, frappe/model/document.py
run_before_save_methods): the ``validate`` doc_event fires only for
save/submit actions; cancel fires ``before_cancel`` and post-submit edits
fire ``before_update_after_submit`` WITHOUT validate. A validate-only
guard therefore has cancel and update-after-submit bypass routes (A13).
This test keeps hooks.py pinned on all three seams for every guarded
doctype. Pure AST; imports nothing from the app.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "apps/toefl_house/toefl_house/hooks.py"
SECURITY = ROOT / "apps/toefl_house/toefl_house/security.py"

GUARDS = {
    # Customer refunds settle credit notes only (2026-10-24 finance mission);
    # the same guard runs on create, cancel and post-submit edits.
    "Payment Entry": "toefl_house.finance.refunds.guard_payment_entry",
    "Journal Entry": "toefl_house.finance.student_journals.guard_student_journal",
    # Book stock integrity (Agent 2, inventory finalization): the same
    # guard judges create, cancel and post-submit edits; non-book stock
    # documents pass through the seam untouched.
    "Stock Entry": "toefl_house.finance.books.guard_stock_entry",
    "Stock Reconciliation": "toefl_house.finance.books.guard_stock_reconciliation",
    # The cashier day close is a control record: command-only on every seam.
    "TH Cashier Day": "toefl_house.finance.cashier.guard",
    # Visitor identity is a protected operational record, not a free-edit CRM lead.
    "TH Reception Inquiry": "toefl_house.reception_intake.protect_inquiry",
    "Program Enrollment": "toefl_house.enrollment.guard_program_enrollment",
    "Course Enrollment": "toefl_house.enrollment.guard_course_enrollment",
    "Sales Invoice": "toefl_house.finance.guard_sales_invoice",
    "Fees": "toefl_house.finance.guard_fees",
    "Student Group": "toefl_house.teaching.guard_student_group",
    "Course Schedule": "toefl_house.teaching.guard_course_schedule",
    "Student Attendance": "toefl_house.teaching.guard_student_attendance",
}
SEAMS = ("validate", "before_cancel", "before_update_after_submit")
MODULE_FILES = {
    "toefl_house.enrollment": ROOT / "apps/toefl_house/toefl_house/enrollment/__init__.py",
    "toefl_house.finance": ROOT / "apps/toefl_house/toefl_house/finance/__init__.py",
    "toefl_house.finance.cashier": ROOT / "apps/toefl_house/toefl_house/finance/cashier.py",
    "toefl_house.reception_intake": ROOT / "apps/toefl_house/toefl_house/reception_intake.py",
    "toefl_house.finance.refunds": ROOT / "apps/toefl_house/toefl_house/finance/refunds.py",
    "toefl_house.finance.student_journals": ROOT / "apps/toefl_house/toefl_house/finance/student_journals.py",
    "toefl_house.finance.books": ROOT / "apps/toefl_house/toefl_house/finance/books.py",
    "toefl_house.teaching": ROOT / "apps/toefl_house/toefl_house/teaching/__init__.py",
}


def doc_events():
    tree = ast.parse(HOOKS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "doc_events" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("doc_events assignment not found in hooks.py")


def _assignments():
    """Module-level literal dict/str assignments from security.py (AST only)."""
    tree = ast.parse(SECURITY.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
    return found


class ContainmentHookWiringTests(unittest.TestCase):
    def test_every_command_doctype_pins_all_three_seams(self):
        events = doc_events()
        for doctype, guard in GUARDS.items():
            for seam in SEAMS:
                self.assertEqual(events.get(doctype, {}).get(seam), guard,
                                 (doctype, seam, "must pin the command-only guard"))

    def test_no_unguarded_doctype_events(self):
        events = doc_events()
        extra = set(events) - set(GUARDS)
        allowed_extras = {"TH Academic Program", "TH Program Level", "TH Discount Rule", "TH Skill",
                            "TH Assessment Policy", "TH Returning Student Policy",
                            "TH Roster Change Policy",
                            "TH Attendance Correction Policy",
                            "TH Enrollment Exit Policy",
                            "TH Billing Policy",
                            "TH Catalog Linkage Policy",
                            "TH Adjustment Posting Policy",
                            "TH Alerting Policy",
                            "TH Guardian Lifecycle Policy",
                            "TH Backup Control",
                            # Exact audited and validation-only notification
                            # and portal model hooks; finance guards unchanged.
                            "TH Guardian Consent", "TH Notification Dispatch Rule",
                            "TH Portal Configuration", "TH Notification",
                            "TH Portal Announcement",
                            "TH Configuration Operation", "TH Configuration Audit Event",
                            # Mission 3 (2026-10-24): the three new teaching
                            # configuration masters carry the same
                            # command-only integrity hook as the other config
                            # masters above — validate-only, not a command
                            # guard, and registered in
                            # configuration.audit.KIND_AUTHORITY.
                            "TH Class Operations Policy", "TH Academic Calendar",
                            "TH Timetable Template",
                            # 2026-10-18: unconditional validate-only integrity hook (Office 365 link
                            # uniqueness, toefl_house/identity_links.py). Not a command guard.
                            "User"}
        self.assertEqual(extra, allowed_extras,
                         "doc_events changed; update this guard deliberately — the "
                         "only sanctioned extras are the governance configuration "
                         "integrity hooks (docs/CONFIGURATION-PLANE.md)")
        app_root = ROOT / "apps/toefl_house/toefl_house"
        for doctype in allowed_extras:
            for seam, target in events[doctype].items():
                module_path = target.rsplit(".", 1)[0].split("toefl_house.", 1)[1].replace(".", "/") + ".py"
                self.assertTrue((app_root / module_path).exists(), (doctype, seam, target))
                self.assertIn(target.rsplit(".", 1)[1],
                              (app_root / module_path).read_text(encoding="utf-8"),
                              (doctype, seam, "function must exist"))

    def test_guard_functions_exist_in_their_modules(self):
        for guard in sorted(set(GUARDS.values())):
            module, function = guard.rsplit(".", 1)
            tree = ast.parse(MODULE_FILES[module].read_text())
            defs = [n.name for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)]
            self.assertIn(function, defs, guard)

    def test_every_finance_command_declares_its_guarded_doctype(self):
        # guard_fees/guard_sales_invoice only accept a write inside the
        # matching finance command, so a finance command that creates one of
        # those doctypes must be registered here or its own writes are refused
        # on a real site (invisible to offline stubs).
        modules = _assignments()
        commands = modules["FINANCE_COMMANDS"]
        self.assertEqual(commands["issue_tuition_fees"], "Fees")
        self.assertEqual(commands["issue_tuition_installment_plan"], "Fees")
        self.assertEqual(commands["issue_placement_fee"], "Sales Invoice")
        self.assertEqual(commands["reconcile_cashier_day"], "TH Cashier Day")
        for command, doctype in commands.items():
            # Either a money doctype with a pinned guard or an owned control
            # record; nothing else may be written by a finance command.
            self.assertTrue(doctype in GUARDS or doctype in modules["DOCTYPES"],
                            (command, doctype))
            self.assertIn(command, modules["KIND_ROLES"],
                          (command, "must have a command role"))

    def test_finance_command_doctypes_are_either_guarded_or_control_records(self):
        commands = _assignments()["FINANCE_COMMANDS"]
        self.assertEqual(
            set(commands.values()) - set(GUARDS),
            set(),
            "every doctype a finance command writes must pin its guard in "
            "hooks.py on all three lifecycle seams",
        )
        self.assertEqual(commands["reconcile_cashier_day"], "TH Cashier Day")
        # The close is a control record: it must never post to the ledger or
        # restock anything, only record counted cash.
        source = MODULE_FILES["toefl_house.finance.cashier"].read_text(encoding="utf-8")
        for primitive in ("make_gl_entries", "Journal Entry", "journal_entry",
                          "get_payment_entry", "Stock Entry", "Sales Invoice"):
            self.assertNotIn(primitive, source, primitive)


if __name__ == "__main__":
    unittest.main()
