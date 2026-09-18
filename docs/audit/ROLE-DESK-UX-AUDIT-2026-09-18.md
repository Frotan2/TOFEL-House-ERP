# Role Desk / UX Qualification — Audit Plan and Findings (2026-09-18)

Status: **Phase 1 — plan and findings only. No product code was changed by this
audit phase.** Implementation waits for the owner's review of this document.
Production remains **REJECT** (SEC-DEPS-01 and the synthetic-activation stop
stay in force; nothing here relaxes them).

Companion records: `docs/product/ROLE-DESKS.md` (the binding desk contract),
`docs/audit/ERP-SEMANTIC-AUDIT-2026-09-18.md`,
`docs/audit/FEE-HANDOFF-AUDIT-2026-09-18.md` (closed same-day, 569/569 hosted
on run 35344291259; tip re-verified 35345838831).

Method: static trace of every desk projection, its client renderer
(`public/js/th_role_desks.js`), the guided-action endpoints, the page/workspace
role data, the projection allow-list, the scope helper, and the in-process test
suite — cross-checked against the **pinned native authorities** (frappe
`988e54f3c4c2`, education `93bc70757533`, erpnext `4048fb70…`) that the hosted
bench builds. No runtime claim below is asserted as proven; each carries the
hosted check that will prove it in Phase 2.

## 1. What the six desks are, and the contract they must keep

A desk is a read-only projection gated on its audience, plus guided-action
prefills into the **existing guarded commands**. It owns no writes, no status
enum of its own (except the six governed TH config doctypes), no metrics
without a stated definition, and no second authority over Student, Student
Group, Fees, Payment, Attendance, Employee/Instructor or permissions. Every
desk verified here upholds that: all six modules only read through the
allow-listed `project_rows`/`project_count` and embed actions only when the
viewer holds the acting role. **The audit found zero competing-authority
violations.** The failures below are reachability, schema-fidelity and journey
completeness failures, not architecture failures.

## 2. Each role's critical workflows (as designed, with desk coverage)

| Role | Desk | Critical workflow | Desks covers |
| --- | --- | --- | --- |
| Reception | th-reception-desk | Walk-in lookup → stage of every open person → hand the next actor | yes, with defects D4 and U3 |
| Admission chain (Officer→Reviewer→Approver) | via Reception/Academic | record → review → decide → student created | partial (actions live on command pages; desks only narrate) |
| Placement chain (Publisher→Releaser) | Academic desk queue | finalize → release decision → admission hand-off | yes (release is guided) |
| Academic Manager | th-academic-desk | cohorts, today's sessions, teaching assignments, waiting queues | queues yes; class lifecycle control **absent** (D5) |
| Finance Manager / Officer | th-finance-desk | today's collections → receivables → unbilled enrollments → corrections | yes, the most complete desk; plan-matching defect U9 and unqualified fees-correction legs (E4) |
| General Manager | th-operations-desk | whole funnel, exceptions, role coverage, cross-desk links | yes; fees corrections render anonymous (D6) |
| Course Owner | th-owner-cockpit + th-academic-setup | see business state and control global config (programs/levels/durations/fee plans/discounts) without touching raw native forms | cockpit ok; **setup plane entirely unreachable (D1)** |

## 3. Expected user journeys (the ones Phase 2 must walk end to end)

1. **Walk-in to admission flow** (Reception): search a name → see the true
   funnel stage with a valid next-step; if none matches, be told how to start
   placement. Today: lookup works, but the student branch asserts "no active
   Student Group" from a hardcoded flag (D4), and an applicant with no
   released placement gets a next-step sentence with no action and no
   explanation of who starts placement (UX gap U3).
2. **Admitted learner to first class** (Academic Manager): submitted
   enrollment → create class → Planned→Active → schedule sessions → record
   attendance. Today every hop exists as a guarded command, but the academic
   desk narrates all of it with `action: None` and points at "the Teaching
   Scheduling page" by name (U1); the cohort facts it shows come from a
   column that does not exist (D2) and mislabels lifecycle anyway (D3).
3. **Enrollment to first fee to receipt** (Finance): awaiting-billing row →
   guided `issue_tuition_fees` with owner-plan prefill → outstanding queue →
   native payment. Today correct — except the desk calls a *submitted* (still
   issuable) fee plan "not configured" and blames the Owner (U9).
