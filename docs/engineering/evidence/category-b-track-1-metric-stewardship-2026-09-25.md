# Category B track 1 — D7 metric stewardship policy — 2026-09-25

Standing rule: constitution §17 (decision classification). Track: D7
"metric stewards/derived-metric policy". Constraint applied: smallest
correct architecture — audit native and existing surfaces before
creating any carrier.

## Native review

The reporting authority inventory (constitution §1, §4 of the
architecture-decision record): Frappe/Education/HRMS carry no concept of
a *metric stewardship policy*. Native query/report doctypes are
technical delivery surfaces; dashboards and reports carry no business
accountability terms. The pinned native schema ledger
(`tests/desk/pinned_schema.json`) confirms no native doctype in scope
carries stewardship semantics. Native configuration cannot represent
D7's requirement, so option "existing native surface" is out.

## Existing-surface review

All existing TH policy carriers (`TH Assessment Policy`, `TH Correction
Policy`, `TH Billing Policy`, `TH Enrollment Exit Policy`,
`TH Roster Change Policy`, `TH Attendance Correction Policy`,
`TH Returning Student Policy`, `TH Catalog Linkage Policy`,
`TH Adjustment Posting Policy`) are domain-bound by §16 semantics;
stewardship is cross-domain governance, so extending any of them would
corrupt their domain boundary. `toefl_house.reporting` already exists
but is the *raw-fact definition register* (engineering-owned visibility
 rules of native queries) — it describes what native records mean, not
WHO is accountable for business-derived definitions. Nothing in the app
contains the words steward/derived-metric policy (grep-verified before
building).

## Architecture choice

A **new versioned policy carrier** is genuinely required and is the
smallest correct architecture. It follows the established carrier
pattern exactly (copy of the S9 attendance-correction carrier's shape):

- `TH Metric Stewardship Policy` (Operations module) + append-only
  `TH Metric Stewardship Policy Version` child rows.
- Terms per version, shape only, no values: `steward_role` (Link→Role,
  the owner links an existing native role; engineering picks none),
  `disclosure_rules` (owner policy text, 1–2000 chars — a technical
  input bound, named and tested, never content), mandatory change
  `reason`, `effective_from`, `set_by/set_on`, `superseded_on`.
- Effective-dated monotone append: `check_appends` refuses backdated or
  same-day versions; a newer version closes the predecessor's
  `superseded_on` without rewriting it.
- Readiness: computed by the shared engine (`compute_readiness`) —
  incomplete → configured → validated → effective, retired terminal.
- Authorization: all four commands bound to the `business_policy`
  authority (Course Owner), receipts + hash-chained
  `TH Configuration Audit Event`; controllers refuse any non-command
  write (native form/REST/import) before any data check.
- Fail-closed resolver `governing_stewardship()` returns `{}` on no
  row / retired / no effective version — there is no code path that
  synthesizes a steward or a disclosure rule.

Guarded whitelisted POST commands (the Owner-facing UX, same operation
mode neglected carriers shipped with):

- `toefl_house.operations.metric_stewardship.create_metric_stewardship_policy`
- `toefl_house.operations.metric_stewardship.set_metric_stewardship_policy_version`
- `toefl_house.operations.metric_stewardship.set_metric_stewardship_policy_status`
- `toefl_house.operations.metric_stewardship.validate_metric_stewardship_policy`

## UX / configuration surface

- Native DocType list/form reachable by the Course Owner (create/write),
  General Manager + Academic Manager read-only, nobody holds delete;
  form saves are refused by the controller with business language
  pointing at the guarded commands — identical to every existing
  carrier's phase.
- Configuration desk: the `reporting-metrics` domain left the desk's
  FUTURE placeholder list and now renders the computed readiness plus
  the governing steward role and dates (`_stewardship_facts`); the
  System Readiness rollup shows the same policy with its stage and next
  action. The desk remains read-only and configures nothing itself.
- Projection discipline: desk projections include identity/status/
  version/steward_role fields only; the owner-authored disclosure text
  stays off the desk (document-only), consistent with hash discipline.

## Readiness and consumer wiring

There are no derived-metric consumers today (R2 raw-fact registers
only). The consumer contract is wired and documented rather than
speculative:

1. `governing_stewardship()` is the single read seam for any future
   derived-metric mechanism; its `{}` answer means "refuse" (three
   fail-closed paths, unit-tested).
2. A future derived metric value-pins its governing stewardship terms at
   definition time (same pattern as pinned correction terms), so later
   policy changes never rewrite history.
3. Nothing in this change creates such a consumer: runtime behavior is
   unchanged; the register's "no derived metrics, no invented
   denominators" state is preserved.

## Tests (focused + full)

`tests/operations/test_metric_stewardship_policy.py` (29 tests): guarded
commands against the scripted frappe stub with REAL modules (create /
second-policy refusal / effective-dating / unknown role refusal /
empty+overlong disclosure refusal / backdated+same-day refusal /
supersede-closes-not-rewrites / retire off-switch / fail-closed reads /
validate requires versions, re-rechecks roles, recovers readiness /
all-four-kinds routing), controller seam (outside-command refusal first,
inside-command binding, ambiguous-date refusal, superseded-before-
effective refusal, no row subscripting), and wiring contracts (doctype
JSON invariants incl. no-delete and Course-Owner-only-writer, hooks
bindings point at existing functions, GOVERNANCE_DOCTYPES,
KIND_AUTHORITY binding, desk projection entries, no owner value
synthesized). Existing protected registries were extended deliberately:
`tests/configuration/test_foundation.py` KIND_AUTHORITY pin, and the
containment-hooks allowed-extras sanction. Desk contract test world
gained the stewardship rows and asserts the real section. Full suite:
**1455 passed** (was 1426), ruff clean.

## What is NOT configured (unchanged owner side)

No stewardship policy row exists on any site; no steward is named; no
disclosure rule exists; no derived metric exists anywhere. The Owner
enters those values through the commands when D7 is answered. This
build supplies the mechanism only.

## Register/baseline updates

- `final-closure-register.json` D7 `current_state` records the shipped
  mechanism (disposition unchanged — no owner value exists).
- `docs/operating-system/DECISION-REGISTER.md` O-D7 records
  "mechanism shipped, values awaiting answer" per the OD-NEW pattern.
