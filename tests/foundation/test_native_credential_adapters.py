"""Synthetic runtime harnesses must reuse credential-safe native adapters."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))


def load_tool_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NativeSiteSetupAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = load_tool_module(
            "native_site_setup_under_test", ROOT / "tools/native/site_setup.py")
        self.original_bench_dir = self.adapter.bootstrap.BENCH_DIR
        self.original_python = self.adapter.bootstrap.ENV_PYTHON
        self.payload = {
            "site": "synthetic-restore.localhost",
            "db_name": "synthetic_restore_probe",
            "db_root_password": "synthetic-root-password",
            "admin_password": "synthetic-admin-password",
            "db_password": "synthetic-site-db-password",
            "db_host": "127.0.0.1",
            "db_port": 13306,
            "set_default_site": False,
        }

    def tearDown(self):
        self.adapter.bootstrap.BENCH_DIR = self.original_bench_dir
        self.adapter.bootstrap.ENV_PYTHON = self.original_python

    def invoke(self, payload):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {
            "SITE_BENCH_DIR": "/synthetic/bench",
            "SITE_PYTHON": "/synthetic/bench/env/bin/python",
        }):
            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    status = self.adapter.main(argv=[])
        return status, output.getvalue(), errors.getvalue()

    def test_secrets_arrive_as_stdin_payload_to_native_bootstrap_installer(self):
        with mock.patch.object(self.adapter.bootstrap, "create_site") as create_site:
            status, output, errors = self.invoke(self.payload)
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertIn("Native Frappe site creation completed", output)
        create_site.assert_called_once()
        args, kwargs = create_site.call_args
        self.assertEqual(args[0], self.payload["site"])
        self.assertEqual(args[1], self.payload["db_root_password"])
        self.assertEqual(args[2], self.payload["admin_password"])
        self.assertEqual(args[3], self.payload["db_password"])
        self.assertEqual(kwargs["db_name"], self.payload["db_name"])
        self.assertFalse(kwargs["set_default_site"])
        for secret in (self.payload["db_root_password"],
                       self.payload["admin_password"], self.payload["db_password"]):
            self.assertNotIn(secret, output + errors)

    def test_site_setup_rejects_command_line_secrets(self):
        secret = "synthetic-root-password-must-not-be-argv"
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = self.adapter.main(argv=[secret])
        self.assertEqual(status, 2)
        self.assertNotIn(secret, output.getvalue() + errors.getvalue())
        self.assertIn("credentials must be supplied on stdin", errors.getvalue())

    def test_invalid_site_is_sanitized_and_never_reaches_frappe(self):
        invalid = dict(self.payload, site="../escape")
        with mock.patch.object(self.adapter.bootstrap, "create_site") as create_site:
            status, output, errors = self.invoke(invalid)
        self.assertEqual(status, 1)
        create_site.assert_not_called()
        self.assertIn("sensitive diagnostics were withheld", errors)
        self.assertNotIn("../escape", output + errors)
        for secret in (self.payload["db_root_password"],
                       self.payload["admin_password"], self.payload["db_password"]):
            self.assertNotIn(secret, output + errors)


class NativeHarnessAuthorityTests(unittest.TestCase):
    @staticmethod
    def direct_bench_authority_calls(source: str):
        tree = ast.parse(source)
        direct_operations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"bench", "b"}:
                continue
            # The first literal is a human-facing step label. Remaining literal
            # arguments are the actual Bench operation and its CLI options.
            for argument in node.args[1:]:
                if isinstance(argument, ast.Constant) and argument.value in {
                        "new-site", "backup", "restore"}:
                    direct_operations.append((node.lineno, argument.value))
        return direct_operations

    def test_all_synthetic_site_creation_and_backup_restore_rehearsals_use_adapters(self):
        harnesses = (
            ROOT / "tools/native/run_native.py",
            ROOT / "tools/foundation/runtime_install.py",
            ROOT / "tools/foundation/runtime_upgrade.py",
        )
        for path in harnesses:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("--db-root-password", source)
                self.assertNotIn("--db-password", source)
                self.assertNotIn("--admin-password", source)
                self.assertEqual(self.direct_bench_authority_calls(source), [])
                self.assertIn("tools/native/site_setup.py", source)
                if path.name == "runtime_upgrade.py":
                    self.assertIn("child diagnostics were withheld", source)
                    self.assertNotIn("r.stderr", source)
        native = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        runtime = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")
        upgrade = (ROOT / "tools/foundation/runtime_upgrade.py").read_text(encoding="utf-8")
        for source in (native, runtime, upgrade):
            self.assertIn("tools/native/run_product_backup.py", source)
        self.assertIn("product/restore.py", native)
        self.assertIn("product/restore.py", runtime)

    def test_product_image_workflow_uses_product_adapters_and_fd_secret_transport(self):
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text(encoding="utf-8")
        self.assertIn("/product/backup.py", workflow)
        self.assertIn("/product/restore.py", workflow)
        self.assertNotIn("--db-root-password", workflow)
        self.assertNotIn("--db-password", workflow)
        self.assertNotIn("--admin-password", workflow)
        self.assertNotIn("--passphrase ''", workflow)
        self.assertIn("--passphrase-fd 0", workflow)


if __name__ == "__main__":
    unittest.main()
