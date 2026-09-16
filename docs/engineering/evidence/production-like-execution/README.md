# Production-like execution evidence (active branch)

Date: 2026-09-16 UTC · Active branch: `arena/01a0aafe-tofel-house-erp` ·
Execution commit: `d7df9ca766cd3039d68051ca83cdc8be5e834452`

Immutable evidence for the production-like readiness execution requested for this
release review. Read [`execution-ledger.json`](execution-ledger.json) first: it
classifies each requested probe and cites the run and check identifiers behind
every executed result.

## Classification rules applied here

- **EXECUTED** — an actual test ran against real services or the real native
  runtime, on a Docker-capable runner, and the result is archived below.
- **EXECUTED / FAIL** — an actual test ran and genuinely failed. Retained as a
  defect; never reclassified, averaged away or waived.
- **PASS / BOUNDED** — real local execution over synthetic filesystem fixtures.
  Explicitly *not* production evidence.
- **PASS / STRUCTURAL**, **PASS / LOCAL** — contract/validator and unit-test
  results. Not runtime evidence.
- **ENVIRONMENT-BLOCKED** — the requesting host cannot provide the capability.
  Recorded instead of simulated.
- **PROVENANCE** — evidence from the prior Arena session branch, retained with
  its original branch/commit/run identity. Never counted as an execution on the
  active branch.

## Venue

The requesting sandbox has no Docker Engine or Compose and cannot install them
([`local-runner-capability-probe.json`](local-runner-capability-probe.json)), so
live-service probes there are **ENVIRONMENT-BLOCKED**. Execution took place on an
ephemeral GitHub-hosted `ubuntu-24.04` runner (image `20260907.300.1`) providing
Docker **28.0.4** and Compose **2.38.2**, which the harness guards already
authorize. Artifact ZIPs and logs are unreachable from this environment (Azure
blob / results-receiver return `EOF`), so reports were retrieved through the
repository's own lossless Checks-API transport (`tools/foundation/publish_evidence.py`).

## Runs

| Run | Workflow | Conclusion |
|---:|---|---|
| `35122242676` | Foundation runner qualification | success |
| `35122242728` | Placement synthetic content qualification | success (542/542) |
| `35122242581` | Foundation runtime validation | **failure** (SEC-DEPS-01) |
| `35122242647` | Foundation frontend candidate review | **failure** (not adopted) |
| `35122242888` | D8 operations contract validation | success (structural) |

## Artifacts

