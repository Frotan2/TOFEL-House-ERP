"""Export pinned database/cache images on the Linux provider runner."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def export_runtime(compose: Path, output: Path, revision: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("a full source revision is required")
    if output.exists():
        raise ValueError("refusing to overwrite an existing runtime export")
    text = compose.read_text(encoding="utf-8")
    rows = []
    for key, repository, tag, filename in (
        ("db", "mariadb", "toefl-house-erp-db:bundled", "db-image.tar"),
        ("cache", "redis", "toefl-house-erp-cache:bundled", "cache-image.tar"),
    ):
        refs = set(re.findall(r"^\s+image:\s+(" + repository + r"@sha256:[a-f0-9]{64})\s*$", text, re.M))
        if len(refs) != 1:
            raise ValueError("expected exactly one pinned identity per runtime component")
        rows.append((key, refs.pop(), tag, filename))
    output.mkdir(parents=True)
    images = []
    for key, source, tag, filename in rows:
        subprocess.run(["docker", "pull", "--platform", "linux/amd64", source], check=True)
        subprocess.run(["docker", "tag", source, tag], check=True)
        identity = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
        if identity.get("Os") != "linux" or identity.get("Architecture") != "amd64":
            raise ValueError("runtime images must be Linux/amd64")
        archive = output / filename
        subprocess.run(["docker", "save", "--output", str(archive), tag], check=True)
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        images.append({"key": key, "source": source, "tag": tag, "file": filename,
                       "sha256": digest.hexdigest(), "config": identity["Config"],
                       "layers": identity["RootFS"]["Layers"]})
    (output / "offline-runtime.json").write_text(json.dumps({
        "schema_version": 1, "source_revision": revision, "images": images,
    }, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    export_runtime(args.compose, args.output, args.source_revision)


if __name__ == "__main__":
    main()
