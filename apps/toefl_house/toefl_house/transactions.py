"""Bounded whole-command recovery; never commit or replay a caller's prior writes."""
import time
import frappe

MAX_RETRIES = 3
LOCK_WAIT_SECONDS = 5


def run_with_retry(work):
    db = frappe.db
    if db.db_type != "mariadb":
        raise frappe.ValidationError("This synthetic increment requires the qualified MariaDB backend")
    # A deadlock can roll back the WHOLE transaction. Savepoint-only retry is unsafe.
    # Embedded callers with prior writes must fail, not silently lose their work.
    may_retry = not db.transaction_writes and not db._disable_transaction_control
    previous_wait = int(db.sql("SELECT @@SESSION.innodb_lock_wait_timeout")[0][0])
    db.sql("SET SESSION innodb_lock_wait_timeout = %s", (LOCK_WAIT_SECONDS,))
    try:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return work()
            except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
                if not may_retry:
                    raise
                # Native rollback resets transaction state, value cache and callbacks.
                # Re-enter the ENTIRE command with the original payload/key and auth.
                db.rollback()
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        db.sql("SET SESSION innodb_lock_wait_timeout = %s", (previous_wait,))
