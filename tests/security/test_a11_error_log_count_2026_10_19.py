"""A11: the historical Error Log count is read-only and prints counts only (2026-10-19).

The statement is run on in-memory SQLite with synthetic rows. SQLite is not MariaDB, so the test
checks the logic and the read-only shape. It does not prove MariaDB syntax; the owner or a restored
site run does that.
"""
from pathlib import Path
import re
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "docs/engineering/evidence/microsoft-auth-review-2026-10-15/A11-error-log-count-2026-10-19.sql"
FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|TRUNCATE|CREATE|GRANT|CALL|LOAD|INTO|RENAME|SET)\b", re.I)


def _statement():
    lines = [line for line in SQL.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


class ErrorLogCountIsReadOnlyTests(unittest.TestCase):
    def test_single_select_statement_with_no_write_keywords(self):
        stmt = _statement()
        self.assertTrue(stmt.upper().startswith("SELECT"), stmt[:40])
        self.assertEqual(stmt.count(";"), 1, "exactly one statement")
        self.assertFalse(FORBIDDEN.search(stmt), FORBIDDEN.search(stmt))

    def test_select_list_returns_no_raw_row_content(self):
        for line in _statement().splitlines():
            self.assertFalse(re.match(r"^\s*`?(method|error|metadata)`?\s*,?\s*$", line), line)

    def test_counts_on_synthetic_rows(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE tabError Log (method TEXT, error TEXT, metadata TEXT, creation TEXT)".replace("Error Log", "Error_Log"))
        rows = [
            # callback row, code and state in metadata, before the 2026-10-18 cut-off
            ("/api/method/toefl_house.social_login.login_via_office365", "tb", '{"code": "SYN-1", "state": "SYN-2"}', "2026-10-17 09:00:00"),
            # callback row, traceback mentions the function, no code/state
            ("/api/method/other", "login_via_office365 failed", '{"path": "x"}', "2026-10-19 10:00:00"),
            # unrelated row with a code key
            ("/api/method/unrelated", "tb", '{"code": "SYN-3", "state": "SYN-4"}', "2026-10-19 11:00:00"),
        ]
        db.executemany("INSERT INTO tabError_Log VALUES (?,?,?,?)", rows)
        sql = _statement().replace("`tabError Log`", "`tabError_Log`")
        row = db.execute(sql).fetchone()
        names = [d[0] for d in db.execute(sql).description]
        result = dict(zip(names, row))
        self.assertEqual(result["total_error_log_rows"], 3)
        self.assertEqual(result["office365_callback_rows"], 2)
        self.assertEqual(result["callback_rows_possibly_holding_code_or_state"], 1)
        self.assertEqual(result["rows_with_code_and_state_keys_any_method"], 2)
        self.assertEqual(result["callback_rows_since_2026_10_18"], 1)
        self.assertEqual(result["first_callback_row_date"], "2026-10-17 09:00:00")
        self.assertEqual(result["last_callback_row_date"], "2026-10-19 10:00:00")


if __name__ == "__main__":
    unittest.main()
