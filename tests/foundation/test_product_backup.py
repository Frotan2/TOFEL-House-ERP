"""Native backup transport must preserve Frappe authority and old artifacts."""
from __future__ import annotations

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
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

import native_gpg  # noqa: E402


def load_backup():
    spec = importlib.util.spec_from_file_location(
        "product_backup_under_test", PRODUCT / "backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeGpgTransportTests(unittest.TestCase):
    def setUp(self):
        self.key = "synthetic key with '$; shell metacharacters"
        self.calls = []
        self.original_calls = []
        self.utils = types.SimpleNamespace()
        self.utils.execute_in_shell = self.original_execute
        self.frappe = types.SimpleNamespace(utils=self.utils)

    def original_execute(self, command, verbose=False, low_priority=False, check_exit_code=False):
        self.original_calls.append((command, verbose, low_priority, check_exit_code))
        return b"native stderr", b"native stdout"

    def fake_run(self, arguments, **kwargs):
        self.calls.append((arguments, kwargs))
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def test_encrypt_and_decrypt_keys_go_only_to_stdin(self):
        commands = (
            f"gpg --yes --passphrase {self.key} --pinentry-mode loopback -c /tmp/backup-file",
            f"gpg --yes --passphrase {self.key} --pinentry-mode loopback "
            "-o /tmp/restore-file -d /tmp/encrypted-file",
        )
        with patch.object(native_gpg.subprocess, "run", side_effect=self.fake_run):
            with native_gpg.safe_gpg_transport(self.frappe, self.key):
                for command in commands:
                    self.assertEqual(self.utils.execute_in_shell(command), (b"", b""))
        self.assertEqual(self.utils.execute_in_shell, self.original_execute)
        self.assertEqual(len(self.calls), 2)
        for arguments, kwargs in self.calls:
            self.assertIn("--batch", arguments)
            self.assertNotIn(self.key, " ".join(arguments))
            self.assertNotIn("--passphrase", arguments)
            self.assertIn("--passphrase-fd", arguments)
            self.assertEqual(kwargs["input"], (self.key + "\n").encode("ascii"))
            self.assertNotIn("shell", kwargs)

    def test_non_gpg_commands_keep_the_native_execute_in_shell_path(self):
        with native_gpg.safe_gpg_transport(self.frappe, self.key):
            result = self.utils.execute_in_shell(
                "file sites/example/private/backups/native.sql.gz",
                check_exit_code=True,
            )
        self.assertEqual(result, (b"native stderr", b"native stdout"))
        self.assertEqual(self.original_calls, [(
            "file sites/example/private/backups/native.sql.gz", False, False, True)])

    def test_unexpected_passphrase_command_fails_closed_without_echoing_key(self):
        command = f"gpg --yes --passphrase {self.key}; echo leaked"
        with native_gpg.safe_gpg_transport(self.frappe, self.key):
            with self.assertRaises(RuntimeError) as error:
                self.utils.execute_in_shell(command)
        self.assertNotIn(self.key, str(error.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.original_calls, [])

    def test_failed_gpg_child_output_is_withheld(self):
        secret = "synthetic gpg failure diagnostic containing secret context"
        command = f"gpg --yes --passphrase {self.key} --pinentry-mode loopback -c /tmp/native-file"
        result = types.SimpleNamespace(
            returncode=7, stdout=secret.encode(), stderr=secret.encode())
        with patch.object(native_gpg.subprocess, "run", return_value=result):
            with native_gpg.safe_gpg_transport(self.frappe, self.key):
                with self.assertRaises(RuntimeError) as error:
                    self.utils.execute_in_shell(command, check_exit_code=True)
        self.assertNotIn(self.key, str(error.exception))
        self.assertNotIn(secret, str(error.exception))
        self.assertIn("sensitive diagnostics were withheld", str(error.exception))

    def test_verbose_gpg_child_diagnostics_are_not_forwarded_to_console(self):
        secret = b"synthetic child diagnostic that must not be echoed"
        command = f"gpg --yes --passphrase {self.key} --pinentry-mode loopback -c /tmp/native-file"
        output, errors = io.StringIO(), io.StringIO()
        result = types.SimpleNamespace(returncode=0, stdout=secret, stderr=secret)
        with patch.object(native_gpg.subprocess, "run", return_value=result):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                with native_gpg.safe_gpg_transport(self.frappe, self.key):
                    returned = self.utils.execute_in_shell(command, verbose=True)
        self.assertEqual(returned, (secret, secret))
        self.assertNotIn(secret.decode(), output.getvalue() + errors.getvalue())


class NativeFrappeBackupAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backup = load_backup()
        self.site = self.backup.SUPPORTED_SITE
        self.sites = Path(self.temp.name) / "sites"
        self.backup.SITES_DIR = self.sites
        self.site_root = self.sites / self.site
        self.backup_dir = self.site_root / "private" / "backups"
        self.backup_dir.mkdir(parents=True)
        self.key = "synthetic-native-frappe-backup-key"
        self.db_password = "synthetic-mariadb-dump-password"
        self.old_database = self.backup_dir / "20261001_old-database-enc.sql.gz"
        self.old_config = self.backup_dir / "20261001_old-site_config_backup-enc.json"
        self.old_database.write_bytes(b"pre-existing encrypted database backup")
        self.old_config.write_text(
            '{"backup_encryption_key":"pre-existing-key"}\n', encoding="utf-8")
        self.old_database_bytes = self.old_database.read_bytes()
        self.old_config_bytes = self.old_config.read_bytes()
        self.events = []
        self.gpg_calls = []
        self.fail_packet_verification = False

        frappe = types.ModuleType("frappe")
        frappe.__path__ = []
        frappe.conf = types.SimpleNamespace(db_type="mariadb")
        frappe.init = lambda name, sites_path: self.events.append(("init", name, sites_path))
        frappe.connect = lambda: self.events.append(("connect",))
        frappe.destroy = lambda: self.events.append(("destroy",))
        frappe.get_system_settings = lambda name: name == "encrypt_backup"
        frappe.utils = types.ModuleType("frappe.utils")
        frappe.utils.__path__ = []
        database = types.ModuleType("frappe.database")
        database.get_command = self.native_get_command
        frappe.database = database

        backups = types.ModuleType("frappe.utils.backups")
        backups.get_backup_path = lambda: str(self.backup_dir)
        backups.get_or_generate_backup_encryption_key = self.get_or_generate_key
        backups.delete_temp_backups = self.native_cleanup
        backups.scheduled_backup = self.native_scheduled_backup
        frappe.utils.backups = backups
        frappe.utils.execute_in_shell = self.original_execute_in_shell
        self.frappe = frappe
        self.backups = backups
        self.database = database
        self.modules = {
            "frappe": frappe,
            "frappe.utils": frappe.utils,
            "frappe.utils.backups": backups,
            "frappe.database": database,
        }
        self.original_cleanup = backups.delete_temp_backups

    def original_execute_in_shell(self, command, verbose=False, low_priority=False,
                                  check_exit_code=False):
        self.events.append(("shell", command, verbose, low_priority, check_exit_code))
        return b"", b""

    def native_get_command(self, **kwargs):
        self.events.append(("native-get-command", kwargs.copy()))
        arguments = [f"--user={kwargs['user']}", f"--password={kwargs['password']}",
                     f"--host={kwargs['host']}", f"--port={kwargs['port']}",
                     kwargs["db_name"], "--single-transaction"]
        return "/usr/bin/mariadb-dump", arguments, "mariadb-dump"

    def get_or_generate_key(self):
        self.events.append(("get-backup-encryption-key",))
        return self.key

    def native_cleanup(self, *args, **kwargs):
        self.events.append(("native-cleanup-called",))
        # If the adapter fails to suppress this Frappe cleanup call, this
        # intentionally destructive stand-in removes the old fixture backups.
        for entry in self.backup_dir.iterdir():
            if entry.is_file():
                entry.unlink()

    def native_scheduled_backup(self, **kwargs):
        self.events.append(("scheduled-backup", kwargs.copy()))
        self.assertFalse(kwargs["ignore_files"])
        self.assertTrue(kwargs["force"])
        self.assertFalse(kwargs["verbose"])
        staging = Path(kwargs["backup_path"])
        binary, dump_arguments, _binary_name = self.database.get_command(
            user="site-db-user", password=self.db_password, host="db", port=3306,
            db_name="toeflhouse_db", dump=True)
        credential_option = dump_arguments[0]
        self.assertTrue(credential_option.startswith("--defaults-extra-file="))
        credential_path = Path(credential_option.split("=", 1)[1])
        self.assertEqual(stat.S_IMODE(credential_path.stat().st_mode), 0o600)
        credential_file_content = credential_path.read_text(encoding="ascii")
        command = f"{binary} {shlex.join(dump_arguments)} | gzip > /tmp/native-dump.sql.gz"
        self.frappe.utils.execute_in_shell(command, low_priority=True, check_exit_code=True)
        self.events.append(("credential-file", credential_path, credential_file_content,
                            dump_arguments.copy(), command))
        # Exercise Frappe's call to delete_temp_backups from new_backup(). The
        # product adapter must leave the already-existing source files intact.
        self.backups.delete_temp_backups()
        backup_set = "20261009_091500-toeflhouse_localhost"
        outputs = {
            "database": staging / f"{backup_set}{self.backup.BACKUP_SUFFIXES['database']}",
            "public_files": staging / f"{backup_set}{self.backup.BACKUP_SUFFIXES['public_files']}",
            "private_files": staging / f"{backup_set}{self.backup.BACKUP_SUFFIXES['private_files']}",
            "site_config": staging / f"{backup_set}-site_config_backup-enc.json",
        }
        for role in ("database", "public_files", "private_files"):
            path = outputs[role]
            path.write_bytes(("plain native " + role).encode("ascii"))
            command = (
                f"gpg --yes --passphrase {self.key} --pinentry-mode loopback "
                f"-c {path}"
            )
            self.frappe.utils.execute_in_shell(command)
            path.rename(Path(str(path) + ".gpg"))
            Path(str(path) + ".gpg").rename(path)
        # Native BackupGenerator copies site_config.json before backup_encryption;
        # this sidecar proves the adapter generated the key first.
        outputs["site_config"].write_text(
            json.dumps({"backup_encryption_key": self.key, "db_password": "secret"}),
            encoding="utf-8",
        )
        return types.SimpleNamespace(
            backup_path_db=str(outputs["database"]),
            backup_path_files=str(outputs["public_files"]),
            backup_path_private_files=str(outputs["private_files"]),
            backup_path_conf=str(outputs["site_config"]),
        )

    def fake_gpg_run(self, arguments, **kwargs):
        self.gpg_calls.append((arguments, kwargs))
        if "-c" in arguments:
            path = Path(arguments[-1])
            Path(str(path) + ".gpg").write_bytes(b"encrypted native artifact")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if "--list-packets" in arguments:
            output = (b"gpg: :symkey enc packet:\n" if not self.fail_packet_verification
                      else b"gpg: :compressed packet:\n")
            return types.SimpleNamespace(returncode=0, stdout=output, stderr=b"")
        self.fail("unexpected child process invocation")

    def _run_adapter(self):
        with patch.dict(sys.modules, self.modules):
            with patch.object(native_gpg.subprocess, "run", side_effect=self.fake_gpg_run):
                self.backup._native_backup()

    def test_native_backup_uses_safe_gpg_and_preserves_preexisting_backups(self):
        self._run_adapter()
        self.assertEqual(self.old_database.read_bytes(), self.old_database_bytes)
        self.assertEqual(self.old_config.read_bytes(), self.old_config_bytes)
        self.assertEqual(self.backups.delete_temp_backups, self.original_cleanup)
        self.assertNotIn(("native-cleanup-called",), self.events)
        self.assertEqual(self.events[0][0], "init")
        self.assertIn(("get-backup-encryption-key",), self.events)
        key_index = self.events.index(("get-backup-encryption-key",))
        schedule_index = next(i for i, event in enumerate(self.events)
                              if event[0] == "scheduled-backup")
        self.assertLess(key_index, schedule_index)
        self.assertEqual(self.events[-1], ("destroy",))
        credential_event = next(event for event in self.events
                                if event[0] == "credential-file")
        credential_path, option_file, dump_arguments, dump_command = credential_event[1:]
        self.assertIn(self.db_password, option_file)
        self.assertNotIn(self.db_password, " ".join(dump_arguments))
        self.assertNotIn(self.db_password, dump_command)
        self.assertFalse(credential_path.exists(), "temporary MariaDB credential file must be removed")

        set_name = "20261009_091500-toeflhouse_localhost"
        expected = [set_name + suffix for suffix in self.backup.BACKUP_SUFFIXES.values()]
        expected.append(set_name + "-site_config_backup-enc.json")
        for name in expected:
            self.assertTrue((self.backup_dir / name).is_file(), name)
        self.assertEqual(json.loads(
            (self.backup_dir / (set_name + "-site_config_backup-enc.json")).read_text()
        )["backup_encryption_key"], self.key)

        encryption_calls = [call for call in self.gpg_calls if "-c" in call[0]]
        packet_calls = [call for call in self.gpg_calls if "--list-packets" in call[0]]
        self.assertEqual(len(encryption_calls), 3)
        self.assertEqual(len(packet_calls), 3)
        for arguments, kwargs in packet_calls:
            self.assertIn("--batch", arguments)
            self.assertIn("--passphrase-fd", arguments)
            self.assertEqual(kwargs["input"], (self.key + "\n").encode("ascii"))
        for arguments, _kwargs in self.gpg_calls:
            self.assertNotIn(self.key, " ".join(arguments))
            self.assertNotIn("--passphrase", arguments)
        for _arguments, kwargs in encryption_calls:
            self.assertEqual(kwargs["input"], (self.key + "\n").encode("ascii"))

    def test_gpg_packet_error_category_is_safe_and_does_not_retain_raw_output(self):
        with patch.object(self.backup.subprocess, "run", return_value=types.SimpleNamespace(
                returncode=2,
                stdout=b"gpg: no valid OpenPGP data found for /private/synthetic-secret",
                stderr=b"")) as gpg_run:
            with self.assertRaises(self.backup.BackupInputError) as caught:
                self.backup._assert_gpg_encrypted(self.old_database, "database", self.key)
        self.assertIn("--batch", gpg_run.call_args.args[0])
        self.assertIn("--passphrase-fd", gpg_run.call_args.args[0])
        self.assertEqual(gpg_run.call_args.kwargs["input"],
                         (self.key + "\n").encode("ascii"))
        self.assertEqual(caught.exception.safe_code, "gpg-database-check-exit-2")
        self.assertEqual(caught.exception.safe_category, "no-valid-openpgp-data")
        self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_cli_failure_diagnostics_withhold_native_secret_exceptions(self):
        secret = "synthetic-gpg-or-mariadb-secret"
        for failure in (RuntimeError("traceback leaked " + secret), SystemExit(secret)):
            with self.subTest(failure=type(failure).__name__):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(self.backup, "_native_backup", side_effect=failure):
                    status = self.backup.main([], stdout, stderr)
                self.assertEqual(status, 1)
                self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())
                self.assertIn("sensitive diagnostics were withheld", stderr.getvalue())
                self.assertIn("Existing backup material was preserved", stderr.getvalue())

    def test_unverified_native_backup_does_not_replace_or_delete_old_backups(self):
        self.fail_packet_verification = True
        with self.assertRaises(self.backup.BackupInputError) as caught:
            self._run_adapter()
        self.assertEqual(caught.exception.safe_code, "gpg-database-symmetric-packet-missing")
        self.assertEqual(caught.exception.safe_category, "unclassified")
        self.assertEqual(self.old_database.read_bytes(), self.old_database_bytes)
        self.assertEqual(self.old_config.read_bytes(), self.old_config_bytes)
        self.assertEqual(self.backups.delete_temp_backups, self.original_cleanup)
        self.assertNotIn(("native-cleanup-called",), self.events)
        self.assertFalse(any("20261009_091500" in path.name
                             for path in self.backup_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
