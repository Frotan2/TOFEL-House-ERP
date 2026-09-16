# D8 operational-input packet

**Date:** 2026-09-16
**Status:** **OPEN — production remains REJECT.**

This is the operational qualification packet for turning the repository's
synthetic evidence into a proposed production-operation plan. The owner/business
requirements have now been recorded in the canonical
[`canonical-owner-decision-record.json`](canonical-owner-decision-record.json).
This packet projects those requirements into D8 evidence gates; it is not an
operating procedure, approval, assignment, or production authorization. Do not put
credentials, private keys, backups, customer data, or named people in this repository.

It complements the code-derived [Operational Ownership Charter](OPERATIONAL-OWNERSHIP-CHARTER.md)
and the [production acceptance ledger](foundation-production-acceptance-ledger.json).
It does not reopen completed Placement, Admission, Enrollment, Teaching, Finance,
T3, or T5 scope.

## What engineering has objectively established

| Control | Evidence and boundary |
|---|---|
| Product execution is synthetically contained | `toefl_house.security.require_synthetic()` requires `toefl_house_synthetic_only=1`, `allow_tests=1`, and a designated qualification site. It is a production hard stop, not a deployment configuration. |
| T3 command pages are contained | Hosted run `35073376790` at `3587700110d21816b239779c93c32f4060cd3c63` passed 542/542; it did not add native Education/ERPNext authority. |
| T5 makes code-derived responsibilities reviewable | The charter records shipped role boundaries and the operational responsibility slots; it assigns no human or production service. |
| Foundation runner prerequisites were repeatable on the historical qualification branch | Hosted run `35075532841` at `d84f1c9bdcfe704a2fdcde213e4891b8f49f090b` passed its controlled runner/download/service probe. Its own report sets `phase2_gate_passed: false`; it is not an ERP or production approval. |
| Earlier Foundation recovery evidence is bounded | The acceptance ledger records same-controlled-runner separate-site restore evidence. It explicitly is not independent-host DR, key-custody, retention, RPO/RTO, or production approval. |

### Latest recorded engineering evidence (still synthetic; historical run provenance retained)

