# Production-readiness closure pass — 2026-09-17

**Commit under review:** `da8b36a347917e81ecf262694cc0d12ffc0fc4b5`
**Branch:** `arena/01a0aef4-tofel-house-erp`
**Outcome:** **NO-GO for production.** Production remains **REJECT**, D8 remains
**BLOCKED**, SEC-DEPS-01 remains **UPSTREAM-BLOCKED / REJECT**.

This pass implemented **no product features**. It reconciled every remaining
blocker against actual hosted evidence, corrected the governance record where
that record had become factually stale, and recorded one gate as
infrastructure-blocked rather than altering code to obtain a green result.

---

## 1. Method

Every state below was read from a hosted check-run report fetched from the GitHub
API during this pass, not from narrative. Where a report is gzip+base64 encoded it
was decoded; where a report embeds raw stderr containing an invalid JSON escape it
was repaired for parsing only. No state was inferred from a previous session's
conclusion.

Two verification limits are stated plainly rather than hidden:

- **Job logs are unreachable from this environment.** The log endpoint returns
  `EOF` against `results-receiver.actions.githubusercontent.com`. Evidence is
  therefore taken from published check-run reports and step conclusions, which is
  the same source the ledger already uses.
- **No workflow could be re-triggered.** See §4.

---

## 2. Evidence basis — every hosted run on this branch

| Workflow | Run | Commit | Result |
|---|---|---|---|
| D8 operations contract validation | `35224205616` | `53520b0` | success |
| Foundation runtime validation | `35225331022` | `da8b36a` | **failure** — SEC-DEPS-01 |
| Foundation operational boundaries (TLS) | `35218007814` | `e8da889` | success — 38/38 |
| Foundation datastore durability | `35218008053` | `e8da889` | success — 20/20 |
| Foundation independent-system recovery | `35218007835` | `e8da889` | success — 31/31 |
| Foundation external key custody | `35225331195` | `da8b36a` | **failure** — infrastructure (§4) |
| Foundation runner qualification | `35222291712` | `1b9f29f` | success — 18/18 |
| Placement synthetic content qualification | `35222291725` | `1b9f29f` | success — 542/542, 101/101 |
| Foundation frontend candidate review | `35222291762` | `1b9f29f` | **failure** — npm advisory |
| Owned suite | `35225330998` | `da8b36a` | success |
| Placement evidence recovery | — | — | **never executed on this branch** |

`da8b36a` touches no path in the D8 workflow's filter, so `53520b0` is
legitimately D8's latest hosted evidence rather than a gap.

Local gate at `da8b36a`: `ruff check .` clean, **702 owned tests pass**,
`d8_validate.py` exit 0, both Node suites pass.

---

## 3. Canonical remaining-blockers matrix

Statuses are the D8 `release_gate_matrix` states, unchanged by this pass. Fourteen
gates: 4 PASS, 8 BLOCKED, 2 REJECT.

### 3.1 dependency-security — **REJECT** (SEC-DEPS-01)

| | |
|---|---|
| **Evidence** | Runtime `35225331022` @ `da8b36a`, check `105222593207`: 121 restricted checks, **119 pass**, only `hosted-full-stack-dependency-audit` and `hosted-frontend-advisory-audit` fail. Frontend `35222291762` @ `1b9f29f`: 22 checks, 20 pass, both audit checks exit 1, 1 advisory introduced / 35 removed, `production_pins_changed` false. |
| **Proven** | The gate is a genuine, reproducible REJECT on the active branch, not inherited provenance. Re-execution on this branch produced the identical profile. |
| **Not proven** | Any remediated dependency set. No passing upstream candidate exists. |
| **To close** | Upstream must publish fixed releases for the 14 PyPI/OSV findings (pdfkit, pypdf, setuptools, weasyprint) and the 57 npm advisories across 21 of 255 packages, and the pinned bundle must adopt them without waiver, override, fabricated lock, unsupported upgrade or fork-like patch. **Not engineer-closable and must not be waived.** |

### 3.2 recovery — **BLOCKED**

