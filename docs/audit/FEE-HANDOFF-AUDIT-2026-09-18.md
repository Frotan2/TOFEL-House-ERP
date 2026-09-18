# Admission → Enrollment → Fees Handoff Audit — Kickoff Plan (2026-09-18)

Status: **CLOSED 2026-09-18 — all five gaps hosted-verified on run
35344291259 (569/569 checks); two product defects found and fixed at root
cause. See §8 ledger.** The plan below is kept as issued (published before
any code change, per the standing rule).
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

## 8. Execution ledger (closed 2026-09-18)

**Product defects found by this audit — both fixed at the smallest root
cause with regression coverage; neither was visible to the 815/819-test
unit layer:**

1. **Discounts never reached the tuition receivable.** The pinned native
   Education `Fees.calculate_total()` (education 93bc70757533) computes
   `grand_total` as the plain sum of component `amount` fields and does
   not apply the child `discount` field; `issue_tuition_fees` recorded the
   resolved single discount only on the child row. Found while validating
   probe arithmetic against the pinned controller (before any hosted run),
   because the offline acceptance rehearsal's fake `Fees` had applied the
   discount field the native controller ignores — the fake itself was the
   second defect (fidelity). Fix: new pure helper
   `rules.apply_charge_discount(gross, pct)` (one application per line by
   construction), command bills `amount = net`, keeps the percentage on the
   child row as the descriptive record, and reports `gross_total` /
   `discount_amount` / per-line `gross_amount`/`net_amount` on the receipt.
   The rehearsal fake now mirrors native exactly.
2. **Rule fetch omitted `status`, so resolution silently found nothing.**
   `resolve_charge_discount` re-validates each fetched row's own `status`;
   the `frappe.db.get_all` field list didn't include it, so at runtime
   every Active rule was treated as non-Active and dropped. Found by
   hosted run 35342862926 (`KeyError: 'discounts_applied'` in
   `odcp-discount-single-winner-tuition`; the other 562 checks passed).
   Fix: fetch `status` alongside the resolver-consumed fields. Pinned by a
   pure resolver row-shape contract test plus a static field-list lock
   (`tests/configuration/test_discount_math.py`).

**Hosted run ledger (branch `arena/01a0b3a7-tofel-house-erp`):**

| Run | Result | Meaning |
| --- | --- | --- |
| 35342862926 (`ecb227b`) | fail 562/563 | Defect #2 exposed on the real site; fixtures, seeding and all command-plane guards already green. |
| 35344291259 (`e870293`) | **success 569/569** | Final qualification. Report SHA-256 `df87b9893abddc14fc06368c7a50389f81452066eb77933509418d38a44e0a3d`, `status: pass`, `production: REJECT`. Owned suite 35344291287: 829 tests, ruff 0.16.8, node guards, D8 BLOCKED assertions — all green. |

**Gap-by-gap evidence (check names as published in the 569-check report):**

- **G1 (OD-CP-1 = A, one discount per charge line):**
  `odcp-fee-catalog-fixture`, `odcp-discount-rules-seeded`,
  `odcp-discount-rule-command-guard` (non-owner writes denied, 100% cap
  boundary accepted-then-retired, precedence format, duplicate code,
  unknown category, unknown rule — all refused),
  `odcp-discount-single-winner-tuition`: exactly one winner per line
  (`one_discount_per_line`, `no_stacking`), higher precedence beats higher
  percentage (TUI 10% p9 wins over broad BIG 20% p5), retired 99-precedence
  rule ignored, non-matching program scope ignored, deterministic tie-break
  to `SYN-DISC-TIE-B`, and — the receivable proof — `grand_total` 26000.0
  on a 30000.0 structure (gross − 4000.0 discount), persisted child rows
  and the GL Entry debit verified equal to the reduced receivable
  (`gl_equals_receivable`), `replay_identical`.
  `odcp-discount-scope-live-and-immutable`: a newly-created 50% family rule
  takes effect for new issuances only (`scoped_rule_applies`,
  `both_lines_reduced`) and the earlier discounted fee stays frozen
  (`historical_fees_unchanged`). `odcp-discount-retirement-control`: retired
  rules vanish from new issuances (`billed_gross_after_retirements`, 25000.0
  gross) while every earlier fee remains untouched (asserted inline);
  non-owner reactivation denied (`non_owner_status_write_denied`).
- **G2 (OD-CP-2 = B, full-amount only, native accounting):** the earlier
  hosted `finance-correction-*` trio already proves fail-closed without
  policy, the dual-key approval, window, partial refusal and native
  credit-note posting; this audit adds `odcp-refund-surface-absent`:
  submitted Fees (tuition receivables) are not a correction target at all
  (`fees_not_correctable`), unknown invoices denied (`missing_invoice_denied`),
  the fee fact untouched (`fee_fact_untouched`) — combined with the
  existing A13 containment (`containment-rpc-routes-denied`, cancel-route
  refusals on Fees) there is no second refund authority.
- **G3 (OD-CP-3 = A, global config only):** `odcp-global-config-no-branch`
  — runtime meta proves no branch dimension on `Fee Structure`,
  `Fee Component`, `Fees`, `TH Discount Rule`, `TH Correction Policy`; the
  branch attribute exists only on the operational class layer
  (`operational_branch_present_only_on_classes`).
- **G4 (seam continuity):** `integration-journey-through-fees` — the
  `TH Placement Operation` receipt for the discounted issuance is Complete
  with the finance actor, exactly one `TH Placement Audit Event` targets
  the fee, a same-key replay adds no event, and the enrollment behind the
  fee is the journey student's (`pe_matches_journey_student`) — admission →
  enrollment → fees is one receipted chain.
- **G5 (legacy leakage):** `odcp-legacy-vocabulary-absent` — all 27 `TH %`
  doctypes on the migrated site scanned; no Refund/Override/Partial/Branch/
  Fee Schedule/Payment-Term vocabulary exists.

**Open owner questions surfaced (deliberately NOT invented):**

- *Discount program scope semantics*: resolution compares the rule's
  `TH Academic Program` code to the enrollment's native Program name
  literally. A rule scoped to a family therefore applies exactly when the
  native program name equals the family code (the behavior pinned above).
  Whether a family-scoped rule should apply to **all levels'** native
  programs of that family is an owner semantics decision — not implemented.
- *Tuition-side refunds/corrections beyond the invoice framework*: fees
  corrections await owner terms, mirroring the invoice-side v1 posture;
  the system stays fail-closed (`odcp-refund-surface-absent` documents the
  containment, not a policy).

Standing blockers unchanged: **SEC-DEPS-01 UPSTREAM-BLOCKED**, D8
**BLOCKED**, production decision **REJECT** (restated by the hosted report
itself). This audit verified existing implemented behavior end-to-end; it
introduces no new business policy and claims no production readiness.