| Evidence | Actual observation | Limit that remains |
|---|---|---|
| Active-branch Placement qualification, `35090760614` at `33b86aed6f8ea4b5997c50f0d1173f4f85af6dea` | Hosted runner report passed 101 recorded setup/runtime checks; native report passed **542/542** checks. Checks `104779440466` / `104779438124`; report SHA-256 `9b3348ba2084039c8aec681b4ba4984bdf337fe2acbf772727ce8b35f278675a` / `4c1e79f14c0d2c070bba58fb3d403ac95f60d3ea87af402ab7d8caa6d0caf1d3`. | Synthetic bounded Placement/content-governance evidence only; report explicitly says `production: REJECT`. Artifact ZIP retrieval returned EOF in this environment, so the Checks transport is the preserved evidence source. |
| Latest active-branch Foundation runtime, `35090904508` at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` | **116** restricted checks ran; **114** passed. Checks `104787576338` / `104787579362`; report SHA-256 `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f` / `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`. The full-stack and frontend advisory checks failed; readiness, realtime, upgrade, Guardian browser, frontend graph, restart and scoped recovery probes passed. | **REJECT** evidence. The latest run keeps `phase2_gate_passed` and `security_gate_passed` false. Its advisory matches are not exploitability/reachability proof, a full SBOM, OS/container coverage, or remediation; SEC-DEPS-01 remains UPSTREAM-BLOCKED / REJECT. Production is not authorized. |
| Active-branch Foundation runtime, `35090761035` at `33b86aed6f8ea4b5997c50f0d1173f4f85af6dea` | **116** restricted checks ran; **114** passed. Checks `104781844050` / `104781847090`; report SHA-256 `00eba6adaae7466023ca8793f719a929d6fed948a5afe21820167893ce78c248` / `3ba703f01e0a3125a94d3ce026e9b1173afea0ace764db3d5ed1fa69e988527f`. Readiness, realtime, upgrade, Guardian browser, frontend graph, restart and remaining-gate probes passed; both dependency audits failed. | **REJECT** evidence. The resolved-stack audit found 14 Python OSV findings and 97 npm advisory findings. `phase2_gate_passed` and `security_gate_passed` are false; findings do not establish exploitability/reachability, a full SBOM, OS/container coverage, or remediation. |
| Active-branch frontend candidate review, `35090760597` at `33b86aed6f8ea4b5997c50f0d1173f4f85af6dea` | Frozen baseline and isolated candidate built successfully; both audits failed. Baseline: 57 advisory entries across 21 packages. Candidate: 23 entries across 6 packages. Check `104776513232`; report SHA-256 `5fbd79f48e7264bef20e9294fcff049e3641a775bdb91ef85f92b5c105003466`. | Candidate is not adopted and does not remediate SEC-DEPS-01. Production pins were unchanged. |
| Foundation runtime, `35084695840` at `955e4cd5eedc34b90f4fbfce047339e18558f1f2` | Historical predecessor: **116** restricted checks ran; **114** passed. Its post-build audit recorded the same unresolved dependency class. | Historical evidence remains preserved; the active-branch record above is authoritative for this cycle. |
| Product backup/restore, `35076449739` at `ebe77676fffb3e2e1f0b49cac8e18c5e7763180a` | Native acceptance re-ran **542/542**. `bench backup --with-files` captured SQL, public files, and private files; restoration into `placement-restore.localhost` used a distinct database and credential, then reapplied the site encryption key and non-database test flags. The restore verifier passed representative record count/name-digest comparisons across 14 doctypes and a private File byte SHA-256 check. | The runner report itself says `production: REJECT` and scopes this as disposable synthetic product recovery, **not** full Placement requalification, an offsite backup, real production DR, an RPO/RTO, or availability proof. |
| First product rehearsal, `35075532675` at `d84f1c9bdcfe704a2fdcde213e4891b8f49f090b` | The 542 native checks passed, then Bench backup failed before restoration because the hosted MySQL client attempted its optional `information_schema.COLUMN_STATISTICS` query against pinned MariaDB. | The failure is retained as REJECT evidence. The retry added a local hosted-only `mysqldump` wrapper which adds `--column-statistics=0` only when that client supports the option; it does not change the pinned database or suppress any backup failure. |

The D8 verifier captures representative synthetic product records and a private File
byte digest, invokes `bench backup --with-files`, restores into a separately created
site/database without copying the source database credential, reapplies the site
encryption key and non-database flags, migrates, and verifies counts/name digests and
private-file bytes. This proves that exact disposable code path only; it is not an
offsite or real-infrastructure recovery claim.

## Owner decision record boundary

The owner/business requirements are not repeated as a second decision list here.
The canonical [`canonical-owner-decision-record.json`](canonical-owner-decision-record.json)
is authoritative. Engineering may implement technical mechanisms autonomously, but
must not invent a provider, hostname, destination, person, numeric capacity target,
availability target, or numeric RPO/RTO.

## Canonical actionable D8 decision matrix

The single canonical decision matrix is the machine-readable
[`d8-production-operations-decision-matrix.json`](d8-production-operations-decision-matrix.json).
It is intentionally provider-neutral and records, for every D8 area, the current
disposition, exact owner decision, whether engineering can proceed, work already
allowed, evidence required after selection, acceptance condition, and current gate
state. This document is the explanation and owner-input boundary; it must not
create a second competing matrix.

The explicit current summary is:

- `D8-OWNERSHIP-CHARTER`: **SELECTED / DELIVERED**, scoped **PASS** only.
- `D8-OPS-AUTHORITY`: **SELECTED / BUSINESS INPUT**; the authority roles are
  resolved, but live authorization, incident, recovery, and escalation evidence is
  still **BLOCKED**.
- `D8-TOPOLOGY-EDGE`: **SELECTED / PHASED** for current local/server operation
  through Tailscale; future public hosting values remain unselected and evidence is
  **BLOCKED**.
- `D8-DURABLE-STATE`, `D8-BACKUP-RECOVERY`, `D8-OBSERVABILITY-INCIDENT`, and
  `D8-CHANGE-ROLLBACK`: selected business requirements with implementation/evidence
  **BLOCKED**.
- `D8-CAPACITY-AVAILABILITY`: numeric objective remains **NOT SELECTED** and is
  **BLOCKED**; engineering may baseline without claiming a target.
- `D8-SECURITY-DEPENDENCY`: **UPSTREAM-BLOCKED / REJECT**. No waiver or owner
  override is requested or accepted.

The provider-neutral fail-closed contract template is
[`d8-operational-contract.template.json`](d8-operational-contract.template.json).
Validate it locally with:

```sh
python3 tools/foundation/d8_validate.py \
  --contract docs/engineering/d8-operational-contract.template.json
