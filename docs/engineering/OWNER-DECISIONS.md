# TOEFL House ERP — Owner Decision Packet (R4)

Date: 2026-09-16 · Branch: `arena/01a0a496-tofel-house-erp`
**Production remains REJECT.** Nothing here invents a business rule —
every gate below is a decision that only the owner may make; engineering
state is stated exactly as evidenced in the Release Gap Map.

Each gate: what is decided, why engineering cannot decide it, current
verified state, and what the decision unblocks. Answering a gate does
not auto-approve any deployment — D8-class operational gates stay
independent.

---

## D1 — Academic assessment & progression (B04/B05 → A06)
**Decide:** level vocabulary (e.g. how many bands/levels exist),
sections/components per level, rubrics/units/cutoffs, course mapping;
grading scale and progression rules.
**Why owner-only:** grading policy is academic business policy; no
native Frappe/Education default may be assumed as TOEFL House policy.
**Current state:** zero implementation started (by design — starting
would invent rules). Native Program/Course Enrollment lifecycle is
closed and available as the carrier (run 34946981784).
**Unblocks:** A06 assessment slice.

## D2 — Payroll input path (B08 → A09)
**Decide:** employment classifications, pay basis, payable units,
statutory rules; confirm single native HRMS input path (no parallel
payroll ledger).
**Why owner-only:** employment/statutory rules are legal business
policy. **Current state:** HRMS v16.18.1 pinned in the bundle; no
payroll slice implemented. **Unblocks:** A09.

## D3 — Refund / cancellation / credit-note terms
**Decide:** who approves refunds, windows, partial-refund policy.
**Why owner-only:** financial terms. **Current state:** Finance domain
closed without a refund surface (run 34999987969); native Credit Note
exists but its issuance policy is undefined. **Unblocks:** finance
correction command surface.

## D4 — Identity & guardian lifecycle (B01/B02 → A02/A03)
**Decide:** identity merge/activation policy; guardian delegation and
pre-admission proxy rules.
**Why owner-only:** defines who may act for a student. **Current
state:** narrow explicit-User-Permissions guardian remedy passes
hosted; full fail-closed isolation (SEC-GUARDIAN-01) awaits this
policy. **Unblocks:** A02/A03 + SEC-GUARDIAN-01 closure.

## D5 — Calendar / repeat / transfer / withdrawal (B03 → A05/A11)
**Decide:** real intake calendars, whether same-term repeats are
required, transfer/withdrawal semantics with history preservation.
**Why owner-only:** operational academic policy. **Current state:** not
implemented. **Unblocks:** A05/A11.

## D6 — Tax configuration & payment gateway (B07 remainder/B12)
**Decide:** tax configuration policy; payment-gateway selection or
explicit "none" for launch.
**Why owner-only:** legal/tax assumptions are prohibited for
engineering to invent; gateway choice is commercial. **Current state:**
`payments` app commit-pinned (`cca07d9f…`) but explicitly *not* a
gateway approval. **Unblocks:** tax setup, online payments.

## D7 — Metrics layer stewards (A12)
**Decide:** named metric stewards; denominators, disclosure and
retention rules for any derived metric.
**Why owner-only:** metrics encode management policy. **Current
state:** R2 registers ship **raw facts only** (hosted-proven, run
35049742120); no derived metric exists anywhere. **Unblocks:**
reporting metrics layer above the registers.

## D8 — Deployment topology ownership
**Decide:** independent-host DR, capacity/monitoring ownership,
TLS/proxy/session policy; who operates each.
**Why owner-only:** operational and contractual. **Current state:**
Phase 2 production acceptance ledger (2026-09-14) = REJECT with scoped
passes (web/worker restart, scheduler, framework patch upgrade,
hardened restore). **Unblocks:** Phase 2 production acceptance; this is
the last class before production may leave REJECT.

## D9 — Attendance-coverage register access anchor (R2 remainder)
**Decide (pick one):**
(a) grant teaching roles native **Academics User** — widens direct
write access beyond the guarded teaching API;
(b) Custom DocPerm replication on Student Attendance — invasive;
replaces native permission rows wholesale (same mechanism that voids
Sales Invoice perms, proven in run 35048606232 diagnostics);
(c) new TH anchor doctype carrying teaching facts for report access;
(d) **no register** — current state; teaching facts reachable via
guarded APIs only.
**Why owner-only:** each option trades off containment vs convenience.
**Current state:** registers shipped without attendance coverage;
option (d) is the enforced status quo. **Unblocks:** TH Attendance
Coverage Register.

## D10 — Desk workspaces for API-first staff roles (R1 remainder)
**Decide:** whether staff roles (invigilator, placement
author/publisher, admission, enrollment, teaching) receive native
document reads (a containment change), a report/page-based surface per
role, or no Desk navigation.
**Why owner-only:** granting native reads changes the A13 containment
boundary — a security decision. **Current state:** pinned frappe
module-visibility gate means no workspace can surface for zero-read
roles (run 35048606232 diagnostic: roles resolve to `["All","Guest"]`,
no workspace module eligible). Auditor and Finance Officer surfaces are
shipped and hosted-proven (run 35049742120). **Unblocks:** staff-facing
Desk workspaces.

---

**How to answer:** reply per gate ID with the chosen option/values.
Every answer is executed as a scoped slice with hosted proof through
the existing 533-check suite — no domain reopening, no parallel
masters, production stays REJECT until D8-class gates are
independently satisfied.

---

## Owner answers (received 2026-09-16, recorded verbatim in effect)

| Gate | Answer | Consequence |
|---|---|---|
| D1 | **Defer** | A06 stays unstarted |
| D2 | **Unlocked — contract-driven teaching compensation** (full business+technical requirement received; rates/terms remain owner configuration) | T1–T3 slices opened; design: TEACHING-COMPENSATION-DESIGN.md |
| D3 | **Framework approved; exact terms later** | Guarded correction/refund command framework with configurable approval terms; no windows/partial-policy invented |
| D4 | **Defer advanced policy** | Narrow hosted-proven remedy stands; SEC-GUARDIAN-01 full closure stays deferred with portals |
| D5 | **Native basic lifecycle; advanced policy later** | A05/A11 stay unstarted |
| D6a | **Tax not configured yet** | No tax configuration anywhere; recorded as decision, not omission |
| D6b | **No gateway at launch** | Gateway closed as 'none'; payments app stays pinned-but-unapproved |
| D7 | **Defer; raw reports now** | Registers stay raw-facts-only (matches shipped state) |
| D8 | **Define role-based operational ownership** | Operational ownership charter (roles/responsibilities) to be produced; named human/contractual assignment remains with the owner; production stays REJECT until satisfied |
| D9 | **(d) No separate register** | Gate CLOSED at status quo; attendance facts via guarded APIs only |
| D10 | **(ii) Role-based report/page surfaces** | Staff navigation via report/page surfaces; containment boundary unchanged (no native reads granted) |
