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
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/arena/01a0a942-tofel-house-erp":
        raise SystemExit("Run only on the authorized branch in an ephemeral Actions runner")
    profile = os.environ.get("FOUNDATION_PROFILE", "forensic")
    if profile not in ("forensic", "hardened"):
        raise SystemExit("Unknown validation profile")
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
    report = {"scope": "Pinned foundation and enumerated security/recovery checks; not full Phase 2 acceptance", "profile": profile,
              "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "commit": os.environ["GITHUB_SHA"], "ref": os.environ["GITHUB_REF"],
              "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
              "status": "running", "checks": [], "phase2_gate_passed": False, "security_gate_passed": False,
              "product_implementation_authorized": False, "created_sites": [], "installed_apps": []}
    passwords = [secrets.token_urlsafe(32) for _ in range(8)]
    for value in passwords:
        print(f"::add-mask::{value}", flush=True)
    root_password, admin_password, db_password, test_password, restore_password, recovery_password, upstream_password, upgrade_password = passwords
    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    processes = []
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="never", UV_NATIVE_TLS="true",
               PYTHONUNBUFFERED="1", CI="1")

    def redact(text):
        values = list(passwords)
        captured = lab / "captured-session.json"
        if captured.exists():
            values.extend(json.loads(captured.read_text()).values())
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
        # Inventory resolved dependency trees after their actual asset build.
        # Findings remain REJECT evidence rather than a hidden best-effort scan.
        stack_audit_path = evidence / "stack-dependency-audit.json"
        stack_node_roots = [bench_dir / "apps" / name / "node_modules"
                            for name in ("frappe", "erpnext", "education", "payments", "hrms")]
        stack_node_roots.append(bench_dir / "apps" / "education" / "frontend" / "node_modules")
        stack_audit_command = [bench_dir / "env/bin/python", ROOT / "tools/foundation/audit_stack.py"]
        for root in stack_node_roots:
            stack_audit_command += ["--node-modules", root]
        for name in ("mariadb", "redis"):
            stack_audit_command += ["--image", name + "=" + components[name]["image_digest"]]
        stack_audit_command += ["--output", stack_audit_path]
        diagnostic_failures = []
        try:
            run("hosted-full-stack-dependency-audit", stack_audit_command, timeout=2400)
        except RuntimeError as exc:
            diagnostic_failures = [str(exc)]
        else:
            diagnostic_failures = []
        if not stack_audit_path.exists():
            raise RuntimeError("Full-stack dependency audit produced no result")
        stack_audit = json.loads(stack_audit_path.read_text())
        if stack_audit.get("status") == "error":
            raise RuntimeError("Full-stack dependency audit failed to complete: " + stack_audit.get("error", "unknown error"))
        report["stack_dependency_audit"] = {
            "status": stack_audit["status"], "scope": stack_audit["scope"],
            "python_package_names": stack_audit["python"]["package_names"],
            "python_osv_findings": stack_audit["python"]["osv"]["findings"],
            "node_package_names": stack_audit["node"]["package_names"],
            "node_npm_findings": stack_audit["node"]["finding_summary"],
            "container_status": stack_audit["containers"]["status"],
        }
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
        baseline_failure = None
        if profile == "forensic":
            try:
                run("http-login-and-isolation", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_http.py"], cwd=bench_dir)
            except RuntimeError as exc:
                baseline_failure = str(exc)
            report["baseline_http_failed"] = baseline_failure is not None
        else:
            report["unsafe_baseline"] = {"executed": False, "reason": "Separate hardened acceptance profile; historical failed baseline is preserved in run 34781717183"}
        run("native-user-permission-configuration", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_permissions.py", site], cwd=bench_dir / "sites")
        run("restore-native-permission-configuration", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_permissions.py", restored_site], cwd=bench_dir / "sites")
        extension = ROOT / "apps/foundation_security"
        report["security_extension"] = {"name": "foundation_security", "version": "0.2.1", "repository_commit": os.environ["GITHUB_SHA"],
                                        "file_sha256": {str(p.relative_to(extension)): hashlib.sha256(p.read_bytes()).hexdigest() for p in extension.rglob("*") if p.is_file() and "__pycache__" not in p.parts}}
        # Bench 5.31 expects a local app Git root even with --soft-link. Export
        # only our app into the disposable lab; never initialize/move repo .git.
        export = lab / "extension-source" / "foundation_security"
        shutil.copytree(extension, export, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        run("security-export-git-init", ["git", "init", "--initial-branch", "arena/01a0a942-tofel-house-erp", export])
        run("security-export-git-add", ["git", "-C", export, "add", "."])
        run("security-export-git-snapshot", ["git", "-C", export, "-c", "user.name=Foundation validation", "-c", "user.email=validation@example.test", "commit", "-m", "Exact security app export from " + os.environ["GITHUB_SHA"]])
        bench("get-security-extension", "get-app", "--soft-link", "--skip-assets", str(export))
        for secured_site in (site, restored_site):
            bench("disable-website-html-cache-" + secured_site, "--site", secured_site, "set-config", "disable_website_cache", "1", "--parse")
            bench("install-security-extension-" + secured_site, "--site", secured_site, "install-app", "foundation_security")
        # Editable installs add interpreter-startup path hooks. A Gunicorn HUP
        # forks the old interpreter and is insufficient: fully restart Python
        # processes, retaining their separate pre-extension logs.
        for process, _, _ in processes[:3]:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=30)
        launch("web-backend-secured", [bench_dir / "env/bin/gunicorn", "--bind", "127.0.0.1:8000", "--workers", "2", "frappe.app:application"], bench_dir / "sites")
        worker = launch("worker-secured", [lab / "tools/bin/bench", "worker", "--queue", "short,default,long"], bench_dir)
        scheduler = launch("scheduler-secured", [lab / "tools/bin/bench", "schedule"], bench_dir)
        env["FOUNDATION_BACKGROUND_REPORT"] = str(evidence / "background-secured-result.json")
        run("secured-background-cache-job", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_background.py", site], cwd=bench_dir / "sites")
        env["FOUNDATION_HTTP_REPORT"] = str(evidence / "http-restricted-result.json")
        run("http-isolation-with-native-user-permissions", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_http.py"], cwd=bench_dir)
        # A host-whitelisted reverse proxy serves only public assets statically.
        # Private files always go through Frappe permissions, and client-provided
        # routing headers are overwritten rather than trusted.
        run("nginx-install", ["sudo", "apt-get", "install", "-y", "--no-install-recommends", "nginx"])
        proxy_conf = lab / "nginx.conf"
        proxy_conf.write_text(f"""pid {lab}/nginx.pid;
error_log {lab}/nginx-error.log;
events {{ worker_connections 128; }}
http {{
 include /etc/nginx/mime.types;
 access_log off;
 client_body_temp_path {lab}/nginx-body;
 proxy_temp_path {lab}/nginx-proxy;
 map $host $foundation_site {{ default ''; foundation.localhost foundation.localhost; restore.localhost restore.localhost; recovery.localhost recovery.localhost; }}
 server {{
  listen 127.0.0.1:8080;
  if ($foundation_site = '') {{ return 444; }}
  location /assets/ {{ alias {bench_dir}/sites/assets/; }}
  location / {{
   proxy_set_header Host $http_host;
   proxy_set_header X-Frappe-Site-Name $foundation_site;
   proxy_pass http://127.0.0.1:8000;
  }}
 }}
}}
""")
        run("nginx-config-check", ["nginx", "-t", "-c", proxy_conf])
        launch("public-proxy", ["nginx", "-c", proxy_conf, "-g", "daemon off;"], lab)
        env["FOUNDATION_ISOLATION_REPORT"] = str(evidence / "isolation-result.json")
        try:
            run("expanded-restricted-http-isolation", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_isolation.py"], cwd=bench_dir / "sites")
        except RuntimeError as exc:
            diagnostic_failures.append(str(exc))
        browser_dir = lab / "browser"
        run("browser-package-install", ["npm", "install", "--prefix", browser_dir, "--save-exact", "--ignore-scripts", "playwright@1.58.2"])
        browser_lock = json.loads((browser_dir / "package-lock.json").read_text())
        assert browser_lock["packages"]["node_modules/playwright"]["integrity"] == "sha512-vA30H8Nvkq/cPBnNw4Q8TWz1EJyqgpuinBcHET0YVJVFldr8JDNiU9LaWAE1KqSkRYazuaBhTpB5ZzShOezQ6A=="
        report["browser_test_tool"] = {"playwright": "1.58.2", "lock_sha256": hashlib.sha256((browser_dir / "package-lock.json").read_bytes()).hexdigest()}
        run("chromium-install", [browser_dir / "node_modules/.bin/playwright", "install", "--with-deps", "chromium"])
        shutil.copyfile(ROOT / "tools/foundation/runtime_browser.mjs", browser_dir / "check.mjs")
        env["FOUNDATION_BROWSER_REPORT"] = str(evidence / "browser-result.json")
        try:
            run("browser-native-portal-isolation", ["node", browser_dir / "check.mjs"], timeout=300)
        except RuntimeError as exc:
            diagnostic_failures.append(str(exc))
        # Restore a backup taken AFTER hardening. No User Permission or singleton
        # re-provisioning is run on the recovered site: those must come from SQL.
        env["FOUNDATION_CAPTURED_SESSION"] = str(lab / "captured-session.json")
        run("capture-source-session-before-security-backup", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_recovery_session.py", "capture"])
        run("prepare-native-encrypted-recovery-fixture", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_recovery_secret.py", "prepare", site], cwd=bench_dir / "sites")
        original_config = json.loads((bench_dir / "sites" / site / "site_config.json").read_text())
        assert original_config.get("encryption_key"), "Native encrypted fixture must initialize the site key"
        bench("hardened-backup-with-files", "--site", site, "backup", "--with-files")
        secured_database = max(backup_dir.glob("*-database.sql.gz"), key=lambda p: p.stat().st_mtime_ns)
        secured_private = max(backup_dir.glob("*-private-files.tar"), key=lambda p: p.stat().st_mtime_ns)
        secured_public = max((p for p in backup_dir.glob("*-files.tar") if "-private-files" not in p.name), key=lambda p: p.stat().st_mtime_ns)
        report["hardened_backup"] = {label: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for label, p in (("database",secured_database),("private_files",secured_private),("public_files",secured_public))}
        recovered_site = "recovery.localhost"
        bench("new-hardened-recovery-site", "new-site", recovered_site, "--db-type", "mariadb", "--db-host", "127.0.0.1", "--db-port", "13306",
              "--db-root-password", root_password, "--db-password", recovery_password, "--admin-password", admin_password,
              "--mariadb-user-host-login-scope", "%")
        report["created_sites"].append(recovered_site)
        bench("hardened-restore-with-files", "--site", recovered_site, "restore", str(secured_database), "--db-root-password", root_password,
              "--admin-password", admin_password, "--with-public-files", str(secured_public), "--with-private-files", str(secured_private))
        recovered_config_file = bench_dir / "sites" / recovered_site / "site_config.json"
        recovered_config = json.loads(recovered_config_file.read_text())
        assert recovered_config["db_name"] not in (original_config["db_name"], restore_config["db_name"])
        # Site config is not SQL. Restore the required non-secret policy flag and
        # encryption key explicitly, without copying source database credentials.
        recovered_config["encryption_key"] = original_config["encryption_key"]
        recovered_config["disable_website_cache"] = 1
        recovered_config_file.write_text(json.dumps(recovered_config,indent=2)+"\n")
        recovered_config_file.chmod(0o600)
        bench("hardened-recovery-migrate", "--site", recovered_site, "migrate")
        env["FOUNDATION_RESTORE_REPORT"] = str(evidence / "restore-secured-result.json")
        run("verify-native-encrypted-credential-recovery", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_recovery_secret.py", "verify", recovered_site], cwd=bench_dir / "sites")
        run("hardened-recovery-invariants", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_restore.py", recovered_site], cwd=bench_dir / "sites")
        run("copied-session-revocation-http-proof", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_recovery_session.py", "verify"])
        env["FOUNDATION_PRIMARY_SITE"] = recovered_site
        env["FOUNDATION_ISOLATION_REPORT"] = str(evidence / "isolation-recovered-result.json")
        try:
            run("recovered-security-regressions", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_isolation.py"], cwd=bench_dir / "sites")
        except RuntimeError as exc:
            diagnostic_failures.append(str(exc))
        # Execute upstream security suites unchanged, on their own Frappe-only
        # site. Their test DocTypes/DDL must never touch lifecycle/recovery sites.
        upstream_site = "upstream-tests.localhost"
        bench("upstream-security-test-dependencies", "setup", "requirements", "--dev", "frappe")
        run("upstream-test-python-consistency", [lab / "tools/bin/uv", "pip", "check", "--python", bench_dir / "env/bin/python"])
        test_freeze = run("upstream-test-python-freeze", [lab / "tools/bin/uv", "pip", "freeze", "--python", bench_dir / "env/bin/python"])
        report["upstream_test_dependency_freeze_sha256"] = hashlib.sha256(test_freeze.encode()).hexdigest()
        bench("new-upstream-security-test-site", "new-site", upstream_site, "--db-type", "mariadb", "--db-host", "127.0.0.1", "--db-port", "13306",
              "--db-root-password", root_password, "--db-password", upstream_password, "--admin-password", admin_password,
              "--mariadb-user-host-login-scope", "%")
        report["created_sites"].append(upstream_site)
        bench("upstream-test-allow-tests", "--site", upstream_site, "set-config", "allow_tests", "1", "--parse")
        bench("upstream-test-developer-mode", "--site", upstream_site, "set-config", "developer_mode", "1", "--parse")
        report["upstream_security_suites"] = []
        for doctype in ("user_permission", "docshare"):
            label = "upstream-security-" + doctype
            module = "frappe.core.doctype." + doctype + ".test_" + doctype
            try:
                bench(label, "--site", upstream_site, "run-tests", "--module", module, timeout=600)
                log = (evidence / (label + ".txt")).read_text()
                counts = re.findall(r"Ran (\d+) tests?", log)
                assert counts and int(counts[-1]) > 0, "No executed upstream test count found"
                report["upstream_security_suites"].append({"module":module, "status":"pass", "tests_run":int(counts[-1]), "site":upstream_site})
            except (RuntimeError, AssertionError) as exc:
                report["upstream_security_suites"].append({"module":module, "status":"fail", "reason":str(exc)})
                diagnostic_failures.append(str(exc))
        # Independent remaining gates: failures must not suppress other evidence.
        env.update(FOUNDATION_BENCH_PYTHON=str(bench_dir / "env/bin/python"), FOUNDATION_SITES_DIR=str(bench_dir / "sites"),
                   FOUNDATION_REALTIME_TASK=str(lab / "realtime-task.json"), FOUNDATION_FRONTEND_ROOT=str(bench_dir / "apps/education/frontend"), FOUNDATION_GRAPH_BUILD=str(lab / "graph-assets"), FOUNDATION_AUDIT_REPORT=str(evidence / "frontend-advisories.json"), FOUNDATION_EVENT_HELPER=str(ROOT / "tools/foundation/runtime_publish_event.py"), FOUNDATION_LAB=str(lab),
                   FOUNDATION_ROOT_PASSWORD=root_password, FOUNDATION_UPGRADE_PASSWORD=upgrade_password)
        for label in ("readiness", "realtime", "upgrade", "guardian_browser", "frontend_graph", "restart"):
            env["FOUNDATION_" + label.upper() + "_REPORT"] = str(evidence / (label + "-result.json"))
        # Controlled replacement, not service liveness: queue a native job with
        # the worker stopped, then prove it completes on the replacement worker.
        try:
            targets = [(p, log) for p, _, log in processes if log.stem in ("web-backend-secured", "worker-secured")]
            assert len(targets) == 2 and all(p.poll() is None for p, _ in targets), "Expected live secured web/worker"
            for process, _ in targets:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=30)
            run("restart-prepare-native-queued-job", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_restart_probe.py", "prepare"], cwd=bench_dir / "sites")
            launch("web-backend-restarted", [bench_dir / "env/bin/gunicorn", "--bind", "127.0.0.1:8000", "--workers", "2", "frappe.app:application"], bench_dir / "sites")
            worker = launch("worker-restarted", [lab / "tools/bin/bench", "worker", "--queue", "short,default,long"], bench_dir)
            run("restart-verify-native-state-and-job", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_restart_probe.py", "verify"], cwd=bench_dir / "sites")
            env["FOUNDATION_PRIMARY_SITE"] = site
            env["FOUNDATION_ISOLATION_REPORT"] = str(evidence / "isolation-restarted-result.json")
            run("restarted-security-regressions", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_isolation.py"], cwd=bench_dir / "sites")
            restart = json.loads((evidence / "restart-result.json").read_text())
            restart["isolation"] = json.loads((evidence / "isolation-restarted-result.json").read_text())
            (evidence / "restart-result.json").write_text(json.dumps(restart, indent=2)+"\n")
        except Exception as exc:
            diagnostic_failures.append("Controlled restart: " + str(exc))
            path = evidence / "restart-result.json"
            restart = json.loads(path.read_text()) if path.exists() else {}
            restart.update(status="fail", failure=str(exc))
            path.write_text(json.dumps(restart, indent=2)+"\n")
        for label, command, directory in (
            ("remaining-role-and-operational-checks", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_readiness.py", site], bench_dir / "sites"),
            ("realtime-client-dependency", ["npm", "install", "--prefix", browser_dir, "--save-exact", "--ignore-scripts", "socket.io-client@4.8.1"], lab),
        ):
            try: run(label, command, cwd=directory)
            except RuntimeError as exc: diagnostic_failures.append(str(exc))
        shutil.copyfile(ROOT / "tools/foundation/runtime_guardian_browser.mjs", browser_dir / "guardian.mjs")
        shutil.copyfile(ROOT / "tools/foundation/runtime_realtime.mjs", browser_dir / "realtime.mjs")
        for label, command in (
            ("guardian-browser-authorization", ["node", browser_dir / "guardian.mjs"]),
            ("actual-realtime-authorization", ["node", browser_dir / "realtime.mjs"]),
            ("hosted-frontend-advisory-audit", [bench_dir / "env/bin/python", ROOT / "tools/foundation/audit_frontend.py", bench_dir / "apps/education/frontend/node_modules", "--output", evidence / "frontend-advisories.json"]),
            ("production-frontend-module-graph", ["node", ROOT / "tools/foundation/runtime_frontend_graph.cjs"]),
            ("isolated-controlled-patch-upgrade", [bench_dir / "env/bin/python", ROOT / "tools/foundation/runtime_upgrade.py"]),
        ):
            try: run(label, command, timeout=2400)
            except RuntimeError as exc: diagnostic_failures.append(str(exc))
        continuation = {"run_id": report["run_id"], "commit": report["commit"], "status":"pass", "security_gate_passed":False, "phase2_gate_passed":False}
        for label in ("readiness", "realtime", "upgrade", "guardian_browser", "frontend_graph", "restart"):
            path=evidence / (label + "-result.json")
            if path.exists(): path.write_text(redact(path.read_text()))
            continuation[label] = json.loads(path.read_text()) if path.exists() else {"status":"blocked","reason":"No completed report"}
            if continuation[label]["status"] != "pass": continuation["status"]="fail"
        continuation["resolved_stack_dependencies"] = {
            "status": stack_audit["status"],
            "scope": stack_audit["scope"],
            "python_packages": stack_audit["python"]["package_names"],
            "python_osv_findings": stack_audit["python"]["osv"]["findings"],
            "node_packages": stack_audit["node"]["package_names"],
            "node_npm_findings": stack_audit["node"]["finding_summary"],
            "container_status": stack_audit["containers"]["status"],
        }
        if stack_audit["status"] != "pass": continuation["status"] = "fail"
        audit_path=evidence / "frontend-advisories.json"
        if audit_path.exists():
            audit=json.loads(audit_path.read_text())
            continuation["advisories"]={"status":"fail" if audit["advisories"] else "pass", "source":audit["source"],
                "checked_at_utc":audit["checked_at_utc"], "packages":audit["packages_with_advisories"],
                "findings":audit["advisories"], "scope":"Installed package matches; reachability/remediation separate"}
            if audit["advisories"]: continuation["status"]="fail"
        else:
            continuation["advisories"]={"status":"blocked"}; continuation["status"]="fail"
        (evidence / "continuation-result.json").write_text(redact(json.dumps(continuation,indent=2))+"\n")
        report["restricted_diagnostic_failures"] = diagnostic_failures
        if diagnostic_failures:
            raise RuntimeError("Restricted policy regressions failed: " + "; ".join(diagnostic_failures))
        if baseline_failure:
            raise RuntimeError("Baseline HTTP isolation failed; restricted-configuration results are separate diagnostics: " + baseline_failure)
        report["status"] = "pass"
        report["hardened_profile_passed"] = profile == "hardened"
        report["security_gate_passed"] = False  # broader roles, advisories and remaining security gates still required
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
        for label in ("business", "restore", "background", "http", "http-restricted", "isolation", "browser", "background-secured", "restore-secured", "isolation-recovered"):
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