| File | Classification | SHA-256 | Bytes | Purpose |
|---|---|---|---:|---|
| [`execution-ledger.json`](execution-ledger.json) | EXECUTION LEDGER | `ede33c91b5d87fc0cbfce98b5d4e0f245b2e209ff9efaf0c4f3bf124eaaa0e6e` | 51313 | Machine-readable probe-by-probe classification of the requested production-like execution. Authoritative index for this directory. |
| [`hosted-frontend-35122242647.json`](hosted-frontend-35122242647.json) | EXECUTED / FAIL | `17d40562f62cddc6168bef34838f128d6dbaa2257a0ab0048739c2c28c6abfb1` | 391633 | Frontend candidate comparison; production pins unchanged, production gate not passed, candidate NOT adopted. |
| [`hosted-placement-native-checks-35122242728.json`](hosted-placement-native-checks-35122242728.json) | EXECUTED | `094111f63a8f4b44e483bfd534a71b404c14b0e87c093477e0a633390ff42251` | 144451 | 542/542 native authorization, isolation, revocation, CSRF, export/print/attachment and observability checks on the real runtime. |
| [`hosted-placement-runner-35122242728.json`](hosted-placement-runner-35122242728.json) | EXECUTED | `1fc72a2420f96f9727d80346c00670b73c8d4ae43cef6e010319ef36e6e911f9` | 10653 | Placement runner result: 101/101 steps exit 0, real bench build, two isolated sites, native backup -> separate-site/separate-database restore -> integrity verification. |
| [`hosted-remaining-gates-35106268963-prior-head.json`](hosted-remaining-gates-35106268963-prior-head.json) | PROVENANCE | `87bcbb769b2b7bfe35844c29c1b2c2dd57a2a6cc981cd868ccfb8d73edab067a` | 128357 | Prior-session remaining-gate result at 60c777e. Historical provenance. |
| [`hosted-remaining-gates-35122242581.json`](hosted-remaining-gates-35122242581.json) | EXECUTED / FAIL | `a1ac7cd78d0ddb5dbd4888f459f38232850083c34562f4b1cd29fec509e6025b` | 128354 | Remaining-gate evidence: readiness 54/54, realtime 4/4, upgrade 33/33, guardian browser 6/6, restart and its explicit limitations, resolved-stack and npm advisory audits (both FAIL). |
| [`hosted-runner-35106268946-prior-head.json`](hosted-runner-35106268946-prior-head.json) | PROVENANCE | `012f41c676510b3a3d5a868b993b70a69b5af58684d00c82fd8ea82125957996` | 4284 | Prior-session runner qualification at 60c777e on arena/01a0a9f7-tofel-house-erp. Historical provenance; not an execution on the active branch. |
| [`hosted-runner-35122242676.json`](hosted-runner-35122242676.json) | EXECUTED | `4f1ad7b9bb09a2c5d5933d5ed8490eb42b2ef0e513d1235a4378165d536e5963` | 5555 | Foundation runner qualification on the active branch: real Docker MariaDB/Redis pull, start, health, transaction rollback, PING/PONG and version probes. 18/18 pass. |
| [`hosted-runtime-35106268963-prior-head.json`](hosted-runtime-35106268963-prior-head.json) | PROVENANCE | `3464276d1770341c19268cae13518175fab8bf70c47d85f6de905c9c2999b2d4` | 120443 | Prior-session runtime result at 60c777e. Historical provenance. |
| [`hosted-runtime-35122242581.json`](hosted-runtime-35122242581.json) | EXECUTED / FAIL | `e3964eb242e1bb467725e7a194ff3a7b76535d3afedbc9c5a0c8c77629eb984b` | 120451 | Foundation runtime result: four real sites, erpnext/education/payments/hrms installed, backups, restore, isolation; overall FAIL on SEC-DEPS-01 (114/116 restricted checks pass). |
| [`local-bounded-encrypted-restore-manifest.json`](local-bounded-encrypted-restore-manifest.json) | PASS / BOUNDED | `82529b6749f67e77a056231d970a59c6b49eaadfb4209680cd638205b02aabbb` | 480 | Bounded restore manifest: source/restore tree digests, database-state digest, external key not archived. No key material, credentials or customer data. |
| [`local-bounded-release-readiness-evidence.json`](local-bounded-release-readiness-evidence.json) | PASS / BOUNDED | `1b88d8341eef8668c84362e048470fd77c61198b59840b397d193d16429342cc` | 4379 | Bounded local harness: real OpenSSL AES-256-CBC/PBKDF2 encryption, HMAC-SHA256, three versions with rotation, external key boundary, alternate-directory restore, offboarding, audit, alert fail-closed, rollback. Not production evidence. |
| [`local-d8-validate.json`](local-d8-validate.json) | PASS / STRUCTURAL | `e39c9fad0ce393541af0a21ab193e8768db4f31d597a74d98e00cc283022d32e` | 1997 | D8 validator output on the rotated active branch: exit 0 while reporting BLOCKED, REJECT, production_enabled false, SEC-DEPS-01 UPSTREAM-BLOCKED / REJECT, checkout_branch_matches_active true. |
| [`local-runner-capability-probe.json`](local-runner-capability-probe.json) | ENVIRONMENT-BLOCKED | `d42a00f281fc5a95c5aceef9d4567bc2b8191ad0941c6dab7a14061e64bbadb4` | 7077 | Capability determination for the requesting sandbox: no Docker Engine/Compose, apt and download.docker.com unreachable, no /lib/modules, read-only /proc, 2 vCPU / 3.8 GiB RAM. Commands and raw outputs inline. |
| [`local-unittest-313.txt`](local-unittest-313.txt) | PASS / LOCAL | `6d95cec0565e3ae2ea04e63dec3ecfad6c4076bb61c772c87a081c465d615562` | 455 | Full local Python suite: 313 tests, OK. |

## Release state after this pass

No D8 release gate flips to PASS. `production_enabled=false`, production
authorization **REJECT**, synthetic-only guard **REQUIRED**, SEC-DEPS-01
**UPSTREAM-BLOCKED / REJECT**, D8 overall **BLOCKED**, no numeric
capacity/availability objective invented, and PR #2 is not merged.

See [`FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md`](../../FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md)
§8 and [`RELEASE-GAP-MAP.md`](../../RELEASE-GAP-MAP.md) §1.6 for the
executed-versus-blocked breakdown.
