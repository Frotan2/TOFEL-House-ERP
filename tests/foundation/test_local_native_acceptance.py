"""Local native qualification must never authorize an operational database."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.native import acceptance_context as context


SOURCE = "a" * 40
CHECKER = "b" * 40


def manifest():
    return {"schema": context.SCHEMA, "scope": context.LOCAL_SCOPE,
            "source_revision": SOURCE, "checker_revision": CHECKER, "production_authorization": "REJECT",
            "sites_path": context.SITES_PATH, "evidence_root": context.EVIDENCE_ROOT,
            "docker_project": "th-qual-win-4b14-20261105",
            "sites": {"placement-test.localhost": {"database": "syn_primary"},
                      "placement-second.localhost": {"database": "syn_second"}},
            "isolation": dict(context.ISOLATION)}


class LocalAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "authorization.json"
        self.document = manifest()
        self.write(self.document)
        self.env = {"TOEFL_HOUSE_LOCAL_ACCEPTANCE_MANIFEST": str(self.path),
                    "TOEFL_HOUSE_ACCEPTANCE_SOURCE_REVISION": SOURCE,
                    "TOEFL_HOUSE_ACCEPTANCE_CHECKER_REVISION": CHECKER,
                    "PLACEMENT_REPORT": context.EVIDENCE_ROOT + "/native-checks.json"}
        # Actual qualification runs non-root in a read-only Docker bind mount.
        # Host tests cannot make a Windows temporary path into that Linux mount.
        self.writable = self.enterContext(patch.object(context.os, "access", return_value=False))
        self.enterContext(patch.object(context, "_validate_output"))
        self.security = ModuleType("toefl_house.security")
        self.security.SYNTHETIC = "SYNTHETIC"
        self.security.site_mode = Mock(return_value="SYNTHETIC")
        self.enterContext(patch.dict("sys.modules", {"toefl_house.security": self.security}))

    def write(self, document):
        self.path.write_text(json.dumps(document), encoding="utf-8")

    def load(self):
        return context.execution_context(self.env, cwd=context.SITES_PATH)

    def frappe(self):
        return SimpleNamespace(local=SimpleNamespace(site=context.SITES[0], sites_path=context.SITES_PATH),
                               conf={"db_name": "syn_primary", "db_type": "mariadb", "db_host": "db",
                                     "db_port": 3306, "allow_tests": 1, "toefl_house_synthetic_only": 1})

    def guard(self, authorization=None, frappe=None, site=context.SITES[0], sites_path=context.SITES_PATH):
        (authorization or self.load()).guard_connection(frappe or self.frappe(), site, sites_path)

    def test_local_scope_records_distinct_source_and_checker_without_hosted_claim(self):
        authorization = self.load()
        self.guard(authorization)
        self.assertTrue(authorization.local)
        self.assertEqual(authorization.source_revision, SOURCE)
        self.assertEqual(authorization.metadata()["checker_revision"], CHECKER)
        self.assertEqual(authorization.metadata()["execution_context"], context.LOCAL_SCOPE)
        self.assertNotIn("GITHUB_ACTIONS", self.env)

    def test_hosted_mode_remains_unchanged_and_local_manifest_is_never_ignored(self):
        hosted = context.execution_context({"GITHUB_ACTIONS": "true", "GITHUB_SHA": SOURCE})
        self.assertFalse(hosted.local)
        self.assertEqual(hosted.metadata(), {})
        hosted.guard_connection(None, "operational-site", "unrelated")
        self.env["GITHUB_ACTIONS"] = "true"
        self.path.write_text("invalid", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.load()

    def test_missing_authorization_does_not_enable_local_execution(self):
        with self.assertRaisesRegex(RuntimeError, "authorization"):
            context.execution_context({})
        self.path.unlink()
        with self.assertRaises(RuntimeError):
            self.load()

    def test_writable_manifest_is_refused(self):
        self.writable.return_value = True
        with self.assertRaisesRegex(RuntimeError, "writable"):
            self.load()

    def test_non_regular_manifest_is_refused_before_opening(self):
        self.path.unlink()
        self.path.mkdir()
        with patch.object(context.os, "open") as opened:
            with self.assertRaisesRegex(RuntimeError, "regular file"):
                self.load()
            opened.assert_not_called()

    def test_malformed_duplicate_oversized_or_relative_manifest_is_refused(self):
        for raw in ("", "invalid", "[]", '{"schema": 1, "schema": 2}', " " * (context.MAX_MANIFEST_BYTES + 1)):
            with self.subTest(raw=raw[:30]):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    self.load()
        self.env["TOEFL_HOUSE_LOCAL_ACCEPTANCE_MANIFEST"] = "relative.json"
        with self.assertRaises(RuntimeError):
            self.load()

    def test_wrong_schema_revision_scope_paths_and_storage_claims_are_refused(self):
        mutations = (("schema", "unknown"), ("scope", "PRODUCTION"), ("source_revision", "c" * 40),
                     ("source_revision", "A" * 40), ("checker_revision", "c" * 40),
                     ("production_authorization", "APPROVE"), ("sites_path", "/customer/sites"),
                     ("evidence_root", "/tmp/../customer"), ("docker_project", "toefl-house-erp"),
                     ("isolation", dict(context.ISOLATION, existing_volumes_reused=True)),
                     ("isolation", dict(context.ISOLATION, fresh_project=1)))
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.write(dict(self.document, **{key: value}))
                self.load()

    def test_unknown_fields_real_sites_duplicate_and_real_databases_are_refused(self):
        variants = [dict(self.document, extra=True)]
        for site, database in (("toeflhouse.localhost", "syn_primary"), (context.SITES[0], "customer_db"),
                               (context.SITES[0], "syn_second")):
            document = copy.deepcopy(self.document)
            document["sites"].pop(context.SITES[0])
            document["sites"][site] = {"database": database}
            variants.append(document)
        for document in variants:
            with self.subTest(document=document), self.assertRaises(RuntimeError):
                self.write(document)
                self.load()

    def test_output_and_working_directory_must_be_the_dedicated_paths(self):
        self.env["PLACEMENT_REPORT"] = "/tmp/other.json"
        with self.assertRaises(RuntimeError):
            self.load()
        self.env["PLACEMENT_REPORT"] = context.EVIDENCE_ROOT + "/native-checks.json"
        with self.assertRaises(RuntimeError):
            context.execution_context(self.env, cwd="/customer/sites")

    def test_manifest_change_is_detected_before_another_connection(self):
        authorization = self.load()
        self.write(dict(self.document, docker_project="th-qual-win-other"))
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.guard(authorization)

    def test_connection_to_real_site_root_database_or_endpoint_is_refused(self):
        for key, value in (("db_name", "customer_db"), ("db_name", "syn_second"), ("db_type", "postgres"),
                           ("db_host", "localhost"), ("db_port", 3307), ("db_port", True), ("db_port", "3306"),
                           ("db_socket", "/var/run/db.sock"), ("db_user", "root")):
            frappe = self.frappe()
            frappe.conf[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.guard(frappe=frappe)
        with self.assertRaises(RuntimeError):
            self.guard(site="toeflhouse.localhost")
        with self.assertRaises(RuntimeError):
            self.guard(sites_path="/customer/sites")
        frappe = self.frappe()
        frappe.local.sites_path = "/customer/sites"
        with self.assertRaises(RuntimeError):
            self.guard(frappe=frappe)

    def test_flags_and_production_state_fail_closed_without_mutation(self):
        for key, value in (("allow_tests", 0), ("allow_tests", True), ("allow_tests", "1"),
                           ("toefl_house_synthetic_only", None), ("toefl_house_production_active", 1),
                           ("toefl_house_production_active", "0"),
                           ("toefl_house_production_site", context.SITES[0])):
            frappe = self.frappe()
            frappe.conf[key] = value
            before = copy.deepcopy(frappe.conf)
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.guard(frappe=frappe)
            self.assertEqual(frappe.conf, before)
        self.security.site_mode.return_value = "REFUSED"
        with self.assertRaisesRegex(RuntimeError, "site mode"):
            self.guard()


class EvidenceOutputTests(unittest.TestCase):
    def test_output_overwrite_and_missing_directory_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native-checks.json"
            context._validate_output(output)
            output.write_text("preserved", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                context._validate_output(output)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserved")
            with self.assertRaisesRegex(RuntimeError, "directory"):
                context._validate_output(Path(directory) / "missing" / "native-checks.json")


class WorkerConnectionTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "tools/native/tuition_refund_races.py"
        self.frappe = Mock()
        with patch.dict("sys.modules", {"frappe": self.frappe}):
            spec = importlib.util.spec_from_file_location("local_refund_race_fixture", path)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def test_worker_guard_runs_before_connect_and_refusal_never_opens_database(self):
        events = []
        self.frappe.init.side_effect = lambda **kwargs: events.append("init")
        self.frappe.connect.side_effect = lambda: events.append("connect")
        guard = Mock(side_effect=lambda *args: events.append("guard"))
        self.module._connect_worker(self.frappe, context.SITES[0], context.SITES_PATH, guard)
        self.assertEqual(events, ["init", "guard", "connect"])
        self.frappe.reset_mock()
        guard.side_effect = RuntimeError("not authorized")
        with self.assertRaises(RuntimeError):
            self.module._connect_worker(self.frappe, context.SITES[0], context.SITES_PATH, guard)
        self.frappe.connect.assert_not_called()
        self.frappe.destroy.assert_called_once()

    def test_hosted_worker_remains_compatible_without_local_guard(self):
        self.module._connect_worker(self.frappe, context.SITES[0], context.SITES_PATH, None)
        self.frappe.connect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
