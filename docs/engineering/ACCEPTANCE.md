# Acceptance ledger

One page for the final acceptance of the TOEFL House ERP as a clean,
understandable, maintainable product. Each row: finding, severity, required
action, the evidence that proves it, and the final status. Statuses change
only when the evidence exists.

## Findings

| # | Severity | Finding | Required action | Evidence | Status |
|---|----------|---------|-----------------|----------|--------|
| 1 | P0 | Windows product not ready for real-world operation (no recovery path after a daemon restart; failure paths gave no diagnosable output) | `unless-stopped` on all services; Start/Repair failure paths show service state + last log lines + plain-language interpretation; operator runbook | `product/docker-compose.yml` (all services `restart: unless-stopped`), `product/windows/*.cmd` `:failed` sections, `tests/foundation/test_product_packaging.py::RecoveryContract`; Product-image workflow restart-persistence check | DONE |
| 2 | P0 | Multi-user (Tailscale) deployment contract undocumented; product exposure unproven | Runbook section with the exact supported setup (Tailscale Serve, tailnet only, no Funnel); real two-client validation in CI; product stays loopback-only | `docs/engineering/LAUNCH-RUNBOOK.md` "Multi-user access (central server + Tailscale)"; Product-image workflow "Multi-user tailnet contract" step (second non-admin client, tailnet-style proxy request, loopback-only binding, restart persistence) | DONE |
| 3 | P0 | Dependency/supply-chain records contradictory (candidate-era fields, tag vs source version conflicts, unpinned Node tarball, probe pinning different images than the product) | One canonical pin source (`foundation-version-matrix.json` restructured: single `selected_version` per component, `lock_status`, no candidate-era keys); upstream education tag/source mismatch recorded explicitly; Node tarball sha256 verified against nodejs.org SHASUMS256.txt (CI pre-build + Dockerfile at build); probe pulls the exact digest-pinned product images | `docs/engineering/foundation-version-matrix.json`; `product/app.Dockerfile` (ARG NODE_TARBALL_SHA256 + sha256sum -c); `product/docker-compose.yml` build arg; `.github/workflows/product-image.yml` (Node tarball integrity, base image digest); `tools/foundation/runner_probe.py`; `tests/foundation/test_product_packaging.py::DependencyPinContract` | DONE |
| 4 | P0 | Production metadata still states synthetic qualification posture | App metadata (title/description/email) of both apps cleaned; Owner cockpit and administration control centre state live, honest facts (production state from the site's own resolver; SEC-DEPS-01 described as gating internet exposure, which the selected D13/D15 deployment does not open; synthetic-only guard stated as enforced) | `apps/*/hooks.py`; `apps/toefl_house/toefl_house/desk/owner.py`; `apps/toefl_house/toefl_house/administration.py` | DONE |
| 5 | P1 | Branch isolation (multi-branch operating rule) not proven | Native User Permission (Branch) scope wired for the domain doctypes the app owns; exact-coverage assembly test extended to the documented branch-scope set; proof in CI | `docs/ROLE-DESKS.md` "Branch scope" (the canonical rule); `apps/toefl_house/toefl_house/permissions.py` (BRANCH_KINDS: hooks for Student/Student Group/Student Applicant/Program Enrollment + branch rule composed into the five guarded kinds; no Branch User Permission = unrestricted, unresolvable branch = fail closed); desk chain scope in `desk/__init__.py` (get_all seam, name-filtered); `Student Applicant-th_branch` custom field (existing fixture mechanism) + `record_applicant` branch of record (explicit or the actor's own branch); `tests/foundation/test_app_assembly.py` (exact coverage + BranchIsolationContract on the real permissions.py); `tools/native/native_checks.py` `branch-isolation-multi-branch-operating-rule` (real site, two branches, two scoped staff + unscoped controls, three surfaces) | DONE |
| 6 | P1 | Teacher compensation operational readiness (desk gap) | Finance desk gains the two compensation commands as guided actions (native commands, no new mechanism); end-to-end proof in the native lifecycle workflow | (pending) | PENDING |
| 7 | P1 | Activation/deactivation not symmetric: a failed deactivation could leave the site half-deactivated | `deactivate()` restores the previous site settings when post-verification fails (site stays deterministically ACTIVE); regression test | `product/activate.py` (restore-on-failure + log line); `tests/foundation/test_product_activation.py::test_failed_deactivation_verification_restores_previous_settings` | DONE |
| 8 | P1 | Upgrade/rollback path unproven | Product-image workflow rehearsal: backup -> rebuild -> migrate -> verify -> restore -> verify | (pending) | PENDING |
| 9 | P1 | No performance baseline | In-image baseline script + Product-image workflow step; measurements recorded, marked measured-but-not-policy (no owner capacity target exists) | (pending) | PENDING |
| 10 | P1 | No operational visibility for the owner | GM operations desk (worker/jobs/schedule/failed-job facts, existing) + runbook diagnostics (restart recovery, failure-path diagnosis, restore procedure) | `product/windows/VALIDATION.md`; `docs/engineering/LAUNCH-RUNBOOK.md` sections 9-11; GM operations desk | DONE |

## Scope decisions (owner)

- **Backup / DR:** the operational model is a same-machine, different-drive
  encrypted backup (existing mechanism). Off-site/disaster recovery is
  intentionally NOT an acceptance gate for this phase; the restore
  procedure is documented and rehearsed (finding 8) so the accepted model is
  proven to work.
- **Multi-user access:** central server + private Tailscale tailnet (owner
  decisions D13/D15). No public internet exposure is ever opened; the
  SEC-DEPS-01 gate binds to internet exposure.
- **Realtime:** the product is command-driven; realtime push over the tailnet
  is a documented current limit, not a defect of the product.
