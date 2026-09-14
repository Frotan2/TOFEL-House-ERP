#!/usr/bin/env python3
"""Publish a small, sanitized runner report through the GitHub Checks API.

The normal artifact remains authoritative for full logs. This transport exposes
reviewed synthetic qualification results when artifact download hosts are blocked.
Never point this at site config, backups, credentials or real business data.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--name", default="Foundation runner evidence")
    args = parser.parse_args()
    # Explicitly authorized hosted session branches: the previous session branch
    # and the current placement build session branch.
    if os.environ.get("GITHUB_REF") not in (
            "refs/heads/arena/01a09bf3-tofel-house-erp",
            "refs/heads/arena/01a0a055-tofel-house-erp"):
        raise SystemExit("Evidence publication is restricted to the authorized branch")
    raw = args.report.read_bytes()
    report = json.loads(raw)
    # Lossless compact transport; no observations are removed to meet the cap.
    raw = json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode()
    transport = raw
    if len(raw) > 58000:
        # Lossless deterministic encoding, never truncate failed observations.
        transport = json.dumps({"encoding":"gzip+base64", "report_sha256":hashlib.sha256(raw).hexdigest(),
                                "data":base64.b64encode(gzip.compress(raw, mtime=0)).decode()},separators=(",", ":")).encode()
    if len(transport) > 58000:
        raise SystemExit("Encoded report too large; retain full artifact")
    summary = ("Qualification evidence only; no full-stack approval. "
               "Report SHA-256: " + hashlib.sha256(raw).hexdigest())
    payload = {
        "name": args.name,
        "head_sha": os.environ["GITHUB_SHA"],
        "status": "completed",
        "conclusion": "success" if report.get("status") == "pass" else "failure",
        "output": {"title": args.name, "summary": summary,
                   "text": "```json\n" + transport.decode() + "\n```"},
    }
    request = Request(
        "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + "/check-runs",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    print("Published check:", result["id"])


if __name__ == "__main__":
    main()
