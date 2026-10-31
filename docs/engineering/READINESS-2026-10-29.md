# Production readiness reconciliation — 29 October 2026

**Decision: Production REJECT / NO-GO. PR #120 remains Draft and unmerged.**

## Source identity and chronology

The existing Windows checkout started on `fix/updater-live-host-observation-20261025`
at `b0e53d30ca94e0e14e231cfc1c03ba065efc5fa6`, with an uncommitted deepmerge
candidate. Its earlier Foundation/Product failures preceded the remote work
branch's scoped 28 October NOT_REACHABLE analysis.

Remote baseline `23dde16f94df49403f9c941b08d0a406cf3fe1a9` subsequently passed:
Owned [40806618803](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40806618803),
Native [40806613088](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40806613088),
Foundation [40806654692](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40806654692),
Product [40806613070](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40806613070),
Windows [40806657078](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40806657078).
Those successes do not qualify this newer overlay.

All local edits were copied outside the checkout and preserved in local commit
`f84b99a8ae7c8b248fb2cc4767dc7a5f513066d9` before switching to work. The candidate
was applied on top of the remote baseline without rewriting its history. The
complete raw acceptance folder remains local and excluded from commits. No
reset, clean, rebase, branch deletion, main merge, tag or production release
was performed. Main was observed at `a5f64a51f9f6b8b9949041d2cd9a0788cf528e4a`.

## Reviewed changes

The supplementary deepmerge 4.3.1 overlay pins publisher metadata and three
JavaScript entry points, patches own data-property writes, refuses drift,
reinstallation and linked dependency directories, and checks expected consumer
coverage. The exact existing Education security lock can prove removal of its
deepmerge dependency; absence in an unknown graph fails. Product/Foundation
apply before compilation and verify afterwards. Native applies and verifies
installed sources without claiming an asset build. Product compares the
pre-export distribution/asset receipt against the actual shipped runtime image.

[Detailed source review and evidence](evidence/sec-deps-01/advisory-delta-2026-10-29/README.md).
The historical 28 October advisory disposition and fail-closed unknown-advisory
handling remain unchanged. The filelock 4.2.4 pins and source overlay are retained.

## Validation and final receipts

The integrated-tree focused security/triage, overlay, packaging, prebuilt-assets
and filelock-pin run completed **134 tests, OK, one Windows symlink-privilege
skip**. All five canonical Node suites and Ruff 0.16.8 passed. Counts from the
older 141/66 runs are historical and are not added to this result.

Local validation is executed on the integrated work tree, with UTF-8 mode for
Windows and the repository's hash-pinned sanitizer dependencies in a disposable
folder. A prior default-Windows-encoding attempt failed reading UTF-8 policy
text; this is an environment correction, not a policy change. Linux-only
cryptography wheel hashes were not weakened to install different Windows bytes.
Windows platform and unavailable optional-dependency skips are reported in the
full log; hosted Owned installs and executes its pinned cryptographic tests.
The Windows whole-tree attempt also encounters Linux-only product restore
imports (`fcntl`). These cases require the Linux hosted Owned environment;
no mock or weakened recovery test was introduced to manufacture a local pass.

The exact pushed commit, full local totals/skips, all five final hosted run URLs,
artifact digest, repository status and remote-ref comparison are recorded in
[PR #120](https://github.com/Frotan2/TOFEL-House-ERP/pull/120) after execution.
This source document deliberately cannot certify its future CI. Missing,
cancelled or failed exact-head gates keep the hold.

## Confirmed unresolved release gates

| Gate | Evidence and limit |
| --- | --- |
| Tuition Fees payout | Issue #115 remains open. GM approval exists, but no verified native credit/GL/Fees payout mechanism. Preserve the fail-closed refusal; no ad-hoc Student Pay or Journal Entry bypass. |
| Final installed image | Historical d32dfb4 Owner browser checks are preserved; this newer candidate has not replaced the live image. Safe update/rollback, final-image recovery and independent package acceptance remain required. |
| Physical recovery | Historical Windows scheduler/isolated Owner-key tests are preserved. Distinct second-person authorization/signatures, final-image recovery and physical separate key custody are not established for this candidate. |
| Staff and finance | Preserve prior role, receipt, stock and payroll-liability evidence. Remaining real staff-device scope and payout/reconciliation acceptance cannot be inferred from hosted fixtures. |
| Signed updater/publisher | Update channel remains disabled. Preserving Repair and hosted attestation do not qualify a signed customer update channel or independent publisher approval. |
| Governance | Live API inspection returned main protected=false and no repository rulesets. Independent mandatory review and reconciliation of divergent main remain open. |
| Owner release decision | Explicit Owner acceptance after all applicable gates is required; engineering CI cannot authorize Production. |

The local Docker engine was unavailable during this continuation. It was not
started because that could affect existing Owner services. Physical acceptance
was not repeated or invented. No live site, keys, policies, backups, customer
records, services or scheduled tasks were changed.
