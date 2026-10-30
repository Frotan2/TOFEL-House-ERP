"""Fail-closed Owner fee-plan identity tests, running without a Frappe site.

The tests compile the actual audited production functions from source rather
than reimplementing their logic. No real Fee Structure or Fees is written.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = (Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
          / "toefl_house" / "academic" / "__init__.py")


def function_from_source(name, context):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(selected) == 1, name
    selected[0].decorator_list = []
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), context)
    return context[name]


class NativeFeeStructureIdentityTests(unittest.TestCase):
    def fee_reader(self, existing):
        db = SimpleNamespace(
            get_all=Mock(return_value=existing),
            get_value=Mock(return_value="Receivable - TH"))
        doc = SimpleNamespace(name="FS-EXISTING", company="TH")
        frappe = SimpleNamespace(
            db=db, get_doc=Mock(return_value=doc), ValidationError=ValueError)
        context = {
            "frappe": frappe,
            "FEE_STRUCTURE": "Fee Structure",
            "FEE_STRUCTURE_NAMING": "EDU-FS-.YYYY.-",
            "_resolve_company": lambda value: "TH",
        }
        return function_from_source("_managed_fee_structure", context), frappe

    def test_one_existing_draft_is_edited_in_place(self):
        resolve, frappe = self.fee_reader([{"name": "FS-EXISTING", "docstatus": 0}])
        self.assertEqual(resolve("N-STARTER", "1405").name, "FS-EXISTING")
        _, options = frappe.db.get_all.call_args
        self.assertEqual(options["filters"]["docstatus"], ("!=", 2))
        self.assertEqual(options["fields"], ["name", "docstatus"])
        frappe.get_doc.assert_called_once_with(
            "Fee Structure", "FS-EXISTING", for_update=True)

    def test_submitted_structure_never_spawns_a_parallel_draft(self):
        resolve, frappe = self.fee_reader([{"name": "FS-SUBMITTED", "docstatus": 1}])
        with self.assertRaisesRegex(ValueError, "submitted"):
            resolve("N-STARTER", "1405")
        frappe.get_doc.assert_not_called()

    def test_multiple_active_drafts_or_submitted_conflict(self):
        for statuses in ((0, 0), (0, 1), (1, 1)):
            with self.subTest(statuses=statuses):
                resolve, frappe = self.fee_reader([
                    {"name": "FS-1", "docstatus": statuses[0]},
                    {"name": "FS-2", "docstatus": statuses[1]},
                ])
                with self.assertRaisesRegex(ValueError, "More than one active"):
                    resolve("N-STARTER", "1405")
                frappe.get_doc.assert_not_called()


class ExistingFeeComponentsTests(unittest.TestCase):
    def owner_fee_command(self, components):
        structure = {"components": components}
        structure_doc = SimpleNamespace(
            get=structure.get, name="FS-EXISTING",
            save=Mock(), append=Mock())
        frappe = SimpleNamespace(
            db=SimpleNamespace(exists=lambda doctype, name: True),
            ValidationError=ValueError)
        audit = SimpleNamespace(
            execute=lambda _operation, _key, _payload, callback: callback("Course Owner"),
            latest_after_hash=lambda target: "")
        context = {
            "frappe": frappe,
            "rules": SimpleNamespace(
                validate_code=lambda value: value,
                validate_fee_amount=lambda value: value),
            "configuration_audit": audit,
            "_level_doc": lambda code, for_update=False: SimpleNamespace(
                status="Active", native_program="N-STARTER"),
            "_managed_fee_structure": lambda *args: structure_doc,
            "_fee_plan_result": lambda *args, **kwargs: {"fee_structure": "FS-EXISTING"},
            "digest": lambda value: "digest",
            "LEVEL": "TH Program Level",
            "YEAR": "Academic Year",
            "FEE_CATEGORY": "Fee Category",
        }
        return function_from_source("set_level_fee_component", context), structure_doc

    def test_duplicate_categories_refused_before_any_save(self):
        for components in (
            [{"fees_category": "Semester Tuition Fee", "amount": 1000},
             {"fees_category": "Semester Tuition Fee", "amount": 1000}],
            [{"fees_category": "Semester Tuition Fee", "amount": 1000},
             {"fees_category": None, "amount": 50}],
        ):
            with self.subTest(components=components):
                apply, structure = self.owner_fee_command(components)
                with self.assertRaisesRegex(ValueError, "missing or repeated"):
                    apply("key", "STARTER", "1405", "Semester Tuition Fee", 1000)
                structure.save.assert_not_called()
                structure.append.assert_not_called()

    def test_unchanged_valid_draft_does_not_add_a_second_component(self):
        apply, structure = self.owner_fee_command([
            {"fees_category": "Semester Tuition Fee", "amount": 1000}])
        result = apply("key", "STARTER", "1405", "Semester Tuition Fee", 1000)
        self.assertEqual(result["fee_structure"], "FS-EXISTING")
        structure.save.assert_not_called()
        structure.append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
