# Role Desk Owner Decisions Ratification — OD-RD-1..4 (2026-09-18)

Date: 2026-09-18 · Active branch at evidence time: `arena/01a0b3a7-tofel-house-erp`
Session branch: `arena/01a0b568-tofel-house-erp`
Base commit for this ratification: `d5f9e426e8bd75f2ad43c1a47b4dddb548ea6d44`
Final product SHA with full Phase-2 green: `31e6add1724bf96a3e2b9eb460ea080738a0117f`

**Production remains REJECT** — SEC-DEPS-01 upstream-blocked, synthetic-only activation required.
This ratification does not authorize production; it closes the product-readiness of the six role desks.

## Hosted evidence that informs these decisions

Both runs were on `arena/01a0b3a7-tofel-house-erp` at `31e6add`:

- **Owned suite** `35365044995` — success, ruff 0.16.8, 847+ Python tests, all four Node suites (realtime_guard, command_pages, design_system, role_desks), D8 gate BLOCKED / production REJECT as required.
- **Placement synthetic content qualification** `35365045006` — success, 570 native checks, check-run `105668996321`, report SHA-256 `45a698dcd6ea5e2341eddbf335e68c5b57ea99c52d8bb10d9289a04265b49cdf`.

The placement report includes the `role-desk-hosted-qualification` observation:

```json
{
  "audiences": "all six desk loads HTTP 200; guest/outsider/cross-audience denied; POST to a read endpoint refused by its GET/POST marks",
  "guided_actions": "schedule prefills reach the acting role over HTTP; non-holders see none",
  "fees_correction": {
    "target_fee": "EDU-FEE-2026-00001",
    "amount": 25000.0,
    "request": "ghph21s107",
    "http_request_and_approve": true,
    "replay_identical_receipt": true,
    "partial_denied": true,
    "outsider_denied": true,
    "duplicate_open_denied": true,
    "dual_key_denied": {"denied": "PermissionError"},
    "posted_and_reversed": true,
    "gl_open_rows_after": 0,
    "desk_shows_named_fee_target": true,
    "desk_clears_after_posting": true,
    "denial_keeps_fee": true,
    "redeny_allowed_after_denial": true,
    "note": "OD-RD-1 evidence only: ratification waits for the owner"
  }
}
```

Cycle-by-cycle ledger (from `ROLE-DESK-UX-AUDIT-2026-09-18.md` §10):

| Cycle (placement-content run) | On | Outcome |
| --- | --- | --- |
| `35356041546` | `53aae30` | fail — finance `section(empty_body=…)` still named `Payment Entry`/`Program Enrollment`; fixed in `64884ff` |
| `35359895735` | `82275fd` | fail — `available()` 403'd guests against its own documented empty-registry contract; fixed (`allow_guest=True`) |
| `35362218310` | `421c533` | fail — Reception class-truth check aimed at `work()` instead of `lookup()`; fixed |
| `35363856854` | `ca9ac7f` | fail — `Lock wait timeout`: intentional partial-denial holds fee row past savepoint rollback (InnoDB keeps locks); fixed with explicit rollback before HTTP request and commit after approval |
| `35365045006` | `31e6add` | **success** — 570 checks pass; including six audience loads 200, guest/outsider/cross-audience denied, non-retargetable POST, payloads free of doctype plumbing, `Class — Active` from governed lifecycle, lookup reads `Enrolled`, U1 prefills per role, and OD-RD-1 fees-correction chain end-to-end |

Offline guards at final SHA:

- `tests/desk` — 53 tests green (audience gates, projection allow-lists, bounded queries, lifecycle, finance vocabulary, page-audience ties, guided endpoint signatures, runtime smoke, schema fidelity via `pinned_schema.json`, branch-scope non-crash).
- `tests.placement.test_native_check_arity` — green.
- Full tree 847 tests: 844 pass, 3 expected branch-boundary failures on non-active session branch `arena/01a0b568` (active pin remains `arena/01a0b3a7` per `BRANCH-RECONCILIATION.md`).

## Owner decisions — recorded 2026-09-18

### OD-RD-1 — Fees-side correction ratification

**Question:** Fees-side correction is wired (request/approve/deny_fees_correction with OD-CP-2-B semantics: full-amount only inside window, dual key, native `fee_doc.cancel()` as money artifact, GL reversal, desk row naming real target, denial-path integrity). Hosted qualification now green end-to-end. Ratify?

**Owner answer:** **Ratify fees-side correction as implemented (RECOMMENDED)**

- Semantics: full-amount only, inside correction window defined by `TH Correction Policy`, dual-key (requester ≠ approver, approver must hold configured `approver_role`), native cancellation as money artifact, GL reversal verified against pinned education `93bc70757533` `fees.py on_cancel → make_reverse_gl_entries`.
- Evidence: `EDU-FEE-2026-00001`, request `ghph21s107`, amount 25000.0, replay-identical receipt, `gl_open_rows_after: 0`, desk shows named fee target then clears, denial keeps fee, re-request after denial allowed.
- Run IDs: `35365044995` (owned-suite) + `35365045006` (placement-content, report SHA `45a698d...`).
- Production: remains REJECT, SEC-DEPS-01 untouched, synthetic-only activation required.
- This ratification does not invent refund terms; partial-refund remains owner-deferred per D3. Window and approver role remain owner configuration in `TH Correction Policy`.

