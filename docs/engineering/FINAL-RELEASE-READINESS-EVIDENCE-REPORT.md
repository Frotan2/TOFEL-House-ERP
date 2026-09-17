# TOEFL House ERP — Final Production Readiness Evidence Closure

Date: 2026-09-16 · Owner-decision baseline: `14cd64e` · Active branch:
`arena/01a0aafe-tofel-house-erp` · Gap-closure addenda: §9 (2026-09-16),
§10 (2026-09-17), §11 (2026-09-17)

## 1. Final authorization state

| Control | Result |
|---|---|
| Production authorization | **REJECT** |
| Production enabled | **false** |
| Synthetic-only guard | **REQUIRED and unchanged** |
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** (re-executed and failed again on the active branch, run `35122242581`) |
| D8 overall | **BLOCKED** (no gate flipped to PASS by the fresh execution) |
| Numeric capacity/availability objective | **NOT SELECTED / BLOCKED** (none invented) |
| Requested local execution host | **ENVIRONMENT-BLOCKED** (no Docker Engine/Compose; see §8.1) |
| Production-like execution on a Docker-capable runner | **EXECUTED** at `d7df9ca7` — 5 runs, probe-by-probe classification in §8 |
| `site_encryption_key_restored=false` defect (P1) | **CLOSED** with hosted evidence — run `35133062884` at `58bd4d1`, independently reproduced by run `35135793582` (§9.1) |
| Container-level MariaDB/Redis durability (P2) | **EXECUTED** — runs `35135793802`, `35137645608` and `35138416558`; the `durability` gate stays **BLOCKED** because its area is wider (§9.2) |
| Independent-system recovery (P3) | **EXECUTED** at `1378ce4` — run `35170062251`: real destructive trigger, then recovery on a provably separate VM with HTTP usability proven; the `recovery` gate stays **BLOCKED** (§10) |

This is the canonical release-readiness report for the closure pass. It separates
owner decisions from technical evidence and does not treat a bounded harness,
static inspection, documentation, or synthetic product result as production proof.
No deployment, production credentials, customer data, public provider, hostname,
DNS, off-site destination, numeric RPO/RTO, capacity target or availability target
was invented or enabled.

**§8 records the production-like execution pass** requested for this release
review: what was genuinely executed on a Docker-capable runner, what was only
bounded/static/preflight, and what the runner could not provide. The
machine-readable probe-by-probe classification is
[`evidence/production-like-execution/execution-ledger.json`](evidence/production-like-execution/execution-ledger.json).

**§9, §10 and §11 record the gap-closure passes** that followed on the same
branch: P1 closed the `site_encryption_key_restored=false` defect, P2 executed
real container-level MariaDB and Redis durability, P3 executed a destructive
recovery onto a genuinely independent system, and P4 executed external custody
of both native keys across three separate systems, including restoration with a
retrieved key and rotation. Every one of those results comes
from real execution on hosted infrastructure, each is classified separately from
the bounded harness, and **none of them flips a D8 gate** — the bounded synthetic
evidence below is not upgraded by any of it.

The machine-readable run result is
[`evidence/release-readiness-evidence.json`](evidence/release-readiness-evidence.json).
Its bounded encrypted-restore manifest is
[`evidence/release-readiness/encrypted-restore-manifest.json`](evidence/release-readiness/encrypted-restore-manifest.json).
The manifest contains hashes and no key material, backup credentials or customer
data.

## 2. Owner decisions versus technical evidence

### Owner decisions recorded, but not evidence

The authoritative record is
[`canonical-owner-decision-record.json`](canonical-owner-decision-record.json).
It selects Course Owner/General Manager/Academic Manager/Finance Manager/Reception
responsibility, role-based access, auditability, offboarding preservation,
multi-branch architecture and branch-level isolation, current local/server
operation through Tailscale, local database/files, encrypted multi-version backup,
recovery onto another system, data-preservation priority, configurable business
policy and compensation models, controlled owner administration and health/
attention visibility. Portal and online payments remain deferred/not required at
launch.

Future internet provider/hostname/DNS/public edge, future off-site destination,
numeric RPO/RTO, numeric capacity/availability and other deferred domain policies
remain unselected. Owner selection does not close a technical evidence gate.

### Technical evidence produced in this pass

The command
`tools/foundation/release_readiness_evidence.py` created a disposable source
system and a physically separate restore-system directory. It generated three
versioned backups, encrypted a real tar archive with system OpenSSL AES-256-CBC
and PBKDF2, authenticated the ciphertext with HMAC-SHA256, rotated version 1,
restored version 3 into the separate system, and compared the complete source and
restore trees. The key was external to the archive and was not copied to the
restore tree.

The same run executed bounded models for offboarding/emergency revocation,
branch scope, audit records, alert delivery/fail-closed missing receiver, native
authority boundaries and versioned rollback. The bounded proof results are
recorded in the machine-readable report. They are implementation/harness proofs,
not deployed production evidence.

## 3. Scoped PASS gates and exact references

These are PASS results only within their stated scope. None is production
authorization.

| Gate/proof | Result | Exact evidence |
|---|---|---|
| Implemented domain qualification | **PASS / SCOPED** | `RELEASE-CANDIDATE-DOSSIER.md`; hosted runs `34932512626`, `34941341845`, `34946981784`, `34966681820`, `34999987969`; current connected release proof `35073376790` (`542/542`) |
| Implemented authorization/synthetic containment | **PASS / SCOPED** | `apps/toefl_house/toefl_house/security.py`; `tests/foundation/test_security_guards.py`; A13 hosted evidence `35008705885` (`523/523`); synthetic hard-stop check in `d8_validate.py` |
| Native-first authority boundary | **PASS / STATIC/SCOPED** | `DOMAIN-CONTRACT.md`; `ERP-CAPABILITY-MAP.md`; `PRODUCTION-OPERATIONS-IMPLEMENTATION-CONTRACT.md`; `tests/foundation/test_governance_surface.py`; no new student/course/accounting/payroll/permission authority introduced by the control centre |
| Owner/manager governance surface | **PASS / SCOPED** | `apps/toefl_house/toefl_house/administration.py`; native Page `th-administration-control-centre`; native `User` role assignment with native `Version` audit; `tests/foundation/test_governance_surface.py` |
| Encrypted versioned backup harness | **PASS / BOUNDED** | `evidence/release-readiness-evidence.json` → `proofs.encrypted_versioned_backup`; `encrypted-restore-manifest.json`; three versions created, versions 2 and 3 retained, OpenSSL encryption and HMAC verified |
| Restore onto another system harness | **PASS / BOUNDED** | Same machine report → `proofs.restore_on_another_system`; source `local-source-system`, restore `independent-restore-system`, equal source/restore tree digest |
| Database/file preservation harness | **PASS / BOUNDED** | Same manifest → `database_state_sha256`, `source_tree_sha256`, `restored_tree_sha256`, `same_tree: true`, private/public file preservation |
| External key boundary harness | **PASS / BOUNDED** | Same machine report → `proofs.key_custody_boundary`; key external to archive and absent from restore tree |
| Offboarding/emergency revocation model | **PASS / BOUNDED** | Same machine report → `proofs.offboarding_emergency_revocation`; active access removed and historical digest preserved |
| Auditability model/native implementation | **PASS / BOUNDED** | Same machine report → `proofs.auditability`; native `Version` authority and actor/request/before/after fields; governance static test |
| Rollback/change-control harness | **PASS / BOUNDED** | Same machine report → `proofs.rollback_change_control`; release A → B → A hash restoration |
| D8 contract integrity | **PASS / STRUCTURAL** | `python3 tools/foundation/d8_validate.py --contract docs/engineering/d8-operational-contract.template.json`; report remains `BLOCKED`, `REJECT`, and `SEC-DEPS-01` remains rejected |

## 4. Remaining BLOCKED/REJECT gates

Every gate below was re-examined against the fresh Docker-runner execution in
§8 and against the gap-closure executions in §9, §10 and §11. Where those
sections record genuinely executed sub-probes, they are cited there and in the
D8 matrix `evidence` fields; none of them closes a gate. Three of the
requirements listed here have now been executed for real — container-level
datastore restart and crash durability (§9.2), recovery onto an independent
system under a destructive trigger (§10), and external key custody with
retrieval and rotation across three separate systems (§11) — and each
corresponding gate still stays **BLOCKED** because its area is wider than the
executed sub-probe. The rest remain **not** executed: session revocation on
recovery, a measured RPO/RTO against an owner-selected objective, deployed
monitoring, TLS/Tailscale edge, full-bundle rollback rehearsal and any capacity
objective.

