# TOEFL House ERP — Current Baseline

Date: 2026-09-22 · Location: `docs/operating-system/CURRENT-BASELINE.md`
Status: **authoritative machine/human-readable project state**.
Reconciled against repository HEAD on the working branch — not guessed from
conversation history. Future agents MUST update this file at every meaningful
milestone (slice completion, gate change, authorization change).

---

## Head and branch

| Fact | Value |
|---|---|
| Working branch | `arena/01a0c987-tofel-house-erp` |
| HEAD commit | `2f8b681928169f2372144c36a0b9749d5ab5b4c6` |
| HEAD subject | D3: append-only effective-dated correction policy versions with request pinning |
| HEAD date | 2026-09-20 |
| Parent | `05a3e35eef97bcd9e9f8167d262844354b20ff98` — "D1: owner-configurable assessment policy facets (configuration plane)", 2026-09-20 (verified from the HEAD commit object; the parent itself records parent `12087cba…`, so history is deeper than two commits). `9eccff9` ("Initial commit") is the tip of `main` in this clone, not HEAD's parent. Clone is shallow: ancestry beyond the fetched parent is not traversable locally. |
| Working tree | CLEAN at baseline capture (before operating-system docs are added) |
| Canonical `active_branch` in governance files | `arena/01a0c987-tofel-house-erp` (fifth rotation completed 2026-09-22 in `e82936f`; previous session branch `arena/01a0ba0d-tofel-house-erp` is now historical provenance — see update log) |

## Last validated baseline

| Check | Result (this branch, HEAD `2f8b681`) |
|---|---|
| `python3 -m unittest discover -s tests -t .` | 1107 tests: **1104 pass, 3 fail** — all 3 failures are branch-boundary pins expecting `arena/01a0ba0d-tofel-house-erp` while checked out on `arena/01a0c987-tofel-house-erp` (`tests/d8/test_contract.py::test_template_is_explicitly_blocked_and_production_disabled`, `tests/foundation/test_branch_boundary.py::test_checkout_matches_the_canonical_pin`, `tests/foundation/test_current_branch_qualification.py::test_checkout_is_the_active_session_branch`). Zero functional/domain failures. |
| `ruff check .` | NOT EXECUTED in this sandbox (no `ruff` binary/module installed). No Python files are added or modified by this governance-only change, so lint status is unchanged from HEAD; `.github/workflows/owned-suite.yml` re-verifies on push. |
| Hosted qualification at this HEAD | **NOT EXECUTED ON THIS BRANCH** — no cited hosted run for `2f8b681` on `arena/01a0c987-tofel-house-erp`. Older-branch runs are historical provenance only and must not be relabeled. |
| `d8_validate.py` | VERIFIED 2026-09-22: exit 0 with D8 BLOCKED / production REJECT, `sec_deps` UPSTREAM-BLOCKED / REJECT, `synthetic_only_guard` REQUIRED, 14/14 `checks` PASS, gate states domain-qualification/authorization-isolation/ownership PASS. `checkout_branch_matches_active` is `false` because the canonical pin still names the previous session branch (the D8 test failure mechanism; posture assertions all hold). |

### Re-validation after the 2026-09-22 rotation (HEAD `e82936f`)

| Check | Result (this branch, HEAD `e82936f`) |
|---|---|
| `python3 -m unittest discover -s tests -t .` | 1107 tests: **1107 pass, 0 fail** — the 3 stale-pin failures are resolved by the rotation; the active branch now records an explicit `NOT_EXECUTED_ON_THIS_BRANCH` absence with no run pinned. Zero functional/domain failures. |
| `ruff check .` | NOT EXECUTED in this sandbox (no `ruff` binary/module installed). The rotation touched two Python files (`tools/session_branch.py`, `tests/d8/test_contract.py`) following existing style; `.github/workflows/owned-suite.yml` re-verifies on push. |
| Hosted qualification at this HEAD | **NOT_EXECUTED ON THIS BRANCH** — no cited hosted run for `e82936f` on `arena/01a0c987-tofel-house-erp`. Pushing the rotation commit will genuinely execute the named hosted workflows here; older-branch runs stay historical provenance and must not be relabeled. |
| `d8_validate.py` | VERIFIED 2026-09-22: exit 0 with D8 BLOCKED / production REJECT, `active_branch_hosted_execution` `NOT_EXECUTED_ON_THIS_BRANCH`, `checkout_branch_matches_active` `true`, `sec_deps` UPSTREAM-BLOCKED / REJECT, 14/14 `checks` PASS. Fail-closed absence enforced: any execution identity on the active block fails the contract. |

