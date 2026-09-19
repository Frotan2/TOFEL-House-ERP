# Production readiness — 2026-09-19

Owner directive §12. The acceptance question: **can TOEFL House staff
realistically run their ordinary daily operations on this system now?**

This report is the current engineering judgment for the **selected**
deployment: local server + Tailscale. It is not a claim about the internet,
a second site, or enterprise hardening.

Exact SHA at publication of this file's commit is recorded by git. Do not
edit this document to say PASS.

## Current production status (selected deployment)

| Question | Answer |
|---|---|
| Production authorization | **REJECT** |
| D8 overall gate | **BLOCKED** |
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** (Owner decision 2026-09-19: keep REJECT until findings can be read) |
| Synthetic-only activation | **REQUIRED** — owned commands refuse a non-synthetic site |
| Local launch readiness (new, derived) | **NOT YET READY** |
| Selected topology | LOCAL_SERVER_TAILSCALE |

Local launch readiness is a different question from production
authorization. It asks whether the *launch-critical* gates for this
topology are satisfied. It does **not** waive REJECT. It does **not**
authorize the public internet.

Launch-critical gates **satisfied**: domain-qualification,
authorization-isolation, ownership.

Launch-critical gates **not satisfied**: backup-restore, dependency-security,
durability, observability (audit-trail subset), topology-edge-session (TLS /
session on Tailscale), production-authorization.

Deferred as operational hardening (do not automatically block local launch,
and also do not pass): recovery (off-site DR), upgrade-rollback, realtime,
capacity-availability, change-control.

## Verified capabilities

Proven in this repository, not assumed:

- Native-first architecture: Frappe / ERPNext / Education / HRMS remain the
  authorities. No TH Teacher, TH Payroll, TH Payment, TH Class, TH Cohort.
- Student lifecycle desks (Reception, Academic, Finance, GM, Owner, Setup)
  execute under the owned suite, refuse the wrong role, project real columns,
  and guide into existing guarded commands.
- D12 teaching payables: one-off, first covering payroll period, contract
  supersession closes the predecessor; hosted-qualified on `9f45359`.
- Financial TOCTOU on corrections: fee-total race and window-closure race
  refused on hosted MariaDB (`1fada99`, `991f097`).
- D11 MIT, D13 RPO 24h / RTO 8h (targets), D14 off-site class (hardware the
  Owner controls, not built).
- Interim backup **mechanism**: different-volume refusal, openssl encrypt /
  digest sidecar, and `--restore` which verifies the digest then decrypts into
  a staging directory that is not the live data root. **Not** a rehearsed
  restore on the real server; the gate stays BLOCKED until that rehearsal
  is recorded there.
- Concurrent first-writer billing (tuition Fees and placement Sales Invoice)
  hosted-proven on `3eaed7d` (placement **PASS** 35437058766). Invoice
  correction approval re-validates the live invoice, matching the fees path,
  hosted-proven on `7e1f346` (placement **PASS** 35435767069).
- SEC-DEPS-01 evidence basis recorded as an inspection limitation — not an
  all-clear, not a demonstrated exploit.

## Remaining non-blocking risks

These must not be silently upgraded into "Blocking Issues" just because they
are unfinished enterprise work.

- Off-site backup hardware (D14) does not exist yet.
- No measured site-loss recovery, no second DR site.
- No public DNS / edge / internet-hosted topology.
- No capacity, SLA, or advanced observability numbers — and none will be
  invented.
- Guardian portal, payment gateway, advanced grading: future product scope.
- Compensation is not a Finance-desk queue; staff use native HRMS.
- Persian/Dari desk UI is not shipped.
- Hosted job logs remain unreadable from this environment; annotations are
  the only diagnostic.

## Blocking issues only

1. **Owner has not authorized production.** `production_state` is REJECT.
   Five guards in `d8_validate.py` keep it there. Editing a document cannot
   change this.
2. **SEC-DEPS-01 stays REJECT** until the dependency-audit findings can
   actually be read. Unreadable advisory detail is an evidence limitation.
