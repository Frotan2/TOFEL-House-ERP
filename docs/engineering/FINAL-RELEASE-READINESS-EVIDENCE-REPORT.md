# TOEFL House ERP — Final Production Readiness Evidence Closure

Date: 2026-09-16 · Owner-decision baseline: `14cd64e` · Active branch:
`arena/01a0a9f7-tofel-house-erp`

## 1. Final authorization state

| Control | Result |
|---|---|
| Production authorization | **REJECT** |
| Production enabled | **false** |
| Synthetic-only guard | **REQUIRED and unchanged** |
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** |
| D8 overall | **BLOCKED** |
| Numeric capacity/availability objective | **NOT SELECTED / BLOCKED** |

This is the canonical release-readiness report for the closure pass. It separates
owner decisions from technical evidence and does not treat a bounded harness,
static inspection, documentation, or synthetic product result as production proof.
No deployment, production credentials, customer data, public provider, hostname,
DNS, off-site destination, numeric RPO/RTO, capacity target or availability target
was invented or enabled.

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

| Gate | Final state | Why it remains open |
|---|---|---|
| Recovery | **BLOCKED** | The encrypted alternate-directory harness is bounded evidence only; no independent production-like host, live DB/Redis recovery, key custody process or measured recovery objective exists |
| Backup/restore | **BLOCKED** | No selected production destination/custody/retention deployment or real production backup exists; future off-site destination remains unselected |
| Upgrade/rollback | **BLOCKED** | Local artifact rollback harness is not a full-bundle deployed upgrade/rollback rehearsal |
| Observability/incident | **BLOCKED** | Local alert model proves missing receivers fail closed, but no deployed logs/metrics/alert receiver/retention/incident evidence exists |
| Topology/edge/session | **BLOCKED** | Current Tailscale/local requirement is selected, but deployed network/session/TLS/CSRF/private-file/realtime evidence is absent; future public edge is unselected |
| Capacity/availability | **BLOCKED / NOT SELECTED** | No owner numeric objective was supplied; no claim is made |
| Durability | **BLOCKED** | File/database fixture preservation is bounded; deployed MariaDB/Redis/configuration/key/host durability and loss/restart evidence are not proven |
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
