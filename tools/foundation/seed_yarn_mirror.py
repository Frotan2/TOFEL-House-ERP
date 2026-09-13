#!/usr/bin/env python3
"""Seed a Yarn Classic offline mirror from npm without editing upstream locks.

Only HTTPS registry.yarnpkg.com tarball entries are supported. Every payload is
verified against the strongest supplied integrity hash BEFORE it is written.
Unsupported entries or any failure abort the command; never regenerates a lock.
This is a transport workaround, not an application dependency upgrade.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


HASHES = ("sha512", "sha384", "sha256", "sha1")


def entries_from_lock(text: str) -> list[dict]:
    entries = []
    for block in text.split("\n\n"):
        resolved = re.search(r'^  resolved "([^"]+)"', block, re.MULTILINE)
        if not resolved:
            if re.search(r"^  version ", block, re.MULTILINE):
                raise ValueError("Package entry without a resolved tarball; unsupported lock")
            continue
        url = urlsplit(resolved[1])
        if (url.scheme != "https" or url.netloc != "registry.yarnpkg.com" or url.query
                or ".." in url.path.split("/")):
            raise ValueError("Unsupported tarball origin or path; refusing to rewrite dependency source")
        match = re.fullmatch(r"/(?:(@[^/]+)/)?[^/]+/-/([^/]+\.tgz)", url.path)
        integrity = re.search(r"^  integrity (.+)$", block, re.MULTILINE)
        if not match or not integrity:
            raise ValueError("Unsupported package path or missing integrity hash")
        scope, filename = match.groups()
        name = f"{scope}-{filename}" if scope else filename
        entries.append({"url": "https://registry.npmjs.org" + url.path,
                        "filename": name, "integrity": integrity[1].strip('"')})
    if not entries:
        raise ValueError("No supported lockfile entries found")
    return entries


def verify(data: bytes, integrity: str) -> None:
    supplied = dict(value.split("-", 1) for value in integrity.split())
    algorithm = next((name for name in HASHES if name in supplied), None)
    if not algorithm:
        raise ValueError("No supported integrity algorithm")
    digest = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if digest != supplied[algorithm]:
        raise ValueError("Tarball integrity mismatch")


def seed(lock: Path, mirror: Path) -> dict:
    entries = entries_from_lock(lock.read_text())
    mirror.mkdir(parents=True, exist_ok=True)

    def fetch(entry: dict) -> None:
        with urlopen(entry["url"], timeout=30) as response:
            data = response.read()
        verify(data, entry["integrity"])
        (mirror / entry["filename"]).write_bytes(data)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, entries))
    return {"count": len(entries), "all_integrity_verified": True,
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "duration_seconds": round(time.monotonic() - started, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("mirror", type=Path)
    args = parser.parse_args()
    print(json.dumps(seed(args.lock, args.mirror), indent=2))


if __name__ == "__main__":
    main()
