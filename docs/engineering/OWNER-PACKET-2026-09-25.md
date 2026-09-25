# Owner packet — 2026-09-25 — four policy mechanisms delivered; four genuine boundaries remain

Audience: the Owner. This packet summarizes what engineering built
today under the permanent decision-classification rule (constitution
§17), what only you can answer through the delivered mechanisms, and
which decisions are genuinely external to engineering. Nothing in this
packet enables anything at runtime: production stays REJECT, every
resolver fails closed, and every listed value below is explicitly
NOT CONFIGURED — no steward named, no receiver selected, no objective
number chosen, no guardian posture picked, anywhere in the product.

## 1. The four mechanisms now available to you (Category B, fully shipped)

Each of the following is a versioned policy carrier you operate, not a
behavior engineering switched on. All four follow the same pattern:
effective-dated append-only versions, mandatory change reasons,
receipt + hash-chained configuration audit on every command, computed
readiness (incomplete → configured → validated → effective; retired
terminal), guarded Course Owner commands as the ONLY write path, and a
fail-closed resolver future consumers must honor.

### (a) D7 metric stewardship — `TH Metric Stewardship Policy`
You bring: the steward Role (an existing native Role name) + the
disclosure-rules text (who may see derived metrics; how labelled).
Commands (POST):
`...operations.metric_stewardship.create_metric_stewardship_policy` /
`...operations.metric_stewardship.set_metric_stewardship_policy_version` /
`...operations.metric_stewardship.set_metric_stewardship_policy_status` /
`...operations.metric_stewardship.validate_metric_stewardship_policy`.
While unset: every derived-metric mechanism refuses; raw reports
(R2 register) are unchanged. Evidence: `evidence/category-b-track-1-metric-stewardship-2026-09-25.md`.

### (b) Alert receiver policy — `TH Alerting Policy`
You bring: channel kind among Email / Webhook / Dashboard (the three
mechanisms engineering can qualify natively; SMS deliberately not
offered), the receiver destination, retention days (required),
optional escalation minutes.
Commands: `...operations.alerting.create_alerting_policy` /
`set_alerting_policy_version` / `set_alerting_policy_status` /
`validate_alerting_policy`.
While unset: alert conditions are generated, never delivered (the
observability RECEIVER BOUNDARY — unchanged). Evidence:
`evidence/category-b-track-2-alerting-receiver-policy-2026-09-25.md`.

### (c) Capacity/availability objective — `TH Capacity Objective`
You bring four numbers: concurrent users target, document scale
target, read share percent, availability target percent.
Commands: `...operations.capacity_objective.create_capacity_objective` /
`set_capacity_objective_version` / `set_capacity_objective_status` /
`validate_capacity_objective`.
While unset: the release gate's verdict is exactly its pinned state
(D8-CAPACITY-AVAILABILITY NOT_SELECTED → gate BLOCKED). The release
gate NEVER reads business settings (pin-tested); engineering measures
against your objective on the real host. Evidence:
`evidence/category-b-track-3-capacity-objective-2026-09-25.md`.

### (d) Guardian lifecycle policy — `TH Guardian Lifecycle Policy`
You bring: delegation window days, pre-admission proxy posture
(Allowed or Refused — no default), consent evidence mode (Link /
Attachment / Both — no default), consent expiry days, records/
recording-rights text.
Commands: `...operations.guardian_lifecycle.create_guardian_lifecycle_policy`
/ `set_guardian_lifecycle_policy_version` / `set_guardian_lifecycle_policy_status`
/ `validate_guardian_lifecycle_policy`.
While unset: advanced guardian features stay refused; identity and
guardian access remain exactly what the SEC-GUARDIAN-01 containment
enforces — the narrow remedy stands untouched (pin-tested neutral).
Retiring is the off-switch restoring today's behavior. Evidence:
`evidence/category-b-track-4-guardian-lifecycle-2026-09-25.md`.

All four render on the configuration desk (th-configuration) as real
domain sections + system-readiness items — read-only, read-only for
GM/Academic Manager too; the desk configures nothing itself.
Register entries updated: O-D7, V-OBS, O-D8N, O-D4 in
`docs/operating-system/DECISION-REGISTER.md`; closure register items
D7, obs-deployed-operation, gate-capacity-availability, D4 updated.
Suite: 1552 targeted tests green, ruff clean.

## 2. The genuine external-authority boundaries (only these stop engineering)

### (i) Production authorization — O-GO
Only you can authorize production. The state remains production REJECT
with the synthetic-only guard REQUIRED. Engineering cannot and must
not self-authorize; there is no environment in which engineering can
execute your GO. Evidence: `evidence/` release artifacts; register
O-GO.

### (ii) Real trust-boundary key custody — V-CUST
Sovereign provider/HSM/kms custody with authorization, revocation,
destruction and audit-log guarantees requires a provider and secrets
outside this repository and outside any Frappe Role — by the
permanent rule custody authority is NEVER bound to a Frappe role.
Evidence/register: V-CUST, sec-kms key-custody items.

### (iii) Real runtime with supported vendor pins — PINNED-UPSTREAM
The true runtime proof (your supported ERPNext/Education/HRMS/Frappe
versions on a real host) needs host access and owner-side authority
that are absent in this workspace. Engineering continues fixing
everything solvable here; the external evidence window remains the
boundary. (Hosted CI validation runs on every pushed commit.)

### (iv) Runtime-state criterion decision
`evidence/active-runtime-state-2026-09-25.md` records that the
transition criterion for the "latest-execution record" can no longer
be met: two independent push-triggered Foundation runtime runs on the
validation branch (`36114770663`, `36119457187`) completed success
with 123/123 checks pass while `security_gate_passed`,
`phase2_gate_passed` and `product_implementation_authorized` remain
false — the authored-runtime pin therefore does not move. Which
criterion governs the latest-execution record (authored-runtime pin vs
newest-run ledger block) is your call to make; the documentation now
records the divergence precisely and the gate enforces the pinned
form.

## 3. What did not change (pinned)
- Production REJECT; synthetic-only guard REQUIRED; d8_validate
  14/14 internal checks PASS with D8 BLOCKED and sec_deps
  UPSTREAM-BLOCKED/REJECT — exactly the maintained pins.
- No Runtime change on any site: no policy rows exist for any of the
  four carriers; no derived metric, alert delivery, capacity claim, or
  guardian feature can operate.
- Authorization/audit/fail-closed behavior and every existing gate:
  untouched; the full 1552-test suite is green on the exact committed
  code, same as before these surfaces existed.
