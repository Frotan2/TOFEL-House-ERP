# Acceptance ledger

One canonical ledger for final acceptance of TOEFL House ERP as a clean,
understandable, maintainable product. Each row records a finding, severity,
required action, evidence, and status. Status changes only when evidence
exists. A passing owned suite or CI qualification is not, by itself, production
readiness. **Production authorization remains REJECT.**

## Findings

| # | Severity | Finding | Required action | Evidence | Status |
|---|----------|---------|-----------------|----------|--------|
| 1 | P0 | Windows restart and failure recovery must be diagnosable | Keep restart policies and plain-language service/log diagnostics; execute the Owner's Windows install/start/stop/restart/recovery checklist | `product/docker-compose.yml`; `product/windows/*.cmd`; `tests/foundation/test_product_packaging.py::RecoveryContract`; `product/windows/VALIDATION.md` (ten screenshots) | IMPLEMENTED; real Windows Owner evidence OPEN |
| 2 | P0 | Real central-server + Tailscale multi-user path is unproven | Owner validates two real clients, access control, Tailscale Serve web and `/socket.io` routes, and a real WebSocket upgrade; never expose a public edge | `docs/engineering/LAUNCH-RUNBOOK.md` §6; Product-image workflow simulates foreign-host/proxy and loopback behavior only; it does **not** run Tailscale Serve or a tailnet/WebSocket | REAL OWNER-PC GATE OPEN |
| 3 | P0 | Dependency/supply-chain pin contradictions | Maintain one canonical pinned matrix, verify source commits and Node tarball hash, and keep image/probe inputs aligned | `docs/engineering/foundation-version-matrix.json`; `product/app.Dockerfile`; `product/docker-compose.yml`; `.github/workflows/product-image.yml`; `tools/foundation/runner_probe.py`; `tests/foundation/test_product_packaging.py::DependencyPinContract` | DONE for the reviewed pin contract; known advisories remain an upstream gate for any future public-internet exposure only (out of current local/Tailscale scope) |
| 4 | P0 | Product-facing administration must state live, separate site-mode and production-authorization facts | Keep the Owner cockpit and Administration control centre truthful; never let operational `PRODUCTION` mode imply release approval | `apps/toefl_house/toefl_house/desk/owner.py`; `administration.py`; `tests/foundation/test_production_state_contract.py`; `README.md`; `docs/PRODUCT.md`; this runbook | IMPLEMENTED; production authorization remains REJECT |
| 5 | P1 | Branch isolation and permissions must cover all owned surfaces | Keep branch scope on native permissions, guarded commands, desk projections and REST/RPC surfaces; unscoped controls and unresolved branch identities must behave as documented | `docs/ROLE-DESKS.md`; `apps/toefl_house/toefl_house/permissions.py`; `tests/foundation/test_app_assembly.py`; `tools/native/native_checks.py` branch and desk-isolation checks | DONE in owned/native qualification evidence |
| 6 | P1 | Teacher compensation operational readiness and daily-user desk gap | Keep the Finance Manager compensation queue actionable while projecting no rate/term/amount and retaining D12 separation of duties | `toefl_house/desk/finance.py`; `public/js/th_role_desks.js`; `tests/desk/test_desk_contract.py`; `tools/native/native_checks.py` role-desk qualification | DONE in owned/native qualification evidence |
| 7 | P1 | Site-mode activation/deactivation must be symmetric | Restore the previous settings on any failed post-write verification and keep regression coverage | `product/activate.py`; `tests/foundation/test_product_activation.py::test_failed_deactivation_verification_restores_previous_settings` | IMPLEMENTED; owned suite pending on this audit branch |
| 8 | P1 | Encrypted upgrade/rollback and recovery rehearsal | Qualify native encrypted database/files artifacts, encrypted recovery of the site-config sidecar, sidecar cleanup, rebuild/migrate, restore with the Frappe encryption key into clean public/private file trees, pre-/post-backup database and file markers, and HTTP health; keep a separate real Owner restore gate | `.github/workflows/product-image.yml` first-run encrypted backup/restore and “Upgrade/rollback rehearsal”; `tests/foundation/test_product_packaging.py`; `docs/engineering/LAUNCH-RUNBOOK.md` §§7–8 | OPEN until this branch's Product-image workflow succeeds; CI evidence is synthetic, not the real Owner-key ceremony |
| 9 | P1 | No measured performance baseline | Keep reproducible per-run measurements explicitly marked as measurements, not business policy or an Owner capacity target | `product/perf_baseline.py`; Product-image “Performance baseline” step; prior per-run evidence | DONE as a measured baseline; no capacity policy is inferred |
| 10 | P1 | Owner/GM operational visibility and recovery instructions | Preserve live job/service facts, diagnosable Windows repair, restore and rollback procedures | GM Operations desk; `product/windows/VALIDATION.md`; `docs/engineering/LAUNCH-RUNBOOK.md` §§5–8 | IMPLEMENTED; real Windows operation/restore evidence OPEN |
| 11 | P0 | Browser login previously rendered with missing JS bundles, so login did nothing | Keep WSGI static middleware in pinned Frappe order, idempotently synchronize built app assets, and prove real browser login through the current image | `product/wsgi.py`; `product/bootstrap.py`; `tests/foundation/test_product_packaging.py`; Product-image browser/login step | FIXED in code; requalification is part of the pending Product-image run |
| 12 | P0 | All guarded Owner-policy commands must be registered to the correct audit authority | Keep all four Owner policy command kinds mapped to `business_policy`, fail closed on missing authority, and test the complete registry | `apps/toefl_house/toefl_house/configuration/audit.py`; `tests/operations/test_owner_operations_policy.py`; static AST audit of all literal audit kinds | FIXED in code; complete owned-suite result pending |
| 13 | P0 | Bootstrap provisions Administrator, not the daily Course Owner | On the real install create a separate native System User with Course Owner role, set credentials, then configure through that account; Administrator remains setup/recovery only | `product/windows/VALIDATION.md` §4; README first-run instructions | REAL OWNER ACCOUNT/CONFIGURATION GATE OPEN |
| 14 | P0 | Real Owner policy, same-computer separate-drive backup and restore/key custody are not demonstrated | Owner supplies actual approved values (no product defaults), completes the effective-dated policy, creates/exports only a public key, verifies custody, Task Scheduler and a separate fixed local drive on the same PC, produces a verified encrypted set and completes restore with the private key | `product/windows/Backup TOEFL House ERP.ps1`; `product/windows/VALIDATION.md` §§7 and “Later”; `docs/engineering/LAUNCH-RUNBOOK.md` §§0–1, 7–8; Product-image synthetic qualification only | REAL OWNER-PC CONFIGURATION/RESTORE GATE OPEN |

