# D8 operational-input packet

**Date:** 2026-09-16
**Status:** **OPEN — production remains REJECT.**

This is the smallest owner/infrastructure packet required to turn the repository's
synthetic evidence into a proposed production-operation plan. It is deliberately a
request for decisions and evidence, not an operating procedure, approval, or
assignment. Do not put credentials, private keys, backups, customer data, or named
people in this repository.

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

## Inputs required from the owner/contract holder

For every row, the response may identify an accountable organization, contract role,
or approved authority reference; a person name is neither requested nor inferred.
Values that are not yet selected can be marked **not selected**. That leaves the
related gate open.

## D8 disposition matrix

| D8 decision area | Current disposition | Boundary |
|---|---|---|
| Role-based operational ownership charter | **SELECTED / DELIVERED** — owner decision D8 as recorded in `OWNER-DECISIONS.md`; T5 derives responsibility slots from shipped code | This selects a reviewable role/responsibility model only. It does not assign people, providers, contracts, service levels, or production authority. |
| Accountable production operating/recovery authority | **NOT SELECTED** | No accountable authority or escalation authority has been supplied. |
| Production hostname, topology and trust boundary | **NOT SELECTED** | No hostname, DNS, proxy, TLS custody, origin policy, or network placement has been approved. |
| Durable state, files, backup destination and key custody | **NOT SELECTED** | No MariaDB/Redis/files/configuration/key storage or backup destination/retention model has been selected. |
| RPO/RTO, capacity and availability objectives | **NOT SELECTED** | No recovery, concurrency, scale, availability, or capacity target has been supplied. |
| Monitoring, alerting, incident and change/rollback controls | **NOT SELECTED** | No alert receiver, retention target, incident authority, release approver, or rollback criterion has been selected. |

The detailed response/evidence contract remains below. **NOT SELECTED** is an
explicit current disposition, not a default and not an engineering recommendation.

| Required input | Minimal response needed | Required evidence before the gate can close |
|---|---|---|
| Operational accountability | An accountable authority for production change approval, service operation, security incident decision, and recovery authorization; escalation authority may be the same or distinct. | A non-secret ownership/escalation record approved by that authority. |
| Deployment and trust boundary | Approved production hostname/DNS ownership, network/reverse-proxy placement, TLS certificate custody/renewal authority, allowed origins, and the boundary between public, application, database, Redis, worker/scheduler, realtime, and file-storage services. | A topology/configuration record plus deployed edge tests for TLS, Secure-cookie/session behavior, origins/headers/CSRF, private-file routing, and realtime authentication. |
| Durable-state and file-storage design | The selected persistence/storage locations and durability responsibility for MariaDB, Redis queues/cache, site configuration, encryption keys, private files, and public assets. | A deployed configuration review and controlled loss/restart evidence proving the selected durability behavior. |
| Backup and key custody | Backup destination and retention authority; encryption/key-custody and retrieval authority; who may authorize restoration; and the intended recovery-point and recovery-time objectives. | An actual encrypted backup, a separate-infrastructure recovery rehearsal, key retrieval under the defined custody model, data/file verification, copied-session revocation check, and measured results against the owner-selected objectives. |
| Service operation and failure detection | The selected monitoring/log/audit retention locations, alert receiver/escalation authority, and incident/recovery decision path for web, database, queues/workers, scheduler, realtime, files, and backup jobs. | Tested failure detection, alert delivery, log/audit retention and rotation/recovery, plus an incident/recovery exercise. |
| Capacity and availability objectives | Representative concurrency, data scale, workload mix, and availability expectation. No numeric target is presumed here. | Controlled database/web/queue/worker/realtime tests measured against those selected objectives, including overload/failure handling. |
| Change, upgrade, and rollback control | Release approver; immutable build/provenance and configuration-promotion method; maintenance/communication authority; rollback decision criteria and supported restore-based fallback. | A controlled full-bundle upgrade rehearsal and supported rollback or restore-based rollback rehearsal in the selected architecture. |
| Security acceptance disposition | A decision on whether unresolved dependencies and security coverage may be remediated, accepted, or otherwise handled. This packet does **not** request a waiver. | Engineering evidence of a coherent maintained dependency migration, clean relevant audits/SBOM, exploit- and integration-specific regressions, plus closure of remaining security gates. |

## Engineering work enabled by those inputs

Once a row is selected, engineering can produce and test only the corresponding
implementation/configuration and evidence: deployment manifests/configuration
handling where approved; edge and session tests; persistence/failure drills;
independent recovery and rollback rehearsals; telemetry/alert tests; and
capacity tests. Until then, synthetic hosted results remain evidence of code paths
only.

## Current D8 blockers

1. No approved production topology, edge/trust boundary, durable-state/file-storage
   design, key custody, backup destination/retention, recovery objectives, or
   accountable operational authority is present in the repository.
2. No separate-infrastructure production-like backup/restore, host-loss, rollback,
   alert-delivery, capacity, or public-edge evidence exists.
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
