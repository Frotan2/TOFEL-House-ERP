#!/usr/bin/env python3
"""Qualify an ephemeral GitHub-hosted runner, not the ERP or any business gate.

Uses only public downloads and synthetic DB data. No published ports, repository
secrets, private data, upstream edits or paid/self-hosted infrastructure required.
Container tags are candidates: resolved digests are evidence for a subsequent pin.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
# Explicitly authorized hosted session branches: prior session branches
# (foundation workflows + previous placement build) and this session.
AUTHORIZED_REFS = (
    "refs/heads/arena/01a09bf3-tofel-house-erp",
    "refs/heads/arena/01a0a055-tofel-house-erp",
    "refs/heads/arena/01a0a13b-tofel-house-erp",
    "refs/heads/arena/01a0a496-tofel-house-erp",
    "refs/heads/arena/01a0a942-tofel-house-erp",
)


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") not in AUTHORIZED_REFS:
        raise SystemExit("Run only in the explicitly authorized GitHub Actions branch/ephemeral runner")
    evidence = ROOT / ".foundation/runner-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    components = {item["name"]: item for item in matrix["components"]}
    temp = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe"
    temp.mkdir(mode=0o700)
    password_file = temp / "db-password"
    password = secrets.token_urlsafe(32)
    print(f"::add-mask::{password}", flush=True)
    password_file.write_text(password)
    password_file.chmod(0o600)
    report = {
        "scope": "Runner/download/service qualification only; NOT Frappe installation or ERP workflow proof",
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "commit": os.environ["GITHUB_SHA"],
        "ref": os.environ["GITHUB_REF"],
        "runner_image": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "checks": [], "phase2_gate_passed": False, "status": "running",
    }

    def run(name, command, *, input_text=None, env=None, timeout=300):
        started = time.monotonic()
        try:
            result = subprocess.run(command, text=True, capture_output=True, input=input_text,
                                    env=env, timeout=timeout, check=False)
            output = (result.stdout + result.stderr).replace(password, "[REDACTED]")
            (evidence / f"{name}.txt").write_text(output)
            record = {"name": name, "command": command, "exit_code": result.returncode,
                      "seconds": round(time.monotonic() - started, 3),
                      "status": "pass" if result.returncode == 0 else "fail"}
            report["checks"].append(record)
            if result.returncode:
                raise RuntimeError(f"{name} failed with exit {result.returncode}; see artifact")
            print(f"{name}: command succeeded ({record['seconds']} s)", flush=True)
            return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["checks"].append({"name": name, "status": "fail", "error_type": type(exc).__name__})
            raise

    try:
        run("os", ["cat", "/etc/os-release"])
        run("docker-version", ["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"])
        run("compose-version", ["docker", "compose", "version", "--short"])
        # Re-run the previously blocked native dependency download on the hosted runner.
        run("apt-update", ["sudo", "apt-get", "update", "-o", "APT::Update::Error-Mode=any"])
        run("native-libraries", ["sudo", "apt-get", "install", "-y", "--no-install-recommends",
                                 "pkg-config", "libmariadb-dev", "libffi-dev", "libssl-dev",
                                 "libjpeg-dev", "zlib1g-dev", "liblcms2-dev", "libpango-1.0-0",
                                 "libharfbuzz0b", "libpangoft2-1.0-0", "libcups2-dev"], timeout=600)
        runtime = components["python"]["runtime_artifact_candidate"]
        archive = temp / "python.tar.gz"
        url = ("https://github.com/astral-sh/python-build-standalone/releases/download/"
               + runtime["release"] + "/" + runtime["name"].replace("+", "%2B"))
        run("python-download", ["curl", "--fail", "--location", "--retry", "3", "--max-time", "180",
                                "--output", str(archive), url])
        observed_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if "sha256:" + observed_hash != runtime["upstream_digest"]:
            raise RuntimeError("Python artifact checksum mismatch")
        report["python_artifact_sha256"] = observed_hash
        run("python-extract", ["tar", "-xzf", str(archive), "-C", str(temp)])
        version = run("python-version", [str(temp / "python/bin/python3"), "--version"])
        if version != "Python " + components["python"]["selected_version"]:
            raise RuntimeError("Python runtime version mismatch")
        run("python-ssl", [str(temp / "python/bin/python3"), "-c", "import ssl; print(ssl.OPENSSL_VERSION)"])
        report["image_digests"] = {}
        for name, tag in [("mariadb", components["mariadb"]["selected_version"]),
                          ("redis", components["redis"]["selected_version"] + "-alpine")]:
            image = f"{name}:{tag}"
            run(name + "-pull", ["docker", "pull", image], timeout=600)
            digests = run(name + "-digests", ["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"])
            report["image_digests"][name] = json.loads(digests)
        run("mariadb-start", ["docker", "run", "--detach", "--name", "foundation-probe-db",
                              "--mount", f"type=bind,source={password_file},target=/run/secrets/db-password,readonly",
                              "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password",
                              "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
                              "--health-interval", "2s", "--health-retries", "30",
                              "mariadb:" + components["mariadb"]["selected_version"],
                              "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"])
        healthy = False
        for attempt in range(60):
            state = subprocess.run(["docker", "inspect", "foundation-probe-db", "--format", "{{.State.Health.Status}}"],
                                   text=True, capture_output=True, check=True).stdout.strip()
            if state == "healthy":
                healthy = True
                break
            if state == "unhealthy":
                break
            time.sleep(2)
        report["mariadb_health"] = {"healthy": healthy, "last_state": state, "polls": attempt + 1}
        if not healthy:
            raise RuntimeError("MariaDB did not become healthy within the bounded startup window")
        sql = """SELECT VERSION();
