"""Contract tests for tools/foundation/operator_bootstrap.py.

The full local bootstrap run needs Docker/MariaDB/Redis and the pinned
toolchain, so the executable proof available in this repository's own sandbox
is the --dry-run plan: every step, in order, built from the live version
matrix, with secrets redacted from all records. Real-run behavior beyond that
is honestly labelled DOCUMENTED BUT NOT EXECUTED in the module docstring.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import operator_bootstrap  # noqa: E402


def make_args(**overrides):
    import argparse

    defaults = dict(site="toefl-house.localhost", workdir="/tmp/operator-test-lab", python=None,
                    db_root_password_env="TH_DB_ROOT_PASSWORD", db_password_env="TH_DB_PASSWORD",
                    admin_password_env="TH_ADMIN_PASSWORD")
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def build_dry_plan(env: dict | None = None, **arg_overrides):
    env = env or {}
    with mock.patch.dict(os.environ, env, clear=False):
        for name in ("TH_DB_ROOT_PASSWORD", "TH_DB_PASSWORD", "TH_ADMIN_PASSWORD"):
            if name not in env:
                os.environ.pop(name, None)
        return operator_bootstrap.build_and_run(make_args(**arg_overrides), operator_bootstrap.load_parts(),
                                                dry_run=True)


class MatrixLoadContract(unittest.TestCase):
    def test_load_parts_from_live_matrix(self):
        parts = operator_bootstrap.load_parts()
        self.assertEqual(parts["frappe"]["commit"], "988e54f3c4c291e2077a83809663f123731abe76")
        self.assertIn("@sha256:", parts["mariadb"]["image_digest"])
        self.assertIn("@sha256:", parts["redis"]["image_digest"])
        self.assertEqual(parts["python"]["selected_version"], "3.14.7")
        self.assertEqual(parts["node"]["selected_version"], "24.21.0")

    def test_fail_closed_on_matrix_without_digest(self):
        matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
        for component in matrix["components"]:
            if component["name"] == "mariadb":
                component["image_digest"] = None
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "matrix.json"
            tampered.write_text(json.dumps(matrix))
            with mock.patch.object(operator_bootstrap, "MATRIX_PATH", tampered):
                with self.assertRaises(SystemExit):
                    operator_bootstrap.load_parts()


class PlanContract(unittest.TestCase):
    def test_full_plan_order_matches_hosted_qualification_sequence(self):
        result = build_dry_plan()
        names = [r["name"] for r in result["records"]]
        anchors = ["docker-version", "tools-venv", "clone-frappe", "verify-hrms", "start-mariadb",
                   "mariadb-health", "bench-init", "config-redis_cache", "get-app-erpnext", "get-app-hrms",
                   "get-app-foundation_security", "get-app-toefl_house", "python-dependency-check", "new-site",
                   "install-app-erpnext", "install-app-foundation_security", "install-app-toefl_house",
                   "migrate-first", "migrate-replay", "initialize-native-site-encryption-key", "asset-build"]
        positions = [names.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions), f"plan order drifted: {anchors}")

    def test_dry_runs_plan_every_step_without_executing(self):
        result = build_dry_plan()
        self.assertTrue(result["records"])
        for record in result["records"]:
            self.assertEqual(record["status"], "planned_not_executed")
            self.assertNotIn("exit_code", record)

    def test_services_use_digest_pinned_images_from_matrix(self):
        result = build_dry_plan()
        parts = operator_bootstrap.load_parts()
        commands = {r["name"]: r["command"] for r in result["records"]}
        self.assertIn(parts["mariadb"]["image_digest"], commands["start-mariadb"])
        self.assertIn(parts["redis"]["image_digest"], commands["start-redis-queue"])
        self.assertIn(parts["redis"]["image_digest"], commands["start-redis-cache"])

    def test_site_and_install_commands_cover_full_app_stack(self):
        result = build_dry_plan()
        names = [r["name"] for r in result["records"]]
        for app in ("erpnext", "education", "payments", "hrms", "foundation_security", "toefl_house"):
            self.assertIn("install-app-" + app, names)

    def test_records_never_embed_password_values(self):
        result = build_dry_plan(env={"TH_DB_ROOT_PASSWORD": "root-secret-x",
                                     "TH_DB_PASSWORD": "db-secret-y",
                                     "TH_ADMIN_PASSWORD": "admin-secret-z"})
        blob = json.dumps(result["records"])
        for secret in ("root-secret-x", "db-secret-y", "admin-secret-z"):
            self.assertNotIn(secret, blob)
        new_site = next(r for r in result["records"] if r["name"] == "new-site")
        self.assertIn("[DB_ROOT_PASSWORD]", new_site["command"])
        self.assertIn("[ADMIN_PASSWORD]", new_site["command"])

    def test_real_run_refuses_missing_password_environment(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in ("TH_DB_ROOT_PASSWORD", "TH_DB_PASSWORD", "TH_ADMIN_PASSWORD"):
                os.environ.pop(name, None)
            with self.assertRaises(SystemExit):
                operator_bootstrap.build_and_run(make_args(), operator_bootstrap.load_parts(), dry_run=False)


class GuardContract(unittest.TestCase):
    def test_refuses_non_linux(self):
        with mock.patch.object(operator_bootstrap.platform, "system", return_value="Windows"):
            with mock.patch.object(sys, "argv", ["operator_bootstrap.py", "--dry-run"]):
                with self.assertRaises(SystemExit):
                    operator_bootstrap.main()

    def test_refuses_repository_checkout_as_workdir(self):
        with mock.patch.object(sys, "argv", ["operator_bootstrap.py", "--dry-run", "--workdir", str(ROOT)]):
            with self.assertRaises(SystemExit):
                operator_bootstrap.main()


if __name__ == "__main__":
    unittest.main()
