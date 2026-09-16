# TOEFL House ERP — Release Candidate Dossier

Date: 2026-09-16 · Branch: `arena/01a0a496-tofel-house-erp`
**Production: REJECT.** This dossier consolidates the evidence index
for Release Candidate status of the *implemented* product surface.
RC definition (from the Release Gap Map): every engineer-executable gap
closed with hosted evidence; owner decision packet delivered; upstream
and operational items precisely tracked. Owner gates (D1–D10) and
deployment-scope operations remain the only outstanding classes —
production stays REJECT until D8-class gates are independently
satisfied.

## 1. Verdict

| Question | Answer | Evidence |
|---|---|---|
| Domains closed with runtime proof? | **YES** (5/5) | §2 domain runs |
| Bypass routes contained (implemented slices)? | **YES** | A13 run + R3 |
| Read-side paths (attachment/export/print) contained? | **YES** | R3, run 35053305607 |
| Role-scoped navigation shipped? | **YES** (auditor + finance officer) | R1, run 35049742120 |
| Factual registers shipped? | **YES** (tuition + placement billing) | R2, run 35049742120 |
| Observability probes green? | **YES** (Error Log roundtrip, scheduler, ping) | R3 |
| Owner decision packet delivered? | **YES** | OWNER-DECISIONS.md (D1–D10) |
| Upstream risk tracked with evidence? | **YES** | UPSTREAM-TRACKING.md |
| Production deployable? | **NO — REJECT** | §5 outstanding classes |

## 2. Hosted evidence index (single synthetic runner, per-push re-execution)

The end-to-end suite is one connected lifecycle proof (placement →
admission → enrollment → teaching → finance → containment → release
gates). Each row is a full green run of the entire suite at that point:

| Milestone | Run | Commit | Checks | Scope added |
|---|---|---|---|---|
| Placement closed | 34932512626 | `4571e6c` | 332/332 | Placement domain |
| Admission closed | 34941341845 | `4da6f1b` | 397/397 | Admission qualification |
| Enrollment closed | 34946981784 | `756614e` | 425/425 | Enrollment lifecycle |
| Teaching closed | 34966681820 | `6ba5663` | 483/483 | Teaching operations |
| Finance closed | 34999987969 | `e73abef` | 517/517 | Finance money chain |
| A13 containment | 35008705885 | `5b5a044` | 523/523 | Bypass-route containment (RPC/REST/edit/cancel/amend seams; report SHA-256 `a66a1b5d…`) |
| R1+R2 release surfaces | 35049742120 | `69a8a95` | 530/530 | Workspaces (visibility model, no-escalation), query-report registers, probe-user restoration |
| R3 read-side + observability | 35053305607 | `46e5040` | 533/533 | Attachment parent-gate, list/export/print denial, Error Log/scheduler/ping probes |
| **D2 teaching compensation (current)** | **35066349129** | **`fa02137`** | **536/536** | Contract authority, skill-area assignment facts, native Additional Salary calculation path |

All release/D2 check IDs in the current suite (13):
`release-probe-users-restored`, `release-workspaces-configured`,
`release-workspace-role-visibility`,
`release-workspace-no-privilege-escalation`,
`release-registers-configured`, `release-registers-role-access`,
`release-registers-facts-only`, `release-attachment-paths-guarded`,
`release-read-export-print-paths-denied`, `release-observability-probes`,
`teaching-compensation-contract-authority`,
`teaching-assignment-facts`, `teaching-compensation-calculation`.

Diagnostic runs kept for the record (failures that produced decisive
evidence): 35046096047 (invigilator module-gate — D10 root cause),
35047650086 (officer visibility — role-strip root cause), 35048606232
(diag: roles `["All","Guest"]`, education SI Custom DocPerm mechanism),
35052640625 (Error Log field name `method`≠`title` — fixed same day).

## 3. Local verification index (all green at tip)

| Suite | Tests |
|---|---|
| tests/foundation | 61 |
| tests/placement | 148 |
| tests/admission | 6 |
| tests/enrollment | 10 |
| tests/teaching | 17 |
| tests/finance | 15 |

## 4. Shipped configuration surface (no parallel masters)

- 2 Desk workspaces as native module files: **TH Receipts** (module
  Placement; five auditor roles) and **TH Finance** (module Accounts;
  Finance Officer; Registers card). Staff workspaces removed per D10
  gate — zero-read roles cannot pass the pinned module-visibility gate.
- 2 role-restricted Query Reports (raw facts only, no derived
  metrics): **TH Tuition Billing Register** (ref Fees), **TH Placement
  Billing Register** (ref TH Placement Operation) + minimal
  report-only permission rows on the TH operations doctype.
- `foundation_security` 0.2.1: Guardian/Student file-permission hooks
  + deny-by-default realtime subscription guard (under runtime
  qualification, not security-approved — see version matrix).
- Integration note: education's `after_install` Custom DocPerms void
  native Sales Invoice permission rows site-wide; all shipped surfaces
  avoid that dependency (anchored on Payment Entry / Fees / TH
  operations doctype).

## 5. Outstanding classes (the only remaining ones)

1. **Owner gates D1–D10** — precise asks in OWNER-DECISIONS.md. No
   engineering workaround exists that would not invent business rules
   or breach containment. Status: D2 executed & qualified (536/536);
   D6a/D6b/D9 closed; D1/D4/D5/D7 deferred; D3 framework in execution;
   D8 charter and D10(ii) surfaces pending.
2. **Upstream items** — SEC-DEPS-01 (education frontend advisory set:
   57 entries / 21 packages at pinned v16.1.0, independently re-scanned
   and exactly reproduced 2026-09-16 via GitHub advisory API — 27 high /
   26 medium / 4 low / 0 critical; runtime exploitability untested,
   upstream toolchain migration required) and SEC-RT-TASK-01
   (upstream realtime task room; product-side exposure proven nil —
   UPSTREAM-TRACKING.md §1).
3. **Deployment-scope operations** — independent-host DR, measured
   restart downtime, HA, full-bundle upgrade/rollback, public
   TLS/proxy qualification, capacity/monitoring ownership (D8). Scoped
   hosted passes exist (ledger 2026-09-14); running them "somewhere
   else" would be evidence theater.
4. **SEC-GUARDIAN-01** — fail-closed Guardian isolation awaits D4;
   narrow explicit-User-Permissions remedy already passes hosted.
5. **Explicit deferrals (do not affect RC):** portals/self-service,
   candidate portal, performance tuning (no measured need), payment
   gateway, analytics platform (prohibited).

## 6. RC readiness statement

Every gap classified as engineer-executable in the Release Gap Map
(§1.2 config-assembly and the non-owner parts of §1.5 security) is
closed with a green hosted run. The product surface shipped is
exactly: five closed domains + A13 containment + release navigation/
registers/read-side containment/observability — all natively carried,
no rewrite, no parallel authorities, no invented policy. **Release
Candidate status of the implemented surface: QUALIFIED. Production:
REJECT** pending D8-class operational gates and owner answers.