4. **Correction round trip** (Finance Officer → policy approver): request →
   approve/deny → native reversal. Invoice side is hosted-qualified; the
   fees side is fully implemented, desk-wired and **never executed on a real
   bench** (E4).
5. **Owner configuration without technical setup**: open Academic Setup →
   define program/level/duration/fee plan/discount from guided dialogs.
   Today the page mounts and its one endpoint is rejected — the Owner is
   pushed back to raw native forms, the exact thing the contract forbids (D1).
6. **GM branch awareness**: see funnel + exceptions across branches; scope
   by User Permission where the records have the field. Branch scoping
   silently no-ops for classes (branch lives on `th_branch`), which is an
   undeclared policy, not a crash (P1).

## 4. Findings, classified

Categories per the mission: (a) real product defect, (b) UX weakness, (c)
missing business policy, (d) deferred owner decision, (e) production/infra
blocker. Line references are current at commit `322f581`.

### (a) Real product defects

- **D1 — Academic Setup desk cannot load.** `desk/setup.py:53` defines
  `work()` without `@frappe.whitelist(methods=["GET","POST"])` while the
  client calls `toefl_house.desk.setup.work` via `frappe.call`
  (`th_role_desks.js:49`); no `override_whitelisted_methods` entry exists.
  On a real bench the Course Owner's entire configuration plane fails closed
  at the API layer. Every existing test calls the function in-process, where
  the stub turns `frappe.whitelist` into a no-op — structurally blind.
- **D2 — Three desks filter/project a column the pinned authority does not
  have.** `desk/academic.py:104-107`, `desk/operations.py:125-128` and
  `desk/owner.py:65-68` select field `active` and filter `{"active": 1}` on
  Student Group; the pinned education doctype has no `active` field (only
  `disabled`, default 0 — verified against `student_group.json` at
  `93bc70757533`), and our fixtures add only seven `th_*` fields. On MariaDB
  this is an Unknown-column error: the Academic Desk, the GM Desk and the
  Owner Cockpit all fail to load. The desk test world is a dict fixture that
  projects whatever fields are asked — schema fiction invisible to every
  current check.
- **D3 — Lifecycle mislabeled as the native flag.** Even with the column
  fixed to `disabled=0`, the desks' "Active cohorts" would include Planned,
  Completed and Cancelled classes: `create_student_group` writes only
  `th_class_status="Planned"` and `transition_class` only maintains
  `th_class_status`; nothing maintains a boolean anyone could call active.
  The academic projection allow-list excludes `th_class_status` entirely
  (`desk/__init__.py:110-113`), so the desk cannot show the truth it should.
  Fix = project the status and derive the tiles from it.
- **D4 — Reception lookup states a fabricated fact.** `desk/reception.py:276`
  calls `lifecycle.enrollment_stage(bool(enrollment), False)` — the cohort
  flag is hardcoded because no Student Group query exists in the reception
  projection — so an enrolled student with a class is told "Enrolled, no
  class" with the definition "no active Student Group exists for this
  cohort".
- **D5 — No guided path for the one gate the Academic Manager must
  operate.** `lifecycle.py` contains no stage whose command is
  `transition_class`, and `academic.py:187/202/215` set `action: None` on
  cohorts, sessions and assignments, while session scheduling is refused for
  non-Active classes (§12 guard, hosted-proven). The desk narrates a gate it
  never helps open.
- **D6 — GM desk renders fees corrections anonymously.** The management
  projection of TH Correction Request selects `sales_invoice` only
  (`desk/operations.py`); a fees-targeted request (whose `sales_invoice` is
  empty) shows no identifiable target. The finance desk projects both legs
  correctly; the gap is management-only.

### (b) UX weaknesses

- **U1 — Journey hand-offs are prose, not affordance.**
  Admission→Enrollment→class→first-fee requires three surfaces and page-name
  knowledge ("open the Teaching Scheduling page"). Keep the one-round-trip
  rule for actions, but the contract should say which desk carries the button
  for each lifecycle edge; proposal: the academic desk gets guided
  `create_student_group`, `transition_class`, `schedule_session` (existing
  commands, no new endpoints).
- **U2 — Terminology leaks implementation names.** Academic desk user-facing
  strings: "Course Schedule has no sessions for today", "No active Student
  Group exists yet", "Submitted Program Enrollments whose … have no active
  Student Group" — violates ROLE-DESKS's own staff-language rule and
  `lifecycle.py`'s "never a DocType name".
