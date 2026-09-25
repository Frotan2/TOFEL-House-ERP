# Category B track 4 — D4 guardian lifecycle policy — 2026-09-25

Standing rule: constitution §17 (decision classification). Track: O-D4
— identity/guardian advanced policy ("merge/activation policy;
delegation + pre-admission proxy rules; consent/evidence/expiry;
records/recording rights"). Constraint applied: smallest correct
architecture.

## Native review

The pinned-schema ledger and the containment stack were audited:

- **Frappe / HRMS have no guardian concept at all.**
- **Education models the people link natively**: the pinned `Student`
  doctype (`frappe/education@93bc70757533`) exposes a `guardians`
  child table, and the containment stack (`apps/foundation_security/
  foundation_security/guards.py`) operates over the native `Guardian` /
  `Student Guardian` doctypes with the SEC-GUARDIAN-01 narrow remedy
  (explicit User Permissions containment) — a tested, CLOSED
  authorization boundary.
- What the platform carries **nowhere**: merge/activation lifecycle,
  delegation windows, pre-admission proxy posture, consent
  evidence/expiry semantics — i.e. the POLICY choices O-D4 names.
  None of these can be represented as a native row: there is no
  doctype with versioning, readiness, audit, or fail-closed semantics
  for them, and the active owner disposition remains "Defer advanced".
- **Existing TH carriers are domain-bound** and no match; the nine
  governance carriers reviewed are academic/finance/operations.

so "existing native surface" and "existing carrier extension" are both
out; a new carrier is the smallest correct architecture.

## Architecture choice

`TH Guardian Lifecycle Policy` (Operations module) + append-only
`TH Guardian Lifecycle Policy Version` child rows, the established
pattern. Terms per version, shape only, no values:

- `delegation_window_days` — Int 1–3650 (technical typo-guard ceiling):
  how long an activation/delegation request may wait before it lapses.
- `pre_admission_proxy` — Select exactly `Allowed` / `Refused`; no
  default is offered (engineering refuses to pick a posture).
- `consent_evidence` — Select exactly `Link` / `Attachment` / `Both`;
  no default.
- `consent_expiry_days` — Int 1–3650 (typo-guard ceiling).
- `records_recording_rights` — owner policy text, 1–2000 chars
  (technical input bound), never a default.

Enumerate/deny discipline: Select options enumerate the *possible
postures* (an engineering capability declaration); which posture the
owner chooses is their value, and none ships.

- Effective-dated monotone append; supersession closes the predecessor
  without rewriting it; readiness computed by the shared engine.
- Four guarded whitelisted POST commands bound to the `business_policy`
  authority (Course Owner): create / set version / set status /
  validate — receipt + hash-chained audit; controllers refuse any
  non-command write before any data check.
- Fail-closed resolver `governing_guardian_lifecycle()`: no row /
  retired / no effective version all resolve to `{}`.

## UX / configuration surface

- Native DocType form reachable by the Course Owner (create/write),
  GM + Academic Manager read-only, delete granted nowhere; form saves
  refused with business language pointing at the commands.
- Configuration desk: the Student & Guardian domain became a real
  section with computed readiness, the governing version's delegation
  window named, and the containment-still-applies statement on its
  face; System Readiness takes the policy on its own stage
  ("Student & Guardian") with next-action text. The desk stays
  read-only; the records/recording-rights text is deliberately NOT
  projected (projection discipline, test-pinned).

## Readiness and consumer wiring

1. `governing_guardian_lifecycle()` is the single read seam for any
   future lifecycle feature (merge/activation, delegation intake,
   proxy handling, consent capture). Its `{}` answer means REFUSE —
   the three fail-closed paths are unit-tested, and retirement is the
   off-switch that restores today's behavior exactly.
2. **SEC-GUARDIAN-01 stands untouched.** The policy NEVER grants any
   User, Role, row, or key any access by itself; the containment
   guards are engineering surfaces and read no owner policy.
   `test_containment_guards_never_read_the_policy_carrier` pins every
   `apps/foundation_security/*.py` source to zero carrier references,
   and the pre-existing `test_guardian_guard.py` containment suite is
   unchanged and green.
3. Runtime behavior is unchanged: no portal, no activation flow, no
   consent machinery exists — the carrier records terms only.

## Tests (focused + full)

`tests/operations/test_guardian_lifecycle_policy.py` (33 tests):
guarded commands on REAL modules against the scripted stub (create /
second refusal / effective-dating / delegation window bounded / proxy
no-default refusal / evidence no-default refusal / expiry bounded /
records-rights text required-bounded / string coercion / backdated +
same-day refusal / supersede closes not rewrites / retire off-switch /
fail-closed resolver / validate requires versions and re-checks every
stored row / readiness / four-kind routing), controller seam
(outside-command refusal first, in-context binding, duplicate-date and
closed-before-effective refusals, no row subscripting), wiring
contracts (doctype JSON invariants incl. no-delete /
Course-Owner-only-writer / no-defaults-on-Selects, hooks bindings,
GOVERNANCE_DOCTYPES, KIND_AUTHORITY binding, desk projection plus
records-text exclusion, containment-purity pin). Protected registries
extended deliberately (KIND_AUTHORITY pin; containment-hooks allowed
extras); desk contract world gained the guardian rows — the Student &
Guardian domain rendering real facts at exactly nine sections. Full
suite: **1552 passed** (was 1519), ruff clean; the containment suite
(`tests/foundation/test_guardian_guard.py`) untouched and green.

## What is NOT configured (unchanged owner side)

No guardian lifecycle policy row exists on any site; no posture chosen;
no window set; behavior remains exactly what SEC-GUARDIAN-01 enforces.
The Owner answers O-D4 through the commands when ready. This build
supplies the mechanism only.

## Register/baseline updates

- `DECISION-REGISTER` O-D4 records the mechanism (values awaited; the
  remedy stands).
- `final-closure-register.json` D4 `current_state` records the shipped
  carrier (disposition unchanged: OWNER DECISION REQUIRED; no guardian
  portal until policy exists).