| Gate | Final state | Why it remains open |
|---|---|---|
| Recovery | **BLOCKED** | A separate-infrastructure rehearsal is now **EXECUTED** (§10, run `35170062251` at `1378ce4`): a real destructive `bench drop-site --no-backup`, then recovery on a provably separate VM with the database, both file trees and HTTP usability verified, including the private-file privacy boundary. **Key retrieval is now EXECUTED too** (§11, run `35179445639` at `252345e`): a third VM restored an *encrypted* backup using a key retrieved from separate custody, after proving by required failure that it could not restore without it, and decrypted the field §10 recorded as undecryptable. The bounded encrypted alternate-directory harness remains bounded and is not upgraded. Still absent: custody inside a real trust boundary (KMS/HSM/owner secret store — ENVIRONMENT-BLOCKED), session revocation on recovery, host/region loss, HTTP usability *after* a rotation, and a measured RPO/RTO against an owner-selected objective |
| Backup/restore | **BLOCKED** | A real `bench backup --with-files` set has now been produced, secret-scanned, transferred and verified byte-for-byte on a separate system, where `bench restore` recovered database, files and a usable application (§10). **Encryption at rest and key rotation are now EXECUTED** (§11, run `35179445639`): the same backup taken with System Settings `encrypt_backup` on leaves the machine as AES-256 GPG ciphertext — asserted with the `file` command, which is the same test `bench restore` applies — under keys issued by a separate custodian, and both keys were then rotated with the boundaries verified. Still absent: a selected production destination, versioned backup **sets**, retention, rotation of backup sets rather than of keys, custody in a real trust boundary, and session revocation; the future off-site destination remains unselected |
| Upgrade/rollback | **BLOCKED** | Local artifact rollback harness is not a full-bundle deployed upgrade/rollback rehearsal |
| Observability/incident | **BLOCKED** | Local alert model proves missing receivers fail closed, but no deployed logs/metrics/alert receiver/retention/incident evidence exists |
| Topology/edge/session | **BLOCKED** | Current Tailscale/local requirement is selected, but deployed network/session/TLS/CSRF/private-file/realtime evidence is absent; future public edge is unselected |
| Capacity/availability | **BLOCKED / NOT SELECTED** | No owner numeric objective was supplied; no claim is made |
| Durability | **BLOCKED** | Container-level MariaDB/Redis graceful restart, SIGKILL crash-recovery and container destruction with recreation from the same named volume are now **EXECUTED** against real servers, with persistence settings read back from the running instances and a negative control (§9.2, runs `35135793802`, `35137645608`, `35138416558`). File/database fixture preservation remains bounded. Still absent: host-loss drills beyond a single host, persistence verified across a host or region failure, queued/in-flight job handling under failure, configuration and key durability, and integrity measured against defined recovery objectives |
| Branch isolation | **BLOCKED / NOT PROVEN** | The evidence run passes a bounded branch-scope/aggregate model, but the checkout has no deployed native branch runtime/fixture proof across read/write/submit/export/file/job paths |
| Change control | **BLOCKED** | Static provenance and local rollback pass in bounded scope; deployed approval, artifact promotion, communication and restore-based rollback evidence is absent |
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** | Closure evidence records Foundation runtime `35090904508` as failed on dependency/frontend advisory gates; independent exact-PR-head run `35101709287` is separately tracked below and cannot waive this hard stop |
| Production authorization | **REJECT** | It is downstream of every applicable gate above and the dependency hard stop |

The bounded alerting harness is intentionally reported as a technical proof, not
an observability gate pass. The same fail-closed treatment applies to bounded
backup, restore, offboarding, audit and rollback proofs.

## 5. Reproducible commands

Run from the repository root on the active branch:

```sh
# Bounded encrypted backup/restore, revocation, audit, alert and rollback evidence
python3 tools/foundation/release_readiness_evidence.py \
  --output docs/engineering/evidence/release-readiness-evidence.json \
  --artifact-dir docs/engineering/evidence/release-readiness

# The test runs the same harness in a disposable temporary workspace
python3 -m unittest tests.foundation.test_release_readiness_evidence -v

# D8 branch, owner-record, ledger, synthetic-guard and production-enable checks
python3 tools/foundation/d8_validate.py \
  --contract docs/engineering/d8-operational-contract.template.json

# Existing static/native containment and governance checks
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/foundation/test_command_pages.cjs
```

The evidence harness requires the system `openssl` executable. It does not accept
an argument naming a Frappe site and never contacts production. A successful run
must still report `production_state: REJECT`; any attempt to turn the bounded
result into a production pass is invalid.

## 6. Canonical release conclusion

The repository now has independently rerunnable bounded evidence for encrypted
versioned backup mechanics, alternate-directory restore, data/file preservation,
external key boundary, offboarding preservation, native Version audit shape,
fail-closed alert behavior and artifact rollback. It does **not** have proof of
the deployed production architecture required by the owner-selected D8 contract.

## 7. Final independent audit of PR #2

