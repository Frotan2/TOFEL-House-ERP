#!/usr/bin/env python3
"""Read-only observer qualification inside the disposable product CI image.

The caller mounts only this public probe, the synthetic product folder (ro),
and the real daemon socket for the root broker. No site/service is modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, "/product")
import update_host as host  # noqa: E402


def client() -> None:
    assert os.getuid() != 0, "the engine-side probe must be unprivileged"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw:
        try:
            raw.connect(host.DOCKER_SOCKET)
        except PermissionError:
            pass
        else:
            raise AssertionError("the engine can reach the privileged Docker API")
    observed = host.observe()
    assert observed["schema_version"] == 1
    assert observed["facts"]["volume_verified"] is True
    assert observed["tag_image_id"] == observed["facts"]["image_id"]
    assert observed["tag_image_labels"] == observed["facts"]["image_labels"]
    assert observed["states"] == {key: "running" for key in host.CONTAINERS}
    assert all(len(value) == 64 for value in observed["identity"].values())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(host.BROKER_SOCKET)
        connection.sendall(json.dumps({"nonce": "f" * 32, "path": "/containers/create",
                                       "method": "POST"}).encode() + b"\n")
        assert json.loads(host._receive(connection)) == {"status": "unavailable"}
    print("PASS: real hosted Docker identity; authenticated root broker; raw API and arbitrary commands denied")


def main() -> int:
    if sys.argv[1:] == ["--client"]:
        client()
        return 0
    if sys.argv[1:]:
        raise SystemExit("unsupported probe arguments")
    assert os.getuid() == 0, "the observer parent must start as root"
    process = subprocess.Popen([sys.executable, "/product/update_host.py", "--serve"])
    try:
        for _ in range(100):
            if Path(host.BROKER_READY).exists():
                break
            if process.poll() is not None:
                raise AssertionError("the root observer failed its socket permission preflight")
            time.sleep(0.05)
        else:
            raise AssertionError("the root observer did not become ready")
        subprocess.run(["su", "-s", "/bin/sh", "frappe", "-c", "exec python3 /probe.py --client"],
                       check=True, timeout=90)
    finally:
        process.terminate()
        process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