## Scope decisions (Owner)

- **Backup / recovery:** the current requirement is a verified encrypted backup
  on a separate fixed local drive on the same computer, with a tested restore
  procedure. Off-site/NAS/second-device/cloud backup is explicitly deferred and
  is not a current release gate. The CI loop-backed filesystem is only a
  synthetic separate-filesystem mechanism check; it is not the Owner's drive.
- **Multi-user access:** central server + private Tailscale tailnet (Owner
  decisions D13/D15). No public internet edge, provider, hostname, DNS, or
  public TLS is a current launch requirement. CI's HTTP proxy/foreign-host
  contract does not qualify a real tailnet, Tailscale Serve, or WebSocket.
- **Dependency advisories:** SEC-DEPS-01 remains an upstream-blocked gate only
  before any future public-internet exposure. That exposure is out of the
  selected local-server + Tailscale deployment scope.
- **Native authority:** ERPNext/Frappe/Education/HRMS remain authoritative; no
  parallel student, course, class, enrollment, accounting, or payroll ledger
  is introduced by this lifecycle work.
- **Site mode is not release authorization:** the guarded operational mode may
  report `PRODUCTION` only after its own checks. Product status, Owner desks,
  and this ledger must continue to report production authorization **REJECT**
  until all applicable engineering, Owner, and non-engineering gates have
  genuine evidence.