### Re-validation after the S7–S13 lifecycle arc (HEAD `cda062d`)

| Check | Result (this branch, HEAD `cda062d`) |
|---|---|
| `python3 -m unittest discover -s tests -t .` | 1333 tests: **1333 pass, 0 fail** (verified at `89b393e` pre-push; docs-only `cda062d` re-verified in tree). Zero functional/domain failures. |
| `ruff check .` | Clean via `.foundation/lint-venv` (verified at `89b393e`; docs-only changes since). |
| `node --test` (4 `tests/foundation/*.cjs` files) | 4 pass, 0 fail (verified at `89b393e`). |
| Hosted qualification at this HEAD | Placement synthetic content qualification green **596/596** (run `35834461078` @ `89b393e`, report SHA-256 independently verified `51169d6e…590b`, production REJECT). Docs-only `cda062d` re-verified by the Owned suite (run `35837939344`, success); the placement workflow's path filters exclude docs-only pushes by design. Ledger active block now EXECUTED (see update log). |
| `d8_validate.py` | VERIFIED 2026-09-23: exit 0 with D8 BLOCKED / production REJECT, `active_branch_hosted_execution` `EXECUTED` (newest Foundation runtime run `35826357964`, fail_reject), `checkout_branch_matches_active` `true`, `sec_deps` UPSTREAM-BLOCKED / REJECT, 14/14 `checks` PASS. |

## Completed domains (with qualifying evidence)

- Placement: CLOSED / QUALIFIED — `4571e6c`, run `34932512626`, 332/332.
- Admission: CLOSED / QUALIFIED — `4da6f1b`, run `34941341845`, 397/397.
- Enrollment (native basic): CLOSED / QUALIFIED — `756614e`, run `34946981784`, 425/425.
- Teaching Operations: CLOSED / QUALIFIED — `6ba5663`, run `34966681820`, 483/483.
- Finance (thin billing): CLOSED / QUALIFIED — `e73abef`, run `34999987969`, 517/517, report `663aad8c…b06`.
- A13 containment (implemented slices): demonstrated — `5b5a044`, run `35008705885`, 523/523.
- R1/R2 (workspaces + raw-fact registers): `69a8a95`, run `35049742120`, 530/530. R3: `46e5040`, run `35053305607`, 533/533.
- T1/T2 (compensation framework): `fa02137`, run `35066349129`, 536/536. T4 (D3 framework): `ed2d81d`, run `35069740378`, 539/539. T3 (command Pages): `3587700`, run `35073376790`, 542/542.
- Academic Control Plane slices 1–5 + D1 assessment-policy carrier (structure only) + D3 effective-dated versions (HEAD): local suites (`tests/configuration`, `tests/finance/test_corrections.py`, `tests/desk`) + controller-registration hosted run `35317973709` @ `c2b779b` (75 checks + 600+ scenarios, 0 errors).
- Desks (7 role surfaces): `tests/desk` + `test_role_desks.cjs` (local contract + runtime smoke).
- Lifecycle arc S1–S13 (audited bugs + owner-policy mechanisms for
  OD-NEW-01..09): latest `89b393e`, run `35834461078`, 596/596, report
  `51169d6e…590b`, production REJECT (per-slice proofs in the update log).

## Current next slice

**S1–S13 are hosted-proven; no further implementation slice is authorized
without new owner answers.** The owner-policy mechanisms for OD-NEW-01..09
are shipped and fail closed; the owner's VALUES for each are still awaited
(see `DECISION-REGISTER.md`), as are the D1/D3-remainder/D4/D5/D6a/D7/D8N
answers. The next actions available without new owner decisions are:

1. Owner value-setting in Owner Settings for the shipped OD-NEW mechanisms
   (values only — no engineering).
2. Readable dependency-audit output from a log-capable environment (SEC-DEPS-01
   evidence, no waiver).
3. Real-server restore rehearsal record + TLS/session evidence on the Tailscale
   URL (owner-operated, recorded).

Any domain slice (D1 values, D3 partials, D4, D5, D6a, D7, payroll posting)
requires its recorded owner decision first — see `DECISION-REGISTER.md`.

## Known blockers

