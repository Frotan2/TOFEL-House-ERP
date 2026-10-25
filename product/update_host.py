#!/usr/bin/env python3
"""Root-owned, GET-only Docker observer for the unprivileged update engine.

The private broker accepts only a nonce, never a URL, path, command or cached
host report. Docker's socket is NOT made available to the frappe process by
this API. Its root/group permissions must actually deny that process access;
a read-only bind mount alone does not make the Docker API read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import struct
from urllib.parse import quote

BROKER_SOCKET = "/run/th-update-observer.sock"
BROKER_READY = "/run/th-update-observer.ready"
DOCKER_SOCKET = "/run/th-update-docker.sock"
PRODUCT_ROOT = Path("/product-root")
SITE = "toeflhouse.localhost"
TAG = "toefl-house-erp-app:local"
VOLUME = "toefl-house-erp_db-data"
CONTAINERS = {name: "toefl-house-erp-" + name.replace("_", "-")
              for name in ("db", "redis_cache", "redis_queue", "web", "worker", "scheduler", "socketio")}
MAX_BYTES = 1024 * 1024


class ObservationError(Exception):
    """No trustworthy observation is available. Never echo raw Docker output."""


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(DOCKER_SOCKET)


def docker_get(path: str) -> dict:
    # This function is internal. The broker protocol cannot supply its path.
    connection = DockerConnection("localhost", timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        raw = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(raw) > MAX_BYTES:
            raise ObservationError("Docker observation unavailable")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ObservationError("Docker observation malformed")
        return document
    except (OSError, ValueError, http.client.HTTPException):
        raise ObservationError("Docker observation unavailable") from None
    finally:
        connection.close()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_file(path: Path) -> bytes:
    # Every parent below the fixed product mount must be an ordinary directory.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ObservationError("Unsafe installation path")
        if parent == PRODUCT_ROOT:
            break
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ObservationError("Installation file unavailable")
    return path.read_bytes()


def collect() -> dict:
    containers = {name: docker_get("/containers/" + quote(value, safe="") + "/json")
                  for name, value in CONTAINERS.items()}
    web = containers["web"]
    original_id = web.get("Image", "")
    if not isinstance(original_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", original_id):
        raise ObservationError("Installed image unavailable")
    original = docker_get("/images/" + quote(original_id, safe="") + "/json")
    target = docker_get("/images/" + quote(TAG, safe="") + "/json")
    volume = docker_get("/volumes/" + quote(VOLUME, safe=""))
    db_mounts = [item for item in containers["db"].get("Mounts", [])
                 if item.get("Destination") == "/var/lib/mysql"]
    if (len(db_mounts) != 1 or db_mounts[0].get("Type") != "volume"
            or db_mounts[0].get("Name") != VOLUME or volume.get("Name") != VOLUME
            or not volume.get("CreatedAt") or not volume.get("Mountpoint")
            or db_mounts[0].get("Source") != volume["Mountpoint"]):
        raise ObservationError("Database volume identity unavailable")
    # Bind the actual database container as well as the volume metadata. A
    # same-name replacement container or volume must not inherit authorization.
    identity = {"volume": {key: volume.get(key) for key in (
        "Name", "Driver", "Scope", "Mountpoint", "CreatedAt", "Labels", "Options")},
        "database_container": containers["db"].get("Id"), "database_mount": db_mounts[0],
        "web_container": web.get("Id"), "web_mounts": web.get("Mounts"),
        "application_containers": {name: {key: item.get(key) for key in ("Id", "Image", "Mounts")}
                                   for name, item in containers.items() if name != "db"}}
    if not identity["database_container"] or not identity["web_container"]:
        raise ObservationError("Container identity unavailable")
    credentials = read_file(PRODUCT_ROOT / "data/secrets/db.env")
    site_config = read_file(PRODUCT_ROOT / "data/sites" / SITE / "site_config.json")
    journal_path = PRODUCT_ROOT / "data/updates/journal.json"
    if journal_path.exists() or journal_path.is_symlink():
        journal = json.loads(read_file(journal_path))
        if (not isinstance(journal, dict) or journal.get("schema_version") != 1
                or journal.get("document_type") != "toefl-house-erp-update-journal"):
            raise ObservationError("Update journal unavailable")
    else:
        journal = {"phase": "idle"}
    states = {name: item.get("State", {}).get("Status") for name, item in containers.items()}
    labels = original.get("Config", {}).get("Labels")
    if original.get("Id") != original_id or not isinstance(labels, dict):
        raise ObservationError("Installed image identity unavailable")
    return {
        "schema_version": 1,
        "facts": {"disk_free_bytes": shutil.disk_usage(PRODUCT_ROOT).free,
                  "volume_present": True, "volume_verified": True,
                  "services": {key: states[key] == "running"
                               for key in ("db", "redis_cache", "redis_queue", "web")},
                  "image_present": True, "image_id": original_id, "image_labels": labels,
                  "site_credentials_present": True, "site_config_present": True},
        "identity": {"storage_sha256": digest(identity),
                     "credentials_sha256": hashlib.sha256(credentials).hexdigest(),
                     "site_config_sha256": hashlib.sha256(site_config).hexdigest()},
        "tag_image_id": target.get("Id"), "tag_image_labels": target.get("Config", {}).get("Labels"),
        "states": states,
        "journal": {key: journal.get(key) for key in ("phase", "version", "transaction_id")},
    }


def _receive(connection: socket.socket) -> bytes:
    raw = b""
    while b"\n" not in raw and len(raw) <= MAX_BYTES:
        chunk = connection.recv(min(65536, MAX_BYTES + 1 - len(raw)))
        if not chunk:
            break
        raw += chunk
    if len(raw) > MAX_BYTES or not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise ObservationError("Invalid observer protocol")
    return raw[:-1]


def observe() -> dict:
    """Get a fresh root-broker observation; a JSON request cannot replace it."""
    import secrets
    nonce = secrets.token_hex(16)
    try:
        info = os.lstat(BROKER_SOCKET)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0:
            raise ObservationError("Trusted observer unavailable")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(60)
            connection.connect(BROKER_SOCKET)
            # Linux SO_PEERCRED authenticates the broker process, independently
            # of the request file and of ownership of the socket directory.
            _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            if uid != 0:
                raise ObservationError("Trusted observer unavailable")
            connection.sendall(json.dumps({"nonce": nonce}).encode() + b"\n")
            result = json.loads(_receive(connection))
        if (not isinstance(result, dict) or result.get("nonce") != nonce
                or result.get("status") != "ok" or not isinstance(result.get("observation"), dict)):
            raise ObservationError("Trusted observer unavailable")
        return result["observation"]
    except (OSError, ValueError, KeyError):
        raise ObservationError("Trusted observer unavailable") from None


def serve() -> None:
    import pwd
    account = pwd.getpwnam("frappe")
    info = os.lstat(DOCKER_SOCKET)
    groups = os.getgrouplist(account.pw_name, account.pw_gid)
    if (os.getuid() != 0 or not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o006
            or (info.st_gid in groups and info.st_mode & 0o060)):
        raise ObservationError("Docker socket must be inaccessible to the engine account")
    # /run is root-owned and not mounted from the caller's request directory.
    if Path(BROKER_SOCKET).exists():
        raise ObservationError("Observer socket already exists")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(BROKER_SOCKET)
        os.chown(BROKER_SOCKET, 0, account.pw_gid)
        os.chmod(BROKER_SOCKET, 0o660)
        server.listen(1)
        Path(BROKER_READY).touch(mode=0o600)
        while True:
            connection, _address = server.accept()
            with connection:
                connection.settimeout(5)
                try:
                    _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                    request = json.loads(_receive(connection))
                    if (uid != account.pw_uid or not isinstance(request, dict)
                            or set(request) != {"nonce"} or not isinstance(request["nonce"], str)
                            or not re.fullmatch(r"[0-9a-f]{32}", request["nonce"])):
                        raise ObservationError("Invalid observer request")
                    response = {"status": "ok", "nonce": request["nonce"], "observation": collect()}
                except (ObservationError, OSError, ValueError, KeyError, TypeError):
                    response = {"status": "unavailable"}
                try:
                    connection.sendall(json.dumps(response).encode() + b"\n")
                except OSError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", required=True)
    parser.parse_args()
    try:
        serve()
    except (ObservationError, OSError, KeyError):
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