| | |
|---|---|
| **Evidence** | Independent-system recovery `35218007835` @ `e8da889`, target check `105193158969`: **31/31 pass**. |
| **Proven** | Recovery onto a genuinely independent ephemeral VM. Independence evidenced by differing `kernel_boot_id`, `dmi_product_uuid`, `runner_name` and `job` — with hostname explicitly **not** used as a discriminator, because the platform reuses generated hostnames across separate VMs. Source site destroyed before recovery; no source lab path, archived site or database present on target; restored into a separate database; target set its own admin credential; payload digests matched the source record (`database.sql.gz` 879650 bytes, both file trees). |
| **Not proven** | Decryption of source-encrypted fields — the key was never transferred, so `decrypts_on_target` is **false**. Recovery onto another provider, region or datacentre. Any RPO/RTO against an owner-selected objective. Off-site or air-gapped storage, retention, rotation. |
| **To close** | Owner-selected recovery objectives, plus external key custody proven end to end so a recovered site can decrypt source-encrypted fields (depends on §4). |

### 3.3 backup-restore — **BLOCKED**

| | |
|---|---|
| **Evidence** | Runtime `35225331022` @ `da8b36a`: `backup-with-files`, `restore-with-files`, `restore-migrate`, `verify-encryption-key-survived-restore`, `restore-verification`, `hardened-backup-with-files`, `hardened-restore-with-files`, `verify-native-encrypted-credential-recovery`, `hardened-recovery-invariants` — **all pass**. Recovery `35218007835` verified archive integrity by digest on a separate VM. |
| **Proven** | Real backup → separate-database restore → integrity verification, twice on this branch (`restore.localhost` and `recovery.localhost`), with the encryption key surviving restore. `restore-verification` and `hardened-recovery-invariants` both invoke `tools/foundation/runtime_restore.py`, which as of `da8b36a` **fails closed** if the positional record lists are empty or disagree in length and publishes `records_verified`. |
| **Not proven** | Backup destination, multi-version retention, off-site storage, any measured recovery objective. |
| **To close** | Owner-selected backup destination, versioning and retention policy, then a hosted run that exercises multi-version retention and off-site storage against it. |

### 3.4 upgrade-rollback — **BLOCKED**

| | |
|---|---|
| **Evidence** | `isolated-controlled-patch-upgrade` passes in runtime `35225331022` @ `da8b36a`; remaining-gate report records **upgrade 33/33**. |
| **Proven** | A controlled framework upgrade on an isolated five-app bundle with the other pins held fixed. |
| **Not proven** | **Rollback was not executed on any hosted runner.** Local artifact rollback A→B→A is a bounded proof only. Full-bundle upgrade in the selected architecture. |
| **To close** | A hosted rollback rehearsal: upgrade, then restore the prior bundle and verify application state, with a recorded rollback decision path (couples to §3.11). |

### 3.5 observability / monitoring — **BLOCKED**

| | |
|---|---|
| **Evidence** | Placement `35222291725` @ `1b9f29f`, native check `105208726304` (542/542): `release-observability-probes` — Error Log roundtrip, scheduler jobs active, health ping. |
| **Proven** | Native audit plumbing exists and round-trips. |
| **Not proven** | **No monitoring stack, alert receiver, delivery attempt, retention window or deployed fail-closed behaviour has been exercised on any hosted runner.** Missing-receiver fail-closed remains a bounded local model. Course Owner health/attention and General Manager operational visibility requirements are unevidenced in a deployed topology. |
| **To close** | Owner-selected monitoring/alerting stack and retention window, then a hosted run that delivers a real alert to a real receiver and proves fail-closed behaviour when the receiver is absent. |

### 3.6 branch isolation — **BLOCKED**

| | |
|---|---|
| **Evidence** | `FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md` §"Native authority"; local bounded `branch_isolation` proof reports **BLOCKED / NOT PROVEN**. |
| **Proven** | The implementation uses the native Company/Branch and permission model. Site-level isolation is proven (`authorization-isolation`, §3.9). |
| **Not proven** | **Multi-branch isolation is explicitly not claimed.** Native cross-branch read, write, submit, export, file and background-job isolation remain unproven. |
| **To close** | A hosted probe exercising cross-branch denial across all six paths with positive controls, in a deployed topology. |