Audit target: PR [#2](https://github.com/Frotan2/TOFEL-House-ERP/pull/2), audited
application head `95c19eec2edb658fde62c1240c57374e367bc6cb`, base `main` at
`9eccff957cadf036a3ac6f8208540a110148e67b`. The final report amendment is a
follow-on documentation-only commit; it does not alter the audited application
or test behavior. This section is an independent review record; it does not
replace the owner-decision record or turn scoped qualification into production
evidence.

### Diff provenance, scope, and repository hygiene

At the initial closure head `16d0d2ac97390999ed4a5ff54fc38b6d2d5ce2dc`,
GitHub reported **352 files changed, 63,852 additions, and 1 deletion**. The
final PR head `092b73aef894b78755d813a3a37720c190d4251e` reports **353 files,
64,126 additions, and 1 deletion** after adding the executable administration
coverage and final audit record. Both figures are explained by repository
history, not by a 63k-line product feature diff: `origin/main` is an unrelated
one-commit history containing only `README.md`, and `git merge-base
origin/main HEAD` returns no merge base. The PR comparison therefore presents
the active repository baseline as additions. The final active tree contains 353
tracked files: 143 Python, 116 JSON, 53 Markdown, 12 curated execution logs, 9
text, 6 YAML, 5 CommonJS, 3 ESM, 2 TOML, 2 JavaScript, one `.gitignore`, and one
reviewed evidence lockfile.

The file-by-file review found no `node_modules`, vendored source, build/dist or
coverage tree, bytecode, database/archive artifact, or duplicate repository
history. The logs, hosted JSON, and candidate lockfile are under the curated
`docs/engineering/evidence/phase-2/` evidence boundary and are referenced by
reports or review tooling; they are not runtime output accidentally committed at
repository root. A repository-local secret scan found no private keys, GitHub
personal tokens, AWS access keys, or generic quoted secret assignments. The
`.gitignore` excludes live site data, credentials, backups, runtime artifacts,
bytecode, and dependency trees.

### Native-first authority and duplication review

The 22 custom TOEFL House DocTypes are limited to placement qualification,
admission decision workflow, teaching/finance extensions, allocation guards,
operations, audit, and configuration revisions. None is named or implemented as
a Student, Course, Enrollment, Attendance, Invoice, Payment, Payroll, Permission,
Ledger, or Branch authority. The code references native Education/Frappe/ERPNext/
HRMS authorities for Student Applicant/Student, Program Enrollment, Course and
Program data, Student Group, Course Schedule, Student Attendance, Sales Invoice,
Fees, Company/Branch, User/Role/User Permission, Employee, and payroll records.
The control centre adds no parallel role, branch, accounting, student, payroll,
or operation ledger.

Native authority remains a scoped/static conclusion only where the deployment is
not present. Multi-branch isolation is not claimed: the implementation uses the
native Company/Branch and permission model, while native cross-branch read/write,
submit, export, file, and background-job isolation remain a blocked release gate.

### Administration Control Centre and security review

`administration.py` is a controlled facade, not a replacement authority. The
native Page is limited to Course Owner and General Manager; the snapshot is
non-sensitive readiness/attention projection; only Course Owner may mutate an
allow-listed managed role. Protected `Administrator` and `Guest` identities and
self-revocation of the acting operational role are rejected. Role assignment is
performed on native `User`, serialized with a native row lock, and recorded in
native `Version`; no custom role or permission ledger is introduced. Native Users,
Roles, User Permissions, Companies, Branches, and System Settings remain routes to
native authorities, and the page grants no implicit document permissions.

The audit found and fixed four related implementation defects on the active
branch: an already-satisfied role request did not create a receipt and could
reuse its idempotency key for a different request; concurrent retries could race
before receipt lookup; malformed non-object Version JSON could raise an
uncontrolled attribute error; and non-string role input could raise a type error.
The fix records no-op requests in native Version, locks the native User before
receipt lookup, validates the decoded record and role type, returns the recorded
`changed` state on replay, and blocks self-revocation of the acting operational
role. Executable tests cover no-op receipt/replay conflict, native row-lock
ordering, malformed role input, and self-revocation denial. No other
independently reproducible Administration Control Centre defect was found.

This does not claim deployed offboarding, session revocation, branch runtime
isolation, production backup custody, or unrestricted native permission safety;
those remain evidence gates and are intentionally not manufactured by this PR.
The bounded offboarding harness preserves history while removing active access,
but it is not deployed evidence.

### Canonical-document reconciliation and validation

The canonical owner-decision record, D8 matrix, acceptance ledger, release dossier,
gap map, machine-readable evidence, and this report agree on the required hard
stops: production authorization `REJECT`, `production_enabled=false`,
synthetic-only `REQUIRED`, and `SEC-DEPS-01=UPSTREAM-BLOCKED / REJECT`. The
acceptance ledger's `latest_branch_head_at_reconciliation` is historical
qualification provenance, not a claim about this PR head; older hosted run
references in the closure packet are retained as historical evidence. This
report now identifies the exact PR-head checks separately to avoid treating those
older references as current status.

Independent local results after the audit fix:

| Validation | Result |
|---|---|
| Governance, idempotency, and bounded evidence tests | **6 passed** |
| Full Python test discovery | **313 passed** |
| D8 contract validator | **exit 0; intentional BLOCKED/REJECT report** |
| Realtime guard | **PASS** |
| D10 command-page and native-dialog smoke | **PASS** |
| Secret, generated-content, duplicate-authority and scope scans | **PASS within repository/static scope** |

Exact GitHub Actions results for the audited application head at the time of
this report: D8 operations contract run `35101709220` on the immediately prior
closure head `16d0d2ac97390999ed4a5ff54fc38b6d2d5ce2dc` completed **SUCCESS**;
the D8 paths were unchanged by the administration fix. Current-head Foundation
runtime run `35104267675` targets `95c19eec2edb658fde62c1240c57374e367bc6cb` and
was **PENDING**. Earlier exact-head runtime run `35101709287` remained
**IN_PROGRESS** with no updated job state and blocked the same concurrency group;
an attempted cancellation returned GitHub **403**, so it was not treated as a
pass or silently discarded. The completed pre-install steps of that earlier
run passed, but its pinned foundation installation gate had no final result at
this audit. The final PR head `092b73aef894b78755d813a3a37720c190d4251e` is a
report-only descendant and currently has **no checks reported**, so no CI result
is implied for that head. Current local D8 validation is passing structurally
while reporting the required BLOCKED/REJECT state. The final documentation-only
amendment does not change these application conclusions.

### Independent audit conclusion

The PR delta is a history-baseline artifact plus a coherent, intentionally
scoped application/evidence tree; it is not evidence of vendoring or accidental
repository duplication. Native authority and the controlled governance facade
are structurally aligned, with the idempotency/concurrency defects above fixed
and covered by governance-source assertions. The PR remains **not production
ready** because the selected D8 deployment/recovery/branch/observability/
capacity/durability/change-control evidence is not independently proven and the
security dependency hard stop remains.

**Final production authorization: REJECT.** Do not enable production, relax the
synthetic-only guard, waive or reinterpret SEC-DEPS-01, relabel bounded synthetic
proof as production evidence, or merge this PR.

## 8. Production-like execution pass on the active branch (2026-09-16)

This section records the requested production-like readiness execution. It keeps
executed evidence strictly separate from preflight, static, mocked and bounded
evidence, and it records unavailable capabilities as BLOCKED or
ENVIRONMENT-BLOCKED instead of simulating success.

Machine-readable ledger:
[`evidence/production-like-execution/execution-ledger.json`](evidence/production-like-execution/execution-ledger.json).
Every archived report carries a SHA-256 in that ledger.

### 8.1 Named commit `d3705e6` does not exist

The pass was asked to resume from commit `d3705e6`. That object does not exist
and was not fabricated, guessed or substituted:

| Verification | Result |
|---|---|
| `git cat-file -t d3705e6` | `fatal: Not a valid object name d3705e6` |
| `git fsck --lost-found --dangling` | no dangling or lost objects |
| `git log --all --oneline` | only `60c777e` and `9eccff9` existed locally |
| `gh api repos/Frotan2/TOFEL-House-ERP/commits/d3705e6` | HTTP **422** — "No commit found for SHA: d3705e6" |
| `gh api search/commits?q=repo:Frotan2/TOFEL-House-ERP+d3705e6` | `total_count: 0` |
| `grep -rn d3705e6` across the working tree | no reference |

At the start of the pass the active branch `arena/01a0aafe-tofel-house-erp` was
at `60c777e81c679b7b7940c01045247102d51db024` with a clean tree — byte-identical
to the already-pushed prior-session head — and the branch itself did not yet
exist on GitHub. There was therefore **no unpushed commit to publish**. The
branch was published to GitHub, and all work in this pass is committed on top of
it as `d7df9ca766cd3039d68051ca83cdc8be5e834452` and descendants.

### 8.2 The requesting host cannot execute the harness (ENVIRONMENT-BLOCKED)

The local sandbox was probed rather than assumed
([capability probe](evidence/production-like-execution/local-runner-capability-probe.json),
all commands and raw outputs inline):

- No `docker`, `docker-compose` or `podman` binary; `/var/run/docker.sock` absent.
- Docker cannot be installed: `deb.debian.org` and `download.docker.com` are both
  unreachable (`apt-get update` fails, `apt-cache policy docker.io` is empty),
  while `pypi.org`, `github.com` and `registry.npmjs.org` return 200 — a
  selective egress allowlist, not a general outage.
- `/lib/modules` is absent so container storage/networking modules cannot be
  loaded, and `/proc` is mounted read-only.
- Envelope: 2 vCPU, ~3.8 GiB RAM, ~20 GiB disk — below a production-like
  Frappe/ERPNext/Education/HRMS stack plus MariaDB and Redis.

Determination: **ENVIRONMENT-BLOCKED** for Docker Engine, Docker Compose and
package installation. Per the evidence rules, no local check-only or preflight
result (including `evidence/phase-2/docker-preflight.json`) was promoted to
execution evidence.

### 8.3 Authorized Docker-capable venue and the runs actually executed

The harness's own guards authorize an ephemeral GitHub-hosted runner, which
genuinely provides Docker Engine, Docker Compose, sufficient resources and
permission to create isolated synthetic sites, databases and services. The
executable branch boundary in `tools/session_branch.py` was rotated from
`arena/01a0a9f7-tofel-house-erp` to the current session branch using the
procedure that module documents — canonical value, workflow filters, hosted
guards and qualification tests in one change — because an unrotated boundary
makes the checkout fail its own branch-qualification test and prevents any
hosted execution on the active branch. Recorded historical provenance was left
untouched.

Execution commit `d7df9ca766cd3039d68051ca83cdc8be5e834452` on
`arena/01a0aafe-tofel-house-erp`, runner image `ubuntu24` / `20260907.300.1`,
**Docker 28.0.4**, **Compose 2.38.2**:

| Workflow | Run | Conclusion | Evidence |
|---|---:|---|---|
| Foundation runner qualification | [`35122242676`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242676) | **success** — 18/18 | Check `104882875418` |
| Placement synthetic content qualification | [`35122242728`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242728) | **success** — 542/542 native, 101/101 runner | Checks `104885934034`, `104885938426` |
| Foundation runtime validation | [`35122242581`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242581) | **failure** — SEC-DEPS-01 | Checks `104889030990`, `104889035777` |
| Foundation frontend candidate review | [`35122242647`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242647) | **failure** — not adopted | Check `104882992093` |
| D8 operations contract validation | [`35122242888`](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/35122242888) | **success** — structural, reports BLOCKED/REJECT | Check `104882627814` |

Runner artifact ZIPs and workflow logs are hosted on Azure blob /
results-receiver endpoints that return `EOF` from this environment, so evidence
was retrieved through the repository's own sanctioned Checks-API transport
(`tools/foundation/publish_evidence.py`), which publishes the complete sanitized
report losslessly. Each retrieved report is archived under
`evidence/production-like-execution/` with its SHA-256.

Pushing the evidence commit `c891949` re-triggered the hosted gates because
`tools/session_branch.py` and `tools/foundation/d8_validate.py` are in their path
filters. All five conclusions were retrieved from the GitHub API:

| Run | Workflow | Conclusion |
|---:|---|---|
| `35125669493` | D8 operations contract validation | **success** |
| `35125669408` | Foundation runner qualification | **success** — 18/18, MariaDB healthy in 4 polls, identical pinned digests |
| `35125669475` | Placement synthetic content qualification | **success** |
| `35125669372` | Foundation frontend candidate review | **failure** — not adopted |
| `35125669370` | Foundation runtime validation | **failure** — step 7, SEC-DEPS-01 |

**Reproduction finding.** Run `35125669370` at `c891949` reproduces run
`35122242581` at `d7df9ca` field for field on every outcome that matters: the
same SEC-DEPS-01 failure with both dependency audits exiting 1, the same
114/116 restricted checks, the same four sites and four installed apps, the same
readiness 54 / realtime 4 / upgrade 33 / guardian-browser 6 passes, the same 57
npm advisory findings across 21 packages and 14 PyPI/OSV findings across
`pdfkit`, `pypdf`, `setuptools` and `weasyprint`, and the same
`site_encryption_key_restored=false` defect. Two independent executions at two
commits agree, which strengthens the REJECT conclusion rather than weakening it.
Its full reports are archived as
[`hosted-runtime-35125669370.json`](evidence/production-like-execution/hosted-runtime-35125669370.json)
and
[`hosted-remaining-gates-35125669370.json`](evidence/production-like-execution/hosted-remaining-gates-35125669370.json).
These re-runs are corroboration; `session_branch.ACTIVE_RUNTIME_RUN` stays pinned
to `35122242581`, whose complete report the probe classifications cite.

**Credential outage, and how it was handled.** Partway through the pass
`gh auth status` reported *"The github.com token in GH_TOKEN is no longer valid"*;
`api.github.com` returned 401 while `github.com` returned 200, so this was an
authentication failure rather than a network outage, and `git push` failed the
same way. While it was invalid, the runtime conclusion at `c891949` was recorded
as **NOT RETRIEVED** and was explicitly *not* assumed to be a failure merely
because every prior runtime run had failed; the PR #2 comment was queued verbatim
rather than paraphrased or silently dropped. No result was invented during the
outage and credentials were never requested or stored. Authentication was
restored on the following turn and all three outstanding items were then
completed: the runtime conclusion was retrieved and archived, the commit was
pushed, and the PR #2 comment was posted.

### 8.4 Probe-by-probe classification

| # | Requested probe | Classification | Executed and genuinely proven | Not executed — remains open |
|---:|---|---|---|---|
| 1 | MariaDB startup, health, restart persistence, durability | **PARTIAL** | Start to `healthy` in 5 polls; version; `utf8mb4`/`utf8mb4_unicode_ci`; `START TRANSACTION`/`ROLLBACK` count 0; pinned digest `sha256:8b5f33eb…`; hosting three real bench sites | MariaDB restart persistence; crash/power-loss/volume-loss durability; durability on the selected local/server host |
| 2 | Redis persistence and restart recovery | **PARTIAL** | Queue and cache instances started; `PING`→`PONG`; version; digest `sha256:75934ddb…`; cache marker survived an app restart | RDB/AOF persistence; Redis restart recovery; in-flight/exactly-once job semantics |
| 3 | Versioned encrypted backups, external key custody, rotation | **BLOCKED** | Real backups with SHA-256 over database, private and public files, plus a hardened variant | Version series and retention; encryption at rest; external custody; rotation. **Executed defect:** run `35122242581` reports `site_encryption_key_restored=false` (run `35122242728` reports `true`); both recorded, neither reclassified |
| 4 | Destructive/recovery then restore into a genuinely independent system | **PARTIAL** | Restore into a separate site **and** separate database, `source_db_credentials_copied=false`; post-restore authorization re-verification | Independent system/environment (all targets were the same ephemeral host); destructive trigger; measured recovery objective |
| 5 | Database and file integrity before/after recovery | **PASS (EXECUTED) / SCOPED** | Snapshot captured before backup and verified after restore across 14 doctypes by exact record count; `private_file_sha256_verified=true` | Whole-database checksum equality; cross-system comparison |
| 6 | Native Frappe/ERPNext/Education runtime with authorization/branch isolation | **PASS (EXECUTED) / SCOPED-SYNTHETIC** | Real bench with frappe, erpnext, education, payments, hrms, `foundation_security`, `toefl_house`; 542/542 native checks; two isolated sites; isolation 47/47; guardian browser 6/6 (own 200 vs other 403); upstream `user_permission` 10 and `docshare` 15 pass; all five app pins unchanged | Deployed multi-branch (Company/Branch) isolation across read/write/submit/export/file/job paths |
| 7 | Authentication/session/offboarding/emergency revocation | **PARTIAL** | `http-role-revocation-old-session-denied`; `http-teaching-revoked-scheduler-old-session-denied`; `cross-site-session-replay-denied`; `live-session-revocation-stops-document-and-task-delivery`; source session 200 vs recovery site 403; readiness 54/54 | Offboarding as an operational process; credential/key rotation; audit retention over time |
| 8 | Monitoring, alert delivery, retention, fail-closed | **BLOCKED** | `release-observability-probes`: native Error Log roundtrip, Scheduled Job Type registry, health ping | Alert receiver and delivery; retention/rotation/archival; deployed fail-closed behavior; incident response |
| 9 | Edge/session/TLS boundaries for the local/server + Tailscale phase | **PARTIAL** | CSRF token presence per site/role; 13 CSRF negative-with-positive-control checks; private-file own/other/guest isolation; `private-file-still-isolated-after-share-attempts`; REST/RPC write denial | TLS termination/certificates/HSTS; reverse proxy and public edge; cookie attributes under the real edge; the Tailscale tailnet/ACL boundary (all traffic was plain `http://127.0.0.1:8000`) |
| 10 | Full artifact-based upgrade and rollback rehearsal | **PARTIAL** | Isolated artifact-based Frappe patch upgrade 33/33, `33bf510b…` → `988e54f3…`, other four pins held fixed | Rollback rehearsal (explicitly out of the harness scope); full-bundle upgrade; promotion/approval/communication |
| 11 | Capacity/availability observations, no invented SLOs | **BLOCKED / NOT SELECTED** | Descriptive timings and runner envelope only | Any load, concurrency, soak, overload, failover or availability measurement. **No numeric objective invented** |

Tally: 2 executed-and-scoped passes, 6 partial, 3 blocked. **No D8 release gate
flips to PASS.**

### 8.5 Separately classified, never counted as execution evidence

- **PASS / BOUNDED** — real local execution over synthetic fixtures: versioned
  encrypted backup with OpenSSL AES-256-CBC + PBKDF2, HMAC-SHA256, three
  versions with v1 rotated, external key absent from the restore tree,
  alternate-directory restore with equal tree digests, offboarding/history
  preservation, audit shape, alert fail-closed on a missing receiver, artifact
  rollback A→B→A
  ([`local-bounded-release-readiness-evidence.json`](evidence/production-like-execution/local-bounded-release-readiness-evidence.json),
  [`local-bounded-encrypted-restore-manifest.json`](evidence/production-like-execution/local-bounded-encrypted-restore-manifest.json)).
  Its own `branch_isolation` and `monitoring_alerting` proofs report
  **BLOCKED / NOT PROVEN**.
- **PASS / STRUCTURAL** — D8 validator and contract tests: exit 0 while
  reporting BLOCKED, REJECT, `production_enabled=false`, synthetic-only
  REQUIRED, SEC-DEPS-01 UPSTREAM-BLOCKED / REJECT,
  `checkout_branch_matches_active=true`
  ([`local-d8-validate.json`](evidence/production-like-execution/local-d8-validate.json)).
- **Local suite** — 313 Python tests pass; realtime guard PASS; D10
  command-page/native-dialog smoke PASS (14 pages)
  ([`local-unittest-313.txt`](evidence/production-like-execution/local-unittest-313.txt)).
- **PREFLIGHT** — `evidence/phase-2/docker-preflight.json` remains toolchain
  availability only and is explicitly not execution evidence.

### 8.6 Hard stops preserved

`production_enabled=false`, production authorization **REJECT**, synthetic-only
guard **REQUIRED**, SEC-DEPS-01 **UPSTREAM-BLOCKED / REJECT**, D8 overall
**BLOCKED**. The validator's pinned active-branch runtime assertion was moved to
the genuine current run and its historical pin retained under
`prior_active_branch_provenance`; it additionally forbids the active branch from
ever reporting a passing Foundation runtime or a true phase2/security/product
flag while SEC-DEPS-01 is open. No gate was weakened, waived or reinterpreted,
no bounded or static result was relabelled as production evidence, and PR #2 was
**not** merged.

---

## 9. Gap-closure execution on the active branch (2026-09-16)

Work resumed from `251eb8d` after the sandbox was re-cloned at `60c777e` and
reconciled by `git fetch` plus `git reset FETCH_HEAD`; the working tree was
verified byte-identical to the pushed tip, so no completed work was repeated.
This section records only the two priorities advanced so far.

### 9.1 P1 — `site_encryption_key_restored=false` is CLOSED

**Status: CLOSED with genuine hosted execution evidence. No gate changed state.**

**Root cause, established from the executable code rather than inferred.** Frappe
writes `encryption_key` into `sites/<site>/site_config.json` *lazily*, on the
first call to `frappe.utils.password.get_encryption_key()`; `bench new-site`
does not create it. `foundation.localhost` installs only erpnext, education,
payments and hrms, so nothing triggered key generation before the first backup.
The harness then copied the key across with
`if "encryption_key" in original_config:` — a silent no-op — and reported the
omission as a passive observation
(`report["site_encryption_key_restored"] = "encryption_key" in original_config`)
instead of failing. `placement-test.localhost` installs `toefl_house`, whose
`after_install()` calls `get_encryption_key()`, which is why that path reported
`true` and masked the defect.

**Fix (`bd5ca02`, `58bd4d1`).** The key is now initialized through the same
native call the application's own hook uses, before the first backup. An
encrypted Password field is written before the backup so the restore has real
ciphertext to prove against. The silent conditional is gone: both restore cycles
call the shared pure helper `restore_key_into_config()`, which raises on a
keyless source, a same-database restore, or reused source credentials. Survival
is proven three ways — SHA-256 key-fingerprint match against the source, real
`get_decrypted_password()` of content encrypted before the backup, and a
byte-identical ciphertext digest. Presence of a key string alone is no longer
accepted. Only fingerprints and byte lengths reach evidence; the fingerprint
file is `0600` inside the unpublished runner lab.

**The interim run that produced the second fix.** Run `35131838300` at `bd5ca02`
(check `104916683776`) failed at `prepare-native-encrypted-fixture-before-backup`
with `AssertionError: Password field was not stored as ciphertext`. That run had
already confirmed the root-cause fix worked
(`site_encryption_key_initialized=true`, key fingerprint
`0aaefb5a94b3228aca1a2742d358a853225bd18990eb420059ee64e12c69965d`). The
failure was in the new observation logic: it read only the raw model column and
treated an empty result as proof that encryption had not happened. The
successful run confirms the real layout — the value lives at `__Auth.password`
and the model column is empty. An empty model column is not evidence of
plaintext storage. `58bd4d1` replaced that assumption with
`stored_representations()`, which enumerates the supported native locations and
fails closed only on real plaintext or on nothing stored at all.

**Proof run `35133062884`** — Foundation runtime validation, profile `hardened`,
commit `58bd4d12f0c755e2f83c4c35eb206db40dfeafd7`, branch
`arena/01a0aafe-tofel-house-erp`. Overall conclusion **failure**, for SEC-DEPS-01
only: of 121 checks executed the sole failures are
`hosted-full-stack-dependency-audit` and `hosted-frontend-advisory-audit`. No
recovery, restore or encryption check failed.

| Observation | First cycle (`restore.localhost`) | Hardened cycle (`recovery.localhost`) |
| --- | --- | --- |
| `site_encryption_key_initialized` | `true` (fingerprint `0b0a2acd41573cc685791fd845a241b5c5a1c554e707c6930d59a960fb17e585`, length 44) | same key |
| `storage_location` | `__Auth.password` | `__Auth.password` |
| `source_db_credentials_copied` | `false` | `false` |
| `fingerprint_matches_source` | `true` | `true` |
| `encrypted_content_decrypts_after_restore` | `true` | `true` |
| ciphertext SHA-256 before backup | `9f771296df54e4c6cd16dead00b62b5993d8d450569ffd0de38b0b21f11caafd` | `029f68b1876ddd0532d1b4e1798faa6e06e458f4b11714f08fe8f2ed8a5ae5c3` |
| ciphertext SHA-256 after restore | `9f771296df54e4c6cd16dead00b62b5993d8d450569ffd0de38b0b21f11caafd` | `029f68b1876ddd0532d1b4e1798faa6e06e458f4b11714f08fe8f2ed8a5ae5c3` |
| `site_encryption_key_restored` | **`true`** | **`true`** (`..._hardened`) |
| verify step | `verify-encryption-key-survived-restore`, 0.661s, pass | `verify-encryption-key-survived-hardened-recovery`, 0.696s, pass |

The two cycles legitimately have different ciphertext digests: the hardened path
re-runs `prepare-native-encrypted-recovery-fixture`, which re-encrypts the same
secret, and Fernet output is randomized per encryption. The harness therefore
re-records the digest immediately before that backup so the comparison is
against the bytes that actually went into it. The observed difference is direct
confirmation that this re-record step was necessary rather than decorative.

Hardened backup digests from the same run: database 1158728 bytes
`0d799d4097a5670fd3a3fc509b88a4d8cfd0aaee0179669c61e55c4d83cb5360`, private
files 10240 bytes `85bea42b7307a6dc3943bd6380f5e5907388f47bd180a8e6a305329dc553425d`,
public files 10240 bytes `9c543b407e134d7d27d9720d99ff0fe2298ce7587e1aa463bd826675c36e3c53`.

**Independently reproduced.** Run `35135793582` at commit `866396a` (check
`104934304007`) repeats the result on a different commit in a different run:
`site_encryption_key_restored=true` and
`site_encryption_key_restored_hardened=true`, `storage_location` again
`__Auth.password`, `source_db_credentials_copied=false`, all three proof
conditions true on both cycles, 121 checks with the identical SEC-DEPS-01-only
failure profile. The key fingerprint (`566c8f5c06ac19a29c556fa146a2095f6fb2447eebf55155b07d2000dd6b55bf`)
and both ciphertext digests (`c8bc1cc141c4fb12…`, `d8f34687db6c4bf7…`) **differ**
from the first run, because the key is generated per run and Fernet output is
randomized per encryption. Identical outcomes on freshly generated key material
is what makes this a reproduction rather than a replay of the same bytes.
Archived as `hosted-runtime-35135793582.json`, SHA-256
`6cfb435d86f3ba0dcb04c8a939cfaf850b4317d00eff3f0442eb6e13e2ad77d5`.

**Retrieved and archived** (Checks API, the only transport that works from this
host): `evidence/production-like-execution/hosted-runtime-35133062884.json`
SHA-256 `fa799c1b259b42750bef2bd7b660f914690eacfe6b389fbcd290a7ea8f5e2780` and
`hosted-remaining-gates-35133062884.json` SHA-256
`981ac18610ae0fb9c744645123922cd7ea78882969f8316ee3416d9ad99a2dda`.

```bash
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/104925371177 --jq '.output.text'
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/104925376227 --jq '.output.text'
```

**Regression coverage.** `tests/foundation/test_encryption_key_recovery.py`, 31
tests. `fingerprint_key`, `restore_key_into_config`,
`stored_representations` and `assert_no_plaintext_at_rest` are imported by the
hosted harness rather than re-implemented, so the tests exercise the same code
that runs on the runner. Includes a direct regression for the observed failure:
ciphertext located via `__Auth` while the model column is NULL. Full suite 369
tests pass; `d8_validate.py` exits 0 with no gate drift.

**What this does not do.** It closes one named recovery defect on the same
disposable hosted runner. Restore still runs on the same ephemeral host as the
source, no destructive trigger has been exercised, and the site encryption key
is still generated on and copied by that same runner rather than held under
separately controlled custody. `recovery` and `backup-restore` therefore remain
**BLOCKED**, and this is not production qualification.

### 9.2 P2 — real MariaDB and Redis durability is EXECUTED

**Status: container-level durability genuinely executed and PASSING. The
durability gate remains BLOCKED, because its area is wider than container
restarts.**

The gate recorded that no MariaDB or Redis restart, no crash or volume-loss
probe and no RDB/AOF persistence verification had ever been executed, and that
the only restart probe was Gunicorn/RQ process replacement which explicitly
excludes the datastore. `tools/foundation/runtime_durability.py` and
`.github/workflows/foundation-durability.yml` close that gap with real
containers. Nothing is mocked, simulated or substituted.

**Run `35135793802`** — Foundation datastore durability, commit
`866396a127164090c41db9ff1bc310ade555409f`, check `104927987397`, conclusion
**success**, report status **pass**, Docker 28.0.4, job wall time 48s
(18:39:52Z–18:40:40Z). Archived as
`evidence/production-like-execution/hosted-durability-35135793802.json`, SHA-256
`8c93b6e7de91f6d58bb2794c9cd45ac0510ad1aed659c5bae250236d00666e65`.

The digest-pinned images reported their own versions from inside the running
servers: `11.8.9-MariaDB-ubu2404-log` and Redis `8.6.6` standalone. Durability
settings were configured explicitly and then **read back from the live servers**
rather than assumed from the command line — `innodb_flush_log_at_trx_commit=1`,
`sync_binlog=1`, `log_bin=1`; `aof_enabled=1`, `appendfsync always`,
`aof_last_write_status=ok`, `rdb_last_bgsave_status=ok`. The probe aborts if
they did not take effect.

Pre-state captured before any disruption: 25 committed rows with an
order-independent `SUM(CRC32(...))` payload checksum of **51945241053**, a Redis
value digest and a 25-item queue digest, and an open uncommitted transaction held
in a separate client session.

| Scenario | Real operation | Result |
| --- | --- | --- |
| 1. Graceful restart | `docker restart` both live servers | survived; CRC and row count identical; Redis digests identical; uncommitted transaction absent |
| 2. Crash | `docker kill --signal=KILL`, both containers observed `exited`/`unhealthy`, then cold start | survived; identical CRC; uncommitted transaction rolled back by InnoDB recovery |
| 3. Container destruction | `docker rm --force`, then new containers recreated from the **same** named volume | survived; identical CRC; new container IDs prove genuine replacement (mariadb `12e831ef68ca`→`c081c5c03e39`, redis `c25b3f0c1c9e`→`0b72e4d5ec16`) |
| 4. Negative control | volume removed, fresh container started | table no longer exists — `confirms_data_lived_in_the_volume: true` |

**Independent proof that the servers really restarted.** The binary log rotated
once per server start: `mariadb-bin.000001` → `000002` → `000003` (graceful
restart) → `000004` (SIGKILL cold start) → `000005` (recreation from volume).
This is server-side evidence that four real restarts occurred, independent of
the query results. The negative control is what makes the survival attributable
to the volume rather than to luck.

**Two weaknesses in that passing run were then fixed rather than left
passing-but-thin** (commit `699ad7e`):

1. The binlog progression was the strongest restart proof but was incidental —
   recorded and never checked. `assert_binlog_rotated()` now fails the run if the
   count does not strictly increase per scenario, and the whole progression is
   reported.
2. `innodb_recovery_messages` came back **empty**, because the filter matched
   only `recovery` or `crash` and MariaDB 11.8 logged neither in the captured
   window. The crash scenario therefore passed on data integrity alone with no
   server-side corroboration that recovery ran. The filter now covers `innodb`,
   `redo`, `rollback`, `roll back`, `ready for connections`, `shutdown` and
   `starting`, keeps the **last** matching lines (because `docker logs` returns
   the whole container history and the post-crash start is at the end), and an
   empty result now fails the run.

**The stricter probe has now produced its own hosted PASS.** Run `35137645608`
at commit `9b96199`, check `104934194163`, conclusion **success**, report status
**pass**. The enforced binary-log invariant held across the whole progression
(`pre_state 2 → graceful restart 3 → crash recovery 4 → volume persistence 5`),
all three scenarios again preserved row count 25 and CRC32 checksum 51945241053
exactly, the uncommitted transaction stayed invisible, and the negative control
again confirmed the data lived in the volume. Archived as
`evidence/production-like-execution/hosted-durability-35137645608.json`, SHA-256
`6f9b379d132ed131d38e68647397b9b9f197312fe5312990e75c191fd0da408b`. Run
`35135793802` is retained as provenance and is not relabelled.

**That re-run then exposed a third defect, in the evidence rather than the
probe's behaviour.** The broadened log filter captured exactly one line:
`[Entrypoint]: Starting temporary server`. That is container startup noise, not
InnoDB crash recovery, so the non-empty check was satisfied while the field name
`innodb_recovery_messages` overstated what had been proven. The substantive
durability proof was never affected — the checksum, rollback and binlog evidence
were all present — but a misleading label in an evidence ledger is itself a
defect. Commit `e92c66e` fixes it:

1. Crash markers (`innodb`, `recovery`, `crash`, `redo`, `rollback`,
   `roll back`) and startup markers (`ready for connections`, `shutdown`,
   `starting`, `entrypoint`) are recorded in **separate** fields and never merged.
2. `SHOW ENGINE INNODB STATUS` is captured and its `LOG` section recorded as the
   authoritative native source for recovery position, because MariaDB does not
   reliably emit crash-recovery lines at default verbosity. A log grep was never
   the right primary source.
3. The run fails closed only when there is neither a genuine InnoDB log line nor
   an `INNODB STATUS` LOG section.
4. `innodb_force_recovery` is read back and must be `0`; any other value would
   make crash recovery skip work and silently void the scenario.
5. `extract_innodb_section()` moved to module level so it is executed against a
   realistic fixture. That test immediately caught a real defect: the first
   implementation stopped on the dash rule that *closes* the header and returned
   only `['LOG']`.

**Commit `e92c66e` has now produced its own hosted PASS.** Run `35138416558` at
commit `fd94e8f`, check `104936842736`, conclusion **success**, report status
**pass**. This is the authoritative durability evidence, because it is the first
run in which the crash scenario is corroborated by an authoritative native source
rather than a log grep:

- `innodb_recovery_messages` is correctly **empty** — MariaDB 11.8 emits no
  crash-recovery lines at default verbosity, and the probe no longer fills that
  field with startup noise to make it look non-empty.
- The entrypoint lines that were previously mislabeled as recovery evidence now
  sit in their own `server_startup_messages` field.
- `SHOW ENGINE INNODB STATUS` supplies the real recovery position: log sequence
  number `52305` equal to log flushed up to `52305`, pages flushed up to `51911`,
  last checkpoint at `51911`.
- `innodb_force_recovery` reads back `0`, proving crash recovery was not bypassed.
- The binary-log progression is enforced and held: `2 → 3 → 4 → 5`.
- All three scenarios again preserved row count 25 and CRC32 checksum
  `51945241053` exactly; the negative control again confirmed the data lived in
  the volume; new container IDs again confirmed genuine replacement.

The run would now fail closed if neither a genuine InnoDB log line nor an
`INNODB STATUS` LOG section were present, so this evidence cannot silently
degrade back into a mislabeled grep match. Archived as
`evidence/production-like-execution/hosted-durability-35138416558.json`, SHA-256
`b5bd967bfa51c84040911404a3c32f2170baace6388c3a81016c5c4f0596fd9b`.

`tests/foundation/test_durability_contract.py`, 27 tests, guards the contract,
including an executed check that the probe refuses to run outside an ephemeral
Actions runner. Full suite 371 tests pass; `d8_validate.py` exits 0 with no gate
drift.

**Why the gate stays BLOCKED.** The probe itself states what it does not prove:
host or region loss, storage-array failure and off-site replication; HA, failover
and multi-node quorum behaviour; application-level workflow correctness after
recovery; backup archive integrity; and any owner-selected durability reference
or retention objective. The gate's area also covers configuration, private/public
file and encryption-key durability, none of which is proven — the site encryption
key is still generated and copied by the same ephemeral runner. The owner
durability references required by `D8-DURABLE-STATE` (`mariadb_durability_reference`,
`redis_durability_reference`, `site_configuration_custody_reference`,
`encryption_key_custody_reference`, `private_file_storage_reference`,
`public_asset_storage_reference`) remain **NOT SELECTED** and are not invented
here.

### 9.3 Hard stops preserved through gap closure

`production_enabled=false`, production authorization **REJECT**, synthetic-only
guard **REQUIRED**, SEC-DEPS-01 **UPSTREAM-BLOCKED / REJECT**, D8 overall
**BLOCKED**, `capacity-availability` **NOT SELECTED** with no owner numeric
objective invented. SEC-DEPS-01 has now failed at three commits on this branch
(`d7df9ca`, `c891949`, `58bd4d1`); no dependency version was forced, no lock was
overridden, no package was forked, no advisory was suppressed and the gate was
not downgraded. Historical provenance is preserved unchanged — the new run is
recorded alongside the prior runs, never relabelled over them. PR #2 remains
**OPEN** and unmerged.

### 9.4 GitHub credential outage — opened and RESOLVED

The `GH_TOKEN` in this sandbox expired while gap-closure work was in flight.
`gh auth status` reported *"The github.com token in GH_TOKEN is no longer valid"*
and the REST API returned `Bad credentials`, so `git push` failed with *"could not
read Username for 'https://github.com': terminal prompts disabled"*. Commits
`699ad7e` and `9b96199` were complete locally but could not be pushed.

**Resolved.** Credentials were restored on the following turn; both commits were
pushed (`866396a..9b96199`) and the stricter durability probe then produced its
own hosted PASS at run `35137645608`.

While the outage was open the local remote-tracking reference was also found to
be stale at `251eb8d` with no upstream configured — a residue of the earlier
sandbox re-clone. It was corrected to `866396a` on the strength of API evidence
(`gh api .../commits/866396a/check-runs` had returned runs, which only exist for
commits on that branch), **not** by assumption. The subsequent push fast-forwarded
from exactly `866396a`, confirming the correction was right.

No evidence was inferred, fabricated or backdated at any point during the outage,
and the missing re-run was recorded as a blocker in `execution-ledger.json`
rather than reported as done.

### 9.5 Evidence-integrity self-check performed during this pass

Every 40-hex identifier in the four canonical documents was verified
programmatically. All seven commit SHAs resolve to real git objects via
`git cat-file -t`. The remaining thirteen are pre-existing content: upstream
application source revisions (frappe, erpnext, education, payments, hrms) and
prior-run commits recorded in earlier sessions, all confirmed present in the
`251eb8d` baseline. One full commit SHA was transcribed by hand during this pass
and was **wrong**; it was detected by this check, replaced with the output of
`git rev-parse 866396a`, and annotated as machine-resolved. Hand-transcribed
identifiers are not acceptable in an evidence ledger.

## 10. P3 — recovery onto a genuinely independent system is EXECUTED (2026-09-17)

**Status: EXECUTED on hosted infrastructure and CLOSED as a probe. No gate
changed state.** Run `35170062251` at commit `1378ce4` on branch
`arena/01a0aafe-tofel-house-erp`, workflow *Foundation independent-system
recovery* (`.github/workflows/foundation-independent-recovery.yml`), both jobs
`success`: source check run `105041393483` (29/29 checks pass) and target
check run `105042127143` (31/31 pass). `mocks_or_simulations_used=false` on
both halves.

This closes the third gap-closure priority: restore onto a genuinely
independent execution environment — **not** the same host — under an explicit
destructive scenario, proving database recovery, private and public file
recovery, and application usability afterwards. The prior evidence in §8
restored only into another directory on the *same* ephemeral runner, which was
correctly classified as bounded and never called independent.

### 10.1 Two separate machines, verified rather than assumed

The target job refuses to proceed unless independence is demonstrated. Two
identifiers were **disproved as discriminators by execution** during this work
and are now recorded as observations only, each annotated in the evidence with
the run that disproved it:

| Identifier | Source | Target | Role |
|---|---|---|---|
| `kernel_boot_id` | `3e203ccd-91de-4ae4-bce4-b9d4cd57fccc` | `3b90e489-ea12-4791-b1be-5a733358f34c` | **required to differ** — differs: true |
| Actions `runner_name` | `GitHub Actions 1000002465` | `GitHub Actions 1000002466` | **required to differ** — differs: true |
| `dmi_product_uuid` | `f30d2adb-8684-4f24-8d6f-e89d8332aff4` | `1a670b47-5c62-428e-a9c2-a4dfed34c761` | corroborating — differs: true, readable: true |
| `hostname` | `runnervmlun5p` | `runnervmlun5p` | observation only — run `35143620884` proved the platform reuses generated hostnames across separate VMs |
| Docker daemon id | `a4efb8b6-20f9-46f4-b827-91ac0547be3a` | `a4efb8b6-20f9-46f4-b827-91ac0547be3a` | observation only — run `35168111875` proved the runner image ships a pre-generated `/etc/docker/key.json` |

Shared state is `false` for filesystem, volumes and containers; the only
shared channel is `github-actions-artifact-only`. The target then positively
confirmed it was not looking at the source's machine:
{"source_archived_site_present_on_target": false,
"source_database_present_in_target_datastore": false,
"source_database_schema_count_on_target": "0",
"source_lab_path_present_on_target": false}. Missing identifiers fail the
verdict closed rather than silently degrading it.

### 10.2 The destructive trigger ran before anything was transferred

The source destroyed its own site with the native command `bench --site
source.localhost drop-site --no-backup --db-root-password <runner-generated,
never printed>`. `--no-backup` is explicit: nothing was archived to fall back
on.

| State | Before | After |
|---|---|---|
| Database `_0da0781ed64f67b4` present | `1` | `0` |
| Site directory exists | true | false |
| Private file present | true | false |
| Public file present | true | false |

`source_destroyed=true`, and the target independently records
`source_site_was_destroyed_before_recovery=true`. Everything the target
recovered therefore came from the transferred backup alone.

### 10.3 Database and file recovery on the independent system

The target rebuilt bench from scratch at the identical pinned revisions —
frappe `988e54f3c4c291e2…` and erpnext `4048fb70e14d1843…`, byte-identical to
the source — started real MariaDB `11.8.9` and Redis `8.6.6` containers pinned
by image digest, restored into `recovered.localhost` with a separate database,
and migrated. Recovered applications: `frappe 16.33.1 HEAD` and `erpnext
16.34.2 HEAD`.

| Recovered | Result |
|---|---|
| ToDo records | 12 of 12, name-digest match: true |
| Note records | 12 of 12, name-digest match: true |
| `independent-recovery-private.txt` | 552 bytes at `private/files/independent-recovery-private.txt`, `is_private=1`, on-disk SHA-256 match: true, File document recovered: true |
| `independent-recovery-public.txt` | 551 bytes at `public/files/independent-recovery-public.txt`, `is_private=0`, on-disk SHA-256 match: true, File document recovered: true |

The transferred payload was verified byte-for-byte before use:
`database.sql.gz` 880248 bytes sha256 `d160d3a3051ae19f…`, `private-files.tar`
10240 bytes, `public-files.tar` 10240 bytes, each
`matches_source_record=true`, plus `manifest.json` and `source-identity.json`.

### 10.4 The recovered application is usable over real HTTP

Usability was proven through an nginx front proxy in front of Gunicorn,
configured the way the pinned bench template configures production — not by
calling Python APIs in-process.

| Check | Result |
|---|---|
| Site reachable through the proxy | true, `ping` → `pong` in 1 attempt(s) |
| Authenticated session | login HTTP 200 as `Administrator`, session cookie set: true |
| Source-created record readable | `ToDo` `56uqdlb6cp` HTTP 200, content matches manifest: true, all source records listed: true (12) |
| `independent-recovery-private.txt` served | `/private/files/independent-recovery-private.txt` HTTP 200, 552 bytes, served digest matches manifest: true |
| `independent-recovery-public.txt` served | `/files/independent-recovery-public.txt` HTTP 200, 551 bytes, served digest matches manifest: true |
| Privacy boundary survived recovery | private anonymous HTTP 403 (denied: true), public anonymous HTTP 200 served by `nginx-static-public-directory` with matching content |

The privacy boundary matters here for a specific reason: the private file is
served by an nginx `internal` offload that Frappe triggers with `X-Accel-
Redirect`, so a recovery that restored the bytes but broke the routing would
look fine on disk and fail over HTTP. It was exercised from both sides —
refused anonymously, served to the session.

### 10.5 Secret hygiene, and the limitation asserted rather than hidden

No plaintext secret was staged, transferred or committed. The site config
backup that Frappe writes beside the dumps — which holds the database password
and the site encryption key — is excluded from staging by an explicit five-
file allowlist (["20260917_065751-source_localhost-site_config_backup.json"]),
the staged text is scanned for every generated secret
(`staged_payload_contains_no_secrets=true`), `bench restore --encryption-key`
exists and is **deliberately unused** (`used=false`), and the recovering
system sets its own Administrator credential with native `bench set-admin-
password` (`source_admin_password_transferred=false`), so recovery never
depends on a source secret. Only SHA-256 fingerprints appear in any artifact.

The consequence is asserted in the evidence as an **expected failure**, not
smoothed over: the field the source encrypted
(`User.Administrator.api_secret`) came back with its ciphertext intact
(`ciphertext_recovered_intact=true`) but is undecryptable on the target
(`decrypts_on_target=false`), because the keys differ — source
`433059bd7bb94a9c…`, target `249d33a6e5be6f96…`. That executed failure is the
concrete evidence that P4 (separately controlled external key custody with
rotation, and proven key retrieval) is a distinct outstanding requirement.

### 10.6 Six defects this workflow found and forced to be fixed

None of these were visible to inspection; each was produced by actually
running the recovery on hosted infrastructure, and each is recorded with its
root cause in `execution-ledger.json` under
`independent_recovery_execution.defects_found_and_fixed_by_execution`.

| Run | Failed check | Root cause and fix |
|---|---|---|
| `35141452778` | `verify-target-independence` | Independence compared only `runner_name` and `hostname` and treated a Docker daemon id as corroborating; both halves reported `runnervmlun5p`, so a genuinely independent pair failed closed on a recycled image name. |
| `35142455523` | `verify-target-independence` | `/sys/class/dmi/id/product_uuid` was unreadable for the non-root runner user, so the corroborating discriminator had no value and the verdict failed closed on a missing identifier; the reader now falls back across DMI/firmware paths and reports availability explicitly. |
| `35143620884` | `verify-target-independence` | Proved GitHub-hosted runners reuse hostnames across separate VMs — `hostname` demoted to an annotated observation. |
| `35168111875` | `verify-target-independence` | Proved the runner image ships a pre-generated `/etc/docker/key.json`, so separate VMs report one daemon id — daemon id demoted to an annotated observation; boot id and runner name are the required discriminators. |
| `35168996127` | `prove-recovered-application-usable-over-http` | Login returned HTTP 401 while every other read passed. At pinned frappe `988e54f3c4c291e2…` the `_new_site` restore path calls `install_app(force=False, set_as_patched=not source_sql)`, so `after_install` never runs and the `--admin-password` stashed in `frappe.conf` is never applied; `bench set-admin-password` added after migrate. |
| `35169957724` | `prove-recovered-application-usable-over-http` | Private file download returned HTTP 500. `frappe.utils.response.send_private_file` answers an `X-Use-X-Accel-Redirect` request with `X-Accel-Redirect: /protected/private/files/<name>` and no body, and the generated nginx config had no `/protected/` location; fixed in `1378ce4` by declaring that `internal` location ahead of the `/files/` rules, pinned by contract tests. |

### 10.7 Why the gates stay BLOCKED

No D8 release gate flips to PASS from this execution, and none is downgraded
either. `recovery` and `backup-restore` stay **BLOCKED** because `D8-BACKUP-
RECOVERY` requires more than a successful separate-system restore: it requires
key retrieval, session revocation and a measured RPO/RTO. Key retrieval is
disproved by omission in §10.5, session revocation on recovery is not
exercised, and no RPO/RTO is measured because no owner objective is selected
and none was invented. Both halves are GitHub-hosted runners from one pool, so
loss of a host, region or provider is unexercised, and the backup travelled
through a GitHub Actions artifact rather than an off-site destination with
versioning, retention and rotation. All data is synthetic.
backup-restore stay BLOCKED because D8-BACKUP-RECOVERY additionally requires
key retrieval, session revocation and a measured RPO/RTO against an owner-
selected target, none of which is proven here, and no owner objective has been
invented. Specifically: `D8-BACKUP-RECOVERY` also requires key retrieval,
session revocation and a measured RPO/RTO. Key retrieval is disproven-by-
omission above, session revocation on recovery is not exercised, and no
RPO/RTO is measured because no owner objective is selected and none was
invented. Both halves are also GitHub-hosted runners from one pool, so loss of
a host, region or provider is unexercised, and the backup travelled through a
GitHub Actions artifact rather than an off-site destination with versioning,
retention and rotation. All data is synthetic.

The probe's own scope limits are recorded verbatim in the evidence under
`not_proven_by_this_probe`, and are reproduced here without softening:

- Recovery onto a different cloud provider, region or physical datacentre
- Restoring with the source encryption key, so decryption of source-encrypted fields needs separately controlled external key custody
- Recovery time and recovery point objectives, which need an owner-selected target
- Off-site or air-gapped backup storage, retention and rotation
- TLS termination and the Tailscale boundary, exercised separately
- Any production workload, since all data here is synthetic

`release-readiness-evidence.json` `release_gate_state.recovery` was
regenerated from its generator
(`tools/foundation/release_readiness_evidence.py`) and now reads `BLOCKED /
SEPARATE-SYSTEM REHEARSAL EXECUTED; KEY RETRIEVAL, SESSION REVOCATION AND
MEASURED RPO/RTO NOT PROVEN`, replacing the stale `BLOCKED / INDEPENDENT
PRODUCTION-LIKE EVIDENCE NOT PROVEN`. It still begins with `BLOCKED`, as
`tools/foundation/d8_validate.py` requires. The archived bounded snapshot
`evidence/production-like-execution/local-bounded-release-readiness-
evidence.json` was deliberately **not** edited: it is historical provenance
pinned by hash in the ledger's integrity map.

### 10.8 Evidence references

| Artifact | SHA-256 |
|---|---|
| `evidence/production-like-execution/hosted-independent-source-35170062251.json` | `9c054dd6e41f57d5f073bbe06e2116bf1ec66b9a48fab1d30b7ec48f9f7df1b5` |
| `evidence/production-like-execution/hosted-independent-target-35170062251.json` | `ea23e9f922eb736eea21437a06db1e5ca0a4d0c223b1ea001268a8720de48cb1` |
| `evidence/production-like-execution/execution-ledger.json` § `independent_recovery_execution` | integrity map now holds 25 archived artifacts, all verified against disk |

```bash
gh run view 35170062251 --repo Frotan2/TOFEL-House-ERP
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105041393483 --jq '.output.text'
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105042127143 --jq '.output.text'
python -m unittest discover -s tests -q
python tools/foundation/d8_validate.py
```
Both archived artifacts are the check runs' own `output.text`, re-serialized
in the ledger's canonical form (`json.dumps(d, indent=2, sort_keys=True) +
trailing newline`); the hashes above are of those exact bytes. Retrieval: `gh
api repos/Frotan2/TOFEL-House-ERP/check-runs/<id> --jq '.output.text'`. `gh
run view --log` and `gh run download` do not work for these runs, which is why
the Checks API is the transport.


## 11. P4 — external key custody with rotation is EXECUTED (2026-09-17)

**Status: EXECUTED on hosted infrastructure and CLOSED as a probe. No gate
changed state.** Run `35179445639` at commit `252345e` on branch
`arena/01a0aafe-tofel-house-erp`, workflow *Foundation external key custody*
(`.github/workflows/foundation-key-custody.yml`), conclusion `success`:
custodian check run `105068259227` (10/10 checks pass), operator check run
`105068842511` (29/29) and recovery check run `105069423253` (37 checks, of
which 34 pass and **3 are required failures**). `mocks_or_simulations_used=false`
in all three roles.

This closes the fourth gap-closure priority and, with it, the specific
limitation §10 asserted rather than hid: there, the source-encrypted field was
recovered intact but **undecryptable** on the target because no key travelled
(`decrypts_on_target=false`). Here the same field decrypts, with the key obtained
from separate custody rather than from the backup (`decrypts_on_target=true`).

### 11.1 Two native keys, and the correction that mattered

Frappe has **two** distinct keys, and conflating them would have produced
evidence that looked right and meant nothing:

| Key | Protects | Installed / used by |
|---|---|---|
| `encryption_key` | `__Auth` ciphertext for native encrypted Password fields | `frappe.installer.update_site_config` — the same call `get_encryption_key()` makes when it generates one lazily |
| `backup_encryption_key` | the backup artifacts, via `gpg --passphrase <key> -c` when System Settings `encrypt_backup` is on | `bench restore --encryption-key` passes it to `gpg -d` |

`bench restore --encryption-key` **decrypts a backup**; it does **not** install a
site key. Verified against `frappe/commands/site.py` `_restore` and
`frappe/utils/backups.py` `decrypt_backup` at the pinned revision `988e54f3`. An
earlier reading of this task assumed the flag installed the site key; had that
assumption gone untested, the probe would have "restored with the source key"
while never actually installing it, and the decryption claim would have been
false.

Two further facts were read from the pinned source and then asserted at runtime
rather than trusted: `installer.py` never writes `encryption_key` (zero
mentions), and `update_password()` stores user passwords — Administrator's
included — as bcrypt hashes with `encrypted=0`, so they are unaffected by the
site key. Together these mean installing a custodian-issued key on a fresh site
strands nothing, and both roles assert that invariant explicitly: the operator
recorded `encrypted_auth_rows_before_install=0`, and the recovery system
verified that the one pre-existing ciphertext row (the operator's, restored from
the backup) decrypts under the key it was about to install.

### 11.2 Three separate machines, verified rather than assumed

The recovery job refuses to publish a pass unless all three roles are proven to
have run on separate machines, using the discriminator model §10 established —
including its two corrections, so hostname and Docker daemon id are recorded as
observations only and each is annotated with the run that disproved it:

| Identifier | Custodian | Operator | Recovery | Role |
|---|---|---|---|---|
| `kernel_boot_id` | `ada63831-…` | `98d290d1-…` | `963ba2b7-…` | **REQUIRED** — differs |
| `runner_name` | `GitHub Actions 1000002471` | `…1000002472` | `…1000002473` | **REQUIRED** — differs |
| `dmi_product_uuid` | `9eef88c7-…` | `44738f95-…` | `08428be9-…` | corroborating — differs, all 3 pairs |
| `hostname` | `runnervmlun5p` | `runnervmlun5p` | `runnervmlun5p` | OBSERVATION ONLY — matches (run `35143620884`) |
| `docker_daemon_id` | absent (no container started) | `a4efb8b6-…` | `a4efb8b6-…` | OBSERVATION ONLY — shared (run `35168111875`) |

Verdict: `SEPARATE MACHINES`, `every_pair_separate=true` across all three pairs,
`missing_required_identifiers=[]`. The hostname matching on all three jobs is a
third observation of the platform reusing generated hostnames across separate
ephemeral VMs — which is exactly why it is never used as a discriminator. The
operator also observed that the recovery machine did **not** already hold its
database before the restore (`operator_database_absent_before_restore="0"`).

### 11.3 Retrieval was proved load-bearing before it was used

A custody rehearsal in which the backup could have been restored anyway would
prove nothing, so the recovery system ran two **required failures** first, both
on copies of the dump so the staged payload could not be damaged:

| Attempt | Result | Frappe's own output |
|---|---|---|
| `bench restore` with **no** key | exit `1` | `Encrypted backup file detected. Decrypting using site config.` / `Decryption failed. Please provide a valid key and try again.` |
| `bench restore` with a **real key from the wrong epoch** | exit `1` | `Encrypted backup file detected. Decrypting using provided key.` / `Decryption failed. Please provide a valid key and try again.` |

The wrong-epoch control matters more than a random string would: it is a key
custody genuinely issued, for the same role, one epoch later, and it still
cannot open the artifact. After both attempts the staged dump was
digest-verified byte-identical (`sha256_before == sha256_after`), which is not a
formality — frappe's `decrypt_backup` renames the dump to `.gpg` and renames it
back in a `finally` block, so a failed attempt could in principle have left the
real restore with a damaged file. Share-level controls were run too: neither
channel alone reproduces the fingerprint, and shares from different epochs do
not either.

### 11.4 The backup was encrypted at rest, asserted not assumed

`bench backup --with-files` ran with System Settings `encrypt_backup=1`, and all
three artifacts were checked with the `file` command — the same test
`bench restore` applies when deciding whether to decrypt:

| Artifact | Bytes | `file` reports |
|---|---|---|
| `database.sql.gz` | 245422 (sha256 `0f337270c29dcf5e…`) | `PGP symmetric key encrypted data - AES with 256-bit key salted & iterated - SHA512` |
| `private-files.tar` | 301 | same |
| `public-files.tar` | 298 | same |

This assertion is load-bearing rather than decorative, because frappe's
`backup_encryption()` catches a gpg failure, prints *"Files are stored without
encryption"* and **continues** — so an `-enc` filename is not by itself evidence
of encryption. Every artifact carried the `-enc` suffix **and** was detected as
AES.

The payload left the machine through an explicit five-file allowlist. Frappe
also writes `20260917_092002-custody-operator_localhost-site_config_backup-enc.json`
beside the dumps; gpg does **not** cover it, so despite its `-enc` name that file
holds `db_password` and both keys in clear text, and it was excluded. Seven
generated secrets were scanned for across every staged byte: zero leaks.

### 11.5 Restoration, and the limitation §10 asserted is closed

The recovery system rebuilt bench at the identical pinned revisions, created an
empty site, and restored with the backup key retrieved from custody
(`--encryption-key`, plus both file archives). It then migrated, set its **own**
Administrator credential with native `bench set-admin-password`
(`operator_admin_password_transferred=false`), installed the retrieved site key
through `frappe.installer.update_site_config`, and verified:

| Check | Result |
|---|---|
| Ciphertext recovered intact | sha256 `3ecadda32e98f718…` — **identical to the operator's record** |
| Retrieved key installed | fingerprint `7ca9c12dcd0a0297…` — matches the custodian's epoch 1 site key |
| **Field decrypts on the recovery system** | **`decrypts_on_target=true`**, plaintext digest matches the operator's record |
| Records | 6 ToDo and 6 Note, name digests matching |
| Files | private (547 bytes, `is_private=1`) and public (546 bytes), on-disk digests matching, both File documents recovered |

`plaintext_published=false` throughout: the value is compared by digest, never
recorded.

### 11.6 Rotation of both keys, composed because Frappe has no command for it

Frappe has no key-rotation command, so rotation was composed from native
primitives and the composition is recorded as composed rather than presented as
native:

1. **The native consequence first.** After installing the epoch 2 site key, the
   epoch 1 ciphertext stopped decrypting, with frappe's own message:
   `ValidationError: Failed to decrypt key User.Administrator.api_secret …
   Encryption key is invalid! Please check site_config.json … If you have
   recently restored the site, you may need to copy the site_config.` That is the
   framework documenting that rotating a key orphans existing ciphertext.
2. **Re-encryption.** `decrypt(…, encryption_key=old)` →
   `set_encrypted_password` → `update_site_config`. The ciphertext changed
   (`3ecadda3…` → `33a39055…`), the plaintext digest did **not**, and the value
   reads back.
3. **Boundaries, three ways.** Epoch 1 key: fails. Epoch 2 key: succeeds with a
   matching plaintext digest. A key custody never issued: fails.
4. **The backup key too**, through the same native config path — and then proved
   cryptographically rather than by paying for a second full restore: a new
   backup was taken under epoch 2, detected as AES, and `gpg -d` **succeeded
   with the epoch 2 key** (exit 0, 245301 bytes) while the **epoch 1 key was
   rejected** (exit 2).

Rotation lineage was published by the custodian as fingerprints only, with
`keys_differ=true` for both roles.

### 11.7 Destruction, and no plaintext key left behind

The operator destroyed itself with native `bench drop-site --no-backup`
(database `_9b96f4509c396e9c` present then absent, site directory and both files
gone) and then went one step further than §10 did: `drop-site` moves the site
directory into `<bench>/archived/sites`, and that archived `site_config.json`
holds **both plaintext keys**, so the archive was removed and the removal
verified. The whole lab and `.foundation` tree were then scanned for all four
keys: `survivors=[]`, `clean=true`. After that job, the only key material
anywhere was one share per channel in two artifacts.

The custodian drops its in-memory bindings and its VM is destroyed at job end,
but it records honestly that **erasure is not provable** — CPython offers no
memory-erasure guarantee — rather than claiming a property it cannot support.

### 11.8 Two defects this pass found, and one recorded for the owner

1. **`-enc` naming (fixed).** Run `35178965074` died on `max() iterable argument
   is empty` *after* a successful backup: `utils/backups.py`
   `set_backup_file_name()` appends `-enc` to every artifact name when
   `encrypt_backup` is on, so globs written for unencrypted names matched
   nothing. Fixed in `252345e`; both probes now accept either form, record the
   names that appeared, and fail if the suffix is missing while encryption is
   enabled.
2. **Unquoted gpg passphrase (mitigated, and reported).** `backup_encryption()`
   interpolates the backup key into a shell command unquoted. The url-safe
   base64 alphabet includes `-`, so a key beginning with a dash is parsed by gpg
   as an option, gpg fails, and frappe prints *"Files are stored without
   encryption"* and continues — leaving a **plaintext backup under an `-enc`
   filename**. About one generated key in 64 would hit this. The generator now
   refuses a leading dash (≈0.02 bits), `command_line_safety()` records why, the
   custodian asserts every issued key is safe to pass unquoted, and the AES
   detection assertion would catch it regardless. **This is recorded for the
   owner as a framework behaviour, not silently mitigated**: an operator who lets
   Frappe generate its own backup key has roughly a 1-in-64 chance of storing
   backups unencrypted. No upstream change was proposed or made.

### 11.9 Why the gates stay BLOCKED

Custody here is a **bounded split-share model, not a trust boundary**, and the
evidence says so in those words. Repository Actions secrets are not accessible
to this session's credential (`gh secret list` → HTTP 403 *Resource not
accessible by integration*; no admin permission), so no KMS, HSM or
owner-provisioned secret store could be provisioned. That is recorded as
**ENVIRONMENT-BLOCKED** rather than worked around by weakening the model, and no
gate was downgraded to compensate. Both channels live in the same artifact
system, so any job able to download both can reconstruct the keys: retrieval is
proven, **authorization of key release is not**.

Also unproven, and the reason `recovery`, `backup-restore`, `durability` and the
overall gate keep their prior states: no rotation ceremony separated in time
from issuance (both epochs are issued in one custodian job so rotation can be
proven at all on ephemeral infrastructure); no revocation, custodian-side
destruction or custody audit log; no channel durability beyond the 14-day
artifact retention window and no versioned or off-site key store; no HTTP
usability after rotation (§10 proved HTTP usability for recovery, not for a
rotated key); no second full restore under the rotated backup key (proved at the
gpg layer instead); no session revocation on recovery; no RPO/RTO measured
against an owner objective, because none exists and none was invented; a
frappe-only rehearsal site with no product app, recorded as a scope limit since
both keys protect framework-level surfaces that behave identically either way;
and three GitHub-hosted runners from one pool, which proves three separate
ephemeral VMs and not three separate providers, regions or datacentres. Every
key, record, file and credential is synthetic.

`encryption_key_custody_reference` and `site_configuration_custody_reference`
remain **NOT SELECTED**: executing a custody *model* is not an owner selection of
a custody *destination*, and no owner numeric objective was invented.

The probe's own scope limits are recorded verbatim in each role's evidence under
`not_proven_by_this_probe` and in the ledger's `key_custody_execution.not_proven`,
and are reproduced above without softening.

`release-readiness-evidence.json` `release_gate_state.recovery` and
`.backup_restore` were regenerated from their generator
(`tools/foundation/release_readiness_evidence.py`) so the stale "KEY RETRIEVAL …
NOT PROVEN" and "PRODUCTION CUSTODY NOT PROVEN" wording no longer overstates the
gap; both still begin with `BLOCKED`, as `tools/foundation/d8_validate.py`
requires. The archived bounded snapshot
`evidence/production-like-execution/local-bounded-release-readiness-evidence.json`
was deliberately **not** edited: it is historical provenance pinned by hash in
the ledger's integrity map.

### 11.10 Evidence references

| Artifact | SHA-256 |
|---|---|
| `evidence/production-like-execution/hosted-key-custodian-35179445639.json` | `b70a5d9370013d8c5827dc787600640f048331d38d3258a37c6e2f489d74342b` |
| `evidence/production-like-execution/hosted-key-operator-35179445639.json` | `4da48bf94c8f60f8edd8866ac16124f027e63564669db87c0c0015e550153086` |
| `evidence/production-like-execution/hosted-key-recovery-35179445639.json` | `215729b6747157a63721695dfd825a6093319c5f53cdf85083998d5ee9a132b3` |
| `evidence/production-like-execution/execution-ledger.json` § `key_custody_execution` | integrity map now holds 28 archived artifacts, all verified against disk |

```bash
gh run view 35179445639 --repo Frotan2/TOFEL-House-ERP
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105068259227 --jq '.output.text'
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105068842511 --jq '.output.text'
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105069423253 --jq '.output.text'
python3 -m unittest tests.foundation.test_key_custody_contract -q   # 67 tests
python tools/foundation/d8_validate.py
```
The three archived artifacts are the check runs' own `output.text`,
re-serialized in the ledger's canonical form (`json.dumps(d, indent=2,
sort_keys=True) + trailing newline`); the hashes above are of those exact bytes.
Retrieval: `gh api repos/Frotan2/TOFEL-House-ERP/check-runs/<id> --jq
'.output.text'`, because `gh run view --log` and `gh run download` do not work
for these runs. The prior failed attempt is preserved as provenance: run
`35178965074` at `9a19e83`, whose published evidence is **not** reused as a pass
anywhere in this report.
