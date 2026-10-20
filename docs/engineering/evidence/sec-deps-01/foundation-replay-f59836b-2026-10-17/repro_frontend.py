"""Re-run the hosted frontend advisory triage against the pinned education lockfile.

Reproduces the inventory of `hosted-frontend-advisory-audit` from the upstream lockfile of
frappe/education at the pinned commit, queries the same npm bulk advisory endpoint the audit
uses, and applies the repo's own triage (tools/foundation/advisory_triage.py).

It is an approximation of the bench inventory: the bench node_modules tree is not rebuilt here.
Run from the repository root:  python3 docs/engineering/evidence/sec-deps-01/foundation-replay-f59836b-2026-10-17/repro_frontend.py
"""
import base64
import json
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/foundation"))
import advisory_triage as at  # noqa: E402

EDUCATION_COMMIT = "93bc7075753369457919720690f80c6d2207b5f2"
BULK = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"


def fetch_lock() -> str:
    url = (f"https://api.github.com/repos/frappe/education/contents/frontend/yarn.lock"
           f"?ref={EDUCATION_COMMIT}")
    with urllib.request.urlopen(url, timeout=120) as response:
        body = json.load(response)
    return base64.b64decode(body["content"]).decode("utf-8")


def inventory(lock_text: str) -> dict:
    versions: dict[str, set[str]] = defaultdict(set)
    header = None
    for line in lock_text.splitlines():
        if line and not line.startswith((" ", "#")) and line.endswith(":"):
            header = line[:-1]
            continue
        match = re.match(r'^  version "([^"]+)"', line)
        if match and header:
            first = header.split(", ")[0].strip('"')
            if first.startswith("@"):
                name = "@" + first[1:].rsplit("@", 1)[0]
            else:
                name = first.rsplit("@", 1)[0]
            versions[name].add(match.group(1))
    return {name: sorted(found) for name, found in sorted(versions.items())}


def main() -> int:
    inv = inventory(fetch_lock())
    request = urllib.request.Request(BULK, data=json.dumps(inv).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    advisories = json.load(urllib.request.urlopen(request, timeout=120))
    result = at.triage_npm(advisories)
    print(f"packages submitted: {len(inv)}; packages with advisories: {len(advisories)}")
    print(f"advisory entries: {len(result['findings'])}; closed: {result['closed']}; "
          f"open: {result['open']}; untriaged: {len(result['untriaged'])}")
    print("dispositions:", dict(Counter(f["disposition"] for f in result["findings"])))
    for f in result["findings"]:
        if f["disposition"] not in at.CLOSED_DISPOSITIONS:
            print("NON-CLOSED:", f["package"], f["id"], f["severity"], f["disposition"])
    for u in result["untriaged"]:
        print("UNTRIAGED:", u["package"], u["id"], u["severity"], u["title"][:100])
    return 0 if not result["untriaged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
