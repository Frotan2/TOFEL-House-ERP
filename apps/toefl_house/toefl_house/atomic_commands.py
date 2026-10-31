"""Command-local rollback, including the operation receipt and audit event.

Used for multi-document financial commands. A failed attempt must remove its
own native postings even when an embedded caller catches the exception and
continues its transaction. Whole-transaction deadlock retry remains bounded
by the existing executor and is forbidden when the caller has prior writes.
"""
import secrets

import frappe

from toefl_house.api import _execute_once
from toefl_house.transactions import run_with_retry


def execute_atomic(kind, request_key, payload, work):
    def attempt():
        point = "th_atomic_" + secrets.token_hex(12)
        frappe.db.savepoint(point)
        try:
            return _execute_once(kind, request_key, payload, work)
        except frappe.QueryDeadlockError:
            # InnoDB already discarded the complete transaction. The retry
            # executor decides whether there were prior caller writes.
            raise
        except BaseException as original:
            try:
                frappe.db.rollback(save_point=point)
            except Exception as rollback_error:
                # innodb_rollback_on_timeout may discard the whole transaction,
                # including its savepoints. Keep the original timeout eligible
                # for the existing whole-command retry in that exact case.
                missing = bool(rollback_error.args and rollback_error.args[0] == 1305)
                if not (isinstance(original, frappe.QueryTimeoutError) and missing):
                    raise RuntimeError("Atomic command rollback could not be verified") from rollback_error
            raise

    return run_with_retry(attempt)
