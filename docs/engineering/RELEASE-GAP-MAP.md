# TOEFL House ERP — Release Gap Map & Execution Plan

Date: 2026-09-16 · Gap-closure addendum: 2026-09-18 (ERP semantic reconciliation) · Role: technical &
product release leader · Active branch: `arena/01a0ba0d-tofel-house-erp`
**Production remains REJECT. Nothing is deployed. No qualified domain is
reopened. No business rule, price, grading policy or legal/tax assumption
is invented anywhere in this plan.**

## 0. Verified current state (evidence, not narrative)

> **Canonical remaining-blockers matrix:** see
> [PRODUCTION-READINESS-CLOSURE-2026-09-17.md](PRODUCTION-READINESS-CLOSURE-2026-09-17.md).
> It reconciles all 14 D8 release gates against hosted evidence at commit
> `da8b36a` — status, exact run/check, what is proven, what is not, and the
> precise condition required to close each. Outcome: **NO-GO**, production
> **REJECT**, D8 **BLOCKED**, SEC-DEPS-01 unchanged.

- **Branch-boundary rotation (2026-09-17).** The Arena session branch changed, so
  the canonical pin, all 10 workflow filters, the current-status headers, the
  governance JSON `active_branch` fields and the qualification tests were rotated
  in one change. At that moment no hosted workflow had run on the active branch,
  so `hosted_execution_state` was recorded as the explicit, validated absence
  `NOT_EXECUTED_ON_THIS_BRANCH` carrying no run/check/commit/report identity, and
  `tools/foundation/d8_validate.py` failed closed if any was attached — so an
  older branch's run could not be re-labelled as an execution here. Full findings:
  [ENGINEERING-REVIEW-2026-09-17.md](ENGINEERING-REVIEW-2026-09-17.md).
- **The active branch has since been executed, and it rejected (2026-09-17).** All
  five named hosted workflows were genuinely re-executed at commit
  `e8da889b22589a5d64f7843ecaf5d11d9260424c`, so `hosted_execution_state` is now
  `EXECUTED` and `session_branch.ACTIVE_RUNTIME_RUN` pins the real run
  `35218007937`. `validate_active_branch_qualification()` asserts both the
  `fail_reject` status and that exact run id, so the pin cannot be swapped for a
  passing run. **Foundation runtime rejected on SEC-DEPS-01** (119/121 checks
  pass; `hosted-full-stack-dependency-audit` and `hosted-frontend-advisory-audit`
  fail) — precisely the outcome predicted before re-execution. The
  `NOT_EXECUTED` guards were not deleted: they are still exercised by forcing that
  state, so a future rotation back to it stays fail-closed. Runs belonging to
  earlier session branches remain historical provenance.
- **Working tree is green and now gated.** `python3 -m unittest discover -s tests
  -t .` passes 665/665 (it was 629 with **2 failures** before the rotation),
  `ruff check .` is clean under a no-suppression `E9,F` ruleset, both Node suites
  pass, and `d8_validate.py` exits 0 with D8 BLOCKED / production REJECT. New
  `.github/workflows/owned-suite.yml` runs that whole set on every push to the
  active branch **and on every pull request** — no workflow previously triggered
  on `pull_request`, and no single run previously exercised the whole owned tree.
- Five domains CLOSED / QUALIFIED on the hosted synthetic runner:
  Placement `34932512626` (332/332, `4571e6c`), Admission `34941341845`
  (397/397, `4da6f1b`), Enrollment `34946981784` (425/425, `756614e`),
  Teaching `34966681820` (483/483, `6ba5663`), Finance `34999987969`
  (517/517, `e73abef`).
- A13 bypass-route containment demonstrated for the implemented slices:
  run `35008705885` (523/523, `5b5a044`, report SHA-256
  `a66a1b5d5dd2793a1e43bf6b90610a79f3afeda4d789c7d7b562e1fce3176f89`) —
  see [CONTAINMENT-A13.md](../domain/CONTAINMENT-A13.md).
- The current **542-check** suite is a single connected end-to-end lifecycle
  proof (placement → admission → enrollment → teaching → finance → containment
  → release surfaces), re-executed on every code push. Recorded hosted run
  `35073376790` at `3587700110d21816b239779c93c32f4060cd3c63` passed 542/542,
  including the T3 Page records/assets, role visibility and no-escalation
  checks. Integration is continuously proven, not separately asserted.
- Foundation pins (docs/engineering/foundation-version-matrix.json):
  frappe v16.33.1 `988e54f3c4c2`, erpnext v16.34.2 `4048fb70e14d`,
  education v16.1.0 `93bc7075`, hrms v16.18.1.