### 3.7 topology-edge-session — **BLOCKED** (evidence corrected by this pass)

| | |
|---|---|
| **Evidence** | Operational boundaries `35218007814` @ `e8da889`, check `105191973507`: **38/38 pass**, `mocks_or_simulations_used` false. |
| **Proven** | A real nginx 1.24.0 reverse proxy with **TLS termination** in front of a live Frappe site at `edge.foundation.internal`. Private CA and issued leaf certificate whose chain verifies. TLS policy **POLICY ENFORCED** — TLS 1.2/1.3 negotiated; SSLv3, TLS 1.0, TLS 1.1 rejected, the two legacy protocols resolved by a policy-independent raw ClientHello returning `alert protocol_version`. Certificate verification enforced: with CA rc=0, without trust anchor rc=21, unrelated CA 21, hostname mismatch 62. **HSTS** `max-age=63072000; includeSubDomains; preload` matching the pinned template. All four security headers present, none missing. Authenticated session over TLS carrying a `sid` cookie with `Secure`, `HttpOnly`, `SameSite=Lax`. Plaintext listener answers **301 only** and never serves application bytes — it holds no `proxy_pass` or `try_files`, so no second route bypasses TLS. Private file **403 anonymous vs 200 authenticated** via `X-Accel-Redirect` to an nginx internal location. |
| **Not proven** | **Tailscale tailnet/ACL boundary** — `ENVIRONMENT-BLOCKED`, binary absent, pending three owner inputs: a tailnet auth key or OAuth client able to register a node; the ACL policy defining which identities may reach the service; whether the service is tailnet-only or also publicly reachable. **Public edge/provider/hostname** remain unselected. **Privileged ports 80/443** — the probe binds 8080/8443 and records the deviation. |
| **To close** | The three owner Tailscale inputs above, plus an owner decision on the future public edge, then a hosted run on 80/443 with the tailnet boundary exercised. |

> **Correction made by this pass.** The gate's evidence string previously asserted
> that "no TLS termination, certificate, HSTS, reverse proxy,
> cookie-attribute-under-edge … was exercised". That was true when written and is
> **false now**. The string is marked `SUPERSEDED BY NEWER EVIDENCE` with the
> observed detail. The gate **stays BLOCKED** — Tailscale and the public edge are
> genuinely unproven — but the record no longer understates what is proven.

### 3.8 durability — **BLOCKED**

| | |
|---|---|
| **Evidence** | Datastore durability `35218008053` @ `e8da889`, check `105191267035`: **20/20 pass**, `mocks_or_simulations_used` false, Docker 28.0.4, ubuntu24 image `20260907.300.1`. |
| **Proven** | Container-level durability, executed. All three scenarios survived with identical `committed_row_count` 25 and `payload_crc32_sum` 51945241053: graceful restart, SIGKILL crash recovery, container destruction with recreation from the same named volume. Binary log rotated once per server start (2→3→4→5). Negative control confirms the data really lived in the volume. `durability_executed` true. |
| **Not proven** | The probe's own list: host or region loss, storage-array failure, off-site replication; high availability, failover, multi-node quorum; application-level workflow correctness after recovery; backup archive integrity (covered by §3.3); any owner-selected durability reference or retention objective. The gate's wider area — configuration, private/public file and encryption-key durability — is unproven. |
| **To close** | Owner-selected durability references and retention objectives, then hosted probes for host-loss, off-site replication and key/configuration durability. |

### 3.9 change-control — **BLOCKED**

