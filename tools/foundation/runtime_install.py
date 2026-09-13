#!/usr/bin/env python3
"""Clean upstream-only Bench installation on a disposable hosted runner.

No product app, schema modification, gateway or production configuration. Executes
supported upstream commands; records failures and stops rather than patching core.
Only sanitized text/JSON evidence is uploaded, never site config, files or backups.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/arena/01a09bf3-tofel-house-erp":
        raise SystemExit("Run only on the authorized branch in an ephemeral Actions runner")
    evidence = ROOT / ".foundation/runtime-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-runtime"
    lab.mkdir(mode=0o700)
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    source_dir.mkdir()
    py = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe/python/bin/python3"
    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    components = {c["name"]: c for c in matrix["components"]}
    report = {"scope": "Clean upstream installation and explicitly executed smoke gates only",
              "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "commit": os.environ["GITHUB_SHA"], "ref": os.environ["GITHUB_REF"],
              "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
              "status": "running", "checks": [], "phase2_gate_passed": False,
              "product_implementation_authorized": False, "created_sites": [], "installed_apps": []}
    passwords = [secrets.token_urlsafe(32) for _ in range(5)]
    for value in passwords:
        print(f"::add-mask::{value}", flush=True)
    root_password, admin_password, db_password, test_password, restore_password = passwords
    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    processes = []
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="never", UV_NATIVE_TLS="true",
               PYTHONUNBUFFERED="1", CI="1")

    def redact(text):
        values = list(passwords)
        for config in bench_dir.glob("sites/*/site_config.json"):
            try:
                data = json.loads(config.read_text())
                values.extend(str(v) for k, v in data.items() if any(x in k.lower() for x in ("password", "secret", "encryption_key")) and v)
            except (ValueError, OSError):
                pass
        for value in values:
            text = text.replace(value, "[REDACTED]")
        return text

    def run(name, command, *, cwd=None, timeout=1200):
        command = [str(c) for c in command]
        started = time.monotonic()
        print("Running", name, flush=True)
        try:
            result = subprocess.run(command, cwd=cwd or lab, env=env, text=True,
                                    capture_output=True, timeout=timeout, check=False)
            output = redact(result.stdout + result.stderr)
            (evidence / (name + ".txt")).write_text(output)
            record = {"name": name, "command": [redact(c) for c in command],
                      "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 3),
                      "status": "pass" if result.returncode == 0 else "fail"}
            report["checks"].append(record)
            if result.returncode:
                report["failure_output_tail"] = output[-10000:]
                raise RuntimeError(f"{name}: exit {result.returncode}")
            return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["checks"].append({"name": name, "status": "fail", "error_type": type(exc).__name__})
            raise

    def bench(name, *args, timeout=1200):
        return run(name, [lab / "tools/bin/bench", *args], cwd=bench_dir, timeout=timeout)

    try:
        report["docker_version"] = run("docker-version", ["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"])
        report["compose_version"] = run("compose-version", ["docker", "compose", "version", "--short"])
        report["python_version"] = run("python-version", [py, "--version"])
        report["node_version"] = run("node-version", ["node", "--version"])
        report["yarn_version"] = run("yarn-version", ["yarn", "--version"])
        if report["node_version"] != "v" + components["node"]["selected_version"]:
            raise RuntimeError("Unexpected Node version")
        run("bench-tools-venv", [py, "-m", "venv", lab / "tools"])
        run("bench-tools-install", [lab / "tools/bin/python", "-m", "pip", "install",
                                    "frappe-bench==5.31.0", "uv==0.11.6"])
        env["PATH"] = str(lab / "tools/bin") + os.pathsep + env["PATH"]
        # Yarn Classic applies these flags to nested upstream install invocations.
        # The upstream lockfile is never rewritten to get a green install.
        (lab / ".yarnrc").write_text("--install.frozen-lockfile true\n--install.non-interactive true\n")
        for name in ("frappe", "erpnext", "education", "payments", "hrms"):
            c = components[name]
            target = source_dir / name
            run("clone-" + name, ["git", "init", str(target)])
            run("origin-" + name, ["git", "-C", target, "remote", "add", "origin", c["repository"]])
            run("fetch-" + name, ["git", "-C", target, "fetch", "--depth", "1", "origin", c["commit"]])
            run("checkout-" + name, ["git", "-C", target, "checkout", "--detach", "FETCH_HEAD"])
            sha = run("verify-" + name, ["git", "-C", target, "rev-parse", "HEAD"])
            if sha != c["commit"]:
                raise RuntimeError("Source revision mismatch for " + name)
        for name, port in (("mariadb", "13306:3306"), ("redis-queue", "11379:6379"), ("redis-cache", "12379:6379")):
            component = "mariadb" if name == "mariadb" else "redis"
            image = components[component]["image_digest"]
            if not image or "@sha256:" not in image:
                raise RuntimeError("A reviewed image digest is required")
            command = ["docker", "run", "--detach", "--name", "foundation-" + name,
                       "--publish", "127.0.0.1:" + port]
            if component == "mariadb":
                command += ["--mount", f"type=bind,source={secret_file},target=/run/secrets/db-password,readonly",
                            "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password",
                            "--env", "MARIADB_ROOT_HOST=%", "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
                            "--health-interval", "2s", "--health-retries", "30", image,
                            "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
            else:
                command += [image]
            run("start-" + name, command)
        for attempt in range(60):
            state = subprocess.run(["docker", "inspect", "foundation-mariadb", "--format", "{{.State.Health.Status}}"],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if state == "healthy":
                break
            if state == "unhealthy":
                raise RuntimeError("MariaDB unhealthy")
            time.sleep(2)
        else:
            raise RuntimeError("MariaDB startup timeout")
        # Redis is supplied by the digest-pinned containers above, not a second
        # host daemon. This upstream option avoids generating host Redis configs;
        # it does not skip Redis service qualification or the connection settings.
        run("bench-init", [lab / "tools/bin/bench", "init", bench_dir, "--frappe-path", source_dir / "frappe",
                           "--python", py, "--no-backups", "--skip-redis-config-generation",
                           "--no-procfile", "--skip-assets", "--verbose"])
        for key, value in {"redis_cache": "redis://127.0.0.1:12379", "redis_queue": "redis://127.0.0.1:11379",
                           "redis_socketio": "redis://127.0.0.1:11379"}.items():
            bench("config-" + key, "set-config", "--global", key, value)
        for name in ("erpnext", "education", "payments", "hrms"):
            bench("get-app-" + name, "get-app", "--skip-assets", str(source_dir / name))
        installed_shas = {}
        for name in ("frappe", "erpnext", "education", "payments", "hrms"):
            path = bench_dir / "apps" / name
            sha = run("installed-revision-" + name, ["git", "-C", path, "rev-parse", "HEAD"])
            if sha != components[name]["commit"]:
                raise RuntimeError("Installed source revision mismatch")
            for relative, expected in components[name].get("source_file_sha256", {}).items():
                if hashlib.sha256((path / relative).read_bytes()).hexdigest() != expected:
                    raise RuntimeError("Upstream input modified during install: " + name + "/" + relative)
            installed_shas[name] = sha
        report["source_revisions"] = installed_shas
        run("python-dependency-check", [lab / "tools/bin/uv", "pip", "check", "--python", bench_dir / "env/bin/python"])
        run("python-resolved-dependencies", [lab / "tools/bin/uv", "pip", "freeze", "--python", bench_dir / "env/bin/python"])
        site = "foundation.localhost"
        bench("new-site", "new-site", site, "--db-type", "mariadb", "--db-host", "127.0.0.1", "--db-port", "13306",
              "--db-root-password", root_password, "--db-password", db_password, "--admin-password", admin_password,
              "--mariadb-user-host-login-scope", "%", "--set-default")
        report["created_sites"].append(site)
        for name in ("erpnext", "education", "payments", "hrms"):
            bench("install-site-" + name, "--site", site, "install-app", name)
            report["installed_apps"].append(name)
        bench("migrate-first", "--site", site, "migrate")
        bench("migrate-replay", "--site", site, "migrate")
        bench("asset-build", "build", timeout=1800)
        report["site_apps"] = bench("site-app-list", "--site", site, "list-apps", "--format", "json")
        env["FOUNDATION_TEST_PASSWORD"] = test_password
        env["FOUNDATION_ADMIN_PASSWORD"] = admin_password
        for label in ("business", "restore", "http", "background"):
            env["FOUNDATION_" + label.upper() + "_REPORT"] = str(evidence / (label + "-result.json"))
        run("business-smoke", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_smoke.py", site], cwd=bench_dir / "sites")
        run("mariadb-client-install", ["sudo", "apt-get", "install", "-y", "--no-install-recommends", "mariadb-client", "file"])
        report["mariadb_client_version"] = run("mariadb-client-version", ["mariadb", "--version"])
        bench("backup-with-files", "--site", site, "backup", "--with-files")
        backup_dir = bench_dir / "sites" / site / "private/backups"
        database = next(backup_dir.glob("*-database.sql.gz"))
        private_files = next(backup_dir.glob("*-private-files.tar"))
        public_files = next(p for p in backup_dir.glob("*-files.tar") if "-private-files" not in p.name)
        report["backup"] = {label: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                            for label, path in (("database", database), ("private_files", private_files), ("public_files", public_files))}
        restored_site = "restore.localhost"
        bench("new-restore-site", "new-site", restored_site, "--db-type", "mariadb", "--db-host", "127.0.0.1", "--db-port", "13306",
              "--db-root-password", root_password, "--db-password", restore_password, "--admin-password", admin_password,
              "--mariadb-user-host-login-scope", "%")
        report["created_sites"].append(restored_site)
        bench("restore-with-files", "--site", restored_site, "restore", str(database), "--db-root-password", root_password,
              "--admin-password", admin_password, "--with-public-files", str(public_files), "--with-private-files", str(private_files))
        original_config = json.loads((bench_dir / "sites" / site / "site_config.json").read_text())
        restore_config_file = bench_dir / "sites" / restored_site / "site_config.json"
        restore_config = json.loads(restore_config_file.read_text())
        assert original_config["db_name"] != restore_config["db_name"], "Restore must use a different database"
        if "encryption_key" in original_config:
            restore_config["encryption_key"] = original_config["encryption_key"]
            restore_config_file.write_text(json.dumps(restore_config, indent=2) + "\n")
            restore_config_file.chmod(0o600)
        report["restore_separate_database"] = True
        report["site_encryption_key_restored"] = "encryption_key" in original_config
        bench("restore-migrate", "--site", restored_site, "migrate")
        run("restore-verification", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_restore.py", restored_site], cwd=bench_dir / "sites")

        def launch(name, command, cwd):
            log_path = lab / (name + ".txt")
            stream = log_path.open("w")
            process = subprocess.Popen([str(c) for c in command], cwd=cwd, env=env,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append((process, stream, log_path))
            return process

        launch("web-backend", [bench_dir / "env/bin/gunicorn", "--bind", "127.0.0.1:8000", "--workers", "2", "frappe.app:application"], bench_dir / "sites")
        worker = launch("worker", [lab / "tools/bin/bench", "worker", "--queue", "short,default,long"], bench_dir)
        bench("enable-scheduler", "--site", site, "enable-scheduler")
        scheduler = launch("scheduler", [lab / "tools/bin/bench", "schedule"], bench_dir)
        socketio = launch("socketio", ["node", bench_dir / "apps/frappe/socketio.js"], bench_dir)
        run("background-cache-job", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_background.py", site], cwd=bench_dir / "sites")
        report["process_liveness"] = {"worker": worker.poll() is None, "scheduler": scheduler.poll() is None, "socketio": socketio.poll() is None}
        if not all(report["process_liveness"].values()):
            raise RuntimeError("One or more background processes exited")
        run("http-login-and-isolation", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_http.py"], cwd=bench_dir)
        report["status"] = "pass"
        report["remaining_gates"] = ["refunds and legacy Fees duplication", "payroll posting", "full staff role matrix",
                                     "full realtime authorization and browser UI", "frontend advisory remediation", "upstream test suites"]
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = redact(str(exc))
        print(report["failure"], file=sys.stderr)
    finally:
        for process, stream, log_path in processes:
            try:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=20)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            finally:
                stream.close()
                (evidence / log_path.name).write_text(redact(log_path.read_text()))
        for label in ("business", "restore", "background", "http"):
            path = evidence / (label + "-result.json")
            if path.exists():
                sanitized = redact(path.read_text())
                path.write_text(sanitized)
                report[label + "_result"] = json.loads(sanitized)
        for name in ("mariadb", "redis-queue", "redis-cache"):
            try:
                subprocess.run(["docker", "rm", "--force", "--volumes", "foundation-" + name],
                               capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                report.setdefault("cleanup_errors", []).append(name)
                report["status"] = "fail"
        secret_file.unlink(missing_ok=True)
        (evidence / "runtime-result.json").write_text(redact(json.dumps(report, indent=2)) + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