```

The validator performs release-provenance, branch, ledger, synthetic-hard-stop,
secret-hygiene, contract-schema, and production-enable checks without connecting
to infrastructure. A successful validator run can still report `BLOCKED` or
`REJECT`; that is the intended result while inputs and release gates are open.
The same check runs in `.github/workflows/d8-operations-contract.yml`.

The matrix also contains the release-gate matrix required for final release
review: scoped domain/authorization/realtime passes are explicitly bounded;
recovery, backup/restore, upgrade/rollback, observability, topology/edge,
capacity/availability, durability, and change-control are **BLOCKED**;
SEC-DEPS-01 and overall production authorization are **REJECT**.

## Engineering work enabled by those inputs

Once a row is selected, engineering can produce and test only the corresponding
implementation/configuration and evidence: deployment manifests/configuration
handling where approved; edge and session tests; persistence/failure drills;
independent recovery and rollback rehearsals; telemetry/alert tests; and
capacity tests. Until then, synthetic hosted results remain evidence of code paths
only.

## Current D8 blockers

1. The current local/server and Tailscale deployment decision, role authority map,
   data-preservation priority, encrypted multi-version backup requirement, recovery
   requirement, auditability, and health/attention visibility are recorded. The
   provider-neutral future internet topology and future off-site destination remain
   unselected by design; engineering must not invent them.
2. No separate-infrastructure production-like backup/restore, host-loss, rollback,
   alert-delivery, capacity, branch-isolation, or public-edge evidence exists. All
   selected D8 operational areas therefore remain evidence-gated and BLOCKED.
3. `SEC-DEPS-01` remains **UPSTREAM-BLOCKED / REJECT**. Latest active-branch runtime
   `35090904508` at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` has a failed
   post-build resolved-tree audit: 14 Python OSV finding records across four
   packages and 97 npm advisory entries across 21 package names. The exact
   active-run report is preserved by Checks `104787576338` / `104787579362` and
   SHA-256 `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f` /
   `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`.
   It covers neither OS packages nor container CVEs and establishes no
   exploitability/reachability. The active-branch Education frontend comparison
   `35090760597` built both profiles but both audits failed: baseline 57 advisory
   entries across 21 packages, candidate 23 across 6. The candidate is not
   adopted. The official-candidate review found no credible released input to
   test without unsafe overrides; exact blockers and the smallest viable upstream
   change are retained in
   [`dependency-remediation-candidate-assessment-2026-09-16.json`](evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json).
   This is rejection evidence, not a partial pass or a waiver.
4. `SEC-GUARDIAN-01` and `SEC-RT-TASK-01` remain tracked by the acceptance ledger;
   D8 does not convert their bounded evidence into production authorization.
5. The synthetic-only application guard remains enabled and must not be relaxed
   merely because this packet is completed.

**Verdict:** no product deployment is authorized. Production remains **REJECT**
until every applicable acceptance-ledger and D8 gate is actually evidenced in the
owner-selected architecture.