1. Branch rotation for this session branch COMPLETE (`e82936f`; pins green;
   ledger active block EXECUTED with genuine runs — see update log).
2. SEC-DEPS-01 REJECT (upstream-blocked; standing owner REJECT; reproduced
   on this branch by run `35826357964`, not waived).
3. Synthetic-only REQUIRED (owner lift decision pending).
4. Backup-restore rehearsal unrecorded; off-site hardware unbuilt.
5. TLS/session evidence on the Tailscale URL missing.
6. Owner-value gates: OD-NEW-01..09 values; D1 values, D3 partials, D4, D5,
   D6a, D7, D8 numerics.
7. Production authorization absent (REJECT enforced by five `d8_validate.py` guards).

## Known architectural risks

- A05/A11: no safe same-term-repeat or history-affecting-cancel representation
  (native cancel deletes Course Enrollments) — destructive workarounds prohibited.
- A13: containment proven for implemented slices only; each new domain must
  re-prove its writer inventory + negative routes.
- A09: payroll posting needs the single-native-path proof + reconciliation.
- Branch drift: older-branch hosted runs must never be cited as this-branch
  evidence (pins + `NOT_EXECUTED_ON_THIS_BRANCH` guard this).
- Scope creep into closed slices (Placement/Admission/Enrollment/Teaching/
  Finance) would invalidate closure evidence — extend via new slices only.

## Working-tree expectations

- Clean tree except for the in-progress authorized slice + this baseline file.
- Never commit: site config, credentials, student/payroll data, dumps,
  backups, `.foundation/`, caches, or hosted-evidence-shaped fiction.
- Never weaken a gate, guard, or assertion to make a suite pass.

## Release posture

| Gate | State |
|---|---|
| Production authorization | **REJECT** |
| D8 overall | **BLOCKED** |
| SEC-DEPS-01 | **REJECT / UPSTREAM-BLOCKED** |
| Synthetic-only | **REQUIRED** |
| Local launch readiness | **NOT YET READY** |
| Launch-critical satisfied | domain-qualification, authorization-isolation, ownership |
| Launch-critical unsatisfied | backup-restore, dependency-security, durability, observability (audit-trail subset), topology-edge-session, production-authorization |

---

## Update log (append-only; newest last)

- 2026-09-22 — Baseline created at HEAD `2f8b681` on `arena/01a0c987-tofel-house-erp`
  (1104/1107 local; 3 branch-pin failures; no hosted run on this branch;
  production REJECT). Operating-system docs added as uncommitted governance-only change.
- 2026-09-22 (pre-commit audit) — Corrected parent row (true parent `05a3e35e`, the D1
  facets commit; `9eccff9` is `main`'s tip, not HEAD's parent; shallow clone noted),
  ruff row (not executed in sandbox; no Python touched by this change), and
  `d8_validate.py` row (verified exit 0 / BLOCKED / REJECT / 14-14 checks PASS);
  fixed `SKILL.md` §C numbering typo; added the recorded-baseline exception to the
  §J commit gate so pre-existing unrelated failures cannot block an unrelated change.
- 2026-09-22 (branch-boundary rotation) — Rotated the canonical pin
  `arena/01a0ba0d-tofel-house-erp` → `arena/01a0c987-tofel-house-erp` via the
  documented procedure (commit `e82936f`: pin, 11 workflow filters/guards, 10
  status headers, D8 records, ledger shift with `01a0ba0d` → prior provenance,
  closure register, 4 qualification tests rewritten to the honest absence).
  Suite re-validated at `e82936f`: 1107/1107 pass. Posting this entry updates
  the canonical-`active_branch` row and adds the re-validation table above;
  the `2f8b681` capture record is left intact as history.
  No code, tests, permissions, hooks, or behavior touched.
- 2026-09-22 (principal-owner domain audit) — Full domain audit recorded in
  `DOMAIN-AUDIT-AND-PLAN.md`: 7 real bugs (BUG-INV-01, BUG-ENR-02, BUG-PAY-01,
  BUG-PAY-02, BUG-ADM-01, BUG-ADMIN-01, BUG-INST-01), 8 gaps (GAP-REENROLL critical),
  7 open owner questions (OD-NEW-01..07, see DECISION-REGISTER.md), 4 remediation
  slices (S1..S4). Verdict NOT READY; production stays REJECT/BLOCKED. Audit commit
  is docs-only; implementation slices follow under the principal-owner mandate.
