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
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))
import bootstrap


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

    def test_native_exception_type_is_safe_to_surface_but_stdin_is_not(self):
        failure = self.adapter.bootstrap.NativeSiteCreationError(
            1, "OperationalError")
        with mock.patch.object(self.adapter.bootstrap, "create_site",
                               side_effect=failure):
            status, output, errors = self.invoke(self.payload)
        self.assertEqual(status, 1)
        self.assertIn("OperationalError", errors)
        self.assertIn("sensitive diagnostics were withheld", errors)
        self.assertNotIn("Traceback", output + errors)
        for secret in (self.payload["db_root_password"],
                       self.payload["admin_password"], self.payload["db_password"]):
            self.assertNotIn(secret, output + errors)


class NativeSiteCreationDiagnosticsTests(unittest.TestCase):
    def test_child_initializes_frappe_with_the_bench_sites_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            bench = Path(directory)
            sites = bench / "sites"
            sites.mkdir()
            (sites / "apps.txt").write_text("frappe", encoding="utf-8")
            observed = {}
            frappe = types.ModuleType("frappe")
            frappe.__path__ = []

            def init(site, *, sites_path, new_site):
                observed.update(site=site, sites_path=sites_path, new_site=new_site)
                self.assertEqual(Path(sites_path), sites)
                self.assertTrue((Path(sites_path) / "apps.txt").is_file())

            frappe.init = init
            frappe.destroy = lambda: None
            installer = types.ModuleType("frappe.installer")
            installer._new_site = lambda *args, **kwargs: None
            installer.update_site_config = lambda *args, **kwargs: None
            payload = {
                "site": "native-probe.localhost",
                "db_root_password": "synthetic-root-password",
                "admin_password": "synthetic-admin-password",
                "db_password": "synthetic-site-password",
                "set_default_site": False,
            }
            with mock.patch.dict(sys.modules, {
                    "frappe": frappe, "frappe.installer": installer}):
                with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
                    with mock.patch("os.getcwd", return_value=str(sites)):
                        exec(bootstrap._CREATE_SITE_SCRIPT, {})
            self.assertEqual(observed, {
                "site": "native-probe.localhost",
                "sites_path": str(sites),
                "new_site": True,
            })

    def test_child_failure_marker_exposes_only_safe_type_code_and_frames(self):
        secrets_ = ("synthetic-root-secret", "synthetic-admin-secret",
                    "synthetic-db-secret")
        stderr = ("Traceback (most recent call last):\n"
                  "TOEFL_NATIVE_SITE_EXCEPTION=OSError\n"
                  "TOEFL_NATIVE_SITE_ERRNO=2\n"
                  "TOEFL_NATIVE_SITE_FRAMES=_new_site|42,setup_db|80\n"
                  + "database password was " + secrets_[0])
        child = mock.Mock(returncode=1, stdout="child output " + secrets_[1],
                          stderr=stderr)
        with mock.patch.object(bootstrap.subprocess, "run", return_value=child) as run:
            with self.assertRaises(bootstrap.NativeSiteCreationError) as caught:
                bootstrap.create_site("diagnostic.localhost", *secrets_)
        self.assertEqual(caught.exception.failure_type, "OSError")
        self.assertEqual(caught.exception.failure_errno, 2)
        self.assertEqual(caught.exception.failure_frames,
                         ("_new_site:42", "setup_db:80"))
        self.assertIn("OSError", str(caught.exception))
        self.assertIn("OS error code: 2", str(caught.exception))
        self.assertIn("frames: _new_site:42,setup_db:80", str(caught.exception))
        for secret in secrets_:
            self.assertNotIn(secret, str(caught.exception))
        argv = run.call_args.args[0]
        stdin_payload = run.call_args.kwargs["input"]
        self.assertEqual(run.call_args.kwargs["errors"], "replace")
        self.assertEqual(Path(run.call_args.kwargs["cwd"]),
                         bootstrap.BENCH_DIR / "sites")
        self.assertFalse(any(secret in repr(argv) for secret in secrets_))
        for secret in secrets_:
            self.assertIn(secret, stdin_payload)
        self.assertEqual(
            bootstrap._native_site_failure_type(
                "TOEFL_NATIVE_SITE_EXCEPTION=OSError\n"
                "TOEFL_NATIVE_SITE_EXCEPTION=ValueError"),
            None)
        self.assertEqual(
            bootstrap._native_site_failure_type(
                "TOEFL_NATIVE_SITE_EXCEPTION=Bad Type"),
            None)
        self.assertEqual(
            bootstrap._native_site_failure_errno(
                "TOEFL_NATIVE_SITE_ERRNO=2\nTOEFL_NATIVE_SITE_ERRNO=13"),
            None)
        self.assertEqual(
            bootstrap._native_site_failure_errno(
                "TOEFL_NATIVE_SITE_ERRNO=999999"),
            None)
        self.assertEqual(
            bootstrap._native_site_failure_frames(
                "TOEFL_NATIVE_SITE_FRAMES=source|2\n"
                "TOEFL_NATIVE_SITE_FRAMES=frame|3"),
            ())
        self.assertEqual(
            bootstrap._native_site_failure_frames(
                "TOEFL_NATIVE_SITE_FRAMES=secret text|2"),
            ())

    def test_parent_os_error_exposes_only_validated_numeric_code(self):
        secrets_ = ("synthetic-root-secret", "synthetic-admin-secret",
                    "synthetic-db-secret")
        error = PermissionError(13, "secret path /synthetic/private", "/synthetic/private")
        with mock.patch.object(bootstrap.subprocess, "run", side_effect=error):
            with self.assertRaises(bootstrap.NativeSiteCreationError) as caught:
                bootstrap.create_site("diagnostic.localhost", *secrets_)
        self.assertEqual(caught.exception.failure_type, "PermissionError")
        self.assertEqual(caught.exception.failure_errno, 13)
        self.assertIn("OS error code: 13", str(caught.exception))
        self.assertNotIn("secret path", str(caught.exception))
        self.assertNotIn("/synthetic/private", str(caught.exception))
        for secret in secrets_:
            self.assertNotIn(secret, str(caught.exception))

    def test_product_bootstrap_log_surfaces_safe_type_without_child_text(self):
        output, errors = io.StringIO(), io.StringIO()
        failure = bootstrap.NativeSiteCreationError(1, "OperationalError")
        with mock.patch.object(bootstrap, "bootstrap", side_effect=failure):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = bootstrap.main()
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("OperationalError", errors.getvalue())
        self.assertIn("sensitive diagnostics were withheld", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())


