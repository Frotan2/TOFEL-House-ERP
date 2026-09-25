# sec-deps-01 — Advisory Feed Delta Re-verification (2026-09-25)

**Register item:** `sec-deps-01` — disposition `EXTERNAL/UPSTREAM BLOCKED` (unchanged).
**Baseline under re-verification:** `per-finding-remediation-analysis-2026-09-23.json`
(full triage of 39 pinned packages / 102 OSV matches, hosted run `35852307687`, 2026-09-23).
**Purpose:** scheduled re-verification between qualification runs — advisories mutate
daily; a new advisory matching the pinned tree would be a regression the gates must see.

## Result

| Check | Outcome |
|---|---|
| Advisory feed rows queried (GitHub Advisory GraphQL, NPM + PIP) | 357 across all 38 pinned packages |
| Advisories whose vulnerable range matches a pinned version | 53 |
| …of those, aliased (GHSA or CVE) to an id already dispositioned in the 2026-09-23 triage | 53 |
| **New applicable advisories not in triage** | **0** |
| Range evaluations that failed (would force manual review) | 0 |
| Newer official Frappe v16 release since triage | none (latest tag remains `v16.35.0` of 2026-09-23; `version-16` branch head 2026-09-22 predates triage) |
| Newer official Bench release since triage | none (`frappe-bench` latest on PyPI remains `5.31.0`) |

**Consequence:** the 2026-09-23 dispositions (FIXABLE fixed / MITIGATED with probe tests /
NOT_REACHABLE with negative tests / BLOCKED where upstream-unreachable) still cover every
advisory that applies to the pinned dependency tree as of 2026-09-25. No code, test, or
disposition change is required. The upstream block itself stands: pinned vendor tree
unchanged, no official release clears it.

## Method (reproducible)

1. **Inventory** — package list + pinned versions taken verbatim from the triage JSON
   (`packages[].package`), i.e. exactly the scope the hosted audit gates on (40 entries,
   38 non-empty package names; npm multi-version pins treated per version).
2. **Feed** — GitHub Advisory Database GraphQL
   (`securityVulnerabilities(ecosystem: NPM|PIP, package: <name>)`, `first: 100`) with
   per-node `vulnerableVersionRange`, `severity`, `firstPatchedVersion`, GHSA id, CVE
   aliases, `publishedAt`. Raw rows preserved at
   `feed-delta-2026-09-25/gh-feed-rows.jsonl`.
3. **Range matching** — npm ranges evaluated with `semver@latest`
   (`satisfies(version, range, includePrerelease)`), PIP ranges with `packaging`
   (`SpecifierSet`) against every pinned version of the package. Script:
   `feed-delta-2026-09-25/compare_feed_delta.py`.
4. **Alias comparison** — a matching advisory counts as covered iff its GHSA id OR any
   of its CVE aliases is present in the triage JSON's per-package advisory ids (the
   triage was id-keyed from OSV: GHSA/PYSEC/CVE mixed namespaces; CVE aliasing bridges
   the namespace gap).
5. **Upstream-release review** (per the register item's standing requirement) — latest
   Frappe GitHub tag on v16 and latest `frappe-bench` on PyPI compared against the
   versions inspected during the 2026-09-23 triage.

## Why dispositions with zero current matches are not contradictions

For some packages (e.g. `engine.io@6.5.4`, `ws@8.11.0`, `socket.io-parser@4.2.4`) the
current GitHub feed reports no vulnerable range matching the pinned version, while the
triage recorded historical OSV ids with runtime dispositions (MITIGATED / NOT_REACHABLE
with probe and negative tests). This reflects OSV vs GHSA range-record differences, not
a conflict: those dispositions and their regression tests remain in force, and nothing
new applies.

## Standing posture

- Hosted audit jobs continue to fail closed on the authoritative inventory; this delta
  check is an additional between-runs verification, not a replacement for the gates.
- Next trigger points: any new Frappe v16 / Bench release, any new range-matching
  advisory id, or the next scheduled re-verification.
- No pins were touched; no vendor code was modified; no lockfiles changed.
