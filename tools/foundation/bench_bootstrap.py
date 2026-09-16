"""Shared bootstrap for the independent-recovery probes.

Builds a real, pinned upstream Bench with digest-pinned MariaDB and Redis
containers on a disposable hosted runner. Both halves of the
independent-recovery workflow use it - the source system that produces and then
destroys its own data, and the genuinely separate target system that recovers it
- so the two sides are built identically and neither can drift.

Independence is a property of the *execution environment*, so this module never
tries to simulate it. Each GitHub Actions job runs on a fresh, separate virtual
machine with its own filesystem, its own containers and its own volumes; the two
probes share nothing but an uploaded backup artifact. The identity of each
machine is captured rather than assumed.

Kept deliberately separate from ``runtime_install.py``, whose harness is proven
and must not be destabilised. Nothing here imports or modifies it.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]

# Distinct names so these containers can never collide with, or be mistaken for,
# the ones the runtime and durability probes use.
MARIADB_CONTAINER = "foundation-indep-mariadb"
REDIS_QUEUE_CONTAINER = "foundation-indep-redis-queue"
REDIS_CACHE_CONTAINER = "foundation-indep-redis-cache"
MARIADB_PORT = "13306"
REDIS_QUEUE_PORT = "11379"
REDIS_CACHE_PORT = "12379"


def require_hosted_runner():
    """Fail closed anywhere that is not an ephemeral Actions runner."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run only in an ephemeral Actions runner with real Docker")


def load_components():
    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    components = {c["name"]: c for c in matrix["components"]}
    for name in ("frappe", "erpnext", "mariadb", "redis"):
        if name not in components:
            raise SystemExit("Version matrix is missing " + name)
    for name in ("mariadb", "redis"):
        digest = components[name].get("image_digest") or ""
        if "@sha256:" not in digest:
            raise SystemExit("A reviewed image digest is required for " + name)
    return components


def machine_identity():
    """Recorded, not assumed: proves the two halves ran on different systems.

    Only non-secret host identity is captured. No IP address is published, since
    that would identify runner infrastructure without adding evidence value
    beyond the hostname and boot time.
    """
    identity = {
        "hostname": socket.gethostname(),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_image": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "job": os.environ.get("GITHUB_JOB"),
        "github_action": os.environ.get("GITHUB_ACTION"),
    }
    boot_id = Path("/proc/sys/kernel/random/boot_id")
    if boot_id.exists():
        # A per-boot identifier: two jobs on the same live host would share it.
        identity["kernel_boot_id"] = boot_id.read_text().strip()
    try:
        identity["uptime_seconds"] = round(
            float(Path("/proc/uptime").read_text().split()[0]), 1)
    except (OSError, ValueError, IndexError):
        identity["uptime_seconds"] = None
    try:
        identity["cpu_count"] = os.cpu_count()
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    identity["mem_total_kb"] = int(line.split()[1])
                    break
    except (OSError, ValueError):
        pass
    return identity


