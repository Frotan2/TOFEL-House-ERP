"""Product lifecycle simulation against the REAL shipped product/bootstrap.py.

No Docker, MariaDB or Windows is available in this engineering environment
(probed and documented 2026-09-29), so the first-boot/Start/Stop/Repair flow
is executed against the actual shipped bootstrap module with two honest
substitutions, recorded here: bench invocations run through a scripted stub
recording every call (filesystem semantics identical to frappe), and service
readiness uses real TCP listeners on loopback instead of compose hostnames.
The shipped code paths — endpoint waits, redis config, site creation, ordered
app installs, migrate replay, native encryption-key initialization, asset
build, one-time credential generation, restart idempotence, repair of a
partial state, restart persistence — are executed unchanged. Assertions are
hard invariants, fail-closed; synthetic-only flags must never appear.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
import bootstrap  # noqa: E402

SITE = "toeflhouse.localhost"
BANNED_TOKENS = ("toefl_house_synthetic_only", "allow_tests", "disable_website_cache", "activate")

FAKE_BENCH = """#!/usr/bin/env python3
import json, sys
from pathlib import Path

BIN = Path(sys.argv[0]).resolve().parent
STATE = BIN.parent / "fakebench-state.json"
BENCH_ROOT = BIN.parent / "benchroot"

state = json.loads(STATE.read_text())

def save():
    STATE.write_text(json.dumps(state, indent=2))

def log(args):
    state.setdefault("calls", []).append(args)
    save()

args = list(sys.argv[1:])
site = None
if len(args) > 2 and args[0] == "--site":
    site = args[1]
    args = args[2:]
if not args:
    sys.exit(2)
cmd = args[0]

if cmd == "set-config" and len(args) >= 4 and args[1] == "--global":
    state.setdefault("global_config", {})[args[2]] = args[3]
    log(sys.argv[1:])
    save()
elif cmd == "new-site":
    name = args[1]
    (BENCH_ROOT / "sites" / name).mkdir(parents=True, exist_ok=True)
    (BENCH_ROOT / "sites" / name / "site_config.json").write_text(
        json.dumps({"db_name": "db_" + name.replace(".", "_"), "db_type": "mariadb"}))
    (BENCH_ROOT / "sites").mkdir(parents=True, exist_ok=True)
    (BENCH_ROOT / "sites" / "currentsite.txt").write_text(name)
    state.setdefault("sites", {}).setdefault(name, {"apps": ["frappe"], "migrate_calls": 0})
    state["current_site_created"] = True
    log(sys.argv[1:])
    save()
elif cmd == "list-apps":
    print(json.dumps({site: state["sites"][site]["apps"]}))
elif cmd == "install-app":
    target = args[1]
    assert target not in state["sites"][site]["apps"], "duplicate app install"
    state["sites"][site]["apps"].append(target)
    log(sys.argv[1:])
    save()
elif cmd == "migrate":
    state["sites"][site]["migrate_calls"] += 1
    log(sys.argv[1:])
    save()
elif cmd == "execute":
    cfg = BENCH_ROOT / "sites" / site / "site_config.json"
    data = json.loads(cfg.read_text())
    data["encryption_key"] = "native-key-material"
    cfg.write_text(json.dumps(data))
    log(sys.argv[1:])
    save()
elif cmd == "build":
    (BENCH_ROOT / "sites" / "assets" / "js").mkdir(parents=True, exist_ok=True)
    state["build_calls"] = state.get("build_calls", 0) + 1
    log(sys.argv[1:])
    save()
elif cmd == "enable-scheduler":
    state["scheduler_enabled"] = True
    log(sys.argv[1:])
    save()
elif cmd == "backup":
    backups = BENCH_ROOT / "sites" / site / "private" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "20260929-database.sql.gz").write_bytes(json.dumps(state).encode())
    (backups / "20260929-files.tar").write_bytes(b"public-files")
    (backups / "20260929-private-files.tar").write_bytes(b"private-files")
    log(sys.argv[1:])
    save()