| | |
|---|---|
| **Evidence** | D8 validation `35224205616` @ `53520b0` — both `Validate D8 contract and fail-closed release invariants` and `Run D8 contract tests` succeeded while the validator reported BLOCKED / REJECT / `production_enabled` false. |
| **Proven** | Release provenance is real and machine-checked: run, check and report SHA-256 identifiers recorded per gate; a fail-closed validator that rejects gate drift and any attempt to relax the production posture. |
| **Not proven** | Deployed approval, artifact promotion, stakeholder communication, and a restore-based rollback decision path. |
| **To close** | An exercised end-to-end change record: approval → promotion → communication → rollback decision, on a deployed target. |

### 3.10 capacity-availability — **BLOCKED**

| | |
|---|---|
| **Evidence** | Runs `35222291712`, `35225331022`, `35218008053` — descriptive timing only. |
| **Proven** | Nothing quantitative. **No numeric capacity or availability objective is selected, and none is invented here.** |
| **Not proven** | Load, concurrency, soak, overload, failover, availability. |
| **To close** | An owner-selected numeric objective, then a hosted load/soak/failover harness measured against it. Engineering may baseline but must not claim a target. |

### 3.11 Gates already PASS (scoped, not production closures)

| Gate | Latest evidence | What the PASS does **not** mean |
|---|---|---|
| `domain-qualification` | Placement `35222291725` @ `1b9f29f` — 542/542 native, 101/101 runner steps, `runtime_complete` true | Domains remain **closed**. Not a reopening, and not full T01–T20. |
| `authorization-isolation` | Runtime `35225331022` @ `da8b36a` — isolation, expanded-restricted-http-isolation, guardian-browser-authorization, recovered-security-regressions all pass | Implemented-slice and isolated qualification only; the synthetic guard stays mandatory. Does not cover §3.6. |
| `realtime` | Remaining-gate report of `35225331022` — realtime 4/4, guardian browser 6/6 | Upstream task-room risk remains separately tracked and is not a production authorization. |
| `ownership` | Charter and canonical owner-decision record | Code-derived charter delivered; role implementation and production evidence remain bounded. |

`production_closure` is `false` for the first three: a PASS here closes no
production gate.

### 3.12 production-authorization — **REJECT**

The active branch now carries its own hosted evidence rather than borrowed
provenance. `hosted_execution_state` is `EXECUTED` with
`foundation_runtime.status = fail_reject` pinned to run `35225331022`, and the
validator asserts both the status and that exact run id so the pin cannot be
swapped for a passing run. **Re-execution moved the evidence onto this branch and
closed no gate.**

---

## 4. Key Custody — recorded as infrastructure-blocked

**Run `35225331195` @ `da8b36a` — failure. No code was altered to obtain a green
result.**

| Job | Result |
|---|---|
| custodian | **success** — key material issued, only SHA-256 fingerprints published |
| operator | **failure** — 18/19 checks pass, then `bench-init` exit 167 |
| recovery | **skipped** (depends on operator) |

**The failure is upstream, not ours.** `bench-init` died with:

```
error: RPC failed; HTTP 503 curl 22 The requested URL returned error: 503
fatal: expected 'packfile'
```

while `uv` cloned `git+https://github.com/frappe/gunicorn@54b59ca…` — a transient
HTTP 503 from GitHub during dependency resolution, before any custody code runs.

**The custody logic itself is evidenced as working at this exact commit:**

- All **4 keys** retrieved (both epochs × both key roles), each with
  `matches_custody_manifest: true`, valid native Fernet format (44 characters, 32
  decoded bytes), `channels_combined: ["a","b"]`.
- All three **negative controls** correct: `channel_a_alone`, `channel_b_alone`
  and `epoch1_a_with_epoch2_b` each reconstruct but produce a fingerprint that
  **does not match** — proving neither channel alone, nor a cross-epoch mix, yields
  a usable key.
- The custodian job succeeded, and it reaches the changed code through
  `split_key()` → `_xor()`.

**Why it could not be re-run — all three legitimate paths attempted:**

| Attempt | Result |
|---|---|
| `gh run rerun 35225331195 --failed` | `cannot be rerun; its workflow file may be broken` |
| `gh run rerun 35225331195` | same |
| `gh workflow run foundation-key-custody.yml` | **HTTP 403 — Resource not accessible by integration** |