### OD-RD-2 — Phase-2 ordering for remaining UX

**Question:** Original Phase-2 plan D1→D2/D3/D4→U9→E4→U-series is DONE and green. Remaining UX: U3 (reception dead-end guidance), U6 (owner cockpit accepted/native_student), U7 (deployment fact staleness), U8 (workspace navigation declaration). All fixed in this turn.

**Owner answer:** **Verify now and close Phase-2 (RECOMMENDED)**

- Accept U3/U6/U7/U8 fixes in this commit, run local desk suite (53 tests) + push to session branch `arena/01a0b568`, then re-qualify via owned-suite + placement-content hosted runs as final close-out. No new product scope.
- U3 fix: reception `Applicant recorded` next text now names who releases: "Open the admission decision once a placement result is released for this applicant's email. A placement result appears after the Placement Publisher finalizes the attempt and the Placement Releaser releases it — ask those roles to publish the result if it is not yet visible."
- U6 fix: `owner.py` projection now selects `accepted, native_student` (allow-list already had them), so oldest open admission stage is true.
- U7 fix: `RELEASE_POSTURE` Deployment value now `LOCAL_SERVER_TAILSCALE (as of 2026-09-16 per canonical-owner-decision-record.json)` with definition referencing canonical record and as-of date, per audit §4 U7 guidance (bind to ledger constant or state as-of).
- U8 fix: `ROLE-DESKS.md` now declares workspace navigation: `TH Finance` gated on `Finance Officer`, `TH Receipts` on five Auditor roles, all other Officer roles intentionally land on no workspace and reach work via desks + command Pages (deliberate, not accidental, to preserve A13 containment).

### OD-RD-3 — Page-level role gates

**Question:** 26 Pages (6 desks + 20 command pages) have no `page_for_role`; enforcement is server-side `require_desk_audience` with human-readable refusal. Safe, but a non-audience user gets mounted shell + red error rather than clean native refusal. Pin `page_for_role`?

**Owner answer:** **Keep current human-readable server gate, declare intended (RECOMMENDED)**

- Keep no `page_for_role`. Keep `require_desk_audience` which throws: "The {Title} is limited to the {Role} role. Ask a Course Owner or General Manager to review your role assignment if you expected access."
- Rationale: better UX than generic Frappe permission error, already tested in `tests/desk` and `test_role_desks.cjs`, and preserves human-readable guidance. Declared as intended in `ROLE-DESKS.md` § Workspace navigation + What is deliberately NOT here.
- Future: if owner wants clean native refusal, can be revisited as separate slice with fixture change + migration.

### OD-RD-4 — Request-key visibility (U4)

**Question:** Originally every guided dialog showed editable "Request key" with "keep this exact value when retrying" — implementation exposure. Now fixed to read-only pre-filled "Request reference (filled in for you)".

**Owner answer:** **Keep read-only Request reference (RECOMMENDED)**

- Current implementation: `th_role_desks.js` field `{fieldname: "request_key", label: "Request reference (filled in for you)", fieldtype: "Data", reqd: 1, read_only: 1, default: newRequestKey(), description: "Reuse this exact value if you must retry the same request after a connection error."}`
- Idempotency intact, auditability preserved (value visible for retry), not editable (fixes U4). Matches Node live-dialog `read_only` pin in `test_role_desks.cjs`.

## Final desk readiness claim

With both hosted gates green on `31e6add` and owner ratification of OD-RD-1..4 above:

- Six role desks are **qualified on the real HTTP pipeline** (audience loads, negatives, lifecycle truth, U1 prefills, D6/OD-RD-1 chain over real HTTP).
- Offline guards and hosted evidence can no longer diverge: desk projection field allow-lists are pinned against `pinned_schema.json` (17 doctypes incl. User Permission) and consumed by `DeskSchemaFidelityTests`; `get_all`/`count` stub fails closed on unlisted fields; whitelist-marking stub ensures `frappe.whitelist` is not a no-op in tests; client-string→endpoint exposure tie-out ensures every `toefl_house.desk.<module>.work` named in JS resolves to a whitelisted endpoint.
- Production remains **REJECT** — SEC-DEPS-01 and synthetic-only activation unchanged. No D8 gate flipped by this ratification.
- Remaining owner decisions: D1, D4, D5, D6a/b, D11 remain as per `OWNER-DECISIONS.md`. OD-RD-1..4 are now CLOSED per this ratification.

Evidence packet for OD-RD-1 is the hosted placement report `45a698dcd6ea5e2341eddbf335e68c5b57ea99c52d8bb10d9289a04265b49cdf` (check-run `105668996321`) plus owned-suite `35365044995`, plus local desk suite 53 tests.

Stamped: 2026-09-18
