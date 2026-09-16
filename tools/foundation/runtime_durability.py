"""Real MariaDB and Redis restart, crash-recovery and volume-persistence proof.

Closes the durability gap recorded in the D8 matrix: previously the only
executed evidence was container *startup* plus a health poll, a
START TRANSACTION/ROLLBACK count-0 query and a Redis PING/PONG. No MariaDB or
Redis restart, no crash or volume-loss probe, and no AOF/RDB persistence
verification had ever been executed. The existing restart probe covers
Gunicorn/RQ process replacement only and explicitly excludes Redis and database
restart.

This probe uses the real pinned upstream images from
docs/engineering/foundation-version-matrix.json, running as actual containers on
a disposable hosted runner. Nothing is mocked, simulated or substituted:

1. Graceful restart - ``docker restart`` of a live server holding committed and
   uncommitted state.
2. Crash - ``docker kill --signal=KILL``, the closest supported analogue of
   power loss, then a cold start exercising InnoDB crash recovery.
3. Container destruction - ``docker rm --force`` and recreation of a brand new
   container from the *same* named volume, which is what proves the data is
   durable in the volume rather than merely in the container's own writable
   layer.

Persistence is configured explicitly rather than left to image defaults:
InnoDB ``innodb_flush_log_at_trx_commit=1`` with ``sync_binlog=1`` and a binary
log for MariaDB; ``appendonly yes`` with ``appendfsync always`` plus an RDB
snapshot policy for Redis. The effective settings are read back from the running
servers and recorded, so the evidence shows the configuration that was actually
in force.

An open, uncommitted transaction is held across every scenario by a dedicated
client session. Its rows must never become visible, and must be gone after crash
recovery; committed rows must survive byte-identically. Recording exact
before/after counts and order-independent CRC32 checksums is what makes this
reproducible rather than anecdotal.

Both images are pinned by index digest. The resolved platform digest is recorded
alongside it, because ``docker image inspect`` reports the platform-specific
manifest digest while the matrix pins the multi-architecture index digest; these
legitimately differ and are not a mismatch.

All data is synthetic. The generated root password is masked with
``::add-mask::``, is supplied through a 0600 bind-mounted secret file, and never
appears in the report.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]

MARIADB_CONTAINER = "foundation-durability-mariadb"
REDIS_CONTAINER = "foundation-durability-redis"
MARIADB_VOLUME = "foundation-durability-mariadb-data"
REDIS_VOLUME = "foundation-durability-redis-data"
DATABASE = "durability"
TABLE = "durable_state"
REDIS_KEY = "durability:committed"
REDIS_QUEUE = "durability:queue"

# Explicit durability settings, not image defaults.
MARIADB_SETTINGS = [
    "--character-set-server=utf8mb4",
    "--collation-server=utf8mb4_unicode_ci",
    "--innodb-flush-log-at-trx-commit=1",
    "--sync-binlog=1",
    "--log-bin=mariadb-bin",
    "--innodb-buffer-pool-size=64M",
]
REDIS_SETTINGS = [
    "--appendonly", "yes",
    "--appendfsync", "always",
    "--save", "900", "1",
    "--maxmemory", "128mb",
]
COMMITTED_ROWS = 25


def extract_innodb_section(text, header):
    """Extract one section from `SHOW ENGINE INNODB STATUS` output.

    A section is a rule of dashes, the header, another rule of dashes, then body
    lines up to the next rule. Batch-mode MySQL escapes embedded newlines as a
    literal backslash-n, so callers must unescape first. Kept at module level so
    it can be executed against a realistic fixture instead of only ever being
    exercised on a hosted runner.
    """
    lines = (text or "").splitlines()

    def is_rule(value):
        value = value.strip()
        return bool(value) and set(value) == {"-"}

    for i, line in enumerate(lines):
        if not is_rule(line) or i + 2 >= len(lines):
            continue
        if lines[i + 1].strip() != header or not is_rule(lines[i + 2]):
            continue
        out = []
        for body in lines[i + 3:]:
            if is_rule(body):
                break
            stripped = body.strip()
            if stripped:
                out.append(stripped[:200])
            if len(out) >= 20:
                break
        return out
    return []


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run only in an ephemeral Actions runner with real Docker")

    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    components = {c["name"]: c for c in matrix["components"]}
    for name in ("mariadb", "redis"):
        digest = components[name]["image_digest"]
        if not digest or "@sha256:" not in digest:
            raise SystemExit("A reviewed image digest is required for " + name)

    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-durability"
    lab.mkdir(mode=0o700)
    evidence = ROOT / ".foundation/durability-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    report_path = evidence / "durability-result.json"

    root_password = secrets.token_urlsafe(32)
    print("::add-mask::" + root_password, flush=True)
    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)

    env = dict(os.environ, MYSQL_PWD=root_password)
    report = {
        "scope": ("Real container MariaDB/Redis restart, crash-recovery and named-volume "
                  "persistence; synthetic data only, not application workflow proof"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "runner_image": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "pinned_images": {
            name: {
                "index_digest": components[name]["image_digest"],
                "selected_version": components[name]["selected_version"],
            } for name in ("mariadb", "redis")
        },
    }

    def redact(text):
        return (text or "").replace(root_password, "[REDACTED]")

    def write():
        report_path.write_text(redact(json.dumps(report, indent=2)) + "\n")

    def run(name, command, *, stdin_text=None, timeout=300, allow_failure=False, quiet=False):
        command = [str(c) for c in command]
        started = time.monotonic()
        try:
            result = subprocess.run(command, input=stdin_text, text=True, env=env,
                                    capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["checks"].append({"name": name, "status": "fail",
                                     "error_type": type(exc).__name__,
                                     "command": [redact(c) for c in command]})
            report["status"] = "fail"
            write()
            raise
        output = redact(result.stdout + result.stderr)
        record = {"name": name, "command": [redact(c) for c in command],
                  "exit_code": result.returncode,
                  "seconds": round(time.monotonic() - started, 3),
                  "status": "pass" if result.returncode == 0 else "fail"}
        if result.returncode:
            record["output_tail"] = output[-2000:]
        # Individual queries are not recorded as separate checks: the captured
        # state objects are the evidence, and recording every query would bury
        # the container operations that actually matter. Failures still raise.
        if not quiet or result.returncode:
            report["checks"].append(record)
            write()
        if result.returncode and not allow_failure:
            report["status"] = "fail"
            report["failure"] = name + ": exit " + str(result.returncode)
            write()
            raise RuntimeError(report["failure"] + "\n" + output[-2000:])
        return result.stdout.strip()

    def sql(statement, *, database=DATABASE, timeout=120):
        return run("mariadb-query", [
            "docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
            "mariadb", "--user=root", "--batch", "--skip-column-names", database,
        ], stdin_text=statement, timeout=timeout, quiet=True)

    def redis_cli(*args, timeout=60):
        return run("redis-cli", ["docker", "exec", REDIS_CONTAINER, "redis-cli", *args],
                   timeout=timeout, quiet=True)

    def container_state(name):
        raw = subprocess.run(
            ["docker", "inspect", name, "--format",
             "{{.Id}} {{.State.Status}} {{.State.Health.Status}}"
             " {{.State.StartedAt}} {{.RestartCount}}"],
            capture_output=True, text=True, env=env, check=False, timeout=60)
        parts = raw.stdout.split()
        return {
            "container_id": parts[0][:12] if parts else "unknown",
            "status": parts[1] if len(parts) > 1 else "unknown",
            "health": parts[2] if len(parts) > 2 else "unknown",
            "started_at": parts[3] if len(parts) > 3 else "unknown",
            "restart_count": parts[4] if len(parts) > 4 else "unknown",
        }

    def wait_healthy(name, timeout=240):
        deadline = time.monotonic() + timeout
        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            state = container_state(name)
            if state["health"] == "healthy":
                return {"healthy": True, "polls": polls, **state}
            if state["health"] == "unhealthy":
                raise RuntimeError(name + " became unhealthy: " + json.dumps(state))
            time.sleep(2)
        raise RuntimeError(name + " did not become healthy within " + str(timeout) + "s")

    def mariadb_command(extra_settings=None):
        return ["docker", "run", "--detach", "--name", MARIADB_CONTAINER,
                "--volume", MARIADB_VOLUME + ":/var/lib/mysql",
                "--mount", f"type=bind,source={secret_file},target=/run/secrets/db-password,readonly",
                "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password",
                "--env", "MARIADB_ROOT_HOST=%",
                "--health-cmd", "healthcheck.sh --connect --innodb_initialized",
                "--health-interval", "2s", "--health-retries", "90",
                components["mariadb"]["image_digest"],
                *(MARIADB_SETTINGS + (extra_settings or []))]

    def redis_command():
        return ["docker", "run", "--detach", "--name", REDIS_CONTAINER,
                "--volume", REDIS_VOLUME + ":/data",
                "--health-cmd", "redis-cli ping | grep -q PONG",
                "--health-interval", "2s", "--health-retries", "90",
                components["redis"]["image_digest"], *REDIS_SETTINGS]

    def mariadb_state():
        """Exact committed-state fingerprint plus effective durability settings."""
        checksum = sql(
            f"SELECT COUNT(*), COALESCE(SUM(CRC32(CONCAT_WS('|', id, payload))), 0) FROM {TABLE};")
        count, crc = (checksum.split("\t") + ["0"])[:2]
        return {
            "committed_row_count": int(count),
            "payload_crc32_sum": int(crc),
            "innodb_flush_log_at_trx_commit": sql("SELECT @@innodb_flush_log_at_trx_commit;"),
            "sync_binlog": sql("SELECT @@sync_binlog;"),
            "log_bin": sql("SELECT @@log_bin;"),
            # Must be 0: any other value would make crash recovery skip work and
            # invalidate the whole scenario.
            "innodb_force_recovery": sql("SELECT @@innodb_force_recovery;"),
            "version": sql("SELECT VERSION();"),
            "binlog_files": [r for r in sql("SHOW BINARY LOGS;").splitlines() if r],
            "uncommitted_visible": sql(
                f"SELECT COUNT(*) FROM {TABLE} WHERE id LIKE 'uncommitted-%';"),
        }

    def parse_info(text):
        parsed = {}
        for line in (text or "").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                key, _, value = line.partition(":")
                parsed[key.strip()] = value.strip()
        return parsed

    def redis_state():
        parsed = parse_info(redis_cli("INFO", "persistence"))
        server = parse_info(redis_cli("INFO", "server"))
        return {
            "dbsize": int(redis_cli("DBSIZE")),
            "committed_value_sha256": hashlib.sha256(
                redis_cli("GET", REDIS_KEY).encode()).hexdigest(),
            "queue_length": int(redis_cli("LLEN", REDIS_QUEUE)),
            "queue_head_sha256": hashlib.sha256(
                redis_cli("LRANGE", REDIS_QUEUE, "0", "-1").encode()).hexdigest(),
            "aof_enabled": parsed.get("aof_enabled"),
            "aof_last_write_status": parsed.get("aof_last_write_status"),
            "aof_current_size": parsed.get("aof_current_size"),
            "rdb_last_bgsave_status": parsed.get("rdb_last_bgsave_status"),
            "loading": parsed.get("loading"),
            "redis_version": server.get("redis_version"),
            "redis_mode": server.get("redis_mode"),
        }

    def resolved_digests():
        return {
            name: json.loads(subprocess.run(
                ["docker", "image", "inspect", components[name]["image_digest"],
                 "--format", "{{json .RepoDigests}}"],
                capture_output=True, text=True, env=env, check=True,
                timeout=60).stdout)
            for name in ("mariadb", "redis")
        }

    holder = None
    try:
        report["docker_version"] = run(
            "docker-version", ["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"])
        for name, volume in (("mariadb", MARIADB_VOLUME), ("redis", REDIS_VOLUME)):
            run("create-" + name + "-volume", ["docker", "volume", "create", volume])
        report["named_volumes"] = {"mariadb": MARIADB_VOLUME, "redis": REDIS_VOLUME}

        run("start-mariadb", mariadb_command())
        run("start-redis", redis_command())
        report["mariadb_startup"] = wait_healthy(MARIADB_CONTAINER)
        report["redis_startup"] = wait_healthy(REDIS_CONTAINER)
        report["resolved_platform_digests"] = resolved_digests()

        # Real schema and committed synthetic data, plus an order-independent
        # checksum so survival can be compared exactly rather than approximately.
        sql("CREATE DATABASE IF NOT EXISTS `" + DATABASE + "`"
            " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;", database="mysql")
        sql(f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            "id VARCHAR(64) PRIMARY KEY, payload VARCHAR(255) NOT NULL,"
            " created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)) ENGINE=InnoDB;")
        inserts = "".join(
            f"INSERT INTO {TABLE} (id, payload) VALUES ('row-{i:03d}',"
            f" 'synthetic-durable-payload-{i:03d}');\n" for i in range(COMMITTED_ROWS))
        sql("START TRANSACTION;\n" + inserts + "COMMIT;")
        redis_cli("SET", REDIS_KEY, "synthetic-committed-value")
        for i in range(COMMITTED_ROWS):
            redis_cli("RPUSH", REDIS_QUEUE, f"synthetic-queue-item-{i:03d}")
        # Force the persistence files to exist before any disruption, so a later
        # survival result cannot be explained by an empty dataset.
        redis_cli("BGREWRITEAOF")
        time.sleep(3)

        # Hold an open, uncommitted transaction in its own session for the whole
        # scenario. Its rows must never be visible and must not survive a crash.
        holder = subprocess.Popen(
            ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
             "mariadb", "--user=root", "--batch", "--skip-column-names", DATABASE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env)
        holder.stdin.write("START TRANSACTION;\n"
                           f"INSERT INTO {TABLE} (id, payload) VALUES"
                           " ('uncommitted-crash-probe', 'synthetic-uncommitted');\n")
        holder.stdin.flush()
        time.sleep(3)

        report["pre_state"] = {"mariadb": mariadb_state(), "redis": redis_state()}
        report["pre_state"]["containers"] = {
            "mariadb": container_state(MARIADB_CONTAINER),
            "redis": container_state(REDIS_CONTAINER),
        }
        pre = report["pre_state"]
        if pre["mariadb"]["committed_row_count"] != COMMITTED_ROWS:
            raise RuntimeError("Committed rows were not present before the scenarios began")
        if pre["mariadb"]["uncommitted_visible"] != "0":
            raise RuntimeError("Uncommitted transaction was visible to another session")
        if pre["redis"]["dbsize"] < 2 or pre["redis"]["queue_length"] != COMMITTED_ROWS:
            raise RuntimeError("Redis fixture was not present before the scenarios began")
        if pre["redis"]["aof_enabled"] != "1":
            raise RuntimeError("Redis AOF persistence was not actually enabled")
        if pre["mariadb"]["innodb_flush_log_at_trx_commit"] != "1":
            raise RuntimeError("InnoDB was not configured for full durability")
        if pre["mariadb"]["innodb_force_recovery"] != "0":
            raise RuntimeError("innodb_force_recovery was not 0, so crash recovery would be bypassed")

        def assert_survived(label, state):
            if state["mariadb"]["committed_row_count"] != COMMITTED_ROWS:
                raise RuntimeError(label + ": committed MariaDB rows did not survive")
            if state["mariadb"]["payload_crc32_sum"] != pre["mariadb"]["payload_crc32_sum"]:
                raise RuntimeError(label + ": committed MariaDB payload checksum changed")
            if state["mariadb"]["uncommitted_visible"] != "0":
                raise RuntimeError(label + ": uncommitted transaction became visible")
            if state["redis"]["committed_value_sha256"] != pre["redis"]["committed_value_sha256"]:
                raise RuntimeError(label + ": Redis committed value did not survive")
            if state["redis"]["queue_length"] != COMMITTED_ROWS:
                raise RuntimeError(label + ": Redis queue did not survive")
            if state["redis"]["queue_head_sha256"] != pre["redis"]["queue_head_sha256"]:
                raise RuntimeError(label + ": Redis queue contents changed")
            return True

        # Each MariaDB server start rotates a new binary log, so a strictly
        # increasing count is independent proof that the server really restarted
        # rather than merely being queried again. Enforced, not just recorded.
        binlog_counts = {"pre_state": len(pre["mariadb"]["binlog_files"])}

        def assert_binlog_rotated(label, state):
            count = len(state["mariadb"]["binlog_files"])
            previous = max(binlog_counts.values())
            binlog_counts[label] = count
            if count <= previous:
                raise RuntimeError(
                    label + ": binary log did not rotate, so the server may not have restarted")
            return count

        # Scenario 1: graceful restart of both live servers.
        run("restart-mariadb", ["docker", "restart", "--time", "30", MARIADB_CONTAINER], timeout=180)
        run("restart-redis", ["docker", "restart", "--time", "30", REDIS_CONTAINER], timeout=180)
        report["restart_recovery"] = {
            "mariadb": wait_healthy(MARIADB_CONTAINER), "redis": wait_healthy(REDIS_CONTAINER)}
        # A restart kills the client session holding the open transaction, so the
        # server must have rolled it back during recovery.
        if holder.poll() is None:
            holder.kill()
        holder = None
        state = {"mariadb": mariadb_state(), "redis": redis_state()}
        state["containers"] = {"mariadb": container_state(MARIADB_CONTAINER),
                               "redis": container_state(REDIS_CONTAINER)}
        report["scenario_1_graceful_restart"] = {
            "post_state": state, "survived": assert_survived("graceful restart", state),
            "uncommitted_row_absent_after_recovery":
                state["mariadb"]["uncommitted_visible"] == "0",
            "binlog_rotations_observed": assert_binlog_rotated("graceful restart", state),
        }

        # Re-open the uncommitted transaction so the crash scenario tests it too.
        holder = subprocess.Popen(
            ["docker", "exec", "--interactive", "--env", "MYSQL_PWD", MARIADB_CONTAINER,
             "mariadb", "--user=root", "--batch", "--skip-column-names", DATABASE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env)
        holder.stdin.write("START TRANSACTION;\n"
                           f"INSERT INTO {TABLE} (id, payload) VALUES"
                           " ('uncommitted-crash-probe', 'synthetic-uncommitted');\n")
        holder.stdin.flush()
        time.sleep(3)
        if mariadb_state()["uncommitted_visible"] != "0":
            raise RuntimeError("Uncommitted transaction was visible before the crash")

        # Scenario 2: SIGKILL the database server, the closest supported analogue
        # of power loss, then cold-start it and exercise InnoDB crash recovery.
        run("kill-mariadb-sigkill", ["docker", "kill", "--signal=KILL", MARIADB_CONTAINER])
        run("kill-redis-sigkill", ["docker", "kill", "--signal=KILL", REDIS_CONTAINER])
        report["crash_states"] = {"mariadb": container_state(MARIADB_CONTAINER),
                                  "redis": container_state(REDIS_CONTAINER)}
        run("start-mariadb-after-crash", ["docker", "start", MARIADB_CONTAINER])
        run("start-redis-after-crash", ["docker", "start", REDIS_CONTAINER])
        report["crash_recovery"] = {
            "mariadb": wait_healthy(MARIADB_CONTAINER), "redis": wait_healthy(REDIS_CONTAINER)}
        if holder.poll() is None:
            holder.kill()
        holder = None
        state = {"mariadb": mariadb_state(), "redis": redis_state()}
        state["containers"] = {"mariadb": container_state(MARIADB_CONTAINER),
                               "redis": container_state(REDIS_CONTAINER)}
        crash_log = run("mariadb-crash-recovery-log",
                        ["docker", "logs", "--tail", "600", MARIADB_CONTAINER],
                        allow_failure=True)
        # `docker logs` returns the whole container history, so the LAST matching
        # lines are the post-crash start. Crash markers and startup markers are
        # kept in SEPARATE lists: a broadened filter once matched only
        # "[Entrypoint]: Starting temporary server", which is startup noise and
        # not InnoDB recovery evidence. Labelling it as recovery overstated the
        # evidence, so the two are never merged.
        crash_markers = ("innodb", "recovery", "crash", "redo", "rollback", "roll back")
        startup_markers = ("ready for connections", "shutdown", "starting", "entrypoint")
        log_lines = [line.strip()[:220] for line in crash_log.splitlines()]
        innodb_lines = [line for line in log_lines
                        if any(marker in line.lower() for marker in crash_markers)][-20:]
        startup_lines = [line for line in log_lines
                         if any(marker in line.lower() for marker in startup_markers)][-20:]
        # SHOW ENGINE INNODB STATUS is the authoritative native source for
        # recovery position. MariaDB does not always emit crash-recovery lines at
        # default verbosity, so this - not a log grep - is what corroborates that
        # recovery ran from a consistent checkpoint.
        try:
            status_text = sql("SHOW ENGINE INNODB STATUS;").replace("\\n", "\n")
        except Exception as exc:
            status_text = ""
            report["innodb_status_error"] = type(exc).__name__

        log_section = extract_innodb_section(status_text, "LOG")
        report["scenario_2_sigkill_crash_recovery"] = {
            "post_state": state, "survived": assert_survived("crash recovery", state),
            "uncommitted_row_absent_after_crash":
                state["mariadb"]["uncommitted_visible"] == "0",
            "binlog_rotations_observed": assert_binlog_rotated("crash recovery", state),
            "innodb_force_recovery_setting": state["mariadb"]["innodb_force_recovery"],
            "innodb_recovery_messages": innodb_lines,
            "server_startup_messages": startup_lines,
            "innodb_status_log_section": log_section,
            "log_lines_captured": len(log_lines),
            "note": ("innodb_recovery_messages may legitimately be empty at default "
                     "server verbosity; innodb_status_log_section is the authoritative "
                     "corroboration and startup messages are recorded separately so "
                     "they are never mistaken for recovery evidence."),
        }
        if not innodb_lines and not log_section:
            raise RuntimeError(
                "Crash scenario has neither InnoDB recovery log lines nor an "
                "INNODB STATUS LOG section, so recovery is uncorroborated")

        # Scenario 3: destroy both containers outright and recreate new ones from
        # the same named volumes. This is what distinguishes real volume
        # persistence from data that merely lived in a container's writable layer.
        destroyed = {}
        for name, container in (("mariadb", MARIADB_CONTAINER), ("redis", REDIS_CONTAINER)):
            destroyed[name] = container_state(container)
            run("destroy-" + name + "-container", ["docker", "rm", "--force", container])
        report["scenario_3_container_destruction"] = {"destroyed_state": destroyed}
        # The volumes must still exist and must not have been recreated empty.
        report["volumes_after_destruction"] = {
            name: json.loads(subprocess.run(
                ["docker", "volume", "inspect", volume, "--format", "{{json .}}"],
                capture_output=True, text=True, env=env, check=True, timeout=60).stdout)
            for name, volume in (("mariadb", MARIADB_VOLUME), ("redis", REDIS_VOLUME))}
        run("recreate-mariadb-from-volume", mariadb_command())
        run("recreate-redis-from-volume", redis_command())
        report["recreation_health"] = {
            "mariadb": wait_healthy(MARIADB_CONTAINER), "redis": wait_healthy(REDIS_CONTAINER)}
        state = {"mariadb": mariadb_state(), "redis": redis_state()}
        state["containers"] = {"mariadb": container_state(MARIADB_CONTAINER),
                               "redis": container_state(REDIS_CONTAINER)}
        report["scenario_3_container_destruction"].update({
            "post_state": state,
            "survived": assert_survived("volume persistence after container destruction", state),
            "mariadb_container_id_before_destruction":
                report["pre_state"]["containers"]["mariadb"]["container_id"],
            "mariadb_container_id_after_recreation":
                state["containers"]["mariadb"]["container_id"],
            "redis_container_id_before_destruction":
                report["pre_state"]["containers"]["redis"]["container_id"],
            "redis_container_id_after_recreation":
                state["containers"]["redis"]["container_id"],
            # Distinct container IDs prove genuinely new containers were created,
            # so survival is attributable to the named volume and not to the
            # original container still being alive.
            "binlog_rotations_observed": assert_binlog_rotated(
                "volume persistence after container destruction", state),
            "new_containers_created": (
                state["containers"]["mariadb"]["container_id"]
                != report["pre_state"]["containers"]["mariadb"]["container_id"]
                and state["containers"]["redis"]["container_id"]
                != report["pre_state"]["containers"]["redis"]["container_id"]),
            "mariadb_log_tail_after_recreation": redact(run(
                "mariadb-log-after-recreation",
                ["docker", "logs", "--tail", "60", MARIADB_CONTAINER],
                allow_failure=True, quiet=True))[-1500:],
        })
        if not report["scenario_3_container_destruction"]["new_containers_created"]:
            raise RuntimeError("Container destruction did not actually replace the containers")

        # A negative control: durability must be attributable to the volume, not
        # to luck. Removing the volume and starting a fresh container must yield
        # an empty database.
        run("remove-mariadb-container-for-control", ["docker", "rm", "--force", MARIADB_CONTAINER])
        run("remove-mariadb-volume", ["docker", "volume", "rm", MARIADB_VOLUME])
        run("create-empty-mariadb-volume", ["docker", "volume", "create", MARIADB_VOLUME])
        run("start-mariadb-on-empty-volume", mariadb_command())
        wait_healthy(MARIADB_CONTAINER)
        sql("CREATE DATABASE IF NOT EXISTS `" + DATABASE + "`"
            " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;", database="mysql")
        control = sql(f"SELECT COUNT(*) FROM information_schema.tables"
                      f" WHERE table_schema='{DATABASE}' AND table_name='{TABLE}';")
        report["negative_control_volume_loss"] = {
            "table_present_after_volume_loss": control,
            "expected": "0",
            "confirms_data_lived_in_the_volume": control == "0",
        }
        if control != "0":
            raise RuntimeError("Negative control failed: data survived complete volume loss")

        report["binlog_rotation_progression"] = binlog_counts
        report["status"] = "pass"
        report["durability_executed"] = True
        report["not_proven_by_this_probe"] = [
            "Host or region loss, storage-array failure and off-site replication",
            "High availability, failover and multi-node quorum behaviour",
            "Application-level workflow correctness after recovery",
            "Backup archive integrity, which is covered by the restore probes",
            "Any owner-selected durability reference or retention objective",
        ]
        write()
        print("Real MariaDB/Redis restart, crash-recovery and volume persistence verified")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = redact(str(exc))[-4000:]
        report["durability_executed"] = False
        write()
        print(report["failure"], file=sys.stderr)
    finally:
        if holder is not None and holder.poll() is None:
            try:
                holder.kill()
            except OSError:
                pass
        for container in (MARIADB_CONTAINER, REDIS_CONTAINER):
            subprocess.run(["docker", "rm", "--force", container],
                           capture_output=True, env=env, check=False, timeout=60)
        for volume in (MARIADB_VOLUME, REDIS_VOLUME):
            subprocess.run(["docker", "volume", "rm", "--force", volume],
                           capture_output=True, env=env, check=False, timeout=60)
        secret_file.unlink(missing_ok=True)
        write()
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