The workflow is confirmed `state=active` and parses as valid YAML with jobs
`custodian`/`operator`/`recovery` and `push` + `workflow_dispatch` triggers, so
"may be broken" is GitHub masking a permission denial — the explicit 403 on
dispatch establishes that the credential lacks `actions:write`.

**Precise condition to close:** grant the credential `actions:write` (or push any
commit touching a file in that workflow's `paths` filter) and re-run. Expected
result on a healthy upstream: operator completes and the recovery job runs. This
is a **rerun**, not a code change — no fix is owed.

---

## 5. Governance record corrections made by this pass

1. **`topology-edge-session` evidence was factually stale** and understated proven
   TLS/HSTS/cookie/proxy behaviour. Marked `SUPERSEDED BY NEWER EVIDENCE` with the
   observed detail. **Gate state unchanged: BLOCKED.**
2. **Twelve further gates** carried only prior-branch citations (`d7df9ca`,
   `35122242581`, `35122242728`). Each received an additive
   `ACTIVE-BRANCH RECONCILIATION` paragraph citing this branch's runs. Historical
   text preserved verbatim.
3. **Verified zero drift:** all 14 gate states, all 14 `production_closure` flags,
   `allowed_states`, `production_state` REJECT, `overall_gate_state` BLOCKED and
   `security_dependency_state` UPSTREAM-BLOCKED / REJECT are byte-identical to
   before the edit. `d8_validate.py` exits 0.

**Not changed, deliberately:** no gate state, no owner decision, no D11 licence
selection, no production enablement, no waiver of SEC-DEPS-01, no code change to
Key Custody.

---

## 6. Owner decisions still required (not invented here)

D1 level vocabulary/rubrics/cutoffs · D2 remaining payroll posting scope ·
D3 partial-refund terms · D4/D5 as previously recorded · D6a tax · D6b gateway ·
D7 · D8 (BLOCKED — REJECT) · D9 · D10 · **D11 product licence — NOT SELECTED**
(`hooks.py` declares MIT in both apps, the README says none is selected, no
LICENSE file exists, GitHub reports `null`).

Also required as owner inputs: the three Tailscale items in §3.7, the recovery and
durability objectives in §3.2/§3.8, the capacity objective in §3.10, and the
backup destination/retention policy in §3.3.

---

## 7. Go / no-go evidence summary

**NO-GO.** Production stays **REJECT**; D8 stays **BLOCKED**.

| Blocking | Count | Engineer-closable? |
|---|---|---|
| REJECT | 2 — `dependency-security` (SEC-DEPS-01), `production-authorization` | No — upstream-blocked |
| BLOCKED | 8 — recovery, backup-restore, upgrade-rollback, observability, topology-edge-session, capacity-availability, durability, change-control | No — each needs an owner input or a deployed target |
| Infrastructure-blocked | 1 — Key Custody operator (`actions:write` or a path-filter push) | Yes, by rerun only |
| PASS (scoped) | 4 — domain-qualification, authorization-isolation, realtime, ownership | n/a — closes no production gate |

**What is genuinely proven now, on this branch:** a real TLS edge with enforced
protocol policy and correct certificate, HSTS and secure-cookie behaviour;
container-level datastore durability across graceful restart, crash and volume
persistence; recovery onto an independent VM with digests verified and no shared
state; backup → separate-database restore with the encryption key surviving;
upgrade of an isolated bundle; 542/542 native domain checks; realtime and
authorization containment; and a fail-closed D8 validator.

**What is genuinely not proven:** any remediated dependency set; rollback;
deployed monitoring and alert delivery; multi-branch isolation; the Tailscale
boundary; the public edge; any capacity or availability objective; off-site
backup, retention and key custody in recovery; end-to-end change control.

**Shortest honest path forward:** grant `actions:write` and re-run Key Custody
(expected to pass — the custody logic is already evidenced at this commit). That
closes one blocked gate. Every other gate needs an owner decision before
engineering can proceed, and SEC-DEPS-01 needs upstream.