- App assembly: 15 TH placement doctypes + `TH Admission Decision` +
  shared receipt/audit ledger; 23 role fixtures (18 operational/auditor roles plus five governance roles); 2 Custom Fields;
  command-only guards pinned on three lifecycle seams for seven
  doctypes; command surfaces for all five domains; owned indexes at
  install. No parallel masters, ledgers or UI stack.
- Phase 2 production ledger (2026-09-14,
  foundation-production-acceptance-ledger.json): REJECT; scoped passes
  for web/worker restart, scheduler, framework patch upgrade, hardened
  restore; open items SEC-DEPS-01, SEC-GUARDIAN-01, SEC-RT-TASK-01 and
  deployment-scope operations.
- **Current active-branch hosted execution (`d7df9ca7`, branch
  `arena/01a0aafe-tofel-house-erp`, real Docker 28.0.4 / Compose 2.38.2 on
  ubuntu-24.04 image `20260907.300.1`):** runner qualification `35122242676`
  **passed** 18/18 (pinned MariaDB digest `sha256:8b5f33eb…` healthy in 5 polls
  with version, `utf8mb4/utf8mb4_unicode_ci` and a transaction/rollback count-0
  proof; pinned Redis digest `sha256:75934ddb…` PING/PONG and version);
  placement `35122242728` **passed** 542/542 native checks and 101/101 runner
  steps including a real backup → separate-site/separate-database restore →
  integrity verification; Foundation runtime `35122242581` **failed** with 114 of
  116 restricted checks passing and both dependency audits failing; frontend
  candidate `35122242647` **failed** and is **not adopted**; D8 contract
  `35122242888` **passed structurally** while reporting BLOCKED/REJECT. Probe-by-probe
  classification: [production-like execution ledger](evidence/production-like-execution/execution-ledger.json).
  The local sandbox that requested this pass has **no Docker Engine or Compose and
  cannot install them**, recorded as
  [ENVIRONMENT-BLOCKED](evidence/production-like-execution/local-runner-capability-probe.json);
  no local preflight result was substituted for execution evidence.