class Probe:
    """Records every executed command into a sanitized report.

    Failures raise by default: a probe that cannot do what it claimed must not
    continue and report partial success.
    """

    def __init__(self, report, evidence_dir, lab, secrets_to_mask=()):
        self.report = report
        self.evidence = Path(evidence_dir)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.lab = Path(lab)
        self._secrets = list(secrets_to_mask)

    def mask(self, value):
        if value:
            self._secrets.append(value)
            print("::add-mask::" + value, flush=True)

    def redact(self, text):
        text = text or ""
        for value in self._secrets:
            if value:
                text = text.replace(value, "[REDACTED]")
        return text

    def write(self, path, text):
        Path(path).write_text(self.redact(text))

    def run(self, name, command, *, cwd=None, timeout=1200, allow_failure=False,
            stdin_text=None, quiet=False, env=None):
        command = [str(c) for c in command]
        started = time.monotonic()
        # Extra variables are merged over the inherited environment, never
        # assigned into os.environ: a caller must not be able to change what a
        # later, unrelated command sees.
        environment = dict(os.environ, **env) if env else None
        try:
            result = subprocess.run(command, cwd=str(cwd) if cwd else None,
                                    input=stdin_text, text=True, env=environment,
                                    capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.report["checks"].append(
                {"name": name, "status": "fail", "error_type": type(exc).__name__,
                 "command": [self.redact(c) for c in command]})
            self.report["status"] = "fail"
            raise
        output = self.redact(result.stdout + result.stderr)
        record = {"name": name, "command": [self.redact(c) for c in command],
                  "exit_code": result.returncode,
                  "seconds": round(time.monotonic() - started, 3),
                  "status": "pass" if result.returncode == 0 else "fail"}
        if result.returncode:
            record["output_tail"] = output[-4000:]
        if not quiet or result.returncode:
            self.report["checks"].append(record)
        if result.returncode and not allow_failure:
            self.report["status"] = "fail"
            self.report["failure"] = name + ": exit " + str(result.returncode)
            raise RuntimeError(self.report["failure"] + "\n" + output[-4000:])
        return result.stdout.strip()

    def docker(self, name, *args, **kwargs):
        return self.run(name, ["docker", *args], **kwargs)


def start_services(probe, components, secret_file):
    """Start digest-pinned MariaDB and Redis as real containers."""
    probe.docker("docker-version", "version", "--format",
                 "{{.Client.Version}} {{.Server.Version}}")
    mariadb = components["mariadb"]["image_digest"]
    redis = components["redis"]["image_digest"]
    probe.docker("start-mariadb", "run", "--detach", "--name", MARIADB_CONTAINER,
                 "--mount", f"type=bind,source={secret_file},target=/run/secrets/db-password,readonly",
                 "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password",
                 "--env", "MARIADB_ROOT_HOST=%",
                 "--publish", "127.0.0.1:" + MARIADB_PORT + ":3306",
                 "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
                 "--health-interval", "2s", "--health-retries", "60",
                 mariadb, "--character-set-server=utf8mb4",
                 "--collation-server=utf8mb4_unicode_ci")
    for name, port in ((REDIS_QUEUE_CONTAINER, REDIS_QUEUE_PORT),
                       (REDIS_CACHE_CONTAINER, REDIS_CACHE_PORT)):
        probe.docker("start-" + name, "run", "--detach", "--name", name,
                     "--publish", "127.0.0.1:" + port + ":6379", redis)
    probe.report["services"] = {
        "mariadb": {"image_digest": mariadb,
                    "selected_version": components["mariadb"]["selected_version"]},
        "redis": {"image_digest": redis,
                  "selected_version": components["redis"]["selected_version"]},
    }


def install_mariadb_client(probe):
    """Install MariaDB's own client tools before any dump or restore.

    The runner image ships the Oracle MySQL client, whose ``mysqldump`` queries
    ``information_schema.COLUMN_STATISTICS`` - a table MariaDB does not have - so a
    backup of the pinned MariaDB container fails with error 1109. Frappe resolves
    ``which("mariadb-dump") or which("mysqldump")``, so installing mariadb-client
    makes both the dump and the restore use MariaDB's tools. This is the same step
    the proven installation harness performs before its backup.

    Fail closed here rather than letting a later dump produce a confusing error.
    """
    probe.run("mariadb-client-install",
              ["sudo", "apt-get", "install", "-y", "--no-install-recommends",
               "mariadb-client", "file"])
    version = probe.run("mariadb-client-version", ["mariadb", "--version"])
    dump_binary = shutil.which("mariadb-dump")
    if not dump_binary:
        raise RuntimeError(
            "mariadb-dump is not on PATH after installing mariadb-client; frappe would fall back "
            "to the Oracle mysqldump, which fails against MariaDB with error 1109")
    probe.report["mariadb_client"] = {
        "version": version, "dump_binary": dump_binary,
        "preferred_over_mysqldump_because": ("MariaDB has no information_schema.COLUMN_STATISTICS, "
                                            "which the Oracle client queries unconditionally"),
    }
    return version


def wait_mariadb_healthy(probe, timeout=240):
    deadline = time.monotonic() + timeout
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        state = subprocess.run(
            ["docker", "inspect", MARIADB_CONTAINER, "--format", "{{.State.Health.Status}}"],
            capture_output=True, text=True, check=False, timeout=60).stdout.strip()
        if state == "healthy":
            return {"healthy": True, "polls": polls}
        if state == "unhealthy":
            raise RuntimeError("MariaDB reported unhealthy")
        time.sleep(2)
    raise RuntimeError("MariaDB did not become healthy within " + str(timeout) + "s")


def clone_pinned_sources(probe, components, source_dir, names):
    """Fetch each app at its pinned commit and verify the checked-out revision."""
    revisions = {}
    for name in names:
        component = components[name]
        target = Path(source_dir) / name
        probe.run("clone-" + name, ["git", "init", str(target)])
        probe.run("origin-" + name,
                  ["git", "-C", str(target), "remote", "add", "origin", component["repository"]])
        probe.run("fetch-" + name,
                  ["git", "-C", str(target), "fetch", "--depth", "1", "origin", component["commit"]])
        probe.run("checkout-" + name,
                  ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"])
        head = probe.run("verify-" + name, ["git", "-C", str(target), "rev-parse", "HEAD"])
        if head != component["commit"]:
            raise RuntimeError("Source revision mismatch for " + name)
        revisions[name] = head
    return revisions


def build_bench(probe, components, lab, source_dir, bench_dir, python_bin):
    """bench init plus the pinned toolchain, matching the proven harness."""
    probe.run("bench-tools-venv", [python_bin, "-m", "venv", Path(lab) / "tools"])
    probe.run("bench-tools-install",
              [Path(lab) / "tools/bin/python", "-m", "pip", "install",
               "frappe-bench==5.31.0", "uv==0.11.6"])
    os.environ["PATH"] = str(Path(lab) / "tools/bin") + os.pathsep + os.environ["PATH"]
    (Path(lab) / ".yarnrc").write_text(
        "--install.frozen-lockfile true\n--install.non-interactive true\n")
    probe.run("bench-init", [Path(lab) / "tools/bin/bench", "init", str(bench_dir),
                             "--frappe-path", str(Path(source_dir) / "frappe"),
                             "--python", str(python_bin), "--no-backups",
                             "--skip-redis-config-generation", "--no-procfile",
                             "--skip-assets", "--verbose"], timeout=2400)
    # Only the Redis endpoints are set globally, exactly as the proven harness
    # does. db_host and db_port are deliberately NOT set here: bench stores global
    # values as strings, and new-site already supplies both per site with the
    # correct types.
    for key, value in (("redis_cache", "redis://127.0.0.1:" + REDIS_CACHE_PORT),
                       ("redis_queue", "redis://127.0.0.1:" + REDIS_QUEUE_PORT),
                       ("redis_socketio", "redis://127.0.0.1:" + REDIS_QUEUE_PORT)):
        probe.run("config-" + key,
                  [Path(lab) / "tools/bin/bench", "set-config", "--global", key, value],
                  cwd=bench_dir)
    for name in ("erpnext",):
        probe.run("get-app-" + name,
                  [Path(lab) / "tools/bin/bench", "get-app", "--skip-assets",
                   str(Path(source_dir) / name)],
                  cwd=bench_dir, timeout=2400)
    return Path(lab) / "tools/bin/bench"


def new_site(probe, bench, bench_dir, site, root_password, db_password,
             admin_password, label="new-site"):
    """bench new-site, run from the bench directory as bench itself expects."""
    probe.run(label, [str(bench), "new-site", site, "--db-type", "mariadb",
                      "--db-host", "127.0.0.1", "--db-port", MARIADB_PORT,
                      "--db-root-password", root_password, "--db-password", db_password,
                      "--admin-password", admin_password,
                      "--mariadb-user-host-login-scope", "%"],
              cwd=bench_dir, timeout=1800)


def install_apps(probe, bench, bench_dir, site, apps):
    installed = []
    for app in apps:
        probe.run("install-site-" + app,
                  [str(bench), "--site", site, "install-app", app],
                  cwd=bench_dir, timeout=2400)
        installed.append(app)
    return installed


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup(containers=(), volumes=()):
    """Best-effort teardown; never masks the real result."""
    for container in containers:
        subprocess.run(["docker", "rm", "--force", container],
                       capture_output=True, check=False, timeout=60)
    for volume in volumes:
        subprocess.run(["docker", "volume", "rm", "--force", volume],
                       capture_output=True, check=False, timeout=60)