- **U3 — The no-decision applicant dead end.** Reception shows "Open the
  admission decision" with no action for applicants whose placement result
  was never released (correctly — `create_admission` requires it), but
  nothing names who releases or how. One sentence of hand-off guidance
  closes it.
- **U4 — Request-key exposure.** Every guided dialog shows a required
  "Request key" field pre-filled with a generated value and instructs the
  user to "keep this exact value when retrying" (`th_role_desks.js`,
  `openGuidedAction`). The idempotency seam is already generated in JS; the
  field is implementation exposure. Keep the value, hide the input.
- **U5 — Page shells open for non-audience users.** None of the 26 Page
  doctypes (6 desks + 20 command pages) sets `page_for_role`; role
  enforcement is server-side (`require_desk_audience`, human-readable
  refusal) plus the registry's link list — safe, but a Reception user
  searching "Finance Desk" gets a mounted page and a red error rather than a
  clean refusal. Decision needed on pinning page roles (OD-RD-3).
- **U6 — Owner cockpit stage facts for the oldest admission read
  `accepted`/`native_student` from a projection that never selects them
  (`desk/owner.py`, the ADMISSION field list), so an already-created student
  is still narrated as "awaiting student creation".**
- **U7 — Release-posture descriptive fact is stale by construction.**
  `desk/owner.py:36-53` hard-codes `Deployment: LOCAL_SERVER_TAILSCALE`
  while the canonical ledger now records Caddy-TLS. Fail-closed posture is
  right; a descriptive line frozen at a past state is wrong. Bind it to the
  ledger constant or state "as of <date>" inline.
- **U8 — Workspaces gate on Auditor roles only.** `th-finance` and
  `th-receipts` workspaces list Auditor roles in their `roles` block while
  the Officer roles that do the work land on no workspace (they reach pages
  via desks). Acceptable, but should be declared, not accidental.
- **U9 — Fee-plan guidance contradicts the command it guides.** Both the
  finance desk (`billing_guidance`, `desk/finance.py`) and the setup desk
  readiness facts treat a fee plan as "configured" only when the native Fee
  Structure is a draft (`docstatus == 0`), while `issue_tuition_fees`
  accepts a submitted structure too. An Owner who submits the plan (normal
  cautious behaviour, encouraged by native UX) is told "No fee plan is
  configured … the Course Owner completes it in Academic Setup", pointing at
  the wrong owner and the wrong blocker while billing could proceed. Desk
  promise and command acceptance must be one rule.
### (c) Missing business policy (underspecified, no code answer)

- **P1 — Branch scope of desks is undeclared.** `_apply_scope` applies User
  Permissions on Company (and a native `branch` field where the doctype has
  one); Student Group carries branch only as `th_branch`, so a
  branch-scoped GM/manager still sees every branch's classes. "GM operates
  across branches" is satisfied; "per existing scope rules" is partially
  honored — silently. The contract should state: desks are company-scoped by
  native permission, and branch filtering of class records is deliberately
  not performed in v1 (or it is added — owner call).
- **P2 — Owner cockpit carries no money-exposure facts at all** (no
  outstanding total, no corrections count) while the ROLE-DESKS contract
  promises "what changed". Finance-desk facts exist; owner-level aggregation
  policy is simply absent. Deliberate? Record it.
- **P3 — No desk-side staleness contract.** "Today" tiles read the server
  date at load time; a desk left open overnight shows yesterday's truth
  under a "Today" label. The v1 answer may be "reload or nothing", but it
  must be said.

### (d) Deferred owner decisions (recorded here, implemented by none)

- **OD-RD-1 — Fees-side correction ratification.** Per E4, the owner must
  ratify this surface (with the hosted qualification added in Phase 2) or
  order the wiring unwired; the code today is neither fully evidenced nor
  formally accepted.
- **OD-RD-2 — Phase-2 ordering.** D1 is a one-line, unarguable fix; whether
  the D2/D3/D4 cohort-fidelity patch or the D6 guidance rule runs first is
  an owner call (this plan proposes D1 → D2/D3/D4 → U9 → E4-qualification →
  U-series).
- **OD-RD-3 — Page-level role gates.** Pin `page_for_role` on all 26 pages
  to their server-side audience (clean native refusal instead of mounted
  shell + error — U5), or declare the current pattern intended.
