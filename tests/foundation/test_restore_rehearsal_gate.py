"""Contract for the database-marker gate of the encrypted restore rehearsal.

Scope: the step "First boot, encrypted backup/restore and guarded site-mode
activation" in .github/workflows/product-image.yml, region from the checkpoint
"database marker setup and encrypted restore" up to "site-mode activation".

The rehearsal proves that a row created after the encrypted backup disappears
after the restore. That absence is only meaningful if the row existed before
the restore, so the gate has two halves:

* the pre-backup marker is created and read back through an explicit
  `RESULT marker_created=True` line, and
* the post-restore check reads `RESULT marker_after_present=False`.

Both probes are plain python3 processes, never `bench console`. Each one runs
from bench/sites, because frappe's database logger opens a CWD-relative
`../logs/` file. Each one fails closed on a non-zero exit or a missing RESULT.

The behaviour tests execute the workflow's own probe bodies against a stub
`frappe` module (in-memory ToDo table in a temporary file). They never import
or contact a real site, database, backup or credential.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-image.yml"
REGION_START = 'checkpoint="database marker setup and encrypted restore"'
REGION_END = 'checkpoint="site-mode activation, refusals and deactivation"'
SITES = "/home/frappe/bench/sites"
YAML_INDENT = " " * 10


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _region() -> str:
    text = _workflow()
    start = text.index(REGION_START)
    return text[start:text.index(REGION_END, start)]


def _heredoc_body(region: str, anchor: str) -> str:
    """Return the python source fed by the `<<'PY'` heredoc on the anchor line."""
    lines = region.splitlines()
    index = next(n for n, line in enumerate(lines) if anchor in line)
    assert "<<'PY'" in lines[index], lines[index]
    body: list[str] = []
    for line in lines[index + 1:]:
        if line == YAML_INDENT + "PY":
            break
        body.append(line[len(YAML_INDENT):] if line.startswith(YAML_INDENT) else line.lstrip())
    else:
        raise AssertionError("heredoc terminator PY not found")
    return "\n".join(body) + "\n"


def _grep_pattern(region: str, target_file: str) -> str:
    """The anchored pattern of the `grep -q '<pattern>' <target_file>` gate."""
    line = next(l for l in region.splitlines() if "grep -q '" in l and target_file in l)
    match = re.search(r"grep -q '(\^[^']+)'", line)
    if not match:
        raise AssertionError(f"no anchored grep on the {target_file} gate: {line!r}")
    return match.group(1)


STUB_FRAPPE = '''\
import json
import os

_PATH = os.environ["STUB_DB"]
_FAIL = os.environ.get("STUB_FAIL", "")


def _rows():
    try:
        with open(_PATH) as handle:
            return set(json.load(handle))
    except FileNotFoundError:
        return set()


def _save(rows):
    with open(_PATH, "w") as handle:
        json.dump(sorted(rows), handle)


def init(site=None, sites_path=None):
    if _FAIL == "init":
        raise RuntimeError("stub init failure")


def connect():
    if _FAIL == "connect":
        raise RuntimeError("stub connect failure")


def destroy():
    pass


class _DB:
    def exists(self, doctype, filters):
        return doctype == "ToDo" and filters.get("description") in _rows()

    def commit(self):
        pass


db = _DB()


class _Doc:
    def __init__(self, values):
        self.values = values

    def insert(self, ignore_permissions=False):
        rows = _rows()
        rows.add(self.values["description"])
        _save(rows)
        return self


def get_doc(values):
    return _Doc(values)
'''


class RestoreGateWiringContract(unittest.TestCase):
    def setUp(self):
        self.region = _region()

    def test_restore_marker_checks_never_use_bench_console(self):
        self.assertNotIn("console", self.region)

    def test_creation_and_absence_are_explicit_result_gates(self):
        self.assertIn("RESULT marker_created=%s", self.region)
        self.assertIn("RESULT marker_after_present=%s", self.region)
        self.assertEqual(_grep_pattern(self.region, "marker-create.txt"), "^RESULT marker_created=True$")
        self.assertEqual(_grep_pattern(self.region, "marker-after.txt"), "^RESULT marker_after_present=False$")

    def test_both_probes_run_from_the_sites_directory(self):
        for anchor in ("marker-create.txt", "marker-after.txt"):
            line = next(l for l in self.region.splitlines() if anchor in l and "docker compose exec" in l)
            self.assertIn("-w /home/frappe/bench/sites", line, anchor)
            body = _heredoc_body(self.region, anchor)
            self.assertLess(body.index('os.chdir("/home/frappe/bench/sites")'), body.index("import frappe"),
                            "chdir must precede the frappe import (logger opens ../logs)")

    def test_each_probe_fails_closed_on_exit_status_or_missing_result(self):
        lines = self.region.splitlines()
        for target, status_var in (("marker-create.txt", "marker_create_rc"),
                                   ("marker-after.txt", "marker_after_rc")):
            index = next(n for n, l in enumerate(lines) if "grep -q '" in l and target in l)
            gate = lines[index]
            self.assertIn(f'"${status_var}" -ne 0 ] ||', gate, target)
            self.assertIn("then", gate, target)
            end = next(n for n in range(index + 1, len(lines)) if lines[n].strip() == "fi")
            self.assertIn("exit 1", "\n".join(lines[index:end]), target)

    def test_order_is_backup_then_creation_then_restore_then_absence(self):
        text = _workflow()
        backup = text.index("/product/backup.py")
        creation = text.index("RESULT marker_created=%s")
        restore = text.index("--entrypoint /home/frappe/bench/env/bin/python web /product/restore.py")
        absence = text.index("RESULT marker_after_present=%s")
        self.assertLess(backup, creation)
        self.assertLess(creation, restore)
        self.assertLess(restore, absence)

    def test_uploaded_file_markers_are_written_before_backup_and_verified_after_restore(self):
        text = _workflow()
        write = text.index('file_marker="ERP-RESTORE-FILE-${GITHUB_RUN_ID}"')
        backup = text.index("/product/backup.py", write)
        self.assertLess(write, backup)
        verify = text.index('test "$restored_file" = "$file_marker"')
        self.assertGreater(verify, text.index("/product/restore.py"))


class RestoreGateBehaviourContract(unittest.TestCase):
    """Run the workflow's own probe bodies against a stub frappe module."""

    @classmethod
    def setUpClass(cls):
        cls.region = _region()
        cls.create_body = _heredoc_body(cls.region, "marker-create.txt")
        cls.after_body = _heredoc_body(cls.region, "marker-after.txt")
        cls.create_gate = _grep_pattern(cls.region, "marker-create.txt")
        cls.after_gate = _grep_pattern(cls.region, "marker-after.txt")
        cls.tmp = Path(tempfile.mkdtemp(prefix="restore-gate-"))
        stub = cls.tmp / "stubs" / "frappe"
        stub.mkdir(parents=True)
        (stub / "__init__.py").write_text(STUB_FRAPPE, encoding="utf-8")
        cls.sites = cls.tmp / "sites"
        cls.sites.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.db_path = self.tmp / f"rows-{self._testMethodName}.json"
        if self.db_path.exists():
            self.db_path.unlink()

    def _run(self, body: str, marker: str, fail: str = "") -> tuple[int, str]:
        script = body.replace(SITES, str(self.sites))
        env = {
            **os.environ,
            "PYTHONPATH": str(self.tmp / "stubs"),
            "STUB_DB": str(self.db_path),
            "STUB_FAIL": fail,
        }
        done = subprocess.run([sys.executable, "-", marker], input=script, text=True,
                              capture_output=True, env=env, cwd=str(self.sites), check=False)
        return done.returncode, done.stdout + done.stderr

    def _gate_passes(self, pattern: str, output: str) -> bool:
        path = self.tmp / "probe-output.txt"
        path.write_text(output, encoding="utf-8")
        result = subprocess.run(["grep", "-q", pattern, str(path)], check=False,
                                stderr=subprocess.DEVNULL)
        return result.returncode == 0

    def _rows(self) -> list[str]:
        return json.loads(self.db_path.read_text(encoding="utf-8")) if self.db_path.exists() else []

    def test_creation_reports_true_and_passes_its_gate(self):
        rc, out = self._run(self.create_body, "ERP-RESTORE-REHEARSAL-1")
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT marker_created=True", out)
        self.assertTrue(self._gate_passes(self.create_gate, out))
        self.assertEqual(self._rows(), ["ERP-RESTORE-REHEARSAL-1"])

    def test_creation_fails_closed_when_frappe_raises(self):
        rc, out = self._run(self.create_body, "ERP-RESTORE-REHEARSAL-2", fail="connect")
        self.assertNotEqual(rc, 0)
        self.assertIn("RESULT marker_created=error RuntimeError: stub connect failure", out)
        self.assertFalse(self._gate_passes(self.create_gate, out))

    def test_absence_passes_when_the_post_backup_row_is_gone(self):
        rc, out = self._run(self.after_body, "ERP-RESTORE-REHEARSAL-3")
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT marker_after_present=False", out)
        self.assertTrue(self._gate_passes(self.after_gate, out))

    def test_absence_fails_when_the_row_survives_the_restore(self):
        self.db_path.write_text(json.dumps(["ERP-RESTORE-REHEARSAL-4"]), encoding="utf-8")
        rc, out = self._run(self.after_body, "ERP-RESTORE-REHEARSAL-4")
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT marker_after_present=True", out)
        self.assertFalse(self._gate_passes(self.after_gate, out))

    def test_absence_fails_closed_when_the_probe_raises(self):
        rc, out = self._run(self.after_body, "ERP-RESTORE-REHEARSAL-5", fail="init")
        self.assertNotEqual(rc, 0)
        self.assertIn("RESULT marker_after_present=error RuntimeError: stub init failure", out)
        self.assertFalse(self._gate_passes(self.after_gate, out))

    def test_prompt_decorated_output_is_rejected(self):
        # The shape that made the earlier `bench console` boolean ambiguous.
        self.assertFalse(self._gate_passes(self.after_gate, "In [2]: False\n"))
        self.assertFalse(self._gate_passes(self.create_gate, "In [1]: True\n"))
        self.assertFalse(self._gate_passes(self.after_gate, ""))


if __name__ == "__main__":
    unittest.main()
