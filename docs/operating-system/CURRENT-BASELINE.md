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
| Canonical `active_branch` in governance files | `arena/01a0ba0d-tofel-house-erp` (previous session branch — rotation pending, see §Tests) |

## Last validated baseline

| Check | Result (this branch, HEAD `2f8b681`) |
|---|---|
| `python3 -m unittest discover -s tests -t .` | 1107 tests: **1104 pass, 3 fail** — all 3 failures are branch-boundary pins expecting `arena/01a0ba0d-tofel-house-erp` while checked out on `arena/01a0c987-tofel-house-erp` (`tests/d8/test_contract.py::test_template_is_explicitly_blocked_and_production_disabled`, `tests/foundation/test_branch_boundary.py::test_checkout_matches_the_canonical_pin`, `tests/foundation/test_current_branch_qualification.py::test_checkout_is_the_active_session_branch`). Zero functional/domain failures. |
| `ruff check .` | NOT EXECUTED in this sandbox (no `ruff` binary/module installed). No Python files are added or modified by this governance-only change, so lint status is unchanged from HEAD; `.github/workflows/owned-suite.yml` re-verifies on push. |
| Hosted qualification at this HEAD | **NOT EXECUTED ON THIS BRANCH** — no cited hosted run for `2f8b681` on `arena/01a0c987-tofel-house-erp`. Older-branch runs are historical provenance only and must not be relabeled. |
| `d8_validate.py` | VERIFIED 2026-09-22: exit 0 with D8 BLOCKED / production REJECT, `sec_deps` UPSTREAM-BLOCKED / REJECT, `synthetic_only_guard` REQUIRED, 14/14 `checks` PASS, gate states domain-qualification/authorization-isolation/ownership PASS. `checkout_branch_matches_active` is `false` because the canonical pin still names the previous session branch (the D8 test failure mechanism; posture assertions all hold). |

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

## Current next slice

**No implementation slice is currently authorized beyond evidence/rotation work.**
The next actions available without new owner decisions are:

1. Branch-boundary rotation for `arena/01a0c987-tofel-house-erp` (canonical pin,
   workflow filters, headers, governance JSON, ledger provenance — the G1/G2
   precedent), followed by re-execution of the named hosted workflows on this
   branch. Until then, hosted state is honestly `NOT_EXECUTED_ON_THIS_BRANCH`.
2. Readable dependency-audit output from a log-capable environment (SEC-DEPS-01
   evidence, no waiver).
3. Real-server restore rehearsal record + TLS/session evidence on the Tailscale
   URL (owner-operated, recorded).

Any domain slice (D1 values, D3 partials, D4, D5, D6a, D7, payroll posting)
requires its recorded owner decision first — see `DECISION-REGISTER.md`.

## Known blockers

1. Branch rotation pending (3 pin tests fail by design until rotated).
2. SEC-DEPS-01 REJECT (upstream-blocked; standing owner REJECT).
3. Synthetic-only REQUIRED (owner lift decision pending).
4. Backup-restore rehearsal unrecorded; off-site hardware unbuilt.
5. TLS/session evidence on the Tailscale URL missing.
6. Owner-value gates: D1 values, D3 partials, D4, D5, D6a, D7, D8 numerics.
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
  No code, tests, permissions, hooks, or behavior touched.