- **OD-RD-4 — Request-key visibility** (U4): hide the input, keep the
  generated value, or keep it shown for auditability.

### (e) Production / infra blockers (unchanged, restated)

- **E1 — SEC-DEPS-01** upstream dependency-audit failure: production stays
  REJECT; nothing in this audit changes it.
- **E2 — Synthetic-activation stop**: every command behind a desk action
  remains confined to isolated synthetic sites until owner authorization;
  desk reads are exempt only because they mutate nothing.
- **E3 — Qualification transport**: the only real bench is the GitHub-hosted
  runner; every desk-runtime claim below is therefore written as a hosted
  check, not a local one.
- **E4 — Fees-side corrections are wired into the product without hosted
  qualification.** `request/approve/deny_fees_correction` exist with full
  OD-CP-2-B semantics (`finance/corrections.py:215-314`: full-amount only
  inside the window, dual key, native `fee_doc.cancel()` as the money
  artifact; `security.py:156-162` confines the Fees guard so the cancel is
  legal only inside the approve context), the finance desk embeds the guided
  "Approve correction" for them (`desk/finance.py:80-86`), and the client
  has dialogs for all three. `tools/placement/native_checks.py` contains no
  check that touches any of them. Money-adjacent code shipped ahead of its
  hosted qualification.

## 5. Runtime / browser checks required (Phase 2, hosted)

1. **Desk-load over HTTP per audience**: for each of the six surfaces, log in
   as an enabled synthetic user holding the desk role and execute the exact
   endpoint the client names (`toefl_house.desk.<module>.work` /
   `owner.cockpit`) through the real request pipeline (whitelist enforcement
   included). Success = HTTP 200 + expected section ids. This is the check D1
   would have failed and no current test can run.
2. **MariaDB column reality**: assert every desk projection's field/filter
   names exist — one `SELECT <fields> FROM tabStudent Group`-style prepared
   read per projection (or `frappe.get_meta` diff against the projection
   allow-lists). Proves D2 fixed and prevents recurrence class-wide.
3. **Cohort fidelity**: create a class via `create_student_group` (Planned) →
   desk lists it with lifecycle status, not "active"; `transition_class` →
   Active → tile follows; Cancel → leaves the waiting-queue math correct.
4. **Reception truth**: lookup a student with a cohort → stage reflects the
   real class; without one → the "no class" definition is true.
5. **Correction round trip, fees side**: policy active → request (full
   amount, in window) → approve as policy approver → `fee_doc.docstatus==2`,
   GL receivable reversed, `refunded_total` equals the fee; audit that the
   desk's guided approve endpoint resolves and posts.
6. **Billing-guidance vs. reality**: submitted Fee Structure with components →
   awaiting-billing row offers the guided issuance (today it says "no plan"),
   and `issue_tuition_fees` succeeds with that structure — desk promise =
   command acceptance, identical rule.
7. **Escape & render audit**: every user-facing string in every desk payload
   contains no `DocType`-casing token; guided dialog has no editable
   implementation field (after U4).
8. **Owner cockpit posture lines match the canonical ledger values at run
   time (or carry the as-of date).**

## 6. Negative / permission checks (hosted, deliberate denials)

- Administrator, Guest, disabled user, and a valid user *without* the desk
  role each receive the human fail-closed refusal from every desk endpoint
  (4 users × 6 endpoints), and `available()` lists exactly the permitted
  desks — already tested in-process; re-run over HTTP.
- Wrong-role command attempt: Finance Manager calling `approve_fees_correction`
  is denied by KIND_ROLES; the policy approver requirement stays dual-key
  (Finance Officer who is not the configured approver is denied).
- Fees containment while un-activated: outside a finance command, direct
  `fee.cancel()` remains denied (regression pin from the fee mission).
- Non-owner writes to `th_class_status` stay denied; desk code gains no new
  write path — grep gate: `desk/` still contains no `db_set|insert|save|cancel|
  delete` beyond allow-listed reads (exists in `tests/desk`; keep).
- A Branch User Permission must not *crash* any desk (P1's chosen answer —
  whatever it is — gets a positive and a negative test).
- Page visibility: if OD-RD-3 pins roles, assert a Reception user gets a
  permission refusal (not a rendered shell) for `th-finance-desk`.

## 7. Success criteria

1. All six desk payloads load over HTTP for their audience on the hosted
   bench, with run id recorded; zero schema-fiction fields (check 5.2 green).
