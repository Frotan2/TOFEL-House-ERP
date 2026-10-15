# Owner acceptance package

Status as of 2026-10-15: **NO-GO**. Each item below is an owner-run or owner-decision step. None of them has been executed by the engineering agent. No secret, token, key, password, tenant GUID or real site data belongs in this document or in any issue, commit or log. Record only the evidence listed in each row.

Reference decisions: `docs/owner-decisions.json` (D12 to D17 recorded; D14 off-site backup is DEFERRED / FUTURE; business-policy values remain unresolved).

## A. Required owner actions

| # | Item | Owner action | Evidence to return (no secrets) | Blocks |
|---|---|---|---|---|
| A1 | Real Windows and Docker Desktop validation | Run the checklist in `product/windows/VALIDATION.md` on the owner's PC: fresh install, start/stop, reboot persistence, repair/update, Docker unavailable and interrupted-install recovery, launcher behavior. | Pass/fail per step, Windows and Docker versions, `docker compose config` result status, log excerpts with secrets redacted | Issue #12; NO-GO |
| A2 | Separate backup drive (same PC) | Connect a dedicated drive. Confirm the ERP validates it as a fixed secondary drive and refuses the system drive and removable media. | Validation result, drive type and letter (not serials) | NO-GO |
| A3 | Keep count and nightly schedule | Set the keep count and nightly time in ERP Configuration (Backup and Recovery). D17 allows deletion of valid older sets beyond the keep count only. | Configured keep count and time, one manual backup, the resulting set list | NO-GO |
| A4 | Recovery key and private-key custody | Generate the OpenPGP recovery keypair on the owner machine. Publish only the public key to the ERP. Store the private key offline with the agreed custodians. Test one restore into a disposable folder. | Public-key fingerprint, custodian count and quorum policy, restore-rehearsal result (no private key material) | NO-GO |
| A5 | Tailscale multi-user acceptance | Add two synthetic test accounts on the tailnet. Verify each reaches only its permitted pages and no public exposure exists. | Account roles tested, reachability results per account | NO-GO |
| A6 | Office 365 tenant pin | Set `office_365_tenant_id` in site configuration to the Entra tenant GUID (non-secret). Then run the owner procedure in `docs/engineering/evidence/microsoft-auth-review-2026-10-15/README.md`. | Denial log line counts and HTTP status codes only | NO-GO if Office 365 login is offered |
| A7 | Business-policy values | Supply values for deferred academic progression, guardian, tax, refund-term, calendar/transfer and metrics-steward policy, or confirm they stay unconfigured and fail closed. | Written decision per item (decision record, not inferred) | NO-GO for affected features |
| A8 | Issue #12 closure | After A1 to A5 evidence exists, comment on #12 with the evidence list and close it. (Engineering cannot comment on issues with its current token, HTTP 403.) | Link to this package and the evidence | Closure |

## B. Repository decisions for the owner

| # | Decision | Current state |
|---|---|---|
| B1 | Delete `arena/68836d1b-tofel-house-erp` (remote). | Zero unique commits; ancestor of `main`; PR #18 head. Not in the owner's earlier six-branch authorization, so it is kept until explicitly approved. |
| B2 | Keep or delete `arena/abdece6c-tofel-house-erp`. | Nine commits not on `main` (PR13 security evidence and "hold" docs/tests). Keep unless the owner confirms each commit is superseded. Do not delete without that confirmation. |
| B3 | Session branch `arena/f99831e4-tofel-house-erp`. | Holds the HRMS evidence commit `4697e7d` (also cherry-picked to the session branch). Keep until the session branch is merged. |

## C. Engineering evidence status (for reference)

| Area | Status | Source |
|---|---|---|
| Full test suite | 1307 OK, 0 skipped, local, with PyJWT[crypto] | `python3 -m unittest discover -s tests -t .` |
| Lint | `ruff check .` clean (ruff 0.16.8, as CI) | owned-suite workflow |
| HRMS editor, built component | Lab PASS on patched tree; FAIL on controls. CI-pending. | `docs/engineering/evidence/hrms-editor-2026-10-15/README.md` |
| GHSA-c8x8 (HRMS prosemirror-view) | MITIGATED_LAB_VERIFIED_CI_PENDING; release gate OPEN | `advisory-delta-2026-10-09/delta-dispositions.json` |
| Microsoft auth review | Fixed tenant pin, denial audit, disabled-user revocation; live tenant test unverified | `docs/engineering/evidence/microsoft-auth-review-2026-10-15/README.md` |
| Business-rule enforcement review (workstream 5) | Not completed in this round | — |
| Windows lifecycle | Owner-run only (A1) | `product/windows/VALIDATION.md` |
| Backup and restore rehearsal | Synthetic CI tests only; real-machine verification is A2 to A4 | — |
