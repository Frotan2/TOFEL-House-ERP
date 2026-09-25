# TOEFL House ERP — Owner Decision Packet (R4)

Date: 2026-09-16 · Active branch: `arena/01a0cd90-tofel-house-erp`
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

## Current state of the owner-value planes (2026-09-25)

The per-gate records below are the canonical decision narrative. This section
records where each plane stands **now**, so the document stays truthful as
engineering ships configuration machinery around the unanswered values.

- **Versioned owner-value mechanisms shipped and hosted-validated** (synthetic
  content qualification run `36151148183`, owned suite `36151148191`, commit
  `88f5311`, 2026-09-25): TH Metric Stewardship Policy, TH Alerting Policy,
  TH Capacity Objective, TH Guardian Lifecycle Policy. Each is a versioned,
  effective-dated, immutable carrier with guarded Course-Owner commands,
  hash-chained configuration audit, explicit readiness, and fail-closed
  consumers — every business value still reads **NOT CONFIGURED** until the
  owner sets it. Command surfaces: `toefl_house.operations.metric_stewardship`,
  `.alerting`, `.capacity_objective`, `.guardian_lifecycle` (`create`,
  `set_version`, `set_status`, `validate_*`); evidence in
  `evidence/category-b-track-{1,2,3,4}-*-2026-09-25.md`.
- **Still awaited from the Owner** (nothing invented): the values for those
  four carriers plus every open item in
  `docs/operating-system/DECISION-REGISTER.md` (OD-NEW-01..09 values, D1
  values, D3 partials, D4/D5/D6a/D7 numerics, D8 numerics, synthetic-only
  lift, offsite destination, backup retention/windows).
- **External-authority boundaries engineering cannot cross**: production
  authorization (O-GO — any production posture change), real secret/key custody
  (V-CUST — machine-readable handoff from a designated custodian), the
  PINNED-UPSTREAM releases (only a new official Frappe/Bench release can clear
  SEC-DEPS-01; no pin override will ever be invented), and the runtime-state
  criterion decision recorded in
  `evidence/active-runtime-state-2026-09-25.md` (authored-runtime pin vs
  latest-execution ledger block — release-contract owner call).
- **SEC-DEPS-01** remains `EXTERNAL/UPSTREAM BLOCKED`; advisory delta
  re-verified 2026-09-25 with zero new applicable advisories
  (`evidence/sec-deps-01/feed-delta-reverification-2026-09-25.md`).

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

## D11 — Product license — **DECIDED 2026-09-19: MIT**
**Decide (pick one):** (a) **MIT** — matches what the app metadata already
declares; (b) a **copyleft** license — must first be checked against the
upstream Frappe/ERPNext/Education/HRMS terms this product links against;
(c) **proprietary / all-rights-reserved** — in which case the metadata
declaration is wrong and must be corrected; (d) **keep it unlicensed**.
**Why owner-only:** a license is a legal grant, it is effectively irreversible
once published, and it constrains how the upstream apps may be combined and
distributed. Engineering has no authority to select one, and none was selected.
**Resolved 2026-09-19 — MIT selected.** `LICENSE` now carries the MIT text,
both `hooks.py` declarations were already `app_license = "MIT"`, and the README
states the same thing, so all three surfaces agree.
`tests/foundation/test_licence_consistency.py` (6 tests) enforces the agreement
and scans the active surfaces for the stale wording, so this cannot silently
return. Upstream Frappe/ERPNext/Education/HRMS terms continue to govern those
apps; MIT does not relicense them.

*Historical (superseded): the 2026-09-17 review recorded a three-way
inconsistency — both `hooks.py` files declared `app_license = "MIT"` while the
README said no product license had been selected and no LICENSE file existed,
with GitHub reporting `null`. That state is preserved here as provenance only.* **Unblocks:** distribution of the owned
application outside this repository. Whichever option is selected, the
`hooks.py` declaration, the README statement, a repository LICENSE file and the
upstream-compatibility note must be made consistent **in the same change**.

---

---

## D12 — Teaching compensation posting basis and contract supersession windows
**Date:** 2026-09-19 · **Status:** DECIDED by the Course Owner.

**Question 1 — payroll posting basis.** A teaching assignment's payable is a
single flat amount derived from its contract (`payable_quantity × rate`, clamped
to the contract minimum/maximum). Assignments are created open-ended, so every
later payroll period selects the same assignment again. What does that flat
amount mean across recurring periods? **Decide (pick one):** (a) one-off
payable; (b) recurring every period; (c) pro-rated across the periods it spans;
(d) paid on completion only.

**Owner answer 1:** **(a) One-off payable.** Each assignment is compensated
exactly once, in the first payroll period that covers it.

**Question 2 — effect of a contract revision on the old window.** Revising an
instructor's contract marked the predecessor `Superseded` but left its
`effective_end` open, so payroll matched two contracts for any period after the
revision and refused to run at all. **Decide (pick one):** (a) close the
predecessor's window at the successor's start; (b) leave it and require a
narrower period; (c) prefer whichever contract is still Active.

**Owner answer 2:** **(a) Close the old contract at the successor's start.**

**Exact scope.** Both answers govern `toefl_house.teaching.compensation` only:
`calculate_teaching_compensation` and `revise_teaching_contract`.

**What this authorizes.** Payroll may post one Additional Salary per teaching
assignment, in the first period that covers it, and never again for that
assignment. A revision closes the predecessor's window the day before the
successor starts, so exactly one contract covers any period and the successor
rate applies from its own start date. Assignments and adjustments already
compensated in an earlier period are reported under
`already_compensated_prior_period` rather than skipped silently.

