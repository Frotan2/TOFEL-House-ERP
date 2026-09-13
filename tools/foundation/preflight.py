#!/usr/bin/env python3
"""Read-only toolchain checks. A pass is NOT ERP runtime/compatibility evidence.

Run from a host or developer container, never against an untrusted Docker daemon.
No package installation, DB connections, credentials, or network probes are made.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/engineering/foundation-version-matrix.json"


def inspect_command(command: list[str], expected: str | None = None) -> dict:
    executable = shutil.which(command[0])
    if not executable:
        return {"status": "missing", "expected": expected, "observed": None}
    try:
        result = subprocess.run(
            [executable, *command[1:]], capture_output=True, text=True, timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "error", "expected": expected, "observed": None,
                "error_type": type(error).__name__}
    # Keep version only; arbitrary stderr, Docker context, and environment can be sensitive.
    match = re.search(r"(?<![\d.])(\d+\.\d+\.\d+)(?![\d.])", result.stdout + result.stderr)
    observed = match.group(1) if match else None
    status = "pass" if result.returncode == 0 and observed else "error"
    if status == "pass" and expected and observed != expected:
        status = "version_mismatch"
    return {"status": status, "expected": expected, "observed": observed,
            "exit_code": result.returncode}


def collect(python: str, matrix: dict) -> dict:
    versions = {row["name"]: row["selected_version"] for row in matrix["components"]}
    commands = {
        "python": [python, "--version"],
        "node": ["node", "--version"],
        "yarn": ["yarn", "--version"],
        "bench": ["bench", "--version"],
        "mariadb": ["mariadbd", "--version"],
        "redis": ["redis-server", "--version"],
    }
    checks = {name: inspect_command(command, versions[name])
              for name, command in commands.items()}
    checks["docker_server"] = inspect_command(["docker", "version", "--format", "{{.Server.Version}}"])
    checks["docker_compose"] = inspect_command(["docker", "compose", "version", "--short"])
    native = all(checks[name]["status"] == "pass" for name in commands)
    docker = all(checks[name]["status"] == "pass" for name in ("docker_server", "docker_compose"))
    return {
        "schema_version": 1,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "Toolchain availability only; no site, workflow, or compatibility test",
        "checks": checks,
        "native_tool_versions_match": native,
        "docker_daemon_and_compose_available": docker,
        "foundation_runtime_validated": False,
        "warning": "Neither tool availability nor exact version matching proves app installation, native libraries, image availability, or runtime behavior.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="python3", help="Candidate Python executable")
    parser.add_argument("--method", choices=("native", "docker"), default="native")
    parser.add_argument("--output", type=Path, help="Write JSON evidence; prefer an ignored artifact directory")
    args = parser.parse_args()
    report = collect(args.python, json.loads(MATRIX.read_text()))
    report["requested_method"] = args.method
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    ready = report["native_tool_versions_match"] if args.method == "native" else report["docker_daemon_and_compose_available"]
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
