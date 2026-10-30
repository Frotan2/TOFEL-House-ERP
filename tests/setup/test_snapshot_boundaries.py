"""Run the actual snapshot functions against controlled native-like rows.

No site, database, external dependencies or real data are used. This pins
bounded reads, duplicate refusals and fail-closed financial interpretations.
"""
import ast
import types
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "toefl_house"
API = APP_ROOT / "toefl_house" / "setup_presets" / "api.py"


class Refused(Exception):
    pass


class Row(dict):
    __getattr__ = dict.__getitem__


class FakeDB:
    def __init__(self, datasets=None):
        self.datasets = datasets or {}
        self.calls = []

    def exists(self, doctype, name):
        return any(row.get("name") == name for row in self.datasets.get(doctype, []))

    def get_all(self, doctype, *, fields=None, filters=None,
                order_by=None, limit_page_length=None, **kwargs):
        self.calls.append((doctype, limit_page_length))
        if limit_page_length is None:
            raise AssertionError("A native get_all must have explicit bounds")
        records = self.datasets.get(doctype, [])
        def accepts(row):
            if not filters:
                return True
            for key, value in filters.items():
                if isinstance(value, tuple):
                    if len(value) != 2 or value[0] != "!=":
                        raise AssertionError("Unsupported test filter")
                    if row.get(key) == value[1]:
                        return False
                elif row.get(key) != value:
                    return False
            return True

        selected = [row for row in records if accepts(row)]
        if order_by:
            # D2: the product passes single-token orders ("name") as
            # well as "field desc"; the old unpack crashed on those.
            # A single token means ascending, like native Frappe.
            parts = order_by.split()
            key, direction = parts[0], (parts[1] if len(parts) > 1 else "asc")
            selected.sort(key=lambda row: row.get(key) or "",
                          reverse=direction.lower() == "desc")
        return [Row(x) for x in selected[:limit_page_length]]


def actual_snapshot_functions(db):
    """Compile only the real implementation with its dependencies injected."""
    module = ast.parse(API.read_text(encoding="utf-8"))
    funcs = [n for n in module.body
             if isinstance(n, ast.FunctionDef) and n.name in
             ("_bounded_rows", "_unique_by",
              "_native_program_has_curriculum", "_snapshot")]
    context = {
        "frappe": types.SimpleNamespace(db=db, ValidationError=Refused),
        "_MAX_CATALOG_ROWS": 500, "_MAX_COMPONENT_ROWS": 100,
    }
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(API), "exec"), context)
    return context