SELECT @@character_set_server, @@collation_server;
CREATE DATABASE foundation_probe CHARACTER SET utf8mb4;
CREATE TABLE foundation_probe.probe (id INT PRIMARY KEY) ENGINE=InnoDB;
START TRANSACTION;
INSERT INTO foundation_probe.probe VALUES (1);
ROLLBACK;
SELECT COUNT(*) FROM foundation_probe.probe;
DROP DATABASE foundation_probe;
"""
        db = run("mariadb-transaction", ["docker", "exec", "--interactive", "--env", "MYSQL_PWD",
                                       "foundation-probe-db", "mariadb", "--user=root", "--batch", "--skip-column-names"],
                 input_text=sql, env={**os.environ, "MYSQL_PWD": password})
        lines = db.splitlines()
        if not lines[0].startswith(components["mariadb"]["selected_version"] + "-") or lines[-1] != "0":
            raise RuntimeError("MariaDB version/rollback result mismatch")
        if lines[1] != "utf8mb4\tutf8mb4_unicode_ci":
            raise RuntimeError("MariaDB character set/collation mismatch")
        image = "redis:" + components["redis"]["selected_version"] + "-alpine"
        run("redis-start", ["docker", "run", "--detach", "--name", "foundation-probe-redis", image])
        pong = run("redis-ping", ["docker", "exec", "foundation-probe-redis", "redis-cli", "PING"])
        if pong != "PONG":
            raise RuntimeError("Redis did not return PONG")
        version = run("redis-version", ["docker", "exec", "foundation-probe-redis", "redis-server", "--version"])
        if "v=" + components["redis"]["selected_version"] + " " not in version:
            raise RuntimeError("Redis version mismatch")
        report["status"] = "pass"
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = str(exc).replace(password, "[REDACTED]")
        print(report["failure"], file=sys.stderr)
    finally:
        for container in ("foundation-probe-db", "foundation-probe-redis"):
            try:
                subprocess.run(["docker", "rm", "--force", "--volumes", container],
                               capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                report.setdefault("cleanup_errors", []).append(type(cleanup_error).__name__)
                report["status"] = "fail"
        password_file.unlink(missing_ok=True)
        (evidence / "runner-result.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
