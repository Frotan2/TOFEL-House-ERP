"""Failed-job fallback: native RQ registries without the virtual controller.

RQ Job is a VIRTUAL doctype on pinned frappe and its controller gates
every read on ``has_permission("RQ Job")`` (ignoring ignore_permissions),
so the sanctioned ``project_rows`` projection 403s for desk audiences over
HTTP. ``operations._rq_failed_jobs`` reads the same native facts the
controller itself reads (queue.failed_job_registry + Job.fetch_many +
serialize_job). These tests drive it with stubbed RQ/framework modules —
no redis, no bench.
"""
import datetime
import sys
import types
import unittest

from tests.desk.test_desk_contract import _import_desk


SITE = "site1.local"


class _FakeJob:
    def __init__(self, jid, status, queue, job_name,
                 started_at=None, ended_at=None, site=SITE):
        self.id = jid
        self._status = status
        self._queue = queue
        self._job_name = job_name
        self._started_at = started_at
        self._ended_at = ended_at
        self._site = site


class _FakeQueue:
    def __init__(self, name):
        self.name = name


def _install_rq_fakes(testcase, jobs, queues=("default", "short"), fail_queues=False):
    """Install fake rq / background_jobs / rq_job modules. Jobs is a list
    of _FakeJob; each is filed under (queue, status) like a real registry.
    """
    registry = {}
    by_id = {}
    for job in jobs:
        registry.setdefault((job._queue, job._status), []).append(job.id)
        by_id[job.id] = job

    rq_pkg = types.ModuleType("rq")
    rq_pkg.__path__ = []
    rq_job_mod = types.ModuleType("rq.job")

    class _Job:
        @staticmethod
        def fetch_many(job_ids, connection):
            assert connection is not None
            return [by_id.get(jid) for jid in job_ids]

    rq_job_mod.Job = _Job

    bg_mod = types.ModuleType("frappe.utils.background_jobs")
    if fail_queues:
        def _boom():
            raise ConnectionError("synthetic redis down")
        bg_mod.get_queues = _boom
    else:
        bg_mod.get_queues = lambda: [_FakeQueue(name) for name in queues]
    bg_mod.get_redis_conn = lambda: object()

    ctrl_mod = types.ModuleType("frappe.core.doctype.rq_job.rq_job")
    ctrl_mod.fetch_job_ids = lambda queue, status: list(
        registry.get((queue.name, status), []))
    ctrl_mod.filter_current_site_jobs = lambda ids: [
        jid for jid in ids if jid.startswith(SITE)]
    ctrl_mod.get_job_status = lambda job: job._status
    ctrl_mod.serialize_job = lambda job: {
        "name": job.id, "job_id": job.id, "queue": job._queue,
        "job_name": job._job_name, "status": job._status,
        "started_at": job._started_at, "ended_at": job._ended_at,
        "exc_info": "TRACEBACK MUST NOT LEAK", "arguments": "{}",
    }

    fakes = {
        "rq": rq_pkg,
        "rq.job": rq_job_mod,
        "frappe.utils.background_jobs": bg_mod,
        "frappe.core": types.ModuleType("frappe.core"),
        "frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
        "frappe.core.doctype.rq_job": types.ModuleType(
            "frappe.core.doctype.rq_job"),
        "frappe.core.doctype.rq_job.rq_job": ctrl_mod,
    }
    for key in ("frappe.core", "frappe.core.doctype",
                "frappe.core.doctype.rq_job"):
        fakes[key].__path__ = []
    previous = {key: sys.modules.get(key) for key in fakes}
    sys.modules.update(fakes)

    def _restore():
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    testcase.addCleanup(_restore)
    return by_id


def _health_module(testcase, rq_rows):
    """operations module whose project_rows 403s exactly like the real
    virtual controller for RQ Job, and returns rq_rows otherwise."""
    _install_rq_fakes(testcase, rq_rows)

    def selective(desk, doctype, fields, filters=None, order_by=None,
                  limit=0):
        if doctype == "RQ Job":
            raise module.frappe.PermissionError("synthetic controller gate")
        return []

    module = _import_desk("operations", roles={"General Manager"})
    module.frappe.ping = lambda: "pong"
    module.project_rows = selective
    return module


