# Daily-use readiness (2026-10-20): status, evidence, blockers

Verdict: **NO-GO for daily use.** Engineering items that could be closed in this round are closed or have evidence. The Foundation advisory gate is red, and several owner-only checks are not done. No gate was weakened.

## Refs

- `main`: `7c847da8fa1279c66fa84d85f4d0d63f5719d1aa` (unchanged).
- Branch `arena/dff19152-tofel-house-erp`, head at the time of CI: `0a6d48a` (this note is committed after it).
- PR #21 (`arena/dff19152-tofel-house-erp` -> `main`): open, mergeable, owned-suite pass. Not merged.

## CI on `0a6d48a`

| Workflow | Run | Result |
|---|---|---|
| Owned suite (push / PR) | `39355581198`, `39355576699` | success |
| Native lifecycle integration | `39355576684` | success (real Frappe, MariaDB, gunicorn) |
| Product image | `39355576589` | success (Windows stale-worktree EOL normalization included) |
| Foundation runtime | `39355576547` | **failure**: `hosted-frontend-advisory-audit` and `hosted-full-stack-dependency-audit` (exit 1). `advisory matches=148 in 40 packages` |

Foundation has failed on every head of this branch since before this round (`882ec90`, `8742b52`, `3eaf6a6`, `507e5e5`, `94107b7`, `0adf145`, `75b8490`, `95394c2`, `0a6d48a`). The failure is the advisory gate, not a lock install.

## What closed or moved this round

1. **Socket.IO residual copies** (`0adf145`): Education frontend `socket.io-parser` 4.2.7 and `ws` 8.21.3; banking frontend `ws` 8.21.3. Evidence: `docs/engineering/evidence/sec-deps-01/realtime-residual-copies-2026-10-19/README.md`.
2. **Native gate regression** (found in CI, `4d9c877`): the expected changed-file set for the ERPNext banking overlay now includes `banking/package.json`. The exact assertion is kept. Native lifecycle `39293858728` is green.
3. **A11 follow-up**: read-only Error Log count (SQL, counts only, owner-run) with tests; Microsoft form_post and PKCE compatibility confirmed for v1 and v2; Frappe `get_oauth2_authorize_url` does not send either, so Option B needs app code and a live tenant test. Owner decision `OD-2026-10-19-D` (Option A) stays in force. Evidence: `docs/engineering/evidence/microsoft-auth-review-2026-10-15/A11-followup-2026-10-19/README.md`.
4. **Showdown ReDoS (GHSA-rmmh-p597-ppvv)**: owner re-confirmed on 2026-10-20 with a compensating control, an input cap of 2000 characters before parsing (`OD-2026-10-20-A`). Implemented as a hash-bound patch (`tools/foundation/secure_markdown.py`), wired into the Foundation runtime, the product image, and the Dockerfile allowlist. Measurements and limits: `docs/engineering/evidence/sec-deps-01/markdown-cap-2026-10-19/README.md`. The register record is still open (see blockers).
5. **Tests**: full unit suite `1478` tests OK; ruff 0.16.8 clean.

## Blockers for GO (each needs evidence before a GO)

Engineering blockers:

- **Foundation advisory gate is red.** Triage replay on the CI match list: 0 untriaged, 66/66 Python closed, npm 80 closed and 2 open. The 2 open are `BROWSER_SELF_DENIAL` records: showdown `GHSA-rmmh-p597-ppvv` and `@tiptap/core` `GHSA-cp6q-959q-f8rh`. Owner decisions `OD-2026-10-18-A` and `OD-2026-10-19-C` keep those records open and the register unchanged. Owner answer `OD-2026-10-20-B` (accepted risks may count as triaged) conflicts with them for these two records. **The owner must decide.**
- **Foundation advisory artifact cannot be downloaded from this sandbox** (blob host blocked). The match list was rebuilt from the check-run annotations, and the counts match the header.
- **Branch protection is unreadable** (`gh api .../branches/main/protection` returns 403).
- **Items not evidenced this round**: stored-HTML audit on an authorized restored copy (item 9); policies, ERP workflows, HRMS and auth end-to-end (items 5, 6, 11); the business-policy values are deferred by the owner.

Owner-only blockers (cannot be done from the sandbox):

- Windows and Docker lifecycle on the owner's machine, and Issue #12 (item 12).
- Backup and restore on the owner's machine (item 13). Hosted native lifecycle includes a product restore, but that is not the owner-machine check.
- A11 proxy and access-log check (no query-string logging on Tailscale Serve or any proxy), `enable_frappe_logger` kept off, and the decision on earlier Error Log rows (`A11-error-log-count-2026-10-19.sql`, owner-run, counts only).
- Live Microsoft tenant sign-in test (`microsoft-auth-review-2026-10-15/LIVE-TENANT-PROCEDURE.md`).
- Showdown register change (proposed in the markdown-cap evidence, not applied) and the `@tiptap/core` decision.

## Housekeeping done this round

- The workspace was re-provisioned during the round. The local branch pointer was at `main` and the working tree was partial. A full backup was taken to `/home/user/work/worktree-backup-20261020-014240.tgz`. Nothing unique was in the working tree; the branch was reset to the remote head `75b8490`, and all later commits were made on top of it.
