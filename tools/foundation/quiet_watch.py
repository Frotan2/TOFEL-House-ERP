"""Quiet-period / no-silent-change watch.

The repository's verdicts (pin baseline, provenance, dated assessments, the
readable SEC-DEPS-01 register) are only as trustworthy as the guarantee that
nobody edits them quietly. This tool maintains a sha256 lock over the
protected set; the suite (`tests/foundation/test_quiet_watch.py`) fails when
any protected file differs from the lock.

Deliberate-change ceremony (the ONLY allowed way to change a locked file):
  1. Edit the file.
  2. Regenerate the lock in the SAME commit: `python3 tools/foundation/quiet_watch.py`.
  3. The commit diff (file + lock) is the reviewed change. Anything else is a
     drift alarm: CI goes red and the mismatch is investigated, not "fixed" by
     regenerating the lock blindly.

Usage:
  python3 tools/foundation/quiet_watch.py          # regenerate the lock file
  python3 tools/foundation/quiet_watch.py --check  # exit 1 on any mismatch
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "docs/engineering/quiet-watch-lock.json"

# Files whose silent change would corrupt a verdict. Append-only ledgers,
# per-run outputs, living owner records and app code are deliberately NOT
# here; see docs/engineering/QUIET-WATCH.md for the exclusion reasons.
LOCKED = (
    "docs/engineering/foundation-version-matrix.json",
    "docs/engineering/evidence/phase-2/source-verification.json",
    "docs/engineering/evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json",
    "docs/engineering/evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-19.json",
    "docs/engineering/evidence/sec-deps-01/readable-register-2026-09-19.json",
)


def digest(path):
    h = hashlib.sha256()
    with open(ROOT / path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build():
    return {
        "generated_by": "tools/foundation/quiet_watch.py (do not hand-edit)",
        "files": {rel: digest(rel) for rel in LOCKED},
    }


def write():
    LOCK_PATH.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {LOCK_PATH}")


def check():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if set(lock["files"]) != set(LOCKED):
        return [f"locked set drifted: lock covers {sorted(lock['files'])}"]
    alarms = []
    for rel in LOCKED:
        want = lock["files"][rel]
        got = digest(rel)
        if got != want:
            alarms.append(f"DRIFT: {rel} differs from the quiet-watch lock")
    return alarms


def main(argv):
    if "--check" in argv:
        alarms = check()
        for alarm in alarms:
            print(alarm)
        return 1 if alarms else 0
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
