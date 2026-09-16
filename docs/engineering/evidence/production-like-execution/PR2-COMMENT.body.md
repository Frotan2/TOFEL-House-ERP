
## Production-like readiness execution — active branch `arena/01a0aafe-tofel-house-erp`

This PR's head branch is `arena/01a0a9f7-tofel-house-erp`. The Arena session
branch is now `arena/01a0aafe-tofel-house-erp`, and this session is fixed to it,
so **no commit was pushed to this PR's head branch**. This comment records the
result on the current active branch. Per
[`BRANCH-RECONCILIATION.md`](https://github.com/Frotan2/TOFEL-House-ERP/blob/main/docs/engineering/BRANCH-RECONCILIATION.md)
the executable boundary in `tools/session_branch.py` was rotated together with
the workflow filters, hosted guards and qualification tests; recorded historical
provenance was left untouched and `arena/01a0a9f7-tofel-house-erp` moved from
*active* to *historical provenance*.

### Two premise corrections

**The named commit `d3705e6` does not exist.** It is not in any branch, not a
dangling object (`git fsck --lost-found --dangling` is empty), not on GitHub
(`GET /commits/d3705e6` → HTTP **422** "No commit found for SHA"), and not
referenced anywhere in the tree. At the start of the pass the active branch sat
at `60c777e` — byte-identical to this PR's already-pushed head — with a clean
tree, so there was **no unpushed commit to publish**. It was not fabricated or
substituted. The branch was published to GitHub and all work is committed on it
as `d7df9ca` and `c891949`.

**The requesting host cannot run the harness.** No `docker`, `docker-compose` or
`podman`; no `/var/run/docker.sock`; Docker cannot be installed because
`deb.debian.org` and `download.docker.com` are unreachable while `pypi.org`,
`github.com` and `registry.npmjs.org` return 200; `/lib/modules` absent; `/proc`
read-only; 2 vCPU / ~3.8 GiB RAM. Recorded as **ENVIRONMENT-BLOCKED** with every
command and raw output inline. `evidence/phase-2/docker-preflight.json` and all
other check-only/preflight results were **not** promoted to execution evidence.

### What was genuinely executed

Venue: ephemeral GitHub-hosted `ubuntu-24.04` (image `20260907.300.1`),
**Docker 28.0.4**, **Compose 2.38.2**, at commit
`d7df9ca766cd3039d68051ca83cdc8be5e834452`.

| Run | Workflow | Conclusion |
|---:|---|---|
| [`35122242676`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242676) | Foundation runner qualification | **success** — 18/18 |
| [`35122242728`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242728) | Placement synthetic content qualification | **success** — 542/542 native, 101/101 runner |
| [`35122242581`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242581) | Foundation runtime validation | **failure** — SEC-DEPS-01, 114/116 restricted |
| [`35122242647`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242647) | Foundation frontend candidate review | **failure** — candidate **not adopted** |
| [`35122242888`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242888) | D8 operations contract validation | **success** — structural, reports BLOCKED/REJECT |

Real execution highlights: pinned MariaDB digest `sha256:8b5f33eb…` started to
`healthy` in 5 polls with version, `utf8mb4`/`utf8mb4_unicode_ci` and a
`START TRANSACTION`/`ROLLBACK` count-0 proof; pinned Redis digest
`sha256:75934ddb…` PING/PONG; a real bench running frappe, erpnext, education,
payments, hrms, `foundation_security` and `toefl_house` across two isolated
sites; real backup digests over database, private and public files; restore into
a **separate site and separate database** with `source_db_credentials_copied=false`;
14 doctypes verified by exact record count plus a private-file SHA-256;
isolation 47/47, guardian browser 6/6 (own 200 vs other 403), readiness 54/54,
realtime 4/4 including live-session-revocation-stops-delivery, upgrade 33/33.

### Probe-by-probe classification

| # | Probe | Classification |
|---:|---|---|
| 1 | MariaDB startup, health, restart persistence, durability | **PARTIAL** — startup/health/rollback executed; **no MariaDB restart or durability probe exists** |
| 2 | Redis persistence and restart recovery | **PARTIAL** — start/PING/version executed; **no RDB/AOF or Redis-restart probe**; harness states "No Redis or database restart" |
| 3 | Versioned encrypted backups, external key custody, rotation | **BLOCKED** — real backup digests only. **Executed defect: `site_encryption_key_restored=false` in `35122242581`** (true in `35122242728`); both recorded, neither reclassified. Versioning/encryption/HMAC/rotation/key-boundary exist only as **PASS / BOUNDED** |
| 4 | Destructive/recovery into a genuinely independent system | **PARTIAL** — same-host separate-database restore executed; **independent system never provisioned, no destructive trigger, no measured recovery objective** |
| 5 | Database and file integrity before/after recovery | **PASS (EXECUTED) / SCOPED** |
| 6 | Native Frappe/ERPNext/Education runtime, authorization/branch isolation | **PASS (EXECUTED) / SCOPED-SYNTHETIC** — deployed multi-branch (Company/Branch) isolation still **BLOCKED** |
| 7 | Authentication/session/offboarding/emergency revocation | **PARTIAL** — revocation and session-replay denial executed; offboarding **process**, key rotation and audit retention not executed |
| 8 | Monitoring, alert delivery, retention, fail-closed | **BLOCKED** — only native Error Log/scheduler-registry/health probes executed; no receiver, delivery or retention |
| 9 | Edge/session/TLS for the local/server + Tailscale phase | **PARTIAL** — CSRF/session/private-file boundaries executed; **no TLS and no Tailscale** (plain `http://127.0.0.1:8000` with Host-header routing) |
| 10 | Full artifact-based upgrade and rollback rehearsal | **PARTIAL** — Frappe patch upgrade 33/33 executed; **rollback never rehearsed**, full-bundle upgrade not executed |
| 11 | Capacity/availability observations | **BLOCKED / NOT SELECTED** — timings and runner envelope only; **no numeric SLO, RPO or RTO invented** |

Tally: 2 executed-and-scoped passes, 6 partial, 3 blocked. **No D8 release gate
flips to PASS.**

Machine-readable ledger with a run/check citation for every PASS and a SHA-256
for every archived report:
[`execution-ledger.json`](https://github.com/Frotan2/TOFEL-House-ERP/blob/arena/01a0aafe-tofel-house-erp/docs/engineering/evidence/production-like-execution/execution-ledger.json).

### Separately classified, never counted as execution evidence

`PASS / BOUNDED` (real local execution over synthetic fixtures: OpenSSL
AES-256-CBC + PBKDF2, HMAC-SHA256, three versions with v1 rotated, external key
absent from the restore tree, alternate-directory restore, offboarding, audit
shape, alert fail-closed, artifact rollback A→B→A — its own `branch_isolation`
and `monitoring_alerting` proofs report **BLOCKED / NOT PROVEN**);
`PASS / STRUCTURAL` (D8 validator: exit 0 while reporting BLOCKED, REJECT,
`production_enabled=false`, synthetic-only REQUIRED, SEC-DEPS-01
UPSTREAM-BLOCKED / REJECT, `checkout_branch_matches_active=true`); local suite
313 Python tests OK, realtime guard PASS, D10 command-page smoke PASS (14
pages); `PREFLIGHT` (`docker-preflight.json`, toolchain availability only).

### Hard stops preserved

`production_enabled=false` · production authorization **REJECT** · synthetic-only
guard **REQUIRED** · SEC-DEPS-01 **UPSTREAM-BLOCKED / REJECT** (re-executed and
failed again on the active branch: 14 PyPI/OSV findings across `pdfkit`, `pypdf`,
`setuptools`, `weasyprint`; 57 npm advisory findings — 27 high, 26 moderate, 4
low — across 21 of 255 queried packages) · D8 overall **BLOCKED** · no numeric
capacity/availability objective invented · **this PR is not merged and production
is not enabled**.

`d8_validate.py` now pins the active-branch runtime run via
`session_branch.ACTIVE_RUNTIME_RUN` and keeps the historical pin as
`PRIOR_ACTIVE_RUNTIME_RUN`; it additionally fails closed if the active branch
ever reports a passing Foundation runtime or a true phase2/security/product flag
while SEC-DEPS-01 is open. No gate was weakened, waived or reinterpreted.

### Corroboration at the evidence commit, and a credential outage that was handled honestly

Pushing the evidence commit `c891949` re-triggered all five gates. Retrieved
conclusions: D8 `35125669493` **success**, runner `35125669408` **success**
(18/18, MariaDB healthy in 4 polls, identical pinned digests), placement
`35125669475` **success**, frontend `35125669372` **failure**, runtime
[`35125669370`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35125669370)
**failure** at step 7 — SEC-DEPS-01.

**Reproduction finding:** runtime `35125669370` at `c891949` reproduces
`35122242581` at `d7df9ca` field for field on every outcome that matters — same
SEC-DEPS-01 failure with both dependency audits exiting 1, same 114/116
restricted checks, same four sites and four apps, same readiness 54 / realtime 4
/ upgrade 33 / guardian-browser 6 passes, same 57 npm advisory findings across
21 packages and 14 PyPI/OSV findings across `pdfkit`, `pypdf`, `setuptools` and
`weasyprint`, and the same `site_encryption_key_restored=false` defect. Two
independent executions at two commits agree, which strengthens the REJECT
conclusion rather than weakening it.

Partway through the pass the GitHub credential expired (`gh auth status`: *"The
github.com token in GH_TOKEN is no longer valid"*; `api.github.com` 401 while
`github.com` 200, so authentication rather than network). While it was invalid,
the runtime conclusion at `c891949` was recorded as **NOT RETRIEVED** and was
explicitly **not** assumed to be a failure merely because every prior runtime run
had failed, and this comment was queued verbatim rather than paraphrased or
dropped. No result was invented during the outage and credentials were never
requested or stored. Authentication was restored afterwards and all three
outstanding items were completed: the run conclusion was retrieved and archived,
the commit was pushed, and this comment was posted.

### Conclusion

Fresh genuine execution on a Docker-capable runner materially increased the real
evidence and independently reproduced the native runtime, authorization
containment, backup/restore mechanics and integrity verification. It closed no
D8 gate. Production authorization remains **REJECT**, `production_enabled`
remains **false**, SEC-DEPS-01 remains **UPSTREAM-BLOCKED / REJECT**, and this PR
is **not merged**.
