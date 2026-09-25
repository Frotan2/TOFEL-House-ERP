#!/usr/bin/env python3
"""Verify that every workflow's branch boundary agrees with the canonical pin.

A rotation has to change the same branch name in two places: the ``push:``
filter and ``github.ref ==`` guard of every workflow, and ``ACTIVE_BRANCH`` in
``tools/session_branch.py``. Those two edits have landed in separate commits.
When they do, every gate whose contract asserts the boundary goes red at once
— not because any qualification failed, but because a literal compared unequal.

That is exactly what happened at ``2deba87``, which re-pointed eleven
workflows at the new branch while the pin still named the old one. Four gates
went red and the cause was invisible, because the only record was
``Process completed with exit code 1``.

The rotation itself cannot be automated: advancing the provenance pins needs
the run id of the previous branch's last recorded rejection, which is a
measured fact and must never be invented. What can be automated is the check,
so a rotation author sees the disagreement before pushing and CI names it
precisely if it slips through.

Usage::

    python3 tools/foundation/branch_boundary.py [--root PATH] [--quiet]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BRANCH_FILTER_INLINE = re.compile(r"branches:\s*\[\s*([^\]\s]+)\s*\]")
REF_EQUAL = re.compile(r"github\.ref\s*==\s*'([^']+)'")
REF_EQUAL_DOUBLE = re.compile(r'github\.ref\s*==\s*"([^"]+)"')


def branch_filters(text: str) -> list[str]:
    """Every branch named in a ``push:`` filter, inline or as a YAML list."""
    found = list(BRANCH_FILTER_INLINE.findall(text))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("branches:"):
            continue
        rest = line.split("branches:", 1)[1].strip()
        if rest:
            continue  # inline form, already captured
        for following in lines[index + 1:]:
            stripped = following.strip()
            if stripped.startswith("- "):
                found.append(stripped[2:].strip())
            elif stripped:
                break
    return found


def ref_guards(text: str) -> list[str]:
    """Every literal compared against ``github.ref``."""
    return (REF_EQUAL.findall(text) + REF_EQUAL_DOUBLE.findall(text))


def mismatch(text: str, branch: str, ref: str) -> str | None:
    """None when the workflow agrees with the pin, else a diagnosis."""
    problems = []
    for value in branch_filters(text):
        if value != branch:
            problems.append(f"push filter names {value!r}")
    for value in ref_guards(text):
        if value != ref:
            problems.append(f"github.ref guard names {value!r}")
    if not problems:
        return None
    return (f"expects branch {branch!r} and ref {ref!r} but " + "; ".join(problems))


def workflow_paths(root: Path) -> list[Path]:
    directory = root / ".github" / "workflows"
    return sorted(directory.glob("*.yml"))


def check_tree(root: Path, branch: str, ref: str) -> list[str]:
    """One explicit diagnosis per workflow that disagrees with the pin."""
    report = []
    for path in workflow_paths(root):
        text = path.read_text(encoding="utf-8")
        problem = mismatch(text, branch, ref)
        if problem:
            report.append(f"{path.relative_to(root)}: {problem}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repository root")
    parser.add_argument("--quiet", action="store_true",
                        help="report nothing when every workflow agrees")
    args = parser.parse_args(argv)

    if args.root:
        root = Path(args.root).resolve()
    else:
        root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "tools"))
    from session_branch import ACTIVE_BRANCH, ACTIVE_REF  # noqa: E402

    report = check_tree(root, ACTIVE_BRANCH, ACTIVE_REF)
    if report:
        print(f"{len(report)} workflow(s) disagree with the canonical pin "
              f"{ACTIVE_BRANCH!r} in tools/session_branch.py:", file=sys.stderr)
        for line in report:
            print(f"  {line}", file=sys.stderr)
        print("\nA rotation must change the workflows and the pin in the same "
              "commit; between the two commits every boundary gate is red for "
              "bookkeeping only.", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"all {len(workflow_paths(root))} workflows agree with the "
              f"canonical pin {ACTIVE_BRANCH!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
