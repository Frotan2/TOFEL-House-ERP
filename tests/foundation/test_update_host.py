"""Independent live-host checks over a real Unix HTTP socket, not request hints.

Docker replies here are a disposable server, not a real Docker daemon. Actual
Docker/Windows qualification is separately required before release.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from tests.foundation import test_update_engine as suite

host = suite.engine.update_host


class DockerHandler(socketserver.StreamRequestHandler):
    def handle(self):
        method, path, _version = self.rfile.readline().decode().split()
        while self.rfile.readline() not in (b"\r\n", b"\n", b""):
            pass
        self.server.calls.append((method, unquote(path)))
        item = self.server.documents.get(unquote(path)) if method == "GET" else None
        payload = json.dumps(item or {}).encode()
        code = b"200 OK" if item is not None else b"404 Not Found"
        self.wfile.write(b"HTTP/1.1 " + code + b"\r\nContent-Length: " + str(len(payload)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + payload)


@unittest.skipUnless(os.name == "posix" and hasattr(socket, "AF_UNIX"), "Linux Docker observer")
class LiveHostTests(unittest.TestCase):
    def setUp(self):
        # Reuse the signed-release and subprocess migration harness. The
        # decision engine's independent observer is replaced below with the
        # real collector talking HTTP over a Unix socket, not a host snapshot.
        real_observer = suite.engine._observe_host
        self.harness = suite.ApplyTests()
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.fixture = self.harness.fixture
        self.documents = {}
        self.original_id = self.fixture.installed()["image_id"]
        self.target_id = self.fixture.identity["config_digest"]
        self.documents["/images/" + self.original_id + "/json"] = {
            "Id": self.original_id, "Config": {"Labels": self.fixture.installed()["image_labels"]}}
        self.documents["/images/" + host.TAG + "/json"] = copy.deepcopy(
            self.documents["/images/" + self.original_id + "/json"])
        self.volume = {"Name": host.VOLUME, "Driver": "local", "Scope": "local",
                       "CreatedAt": "2026-10-25T00:00:00Z", "Mountpoint": "/docker/volumes/db/_data"}
        self.documents["/volumes/" + host.VOLUME] = self.volume
        for name, container in host.CONTAINERS.items():
            self.documents["/containers/" + container + "/json"] = {
                "Id": name + "-original-container", "Image": self.original_id,
                "State": {"Status": "running"}, "Mounts": []}
        self.db = self.documents["/containers/" + host.CONTAINERS["db"] + "/json"]
        self.db["Mounts"] = [{"Type": "volume", "Name": host.VOLUME,
                              "Destination": "/var/lib/mysql", "Source": self.volume["Mountpoint"]}]
        self.journal = self.fixture.product_root / "data/updates/journal.json"
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        # Keep the Unix socket name below Linux's 108-byte limit.
        self.socket_dir = tempfile.TemporaryDirectory(prefix="th-docker-")
        self.addCleanup(self.socket_dir.cleanup)
        self.socket_path = str(Path(self.socket_dir.name) / "docker.sock")
        try:
            self.server = socketserver.UnixStreamServer(self.socket_path, DockerHandler)
        except PermissionError:
            # Some hosted editing environments prohibit Unix sockets entirely.
            # Keep the live-state decision cases running with a fake transport;
            # the unrestricted Linux CI uses the real Unix HTTP server above.
            from types import SimpleNamespace
            documents = self.documents
            calls = []
            class MemoryConnection:
                def request(self, method, path):
                    calls.append((method, unquote(path)))
                    self.document = copy.deepcopy(documents.get(unquote(path)))
                def getresponse(self):
                    raw = json.dumps(self.document or {}).encode()
                    return SimpleNamespace(status=200 if self.document is not None else 404,
                                           read=lambda _limit: raw)
                def close(self):
                    pass
            transport = patch.object(host, "DockerConnection", side_effect=lambda *_args, **_kw: MemoryConnection())
            transport.start()
            self.addCleanup(transport.stop)
            self.server = SimpleNamespace(calls=calls)
        else:
            self.server.documents = self.documents
            self.server.calls = []
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            self.thread.start()
            self.addCleanup(self.close_server)
        for patcher in (
            patch.object(host, "DOCKER_SOCKET", self.socket_path),
            patch.object(host, "PRODUCT_ROOT", self.fixture.product_root),
            patch.object(host.shutil, "disk_usage", return_value=type("Usage", (), {"free": 60 * 1024**3})()),
            patch.object(host, "observe", side_effect=host.collect),
            patch.object(suite.engine, "_observe_host", side_effect=real_observer),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def prepare(self):
        transaction = self.harness.transaction()
        for name in ("web", "worker", "scheduler", "socketio"):
            self.documents["/containers/" + host.CONTAINERS[name] + "/json"]["State"]["Status"] = "exited"
        self.documents["/images/" + host.TAG + "/json"] = {
            "Id": self.target_id, "Config": {"Labels": self.fixture.identity["labels"]}}
        self.journal.write_text(json.dumps({"schema_version": 1,
            "document_type": "toefl-house-erp-update-journal", "phase": "applying",
            "version": self.fixture.version, "transaction_id": transaction["transaction_id"]}))
        return transaction

    def assert_refused_without_migration(self, transaction, code):
        report = self.harness.apply(transaction=transaction)
        self.assertEqual(report["status"], "failed", report)
        self.assertIn(code, suite.codes(report))
        self.assertFalse(self.harness.migrate_called())

    def test_expected_stopped_application_and_loaded_target_can_migrate(self):
        report = self.harness.apply(transaction=self.prepare())
        self.assertEqual(report["status"], "succeeded", report)
        self.assertEqual(self.harness.read_state()["migrate_calls"], 2)
        self.assertTrue(self.server.calls)
        self.assertEqual({method for method, _path in self.server.calls}, {"GET"})

    def test_same_name_recreated_volume_is_not_the_authorized_volume(self):
        transaction = self.prepare()
        self.volume["CreatedAt"] = "2026-10-25T01:00:00Z"
        self.assert_refused_without_migration(transaction, "apply.host_unsafe")

    def test_database_container_replacement_is_not_authorized(self):
        transaction = self.prepare()
        self.db["Id"] = "replacement-container"
        self.assert_refused_without_migration(transaction, "apply.host_unsafe")

    def test_a_worker_running_another_image_is_not_a_valid_installation(self):
        transaction = self.prepare()
        self.documents["/containers/" + host.CONTAINERS["worker"] + "/json"]["Image"] = (
            "sha256:" + "8" * 64)
        self.assert_refused_without_migration(transaction, "preflight.host.unavailable")

    def test_changed_real_journal_is_not_hidden_by_stale_idle_hint(self):
        transaction = self.prepare()
        document = json.loads(self.journal.read_text())
        document["transaction_id"] = "f" * 32
        self.journal.write_text(json.dumps(document))
        self.assert_refused_without_migration(transaction, "apply.journal_unsafe")

    def test_live_original_container_image_change_is_not_hidden_by_request(self):
        transaction = self.prepare()
        image = copy.deepcopy(self.documents["/images/" + self.original_id + "/json"])
        image["Id"] = "sha256:" + "7" * 64
        self.documents["/images/" + image["Id"] + "/json"] = image
        self.documents["/containers/" + host.CONTAINERS["web"] + "/json"]["Image"] = image["Id"]
        self.assert_refused_without_migration(transaction, "preflight.host.unavailable")

    def test_loaded_tag_must_be_the_verified_candidate(self):
        transaction = self.prepare()
        self.documents["/images/" + host.TAG + "/json"]["Id"] = "sha256:" + "8" * 64
        self.assert_refused_without_migration(transaction, "apply.installed_mismatch")

    def test_changed_real_credentials_are_not_hidden_by_presence_flags(self):
        transaction = self.prepare()
        path = self.fixture.product_root / "data/secrets/db.env"
        path.write_text("different-test-password")
        self.assert_refused_without_migration(transaction, "apply.host_unsafe")

    def test_changed_site_configuration_is_not_authorized(self):
        transaction = self.prepare()
        path = self.fixture.product_root / "data/sites" / host.SITE / "site_config.json"
        path.write_text('{"db_name":"different-test-database"}')
        self.assert_refused_without_migration(transaction, "apply.host_unsafe")

    def test_missing_volume_or_docker_failure_does_not_fall_back_to_request(self):
        transaction = self.prepare()
        del self.documents["/volumes/" + host.VOLUME]
        with self.assertRaises(host.ObservationError):
            host.collect()
        # The production bridge converts an unavailable broker to a stable
        # refusal; do not let the fake collector exception bypass that bridge.
        with patch.object(suite.engine, "_observe_host", side_effect=suite.engine.refuse(
                "preflight.host.unavailable", "unavailable")):
            self.assert_refused_without_migration(transaction, "preflight.host.unavailable")

    def test_wrong_volume_mount_is_not_verified_by_matching_name(self):
        transaction = self.prepare()
        self.db["Mounts"][0]["Source"] = "/different-storage"
        with self.assertRaises(host.ObservationError):
            host.collect()
        self.assertFalse(self.harness.migrate_called())
        self.assertIsNotNone(transaction)

    def test_host_change_between_migrate_replays_requires_recovery(self):
        transaction = self.prepare()
        original = suite.engine.BenchRunner.migrate
        volume = self.volume
        def change_after_first_migration(runner, site):
            original(runner, site)
            volume["CreatedAt"] = "2026-10-25T02:00:00Z"
        with patch.object(suite.engine.BenchRunner, "migrate", change_after_first_migration):
            report = self.harness.apply(transaction=transaction)
        self.assertEqual(report["transaction_outcome"], "recovery-required")
        self.assertEqual(self.harness.read_state()["migrate_calls"], 1)
        self.assertIn("apply.host_unsafe", suite.codes(report))

    def test_tag_change_during_post_migration_verification_cannot_report_success(self):
        transaction = self.prepare()
        original = suite.engine.BenchRunner.role_desk_pages
        documents = self.documents
        def change_after_pages(runner, site):
            result = original(runner, site)
            documents["/images/" + host.TAG + "/json"]["Id"] = "sha256:" + "8" * 64
            return result
        with patch.object(suite.engine.BenchRunner, "role_desk_pages", change_after_pages):
            report = self.harness.apply(transaction=transaction)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["transaction_outcome"], "recovery-required")
        self.assertIn("apply.installed_mismatch", suite.codes(report))

    def test_recheck_catches_live_change_before_host_mutation(self):
        transaction = self.harness.transaction()
        self.volume["CreatedAt"] = "2026-10-25T01:00:00Z"
        request = {**self.fixture.authorize_request(transaction), "action": "recheck"}
        response, code = suite.engine.run(request, now=suite.NOW, state_dir=self.fixture.state_dir)
        self.assertEqual(code, 3)
        self.assertIn("transaction.mismatch", suite.codes(response))
        self.assertFalse(self.harness.migrate_called())


class BrokerTrustTests(unittest.TestCase):
    def test_absent_observer_cannot_be_replaced_by_request_json(self):
        with patch.object(host, "BROKER_SOCKET", "/no-such-root-observer.sock"):
            with self.assertRaises(host.ObservationError):
                host.observe()

    @unittest.skipUnless(os.name == "posix", "Unix permissions")
    def test_a_regular_file_is_not_a_trusted_broker_socket(self):
        with tempfile.NamedTemporaryFile() as handle, patch.object(host, "BROKER_SOCKET", handle.name):
            with self.assertRaises(host.ObservationError):
                host.observe()
