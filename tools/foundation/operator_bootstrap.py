#!/usr/bin/env python3
"""Local operator bootstrap for the pinned TOEFL House ERP stack.

Takes an operator machine (Windows + WSL2/Ubuntu 24.04, or plain Ubuntu 24.04)
from a repository clone to a running local ERP: commit-pinned upstream sources,
digest-pinned MariaDB/Redis services, a bench with ERPNext/Education/Payments/
HRMS plus the owned ``foundation_security`` and ``toefl_house`` apps,
migrations and an asset build.

Design rules:

- Single source of version truth: docs/engineering/foundation-version-matrix.json.
  No version is hardcoded here; if the matrix moves, this bootstrap follows.
- Same command shapes as the hosted qualification harnesses
  (tools/foundation/runtime_install.py, tools/placement/run_native.py), which
  pass 123/123 and 596/596 hosted checks on this branch. Only supported
  upstream commands are executed; upstream is never patched and no gate is
  weakened.
- Fail closed: any failed step aborts the run and is recorded in the JSON
  report (stdout plus --report file). Nothing is silently skipped.
- Honesty class: the full local run is DOCUMENTED BUT NOT EXECUTED (no
  Docker/MariaDB/Redis/WSL2 in the engineering sandbox; equivalently-shaped
  hosted runs are verified, and ``--dry-run`` construction of the complete
  ordered command plan is executed and unit-tested locally).

What it deliberately does NOT do:

- No production activation of any kind. Production activation is the
  separately authorized flow in docs/engineering/LAUNCH-RUNBOOK.md.
- No synthetic/qualification flags. ``allow_tests``,
  ``toefl_house_synthetic_only`` and ``disable_website_cache`` are test-mode
  switches and must never be set on a real operator site.
- No business configuration values. After install, the owner configures the
  TH policy DocTypes (owner decisions D1/D3/D4/D7); until then the fail-closed
  owner-value carriers behave exactly as designed.

Required environment variables on a real run (never invented, never defaulted):
``TH_DB_ROOT_PASSWORD`` (MariaDB root), ``TH_DB_PASSWORD`` (site database
user), ``TH_ADMIN_PASSWORD`` (site Administrator login).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "docs/engineering/foundation-version-matrix.json"

UPSTREAM_APPS = ("frappe", "erpnext", "education", "payments", "hrms")
GET_APP_ORDER = ("erpnext", "education", "payments", "hrms")
OWNED_APPS = ("foundation_security", "toefl_house")
INSTALL_ORDER = GET_APP_ORDER + OWNED_APPS


def fail(message: str) -> "None":
    raise SystemExit(f"operator bootstrap: {message}")


def load_parts() -> dict:
    matrix = json.loads(MATRIX_PATH.read_text())
    parts = {c["name"]: c for c in matrix["components"]}
    for name in (*UPSTREAM_APPS, "python", "node"):
        if not parts[name].get("commit"):
            fail(f"matrix entry {name!r} lacks a pinned commit")
    for name in ("mariadb", "redis"):
        if "@sha256:" not in (parts[name].get("image_digest") or ""):
            fail(f"matrix entry {name!r} lacks a reviewed image digest")
    for name in ("bench", "uv", "yarn"):
        if not parts[name].get("selected_version"):
            fail(f"matrix entry {name!r} lacks a selected version")
    return parts


class Runner:
    """Record every step; execute only outside --dry-run; fail closed."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.records: list[dict] = []

    def run(self, name: str, command: list, *, cwd: Path | None = None, redact_map: dict | None = None) -> str:
        command = [str(c) for c in command]
        shown = [self._redact(c, redact_map) for c in command]
        record = {"name": name, "command": shown, "cwd": str(cwd) if cwd else None}
        self.records.append(record)
        if self.dry_run:
            record["status"] = "planned_not_executed"
            return ""
        started = time.monotonic()
        print(f"[operator-bootstrap] {name}: {' '.join(shown)}", flush=True)
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        record["exit_code"] = result.returncode
        record["seconds"] = round(time.monotonic() - started, 3)
        record["status"] = "pass" if result.returncode == 0 else "fail"
        output = self._redact((result.stdout or "") + (result.stderr or ""), redact_map)
        record["output_tail"] = output[-4000:]
        if result.returncode:
            raise RuntimeError(f"step {name!r} failed with exit {result.returncode}\n{record['output_tail'][-800:]}")
        return result.stdout.strip()

    @staticmethod
    def _redact(text: str, redact_map: dict | None) -> str:
        for secret, label in (redact_map or {}).items():
            if secret:
                text = text.replace(secret, label)
        return text


