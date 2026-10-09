"""The product restore adapter must not put restore secrets in argv or logs."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_PATH = ROOT / "product"
if str(PRODUCT_PATH) not in sys.path:
    sys.path.insert(0, str(PRODUCT_PATH))
RESTORE_PATH = PRODUCT_PATH / "restore.py"


def load_restore():
    spec = importlib.util.spec_from_file_location("product_restore_under_test", RESTORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(site="toeflhouse.localhost", backup_set="20261008-test"):
    return {
        "site": site,
        "backup_set": backup_set,
        "encryption_key": "synthetic-native-backup-key",
        "db_root_password": "synthetic-mariadb-root-password",
        "admin_password": "synthetic-owner-admin-password",
    }


class ProductRestoreInputTests(unittest.TestCase):
    def test_credentials_are_read_from_stdin_and_passed_in_process(self):
        restore = load_restore()
        request = payload()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(restore, "_native_restore") as native:
            status = restore.main(io.StringIO(json.dumps(request)), stdout, stderr, argv=[])
        self.assertEqual(status, 0)
        native.assert_called_once_with(
            request["site"], request["backup_set"], request["encryption_key"],
            request["db_root_password"], request["admin_password"],
            context_writer=stdout)
        self.assertEqual(stdout.getvalue(), "Native Frappe restore completed.\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_rejects_secret_arguments_without_echoing_them(self):
        restore = load_restore()
        secret = "synthetic-credential-must-not-be-an-argument"
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(restore, "_native_restore") as native:
            status = restore.main(io.StringIO("{}"), stdout, stderr, argv=[secret])
        self.assertEqual(status, 2)
        native.assert_not_called()
        self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())
        self.assertIn("accepts no command-line arguments", stderr.getvalue())

    def test_invalid_site_set_or_missing_credentials_fail_before_native_restore(self):
        restore = load_restore()
        for update in (
            {"site": "../other"},
            {"backup_set": "../escape"},
            {"db_root_password": ""},
        ):
            with self.subTest(update=update):
                request = payload()
                request.update(update)
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(restore, "_native_restore") as native:
                    status = restore.main(io.StringIO(json.dumps(request)), stdout, stderr, argv=[])
                self.assertEqual(status, 2)
                native.assert_not_called()
                for secret in (request["encryption_key"],
                               request["db_root_password"],
                               request["admin_password"]):
                    if secret:
                        self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())

    def test_missing_database_or_file_artifacts_are_rejected_before_native_restore(self):
        restore = load_restore()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        site = "toeflhouse.localhost"
        backup_set = "20261008-test"
        request = payload(site=site, backup_set=backup_set)

        for missing_role in restore.BACKUP_SUFFIXES:
            with self.subTest(missing_role=missing_role):
                restore.SITES_DIR = Path(temp.name) / missing_role
                backup_dir = restore.SITES_DIR / site / "private" / "backups"
                backup_dir.mkdir(parents=True)
                for role, suffix in restore.BACKUP_SUFFIXES.items():
                    if role != missing_role:
                        (backup_dir / f"{backup_set}{suffix}").write_bytes(
                            b"synthetic encrypted fixture")

                with self.assertRaises(restore.RestoreInputError) as caught:
                    restore._native_restore(
                        site, backup_set, request["encryption_key"],
                        request["db_root_password"], request["admin_password"])
                self.assertIn(missing_role, str(caught.exception))

    def test_restore_failure_paths_outside_known_roots_are_not_reported(self):
        restore = load_restore()
        error = FileNotFoundError(2, "No such file or directory", "/private/synthetic-secret")
        self.assertIsNone(restore._safe_failure_location(error, Path("/tmp/restore-test")))
        command_error = FileNotFoundError(2, "No such file or directory", "mariadb")
        self.assertEqual(
            restore._safe_failure_location(command_error, Path("/tmp/restore-test")),
            "relative:mariadb")

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bench_dir = Path(temp.name) / "bench"
        sites_dir = bench_dir / "sites"
        sites_dir.mkdir(parents=True)
        restore.BENCH_DIR = bench_dir
        restore.SITES_DIR = sites_dir
        logger_error = FileNotFoundError(
            2, "No such file or directory", "../logs/frappe.log")
        restore_temp = Path(temp.name) / "restore-temp"
        with patch("os.getcwd", return_value=str(sites_dir)):
            self.assertEqual(
                restore._safe_failure_location(logger_error, restore_temp),
                "bench:logs/frappe.log")
            self.assertEqual(
                restore._safe_failure_parent(logger_error, restore_temp),
                ("bench:logs", "missing"))
            self.assertEqual(restore._safe_restore_context(), ("site-data", "missing"))
            summary = restore._native_restore_failure(logger_error, "")
            self.assertEqual(summary.reported_cwd, "site-data")
            self.assertEqual(summary.failure_location, "bench:logs/frappe.log")
            self.assertEqual(summary.failure_parent_location, "bench:logs")
            self.assertEqual(summary.failure_parent_state, "missing")
        (bench_dir / "logs").mkdir()
        with patch("os.getcwd", return_value=str(sites_dir)):
            self.assertEqual(restore._safe_restore_context(), ("site-data", "directory"))
        with patch("os.getcwd", return_value=str(bench_dir)):
            self.assertEqual(
                restore._safe_failure_location(logger_error, restore_temp),
                "bench-parent:logs/frappe.log")
            self.assertEqual(
                restore._safe_failure_parent(logger_error, restore_temp),
                ("bench-parent:logs", "missing"))
            self.assertEqual(restore._safe_restore_context(), ("bench", "missing"))

    def test_native_restore_output_and_exceptions_cannot_leak_credentials(self):
        restore = load_restore()
        site = "toeflhouse.localhost"
        backup_set = "20261008-test"
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        restore.SITES_DIR = Path(temp.name)
        backup_dir = restore.SITES_DIR / site / "private" / "backups"
        backup_dir.mkdir(parents=True)
        original_artifacts = {}
        for role, suffix in restore.BACKUP_SUFFIXES.items():
            path = backup_dir / f"{backup_set}{suffix}"
            path.write_bytes(b"encrypted fixture: " + role.encode("ascii"))
            original_artifacts[role] = (path, path.read_bytes())

        events = []
        frappe = types.ModuleType("frappe")
        frappe.__path__ = []
        frappe.conf = types.SimpleNamespace(db_type="mariadb")
        frappe.init = lambda name, sites_path=".": events.append(
            ("init", name, sites_path, Path.cwd()))
        frappe.destroy = lambda: events.append(("destroy",))
        database = types.ModuleType("frappe.database")
        synthetic_site_db_password = "synthetic-native-site-db-password"

        def get_database_command(**kwargs):
            return "/usr/bin/mariadb", [
                f"--user={kwargs['user']}", f"--password={kwargs['password']}",
                f"--host={kwargs['host']}", f"--port={kwargs['port']}",
                kwargs["db_name"],
            ], "mariadb"

        database.get_command = get_database_command
        frappe.database = database
        commands = types.ModuleType("frappe.commands")
        commands.__path__ = []
        site_commands = types.ModuleType("frappe.commands.site")

        def native_restore(**kwargs):
            events.append(("restore", kwargs))
            binary, db_args, _binary_name = frappe.database.get_command(
                user="site-db-user", password=synthetic_site_db_password,
                host="db", port=3306, db_name="restored_site_db")
            credential_option = db_args[0]
            credential_path = Path(credential_option.split("=", 1)[1])
            events.append(("database-command", db_args.copy(),
                           f"{binary} {shlex.join(db_args)}"))
            events.append(("database-credential-file", credential_path,
                           credential_path.read_text(encoding="ascii"),
                           stat.S_IMODE(credential_path.stat().st_mode)))
            frappe.utils.execute_in_shell(
                f"{binary} {shlex.join(db_args)}", check_exit_code=True)
            command = (
                "gpg --yes --passphrase " + kwargs["encryption_key"]
                + " --pinentry-mode loopback -o /tmp/restore-output"
                + " -d /tmp/native-encrypted-backup"
            )
            frappe.utils.execute_in_shell(command)
            print(kwargs["db_root_password"])
            print(kwargs["admin_password"])
            print(kwargs["encryption_key"])
            print("gpg: Inappropriate ioctl for device /private/synthetic-private-context")
            staged = {}
            fields_by_role = {
                "database": "sql_file_path",
                "public_files": "with_public_files",
                "private_files": "with_private_files",
            }
            roles_by_field = {field: role for role, field in fields_by_role.items()}
            for field in ("sql_file_path", "with_public_files", "with_private_files"):
                staged_path = Path(kwargs[field])
                staged[field] = staged_path
                source, original_bytes = original_artifacts[roles_by_field[field]]
                self.assertEqual(staged_path.read_bytes(), original_bytes)
                # Pinned Frappe decrypts/replaces the paths it receives. Simulate
                # that behavior and prove only disposable copies were passed.
                staged_path.write_bytes(b"native restore mutated this staged input")
                self.assertEqual(stat.S_IMODE(staged_path.stat().st_mode), 0o600)
                self.assertNotEqual(staged_path.parent, backup_dir)
                self.assertTrue(source.is_file())
            events.append(("staged-inputs", staged))
            missing_path = Path(kwargs["sql_file_path"]).parent / "missing-native-restore-input"
            try:
                raise FileNotFoundError(2, "No such file or directory", str(missing_path))
            except FileNotFoundError as native_error:
                print(f"{type(native_error).__name__}: {native_error}")
                raise SystemExit(1)

        site_commands._restore = native_restore
        utils = types.ModuleType("frappe.utils")
        utils.__path__ = []

        def original_execute(command, verbose=False, low_priority=False, check_exit_code=False):
            events.append(("original-shell", command))
            return b"", b""

        utils.execute_in_shell = original_execute
        frappe.utils = utils
        synchronization = types.ModuleType("frappe.utils.synchronization")

        @contextlib.contextmanager
        def filelock(name, timeout):
            events.append(("lock", name, timeout))
            yield

        synchronization.filelock = filelock
        modules = {
            "frappe": frappe,
            "frappe.commands": commands,
            "frappe.commands.site": site_commands,
            "frappe.database": database,
            "frappe.utils": utils,
            "frappe.utils.synchronization": synchronization,
        }
        request = payload(site=site, backup_set=backup_set)
        caller_cwd = Path.cwd()
        stdout, stderr = io.StringIO(), io.StringIO()
        gpg_calls = []

        def fake_gpg_run(arguments, **kwargs):
            gpg_calls.append((arguments, kwargs))
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        import native_gpg
        with patch.dict(sys.modules, modules):
            with patch.object(native_gpg.subprocess, "run", side_effect=fake_gpg_run):
                status = restore.main(io.StringIO(json.dumps(request)), stdout, stderr, argv=[])

        self.assertEqual(status, 1)
        self.assertEqual(len(gpg_calls), 1)
        self.assertIn(
            "Restore context before frappe.init: cwd=site-data; ../logs=unknown\n",
            stdout.getvalue())
        self.assertNotIn(request["encryption_key"], " ".join(gpg_calls[0][0]))
        self.assertEqual(gpg_calls[0][1]["input"],
                         (request["encryption_key"] + "\n").encode("ascii"))
        self.assertNotIn("--passphrase", gpg_calls[0][0])
        db_event = next(event for event in events if event[0] == "database-command")
        db_args, db_command = db_event[1:]
        self.assertNotIn(synthetic_site_db_password, " ".join(db_args))
        self.assertNotIn(synthetic_site_db_password, db_command)
        self.assertNotIn("--password", db_args)
        credential_event = next(event for event in events
                                if event[0] == "database-credential-file")
        credential_path, option_file, file_mode = credential_event[1:]
        self.assertIn(synthetic_site_db_password, option_file)
        self.assertEqual(file_mode, 0o600)
        self.assertFalse(credential_path.exists())
        self.assertIs(frappe.database.get_command, get_database_command)
        self.assertIs(frappe.utils.execute_in_shell, original_execute)
        self.assertEqual(
            events[0], ("init", site, ".", restore.SITES_DIR))
        self.assertEqual(Path.cwd(), caller_cwd)
        self.assertEqual(events[1], ("lock", "site_restore", 1))
        native_call = next(event[1] for event in events if event[0] == "restore")
        self.assertEqual(native_call["db_root_password"], request["db_root_password"])
        self.assertEqual(native_call["admin_password"], request["admin_password"])
        self.assertEqual(native_call["encryption_key"], request["encryption_key"])
        staged_inputs = next(event[1] for event in events if event[0] == "staged-inputs")
        for role, field in (("database", "sql_file_path"),
                            ("public_files", "with_public_files"),
                            ("private_files", "with_private_files")):
            source, original_bytes = original_artifacts[role]
            self.assertEqual(source.read_bytes(), original_bytes,
                             "native restore must leave the preserved backup unchanged")
            self.assertFalse(staged_inputs[field].exists(),
                             "disposable restore copy must be removed after failure")
        self.assertEqual(events[-1], ("destroy",))
        combined = stdout.getvalue() + stderr.getvalue()
        for secret in (request["encryption_key"],
                       request["db_root_password"],
                       request["admin_password"]):
            self.assertNotIn(secret, combined)
        self.assertIn("Sensitive diagnostics were withheld", stderr.getvalue())
        self.assertIn("exception type: SystemExit", stderr.getvalue())
        self.assertIn("reported exception type: FileNotFoundError", stderr.getvalue())
        self.assertIn("OS error code: 2", stderr.getvalue())
        self.assertIn("GPG diagnostic category: terminal-unavailable", stderr.getvalue())
        self.assertIn("frames:", stderr.getvalue())
        self.assertRegex(stderr.getvalue(), r"reported frames: native_restore:[0-9]+")
        self.assertIn("reported CWD: site-data", stderr.getvalue())
        self.assertIn(
            "reported path: restore-temp:artifacts/missing-native-restore-input",
            stderr.getvalue())
        self.assertIn(
            "reported parent: restore-temp:artifacts (unknown)", stderr.getvalue())
        self.assertNotIn("/tmp/toefl-house-native-restore-", stderr.getvalue())
        self.assertNotIn("synthetic-private-context", stderr.getvalue())
        self.assertNotIn("synthetic-secret", stderr.getvalue())
        self.assertNotIn("Inappropriate ioctl", stderr.getvalue())
        self.assertNotIn("No such file or directory", stderr.getvalue())

    def test_adapter_uses_stdin_in_product_and_ci_restore_paths(self):
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        runbook = (ROOT / "docs/engineering/LAUNCH-RUNBOOK.md").read_text()
        dockerfile = (ROOT / "product/app.Dockerfile").read_text()
        dockerignore = (ROOT / ".dockerignore").read_text()
        self.assertIn("COPY product/restore.py /product/restore.py", dockerfile)
        self.assertIn("COPY product/backup.py /product/backup.py", dockerfile)
        self.assertIn("COPY product/native_gpg.py /product/native_gpg.py", dockerfile)
        self.assertIn("COPY product/native_db.py /product/native_db.py", dockerfile)
        self.assertIn("!product/restore.py", dockerignore)
        self.assertIn("!product/backup.py", dockerignore)
        self.assertIn("!product/native_gpg.py", dockerignore)
        self.assertIn("!product/native_db.py", dockerignore)
        self.assertEqual(workflow.count("web /product/restore.py"), 2)
        self.assertIn("ConvertTo-Json -Compress", runbook)
        self.assertIn("StandardInput.BaseStream", runbook)
        self.assertIn("Encoding]::UTF8.GetBytes($restorePayload", runbook)
        self.assertIn('config.get("backup_encryption_key")', workflow)
        self.assertNotIn('config.get("encryption_key")', workflow)
        self.assertIn("$siteConfig.backup_encryption_key", runbook)
        backup_script = (ROOT / "product/windows/Backup TOEFL House ERP.ps1").read_text()
        self.assertIn("$siteConfigObject.backup_encryption_key", backup_script)
        for argument in ("--db-root-password", "--admin-password", "--encryption-key"):
            self.assertNotIn(argument, workflow)
            self.assertNotIn(argument, runbook)
        self.assertIn("frappe.commands.site import _restore", RESTORE_PATH.read_text())
        self.assertIn("filelock(\"site_restore\", timeout=1)", RESTORE_PATH.read_text())


if __name__ == "__main__":
    unittest.main()
