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

GUARDS = {
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
    "toefl_house.teaching": ROOT / "apps/toefl_house/toefl_house/teaching/__init__.py",
}


def doc_events():
    tree = ast.parse(HOOKS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "doc_events" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("doc_events assignment not found in hooks.py")


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
                            "TH Configuration Operation", "TH Configuration Audit Event"}
        self.assertEqual(extra, allowed_extras,
                         "doc_events changed; update this guard deliberately — the "
                         "only sanctioned extras are the governance configuration "
                         "integrity hooks (docs/product/CONFIGURATION-PLANE.md)")
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


if __name__ == "__main__":
    unittest.main()
