"""Course Owner dropdowns must not grant native Admin or expose customer data."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SRC = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
       / "toefl_house" / "setup_presets" / "owner_policy_forms.py")


def command(fake, owner=lambda: None):
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef)
               and n.name == "owner_form_options"]
    assert len(targets) == 1
    targets[0].decorator_list = []
    ns = {"frappe": fake, "_owner": owner}
    exec(compile(ast.Module(body=targets, type_ignores=[]),
                 str(SRC), "exec"), ns)
    return ns["owner_form_options"]


class LimitedOwnerChoiceTests(unittest.TestCase):
    def test_only_six_allowlisted_nonpersonal_master_types_are_read(self):
        queries = []
        names = {
            "Grading Scale": ["GE-Scale-V1"],
            "TH Academic Program": ["GEN-ENG"],
            "TH Program Level": ["STARTER"],
            "Academic Year": ["2026-27"],
            "Fee Category": ["Semester Tuition Fee"],
            "Company": ["The TOEFL House"],
        }
        def get_all(doctype, *, filters, fields, order_by, limit_page_length):
            queries.append((doctype, filters, fields, order_by, limit_page_length))
            return [{"name": name} for name in names[doctype]]
        frappe = SimpleNamespace(
            db=SimpleNamespace(get_all=get_all), ValidationError=ValueError)
        choices = command(frappe)()
        self.assertEqual(set(choices), {
            "grading_scale", "program", "level", "academic_year",
            "fee_category", "company"})
        self.assertEqual(choices["grading_scale"], ["GE-Scale-V1"])
        self.assertEqual(set(row[0] for row in queries), set(names))
        self.assertEqual(queries[0][1], {"docstatus": 1})
        self.assertTrue(all(row[-1] == 101 and row[2] == ["name"]
                            for row in queries))
        self.assertFalse({"Student", "User", "Payment Entry"} &
                         {row[0] for row in queries})

    def test_owner_permission_is_checked_before_any_select(self):
        def deny():
            raise PermissionError("Course Owner only")
        def no_query(*args, **kwargs):
            raise AssertionError("Must not read data without Owner")
        frappe = SimpleNamespace(
            db=SimpleNamespace(get_all=no_query), ValidationError=ValueError)
        with self.assertRaises(PermissionError):
            command(frappe, owner=deny)()

    def test_unbounded_and_malformed_choices_are_rejected(self):
        for records in (
            [{"name": "A"}] * 101,
            [{"name": "Injected\nOption"}],
            [{"name": "X" * 141}],
        ):
            with self.subTest(size=len(records)):
                frappe = SimpleNamespace(
                    db=SimpleNamespace(get_all=lambda *args, **kwargs: records),
                    ValidationError=ValueError)
                with self.assertRaises(ValueError):
                    command(frappe)()

    def test_ui_loads_owner_choices_without_native_permission_widening(self):
        js = (SRC.parents[2] / "toefl_house" / "public" / "js" /
              "th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn("owner_policy_forms.owner_form_options", js)
        self.assertIn('type: "GET"', js)
        self.assertIn('__owner_choice:grading_scale__', js)
        self.assertIn('__owner_choice:fee_category__', js)
        self.assertIn('options: ["", ...action._owner_choices[kind]].join(', js)
        self.assertIn('const requestKey = newRequestKey()', js)
        self.assertIn('const args = { request_key: requestKey };', js)


if __name__ == "__main__":
    unittest.main()
