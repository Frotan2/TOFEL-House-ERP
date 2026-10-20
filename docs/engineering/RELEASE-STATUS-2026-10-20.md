# Release status (2026-10-20)

> **Current-state note (2026-10-20):** `main` is now at `d999ca9` (PR #30 merged; commit `969e93b` content). All four CI gates are **green on the exact final commit**: Native lifecycle integration `39437595961`, Product image `39437590114`, Owned suite `39437590101`, Foundation runtime `39402382165`. Local unit suite 1493 tests OK; ruff clean. The native-lifecycle restart-persistence defect is fixed. This document below is a **historical snapshot** referencing pre-merge commits (`bae5def`, PR #21); the authoritative current report is `docs/engineering/RELEASE-ACCEPTANCE.md`. Engineering-complete and CI-qualified; **owner/deployment-verified: NO** — see the owner-only actions in the acceptance report.

## Final release

- `main`: `d999ca9` (merge of PR #30 from `arena/6fb481a1-tofel-house-erp`). Content head `969e93b`. All four CI gates green on the exact final commit.
- PR #30 merged 2026-10-20. PR #29 closed as superseded.

## CI on `main` (`bae5def`)

| Workflow | Run | Result |
|---|---|---|
| Foundation runtime | `39389276504` | success |
| Native lifecycle integration | `39389276464` | success (real Frappe, MariaDB, gunicorn: security, native checks, stored HTML, product backup and restore) |
| Product image | `39389276541` | success (incl. Windows stale-worktree EOL normalization) |
| Owned suite | `39389276508` | success |

Pre-merge CI on `3748017`: the same four workflows all succeeded (Foundation `39387044471`, Native `39387044536`, Product image `39387044532`, Owned suite `39387051654`, `39387044677`).

Local: full unit suite 1486 tests OK; ruff 0.16.8 clean.

## Security dispositions

- **Foundation advisory gate: green.** 148 matches in 40 packages. 80 npm and 66 Python findings are closed by the register. Two npm findings are reported as `OWNER_ACCEPTED_RISK`. These are **not closed and not fixed**:
  - `GHSA-rmmh-p597-ppvv` (showdown `<=2.1.0`, ReDoS, no patched version): owner decision `OD-2026-10-20-A`. Compensating control: input above 2000 characters is shown as plain text before parsing (`tools/foundation/secure_markdown.py`, hash-bound). The control bounds cost; it is not a vendor fix.
  - `GHSA-cp6q-959q-f8rh` (`@tiptap/core` 2.27.3, prototype issue in `mergeAttributes`): owner decision `OD-2026-10-19-B`. The only fixed version is 3.30.4, a major upgrade that was not taken.
  - Every other `BROWSER_SELF_DENIAL` record stays open (`OD-2026-10-18-A`, `OD-2026-10-19-C`).
- **Socket.IO** root and Education/banking residual copies: pinned at fixed versions (`socket.io` 4.8.4, `engine.io` 6.6.11, `ws` 8.21.3, `socket.io-parser` 4.2.7) and tested. Details: `docs/engineering/evidence/sec-deps-01/realtime-residual-copies-2026-10-19/README.md`.
- **Microsoft OAuth (A11):** Option A accepted (`OD-2026-10-19-D`). Option B (`form_post` + PKCE) is **not implemented**. Frappe `get_oauth2_authorize_url` sends neither parameter, so it needs app code and a live tenant test. The live sign-in is **not verified**. Read-only Error Log count: `docs/engineering/evidence/microsoft-auth-review-2026-10-15/A11-error-log-count-2026-10-19.sql` (owner-run).

## Not verified (blocks DELIVERED)

1. **Owner-configurable policies.** The eight policies have code and tests. The full suite exercises them, but there is no per-policy matrix for owner-only edit, rejection of invalid or unauthorized changes, runtime effect, and bypass through other routes.
2. **Windows lifecycle** (Issue #12, sections 4 and 1 for existing checkouts). Repository-side LF contract is met. Install, reboot, stop, start, repair, and login on Docker Desktop must run on the owner's machine.
3. **Backup to the owner's separate drive.** The restore path is exercised in the hosted native lifecycle, which restores an encrypted product backup into a disposable site. The destination drive on the owner's PC is not verified.
4. **Microsoft live tenant sign-in** (see above).

## Owner-only checklist

1. On the Windows PC with Docker Desktop: follow `product/windows/VALIDATION.md` (install, reboot, stop/start, repair, backup, restore, browser login). Record the result on Issue #12.
2. Confirm the backup destination drive and run one backup and one restore to a disposable site.
3. Run the A11 Error Log count (owner-run SQL) and the proxy/access-log check. Keep `enable_frappe_logger` off.
4. Run the Microsoft live tenant sign-in procedure: `docs/engineering/evidence/microsoft-auth-review-2026-10-15/LIVE-TENANT-PROCEDURE.md`.
5. Decide whether the `@tiptap/core` pin stays until a 3.x migration is scheduled.

## Operational notes

- Issue #12 could not be commented on from this session (token returns `Resource not accessible by integration`). Its status above is in this document.
- Workspace was re-provisioned during the session. A preserved backup is in `/home/user/work/`.
