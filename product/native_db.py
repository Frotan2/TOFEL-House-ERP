"""Safe MariaDB client-credential transport for pinned native Frappe calls.

Frappe's MariaDB ``get_command`` helper emits ``--password=...`` for both
native backup dumps and native restore imports. This narrow context manager
keeps Frappe's command selection and database behavior, replacing only that
password argument with a mode-0600 temporary MariaDB option file. The file is
stored in caller-owned ephemeral staging and removed when the native operation
finishes.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


def _option_value(value: str) -> str:
    if (not isinstance(value, str) or not value or not value.isascii()
            or any(ord(char) < 0x20 or ord(char) == 0x7f for char in value)):
        raise RuntimeError("MariaDB credential cannot be transported safely")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _password_argument(args, kwargs):
    if "password" in kwargs:
        return kwargs["password"]
    # Match pinned frappe.database.get_command positional parameters:
    # socket, host, port, user, password, db_name, extra, dump.
    return args[4] if len(args) > 4 else None


@contextmanager
def safe_mariadb_credential_transport(frappe, temporary_dir: Path):
    """Temporarily remove MariaDB passwords from native child argv."""
    import frappe.database

    original = frappe.database.get_command
    credential_files = []

    def get_command(*args, **kwargs):
        binary, raw_arguments, binary_name = original(*args, **kwargs)
        arguments = list(raw_arguments)
        password_args = [arg for arg in arguments
                         if isinstance(arg, str) and arg.startswith("--password")]
        password = _password_argument(args, kwargs)
        if password is None or password == "":
            if password_args:
                raise RuntimeError("Native MariaDB password option could not be safely identified")
            return binary, raw_arguments, binary_name
        if (getattr(frappe.conf, "db_type", None) != "mariadb"
                or not isinstance(password, str)):
            raise RuntimeError("Unsupported native database credential transport")

        expected = f"--password={password}"
        if password_args != [expected]:
            raise RuntimeError("Native MariaDB password option could not be safely identified")

        descriptor, filename = tempfile.mkstemp(
            prefix="toefl-house-mariadb-", suffix=".cnf", dir=temporary_dir)
        credential_path = Path(filename)
        try:
            os.fchmod(descriptor, 0o600)
            option_file = "[client]\npassword = " + _option_value(password) + "\n"
            with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
                descriptor = -1
                stream.write(option_file)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                credential_path.unlink()
            except OSError:
                pass
            raise RuntimeError("Native MariaDB credential setup failed") from None

        credential_files.append(credential_path)
        arguments = [arg for arg in arguments if arg != expected]
        # MariaDB requires --defaults-extra-file to be the first client option.
        arguments.insert(0, f"--defaults-extra-file={credential_path}")
        return binary, arguments, binary_name

    frappe.database.get_command = get_command
    try:
        yield
    finally:
        frappe.database.get_command = original
        for credential_path in credential_files:
            try:
                credential_path.unlink()
            except FileNotFoundError:
                pass
