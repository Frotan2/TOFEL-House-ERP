# Category B track 3 — capacity / availability objective — 2026-09-25

Standing rule: constitution §17 (decision classification). Track:
O-D8N — "concurrency profile, data scale, workload mix, availability
objective (numbers only; mechanism is engineering)". Constraint applied:
smallest correct architecture.

## Native review

Capacity planning exists natively only as *infrastructure
configuration*: worker counts, Redis/supervisor/process tuning, and the
platform's `admin/` load-guide documentation. There is no in-ERP
capacity-objective record: no doctype states "these are the owner's
concurrency/scale/mix/availability objectives" with versioning,
readiness, audit, or effective dating. The distinction matters: the
infrastructure numbers are deployment mechanics (engineering); the
OBJECTIVES a business sizes itself to are business policy (O-D8N).
Native surfaces cannot carry the policy, so "existing native surface"
is out.

## Existing-surface review

The D8 release gate itself (`tools/foundation/d8_validate.py`) is the
only TH surface mentioning capacity — and it correctly treats
D8-CAPACITY-AVAILABILITY as the one business objective still
unresolved. The gate is a release-authorization control: by the
permanent rule it must NEVER become a business setting or read one
(pin-tested: the validator contains zero `frappe` coupling and no
reference to the carrier). The closure register's
`gate-capacity-availability` item records the intended dance exactly:
"Owner supplies concurrency/availability targets; engineering measures
against them on the real host." No existing carrier may be extended
(reporting register is raw facts; alerting is receivers).

## Architecture choice

A **new versioned carrier** in the established pattern:

- `TH Capacity Objective` (Operations module) + append-only
  `TH Capacity Objective Version` child rows.
- Terms per version are exactly the four O-D8N numbers — required,
  owner-entered, validated only against technical typo-guard ceilings:
  `concurrent_users_target` (Int 1–100000), `document_scale_target`
  (Int 1–1000000000), `read_share_percent` (Int 0–100, the numeric form
  of workload mix), `availability_target_percent` (Float, 0 < v ≤ 100).
  Digit strings coerce; booleans and out-of-range values refuse. No
  default, placeholder, or suggested number ships anywhere.
- Effective-dated monotone append; supersession closes the predecessor
  without rewriting it; readiness computed by the shared engine.
- Four guarded whitelisted POST commands bound to the `business_policy`
  authority (Course Owner): create / set version / set status /
  validate — receipt + hash-chained audit; controllers refuse any
  non-command write before any data check.
- Fail-closed `governing_capacity_objective()`: no row / retired / no
  effective version all resolve to `{}` — there is no code path that
  synthesizes an objective.

## UX / configuration surface

- Native DocType form reachable by the Course Owner (create/write),
  GM + Academic Manager read-only, delete granted nowhere; form saves
  refused with business language pointing at the guarded commands.
- Configuration desk Operations section now carries the capacity
  objective alongside the alerting policy: computed readiness, and the
  owner's four numbers named only from a governing version, flanked by
  two deliberately plain statements — measurement is a real-host
  engineering proof, and the release gate never reads these settings.
  Fail-closed language when nothing governs ("no capacity objective may
  be claimed"). The desk stays read-only; all four numbers are
  projected (business intent, not secrets) and only from the engine's
  governing version.

## Readiness and consumer wiring

1. `governing_capacity_objective()` is the single read seam for the
   future real-host measurement; `{}` means "no objective may be
   claimed" (three fail-closed paths unit-tested).
2. **The release gate is untouched and provably unwireable:**
   `test_release_gate_never_reads_business_settings` pins
   `d8_validate.py` to zero Frappe coupling + zero carrier references.
   While NOT CONFIGURED, the gate's verdict is exactly what it already
   was (D8-CAPACITY-AVAILABILITY NOT_SELECTED → gate BLOCKED,
   production REJECT — pins unchanged).
3. Runtime behavior is unchanged: nothing measures, nothing scales,
   nothing claims targets.

## Tests (focused + full)

`tests/operations/test_capacity_objective.py` (32 tests): guarded
commands on REAL modules against the scripted stub (create / second
refusal / effective-dating / bounded users+documents / percent share /
positive availability / string coercion-stored-as-numbers / backdated+
same-day refusal / supersede closes not rewrites / retire off-switch /
fail-closed resolver / validate requires versions and re-checks every
stored row / readiness / four-kind routing), controller seam (outside-
command refusal first, in-context binding, duplicate-date and closed-
before-effective refusals, no row subscripting), wiring contracts
(doctype JSON invariants incl. no-delete / Course-Owner-only-writer /
no defaults, hooks bindings, GOVERNANCE_DOCTYPES, KIND_AUTHORITY
binding, desk projection of all four numbers, gate purity pin).
Protected registries extended deliberately (KIND_AUTHORITY pin;
containment-hooks allowed extras). Desk contract world gained the
capacity rows; the Operations section carries the real capacity fact
(governing numbers + both plain statements). Full suite: **1519
passed** (was 1487), ruff clean.

## What is NOT configured (unchanged owner side)

No capacity objective row exists on any site; none of the four numbers
is chosen anywhere; d8_validate stays at its pinned state (14/14
internal PASS, D8 BLOCKED, production REJECT, sec_deps
UPSTREAM-BLOCKED/REJECT). The Owner enters the numbers through the
commands when O-D8N is answered. This build supplies the mechanism
only.

## Register/baseline updates

- `decision-…`: O-D8N records the shipped mechanism (values still
  awaiting answer).
- `final-closure-register.json` gate-capacity-availability
  `current_state` records the shipped carrier (disposition unchanged:
  selection + real-host measurement still open).
