# Delivery readiness checkpoint — 2026-10-25

**Decision: engineering test package available; production REJECT / NO-GO.**

This is a snapshot of source `9c9ec48a6ead45dc802117eecb4f423e9b64f99d`,
not a claim that later documentation commits are included in its package.
GitHub run, job, artifact, branch and release metadata were checked directly.
The approximately 1 GB artifact was not independently downloaded, extracted,
or installed during this checkpoint; publisher authenticity and package contents
still require independent verification before the disposable Windows test.

## Exact-source hosted evidence

Every row below completed successfully on the full source SHA above.

| Gate | Run | Evidence boundary |
| --- | --- | --- |
| Owned suite | [40173457999](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173457999) | Static, unit and contract checks |
| Native lifecycle | [40173526096](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173526096) | Installed native stack; synthetic lifecycle and recovery checks |
| Foundation runtime | [40173527743](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173527743) | Hosted security/runtime qualification within recorded advisory dispositions |
| Windows customer package smoke | [40173529124](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173529124) | Hosted Windows script/package checks; not physical Docker Desktop acceptance |
| Product image | [40173457925](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173457925) | Real image, browser login, synthetic recovery, package assembly and attestation steps |

Product-image job metadata records successful **Assemble verified customer
package**, **Attest customer package provenance**, and **Publish customer
package artifact** steps. **Publish tagged customer release** was skipped.
GitHub's Releases collection was empty at inspection. Do not label an Actions
artifact as a production release or infer independent approval from CI success.

## Available test download

| Identity | Value |
| --- | --- |
| Download | [Actions artifact 12593015016](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40173457925/artifacts/12593015016) |
| Artifact name | `TOEFL-House-ERP-Customer-ci-9c9ec48a6ead` |
| Source | `9c9ec48a6ead45dc802117eecb4f423e9b64f99d` |
| Outer Actions archive size | 1,029,965,282 bytes |
| Outer Actions archive digest | `sha256:4cc664ab5dac25038e3c7358ba629937e7f32ea1d2534c920c7cf2263339c2a5` |
| Created | 2026-10-25 08:21:32 UTC |
| Scheduled expiry | 2027-01-23 07:37:16 UTC; availability must be rechecked |
| Label | **TEST PACKAGE - NO REAL DATA** |

GitHub may require sign-in to download Actions artifacts. The provider must
verify the downloaded outer archive against this artifact identity, extract
the packaged customer ZIP, independently verify that ZIP's GitHub provenance
against the expected repository/workflow/source, and verify its embedded
manifest, image and four-gate receipt. The outer Actions archive digest is
**not** the inner customer ZIP or image-tar digest. A matching hash alone does
not authenticate a publisher. Stop if provenance or any identity cannot be
verified; do not use an earlier package as if it contained D18.

The source includes the Owner-only **Backup On / Off** control, **Off by
default** on new and upgraded sites. Off preserves existing backup files.
On does not bypass D17 retention terms, the complete Owner policy, separate
local drive, key custody, recovery acceptance or production NO-GO.

## Remaining work and evidence owners

| Gate | Next concrete action | Required evidence / authority |
| --- | --- | --- |
| Independent package acceptance — [#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36) | Provider verifies the actual downloaded package and provenance, then supplies it for a separate disposable Windows test. | Verified source/image/package identities and redacted independent download results; hosted publication is insufficient. |
| Windows lifecycle and staff access — [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12) | Authorized tester follows the packaged Owner Readiness Guide on a clean disposable Windows PC with synthetic records. | Install/login, Stop/Start, Windows reboot, authorized Repair, persistent records, native role denials and real staff-device/Tailscale results; measured timings. |
| Cashier and stock — [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35) | Authorized synthetic cashier exercise on that separate Windows installation. | Native receipt, Books-only invoice, stock/GL, payment, return/restock, separate cash refund and denied-role/mixed-service outcomes. |
| Owner recovery — [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12) | Resolve the preservation hold through a separately authorized procedure before any Owner backup/recovery action. | Actual separate fixed drive, complete policy, Task Scheduler, key custody and isolated recovery evidence. D18 Off does not waive this gate. |
| Updater — [#40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40), [#71](https://github.com/Frotan2/TOFEL-House-ERP/issues/71) | Engineering independently reviews and corrects apply-time observation of actual Docker volume/image/journal state, with negative native-host tests. | Exact corrected revision and independent approval; keep `product/updates/channel.json` disabled. Existing request snapshots and green smoke do not close the recorded concern. |
| Merge governance — [#71](https://github.com/Frotan2/TOFEL-House-ERP/issues/71) | Repository administrator enables mandatory independent review and required exact-head checks. | Enforced branch protection/ruleset evidence. At inspection `main` reported `protected:false`; this connection has no admin permission. |
| Production decision | Owner reviews all applicable physical, financial, recovery, security and configuration evidence. | Explicit recorded authorization. Until then production remains **REJECT**. |

Current configuration and tests do not supersede deferred D1/D4/D5/D7 policy.
Do not enable transfers, derived ratios, public portals or update channels
because their source mechanisms exist. Green post-merge runs do not replace
independent review of the recorded security findings.

## Safe execution order

1. Preserve the existing Owner installation. Use only **Check This PC** and
   **Copy Safe Support Status** while its hold remains active.
2. Have the provider independently verify the existing test artifact. Follow
   [Customer delivery](../CUSTOMER-DELIVERY.md) and the packaged **Owner
   Readiness Guide** on a separate disposable PC. Never substitute a repository
   ZIP or ask the customer to build an image.
3. Record pass/fail, versions, measured durations and redacted observations.
   Never return passwords, private keys, raw logs, backups or real student data.
4. Correct failures in narrow reviewed PRs, rerun applicable exact-revision
   gates and rebuild the candidate if shipped inputs change. This checkpoint
   does not certify those future revisions or the documentation changes that
   record it.
5. Complete the separately authorized recovery, staff, financial and governance
   gates before requesting any production decision. Do not close #12/#35/#36
   solely on these hosted results.

The [acceptance matrix](ACCEPTANCE-MATRIX.md) defines scope and evidence states;
its historical baseline remains historical. The
[2026-10-24 integration audit](INTEGRATION-AUDIT-2026-10-24.md) remains an audit
of its stated revision, not a current inventory of merged files.