- 2026-09-22 (S1 implemented, hosted proof pending) — BUG-INV-01 (in-command
  exemption in `deny_premature_invoice`) + BUG-ENR-02 (before/after invoice
  name-set diff in `enroll_in_program`) fixed in `enrollment/__init__.py`;
  8 mock-based local regression tests (`tests/enrollment/test_billing_guards.py`,
  mutation-checked: 5 fail with the fix reverted); 4 hosted checks in
  `native_checks.py` (out-of-band denial control, converted-student billing,
  converted-student correction, customer-history enrollment). Local suite
  1115/1115. Hosted proof executes on push CI; no push without authorization.
- 2026-09-22 (S2 implemented, hosted proof pending) — BUG-PAY-01 (contract-row
  locks in sorted-name order + locking posting re-reads + post-lock
  re-validation; `th_ads_ref` index on Additional Salary) + BUG-PAY-02
  (per-adjustment-row one-off key and audit ref) + currency fail-closed in
  `teaching/compensation.py`; 7 mock-based local regression tests
  (`tests/teaching/test_compensation_guards.py`, all fail with the fix
  reverted); 2 static wiring tests updated to pin the per-row key (one regex
  tightened to its documented intent); hosted ref assertions updated + new
  concurrent-calc first-writer race check. Local suite 1122/1122. Found
  GAP-ADJUST-ORPHAN → OD-NEW-08 (owner question, not implemented).
- 2026-09-22 (S3 implemented, hosted proof pending) — BUG-ADM-01 (case-row lock
  + locking applicant probe in `record_applicant`) + BUG-ADMIN-01 (escaped LIKE,
  exact-key receipt scan in `set_managed_role`) + BUG-INST-01 (duplicate-only
  swallow in `_seed_skills`) + enabled-actor gates (academic + administration) +
  hosted isolation-evidence probe. Local tests: 3 intake guards, 4 new admin
  tests (+harness db stub), 1 lifecycle test, 2 install tests, all
  mutation-checked; 1 governance static test re-pinned to the exact-match
  receipt. Local suite 1132/1132. Reclassified retired-level → GAP-CATALOG-LINKAGE
  (S4); recorded GAP-ACADEMIC-IDEMPOTENCY (later engineering slice).
- 2026-09-22 (S1+S2+S3 HOSTED-PROVEN) — Placement synthetic content
  qualification green 581/581 (run 35758871057, HEAD 5863db9): all four S1
  checks, the S2 concurrent-calc race, the S3 isolation probe
  (REPEATABLE-READ, MariaDB 11.8.9), corrections policy-versioning, and desk
  qualification pass. Push cycle also repaired three pre-existing failures
  born in the parent D3 commit (correction-date TypeError, readiness
  semantics, stale owner-registry assert) plus four S1/S2 proof-harness
  issues (ruff F841, revoked finance session, short key prefix, unrestored
  reviewer2); S2 re-validation corrected to window-coverage-only per hosted
  evidence. Local suite 1135/1135, ruff clean. S4 remains owner-gated
  (OD-NEW-01..08 open). Verdict: S1–S3 proven; production still blocked
  pending S4 owner decisions.
- 2026-09-22 (S5+S6 HOSTED-PROVEN) — Placement synthetic content
  qualification green 583/583 (run 35767412041, HEAD 6ea35aa): the S5
  catalog-receipt check (replay/conflict/duplicate + receipt presence) and
  the S6 conditional journey (Conditional → accept → independent satisfy →
  convert → enroll) pass with zero nonpass. Push cycle repaired four
  S6 proof-harness issues (missing approval-Page command form per the D10
  contract, candidate9 applicant collision → candidate2, missing
  Conditional→Approved controller edge, clear-only conditions exemption)
  without weakening any gate. Local suite 1146/1146, ruff clean, Node
  suites green. Mandate evolved: OD-NEW-01..08 no longer block — business
  policy ships as versioned/effective-dated/audited Owner-Settings
  mechanisms, fail-closed when unconfigured, values never invented.
  Verdict: S1–S3 + S5 + S6 proven; production still blocked on owner S4
  value-setting + activation.
