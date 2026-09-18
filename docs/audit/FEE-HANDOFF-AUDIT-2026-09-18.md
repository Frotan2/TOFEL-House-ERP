# Admission → Enrollment → Fees Handoff Audit — Kickoff Plan (2026-09-18)

Status: **PLAN — published before any code change** (standing rule).
Scope discipline inherited from the Class + TH Skill slice (ERP-SEMANTIC-AUDIT-2026-09-18.md §12):
unit tests and static analysis are never runtime evidence; every verified line below cites a
hosted run; anything not hosted-proven is listed as a gap, not a claim.

## 1. Mission

Prove in a real Frappe runtime that the money path honors the Owner's settled decisions —
OD-CP-1 (one discount per charge line, no stacking), OD-CP-2 (full-amount corrections only,
native accounting for reversal), OD-CP-3 (global configuration only; branch is an operational
attribute, never a pricing override) — and that the three seams admission → enrollment →
fees hand off without letting any actor or API bypass the guards. Where runtime exposes a
defect: fix the smallest root cause, add regression coverage, rerun the full relevant suite,
and repeat the hosted qualification. No new business policy is introduced anywhere in this
mission; deferred owner decisions (§11.2 of the semantic audit) stay deferred.

## 2. What is already runtime-proven (do not re-litigate; keep as regression)

Hosted run 35337366200 (commit `bdbacc0`), report SHA-256
`df108f6a9428dcbdd74491f158e3acac6daa828ace29fa993e3cad00ce276694`, 559/559 checks green
on both fresh pinned sites (`placement-test.localhost`, `placement-second.localhost`;
frappe 988e54f3c4c2, education 93bc70757533, erpnext 4048fb70…, hrms a4768b44…):

- **Admission decisioning** — 66 `admission-*` / `http-admission-*` checks: applicant
  recording, review/approve/accept SoD with self-decision refusals, conditional offers that
  must not convert, expiry against placement validity, withdraw/reject paths that do not
  convert, direct-DB and `ignore_permissions` bypass refusals, idempotent conversion,
  concurrent idempotency, per-site isolation.
- **Enrollment** — 35 `enrollment-*` / `http-enrollment-*` checks: role refusals
  (outsider/author/officer/approver/publisher/withdrawn/rejected/expired), happy path,
  idempotent replay, duplicate refusal, native Program Enrollment stays the authority
  (`enrollment-direct-pe-still-denied`), atomic rollback, REST seam coverage.
- **Fee issuance** — `finance-tuition-*` (catalog, unknown-enrollment/bad-window/
  outside-year-structure refusals, role refusals, happy path, idempotent replay, duplicate
  billing denial, direct-write denial, atomic rollback) and `http-finance-tuition-positive` /
  `-idempotent-replay`; `finance-placement-*` (case billing incl.
  `finance-placement-native-pricing-rule-waiver`); `finance-write-containment`;
  `finance-correction-fail-closed` / `-sod-and-window` / `-posting`.

These cover the *existence and containment* of the handoff. They do **not** yet exercise the
OD-CP semantics end-to-end on the live site — that is the gap set.

## 3. Gap register (unit/static coverage only today)

G1 — **OD-CP-1 discount resolution at runtime**. `resolve_charge_discount`
(`apps/toefl_house/toefl_house/academic/rules.py`) implements single-winner resolution
(highest precedence; deterministic tie-break on percentage then code) and
`issue_tuition_fees` applies at most one discount per charge line, but this is exercised
only by `tests/configuration` (pure-policy) tests. Hosted probe: seed 2+ Active
`TH Discount Rule` records overlapping one fee category (plus one Inactive and one
scoped to a different category/program), issue tuition on the real site, and assert
(i) exactly one discount applied to the matching line, (ii) `grand_total` equals the
single-discount amount — no stacking — (iii) Inactive/category/program scoping honored,
(iv) the `discounts_applied` receipt names the winning rule, (v) a tie resolves to the
documented deterministic winner.

