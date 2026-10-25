#!/usr/bin/env python3
"""Linux root/nobody IPC probe with synthetic Docker HTTP, not Owner acceptance.

Run only in an isolated Linux CI runner, as root. Creates temporary sockets and
files, drops the client to nobody, and never contacts a real Docker daemon.
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import pwd
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "product"))
import update_host as host  # noqa: E402


class DockerHandler(socketserver.StreamRequestHandler):
    def handle(self):
        method, path, _version = self.rfile.readline().decode().split()
        while self.rfile.readline() not in (b"\r\n", b"\n", b""):
            pass
        self.server.calls.append((method, unquote(path)))
        item = self.server.documents.get(unquote(path)) if method == "GET" else None
        raw = json.dumps(item or {}).encode()
        status = b"200 OK" if item is not None else b"404 Not Found"
        self.wfile.write(b"HTTP/1.1 " + status + b"\r\nContent-Length: " + str(len(raw)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + raw)


def client(broker_path, docker_path):
    host.BROKER_SOCKET = broker_path
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw:
        try:
            raw.connect(docker_path)
        except PermissionError:
            pass
        else:
            raise AssertionError("engine account can open the raw Docker socket")
    observation = host.observe()
    assert observation["facts"]["volume_verified"] is True
    assert len(observation["identity"]["storage_sha256"]) == 64
    assert "private-test-value" not in json.dumps(observation)
    # The client cannot turn the broker into an arbitrary Docker API proxy.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(broker_path)
        connection.sendall(json.dumps({"nonce": "a" * 32, "method": "POST",
                                       "path": "/containers/create"}).encode() + b"\n")
        assert json.loads(host._receive(connection)) == {"status": "unavailable"}
    print("PASS: authenticated root observation; raw socket denied; arbitrary API request denied")


def broker(account):
    original = pwd.getpwnam
    with patch("pwd.getpwnam", side_effect=lambda name: account if name == "frappe" else original(name)):
        host.serve()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--client":
        client(sys.argv[2], sys.argv[3])
        return 0
    if os.geteuid() != 0:
        raise SystemExit("Run this isolated synthetic privilege probe as root")
    account = pwd.getpwnam("nobody")
    with tempfile.TemporaryDirectory(prefix="th-observer-privilege-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        host.BROKER_SOCKET = str(root / "broker.sock")
        host.BROKER_READY = str(root / "ready")
        host.DOCKER_SOCKET = str(root / "docker.sock")
        host.PRODUCT_ROOT = root / "product"
        for relative, contents in (("data/secrets/db.env", "private-test-value"),
                                   ("data/sites/" + host.SITE + "/site_config.json", "{}")):
            path = host.PRODUCT_ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        image_id = "sha256:" + "a" * 64
        labels = {"org.toefl-house.source-revision": "b" * 40}
        volume = {"Name": host.VOLUME, "Driver": "local", "Scope": "local",
                  "CreatedAt": "2026-10-25T00:00:00Z", "Mountpoint": "/synthetic/db"}
        documents = {"/images/" + image_id + "/json": {"Id": image_id, "Config": {"Labels": labels}},
                     "/images/" + host.TAG + "/json": {"Id": image_id, "Config": {"Labels": labels}},
                     "/volumes/" + host.VOLUME: volume}
        for name, container in host.CONTAINERS.items():
            mounts = ([{"Type": "volume", "Name": host.VOLUME, "Source": volume["Mountpoint"],
                        "Destination": "/var/lib/mysql"}] if name == "db" else [])
            documents["/containers/" + container + "/json"] = {
                "Id": "synthetic-" + name, "Image": image_id, "State": {"Status": "running"},
                "Mounts": mounts, "Config": {"Env": ["SECRET=private-test-value"]}}
        with socketserver.UnixStreamServer(host.DOCKER_SOCKET, DockerHandler) as server:
            os.chmod(host.DOCKER_SOCKET, 0o600)
            server.documents = documents
            server.calls = []
            # Fork before starting a server thread. This child is the only
            # root broker; no system users or persistent host files are changed.
            process = multiprocessing.get_context("fork").Process(target=broker, args=(account,))
            process.start()
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            thread.start()
            try:
                for _ in range(100):
                    if Path(host.BROKER_READY).exists():
                        break
                    if not process.is_alive():
                        raise AssertionError("root observer exited before readiness")
                    time.sleep(0.02)
                else:
                    raise AssertionError("root observer did not become ready")
                def drop_privileges():
                    os.setgroups([])
                    os.setgid(account.pw_gid)
                    os.setuid(account.pw_uid)
                # nobody need not traverse the runner's private home folder.
                # Copy only these public source files into the temporary area.
                client_script = root / "client.py"
                client_script.write_bytes(Path(__file__).read_bytes())
                (root / "update_host.py").write_bytes(Path(host.__file__).read_bytes())
                subprocess.run([sys.executable, str(client_script), "--client",
                                host.BROKER_SOCKET, host.DOCKER_SOCKET],
                               check=True, timeout=30, preexec_fn=drop_privileges)
                assert len(server.calls) == len(documents), server.calls
                assert {method for method, _path in server.calls} == {"GET"}
            finally:
                process.terminate()
                process.join(timeout=5)
                server.shutdown()
                thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
