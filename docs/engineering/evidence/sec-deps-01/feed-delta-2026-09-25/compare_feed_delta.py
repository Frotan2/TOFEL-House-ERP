"""Version-match + alias-compare live GH feed against the 2026-09-23 triage baseline."""
import json, subprocess, sys
sys.path.insert(0, "/tmp/yamlvenv/lib/python3.11/site-packages")
from packaging.version import Version
from packaging.specifiers import SpecifierSet

REPO = "/home/user/TOFEL-House-ERP"
triage = json.load(open(f"{REPO}/docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json"))
triaged = {}
for p in triage["packages"]:
    eco, rest = p["package"].split(":", 1)
    key = eco + ":" + rest
    triaged[key] = {a["id"] for a in p.get("advisories", [])}

rows = [json.loads(l) for l in open("/tmp/adv2/rows.jsonl") if l.strip()]

def npm_match(rng, ver):
    try:
        out = subprocess.run(
            ["node", "-e",
             f"const s=require('/tmp/semverwork/node_modules/semver');"
             f"process.stdout.write(s.satisfies({json.dumps(ver)},{json.dumps(rng)},{{includePrerelease:true}})?'1':'0')"],
            capture_output=True, text=True, timeout=30)
        return out.stdout == "1"
    except Exception as e:
        return None

def pip_match(rng, ver):
    try:
        spec = SpecifierSet(rng.replace(",", ", "))
        return Version(ver) in spec
    except Exception:
        return None

per_pkg = {}
unmatched_evals = []
for r in rows:
    pkgkey = r["pkg"]
    eco, rest = pkgkey.split(":", 1)
    base, _, pinned = rest.partition("@")
    versions = [v.strip() for v in pinned.split(",") if v.strip()]
    if not versions:
        continue
    en = per_pkg.setdefault(pkgkey, {
        "rows": 0, "range_match": [], "covered": [], "new": [], "eval_failed": []})
    en["rows"] += 1
    # version-range test against EVERY pinned version of that package
    hit = None
    for v in versions:
        m = npm_match(r["range"], v) if eco == "npm" else pip_match(r["range"], v)
        if m:
            hit = v
            break
        if m is None:
            unmatched_evals.append((pkgkey, v, r["range"]))
    if hit is None:
        continue
    en["range_match"].append(r)
    aliases = {r["ghsa"], *r.get("cve", [])}
    if aliases & triaged.get(pkgkey, set()):
        en["covered"].append(r)
    else:
        en["new"].append(r)

print("=== per-package: current-feed rows / range-matching pinned / covered-by-triage / NEW ===")
total_new = 0
for k in sorted(per_pkg):
    en = per_pkg[k]
    flag = "  <-- REVIEW" if en["new"] else ""
    print(f"{k}: feed={en['rows']} matched={len(en['range_match'])} covered={len(en['covered'])} new={len(en['new'])}{flag}")
    total_new += len(en["new"])
print("\nTOTAL NEW (range-matching, not aliased in triage):", total_new)
for k in sorted(per_pkg):
    for r in per_pkg[k]["new"]:
        print(f"\nNEW {k}: {r['ghsa']} {r.get('cve')} {r['severity']} published={r['published'][:10]}")
        print(f"  range={r['range']!r} patched={r['patched']!r}")
        print(f"  {r['summary']}")
print("\neval failures:", len(unmatched_evals))
for e in unmatched_evals[:10]:
    print("  ", e)