class NativeProductBackupDiagnosticsTests(unittest.TestCase):
    def test_backup_failure_summary_withholds_message_path_and_secrets(self):
        adapter = load_tool_module(
            "native_product_backup_under_test", ROOT / "tools/native/run_product_backup.py")
        try:
            raise PermissionError(13, "synthetic secret path", "/private/synthetic-secret")
        except PermissionError as error:
            summary = adapter.safe_failure_summary(error)
        self.assertIn("exception type: PermissionError", summary)
        self.assertIn("OS error code: 13", summary)
        self.assertIn("frames: test_backup_failure_summary_withholds_message_path_and_secrets:",
                      summary)
        self.assertNotIn("synthetic secret", summary)
        self.assertNotIn("/private", summary)
        self.assertNotIn("Traceback", summary)

    def test_backup_failure_summary_never_surfaces_system_exit_text(self):
        adapter = load_tool_module(
            "native_product_backup_under_test", ROOT / "tools/native/run_product_backup.py")
        summary = adapter.safe_failure_summary(SystemExit("synthetic private detail"))
        self.assertIn("exception type: SystemExit", summary)
        self.assertNotIn("synthetic private detail", summary)


class NativeHarnessAuthorityTests(unittest.TestCase):
    def test_native_runner_stages_the_exact_canonical_owner_ledger_idempotently(self):
        runner = load_tool_module("native_runner_under_test", ROOT / "tools/native/run_native.py")
        canonical = ROOT / "docs/owner-decisions.json"
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory) / "lab"
            target = runner.stage_owner_decision_ledger(lab)
            self.assertEqual(target, lab / "docs/owner-decisions.json")
            self.assertEqual(target.read_bytes(), canonical.read_bytes())
            self.assertEqual(runner.stage_owner_decision_ledger(lab), target)
            target.write_text("conflicting ledger", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "conflicts with the canonical copy"):
                runner.stage_owner_decision_ledger(lab)
            self.assertEqual(target.read_text(encoding="utf-8"), "conflicting ledger")

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
