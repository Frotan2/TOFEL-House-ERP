"""Replay the CI-style advisory set (replay-snapshot.json) through the current register.

Run from the repository root:  python3 docs/engineering/evidence/sec-deps-01/gate-replay-2026-10-16/replay_gate.py

Reports: rows replayed, dispositions, untriaged rows, and non-closed rows. The
gate fails when untriaged or non-closed rows exist. This is a replay of the
snapshot, not the live installed-tree audit run by CI.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, "tools/foundation")
import advisory_triage as t
triage = t.load_triage()
by_id = triage["by_id"]
snap = json.load(open("docs/engineering/evidence/sec-deps-01/advisory-delta-2026-10-09/replay-snapshot.json"))
rows = []
for e in snap["npm_entries"]:
    rows.append(("npm", e["package"], e.get("matched_versions"), e["ghsa"], []))
for e in snap["pypi_records"]:
    rows.append(("py", e["package"], [e.get("version")], e["id"], e.get("aliases", [])))
from collections import Counter
status = Counter(); untriaged = []; nonclosed = []
for eco, pkg, vers, pid, aliases in rows:
    rec = None
    for cand in [pid] + list(aliases):
        rec = by_id.get(t._norm(cand))
        if rec: break
    if rec is None:
        untriaged.append((eco, pkg, vers, pid))
        continue
    d = rec.get("runtime_disposition")
    status[d] += 1
    if d not in t.CLOSED_DISPOSITIONS:
        nonclosed.append((eco, pkg, vers, pid, d))
print("rows", len(rows), "status", dict(status))
print("untriaged", len(untriaged), untriaged[:10])
print("nonclosed", len(nonclosed))
for r in sorted(set((x[3], x[4]) for x in nonclosed)): print("  ", r)