2. Every class fact a desk states is derived from `th_class_status` (plus
   native `disabled`), never from a flag nobody maintains; reception cohort
   claims are true; a Cancelled class is invisible to "awaiting a cohort"
   math and visible as cancelled.
3. Admission→Enrollment→class→session→fee is walkable on desks with guided
   actions only onto existing guarded commands — **no new doctype, no new
   endpoint semantics, no second authority** (contract grep gate stays green).
4. Desk guidance and command acceptance agree everywhere (one plan-matching
   rule for fee plans, shared helper).
5. No user-facing string names a DocType; no business dialog demands
   developer knowledge (terminology and request-key checks).
6. Fees corrections are either hosted-qualified with OD-RD-1 ratified or the
   wiring is reverted — no half-evidenced money path survives.
7. The desk test world mirrors pinned native schema (field lists frozen from
   the pinned doctypes), so a projected-or-filtered column that does not
   exist fails the suite — the recurrence guard that was missing.
8. Full-tree suite green (was 829) and the Owned qualification CI green on the
   tip sha; production posture remains REJECT with the ledger updated to point
   here.

## 8. Proposed execution order (Phase 2, after owner review)

1. **D1 whitelist + §7.7 test-class fix first** (two small, unarguable patches;
   unblocks the Owner entirely and immediately hardens the harness).
2. **D2+D3+D4 cohort fidelity as one coordinated patch** (projection fields,
   filters, tile math, reception lookup query) + 5.2/5.3/5.4 checks.
3. **D6 + U6 small data-fidelity fixes** (fees leg in management
   projection; owner attention flags selected).
4. **U9 plan-matching rule** shared between finance and setup desks + 5.6.
5. **U1 journey affordances** (guided `create_student_group` /
   `transition_class` / `schedule_session` on the academic desk; U3 hand-off
   sentence) — commands already exist; zero new authority.
6. **U2/U4/U5/U7 text & surface polish**, subject to OD-RD-3/4 decisions.
7. **OD-RD-1 handling**: hosted-qualify the fees-correction round trip with
   the owner's ratification note, or unwire. Then full hosted re-run, ledger
   and ROLE-DESKS updates, and this document gains an execution ledger.
8. **P1–P3 answered in the contract doc** (as declarations, not code) unless
   the owner directs otherwise.

## 9. What the audit deliberately did NOT find (protection list)

No desk writes; no parallel ledgers or enums; money facts are native numbers
with native docstatus; scope is native User Permission; guided actions embed
only for role-holders with fresh idempotency keys and refusal-free buttons;
escaping and forbidden-primitive client tests exist; the six-desk registry,
titles and role pins match `security.py`'s command roles. Phase 2 must keep
every line of this list true.

## 10. Phase 2 execution evidence (2026-09-18)

Ordered per §8. Offline suites were green at every commit; hosted
qualification per §5/§6 is recorded with exact run IDs.

