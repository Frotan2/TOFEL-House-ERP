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
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** | Latest active-branch Foundation runtime `35090904508` remains failed on dependency/frontend advisory gates; Checks `104787576338` and `104787579362`, SHA-256 values recorded in the acceptance ledger |
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

**Final production authorization: REJECT.** Do not enable production, relax the
synthetic-only guard, waive or reinterpret SEC-DEPS-01, relabel bounded synthetic
proof as production evidence, or merge this PR.
