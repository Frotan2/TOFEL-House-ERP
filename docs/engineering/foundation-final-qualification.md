# Final foundation qualification — dependency and operations review

## Recommendation: REJECT current production / Phase 2 acceptance

The architecture remains a candidate, not a rejected product direction. The pinned
ERPNext/Education bundle and security extension have **not been changed** by the
frontend experiment. No TOEFL-specific implementation is authorized.

### Frontend result: partial remediation is reproducible, but the gate still fails

Hosted comparison **34823793929**, source **4556801**, Check **103911386257**, used
Node **24.21.0**, Yarn **1.22.22**, exact Education source
`93bc7075753369457919720690f80c6d2207b5f2`, and frozen baseline/candidate locks.
The lossless report is `evidence/phase-2/hosted/frontend-34823793929.json`.

| Observation | Baseline | Isolated candidate |
|---|---:|---:|
| Installed package names audited | 255 | 257 |
| Advisory entries | **57** | **23** |
| Production asset build | Pass | Pass |
| Basic package API smoke checks | 8 pass | 8 pass |
| Detected installed dependency/peer range conflicts | 3 | 0 |
| Native ERPNext/Education integration with changed dependencies | Existing baseline evidence only | **Not qualified** |
| Production approval | **No** | **No — not adopted** |

The candidate removes **35** original advisory matches, retains **22**, and adds one
newly applicable match: **GHSA-93m4-6634-74q7**, which reports Vite 2.9.18's exposed
Windows dev-server backslash path bypass. This is an advisory match, not an independently
proved exploit or a newly exposed production endpoint. The selected serving profile
has no Windows/Vite dev server, but that is not a general developer-environment waiver.
Both workflows/audits remain failed. No advisory was filtered out to make them pass.

Application source and the six reviewed frappe-ui source hashes are unchanged between
profiles. This supports a bounded build comparison, **not** browser/backend compatibility,
unchanged bundle behavior, exploit regression, or a full-stack dependency certification.
The three baseline range conflicts are retained CLI-alias dependency observations, not
silently ignored or described as tested runtime failures. Their exact edges are in the report.

### Every advisory has an explicit decision

The review covers **58 distinct entries**: all 57 baseline findings plus the additional
candidate finding. See:

- [Advisory-by-advisory table](evidence/phase-2/frontend-advisory-compatibility-review.md)
- [Machine-readable detailed review](evidence/phase-2/frontend-advisory-compatibility-review.json)
- `frontend-package-compatibility-metadata.json`: exact public manifests, dependencies,
  peers, engines and package-integrity metadata.
- `frontend-resolution-proposal.json` and `frontend-candidate.yarn.lock`: reviewed,
  reproducible experimental inputs, **not approved production pins**.

Each entry records the affected dependency path and consumer constraints, source/build
reachability, published patch ranges, candidate match outcome, compatibility impact,
remediation options and further validation. Serving-profile exclusion, ES-only generator
output, absent browser code, dormant emitted code and reachable build tooling remain
separate categories. None alone establishes full dependency safety.

### Why a blind upgrade is rejected

1. **Rollup and esbuild require a coordinated Vite change.** Vite 2.9.17/2.9.18 caps
   Rollup at `<2.78.0`, while the recorded fixes require 2.80.0 for all retained Rollup
   findings. Its esbuild range is `^0.14.27`, not the patched 0.25.x line. Those packages
   were not forcibly overridden. Vite 2.9.18 alone cannot close the gate.
2. **Tiptap requires coherent peers.** Core 3.30.4 requires matching pm 3.30.4; link
   2.10.4 requires core/pm `^2.7.0`, not the locked 2.2.3. Updating one package is not a
   safe editor migration. Persisted HTML, schema, commands, link protocols and malicious
   attribute handling need explicit regressions.
3. **Showdown has no recorded patched release.** Maintained upstream removal or a
   parser/sanitation migration is needed. Removing it from one import or asserting
   dormancy does not fix all retained consumers or remove the installed finding.
