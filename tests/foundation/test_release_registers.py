"""Static validation of the R2 release surface (factual operations
registers). Pure JSON/AST; imports nothing from the app.

The registers ship as native Report module files
(finance/report/<slug>/<slug>.json, the upstream-canonical route used by
ERPNext itself) and import via module sync. This suite guards the
invariants: raw facts only (single SELECT, no aggregates - the metrics
layer is the A12 owner deliverable), an explicit designed audience (Has
Role rows), a ref-doctype anchor whose native `report` permission can be
satisfied by the audience roles without widening them into broad native
roles, and the minimal report-only permission grants on the TH-owned
operations doctype. Hosted proof of import, execution and role gating
lives in tools/placement/native_checks.py (release-registers-* checks).

The attendance-coverage register is deliberately absent: no narrow TH
teaching role holds the native `report` flag on Student Attendance, and
the options to anchor one (granting Academics User, Custom DocPerm
replication, or a new TH anchor doctype) are owner decisions recorded in
docs/engineering/RELEASE-GAP-MAP.md.
"""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"
ROLES = APP / "fixtures/role.json"
MODULES = APP / "modules.txt"
REPORT_DIR = APP / "finance/report"
OP_JSON = APP / "placement/doctype/th_placement_operation/th_placement_operation.json"

EXPECTED = {
    "TH Tuition Billing Register": {
        "ref": "Fees",
        "roles": {"Finance Officer"},
        "columns": ["fees", "student", "program_enrollment", "academic_year",
                    "posting_date", "due_date", "grand_total",
                    "outstanding_amount", "docstatus"],
    },
    "TH Placement Billing Register": {
        "ref": "TH Placement Operation",
        "roles": {"Finance Officer", "Finance Auditor"},
        "columns": ["sales_invoice", "customer", "placement_case",
                    "posting_date", "due_date", "grand_total",
                    "outstanding_amount", "docstatus"],
    },
}
AGGREGATES = re.compile(r"\b(count|sum|avg|min|max)\s*\(|\bgroup\s+by\b", re.I)


class ReleaseRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reports = {}
        for path in sorted(REPORT_DIR.glob("*/*.json")):
            cls.reports[path.parent.name] = json.loads(path.read_text())
        cls.role_names = {r["name"] for r in json.loads(ROLES.read_text())}
        cls.modules = {m.strip() for m in MODULES.read_text().splitlines() if m.strip()}

    def test_expected_register_set(self):
        self.assertEqual({r["name"] for r in self.reports.values()}, set(EXPECTED))

    def test_module_file_layout(self):
        # exact paths frappe.model.sync.get_doc_files scans for each module
        for slug, report in self.reports.items():
            self.assertEqual(slug, report["name"].lower().replace(" ", "_"), slug)
            self.assertEqual(report["doctype"], "Report")
            self.assertEqual(report["name"], report["report_name"], slug)
            self.assertEqual(report["module"], "Finance")
            self.assertIn(report["module"], self.modules)

    def test_native_shape(self):
        for report in self.reports.values():
            self.assertEqual(report["report_type"], "Query Report")
            self.assertEqual(report["is_standard"], "Yes")
            self.assertEqual(report["disabled"], 0)
            spec = EXPECTED[report["name"]]
            self.assertEqual(report["ref_doctype"], spec["ref"])

    def test_audience_explicit_and_narrow(self):
        for report in self.reports.values():
            roles = {r["role"] for r in report["roles"]}
            spec = EXPECTED[report["name"]]
            self.assertTrue(roles, (report["name"], "empty roles would open the register to every desk user"))
            self.assertEqual(roles, spec["roles"], report["name"])
            self.assertTrue(roles <= self.role_names,
                            (report["name"], sorted(roles - self.role_names)))

    def test_query_is_raw_facts_only(self):
        for report in self.reports.values():
            q = report["query"].strip()
            self.assertTrue(q.lower().startswith("select"), report["name"])
            self.assertNotIn(";", q, (report["name"], "single statement only"))
            self.assertIsNone(AGGREGATES.search(q),
                              (report["name"], "aggregates are metrics, not facts (A12 owner layer)"))

    def test_column_contract_matches_query_aliases(self):
        for report in self.reports.values():
            aliases = re.findall(r"\bas\s+([a-z_]+)", report["query"], re.I)
            self.assertEqual(aliases, EXPECTED[report["name"]]["columns"], report["name"])

    def test_operations_doctype_report_grants_are_minimal(self):
        perms = json.loads(OP_JSON.read_text())["permissions"]
        by_role = {p["role"]: p for p in perms}
        # Finance Auditor keeps its pre-existing read row, extended with report
        auditor = by_role["Finance Auditor"]
        self.assertEqual(auditor.get("report"), 1)
        self.assertEqual(auditor.get("read"), 1)
        # Finance Officer: report-only - no read/write/create/submit/select
        officer = by_role["Finance Officer"]
        self.assertEqual(officer.get("report"), 1)
        for flag in ("read", "write", "create", "submit", "cancel", "select", "delete", "export"):
            self.assertFalse(officer.get(flag), (flag, "report grant must stay minimal"))

    def test_no_unanchored_attendance_register(self):
        # Owner decision D9 gates the attendance-coverage register; it must not
        # half-ship without an access-anchor decision.
        for path in APP.glob("*/report/*/*.json"):
            self.assertNotIn("attendance", path.name.lower())


if __name__ == "__main__":
    unittest.main()
