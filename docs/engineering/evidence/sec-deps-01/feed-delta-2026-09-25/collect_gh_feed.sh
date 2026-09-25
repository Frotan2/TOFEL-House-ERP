#!/bin/bash
set -u
mkdir -p /tmp/adv2
: > /tmp/adv2/rows.jsonl
: > /tmp/adv2/raw.jsonl
Q='query($ec:SecurityAdvisoryEcosystem,$pk:String){securityVulnerabilities(first:100,ecosystem:$ec,package:$pk){nodes{vulnerableVersionRange severity firstPatchedVersion{identifier} advisory{ghsaId publishedAt identifiers{type value} summary}}}}'
while IFS='|' read -r eco base full; do
  case "$eco" in npm) E=NPM;; py) E=PIP;; *) continue;; esac
  resp=$(gh api graphql -f query="$Q" -F ec="$E" -F pk="$base")
  echo "$resp" >> /tmp/adv2/raw.jsonl
  python3 - "$eco" "$full" "$resp" >> /tmp/adv2/rows.jsonl <<'PY'
import sys, json
eco, full = sys.argv[1], sys.argv[2]
resp = json.loads(sys.argv[3])
for n in resp.get("data", {}).get("securityVulnerabilities", {}).get("nodes", []):
    a = n["advisory"]
    print(json.dumps({"pkg": eco + ":" + full, "ghsa": a["ghsaId"], "published": a["publishedAt"],
                      "cve": [i["value"] for i in a["identifiers"] if i["type"] == "CVE"],
                      "range": n["vulnerableVersionRange"], "severity": n["severity"],
                      "patched": (n.get("firstPatchedVersion") or {}).get("identifier"),
                      "summary": a["summary"]}))
PY
done < /tmp/packages2.txt
echo "rows: $(wc -l < /tmp/adv2/rows.jsonl)"
