"""SEC-DEPS-01 readable-audit slice: advisory ids must survive as annotations."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "foundation"))
from runtime_install import (ANNOTATION_MAX_LINES, ANNOTATION_TEXT_LIMIT,  # noqa: E402
                             advisory_finding_annotations,
                             advisory_group_entries,
                             advisory_summary_markdown,
                             write_advisory_step_summary,
                             untriaged_advisory_annotations,
                             hosted_failure_annotations,
                             safe_native_restore_failure_detail,
                             safe_native_site_failure_detail,
                             hrms_editor_stage_annotation)

PREFIX = "::warning file=tools/foundation/runtime_install.py::"


def stack(py=(), npm=()):
    return {"python": {"osv": {"findings": list(py)}},
            "node": {"finding_summary": list(npm)}}


class AdvisoryAnnotationTests(unittest.TestCase):
    def test_only_one_exact_sanitized_native_site_failure_is_annotated(self):
        detail = ("Native Frappe site creation failed: secure native site creation failed "
                  "(exit 1); exception type: OSError; OS error code: 2; "
                  "frames: _new_site:42,setup_db:80; "
                  "sensitive diagnostics were withheld")
        output = "private traceback and credentials\n" + detail + "\nraw private message"
        self.assertEqual(safe_native_site_failure_detail(output), detail)
        self.assertIsNone(safe_native_site_failure_detail(output + "\n" + detail))
        self.assertIsNone(safe_native_site_failure_detail(
            "Native Frappe site creation failed: password was leaked"))
        lines = hosted_failure_annotations(
            "new-site: exit 1", "new-site", safe_site_detail=detail)
        self.assertTrue(any("OS error code: 2" in line for line in lines))
        self.assertTrue(all("private traceback" not in line and
                            "raw private message" not in line for line in lines))
        self.assertFalse(any("password was leaked" in line for line in
                             hosted_failure_annotations(
                                 "new-site: exit 1", "new-site",
                                 safe_site_detail="Native Frappe site creation failed: password was leaked")))

    def test_only_exact_sanitized_native_restore_summary_is_annotated(self):
        detail = (
            "Native Frappe restore failed; exception type: SystemExit; "
            "reported exception type: FileNotFoundError; OS error code: 2; "
            "frames: _native_restore:267,_restore:276,restore_backup:378; "
            "reported frames: native_restore:91; reported CWD: other; "
            "reported path: restore-temp:artifacts/missing.sql.gz; "
            "reported parent: restore-temp:artifacts (directory); "
            "Sensitive diagnostics were withheld. Leave the application writers stopped "
            "and inspect logs through the approved secure procedure.")
        output = "raw private traceback\n" + detail + "\n/private/secret-backup"
        self.assertEqual(safe_native_restore_failure_detail(output), detail)
        self.assertIsNone(safe_native_restore_failure_detail(output + "\n" + detail))
        bench_path_detail = (
            detail.replace("reported CWD: other", "reported CWD: site-data")
            .replace("restore-temp:artifacts/missing.sql.gz", "bench:logs/frappe.log")
            .replace("restore-temp:artifacts (directory)", "bench:logs (missing)"))
        self.assertEqual(
            safe_native_restore_failure_detail(bench_path_detail), bench_path_detail)
        bench_parent_detail = (
            bench_path_detail.replace("reported CWD: site-data", "reported CWD: bench")
            .replace("bench:logs/frappe.log", "bench-parent:logs/frappe.log")
            .replace("bench:logs (missing)", "bench-parent:logs (missing)"))
        self.assertEqual(
            safe_native_restore_failure_detail(bench_parent_detail), bench_parent_detail)
        self.assertIsNone(safe_native_restore_failure_detail(
            detail.replace("restore-temp:artifacts/missing.sql.gz", "/private/secret-backup")))

        lines = hosted_failure_annotations(
            "restore-with-files: exit 1", "restore-with-files",
            safe_restore_detail=detail)
        self.assertTrue(any("native restore diagnostic: " + detail in line for line in lines))
        self.assertTrue(all("raw private traceback" not in line and
                            "/private/secret-backup" not in line for line in lines))

    def test_public_ids_are_preferred_from_aliases_and_urls(self):
        lines = advisory_finding_annotations(stack(
            py=[{"package": "pypdf", "version": "3.1", "id": "PYSEC-2099-1",
                 "aliases": ["GHSA-aaaa-bbbb-cccc"], "severity": "HIGH"}],
            npm=[{"package": "lodash", "installed_versions": ["4.17.0"], "id": 1234,
                  "url": "https://github.com/advisories/GHSA-dddd-eeee-ffff",
                  "severity": "moderate"}]), None)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(PREFIX + "advisory matches=2 in 2 packages: "))
        self.assertIn("py:pypdf@3.1 GHSA-aaaa-bbbb-cccc(high)", lines[0])
        self.assertLess(lines[0].index("py:"), lines[0].index("npm:"))
        self.assertIn("npm:lodash@4.17.0 GHSA-dddd-eeee-ffff(moderate)", lines[0])

    def test_no_findings_no_annotation_and_missing_reports_are_tolerated(self):
        self.assertEqual(advisory_finding_annotations(stack(), {"advisories": {}}), [])
        self.assertEqual(advisory_finding_annotations(None, None), [])

    def test_frontend_advisories_are_named(self):
        lines = advisory_finding_annotations(None, {"advisories": {
            "axios": [{"id": 99, "url": "https://github.com/advisories/GHSA-1111-2222-3333",
                       "severity": "high"}]}})
        self.assertIn("fe:axios GHSA-1111-2222-3333(high)", lines[0])

    def test_lines_are_single_bounded_and_truncation_is_stated(self):
        many = [{"package": f"pkg{i:03d}", "version": "1.0", "id": f"GHSA-{i:04d}-xxxx-yyyy",
                 "severity": "LOW"} for i in range(400)]
        lines = advisory_finding_annotations(stack(py=many), None)
        self.assertLessEqual(len(lines), ANNOTATION_MAX_LINES)
        for line in lines:
            self.assertNotIn("\n", line)
            self.assertLessEqual(len(line) - len(PREFIX), ANNOTATION_TEXT_LIMIT)
        self.assertRegex(lines[-1], r"\+\d+ packages not shown$")

    def test_grouped_by_package_worst_first_and_frontend_dedup(self):
        lines = advisory_finding_annotations(stack(npm=[
            {"package": "a", "installed_versions": ["1"], "id": "GHSA-low1", "severity": "low"},
            {"package": "b", "installed_versions": ["2"], "id": "GHSA-crit", "severity": "critical"},
            {"package": "b", "installed_versions": ["2"], "id": "GHSA-mod1", "severity": "moderate"}]),
            {"advisories": {"b": [{"id": "GHSA-crit", "severity": "critical"}],
                            "c": [{"id": "GHSA-fe01", "severity": "high"}]}})
        text = lines[0]
        self.assertIn("advisory matches=4 in 3 packages", text)
        self.assertIn("npm:b@2 GHSA-crit(critical),GHSA-mod1(moderate)", text)
        self.assertLess(text.index("npm:b@2"), text.index("npm:a@1"))
        self.assertNotIn("fe:b", text)
        self.assertIn("fe:c GHSA-fe01(high)", text)

    def test_ids_are_never_invented(self):
        lines = advisory_finding_annotations(stack(
            py=[{"package": "x", "version": "1", "id": None}]), None)
        self.assertIn("unidentified", lines[0])

    def test_missing_severity_is_rendered_as_question_mark(self):
        # Observed in production output of hosted run 36628837943: newly
        # published advisories whose severity the feed has not yet populated
        # render as "(?)", never as an empty string or a dropped finding.
        lines = advisory_finding_annotations(stack(
            py=[{"package": "pypdf", "version": "6.15.0", "id": "GHSA-aa11-bb22-cc33"},
                {"package": "pypdf", "version": "6.15.0", "id": "GHSA-dd44-ee55-ff66",
                 "severity": None}]), None)
        text = lines[0]
        self.assertIn("advisory matches=2 in 1 packages", text)
        self.assertIn("GHSA-aa11-bb22-cc33(?)", text)
        self.assertIn("GHSA-dd44-ee55-ff66(?)", text)
        self.assertNotIn("()", text)

    def test_multiple_installed_versions_render_as_comma_list(self):
        # Observed in production output of hosted run 36668343658:
        # npm:brace-expansion@1.1.11,2.0.1 — one package row, both resolved
        # versions, comma-joined in declaration order, advisory ids attached.
        lines = advisory_finding_annotations(stack(npm=[
            {"package": "brace-expansion", "installed_versions": ["1.1.11", "2.0.1"],
             "id": "GHSA-6j4f-fj2g-mc7p", "severity": "high"},
            {"package": "brace-expansion", "installed_versions": ["1.1.11", "2.0.1"],
             "id": "GHSA-q2hr-2g5m-vwhr", "severity": "moderate"}]), None)
        text = lines[0]
        self.assertIn("npm:brace-expansion@1.1.11,2.0.1 "
                      "GHSA-6j4f-fj2g-mc7p(high),GHSA-q2hr-2g5m-vwhr(moderate)", text)

    def test_all_untriaged_ids_survive_even_when_more_than_three_lines(self):
        # The expanded audit had 77 lockfile matches; a three-line cap hid
        # follow-redirects/1116560. Failed gates must expose every public ID.
        findings = [{"package": f"package-{i:03d}", "id": 1100000+i}
                    for i in range(90)]
        findings.append({"package": "follow-redirects", "id": 1116560})
        report = {"triage": {"node": {"untriaged": findings}}}
        lines = untriaged_advisory_annotations(report)
        self.assertGreater(len(lines), 3)
        self.assertIn("matches=91; full set", lines[0])
        self.assertEqual(sum(line.count("npm:") for line in lines), 91)
        self.assertIn("npm:follow-redirects 1116560", " ".join(lines))
        prefix = "::error file=tools/foundation/runtime_install.py::"
        self.assertTrue(all(line.startswith(prefix) and
                            len(line) - len(prefix) <= ANNOTATION_TEXT_LIMIT for line in lines))
        self.assertFalse(any("not shown" in line for line in lines))

    def test_runtime_emits_annotations_from_its_own_reports(self):
        source = (Path(__file__).resolve().parents[2]
                  / "tools/foundation/runtime_install.py").read_text()
        self.assertIn("advisory_finding_annotations(*audits)", source)
        self.assertIn('"stack-dependency-audit.json", "frontend-advisories.json"', source)


REPO = Path(__file__).resolve().parents[2]
REPLAY = REPO / "docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-09/replay-snapshot.json"
GROUP_LABEL_RE = re.compile(r"\b(py|npm|fe):([^\s@;]+)@")


def _visible_groups(lines):
    seen = set()
    for line in lines:
        for label, name in GROUP_LABEL_RE.findall(line):
            seen.add((label, name))
    return seen


class AdvisoryCompleteListTests(unittest.TestCase):
    """The annotation budget may hide groups, but never silently.

    The 2026-10-14 gap ("47 reported, 44 visible") was the nine-line annotation
    budget: the writer printed "+3 packages not shown" and the three hidden groups
    were not otherwise recorded. The complete list is now in the job summary too.
    """

    def test_budget_never_hides_a_group_silently(self):
        many = [{"package": f"pkg{i:03d}", "version": "1.0", "id": f"GHSA-{i:04d}-xxxx-yyyy",
                 "severity": "LOW"} for i in range(400)]
        audit = stack(py=many)
        lines = advisory_finding_annotations(audit, None)
        visible = _visible_groups(lines)
        hidden = re.search(r"\+(\d+) packages not shown", " ".join(lines))
        self.assertIsNotNone(hidden)
        _total, entries = advisory_group_entries(audit, None)
        self.assertEqual(len(entries), 400)
        self.assertEqual(len(visible) + int(hidden.group(1)), len(entries))

    def test_summary_lists_every_group_without_truncation(self):
        many = [{"package": f"pkg{i:03d}", "version": "1.0", "id": f"GHSA-{i:04d}-xxxx-yyyy",
                 "severity": "LOW"} for i in range(120)]
        text = advisory_summary_markdown(stack(py=many), None)
        self.assertEqual(text.count("\n- `"), 120)
        self.assertNotIn("not shown", text)
        self.assertIn("120 package groups", text)

    def test_summary_is_empty_without_matches(self):
        self.assertEqual(advisory_summary_markdown(stack(), None), "")

    def test_summary_is_written_only_inside_actions(self):
        import os
        from unittest import mock
        audit = stack(npm=[{"package": "yaml", "installed_versions": ["1.10.2"],
                            "id": "GHSA-48C2-RRV3-QJMP", "severity": "moderate"}])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            write_advisory_step_summary(audit, None)  # no target: must not raise or write
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                write_advisory_step_summary(audit, None)
                write_advisory_step_summary(audit, None)  # appends, never overwrites
            text = target.read_text()
            self.assertEqual(text.count("npm:yaml@1.10.2"), 2)

    def test_runtime_writes_the_summary_from_its_own_reports(self):
        source = (REPO / "tools/foundation/runtime_install.py").read_text()
        self.assertIn("write_advisory_step_summary(*audits)", source)

    def test_replay_snapshot_reconciles_to_ci_group_count(self):
        import json
        snap = json.loads(REPLAY.read_text(encoding="utf-8"))
        npm_groups = {e["package"] for e in snap["npm_entries"]}
        py_groups = {(r["package"], r["version"]) for r in snap["pypi_records"]}
        self.assertEqual(len(npm_groups), snap["counts"]["groups_npm_packages"])
        self.assertEqual(len(py_groups), snap["counts"]["groups_python_package_versions"])
        self.assertEqual(len(npm_groups) + len(py_groups), snap["counts"]["ci_reported_groups"])
        self.assertEqual(snap["counts"]["ci_reported_groups"], 47)

    def test_every_replay_group_is_covered_by_the_register(self):
        import json
        import advisory_triage as triage_mod
        snap = json.loads(REPLAY.read_text(encoding="utf-8"))
        triage = triage_mod.load_triage()
        for entry in snap["npm_entries"]:
            rec = triage_mod.disposition_for_finding(
                triage, package=entry["package"],
                advisories=[entry["ghsa"], str(entry["numeric_id"])],
                finding_id=str(entry["numeric_id"]))
            self.assertIsNotNone(rec, entry["package"] + " " + entry["ghsa"])
        for record in snap["pypi_records"]:
            rec = triage_mod.disposition_for_finding(
                triage, package="py:" + record["package"],
                advisories=[record["id"]] + list(record.get("aliases") or []),
                finding_id=record["id"])
            self.assertIsNotNone(rec, record["package"] + " " + record["id"])

    def test_the_three_hidden_2026_10_14_groups_are_covered(self):
        import advisory_triage as triage_mod
        triage = triage_mod.load_triage()
        expected = {
            "@tiptap/extension-link": "GHSA-vhrc-hgrq-x75r",
            "cookie": "GHSA-pxg6-pf52-xh8x",
            "yaml": "GHSA-48c2-rrv3-qjmp",
        }
        for package, ghsa in expected.items():
            rec = triage_mod.disposition_for_finding(
                triage, package=package, advisories=[ghsa], finding_id=ghsa)
            self.assertIsNotNone(rec, package)
            if package == "@tiptap/extension-link":
                # Withdrawn 2026-10-15 (ERRATUM E6): the BROWSER_SELF_DENIAL premise does not hold.
                self.assertEqual(rec["runtime_disposition"], "BLOCKED")
                self.assertEqual(rec["withdrawn_from"], "BROWSER_SELF_DENIAL")
            else:
                # Closed, or BROWSER_SELF_DENIAL (open by owner decision OD-2026-10-18-A).
                self.assertIn(rec["runtime_disposition"],
                              triage_mod.CLOSED_DISPOSITIONS | triage_mod.OWNER_OPEN_DISPOSITIONS)


if __name__ == "__main__":
    unittest.main()


class HrmsEditorStageAnnotationTests(unittest.TestCase):
    def test_stage_line_names_only_stage_and_error_class(self):
        output = ("built\n{\"status\":\"pass\"}\n"
                  "HRMS-EDITOR-STAGE-FAILED keyboard-formatting TimeoutError\n"
                  "  name: 'TimeoutError'\n")
        self.assertEqual(
            hrms_editor_stage_annotation(output),
            "::error file=tools/foundation/hrms_editor_security.mjs::"
            "built HRMS editor check failed at stage keyboard-formatting (TimeoutError)")

    def test_no_stage_line_yields_no_annotation(self):
        self.assertIsNone(hrms_editor_stage_annotation("AssertionError: plain output"))
        self.assertIsNone(hrms_editor_stage_annotation(""))
        self.assertIsNone(hrms_editor_stage_annotation(None))

    def test_page_content_in_error_text_is_not_echoed(self):
        output = "HRMS-EDITOR-STAGE-FAILED paste AssertionError <img src=x onerror=alert(1)>"
        line = hrms_editor_stage_annotation(output)
        self.assertEqual(line.split("::")[-1], "built HRMS editor check failed at stage paste (AssertionError)")
        self.assertNotIn("onerror", line)
        self.assertNotIn("<img", line)