| Step | Findings | Commits | Offline anchor | Hosted evidence |
| --- | --- | --- | --- | --- |
| 1 | D1a (setup.work whitelist), D1b (`toefl_house.desk.available` at all call sites) + harness hardening (whitelist-marking stub, client-string→endpoint exposure tie-out, pinned-schema fail-closed `get_all`/`count`) | `5453bce` | `DeskReadEndpointExposureTests`; `test_role_desks.cjs` whitelist mirror; **mutation-checked**: removing the decorator fails the suite | owned-suite `35356041526` ✅ (ruff 0.16.8 + 847 tests + all 4 Node suites) |
| 2 | D2/D3/D4 cohort fidelity (real Student Group schema; `th_class_status` canonical; Reception derives from open classes; no duplicate `active` authority) | `5453bce` | `pinned_schema.json` (17 doctypes incl. User Permission) consumed by `DeskSchemaFidelityTests` + world tests; **mutation-checked**: restoring the phantom `active` query fails | same owned-suite ✅ |
| 3 | D6 (correction rows name the real fees-or-invoice target) + U9 (issuance rule = desk guidance: non-cancelled plan with components, draft or submitted; `Submitted (locked)` honesty) | `924a2ac` | `FinanceBillingGuidanceWorldTests` (7 cases incl. submitted-plan prefill, null-year match, cancelled refusal), `ManagementCorrectionsWorldTests`, configuration contract re-pinned | — |
| 4 | U1 affordances: Activate class (Planned), Schedule session (Active), Create class (unclassed intake), prefilled into the existing teaching commands; role-gated | `0b49e48` | `AcademicClassActionsWorldTests` (5 cases) + `GuidedEndpointRegistryTests` teaching signatures + Node signature diff via the `toefl_house.teaching` module map | — |
| 5 | U5 plain-language sweep; request key → read-only pre-filled "Request reference" (idempotency/audit intact) | `2019656` | `DeskPlainLanguageTests` (AST, dict **and** `section()` kwargs) + Node live-dialog `read_only` pin | hosted payload scan (see below) |
| 6 | P1 honored by filtering, never by crashing (declared answer pinned executable; nothing invented for P2/P3) | `4ea3ab0` | `DeskBranchScopeTests` with ledger-backed `get_meta` stub | — |
| 7 | Hosted desk qualification (audience loads, negatives, lifecycle truth, U1 prefills, D6/OD-RD-1 chain over real HTTP) | `53aae30`, fix `0c54bc2` | `tests.placement.test_native_check_arity` ✅ | placement-content `35356041546` **failed by design once**: the new `role-desk-hosted-qualification` check caught two stale finance `section(empty_body=…)` strings naming `Payment Entry`/`Program Enrollment` that the dict-only offline scan had missed (`report_sha256 593baf16…`). Fixed (`0c54bc2`) and the guard widened to `section()` kwargs, so the escape path is closed, not just the instance. GL-reversal assertion verified against pinned education `93bc70757533` `fees.py on_cancel` → `make_reverse_gl_entries`. |

### State of the re-runs — final: GREEN
The fix rode five hosted cycles, each surfacing the next true issue and
each fixed at its root (the point of §5/§6 being real, not decorative):

| Cycle (placement-content run) | On | Outcome |
| --- | --- | --- |
| `35356041546` | `53aae30` | fail — finance `section(empty_body=…)` still named `Payment Entry`/`Program Enrollment`; fixed in `64884ff` |
| `35359895735` | `82275fd` | fail — `available()` 403'd guests against its own documented empty-registry contract; fixed (`allow_guest=True`) in `82275fd`→`421c533` chain |
| `35362218310` | `421c533` | fail — the Reception class-truth check aimed at `work()` instead of `lookup()` (harness mis-aim); fixed in `421c533`→`ca9ac7f` |
| `35363856854` | `ca9ac7f` | fail — `Lock wait timeout`: the intentional partial-denial probe holds the fee row past savepoint rollback (InnoDB keeps those locks); fixed (explicit rollback before the worker's request; commit to re-snapshot after) in `31e6add` |
| `35365045006` | `31e6add` | **success** — 570 checks pass; check-run `105668996321`; report SHA-256 `45a698dcd6ea5e2341eddbf335e68c5b57ea99c52d8bb10d9289a04265b49cdf` |

Final gates on `31e6add`: owned-suite `35365044995` **success** (ruff
0.16.8, 847+ Python tests, all four Node suites) and placement-content
`35365045006` **success**, including the `role-desk-hosted-qualification`
observation recorded in the report: six audience loads 200,
guest/outsider/cross-audience denied, non-retargetable POST, payloads free
of doctype plumbing, `Class — Active` from the governed lifecycle,
lookup reads `Enrolled`, U1 prefills delivered per role, and the OD-RD-1
fees-correction chain end to end (target `EDU-FEE-2026-00001`, request
`ghph21s107`, replay-identical receipt, `gl_open_rows_after: 0`, desk row
named then cleared, denial keeps the fee, re-request after denial allowed).

**Foundation runtime validation** (`foundation-runtime.yml`) fails on every
recent SHA including pre-Phase-2 ones (`b83d118`, `10939bb`): it is the
documented SEC-DEPS-01 upstream-dependency hard stop, deliberately left
untouched by this mission and unchanged by it — production stays REJECT.

Desk-readiness for the six role desks is therefore **qualified on the real
HTTP pipeline**; OD-RD-1 ratification is now an owner decision informed by
green evidence — the evidence does not self-ratify.

### What the hosted failure proves
The §5 checks were not decoration: the first real-pipeline pass executed the
whitelist path, loaded all six desks for their audiences and reached the
fees-correction chain — and a scan stricter than anything previously wired
caught the residue. That is the harness-strengthening objective (make this
defect class visible) demonstrated on a live bench, catching what offline
dict-scan coverage had let through.