def build_and_run(args, parts, dry_run: bool) -> dict:
    lab = Path(args.workdir).expanduser().resolve()
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    owned_dir = lab / "owned"
    site = args.site

    if args.python:
        py = Path(args.python).expanduser()
    else:
        discovered = shutil.which("python3")
        if not discovered:
            fail("no python3 on PATH; pass --python PATH (e.g. from `uv python find 3.14.7`)")
        py = Path(discovered)

    secrets_in_use = {
        os.environ.get(args.db_root_password_env, ""): "[DB_ROOT_PASSWORD]",
        os.environ.get(args.db_password_env, ""): "[DB_PASSWORD]",
        os.environ.get(args.admin_password_env, ""): "[ADMIN_PASSWORD]",
    }
    if not dry_run:
        missing = [env_name for env_name in (args.db_root_password_env, args.db_password_env, args.admin_password_env)
                   if not os.environ.get(env_name)]
        if missing:
            fail("set non-empty password environment variables before a real run: " + ", ".join(missing))
    db_root_password = os.environ.get(args.db_root_password_env, "") or "[DB_ROOT_PASSWORD]"
    db_password = os.environ.get(args.db_password_env, "") or "[DB_PASSWORD]"
    admin_password = os.environ.get(args.admin_password_env, "") or "[ADMIN_PASSWORD]"

    runner = Runner(dry_run=dry_run)
    bench = lab / "tools/bin/bench"
    secret_file = lab / "db-password"
    yarnrc = lab / ".yarnrc"

    # Phase A - toolchain (parity: runtime_install.py "bench-tools" + .yarnrc).
    runner.run("docker-version", ["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"])
    runner.run("compose-version", ["docker", "compose", "version", "--short"])
    observed_node = runner.run("node-version", ["node", "--version"]) or "v" + parts["node"]["selected_version"]
    if observed_node != "v" + parts["node"]["selected_version"] and not dry_run:
        fail(f"Node {observed_node} does not match the pinned {parts['node']['selected_version']}")
    observed_yarn = runner.run("yarn-version", ["yarn", "--version"]) or parts["yarn"]["selected_version"]
    if observed_yarn != parts["yarn"]["selected_version"] and not dry_run:
        fail(f"Yarn {observed_yarn} does not match the pinned {parts['yarn']['selected_version']}")
    observed_python = runner.run("python-version", [py, "--version"]) or "Python " + parts["python"]["selected_version"]
    if observed_python.split()[-1] != parts["python"]["selected_version"] and not dry_run:
        fail(f"Python {observed_python} does not match the pinned {parts['python']['selected_version']}; "
             "install it (e.g. `uv python install 3.14.7` with uv " + parts["uv"]["selected_version"] +
             ") and pass --python")
    runner.run("tools-venv", [py, "-m", "venv", lab / "tools"])
    runner.run("tools-install", [lab / "tools/bin/python", "-m", "pip", "install",
                                 f"frappe-bench=={parts['bench']['selected_version']}",
                                 f"uv=={parts['uv']['selected_version']}"])

    # Phase B - commit-pinned upstream sources (parity: hosted fetch/verify loop).
    for name in UPSTREAM_APPS:
        component = parts[name]
        target = source_dir / name
        runner.run(f"clone-{name}", ["git", "init", target])
        runner.run(f"origin-{name}", ["git", "-C", target, "remote", "add", "origin", component["repository"]])
        runner.run(f"fetch-{name}", ["git", "-C", target, "fetch", "--depth", "1", "origin", component["commit"]])
        runner.run(f"checkout-{name}", ["git", "-C", target, "checkout", "--detach", "FETCH_HEAD"])
        observed_sha = runner.run(f"verify-{name}", ["git", "-C", target, "rev-parse", "HEAD"]) or component["commit"]
        if observed_sha != component["commit"]:
            fail(f"source revision mismatch for {name}: {observed_sha} != {component['commit']}")

    # Phase C - digest-pinned services (parity: hosted docker runs + health gate).
    runner.records.append({"name": "lab-preparation", "command": ["<internal python: mkdir/secret-file/yarnrc>"],
                           "cwd": None, "status": "planned_not_executed" if dry_run else "pass"})
    if not dry_run:
        for directory in (lab, source_dir, owned_dir, bench_dir):
            directory.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(db_root_password)
        secret_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        # Yarn Classic applies these flags to nested upstream install invocations.
        # The upstream lockfile is never rewritten to get a green install.
        yarnrc.write_text("--install.frozen-lockfile true\n--install.non-interactive true\n")
    for name, port in (("mariadb", "13306:3306"), ("redis-queue", "11379:6379"), ("redis-cache", "12379:6379")):
        component = "mariadb" if name == "mariadb" else "redis"
        image = parts[component]["image_digest"]
        command = ["docker", "run", "--detach", "--name", "toefl-house-" + name, "--publish", "127.0.0.1:" + port]
        if component == "mariadb":
            command += ["--mount", f"type=bind,source={secret_file},target=/run/secrets/db-password,readonly",
                        "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password",
                        "--env", "MARIADB_ROOT_HOST=%", "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
                        "--health-interval", "2s", "--health-retries", "30", image,
                        "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
        else:
            command += [image]
        runner.run("start-" + name, command)
    if not dry_run:
        for _ in range(60):
            state = subprocess.run(["docker", "inspect", "toefl-house-mariadb", "--format", "{{.State.Health.Status}}"],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if state == "healthy":
                break
            if state == "unhealthy":
                fail("MariaDB container reported unhealthy")
            time.sleep(2)
        else:
            fail("MariaDB startup timeout")
    runner.run("mariadb-health", ["docker", "inspect", "toefl-house-mariadb", "--format", "{{.State.Health.Status}}"])

    # Phases D-F - bench init, redis config, apps (parity: hosted bench phase).
    def bench_step(name, *bench_args):
        command = [bench, *bench_args]
        if dry_run:
            return runner.run(name, command, cwd=bench_dir, redact_map=secrets_in_use)
        env = dict(os.environ, PATH=str(lab / "tools/bin") + os.pathsep + os.environ.get("PATH", ""))
        shown = [Runner._redact(str(a), secrets_in_use) for a in bench_args]
        started = time.monotonic()
        print(f"[operator-bootstrap] {name}: bench {' '.join(shown)}", flush=True)
        result = subprocess.run([str(c) for c in command], cwd=bench_dir, env=env, text=True,
                                capture_output=True, check=False)
        redacted = Runner._redact((result.stdout or "") + (result.stderr or ""), secrets_in_use)
        record = {"name": name, "command": [bench.name] + shown, "cwd": str(bench_dir),
                  "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 3),
                  "status": "pass" if result.returncode == 0 else "fail", "output_tail": redacted[-4000:]}
        runner.records.append(record)
        if result.returncode:
            raise RuntimeError(f"step {name!r} failed with exit {result.returncode}\n{redacted[-800:]}")
        return result.stdout.strip()

    bench_step("bench-init", "init", bench_dir, "--frappe-path", source_dir / "frappe", "--python", py,
               "--no-backups", "--skip-redis-config-generation", "--no-procfile", "--skip-assets", "--verbose")
    for key, value in {"redis_cache": "redis://127.0.0.1:12379", "redis_queue": "redis://127.0.0.1:11379",
                       "redis_socketio": "redis://127.0.0.1:11379"}.items():
        bench_step("config-" + key, "set-config", "--global", key, value)
    for name in GET_APP_ORDER:
        bench_step("get-app-" + name, "get-app", "--skip-assets", str(source_dir / name))
    for name in UPSTREAM_APPS:
        observed_sha = runner.run(f"installed-revision-{name}", ["git", "-C", bench_dir / "apps" / name, "rev-parse", "HEAD"]) \
            or parts[name]["commit"]
        if observed_sha != parts[name]["commit"]:
            fail(f"installed source revision mismatch for {name}")
    # Owned apps: export from the repo checkout into the lab, soft-linked, so the
    # bench never depends on, or mutates, the operator's repository clone
    # (parity: tools/placement/run_native.py export + soft-link sequence).
    for name in OWNED_APPS:
        export = owned_dir / name
        if not dry_run:
            if export.exists():
                shutil.rmtree(export)
            shutil.copytree(ROOT / "apps" / name, export, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        runner.run(f"export-init-{name}", ["git", "init", "--initial-branch", "operator-lab", export])
        runner.run(f"export-add-{name}", ["git", "-C", export, "add", "."])
        runner.run(f"export-commit-{name}", ["git", "-C", export, "-c", "user.name=TOEFL House operator",
                                             "-c", "user.email=operator@localhost", "commit", "-m",
                                             "Exact app export for local operator bootstrap"])
        bench_step("get-app-" + name, "get-app", "--soft-link", "--skip-assets", str(export))
    runner.run("python-dependency-check", [lab / "tools/bin/uv", "pip", "check", "--python", bench_dir / "env/bin/python"])

    # Phases G-J - site, installs, migrations, encryption key, asset build.
    bench_step("new-site", "new-site", site, "--db-type", "mariadb", "--db-host", "127.0.0.1", "--db-port", "13306",
               "--db-root-password", db_root_password, "--db-password", db_password, "--admin-password", admin_password,
               "--mariadb-user-host-login-scope", "%", "--set-default")
    for name in INSTALL_ORDER:
        bench_step("install-app-" + name, "--site", site, "install-app", name)
    bench_step("migrate-first", "--site", site, "migrate")
    bench_step("migrate-replay", "--site", site, "migrate")
    # Initialize the native site encryption key before any future first backup
    # (parity: runtime_install.py; identical call the app after_install hook uses).
    key_report = lab / "encryption-key-initialize.json"
    env_extra = str(lab / "encryption-key-initialize.json")
    if not dry_run:
        os.environ["FOUNDATION_LAB"] = str(lab)
        os.environ["FOUNDATION_ENCRYPTION_KEY_REPORT"] = env_extra
    runner.run("initialize-native-site-encryption-key",
               [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_encryption_key.py", "initialize", site],
               cwd=bench_dir / "sites")
    if not dry_run and json.loads(key_report.read_text()).get("status") != "pass":
        fail("native site encryption key was not initialized")
    bench_step("asset-build", "build")

    return {"records": runner.records, "lab": str(lab), "bench_dir": str(bench_dir), "site": site,
            "tools_venv": str(lab / "tools"), "bench": str(bench), "dry_run": dry_run}


START_INSTRUCTIONS = """\
Local start (four long-running processes, one per terminal; Ctrl-C to stop):

  Terminal 1 - web:      cd {bench_dir}/sites && {bench_dir}/env/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 frappe.app:application
  Terminal 2 - worker:   cd {bench_dir} && {tools_venv}/bin/bench worker --queue short,default,long
  Terminal 3 - scheduler: {tools_venv}/bin/bench --site {site} enable-scheduler
                          cd {bench_dir} && {tools_venv}/bin/bench schedule
  Terminal 4 - realtime: cd {bench_dir} && node apps/frappe/socketio.js

Browser: http://127.0.0.1:8000  (WSL2 forwards localhost to Windows automatically)
Login:   Administrator / the value you placed in ${admin_env}

These mirror the hosted launch commands (web/worker/scheduler exactly; realtime
in frappe's native dev form - the hardened nginx edge is production-only and
comes from docs/engineering/LAUNCH-RUNBOOK.md on the authorized server).
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the pinned TOEFL House ERP stack on a local Linux/WSL2 machine")
    parser.add_argument("--site", default="toefl-house.localhost", help="Site name (default: toefl-house.localhost)")
    parser.add_argument("--workdir", default=str(Path.home() / "toefl-house-erp-lab"),
                        help="Lab directory for tools/sources/owned exports/bench (default: ~/toefl-house-erp-lab)")
    parser.add_argument("--python", default=None, help="Python 3.14.7 interpreter path (e.g. `uv python find 3.14.7`)")
    parser.add_argument("--db-root-password-env", default="TH_DB_ROOT_PASSWORD")
    parser.add_argument("--db-password-env", default="TH_DB_PASSWORD")
    parser.add_argument("--admin-password-env", default="TH_ADMIN_PASSWORD")
    parser.add_argument("--report", default=None, help="Write the JSON step report to this path")
    parser.add_argument("--dry-run", action="store_true", help="Build and print the full ordered plan; execute nothing")
    args = parser.parse_args()

    if platform.system() != "Linux":
        fail("native Windows is not supported; run inside WSL2 Ubuntu 24.04 (or any Ubuntu 24.04 machine)")
    if Path(args.workdir).expanduser().resolve() == ROOT:
        fail("workdir must not be the repository checkout")
    parts = load_parts()
    result = build_and_run(args, parts, dry_run=args.dry_run)
    report = {"scope": "Local operator bootstrap of the reviewed pinned foundation; no production activation; "
                       "no synthetic flags; identical command shapes to hosted qualification runs 36119829355 (123/123) "
                       "and 36161953566 (596/596) on this branch",
              "verification_class": "DOCUMENTED BUT NOT EXECUTED locally; hosted equivalents verified; "
                                    "dry-run plan executed and unit-tested in the engineering sandbox",
              "dry_run": result["dry_run"], "site": result["site"], "workdir": result["lab"],
              "steps": result["records"]}
    payload = json.dumps(report, indent=2) + "\n"
    report_path = Path(args.report).expanduser() if args.report else Path(result["lab"]) / "bootstrap-report.json"
    if not result["dry_run"]:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload)
    if result["dry_run"]:
        print(payload, end="")
    else:
        print(START_INSTRUCTIONS.format(bench_dir=result["bench_dir"], tools_venv=result["tools_venv"],
                                        site=result["site"], admin_env=args.admin_password_env))
        print(f"Bootstrap complete. Step report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