class SnapshotSafetyTests(unittest.TestCase):
    def test_21_programs_are_not_silently_truncated_at_default_twenty(self):
        rows = [Row(name=f"F-{n}", code=f"X-{n}", title=f"Family {n}",
                    status="Active") for n in range(21)]
        db = FakeDB({"TH Academic Program": rows})
        snapshot = actual_snapshot_functions(db)["_snapshot"]()
        self.assertEqual(len(snapshot["programs"]), 21)
        # D2: range(21) yields X-0..X-20 — the 21st program is X-20,
        # not X-21. Asserting X-21 was an off-by-one in the test, not
        # a truncation in the product (which returns all 21 rows,
        # not Frappe's default first 20).
        self.assertIn("X-20", snapshot["programs"])
        self.assertIn(("TH Academic Program", 501), db.calls)

    def test_over_limit_refuses_instead_of_partial_preview(self):
        rows = [Row(name=f"F-{n}", code=f"X-{n}", title=f"Family {n}",
                    status="Active") for n in range(501)]
        db = FakeDB({"TH Academic Program": rows})
        with self.assertRaisesRegex(Refused, "more than 500"):
            actual_snapshot_functions(db)["_snapshot"]()

    def test_duplicate_program_code_refused(self):
        rows = [Row(name="F-1", code="GEN", title="General", status="Active"),
                Row(name="F-2", code="GEN", title="Alias", status="Active")]
        db = FakeDB({"TH Academic Program": rows})
        with self.assertRaisesRegex(Refused, "duplicate program code"):
            actual_snapshot_functions(db)["_snapshot"]()

    def test_duplicate_level_code_refused(self):
        rows = [
            Row(name="L-1", code="PREP-1", title="P1", family="F-1",
                native_program="N-1", next_level="", status="Active"),
            Row(name="L-2", code="PREP-1", title="P1", family="F-1",
                native_program="N-2", next_level="", status="Active")]
        db = FakeDB({"TH Program Level": rows})
        with self.assertRaisesRegex(Refused, "duplicate level code"):
            actual_snapshot_functions(db)["_snapshot"]()

    def test_distinct_level_codes_cannot_share_one_native_program(self):
        rows = [
            Row(name="L-1", code="PREP-1", title="Prep 1", family="F-1",
                native_program="N-1", next_level="", status="Active"),
            Row(name="L-2", code="PREP-2", title="Prep 2", family="F-1",
                native_program="N-1", next_level="", status="Active"),
        ]
        db = FakeDB({"TH Program Level": rows})
        with self.assertRaisesRegex(Refused, "Two levels use native Program N-1"):
            actual_snapshot_functions(db)["_snapshot"]()

    def test_older_duration_versions_do_not_block_newer(self):
        db = FakeDB({
            "TH Academic Program": [Row(name="F-1", code="GE", title="GE",
                                        status="Active")],
            "TH Program Level": [Row(name="L-1", code="PRE-STARTER",
                                     title="Pre Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "TH Level Duration": [
                Row(parent="L-1", duration_value=1, duration_unit="Month",
                    effective_from="2026-03-21"),
                Row(parent="L-1", duration_value=2, duration_unit="Month",
                    effective_from="2025-03-21"),
            ],
        })
        state = actual_snapshot_functions(db)["_snapshot"]()
        self.assertEqual(state["levels"]["PRE-STARTER"]["duration_months"], 1)
        self.assertIn(("TH Level Duration", 1), db.calls)

    def test_solar_hijri_duration_is_recognized_without_overwriting_history(self):
        for unit, value, expected in (
                ("Solar Hijri Month", 2, 2),
                ("Solar Hijri Month", 1.5, None),
                ("Day", 60, None)):
            with self.subTest(unit=unit, value=value):
                db = FakeDB({
                    "TH Program Level": [Row(
                        name="L-1", code="STARTER", title="Starter",
                        family="F-1", native_program="N-1",
                        next_level="", status="Active")],
                    "TH Level Duration": [
                        Row(parent="L-1", duration_value=value,
                            duration_unit=unit, effective_from="2026-10-30"),
                        Row(parent="L-1", duration_value=1,
                            duration_unit="Month", effective_from="2026-03-21")],
                })
                state = actual_snapshot_functions(db)["_snapshot"]()
                self.assertEqual(
                    state["levels"]["STARTER"]["duration_months"], expected)

    def test_old_native_program_without_courses_is_not_ready_for_setup(self):
        db = FakeDB({
            "TH Program Level": [Row(name="L-1", code="STARTER",
                                     title="Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "Program": [Row(name="N-1")],
            "TH Level Duration": [Row(parent="L-1", duration_value=2,
                                      duration_unit="Solar Hijri Month",
                                      effective_from="2026-03-21")],
        })
        result = actual_snapshot_functions(db)["_snapshot"]()
        self.assertFalse(result["levels"]["STARTER"]["curriculum_ready"])

    def test_valid_native_course_links_are_required_and_distinct(self):
        base = {
            "TH Program Level": [Row(name="L-1", code="STARTER",
                                     title="Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "Program": [Row(name="N-1")],
            "Course": [Row(name="C-1")],
            "Program Course": [Row(parent="N-1", parenttype="Program",
                                   course="C-1", required=1)],
        }
        db = FakeDB(base)
        self.assertTrue(actual_snapshot_functions(db)["_snapshot"]()
                        ["levels"]["STARTER"]["curriculum_ready"])
        db.datasets["Program Course"].append(
            Row(parent="N-1", parenttype="Program", course="C-1", required=1))
        self.assertFalse(actual_snapshot_functions(db)["_snapshot"]()
                         ["levels"]["STARTER"]["curriculum_ready"])
        db.datasets["Program Course"][1]["course"] = "C-missing"
        self.assertFalse(actual_snapshot_functions(db)["_snapshot"]()
                         ["levels"]["STARTER"]["curriculum_ready"])

    def test_malformed_fee_plan_is_conflict_not_missing(self):
        db = FakeDB({
            "TH Program Level": [Row(name="L-1", code="PRE-STARTER",
                                     title="Pre Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "Fee Structure": [Row(name="FS-1", program="N-1",
                                  docstatus=0, academic_year="1405")],
            "Fee Component": [Row(parent="FS-1",
                                   parenttype="Fee Structure",
                                   fees_category="Other Fee", amount=500)],
        })
        state = actual_snapshot_functions(db)["_snapshot"]()
        self.assertIn("1405", state["tuition"]["PRE-STARTER"])
        self.assertIsNone(state["tuition"]["PRE-STARTER"]["1405"])

    def test_submitted_fee_structure_is_conflict_not_missing(self):
        db = FakeDB({
            "TH Program Level": [Row(name="L-1", code="PRE-STARTER",
                                     title="Pre Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "Fee Structure": [Row(name="FS-1", program="N-1",
                                  docstatus=1, academic_year="1405")],
            "Fee Component": [Row(parent="FS-1", parenttype="Fee Structure",
                                  fees_category="Semester Tuition Fee", amount=500)],
        })
        state = actual_snapshot_functions(db)["_snapshot"]()
        self.assertIsNone(state["tuition"]["PRE-STARTER"]["1405"])

    def test_duplicate_draft_fee_structure_is_conflict(self):
        db = FakeDB({
            "TH Program Level": [Row(name="L-1", code="PRE-STARTER",
                                     title="Pre Starter", family="F-1",
                                     native_program="N-1", next_level="",
                                     status="Active")],
            "Fee Structure": [
                Row(name="FS-1", program="N-1", docstatus=0, academic_year="1405"),
                Row(name="FS-2", program="N-1", docstatus=0, academic_year="1405")],
            "Fee Component": [
                Row(parent="FS-1", parenttype="Fee Structure",
                    fees_category="Semester Tuition Fee", amount=500),
                Row(parent="FS-2", parenttype="Fee Structure",
                    fees_category="Semester Tuition Fee", amount=500)],
        })
        state = actual_snapshot_functions(db)["_snapshot"]()
        self.assertIsNone(state["tuition"]["PRE-STARTER"]["1405"])


if __name__ == "__main__":
    unittest.main()
