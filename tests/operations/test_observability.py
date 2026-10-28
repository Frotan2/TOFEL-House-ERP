"""Alert-condition generation over native health facts (pure module).

toefl_house.observability turns a desk-projected snapshot into NAMED
conditions. These tests pin the pinning: native vocabulary only (RQ Job
failed, Scheduled Job Log Failed, stopped flag), no invented severity, no
interpretation of the free-text worker state, and an empty snapshot yields
silence rather than an all-clear claim.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/toefl_house"))

from toefl_house import observability as obs  # noqa: E402


class SummarizeSnapshotTests(unittest.TestCase):
    def test_counts_are_counts_with_no_thresholds(self):
        summary = obs.summarize_snapshot({
            "error_logs": [{"name": "ERR-1"}, {"name": "ERR-2"}],
            "failed_jobs": [{"name": "J-1", "queue": "default"},
                            {"name": "J-2", "queue": "long"}],
            "workers": [{"status": "Active"}, {"status": "Suspended"}],
            "stopped_job_types": [{"name": "S-1"}],
            "failed_scheduled_logs": [],
        })
        self.assertEqual(summary["unseen_error_logs"], 2)
        self.assertEqual(summary["failed_jobs"], 2)
        self.assertEqual(summary["failed_job_queues"], ["default", "long"])
        self.assertEqual(summary["workers_observed"], 2)
        # Worker states are echoed verbatim, never bucketed.
        self.assertEqual(summary["worker_states"], ["Active", "Suspended"])
        self.assertEqual(summary["stopped_scheduled_job_types"], 1)
        self.assertEqual(summary["failed_scheduled_logs"], 0)

    def test_missing_keys_snapshot_to_zero(self):
        summary = obs.summarize_snapshot({})
        self.assertEqual(summary["unseen_error_logs"], 0)
        self.assertEqual(summary["failed_jobs"], 0)
        self.assertEqual(summary["workers_observed"], 0)


class EvaluateAlertConditionsTests(unittest.TestCase):
    def test_empty_world_is_silent_not_all_clear(self):
        self.assertEqual(obs.evaluate_alert_conditions(
            obs.summarize_snapshot({}), ping_ok=True), [])

    def test_failed_ping_is_its_own_condition(self):
        conditions = obs.evaluate_alert_conditions(
            obs.summarize_snapshot({}), ping_ok=False)
        self.assertEqual([c["condition"] for c in conditions],
                         ["application_unreachable"])

    def test_each_native_trigger_names_itself(self):
        summary = {"unseen_error_logs": 3, "failed_jobs": 2,
                   "failed_job_queues": ["long"],
                   "stopped_scheduled_job_types": 1,
                   "failed_scheduled_logs": 4}
        conditions = obs.evaluate_alert_conditions(summary, ping_ok=True)
        self.assertEqual([c["condition"] for c in conditions], [
            "unseen_error_logs", "failed_background_jobs",
            "stopped_scheduled_job_types", "failed_scheduled_runs"])
        detail = {c["condition"]: c["detail"] for c in conditions}
        self.assertIn("3", detail["unseen_error_logs"])
        self.assertIn("long", detail["failed_background_jobs"])
        # The traceback boundary is stated on the condition itself.
        self.assertIn("stay", detail["failed_background_jobs"])

    def test_conditions_carry_no_severity(self):
        conditions = obs.evaluate_alert_conditions(
            {"failed_jobs": 1, "failed_job_queues": []}, ping_ok=True)
        self.assertEqual(set(conditions[0]), {"condition", "detail", "observed"})

    def test_worker_states_alone_never_raise_a_condition(self):
        summary = obs.summarize_snapshot(
            {"workers": [{"status": "mysterious-state"}, {"status": ""}]})
        self.assertEqual(obs.evaluate_alert_conditions(summary, ping_ok=True), [])
