"""Exact-SHA release gates and narrowly scoped workflow dispatch orchestration."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from tools.release import verify_ci_gates as gates


SHA = "a" * 40
OTHER_SHA = "b" * 40
TOKEN = "test-token-never-print"
REPOSITORY = "example/customer-erp"
REF = "refs/heads/release-candidate"


def run(path, run_id, *, sha=SHA, status="completed", conclusion="success", attempt=1, created=None):
    return {"id": run_id, "path": path, "head_sha": sha, "status": status, "conclusion": conclusion,
            "run_attempt": attempt, "created_at": created or f"2026-10-23T00:00:{run_id:02d}Z"}


def passing_runs():
    return [run(path, index + 1) for index, path in enumerate(gates.REQUIRED_WORKFLOWS)]


def response(payload):
    return io.BytesIO(json.dumps(payload).encode() if payload is not None else b"")


class EvaluateGateRunsTests(unittest.TestCase):
    def evaluate(self, runs, current=None):
        return gates.evaluate_gate_runs(runs, SHA, current)

    def test_all_four_canonical_workflows_are_required(self):
        self.assertEqual(gates.REQUIRED_WORKFLOWS, (
            ".github/workflows/owned-suite.yml", ".github/workflows/native-lifecycle.yml",
            ".github/workflows/foundation-runtime.yml", ".github/workflows/windows-customer-package.yml"))
        self.assertEqual(self.evaluate(passing_runs())["status"], "passed")

    def test_wrong_sha_display_name_and_unrelated_workflows_do_not_qualify(self):
        runs = passing_runs()
        runs[0]["head_sha"] = OTHER_SHA
        runs += [run("Owned suite", 20), run(".github/workflows/unrelated.yml", 21)]
        report = self.evaluate(runs)
        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["gates"][0]["reason"], "missing")

    def test_missing_and_current_run_cannot_qualify(self):
        self.assertEqual(self.evaluate([])["status"], "pending")
        report = self.evaluate(passing_runs(), current="1")
        self.assertEqual(report["gates"][0]["reason"], "missing")

    def test_every_nonsuccess_completed_conclusion_rejects(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped", "neutral", "action_required",
                           "startup_failure", "stale", None, "unrecognized"):
            with self.subTest(conclusion=conclusion):
                runs = passing_runs()
                runs[0]["conclusion"] = conclusion
                self.assertEqual(self.evaluate(runs)["status"], "failed")

    def test_incomplete_statuses_remain_pending_even_with_stale_success(self):
        for status in gates.PENDING_STATUSES:
            with self.subTest(status=status):
                runs = passing_runs()
                runs.append(run(gates.REQUIRED_WORKFLOWS[0], 10, status=status, conclusion="success"))
                self.assertEqual(self.evaluate(runs)["status"], "pending")

    def test_latest_failure_beats_old_pass_regardless_of_input_order_or_updated_time(self):
        runs = passing_runs()
        runs[0]["updated_at"] = "2099-01-01T00:00:00Z"
        runs.append(run(gates.REQUIRED_WORKFLOWS[0], 10, conclusion="failure"))
        for ordered in (runs, list(reversed(runs))):
            report = self.evaluate(ordered)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["gates"][0]["run_id"], 10)

    def test_new_success_can_supersede_old_failure(self):
        runs = passing_runs()
        runs[0]["conclusion"] = "failure"
        runs.append(run(gates.REQUIRED_WORKFLOWS[0], 10))
        self.assertEqual(self.evaluate(runs)["status"], "passed")

    def test_latest_attempt_of_same_run_is_selected(self):
        runs = passing_runs()
        rerun = dict(runs[0], run_attempt=2, status="in_progress", conclusion=None)
        for ordered in (runs + [rerun], [rerun] + runs):
            report = self.evaluate(ordered)
            self.assertEqual(report["status"], "pending")
            self.assertEqual(report["gates"][0]["run_attempt"], 2)
        rerun.update(status="completed", conclusion="failure")
        self.assertEqual(self.evaluate(runs + [rerun])["status"], "failed")

    def test_creation_time_precedes_id_and_old_rerun_cannot_hide_new_failure(self):
        runs = passing_runs()
        runs.append(run(gates.REQUIRED_WORKFLOWS[0], 10, conclusion="failure"))
        runs.append(run(gates.REQUIRED_WORKFLOWS[0], 20, attempt=5, created=runs[0]["created_at"]))
        self.assertEqual(self.evaluate(runs)["status"], "failed")

    def test_malformed_or_conflicting_relevant_metadata_fails_closed(self):
        for overrides in ({"id": None}, {"id": True}, {"created_at": "bad"}, {"run_attempt": 0},
                          {"created_at": "2026-10-23T00:00:10"}, {"status": "unknown"}):
            with self.subTest(overrides=overrides):
                runs = passing_runs()
                runs[0].update(overrides)
                self.assertEqual(self.evaluate(runs)["status"], "failed")
        runs = passing_runs()
        self.assertEqual(self.evaluate(runs + [dict(runs[0], conclusion="failure")])["status"], "failed")

    def test_evaluation_does_not_mutate_inputs(self):
        runs = passing_runs()
        before = copy.deepcopy(runs)
        self.evaluate(runs)
        self.assertEqual(runs, before)


class GateEvidenceTests(unittest.TestCase):
    def evidence(self):
        report = gates.evaluate_gate_runs(passing_runs(), SHA, None)
        return gates.make_gate_evidence(report, REPOSITORY)

    def test_portable_receipt_binds_every_exact_sha_run_and_preserves_reject(self):
        evidence = self.evidence()
        self.assertIs(gates.validate_gate_evidence(evidence, SHA), evidence)
        self.assertEqual(evidence["source_revision"], SHA)
        self.assertEqual(evidence["production_authorization"], "REJECT")
        self.assertEqual({row["workflow"] for row in evidence["gates"]}, set(gates.REQUIRED_WORKFLOWS))
        for row in evidence["gates"]:
            self.assertEqual(row["run_url"], f"https://github.com/{REPOSITORY}/actions/runs/{row['run_id']}")

    def test_wrong_revision_missing_run_or_non_success_cannot_be_embedded(self):
        for mutate in (
            lambda row: row.update(source_revision=OTHER_SHA),
            lambda row: row.update(status="pending"),
            lambda row: row.update(production_authorization="ALLOW"),
            lambda row: row["gates"].pop(),
            lambda row: row["gates"][0].update(run_id=None),
            lambda row: row["gates"][0].update(run_url="https://example.invalid/1"),
            lambda row: row["gates"][0].update(reason="manual_override"),
        ):
            with self.subTest(mutate=mutate):
                evidence = self.evidence()
                mutate(evidence)
                with self.assertRaises(ValueError):
                    gates.validate_gate_evidence(evidence, SHA)

    def test_one_run_cannot_impersonate_multiple_workflows(self):
        evidence = self.evidence()
        first = evidence["gates"][0]
        evidence["gates"][1]["run_id"] = first["run_id"]
        evidence["gates"][1]["run_url"] = first["run_url"]
        with self.assertRaisesRegex(ValueError, "reuses one run"):
            gates.validate_gate_evidence(evidence, SHA)

    def test_receipt_write_is_new_only_and_never_overwrites(self):
        evidence = self.evidence()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "gates.json"
            gates.write_gate_evidence(destination, evidence, SHA)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), evidence)
            before = destination.read_bytes()
            with self.assertRaises(ValueError):
                gates.write_gate_evidence(destination, evidence, SHA)
            self.assertEqual(destination.read_bytes(), before)


class GateApiTests(unittest.TestCase):
    def test_pagination_fetches_unfiltered_statuses_for_exact_sha(self):
        batches = [{"total_count": 4, "workflow_runs": passing_runs()[:2]},
                   {"total_count": 4, "workflow_runs": passing_runs()[2:]}]
        with patch.object(gates, "urlopen", side_effect=[response(p) for p in batches]) as request:
            self.assertEqual(gates.fetch_gate_runs(REPOSITORY, SHA, TOKEN), passing_runs())
        for index, call in enumerate(request.call_args_list):
            req = call.args[0]
            self.assertEqual(req.get_method(), "GET")
            query = parse_qs(urlsplit(req.full_url).query)
            self.assertEqual(query["head_sha"], [SHA])
            self.assertEqual(query["page"], [str(index + 1)])
            self.assertNotIn("status", query)
            self.assertEqual(req.get_header("Authorization"), "Bearer " + TOKEN)

    def test_bad_incomplete_and_truncated_api_results_fail_closed(self):
        for payload in (None, {}, {"total_count": 1001, "workflow_runs": []},
                        {"total_count": True, "workflow_runs": []}, {"total_count": 1, "workflow_runs": []},
                        {"total_count": 1, "workflow_runs": [None]}):
            with self.subTest(payload=payload), patch.object(gates, "urlopen", return_value=response(payload)):
                with self.assertRaises(gates.GateQueryError):
                    gates.fetch_gate_runs(REPOSITORY, SHA, TOKEN)

    def test_ensure_started_dispatches_only_missing_paths_with_validated_ref(self):
        existing = passing_runs()[:2]
        existing[0]["conclusion"] = "failure"  # Must never be rerun/replaced.
        replies = [response({"total_count": 2, "workflow_runs": existing}),
                   response({"object": {"type": "commit", "sha": SHA}}), response(None),
                   response({"object": {"type": "commit", "sha": SHA}}), response(None)]
        with patch.object(gates, "urlopen", side_effect=replies) as api:
            report = gates.ensure_gate_runs_started(REPOSITORY, SHA, 999, REF, TOKEN)
        self.assertEqual(report["dispatched"], list(gates.REQUIRED_WORKFLOWS[2:]))
        calls = [call.args[0] for call in api.call_args_list]
        self.assertEqual(calls[1].get_method(), "GET")
        self.assertTrue(calls[1].full_url.endswith("/git/ref/heads/release-candidate"))
        for req, path in zip((req for req in calls if req.get_method() == "POST"), gates.REQUIRED_WORKFLOWS[2:]):
            self.assertEqual(req.get_method(), "POST")
            self.assertTrue(req.full_url.endswith("/actions/workflows/" + path.rsplit("/", 1)[1] + "/dispatches"))
            self.assertEqual(json.loads(req.data), {"ref": REF})

    def test_moved_ref_never_dispatches_anything(self):
        replies = [response({"total_count": 0, "workflow_runs": []}),
                   response({"object": {"type": "commit", "sha": OTHER_SHA}})]
        with patch.object(gates, "urlopen", side_effect=replies) as api:
            with self.assertRaisesRegex(gates.GateQueryError, "ref moved"):
                gates.ensure_gate_runs_started(REPOSITORY, SHA, None, REF, TOKEN)
        self.assertTrue(all(call.args[0].get_method() == "GET" for call in api.call_args_list))

    def test_ref_is_rechecked_before_each_missing_workflow_dispatch(self):
        replies = [response({"total_count": 2, "workflow_runs": passing_runs()[:2]}),
                   response({"object": {"type": "commit", "sha": SHA}}), response(None),
                   response({"object": {"type": "commit", "sha": OTHER_SHA}})]
        with patch.object(gates, "urlopen", side_effect=replies) as api:
            with self.assertRaisesRegex(gates.GateQueryError, "ref moved"):
                gates.ensure_gate_runs_started(REPOSITORY, SHA, None, REF, TOKEN)
        posts = [call.args[0] for call in api.call_args_list if call.args[0].get_method() == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0].full_url.endswith("/foundation-runtime.yml/dispatches"))

    def test_existing_runs_are_never_dispatched_or_cancelled(self):
        runs = passing_runs()
        runs[0].update(status="in_progress", conclusion=None)
        runs[1]["conclusion"] = "cancelled"
        with patch.object(gates, "urlopen", return_value=response({"total_count": 4, "workflow_runs": runs})) as api:
            report = gates.ensure_gate_runs_started(REPOSITORY, SHA, None, REF, TOKEN)
        self.assertEqual(report["status"], "present")
        self.assertEqual(report["dispatched"], [])
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args[0].get_method(), "GET")

    def test_annotated_tags_are_peeled_before_dispatch(self):
        replies = [response({"total_count": 3, "workflow_runs": passing_runs()[:3]}),
                   response({"object": {"type": "tag", "sha": OTHER_SHA}}),
                   response({"object": {"type": "commit", "sha": SHA}}), response(None)]
        with patch.object(gates, "urlopen", side_effect=replies) as api:
            report = gates.ensure_gate_runs_started(REPOSITORY, SHA, None, "refs/tags/v1.0", TOKEN)
        self.assertEqual(len(report["dispatched"]), 1)
        self.assertTrue(api.call_args_list[2].args[0].full_url.endswith("/git/tags/" + OTHER_SHA))
        self.assertEqual(json.loads(api.call_args.args[0].data), {"ref": "refs/tags/v1.0"})


class GateCliTests(unittest.TestCase):
    def setUp(self):
        self.env = {"GH_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_SHA": SHA,
                    "GITHUB_RUN_ID": "999", "GITHUB_REF": REF}

    def invoke(self, args=()):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(output), redirect_stderr(errors):
            code = gates.main(list(args))
        self.assertNotIn(TOKEN, output.getvalue() + errors.getvalue())
        return code, output.getvalue(), errors.getvalue()

    def test_default_cli_polls_pending_then_passes_without_writes(self):
        queued = passing_runs()
        queued[0].update(status="queued", conclusion=None)
        replies = [response({"total_count": 4, "workflow_runs": queued}),
                   response({"total_count": 4, "workflow_runs": passing_runs()})]
        with patch.object(gates, "urlopen", side_effect=replies) as api, patch.object(gates.time, "sleep") as sleep:
            code, output, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)["status"] for line in output.splitlines()], ["pending", "passed"])
        sleep.assert_called_once_with(15)
        self.assertTrue(all(call.args[0].get_method() == "GET" for call in api.call_args_list))

    def test_default_cli_fails_immediately_on_failed_gate(self):
        runs = passing_runs()
        runs[0]["conclusion"] = "failure"
        with patch.object(gates, "fetch_gate_runs", return_value=runs), patch.object(gates.time, "sleep") as sleep:
            self.assertEqual(self.invoke()[0], 1)
        sleep.assert_not_called()

    def test_timeout_never_qualifies_missing_or_late_success(self):
        with patch.object(gates, "fetch_gate_runs", return_value=[]), \
                patch.object(gates.time, "monotonic", side_effect=[0, 901]), patch.object(gates.time, "sleep") as sleep:
            self.assertEqual(self.invoke()[0], 1)
        sleep.assert_not_called()
        with patch.object(gates, "fetch_gate_runs", return_value=passing_runs()), \
                patch.object(gates.time, "monotonic", side_effect=[0, 901]):
            self.assertEqual(self.invoke()[0], 1)

    def test_ensure_started_cli_posts_without_waiting(self):
        replies = [response({"total_count": 3, "workflow_runs": passing_runs()[:3]}),
                   response({"object": {"type": "commit", "sha": SHA}}), response(None)]
        with patch.object(gates, "urlopen", side_effect=replies), patch.object(gates.time, "sleep") as sleep:
            code, output, _ = self.invoke(["--ensure-started"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["status"], "started")
        sleep.assert_not_called()

    def test_cli_emits_receipt_only_after_all_gates_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "receipt.json"
            with patch.object(gates, "fetch_gate_runs", return_value=passing_runs()):
                code, _, _ = self.invoke(["--output", str(destination)])
            self.assertEqual(code, 0)
            gates.validate_gate_evidence(json.loads(destination.read_text(encoding="utf-8")), SHA)
            before = destination.read_bytes()
            with patch.object(gates, "fetch_gate_runs") as fetch:
                self.assertEqual(self.invoke(["--output", str(destination)])[0], 1)
                fetch.assert_not_called()
            self.assertEqual(destination.read_bytes(), before)

    def test_dispatch_mode_cannot_emit_a_passing_receipt(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(gates, "urlopen") as api:
            code, _, _ = self.invoke(["--ensure-started", "--output", str(Path(temporary) / "receipt.json")])
            self.assertEqual(code, 1)
            api.assert_not_called()

    def test_full_workflow_deadline_allows_slow_checks_but_stays_bounded(self):
        with patch.object(gates, "fetch_gate_runs", return_value=passing_runs()), \
                patch.object(gates.time, "monotonic", side_effect=[0, 1800]):
            self.assertEqual(self.invoke(["--timeout", "3600"])[0], 0)
        with patch.object(gates, "fetch_gate_runs") as fetch:
            self.assertEqual(self.invoke(["--timeout", "3601"])[0], 1)
            fetch.assert_not_called()

    def test_api_failures_never_print_response_body_or_credentials(self):
        for error in (HTTPError("https://api.github.com/" + TOKEN, 403, TOKEN, {}, io.BytesIO(TOKEN.encode())),
                      URLError(TOKEN), OSError(TOKEN)):
            with self.subTest(error_type=type(error).__name__), patch.object(gates, "urlopen", side_effect=error):
                code, _, errors = self.invoke()
                self.assertEqual(code, 1)
                self.assertIn("GitHub API request failed", errors)

    def test_missing_credentials_and_invalid_configuration_do_not_call_api(self):
        for key, value in (("GH_TOKEN", ""), ("GITHUB_SHA", "bad"), ("GITHUB_REPOSITORY", "../bad"),
                           ("GITHUB_RUN_ID", "bad")):
            with self.subTest(key=key), patch.object(gates, "urlopen") as api:
                original = self.env[key]
                self.env[key] = value
                try:
                    self.assertEqual(self.invoke()[0], 1)
                finally:
                    self.env[key] = original
                # Run-ID validation occurs before a request as well.
                api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
