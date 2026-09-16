# TOEFL House ERP — Owner Decision Packet (R4)

Date: 2026-09-16 · Active branch: `arena/01a0a9f7-tofel-house-erp`
**Production remains REJECT.** Nothing here invents a business rule. This
file is the human-readable projection and navigation document for the canonical
[`canonical-owner-decision-record.json`](canonical-owner-decision-record.json);
that record is authoritative for the owner decisions supplied on 2026-09-16.
Engineering state is stated exactly as evidenced in the Release Gap Map.

Each gate records what is decided, why business policy cannot be invented by
engineering, current verified state, and what the decision unblocks. Selecting a
business requirement does not auto-approve deployment — D8-class operational
evidence gates and SEC-DEPS-01 remain independent.

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

## D8 — Production-operation inputs
**Authoritative decision:** the owner requirements are recorded in the
[canonical owner-decision record](canonical-owner-decision-record.json). They
select Course Owner as system/strategic final authority; General Manager for
routine administration and operations; Academic Manager for academic operations
and progress; Finance Manager for finance/payroll; Reception for intake; role-based
access, auditability, and offboarding; multi-branch architecture with branch-level
operational isolation; current local/server operation through Tailscale with local
database/files; automated multi-version encrypted backup and recovery onto another
system with data preservation prioritized; configurable business policy and teacher
compensation; controlled role/permission administration and health/attention
visibility. Student/guardian portal and online payments are not launch scope.

**Engineering boundary:** authentication/MFA, RBAC mechanics, network/session
controls, encryption/secrets, backup rotation/recovery, monitoring, configuration
versioning, rollback, CI/CD, and deployment hardening are engineering-owned.
Future internet provider/hostname/DNS/public edge, future off-site destination,
numeric capacity/availability, and numeric RPO/RTO are not supplied and are not
invented. The [D8 production-operations decision matrix](d8-production-operations-decision-matrix.json)
records selected business requirements separately from technical evidence.
The provider-neutral contract template and fail-closed validator are
[`d8-operational-contract.template.json`](d8-operational-contract.template.json),
[`PRODUCTION-OPERATIONS-IMPLEMENTATION-CONTRACT.md`](PRODUCTION-OPERATIONS-IMPLEMENTATION-CONTRACT.md)
and [`d8_validate.py`](../../tools/foundation/d8_validate.py).

**Current state:** owner policy is reconciled, but selected operational areas
remain **BLOCKED** pending implementation and independent evidence. The current
synthetic SQL/files backup and separately created-site restore verifier cannot
establish independent-host DR or production operations. Capacity/availability
remains the only unresolved numeric business objective. Selecting D8 requirements
does not remove production **REJECT** or waive any acceptance-ledger/security gate.

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

## D10 — Staff Page/report navigation (R1 remainder)
**Decide:** whether staff roles (invigilator, placement
author/publisher, admission, enrollment, teaching) receive a native
read/Workspace change, a report/Page surface per role, or no Desk
navigation.
**Why owner-only:** adding native reads would change the A13 containment
boundary. **Selected answer:** option (ii), a role-based Page/report
surface with **no new authority**. The factual record is more precise
than the former “zero document permissions” shorthand: these roles
already have limited, existing TH-DocType read scopes, narrowed again
by `policy.can_read`; no native Education/ERPNext CRUD role is being
added. The pinned Workspace/module-gate composition nevertheless did
not yield a compliant staff Workspace (diagnostic run 35048606232).
Auditor and Finance Officer Workspace/report surfaces remain shipped and
hosted-proven (run 35049742120). **Unblocks:** a separately role-gated
native Page command surface, whose client can call only existing guarded
commands. **Qualified evidence:** current-branch run `35073376790` at
`3587700110d21816b239779c93c32f4060cd3c63`, 542/542 checks, proved the
13 Page records/assets, each of 12 role-specific Page audiences plus
seven non-members, and no native-read escalation.

---

**How this packet is used:** business decisions are recorded once in the
canonical JSON record and projected here. Engineering executes only the scope
that those decisions unlocks, with narrow then broad validation; no domain
reopening, no parallel masters, and production stays REJECT until D8-class
technical gates are independently satisfied.

---

## Owner answers (received 2026-09-16, recorded verbatim in effect)

| Gate | Answer | Consequence |
|---|---|---|
| D1 | **Defer** | A06 stays unstarted |
| D2 | **Unlocked — contract-driven teaching compensation** (full business+technical requirement received; rates/terms remain owner configuration) | **EXECUTED & QUALIFIED** — T1/T2 hosted-proven (run 35066349129 @ fa02137, 536/536); design: TEACHING-COMPENSATION-DESIGN.md |
| D3 | **Framework approved; exact terms later** | **FRAMEWORK SHIPPED & QUALIFIED** — run 35069740378 @ ed2d81d, 539/539. Fail-closed until you configure: approver role + correction window (TH Correction Policy). Remaining owner asks: partial-refund terms, Fees-side correction scope |
| D4 | **Defer advanced policy** | Narrow hosted-proven remedy stands; SEC-GUARDIAN-01 full closure stays deferred with portals |
| D5 | **Native basic lifecycle; advanced policy later** | A05/A11 stay unstarted |
| D6a | **Tax not configured yet** | No tax configuration anywhere; recorded as decision, not omission |
| D6b | **No gateway at launch** | Gateway closed as 'none'; payments app stays pinned-but-unapproved |
| D7 | **Defer; raw reports now** | Registers stay raw-facts-only (matches shipped state) |
| D8 | **Owner requirements selected and recorded in the canonical owner-decision record** | Authority roles, role-based access/auditability/offboarding, branch isolation, current local/Tailscale deployment, local state, encrypted versioned backup/recovery, preservation priority, configurable policy, compensation models, controlled administration, and health/attention visibility are now business inputs. Future provider/hostname/DNS/public edge, off-site destination, numeric capacity/availability, and numeric RPO/RTO remain unselected. Engineering implementation and independent evidence remain D8-BLOCKED; production stays REJECT. |
| D9 | **(d) No separate register** | Gate CLOSED at status quo; attendance facts via guarded APIs only |
| D10 | **(ii) Role-based report/page surfaces** | **T3 EXECUTED & QUALIFIED** — 13 native command Pages (role-filtered command centre + 12 one-role action Pages), no new native Education/ERPNext authority; run 35073376790 @ 3587700, **542/542**. The separate Course Owner/General Manager control-centre Page is a locally contract-tested governance surface and not a replacement for the qualified command evidence. |