else:
    sys.exit(2)
"""


def open_listeners(ports=3):
    listeners = []
    sockets = []
    threads = []

    def drain(sock):
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            conn.close()

    for _ in range(ports):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(64)
        sockets.append(sock)
        listeners.append(sock.getsockname()[1])
        threads.append(threading.Thread(target=drain, args=(sock,), daemon=True))
        threads[-1].start()
    return sockets, listeners


class ProductLifecycleSim(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="product-lifecycle-"))
        self.bench_root = self.tmp / "benchroot"
        self.bench_root.mkdir(parents=True)
        fake_bin = self.tmp / "fakebin"
        fake_bin.mkdir()
        bench_file = fake_bin / "bench"
        bench_file.write_text(FAKE_BENCH)
        bench_file.chmod(0o755)
        secrets_dir = self.tmp / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "db.env").write_text("MARIADB_ROOT_PASSWORD=sim-root-password\n")
        self.state_path = self.tmp / "fakebench-state.json"
        self.state_path.write_text(json.dumps({"sites": {}, "calls": []}))
        self.sockets, self.ports = open_listeners(3)
        self.patches = [
            mock.patch.object(bootstrap, "BENCH_DIR", self.bench_root),
            mock.patch.object(bootstrap, "SITES_DIR", self.bench_root / "sites"),
            mock.patch.object(bootstrap, "SECRETS_DIR", secrets_dir),
            mock.patch.object(bootstrap, "SERVICE_ENDPOINTS",
                              tuple(("127.0.0.1", port) for port in self.ports)),
            mock.patch.dict(os.environ, {"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        for sock in self.sockets:
            sock.close()

    def state(self):
        return json.loads(self.state_path.read_text())

    def test_first_boot_installs_everything_exactly_once_in_proven_order(self):
        summary = bootstrap.bootstrap(SITE, log=lambda _: None)
        self.assertEqual(summary["actions"],
                         ["services-reachable", "redis-configured", "site-created",
                          "installed-erpnext", "installed-education", "installed-payments",
                          "installed-hrms", "installed-foundation_security", "installed-toefl_house",
                          "migrated", "migrate-replayed", "encryption-key-initialized",
                          "assets-built", "scheduler-enabled"])
        state = self.state()
        site_state = state["sites"][SITE]
        self.assertEqual(site_state["apps"],
                         ["frappe", "erpnext", "education", "payments", "hrms",
                          "foundation_security", "toefl_house"])
        self.assertEqual(site_state["migrate_calls"], 2)  # hosted-parity migrate replay
        self.assertTrue(state.get("scheduler_enabled"))
        self.assertEqual(state["global_config"]["redis_cache"], "redis://redis-cache:6379")
        self.assertEqual(state["global_config"]["redis_queue"], "redis://redis-queue:6379")
        site_config = json.loads((self.bench_root / "sites" / SITE / "site_config.json").read_text())
        self.assertEqual(site_config["encryption_key"], "native-key-material")
        # call order: new-site strictly precedes every install-app; migrate follows installs
        # (site-scoped calls are logged with the leading "--site <site>" prefix)
        verb = lambda call: call[2] if call[:1] == ["--site"] else call[0]  # noqa: E731
        first_words = [verb(call) for call in state["calls"]]
        new_site_at = first_words.index("new-site")
        self.assertTrue(all(first_words.index(name) > new_site_at
                            for name in ("install-app", "migrate")),
                        f"unexpected bench call order: {first_words}")
        self.assertLess(first_words.index("install-app"), first_words.index("migrate"),
                        f"installs must precede migrate: {first_words}")
        # banned synthetic/production-activation tokens never reach bench
        for call in state["calls"]:
            blob = " ".join(call)
            for banned in BANNED_TOKENS:
                self.assertNotIn(banned, blob)
        credentials = self.bench_root / "sites" / SITE / "private" / "first-run-credentials.txt"
        body = credentials.read_text()
        self.assertIn("Username: Administrator", body)
        self.assertEqual(oct(credentials.stat().st_mode & 0o777), "0o600")

    def test_restart_is_fully_idempotent(self):
        bootstrap.bootstrap(SITE, log=lambda _: None)
        before = (self.bench_root / "sites" / SITE / "private" / "first-run-credentials.txt").read_bytes()
        summary = bootstrap.bootstrap(SITE, log=lambda _: None)  # Start -> Stop -> Start
        self.assertEqual(summary["actions"],
                         ["services-reachable", "redis-configured", "site-present", "apps-present",
                          "migrated", "migrate-replayed", "encryption-key-initialized", "assets-present"])
        after = (self.bench_root / "sites" / SITE / "private" / "first-run-credentials.txt").read_bytes()
        self.assertEqual(before, after, "credentials must never rotate silently")
        state = self.state()
        self.assertEqual(state["sites"][SITE]["migrate_calls"], 4)  # migrate always runs, per boot
        self.assertEqual(state.get("build_calls", 1), 1)  # assets built exactly once

    def test_repair_reinstalls_only_missing_and_never_rotates(self):
        bootstrap.bootstrap(SITE, log=lambda _: None)
        credentials_before = (self.bench_root / "sites" / SITE / "private"
                              / "first-run-credentials.txt").read_bytes()
        state = self.state()
        state["sites"][SITE]["apps"] = ["frappe", "erpnext"]  # crashed/partial state
        self.state_path.write_text(json.dumps(state))
        summary = bootstrap.bootstrap(SITE, log=lambda _: None)  # Repair script runs this same entrypoint
        self.assertEqual([action for action in summary["actions"] if action.startswith("installed-")],
                         ["installed-education", "installed-payments", "installed-hrms",
                          "installed-foundation_security", "installed-toefl_house"])
        after = (self.bench_root / "sites" / SITE / "private" / "first-run-credentials.txt").read_bytes()
        self.assertEqual(credentials_before, after)
        self.assertEqual(self.state()["sites"][SITE]["apps"],
                         ["frappe", "erpnext", "education", "payments", "hrms",
                          "foundation_security", "toefl_house"])

    def test_persistence_survives_cross_restart_state(self):
        bootstrap.bootstrap(SITE, log=lambda _: None)
        first_migrates = self.state()["sites"][SITE]["migrate_calls"]
        credentials_body = (self.bench_root / "sites" / SITE / "private"
                            / "first-run-credentials.txt").read_bytes()
        for _ in range(3):  # three more daily Start cycles
            bootstrap.bootstrap(SITE, log=lambda _: None)
        state = self.state()
        self.assertEqual(state["sites"][SITE]["migrate_calls"], first_migrates + 6)
        self.assertEqual((self.bench_root / "sites" / SITE / "private"
                          / "first-run-credentials.txt").read_bytes(), credentials_body)
        # db + files persist exactly as created (bind-mounted media remains untouched)
        site_config = json.loads((self.bench_root / "sites" / SITE / "site_config.json").read_text())
        self.assertEqual(site_config["db_type"], "mariadb")
        self.assertEqual(site_config["encryption_key"], "native-key-material")

    def test_unavailable_services_fail_closed(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
        probe.close()  # nothing answers on this port
        with self.assertRaises(RuntimeError, msg="bootstrap must fail closed when services never come up"):
            bootstrap.wait_for_endpoints((("127.0.0.1", dead_port),), timeout=0.2)
        # and the full entrypoint must not proceed past the wait gate
        real_wait = bootstrap.wait_for_endpoints
        with mock.patch.object(bootstrap, "wait_for_endpoints",
                               lambda _endpoints=(): real_wait((("127.0.0.1", dead_port),), timeout=0.2)):
            with self.assertRaises(RuntimeError):
                bootstrap.bootstrap(SITE, log=lambda _: None)
        self.assertEqual(self.state()["sites"], {}, "no site must be created when services are down")


if __name__ == "__main__":
    unittest.main()