- 2026-09-22 (S7 journey-proven) — Returning-student lane (OD-NEW-01/B):
  the journey reuses the single native applicant row and the fresh decision
  is the per-journey vehicle; convert links the existing Student/Customer;
  the duplicate-Student guard runs on the first-time lane only; the
  returning journey enrolls into the NEXT term. Journey check
  `admission-s7-returning-link-reuse-enroll-bill` passed in run 35792113368
  @ `a6e91fd` (585 checks; the run went on to fail at the S8 journey, fixed
  separately). Option A (placement-free lane) deferred.
- 2026-09-22 (S8+S9 journey-proven) — Policy-gated roster changes (OD-NEW-05):
  TH Roster Change Policy with effective-dated `changes_allowed_until`,
  Teaching Scheduler executes, moves deactivate the source row; attendance
  corrections (OD-NEW-06): D3-shaped request/approve/deny with TH Attendance
  Correction Policy (approver-role + window-days terms), approval voids the
  erroneous mark and submits a replacement so history shows both. Journey
  checks passed in run 35793620978 @ `a05d6bc` (S8; 586 checks, failed later
  at S9, fixed separately) and run 35826357916 @ `bfab083` (S9; 587 checks,
  failed later at S10, fixed separately).
- 2026-09-23 (S10 HOSTED-PROVEN) — Enrollment exits (OD-NEW-07): withdrawals
  single-shot plus D3-shaped dismissal request/approve/deny under TH
  Enrollment Exit Policy; posting deletes derived Course Enrollments and
  cancels the Program Enrollment (row preserved); submitted Fees block every
  exit until finance settles; each exit snapshots every Fees on record.
  Green 587/587, run 35827688760 @ `0eb21d8`. Push cycle repaired the native
  `on_cancel` permission-checked re-query for narrow roles.
- 2026-09-23 (S11 HOSTED-PROVEN) — Billing policy (OD-NEW-03/04): TH Billing
  Policy with max-backdate/max-future-days bounds plus placement-fee timing
  (any / attempt stage / released); both billing commands judge the live
  governing terms. Green 590/590, run 35830061680 @ `e2d3fc0`.
- 2026-09-23 (S12 HOSTED-PROVEN) — Catalog linkage (OD-NEW-09): TH Catalog
  Linkage Policy with advisory/enforcing enforcement; under enforcing,
  `enroll_in_program` resolves the TH level anchored to the admission's
  native program and refuses retired levels. Green 593/593, run 35832956762
  @ `48ffa87` (fix commit: S12 applicant names marked SYNTHETIC per the
  admission rule).
- 2026-09-23 (S13 HOSTED-PROVEN) — Orphan adjustments (OD-NEW-08): TH
  Adjustment Posting Policy with post/skip orphan_posting; under post, due
  orphan adjustments pay through the covering contract exactly once, under
  skip they are reported per contract and paid nothing; unconfigured /
  retired / version-less refuses. Green 596/596, run 35834461078 @
  `89b393e` (report SHA-256 independently verified). Local gate at push:
  1333/1333, ruff clean, Node 4/4. GAP-ACADEMIC-IDEMPOTENCY verified CLOSED
  (all 23 academic commands replay through `configuration_audit.execute`;
  hosted receipt probe green) — no slice needed. Every S6–S13 journey
  re-passes in this run.
- 2026-09-23 (D8 absence closed: EXECUTED) — Genuine push-triggered execution
  on this branch closed the `NOT_EXECUTED_ON_THIS_BRANCH` absence recorded
  at the fifth rotation: newest Foundation runtime run 35826357964 @
  `bfab083` (fail_reject — the SEC-DEPS-01 condition reproduced here, not
  waived), with the full newest-run set for all ten named workflows recorded
  in the ledger's `active_branch_qualification` block and the run pinned in
  `tools/session_branch.py`. `d8_validate.py` exits 0 (14/14 checks PASS);
  D8 stays BLOCKED, production stays REJECT. V-BRANCH superseded by
  R-VBRANCH in the register. Verdict: S1–S13 proven; production still
  blocked on owner value-setting + activation + evidence gates.
- 2026-09-23 (closure commit re-proven) — Push `82709e6` re-executed the
  hosted set: placement green 596/596 with zero non-pass (run 35838656234,
  report SHA-256 independently verified), owned suite + D8 contract +
  runner green; runtime validation and frontend review reject at the same
  known steps (`Install and validate the pinned foundation`, `Compare
  frozen baseline and isolated candidate`), reproducing the standing
  SEC-DEPS-01 REJECT with fresh evidence. No outcome changed.