**What this does NOT authorize.** It does not make the flat amount a per-period
or pro-rated figure. It does not permit retroactive application of a successor
rate to periods already paid. It does not rewrite any rate, term, quantity or
adjustment on a superseded contract, so historical compensation remains
reproducible from it. It does not create a second payroll engine, a parallel
payable ledger, or any statutory/tax/slip calculation - native HRMS Salary Slip
and Payroll Entry remain the payroll authority. It does not authorize
production; production remains **REJECT**.

**Why owner-only.** Both are compensation semantics with direct financial
consequences: one determines how many times a teacher is paid for one teaching
fact, the other determines which rate applies from which date. Engineering had
failed both closed rather than guess, and both were escalated.

---

## D13 — Recovery objectives (RPO / RTO) — **DECIDED 2026-09-19**
**Owner answer:** **RPO 24 hours, RTO 8 hours.** Recover to the last nightly
backup; tolerate up to roughly one day of lost enrolments and payments; restore
service within eight hours.
**Scope:** the local-server + Tailscale deployment currently selected. No
internet-hosted topology is implied.
**Authorizes:** engineering to build and rehearse backup and restore against
those figures and to record measured results against them.
**Does NOT authorize:** production. Selecting a target is an input to
engineering, not evidence the target is met — D8-CAPACITY-AVAILABILITY stays
**BLOCKED** until it is independently proven. Nor does it authorize inventing any
availability, SLA or capacity number beyond these two figures.
**Why owner-only:** RPO and RTO are business tolerances for lost tuition records
and closed-door time, not engineering preferences; §12 forbids inventing them.

## D14 — Off-site backup destination — **DECIDED 2026-09-19**
**Owner answer:** **off-site hardware the Owner controls** — a separate physical
location, such as an off-site NAS or a second building. No third-party cloud;
student data stays in Owner-controlled custody, consistent with the local-server
+ Tailscale architecture.
**Scope:** the destination *class* and its custody. No specific device, hostname,
address or vendor is recorded, and none is invented here.
**Authorizes:** engineering to design and rehearse an encrypted off-site copy to
Owner-controlled hardware and to prove both the copy and its restore.
**Does NOT authorize:** production, sending student data to any third-party cloud
or provider, or naming a specific device, site or address — that remains an
operational detail the Owner supplies at implementation time.
D8-BACKUP-RECOVERY stays **BLOCKED** until an off-site restore is proven.
**Why owner-only:** the destination determines who physically holds student data
and where a disaster can and cannot destroy it.

---

## D15 — Production authorization scope — **DECIDED 2026-09-19**
**Owner answer:** **LOCAL LAUNCH ONLY.** The local server + Tailscale deployment
is the authorized launch scope. The public internet edge (provider, hostname,
DNS, public edge) is **not** authorized and stays unselected.
**Scope:** deployment-scope authorization for the currently selected local-server
+ Tailscale topology only.
**Authorizes:** the local server + Tailscale deployment as the launch target
(the Owner runs the launch runbook there); engineering to build the D16
controlled production-activation path; closing launch evidence (restore
rehearsal, TLS/session checks) against the local scope only.
**Does NOT authorize:** flipping production to GO while SEC-DEPS-01 is REJECT
(the Owner's simultaneous standing decision); any internet deployment; waiving
the backup-restore rehearsal, TLS/session evidence, or durability/observability
gates — scope authorization is not gate passage; treating hosted synthetic
qualification as production evidence. Production stays **REJECT**.
**Why owner-only:** only the Owner can accept the business risk of serving real
students on the system and can bound where that risk may be taken.

## D16 — Production activation mechanism — **DECIDED 2026-09-19**
**Owner answer:** **YES — build the controlled activation.** Owned commands may
operate on the named production site once the explicit activation flags are
present; everywhere else the synthetic-only hard stop stays in force.
**Scope:** `toefl_house.security` site-mode resolution and the guarded command
entry points only. Activation is the explicit triple:
`toefl_house_production_active=1` **and** `toefl_house_production_site` equal to
the running site name. Mixed synthetic+production mode is refused; the two
qualification hostnames can never be the production site.
**Authorizes:** site-mode resolution (SYNTHETIC / PRODUCTION / REFUSED) with
fail-closed refusal as the default; accepting PRODUCTION mode at the guarded
command entry points alongside unchanged SYNTHETIC qualification behavior; the
server activation steps in the launch runbook with verification commands.
**Does NOT authorize:** removing or weakening `require_synthetic` on any
qualification path; any activation that does not name the production site
explicitly; production GO by itself — activation is a mechanism, and production
stays **REJECT** until the gates close.
**Why owner-only:** lifting the synthetic-only hard stop changes what data the
system may touch. Only the Owner can permit real student data into command paths.

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
| D11 | **(a) MIT** — DECIDED 2026-09-19 | Found by the 2026-09-17 engineering review as a three-way contradiction: `hooks.py` declared MIT in both apps, the README said no license was selected, no LICENSE file existed and GitHub reported `null`. The Course Owner selected MIT on 2026-09-19; all three surfaces were made consistent in one change and `tests/foundation/test_licence_consistency.py` now enforces the agreement. Upstream Frappe/ERPNext/Education/HRMS terms still govern those apps. |
| D15 | **LOCAL LAUNCH ONLY** — DECIDED 2026-09-19 | Local server + Tailscale is the authorized launch scope; the internet edge stays unselected and unauthorized. Scope authorization is not gate passage: SEC-DEPS-01 stays REJECT per the simultaneous standing decision, so production stays REJECT. |
| D16 | **Build the activation** — DECIDED 2026-09-19 | Controlled production-activation path authorized: explicit named-site triple, mixed mode refused, qualification hostnames never production. `require_synthetic` unchanged on qualification paths. Activation is a mechanism, not GO. |
