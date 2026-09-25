# Category B track 2 — alerting / receiver policy — 2026-09-25

Standing rule: constitution §17 (decision classification). Track: the
alert receiver decision declared by the observability RECEIVER BOUNDARY
and register item V-OBS. Constraint applied: smallest correct
architecture — audit native and existing surfaces before creating any
carrier.

## Native review

`apps/toefl_house/toefl_house/observability.py` states the binding
boundary: alert CONDITIONS are generated, never delivered — "no receiver
exists in this product: no email, no SMS, no webhook, no dashboard
push. Selecting a receiver (and the retention/escalation policy around
it) is an owner decision."

Native Frappe provides delivery *mechanisms* — the Notification doctype
(now "Server Script-based notifications"), the Webhook doctype, Email
Account/SMTP, `publish_realtime` — but:

1. A native Notification/Webhook row **starts delivering the moment it
   exists**. The requirement here is the opposite: record the owner's
   receiver selection *without* activating any delivery path (V-OBS
   delivery remains a real-environment qualification).
2. Native delivery rows carry no effective-dated version history, no
   immutable audit chain, no readiness states, and no fail-closed
   resolver.
3. The pinned desk schema ledger touches no native Notification doctype
   at all; adopting it as the policy surface would sidestep the
   configuration engine's authorization + audit discipline entirely.

so "existing native surface" is out as the POLICY carrier. When (and if)
the owner selects a channel and a real host exists, engineering may
qualify a native mechanism as the delivery plumbing — that remains a
Category A execution question, out of scope here.

## Existing-surface review

All nine existing TH policy carriers are domain-bound by §16 semantics;
alerting is cross-domain operational governance and matches none. The
configuration engine itself (`toefl_house.configuration`) supplies the
generic machinery the carrier reuses unchanged: command contexts,
receipts, `resolve_governing`, `check_appends`, `snapshot_digest`,
`assert_no_ambiguous_versions`, `compute_readiness`,
`latest_after_hash`, ledger.

## Architecture choice

A **new versioned policy carrier**, smallest shape, same established
pattern as every other carrier:

- `TH Alerting Policy` (Operations module) + append-only
  `TH Alerting Policy Version` child rows.
- Terms per version, shape only, no values:
  - `channel_kind` — Select with exactly the mechanisms engineering can
    qualify natively: **Email** (Notification/Email Account), **Webhook**
    (Webhook doctype), **Dashboard** (realtime into desk surfaces).
    **SMS is deliberately absent**: no native SMS mechanism exists at
    the pinned platform, so offering it would be a fiction. Option sets
    are engineering's capability enumeration; the owner's choice among
    them is the value, and none ships.
  - `receiver_reference` — owner destination string, 1–140 chars
    (technical input bound, named + tested).
  - `retention_days` — REQUIRED integer 1–3650: retention is declared
    whenever a receiver is selected (that necessity is the owner
    decision V-OBS declares; the bounds are typo guards).
  - `escalate_after_minutes` — OPTIONAL integer 1–525600; blank means
    "no escalation" (owner choice). Digit strings are coerced.
- Effective-dated monotone append; supersession closes the predecessor
  without rewriting it; readiness computed by the shared engine.
- Four guarded whitelisted POST commands bound to the `business_policy`
  authority (Course Owner): create / set version / set status /
  validate — idempotency receipt + hash-chained audit event each;
  controllers refuse any non-command write before any data check.
- Fail-closed resolver `governing_alerting_policy()`: no row / retired /
  no effective version all resolve to `{}`. No code path synthesizes a
  receiver.

## UX / configuration surface

- Native DocType form reachable by the Course Owner (create/write),
  General Manager + Academic Manager read-only, delete granted nowhere;
  form saves are refused by the controller with business language
  pointing at the guarded commands.
- Configuration desk: the "Operations" domain moved out of the future
  placeholder list into a real section (`th-configuration` ops facts):
  computed readiness + "Governing since &lt;date&gt; on channel
  &lt;kind&gt;, retained &lt;n&gt; day(s)"; fail-closed "No versions;
  alert delivery stays refused (fail-closed)" language. The pending
  capacity objective stays visible there as an explicit fact of the
  same kind as the future-domain facts. The desk stays read-only.
- Projection discipline: the desk projects channel kind, terms and
  dates; the owner-provided `receiver_reference` destination stays on
  the document itself (test-pinned), consistent with hash discipline.

## Readiness and consumer wiring

There is no delivery consumer today and this change creates none —

1. `governing_alerting_policy()` is the single read seam for a future
   delivery mechanism; its `{}` answer means "refuse" (all three
   fail-closed paths unit-tested).
2. A future delivery mechanism value-pins its governing receiver terms
   at activation time; later policy changes never rewrite history.
3. **Negative consumer guard**: `test_observability_stays_delivery_free`
   pins `observability.py` to zero delivery primitives
   (`publish_realtime`, `enqueue`, `sendmail`, `smtplib`,
   `requests.post`) alongside its RECEIVER BOUNDARY text — the boundary
   the policy serves cannot silently become a sender.
4. Runtime behavior is unchanged: conditions are still generated,
   still never delivered.

## Tests (focused + full)

`tests/operations/test_alerting_policy.py` (32 tests): guarded commands
on REAL modules against the scripted frappe stub (create / second
refusal / effective-dating / unknown channel refusal / empty+overlong
receiver refusal / retention required-bounded-coerced / escalation
optional-bounded / backdated+same-day refusal / supersede closes not
rewrites / retire off-switch / fail-closed resolver / validate requires
versions and re-checks every stored row / readiness / four-kind
routing), controller seam (outside-command refusal first, in-context
binding, duplicate-date and closed-before-effective refusals, no row
subscripting), and wiring contracts (doctype JSON invariants incl.
no-delete / Course-Owner-only-writer / SMS-absent / no defaults,
hooks bindings, GOVERNANCE_DOCTYPES, KIND_AUTHORITY binding, desk
projection presence + receiver_reference exclusion, observability
delivery-free pin). Protected registries extended deliberately
(KIND_AUTHORITY pin in `tests/configuration/test_foundation.py`;
containment-hooks allowed extras in `tests/finance/
test_containment_hooks.py`). Desk contract world gained the alerting
rows; section count stays at nine (Operations became the real section;
capacity pending moved to an explicit fact inside it). Full suite:
**1487 passed** (was 1455), ruff clean.

## What is NOT configured (unchanged owner side)

No alerting policy row exists on any site; no receiver selected; no
channel chosen; no retention declared; nothing delivered; no delivery
runbook. Delivery against a real receiver remains the V-OBS real-
environment qualification. This build supplies the mechanism only.

## Register/baseline updates

- `DECISION-REGISTER` V-OBS records the shipped policy mechanism
  (disposition unchanged: delivery/runbook remain real-env).
- `final-closure-register.json` obs-deployed-operation `current_state`
  notes the policy mechanism.