3. **Synthetic-only is REQUIRED.** Real-site mutations are refused. Daily
   operations on real students cannot start until the Owner lifts this.
4. **backup-restore is BLOCKED.** The tool exists; the restore rehearsal on
   the real server has not been executed, so the gate is not closed.
5. **TLS / session on the Tailscale deployment** is launch-critical and not
   independently evidenced on the exact SHA from this environment.
6. **Durability / observability (audit trail readable in ops)** not
   independently evidenced for launch.

If any of (1)–(3) remain, the honest answer to the acceptance question is
**no**.

## Backup

| Item | State |
|---|---|
| Classification | INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY |
| Mechanism | `python3 -m tools.operations.interim_backup` — dump command in, openssl AES-256-CBC PBKDF2, sha256 sidecar; `--restore` verifies then decrypts to staging |
| Destination | A **different local volume** than the live data (`st_dev` must differ). Same-volume copies are refused. |
| Retention | 14 daily / 8 weekly / 12 monthly, reported not auto-deleted |
| Verification | sha256 of the cipher against the sidecar before any decrypt; decrypted dump checked against the sidecar plaintext digest |
| Restore test | **Not executed on the real server.** Staging restore: `python3 -m tools.operations.interim_backup --restore ...`. Procedure: `python3 -m tools.operations.interim_backup --print-restore-procedure` |
| Same-machine limitation | A second drive in the same machine does **not** protect against theft, fire, flood, total hardware loss, site loss, or ransomware that reaches both mounted volumes. D14 off-site is NOT YET BUILT. |
| RPO / RTO | Owner selected 24 hours / 8 hours as **targets**. They are not measured by this tool. |

## Exact known security status

- Gate: REJECT / UPSTREAM-BLOCKED.
- Known: the gate rejects, hosted-proven, enforced in code; no dependency
  upgrade exists in this history; foundation is pinned.
- Unknown: which advisories, which packages, severity, exploitability in
  this deployment, whether a compatible fix exists.
- Why unknown: scanner advisory detail has never been retrievable here
  (blob-log EOF; annotations carry no CVE ids).
- Classification: evidence and inspection limitation — **not** a
  demonstrated exploitable finding, **and not** an all-clear.
- No CVE identifiers are invented in the record.

## Legacy extraction

See `docs/engineering/LEGACY-EXTRACTION-2026-09-19.md`. SPA, custom ledger,
custom payroll, custom RBAC, custom event bus: **rejected**. Fail-closed
policy, single discount, named refunds, immutable placement snapshots,
different-volume backup, departed-instructor refusal: **adopted or
adapted**.

## Staff journey

See `docs/engineering/STAFF-JOURNEY-AUDIT-2026-09-19.md`. Desks plus command
pages plus native finance/payroll cover the ordinary path **on a synthetic
site**. That is not production authorization.

## Evidence-based final judgment

**No. Staff cannot realistically run ordinary daily operations on this as
an authorized local production system today.**

The product is coherent, native-first, and command-complete for the owned
slices. The thing that stops "use it tomorrow with real students" is not a
missing Reception screen. It is: production REJECT, synthetic-only
REQUIRED, unread dependency findings, and an unrehearsed restore.

Calling that "not yet enterprise-hardened" would be the conflation the
directive forbids. Calling it production-ready would be the other
forbidden error.

## Engineering backlog for the next stage (clean, explicit)

1. Owner decision: lift or keep synthetic-only for the local Tailscale site.
2. Restore rehearsal on the real server against a real MariaDB dump; record
   date, digest, elapsed time, outcome. Staging verify-and-decrypt exists;
   that is not the rehearsal. The rehearsal is what moves backup-restore.
3. Readable dependency-audit output from an environment with log access;
   triage; upgrade only with compatibility evidence; re-qualify hosted.
4. Independent evidence of TLS and session cookies on the Tailscale URL.
5. Do not start: guardian portal, payment gateway, public DNS, off-site
   hardware fiction, capacity numbers, SPA frontend.
