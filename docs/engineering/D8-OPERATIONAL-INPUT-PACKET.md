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
| Foundation runner prerequisites are repeatable on the active session branch | Hosted run `35075532841` at `d84f1c9bdcfe704a2fdcde213e4891b8f49f090b` passed its controlled runner/download/service probe. Its own report sets `phase2_gate_passed: false`; it is not an ERP or production approval. |
| Earlier Foundation recovery evidence is bounded | The acceptance ledger records same-controlled-runner separate-site restore evidence. It explicitly is not independent-host DR, key-custody, retention, RPO/RTO, or production approval. |

### Current-branch engineering evidence (still synthetic)

| Evidence | Actual observation | Limit that remains |
|---|---|---|
| Foundation runtime, `35076449577` at `ebe77676fffb3e2e1f0b49cac8e18c5e7763180a` | 115 restricted checks ran; 114 passed. Readiness, realtime, upgrade, Guardian browser, frontend graph, restart, encrypted backup/restore and the remaining-gate probes ran; the one failing restricted check was the frontend advisory audit. | The workflow and its `Foundation runtime evidence` / `Foundation remaining gate evidence` Checks are **failure/REJECT** evidence; `phase2_gate_passed` and `security_gate_passed` are both false. It is not a production deployment. |
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
3. `SEC-DEPS-01` remains a failure: the active-branch frontend comparison run
   `35075532676` at `d84f1c9bdcfe704a2fdcde213e4891b8f49f090b` built both profiles
   but both audits failed. The frozen baseline has 57 advisory matches across 21
   packages; its isolated candidate has 23 matches across 6 packages, removes 35
   baseline matches, and introduces one. The candidate is not adopted. This is
   rejection evidence, not a partial pass or a waiver.
4. `SEC-GUARDIAN-01` and `SEC-RT-TASK-01` remain tracked by the acceptance ledger;
   D8 does not convert their bounded evidence into production authorization.
5. The synthetic-only application guard remains enabled and must not be relaxed
   merely because this packet is completed.

**Verdict:** no product deployment is authorized. Production remains **REJECT**
until every applicable acceptance-ledger and D8 gate is actually evidenced in the
owner-selected architecture.