G2 — **OD-CP-2 correction/refund semantics at the money seam**. The D3 framework
(`finance/corrections.py`) refuses anything but the full invoice amount and posts only via
the native return invoice; hosted `finance-correction-*` checks exercise this against
placement Sales Invoices. Not yet hosted-proven: (i) a partial `requested_amount` against a
**tuition-side** invoice/fee is refused with the exact message "v1 corrects the full
invoice amount", (ii) the Fees document itself cannot be cancelled/edited to fake a refund
(extend `finance-write-containment`/`finance-tuition-direct-write-denied` to the refund
intent), (iii) no `TH` refund ledger exists (`no second accounting system` stays true —
assert absence of refund DocTypes on the migrated site), (iv) refunding an *issued tuition
Fee before the owner defines fee-side correction policy* remains fail-closed. Note
explicitly: whether class cancellation refunds fees is a **deferred owner decision**
(§11.2) — this mission verifies the refusal behavior, never the policy.

G3 — **OD-CP-3 no branch-specific pricing**. Verify on the migrated runtime that
`Fee Structure`, `TH Discount Rule`, and `TH Correction Policy` carry **no** branch field
(meta absence), that a class/record's branch changes nothing in discount or fee resolution
(issue identical tuition under two different branches → identical `grand_total`), and that
the legacy per-branch fee-override shape is absent from fixtures and doctypes (static scan
already exists; add the runtime half).

G4 — **Seam continuity through the money layer**. `integration-journey-receipt-continuity`
proves receipt linkage admission → enrollment. Extend one journey check to continue into
`issue_tuition_fees` + discount application + correction request on the *same* enrollment,
asserting audit-ledger continuity across all three seams and that a re-run of the whole
journey is idempotent end-to-end.

G5 — **Legacy leakage guard at runtime**. One negative probe per forbidden legacy semantic:
partial-refund fields never settable on return invoices through our commands, discount
values >100% or negative refused at rule creation (configuration side; check whether a
hosted half already exists in the config-plane checks — if yes, reference only), and
branch-scoped discount rules cannot be created even via direct DB insert+issue (guard fires
at resolution, not only at form level).

## 4. Method and evidence protocol (unchanged)

Reuse `.github/workflows/placement-content.yml` → `tools/placement/run_native.py` on fresh
pinned sites; publish gzip+base64 reports with SHA-256 as check runs; transcribe results
from the check-run output before claiming anything; deliberately test negative paths; fix
harness bugs at the smallest root cause (the `tests/placement/test_native_check_arity.py`
guard now catches the arity bug class before pushing). Owned suite (currently **819
tests**) plus ruff 0.16.8 must stay green for every push.

## 5. Standing constraints (carry-over, binding)

Native Student Group remains the class authority; no TH Class/TH Cohort/Offering/Program
Version may be created to satisfy a test; no second permission engine or accounting system;
legacy extracted files are evidence only; delivery mode stays on the operational class
layer; OD-CP-1=A, OD-CP-2=B, OD-CP-3=A exactly as decided; production stays blocked by
SEC-DEPS-01 (UPSTREAM-BLOCKED) and D8 (BLOCKED); the report must end at the evidence
boundary — no production-readiness claim.

## 6. Definition of done

Hosted run(s) green with per-item check names recorded in the §12-style ledger (new §13
section of this document or an appended ledger here); items G1–G5 marked verified only from
transcribed evidence; any defect found fixed at root cause with regression coverage and a
full re-qualification; owned suite ≥ current count, lint clean; audit doc pushed to
`arena/01a0b3a7-tofel-house-erp`; blockers unchanged.

## 7. Sequencing

1. Owner (or this agent on request) confirms the gap set and probe list above.
2. Add probes to `tools/placement/native_checks.py` in dependency order G1 → G3 → G2 → G5 → G4
   (config plane first so the money probes can seed rules through the published commands).
3. Push → hosted run → transcribe → fix defects at root cause → rerun until green → ledger.