- Prior-branch provenance (not an execution on the active branch): Foundation run
  `35090904508` at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47` on
  `arena/01a0a9f7-tofel-house-erp` ran 116 restricted checks; 114
  passed. Its post-build full-stack resolved-tree audit recorded 14 PyPI/OSV
  findings across four packages and 97 npm advisory findings; the full-stack and
  Education frontend audits failed. Runtime/remaining-gate Checks `104787576338` /
  `104787579362` have SHA-256 `08b0453bf78adfc7096dbef3535877feedbb415da31407b5aa77d497b1f86b3f` /
  `3e229cb48c15c8a73d465b82d3f73bbca02f69ba8112b0bddae1e56f2e4cf1aa`. Both Phase 2
  and security gates remain false; this is not OS-package, container-CVE,
  exploitability/reachability, full-SBOM, or production evidence.
- D8 engineering now has a hosted disposable product SQL/public-files/private-files
  backup and distinct-site restore rehearsal: run `35076449739` at `ebe7767`
  passed its 542 native checks and restore verifier. This does not reopen a
  qualified domain, and on its own it did not satisfy independent-host
  recovery; a destructive independent-system rehearsal was later executed at
  the separate-VM level (run `35170062251`, §1.6 and report §10), while
  production recovery remains unproven. Exact
  boundary, retained initial failure, and remaining owner inputs:
  [D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md).

## 1. Classification of everything that remains

### 1.1 Already fully provided natively (no work; cite in RC dossier)
Student/Applicant identity records, programs/courses/terms catalog,
Program/Course Enrollment lifecycle, Student Group/Course Schedule/
Student Attendance, Fees/Sales Invoice/Payment Entry/GL money chain,
Fee Structure/Category price configuration, Item/Price List/Pricing
Rule, Customer/Company/COA, Desk permission model incl. User
Permissions, Version/audit trail, Email Queue/Notification engine,
backup/restore tooling, scheduler/RQ. Verified by the domain closure
runs, which exercised these authorities directly.

### 1.2 Configuration / assembly only (engineer-executable now)
| ID | Item | Treatment | Status |
|---|---|---|---|
| R1 | Role-scoped Desk workspaces (navigation; grants no read). Pinned visibility model (frappe `988e54f3c4c2` `desktop.py Workspace.__init__` + `utils/user.py allow_modules`): reachable only when the workspace's module holds a doctype the user can natively read/write/create, then Has-Role scopes it. Shipped surfaces match who actually has native reads under A13 containment: **TH Receipts** (module Placement; five auditor roles — they read the TH operations ledger) and **TH Finance** (module Accounts; Finance Officer via native Accounts User reads; cards include the R2 registers). API-first operational roles (invigilator, author, admission/enrollment/teaching staff) have existing, narrowly scoped TH-DocType reads, further constrained by `policy.can_read`; no native Education/ERPNext CRUD authority is granted. The pinned Workspace/module gate did not produce a compliant staff Workspace, so a separately Page-gated command surface is the selected D10(ii) path and must not widen authority | Native `Workspace` module files, explicit roles | **CLOSED** — run 35049742120 @ 69a8a95, 530/530; checks `release-workspace-*` (+ `release-probe-users-restored`) |
| R2 | Factual operations registers (tuition billing, placement billing) as role-restricted native Query Reports — raw facts only, no denominators/thresholds (metrics layer is A12, owner stewards). Native access model: Report Has-Role table gates execution (pinned `Report.is_permitted`), ref-doctype `report` permission gates the query surface (pinned `query_report._run`). Attendance-coverage register awaits D9 (no narrow teaching role holds the native `report` flag on Student Attendance; widening options are owner decisions) | Native `Report` module files (`finance/report/…`) + minimal report-only grants on the TH operations doctype | **CLOSED (registers shipped)** — run 35049742120 @ 69a8a95, 530/530; checks `release-registers-*`; attendance register remains gated by D9 |
| R3 | Export/attachment/print-path containment proofs for the guarded doctypes (addresses ledger "broad roles/attachment/export/print paths" for implemented slices) + native health/error-observability probes. Proven against pinned core behavior (`988e54f3c4c2`): private attachments on the guarded ledger resolve through the parent-document permission fallback (auditor reads; invigilator/outsider denied on `File.has_permission` and `is_downloadable`); list/export reads via the `db_query` permission layer leak nothing to non-member roles; `download_pdf` denied via `validate_print_permission`. Observability: native Error Log roundtrip (persist→retrieve→cleanup), active Scheduled Job Type registry, health ping | Hosted negative checks | **CLOSED** — run 35053305607 @ 46e5040, 533/533; checks `release-attachment-paths-guarded`, `release-read-export-print-paths-denied`, `release-observability-probes` |

**Integration note (proven by hosted diagnostics, run 35048606232):** the
education app's `after_install` creates Custom DocPerm rows on Sales Invoice
(Student invoice access). Under the pinned `frappe.permissions.get_valid_perms`,
any Custom DocPerm on a doctype replaces its standard permission rows entirely,
so native Accounts-role reads on Sales Invoice are void site-wide after
education installs. R2 register gates avoid the dependency (Fees and the TH
operations doctype carry their own permission rows), and the TH Finance
workspace's module gate is fed by the officer's untouched Payment Entry read.
Any future surface that assumes native Sales Invoice reads must re-check this.

### 1.3 Genuinely requires further implementation (only behind owner decisions)
Academic assessment & progression (B04/B05 → A06); payroll input path
(B08 → A09); refund/credit-note command surface (owner refund terms);
identity/guardian lifecycle (B01/B02 → A02/A03); calendar/repeat/
transfer/withdrawal (B03 → A05/A11); payment gateway (B12). None may be
started without the named decision — building any of them now would
invent business rules.

### 1.4 Business-policy gates blocking release (precise owner asks)
| Gate | Exact decision required | Unblocks |
|---|---|---|
| D1 = B04/B05 | Level vocabulary, sections/components, rubrics/units/cutoffs, course-mapping; academic grading scales & progression | A06 assessment slice |
| D2 = B08 | Employment classification, pay basis, payable units, statutory rules; single native payroll input path | A09 |
| D3 | Refund/cancellation/credit-note terms (who approves, windows, partial refunds) | Finance correction command surface |
| D4 = B01/B02 | Identity/merge/activation policy; guardian delegation & pre-admission proxy rules | A02/A03 + SEC-GUARDIAN-01 closure |
| D5 = B03 | Real intake calendars, same-term repeat requirement, transfer/withdrawal semantics with history preservation | A05/A11 |
| D6 = B07 remainder/B12 | Tax configuration policy; payment-gateway selection (or explicit none) | Tax setup, payments |
| D7 = A12 stewards | Named metric stewards; denominators/disclosure/retention rules | Reporting metrics layer (over R2 registers) |
| D8 | [Canonical D8 decision matrix](d8-production-operations-decision-matrix.json), [canonical owner-decision record](canonical-owner-decision-record.json), [operational qualification packet](D8-OPERATIONAL-INPUT-PACKET.md), and [final evidence closure report](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md): selected authority roles, current local/Tailscale boundary, local state, encrypted versioned backup/recovery requirement, preservation priority, audit/health visibility, and change responsibility; numeric capacity/availability remains unresolved | Bounded encrypted backup/restore, preservation, offboarding, audit, alert fail-closed and rollback proofs are reproducible. Selected-operation implementation and independent evidence remain **BLOCKED**; production remains **REJECT** |
| D9 | Attendance-coverage register access anchor: native `report` flag on Student Attendance belongs to Academics User/Student/Guardian only. Options (owner picks): (a) grant teaching roles native Academics User — widens direct write access beyond the guarded teaching API; (b) Custom DocPerm replication on Student Attendance — invasive, replaces native permission rows wholesale; (c) new TH anchor doctype for teaching facts; (d) no register (current state — teaching facts reachable via guarded APIs only) | TH Attendance Coverage Register (R2 remainder) |
| D10 | Desk workspaces for API-first staff roles (invigilator, placement author/publisher, admission, enrollment, teaching): the pinned frappe module-visibility gate makes workspaces reachable only for users with at least one native document read in the workspace's module. Their existing TH-DocType reads remain narrowly contained by `policy.can_read`, and no native Education/ERPNext read should be added. The pinned Workspace/module-gate composition did not yield a compliant staff Workspace; D10(ii) selects a role-gated native Page surface per role with no authority change. **T3 is shipped and qualified** in run `35073376790` @ `3587700` (542/542): Page roles/assets, 12 member audiences + seven non-members, and no native-read escalation. | Staff-facing native Page navigation |

### 1.5 Security gates (non-owner parts vs upstream/owner parts)
- **Closed here:** A13 implemented-slice containment (523/523).
- **SEC-DEPS-01** (resolved dependency advisories): re-executed on the current
  active branch — hosted runtime `35122242581` at
  `d7df9ca766cd3039d68051ca83cdc8be5e834452` again reports 14 PyPI/OSV finding
  records across `pdfkit`, `pypdf`, `setuptools` and `weasyprint` from 161
  inventoried Bench Python package names, plus 57 npm advisory findings (27 high,
  26 moderate, 4 low) across 21 of 255 queried package names in 572 supplied
  installed Node package names; both the full-stack and Education frontend
  advisory checks fail (runtime Check `104889030990`, remaining-gate Check
  `104889035777`; report SHA-256 values are recorded in
  `foundation-production-acceptance-ledger.json`). The frontend candidate review
  `35122242647` also failed and the candidate is **not adopted**. Prior-branch
  provenance: run `35090904508` at `6e7ccb99fc9d5f80fe550aa187787c56d72fea47`,
  Checks `104787576338` / `104787579362`.
  A coherent maintained upstream stack migration and clean re-run are required;
  patching the pinned upstream bundle in-repo would invent a fork. The audit
  explicitly does not cover OS packages or container image CVEs, and does not
  establish exploitability/reachability, an SBOM, or production acceptance.
  Official newer Frappe/ERPNext v16 releases and Education's official
  `version-16` head retain byte-identical reviewed dependency inputs, while
  current Python findings include a no-fixed-version pdfkit advisory and a
  Bench-constrained setuptools fix. No credible official candidate can pass
  this gate yet; the verified rejection and smallest viable upstream input are
  in [`dependency-remediation-candidate-assessment-2026-09-16.json`](evidence/phase-2/dependency-remediation-candidate-assessment-2026-09-16.json).
  **This gate was not weakened, waived or reinterpreted by the fresh execution.**
- **SEC-GUARDIAN-01**: fail-closed Guardian isolation requires D4 policy;
  the narrow explicit-User-Permissions remedy already passes hosted.
- **SEC-RT-TASK-01**: upstream realtime task-room behavior. Product-side
  containment verified by code inspection: owned code enqueues no task/
  progress events with business payloads (R5 records the grep evidence).

### 1.6 Operational gates (deployment-scope; cannot be closed without deploy)
Measured restart downtime, HA, recovery onto a different provider/region/datacentre,
custody of key material in a real trust boundary (a KMS, HSM or owner-provisioned
secret store), session revocation on recovery, a measured RPO/RTO against an
owner-selected objective, full-bundle upgrade/rollback, public TLS/proxy
qualification, capacity, branch-isolation runtime proof and deployed monitoring
operation (D8).
Independent-host recovery is no longer wholly unexercised: a destructive
recovery onto a provably separate ephemeral VM has been executed (run
`35170062251`, see the table below and
[FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md §10](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md)),
which is a separate *machine*, not a separate provider, region or datacentre,
and it does not close the `recovery` gate. Key retrieval from separately
controlled custody is likewise no longer wholly unexercised: run `35179445639`
executed it across three separate ephemeral VMs, including rotation of both
native keys
([FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md §11](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md)).
That is a *structural* custody model over two artifact channels, not a trust
boundary — repository Actions secrets are inaccessible to this session's
credential (HTTP 403, no admin permission), recorded as ENVIRONMENT-BLOCKED
rather than worked around — so it does not close the `backup-restore` or
`durability` gates either. The
final closure harness supplies bounded encrypted SQL/files-shaped preservation,
revocation, audit, alert fail-closed and rollback evidence; it is tracked in
[FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md](FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md)
and is not production evidence. The minimal owner inputs and closure evidence
are in the [D8 operational-input packet](D8-OPERATIONAL-INPUT-PACKET.md). These
remain blocked until an authorized deployment target exists — running them
"somewhere else" would be evidence theater.

The production-like execution pass on the active branch
([execution ledger](evidence/production-like-execution/execution-ledger.json))
separates what a real Docker runner genuinely proved from what it structurally
cannot prove, so the remaining asks are precise rather than generic. The
gap-closure passes P1–P4 (execution-ledger sections
`encryption_key_defect_closure`, `durability_probe_execution`,
`independent_recovery_execution` and `key_custody_execution`; report §9, §10 and
§11) moved several cells from
the blocked column into the executed column — those cells are marked with their
run identifiers below. No row was moved wholesale, and no gate changed state:

| Operational ask | Genuinely executed on a Docker runner | Still structurally blocked |
|---|---|---|
| MariaDB | Startup, healthcheck to healthy, version, charset/collation, transaction rollback, hosting three real bench sites (`35122242676`, `35122242728`). **P2:** graceful restart, SIGKILL crash-recovery with InnoDB rolling back an open transaction, and container destruction with recreation from the same named volume — `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1` and `log_bin=1` read back from the live server, binary-log rotation proving each real restart, and a negative control confirming the data lived in the volume (`35135793802`, `35137645608`, `35138416558`). **P3:** a destroyed site's database recovered onto a separate VM (`35170062251`) | Power-loss durability and volume loss on the selected local/server host, durability across host or region failure, measured restart downtime against a recovery objective |
| Redis | Startup of queue and cache instances, PING/PONG, version, cache marker surviving an app restart (`35122242676`, `35122242728`, `35122242581`). **P2:** RDB/AOF persistence configured and read back from the live server (`aof_enabled=1`, `appendfsync always`, `aof_last_write_status=ok`, `rdb_last_bgsave_status=ok`), with value and 25-item queue digests surviving graceful restart, SIGKILL crash and recreation from the same named volume (`35135793802`, `35137645608`, `35138416558`) | In-flight/exactly-once job semantics after a Redis loss, persistence across host or region failure |
| Backup | Real bench backup with SHA-256 over database, private files and public files; hardened variant (`35122242728`, `35122242581`). **P3:** `bench backup --with-files` staged through an explicit five-file allowlist that excludes the site-config backup Frappe writes beside the dumps, scanned for every generated secret, transferred to a separate VM and verified byte-for-byte there (`35170062251`). **P4:** the same backup taken with System Settings `encrypt_backup` on, so all three artifacts leave the machine as GPG ciphertext — `file` reports *PGP symmetric key encrypted data - AES with 256-bit key salted & iterated - SHA512* for the database dump (245422 bytes, sha256 `0f337270c29dcf5e6ef4e25e05ce2183fae239d35c713f1c6243677103f60df7`) and both file archives, asserted rather than assumed because that is the exact test `bench restore` applies before deciding to decrypt (`35179445639`). **P1:** the `site_encryption_key_restored=false` defect recorded by run `35122242581` is **CLOSED** — the key is initialized natively before the first backup and its survival is proven three ways (fingerprint match, real `get_decrypted_password()` of pre-backup ciphertext, byte-identical ciphertext digest) at `35133062884`, independently reproduced at `35135793582` | Multiple retained versions, an off-site or external destination, retention, rotation of backup **sets**, and session revocation on recovery. Encryption at rest, external key custody and rotation of the **keys** moved to the executed column at P4. The closed P1 defect stays recorded as a real defect that was found by execution, not reclassified |
| Key custody | **P4:** both native keys — `encryption_key`, protecting `__Auth` ciphertext, and `backup_encryption_key`, protecting the artifacts — issued on a separate custodian VM for two epochs in native Fernet shape, split by XOR one-time pad into two shares published to two separately named artifact channels with only SHA-256 fingerprints published; retrieved and fingerprint-verified on an operating VM and installed with `frappe.installer.update_site_config` (the call `get_encryption_key()` itself makes) with zero pre-existing ciphertext to orphan; retrieved again on a third VM, where retrieval was first proved load-bearing by two required failures — restore with no key exits 1 and restore with a real key from the wrong epoch exits 1 — before the field the operator encrypted decrypted (`decrypts_on_target=true`, closing run `35170062251`'s asserted limitation); rotation of both keys composed from native primitives with the native consequence recorded (epoch 1 ciphertext stops decrypting, is re-encrypted under epoch 2 with its plaintext digest unchanged, and epoch 1 then fails while epoch 2 and a never-issued key both fail); the rotated backup key proved at the gpg layer (new backup opens with epoch 2, exit 0, and is rejected by epoch 1, exit 2); no plaintext key in any published artifact, and none surviving destruction on the operator machine after `drop-site` and removal of the archived site directory that holds both keys (`35179445639`) | Custody inside a real trust boundary: a KMS, HSM or owner-provisioned secret store — ENVIRONMENT-BLOCKED, since repository Actions secrets return HTTP 403 to this session's credential. Consequently no authorization of key release (any job able to download both channels can reconstruct the keys), no revocation, no custodian-side destruction, no custody audit log, no channel durability beyond the 14-day artifact retention window, and no rotation ceremony separated in time from issuance. `encryption_key_custody_reference` and `site_configuration_custody_reference` remain **NOT SELECTED**: executing a custody model is not an owner selection of a custody destination |
| Recovery | Restore into a separate site **and** separate database with source credentials not copied; post-restore integrity and authorization re-verification (`35122242728`, `35122242581`). **P3:** a real destructive trigger — `bench drop-site --no-backup`, database present then absent, site directory and both files gone — followed by restore onto a provably separate ephemeral VM (differing `kernel_boot_id`, `runner_name` and `dmi_product_uuid`; no shared filesystem, volume or container), recovering both record sets by name digest, the private and public files byte-exact with their File documents, and an application usable over real HTTP through nginx/Gunicorn including the private-file privacy boundary (`35170062251`). **P4:** the same recovery performed on an **encrypted** backup, where the recovering system obtains the key from custody rather than from the backup, proves by required failure that it could not restore without it, and then decrypts the source-encrypted field whose ciphertext digest is identical to the operating system's record (`35179445639`) | Restore onto a different provider, region or datacentre; session revocation on recovery; a measured recovery objective against an owner-selected RPO/RTO; HTTP usability **after** a key rotation, which P4 proved at the native API and gpg layers but not over HTTP. Key retrieval and external key custody with rotation moved to the executed column at P4 — run `35170062251`'s `decrypts_on_target=false` is now `true` |
| Integrity | Snapshot before backup verified after restore across 14 doctypes by exact record count plus a private-file SHA-256 (`35122242728`). **P3:** comparison **across independent systems** — per-doctype record-name SHA-256 digests and per-file on-disk SHA-256 digests matched between the destroyed source's manifest and the recovered target, and served-content digests matched over HTTP (`35170062251`); **P2:** whole-table row-level payload checksum equality across four real disruptions, single host (`35135793802`) | Whole-database checksum equality compared *across* independent systems |
| Edge/session/TLS | CSRF token presence per site/role, 13 CSRF negative-with-positive-control checks, cross-site session replay denial, private-file own/other/guest isolation (`35122242581`, `35122242728`) | TLS termination/certificates/HSTS, reverse proxy and public edge, cookie attributes under the real edge, the Tailscale tailnet/ACL boundary |
| Monitoring | Native Error Log roundtrip, Scheduled Job Type registry, health ping (`35122242728`) | Alert receiver and delivery, retention/rotation/archival, deployed fail-closed behavior, incident response |
| Upgrade/rollback | Isolated artifact-based Frappe patch upgrade, 33/33, other four pins held fixed (`35122242581`) | Rollback rehearsal, full-bundle upgrade of ERPNext/Education/HRMS/payments and the owned extension, promotion/approval/communication |
| Capacity/availability | Descriptive timings and runner envelope only | Any load, concurrency, soak, overload, failover or availability measurement. **No numeric objective is selected and none is invented** |


### 1.7 Explicitly deferred (does not affect RC readiness)
Portals/student self-service (B11 + D4), placement candidate portal,
performance tuning (no measured need — capability-map rule: projections
only after measurement), payment gateway integration, analytics
platform/warehouse (prohibited), any new ERP-adjacent platform.

## 2. Execution plan (ordered by release criticality & dependencies)

| # | Work | Depends on | Parallel-safe? |
|---|---|---|---|
| R1 | Workspaces + hosted proof | — | done (run 35049742120) |
| R2 | Query-Report registers + hosted proof | R1 merged (shares suite) | done (run 35049742120); D9 remainder owner-gated |
| R3 | Export/attachment containment proofs + observability probes | R2 merged | **DONE** — run 35053305607 @ 46e5040, 533/533 |
| R4 | Owner decision packet (one-page asks, current state per gate) | — | **DONE** — docs/engineering/OWNER-DECISIONS.md (D1–D10, 2026-09-16) |
| R5 | Upstream tracking evidence: realtime non-exposure grep, dependency advisory triage summary, upgrade-path note | — | **DONE** — docs/engineering/UPSTREAM-TRACKING.md (grep: 0 emit sites; advisories triaged; upgrade path + hazards, 2026-09-16) |
| RC | Release Candidate dossier: consolidated evidence index (runs, SHAs, gates, deferrals) | R1–R5 | **DONE** — docs/engineering/RELEASE-CANDIDATE-DOSSIER.md (implemented surface QUALIFIED; production REJECT) |
| T1 | D2 teaching compensation: `TH Instructor Contract` (+skill-term/adjustment children) + `TH Teaching Assignment` doctypes, fixtures, guarded command surface | Owner answer 2026-09-16 | **DONE** — shipped @ 8c92e2f; qualified in run 35066349129 |
| T2 | D2 hosted checks: multi-instructor/skill facts, effective dating, duplicate-payable prevention, idempotent calc, fixed-salary exclusion, audit chain | T1 merged (shares suite) | **DONE** — run 35066349129 @ fa02137, **536/536**; checks `teaching-compensation-contract-authority`, `teaching-assignment-facts`, `teaching-compensation-calculation` |
| T3 | D10 (ii): role-based native Page surfaces for API-first staff roles (no **additional** native reads; containment unchanged) | T5 charter + D10(ii) answer | **DONE** — 13 qualified standard command Pages + shared guarded-command client, current-branch run 35073376790 @ 3587700, **542/542**; the additional Course Owner/General Manager control-centre Page is locally contract-tested and adds no business-document authority; checks `release-command-pages-*` |
| T4 | D3 framework: guarded correction/refund command framework, approval terms configurable (owner terms pending) | T1 done | **DONE** — run 35069740378 @ ed2d81d, **539/539**; checks `finance-correction-*` (fail-closed, SoD/window/dual-key, native credit-note posting). v1 scope: full-amount corrections of TH placement invoices; partials + Fees-side await owner exact terms (refused fail-closed) |
| T5 | D8: code-derived operational ownership charter and canonical owner-authority reconciliation | Owner decision record 2026-09-16 | **DONE** — [OPERATIONAL-OWNERSHIP-CHARTER.md](OPERATIONAL-OWNERSHIP-CHARTER.md) and [canonical-owner-decision-record.json](canonical-owner-decision-record.json); selected engineering implementation/evidence remain blocked, production REJECT |
| G1 | 2026-09-17 review: rotate the drifted branch boundary (canonical pin, 10 workflows, headers, governance JSON, ledger provenance chain) | — | **DONE** — 665/665 owned tests (was 629 with **2 failures**); `d8_validate.py` exit 0; no run re-executed or re-labelled |
| G2 | Make the rotation procedure honestly followable: explicit fail-closed `NOT_EXECUTED_ON_THIS_BRANCH` state + identity rejection + per-previous-branch run pins | G1 | **DONE** — 8 `ActiveBranchEvidenceTests`; D8 report discloses `active_branch_hosted_execution`; no gate changed state |
| G3 | Fix latent `NameError` in `tools/placement/recover_evidence.py` (undefined `root` in the evidence publish step — never reached because the recovery run failed earlier) | — | **DONE** — caught by enabling pyflakes F821 |
| G4 | Unfiltered `tarfile.extractall()` on a decrypted archive → `extract_safely()` (`filter="data"` + refusal fallback); record the computed per-version ciphertext digests and assert fixture members survive the round trip | — | **DONE** — 4 `SafeExtractionTests`; **limit:** only the fallback branch executed here (sandbox Python 3.11.2 has no `filter` parameter) |
| G5 | Static-analysis gate (`pyproject.toml`, `E9,F`, no suppressions) + whole-suite gate on push **and** `pull_request` (`.github/workflows/owned-suite.yml`) | G1–G4 | **DONE** — 11 pyflakes findings fixed not silenced; all 5 workflow step scripts executed locally, exit 0 |
| G6 | Turn the two prose-only review rules into executable guards: branch-boundary classification (7 tests) and app-assembly consistency (11 tests) | — | **DONE** — both proved load-bearing by mutation, not just passing |
| G7 | D11 product-license inconsistency (hooks declare MIT, README says none selected, no LICENSE file, GitHub reports null) | Owner decision | **CLOSED 2026-09-19** — the Course Owner selected **MIT** (decision D11). `LICENSE` added, README corrected, both `hooks.py` declarations already correct, and `tests/foundation/test_licence_consistency.py` (4 tests) makes the agreement mechanical so the contradiction cannot silently return. No production posture changed. |
| G8 | TLS edge `tls-protocol-policy-enforced-at-the-listener` undecidable on the runner image **and** its own evidence never published (`probe.run` raised before `tls-checks-result.json` was read). Pre-existing: failed identically in run 35197870620 on the previous session branch and run 35214660151 here — not caused by the G1 rotation, and recorded nowhere before this row | — | **FIXED in code** — inner result ingested before the exception re-raises (fail-closed unchanged); `summarize_refusals()` publishes `complete:false` + `client_side_refusal_reasons` for a half-finished run; policy-independent raw-ClientHello probe (`build_legacy_client_hello`/`parse_tls_record` pure, `legacy_protocol_outcome` does the I/O) merged via `merge_legacy_observations`, which only upgrades an entry already `NOT OBSERVABLE`. 10 tests added, 665→675. **Verified green on the runner** — run 35216709160 @ 37e4bff passed 38/38, `tls_protocol_policy = POLICY ENFORCED`, TLSv1/TLSv1.1 `REFUSED` via `resolved_by: "raw ClientHello (policy-independent)"` with `alert_description: protocol_version` (the same alert seen locally), `required_refusals_observed.complete: true`. A third defect surfaced from that report and is fixed in e8da889: the published verdicts were copied through a hardcoded pair of keys, so `tls_protocol_raw_client_hello` was silently discarded — the same evidence-loss mode one layer up. 685 owned tests. |
| G9 | Three of four pinned workflow actions declared `runs.using: node20` and were force-run on Node 24 (GitHub deprecated it 2025-09-19). The warning is an *annotation*, so the suite stayed green and nothing recorded it. Also: pin comments used four inconsistent styles and the same literals were duplicated into three contract tests (the F1b failure mode) | — | **DONE** — checkout→v5.1.0, upload-artifact→v6.0.0, download-artifact→v7.0.0, setup-node already node24; lowest node24 major chosen deliberately; all 48 pin comments normalized; 9 `test_workflow_action_pins.py` tests, proved by mutation. **Verified by controlled comparison** — the identical annotation query on f813a5c (runs 35214660202/35214660234/35214660271) returns the Node 20 warning in all three, naming the old pins; on e8da889 (runs 35218007896/35218008053/35218007835/35218007901) it is absent in all four. Key custody and independent recovery, which pass artifacts between jobs, both still pass (35218007872, 35218007835). |
| G10 | `tools/foundation/runtime_restore.py` zipped `students`/`applicants`/`enrollments` positionally with no `strict=` and no length check, so a shorter or empty list made the loop body never run while the following line still appended `status: "pass"`. A restore verification that checked **zero** records published evidence indistinguishable from a real pass, and every downstream "restore verified" claim inherited the falsehood undetectably. Reached by both `restore-verification` and `hardened-recovery-invariants` | — | **DONE** — `positional_record_count()` guard (rejects empty *and* disagreeing lists; `strict=True` alone is silent on all-empty), `strict=True` on the loop, and `verified_records` reconciled and published as `records_verified`. 11 tests, proved by mutation. `_xor()` key-share combine also given redundant `strict=True`. Remaining `zip()` sites triaged and left: `audit_stack.py` is guarded on the line above, the `ast.Dict` zips are equal-length by construction. 702 owned tests |

Owner gate dispositions (2026-09-16): D1 defer · D2 unlocked (T1/T2) ·
D3 framework (T4) · D4 defer · D5 defer · D6a no tax · D6b no gateway ·
D7 defer · D8 owner/business requirements recorded in the canonical record
(charter delivered; implementation and evidence remain D8-blocked; numeric
capacity/availability target not supplied) · D9 CLOSED at (d) · D10 (ii)
**EXECUTED & QUALIFIED** (T3, run 35073376790). Details:
[OWNER-DECISIONS.md](OWNER-DECISIONS.md),
[canonical-owner-decision-record.json](canonical-owner-decision-record.json), and
[TEACHING-COMPENSATION-DESIGN.md](TEACHING-COMPENSATION-DESIGN.md).

Parallelization note: this environment executes sequentially; R2/R3/R5
are marked parallel-safe because they touch disjoint files (separate
fixtures, separate check blocks, docs), with `native_checks.py` as the
only shared file — sequenced through the single hosted suite by design.

**Release Candidate definition used here:** every engineer-executable gap
(1.2/1.5-non-owner) closed with hosted evidence, owner decision packet
delivered (1.4), upstream/ops items precisely tracked (1.5/1.6). Owner
gates and deployment-scope operations then remain as the *only*
outstanding classes — production stays REJECT until D8-class gates are
independently satisfied.

## 3. What will NOT be done (guardrails)
No rewrite, no new ERP, no parallel masters/ledgers/UI stack; no
invented prices, grades, taxes, refund or operational rules; no reopening
of Placement/Admission/Enrollment/Teaching/Finance; no deployment; no
custom platform "to get ready" for deferred domains.