class RQRegistryFallbackTests(unittest.TestCase):
    def test_rows_are_confined_to_the_allow_listed_projection(self):
        module = _import_desk("operations", roles={"General Manager"})
        _install_rq_fakes(self, [_FakeJob(
            SITE + ":9", "failed", "default", "send_digest")])
        rows, readable = module._rq_failed_jobs(25)
        self.assertTrue(readable)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]),
                         set(module.RQ_JOB_FAILED_FIELDS))
        self.assertEqual(rows[0]["job_name"], "send_digest")
        self.assertEqual(rows[0]["queue"], "default")
        self.assertNotIn("exc_info", rows[0])

    def test_only_current_site_failed_jobs_survive(self):
        module = _import_desk("operations", roles={"General Manager"})
        _install_rq_fakes(self, [
            _FakeJob(SITE + ":1", "failed", "default", "bad"),
            _FakeJob(SITE + ":2", "finished", "default", "ok"),
            _FakeJob("other.local:3", "failed", "default", "foreign"),
        ])
        rows, readable = module._rq_failed_jobs(25)
        self.assertTrue(readable)
        self.assertEqual([row["name"] for row in rows], [SITE + ":1"])

    def test_rows_sort_by_ended_desc_with_unknown_last_and_limit(self):
        module = _import_desk("operations", roles={"General Manager"})
        _install_rq_fakes(self, [
            _FakeJob(SITE + ":old", "failed", "default", "a",
                     ended_at=datetime.datetime(2026, 9, 17, 7, 0, 0)),
            _FakeJob(SITE + ":new", "failed", "default", "b",
                     ended_at=datetime.datetime(2026, 9, 17, 8, 0, 0)),
            _FakeJob(SITE + ":mystery", "failed", "default", "c",
                     ended_at=""),
        ])
        rows, _ = module._rq_failed_jobs(2)
        self.assertEqual([row["name"] for row in rows],
                         [SITE + ":new", SITE + ":old"])
        rows, _ = module._rq_failed_jobs(25)
        self.assertEqual([row["name"] for row in rows],
                         [SITE + ":new", SITE + ":old", SITE + ":mystery"])

    def test_unreachable_registries_yield_unknown_not_zero(self):
        module = _import_desk("operations", roles={"General Manager"})
        _install_rq_fakes(self, [], fail_queues=True)
        rows, readable = module._rq_failed_jobs(25)
        self.assertEqual((rows, readable), ([], False))

    def test_health_falls_back_when_the_projection_is_gated(self):
        module = _health_module(self, [_FakeJob(
            SITE + ":9", "failed", "default", "send_digest",
            started_at="2026-09-17 07:00:00",
            ended_at="2026-09-17 07:01:00")])
        facts, items = module._system_health()
        values = {fact["label"]: fact["value"] for fact in facts}
        self.assertEqual(values["Failed background jobs"], 1)
        staged = {item["id"]: item for item in items}
        self.assertEqual(staged[SITE + ":9"]["stage"],
                         "Failed background job")
        self.assertIn("condition:failed_background_jobs", staged)

    def test_health_marks_unreadable_registries_instead_of_zero(self):
        module = _import_desk("operations", roles={"General Manager"})
        _install_rq_fakes(self, [], fail_queues=True)

        def selective(desk, doctype, fields, filters=None, order_by=None,
                      limit=0):
            if doctype == "RQ Job":
                raise module.frappe.PermissionError(
                    "synthetic controller gate")
            return []

        module.frappe.ping = lambda: "pong"
        module.project_rows = selective
        facts, items = module._system_health()
        values = {fact["label"]: fact["value"] for fact in facts}
        self.assertEqual(values["Failed background jobs"], "Not readable")
        staged = {item["id"]: item for item in items}
        self.assertNotIn("condition:failed_background_jobs", staged)


if __name__ == "__main__":
    unittest.main()
