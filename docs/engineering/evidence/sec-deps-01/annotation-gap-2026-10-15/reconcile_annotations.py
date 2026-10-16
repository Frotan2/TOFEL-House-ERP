"""Reconcile the Foundation advisory header (47 groups) with the visible annotations.

Input: fnd_annotations_7c847da.json (check-run annotations, Foundation runtime job,
run 38672481320, head 7c847da). Expected groups: the replay snapshot, which
reproduces the CI header counts (40 npm packages + 7 Python name@version = 47).

Run from this directory:  python3 reconcile_annotations.py
Exit 0 only when visible + hidden == expected and the hidden groups are named.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANNOTATIONS = HERE / "fnd_annotations_7c847da.json"
REPLAY = HERE.parent / "advisory-delta-2026-10-09" / "replay-snapshot.json"

ENTRY_RE = re.compile(r"(?:^|[\s;:]|: )((?:npm|py|fe):(?:@[^/\s@]+/)?[^\s@/]+)@")


def main() -> int:
    annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))["annotations"]
    text = "\n".join(item.get("message", "") for item in annotations)
    hidden_match = re.search(r"\+(\d+) packages not shown", text)
    hidden_count = int(hidden_match.group(1)) if hidden_match else 0

    visible = set()
    for match in ENTRY_RE.finditer(text):
        kind, name = match.group(1).split(":", 1)
        visible.add((kind, name))

    snap = json.loads(REPLAY.read_text(encoding="utf-8"))
    expected = ({("npm", e["package"]) for e in snap["npm_entries"]}
                | {("py", r["package"]) for r in snap["pypi_records"]})
    expected_groups = snap["counts"]["ci_reported_groups"]

    print("expected groups (replay, CI header):", expected_groups, len(expected))
    print("visible in annotations:", len(visible))
    print("header says not shown:", hidden_count)
    print("visible not in expected:", sorted(visible - expected))
    print("expected not visible:", sorted(expected - visible))
    ok = (len(expected) == expected_groups == len(visible) + hidden_count
          and not (visible - expected) and len(expected - visible) == hidden_count)
    print("RECONCILED" if ok else "NOT RECONCILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