4. **Current frappe-ui is not drop-in compatible.** Reviewed 0.1.278 requires Vue
   `>=3.5.0` versus locked 3.4.19. Its exports do not expose Education's existing
   `frappe-ui/src/utils/tailwind.config` require path. It changes parser/editor dependencies
   and requires a new audit and native integration tests. No claim is made that its
   broader version ranges automatically select safe dependencies.
5. **Transitive changes require their consumer chain.** The candidate pairs minimatch
   9.0.7 with brace-expansion 5.0.9, and socket.io-client 4.8.3 with engine.io-client
   6.6.6 / ws 8.21.0. Forcing brace-expansion 2.x or ws 8.21 beneath incompatible old
   consumers would be wrong. Socket protocol/reconnect/authorization integration still
   needs testing with this candidate, independently of the baseline guard passes.
6. **Root declarations matter.** An initial resolution-only local attempt retained
   vulnerable root Vite/PostCSS copies alongside updated nested copies (28 findings).
   That failed audit is preserved. Explicit root/development declarations and a fresh
   frozen candidate lock are now tested. Intermediate transport/offline failures are
   also retained, not counted as successful installs.

### Required remediation path

Prefer a maintained upstream Education frontend refresh that jointly qualifies Vite,
Vue plugin, Vue/compiler, frappe-ui/Tiptap and parser behavior. An illustrative
metadata-compatible Vite 6.4.3 / Vue-plugin 5.2.4 pair is **not a selected supported
production target**. Confirm vendor support policy and choose exact maintained inputs
before implementation. Avoid a permanent collection of unsupported global overrides.

For any replacement lock, require clean install with all declared/peer/engine constraints,
a fresh audit of all relevant app/tool/runtime trees, malicious-input regression cases,
asset and supported-browser tests, native login/resource/CSRF/role/file/Guardian and
realtime tests, and a controlled deployment/recovery drill. Do not reuse the baseline's
successful native tests as evidence for changed frontend dependencies.

### Production-readiness closure

Hosted native run **34823345078**, source **4fa3192880a05ec5ba67899ecfff64679821ec74**,
passes the controlled Gunicorn/RQ restart probe: the native Student record and cached
marker remain, a job queued while the sole worker was stopped completes on the replacement
worker, and native ping responds through Nginx. **47 post-restart isolation checks pass.**
The completion verifier's 0.035s is only its measurement interval, **not restart downtime**.

The unchanged native bundle also repeats **54 readiness**, **6 Guardian browser**,
**4 realtime**, and **33 upgrade** passes. Scheduler-driven Complete is observed at
**234.2s** against the native 240s tick / 360s observer. Overall workflow **FAIL solely
on the original 57-entry advisory audit**. Runtime Check **103915411886** and remaining
Check **103915414737** are preserved with their hashes, source identity and failures.

These results are scoped process-replacement proofs, not Redis/database durability,
host failure, in-flight exactly-once processing, high availability or pre-existing browser
session continuity. The [acceptance ledger](foundation-production-acceptance-ledger.json)
separates completed evidence from remaining production requirements.

Remaining production acceptance requires evidence for public TLS/proxy/origin trust,
service/data-store/host durability, independent-host backup recovery and key handling,
rollback and independent app upgrades, monitoring/alert delivery, representative capacity,
and the wider role/export/print/attachment/payroll-posting requirements. Exact deployment,
recovery and performance targets must be specified before results can meet them.

**Why not ACCEPT WITH CONDITIONS?** Known dependency findings, an unqualified replacement
frontend and critical operational gaps remain. These are acceptance blockers, not merely
minor rollout conditions. All existing failed reports remain preserved; partial passes
are reported separately. Main remains untouched.

## Reproduction

- The branch-only `foundation-frontend-review.yml` runs frozen baseline and candidate
  comparisons; npm/Yarn tarballs are integrity-verified before offline installation.
- The branch-only `foundation-runtime.yml` tests the unchanged native bundle, including
  the controlled restart probe, existing security regressions and the failed advisory gate.
- `publish_evidence.py` exposes lossless sanitized reports with SHA-256 in Checks; full
  logs remain artifacts. No site configuration, credentials or backups are committed.
