# TOEFL House ERP — Native-first integration contracts

Status: binding engineering contract for the consolidated release candidate

Effective baseline: `c22b9979542c88a2cd179e179a91829d07a79a3a`

Authority: `docs/PRODUCT.md`, `docs/DECISIONS.md`, `docs/CONFIGURATION-PLANE.md`, and `docs/owner-decisions.json`

This document joins the existing features into one product. It does not authorize production, create an Owner policy, or make a deferred capability available. A successful unit test, a hosted Linux job, and a downloadable archive are different evidence classes and must not be interchanged.

## 1. System boundary

- The supported product is native Frappe Desk on ERPNext + Education + HRMS. It includes role-specific Desk Pages, standard DocTypes, Print Formats, and native reports.
- The complete pipeline is **Applicant → Placement → Admission → Enrollment → Schedule → Attendance → Assessment → Progression → Billing → Payment**. The current candidate implements and exercises the native subsets identified in `ACCEPTANCE-MATRIX.md`; Assessment/Progression remain deferred under D1.
- Public admission, student, guardian, and other portals are not built. A desk/API/POST-only endpoint is not a portal. Any portal implementation requires an explicit D4 revision and a separate security review.
- Owner-selected raw-to-derived reporting (D7) remains future scope. The candidate may expose source-owned native facts; it must not invent derived outcomes.
- No production, Owner-machine, staff-device, backup-drive, real-data, real-money, or real-payroll conclusion follows from synthetic hosted evidence.

## 2. Domain and data ownership

| Domain / fact | Exclusive authority | Owned custom carrier | Consumers may do | Consumers must not do |
|---|---|---|---|---|
| Applicants and native Students | Native Education records + `TH Applicant Intake`; `TH Placement Case` holds the testing journey | Intake, Placement Case, Attempt, Review, Decision | Read permitted facts; transition through owned commands | Create a second student master; infer admission from placement |
| Delivery, marking, and placement decision | `TH Placement Case` | Delivery, Assignment, Response, Marking, Review, Decision | Consume the published Placement Decision | Rewrite a sealed attempt/key or duplicate assessment authority |
| Admission | `TH Admission Application` and its native conversion adapter | Condition, Offer, Admission Decision, conversion | Create/reuse native Student only through conversion | Treat an offer as enrollment; create an enrollment before eligibility |
| Enrollment | `TH Program Enrollment`, `TH Course Enrollment`, `TH Enrollment Exit` | Roster and enrollment transition records | Reuse historical Program Enrollment; link intake and placement | Move financial ownership out of native ERPNext; delete history |
| Catalog / policy snapshots | Owned catalog plus versioned TH policies | Policy and version snapshot fields | Resolve the policy applicable at the business event | Apply a current default retroactively |
| Schedule / teaching group | Native Student Group + owned teaching assignment/roster adapters | TH Teaching Group/Session/Assignment carriers | Schedule only eligible active enrollment/roster members | Establish a parallel native Course Schedule master |
| Attendance | Native Student Attendance via owned command | TH attendance/correction records | Correct through the approved PIN/window path | Edit submitted attendance silently or write through a generic RPC |
| Assessment / Progression | Native Education only when D1 is revised | No enabled owned grading/progression engine | Preserve existing native historical outcomes | Activate PR #48 grade/portal scope or invent pass bands/next levels |
| Billing / tuition / placement fees | Native ERPNext Item, Price List, Sales Invoice, Payment Entry, GL, and Fees where native | TH billing links, calculation snapshots, correction requests | Bill an accepted offer/eligible enrollment using explicit policy | Create a custom ledger; bypass invoice/payment native posting |
| Book stock and sales | Native ERPNext Item, Bin, Stock Ledger Entry, Sales Invoice, GL | Native book-sale adapter and trace evidence | Sell/return books with cashier permissions and native stock update | Mix stock and tuition service lines in one invoice; maintain custom stock balances |
| Teacher compensation | Native Employee, Attendance, Timesheet, Additional Salary, HRMS payroll | TH Instructor Contract and TH Teaching Assignment | Calculate explicit contract/session facts into the native payroll input path | Post Salary Slip/payroll without explicit configured terms; store a second payable ledger |
| Configuration | Authorized Settings/configuration commands and versioned records | `TH System Settings`, `TH Alerting Policy`, domain policy records | Change only policy-manager-owned fields through the Desk | Write business configuration in hidden constants, UI-local state, or provider stubs |
| Notifications | `TH Alerting Policy` is the only current policy carrier | Existing policy only; no runtime consumer | Preserve configuration and design a future adapter after approval | Claim email/SMS delivery, add provider secrets in records, or create a parallel policy plane |
| Reporting | Source-owned native and TH records | Existing native reports/registers | Read with source-domain permissions and show provenance | Invent derived risk, ranking, next-level, tax, payroll, or reconciliation outcomes |
| Security | `apps/foundation_security`, owned API guards, and native permissions | Deny-by-default overlays and test fixtures | Deny first, audit denials, minimize disclosure | Grant access by hidden UI alone; trust caller-supplied role/host/issuer assertions |

### Cross-domain invariants

1. **No shadow masters or ledgers.** Identity, Student, Employee, invoice, payment, stock, GL, payroll, attendance, and assessment facts remain native where ERPNext/Education/HRMS already owns them.
2. **One transition writer.** A business state is changed only by its owning command. Readers and integrations cannot update the same state directly.
3. **Eligibility is checked again at the transition.** A prior offer, roster row, invoice, or browser result is not authority for a later command.
4. **Branch and Company are explicit.** Finance and compensation require their native Company context; branch-scoped academic operations use the authorized branch rule. No global default is silently substituted.
5. **History is append/correct, not rewrite.** Submitted native documents and versioned policy snapshots are never destructively rewritten to make a new rule fit an old outcome.
6. **Synthetic fixtures are segregated.** Test identities use synthetic markers and cannot be interpreted as real applicants, students, staff, money, consent, or payroll approval.

## 3. Lifecycle contracts

### Applicant → Placement → Admission

- Intake creates/reuses the allowed native identity only through the owned adapter. Returning-student reuse preserves history; it does not clone a Student.
- Placement allocation, delivery, response, marking, review, and decision are separate commands with separate roles and sealed boundaries.
- Admission references an actual eligible placement decision where required. Conditional admission records explicit conditions; conversion checks their satisfaction again.
- Conversion is atomic from the product’s perspective: native Student creation/reuse, intake linkage, and admission conversion either complete together or the transaction fails. A consumed idempotency response is returned without creating another Student.

### Admission → Enrollment → Schedule → Attendance

- Enrollment requires the applicable admission/eligibility state, catalog linkage, intake gate, and policy snapshot.
- Program Enrollment may be reused only for the same authorized historical student/program context; Course Enrollment and roster membership are linked to that native context.
- Teaching sessions and schedules accept only eligible active roster members. Adding, moving, or disabling a roster member does not rewrite past attendance.
- D5 selects the native basic calendar/lifecycle and defers repeat, transfer and withdrawal policy. Any existing exit mechanism remains fail-closed until an explicit superseding Owner decision authorizes the action.
- Attendance writes through the native adapter. Corrections require the configured correction authority, PIN/window, and audit record; cancellation/rollback tests must leave no partial native rows.

### Assessment → Progression

- D1 currently defers grading, progression, and credits. There is no release candidate contract that permits a custom grading result, pass band, next level, guardian grade view, or progression command.
- A future D1 revision must name the native Education DocTypes, grading-period/course scope, policy snapshot, result immutability, and progression authority before code or fixtures are added.
- Historical native assessment results remain untouched. No migration may translate them using invented thresholds.

### Enrollment → Billing → Payment

- Billing resolves the effective dated fee policy and native Item/Price List. No amount, discount, refund, tax, due date, or stock threshold is invented by integration code.
- A tuition/placement line and a stock Item cannot share the custom book-sale invoice path. Native stock update must be enabled for book sales.
- Sales Invoice, Payment Entry, Stock Ledger Entry, and GL Entry are the financial evidence. A TH record is a linkage/snapshot, not a replacement ledger.
- Payment settles the actual native invoice through the approved manual native process. D6a supplies no tax configuration; D6b selects no online payment gateway. Neither may be inferred or enabled by integration code.
- Returns/restock/credit/refund follow native reversal documents and preserve row-level direction and reconciliation.
- Corrections use the D3 finance correction request, separation-of-duties, window, and native reversal/reposting path. Exact refund/partial-refund/Fees terms still require explicit policy. Generic cancel/amend/RPC shortcuts remain denied.

### Compensation and payroll

- Instructor Contract and Teaching Assignment are facts/inputs, not proof of payment.
- Calculation requires an active dated contract, eligible sessions/assignments, explicit rates and native Salary Components, and the configured adjustment-posting policy.
- The only payroll input is native Additional Salary. Employee linkage, component type, payroll date, recurrence/pro-ration semantics, and amount must be verified before posting.
- Salary Slip, Payroll Entry, bank/payment, statutory, and payable outcomes remain native HRMS authority. Unsupplied real rates/terms are BLOCKED, not defaulted. Synthetic calculation evidence is not real payroll acceptance.

### Reporting

- Every report/register names its source records, as-of date, branch/company scope, and native/custom authority.
- A derived result cannot be released by relabelling a query as a report. D7 requires Owner-defined inputs, formula, rounding, effective dates, permissions, and historical treatment.
- Financial and payroll exports are sensitive native data; role-desk visibility is not export permission.

## 4. Configuration plane

- Business behavior is managed in authorized Settings interfaces by the designated policy manager. Source constants are for fail-closed validation and structural limits, not hidden institutional policy.
- Policy records are versioned, dated, branch/company-scoped where applicable, and auditable. Commands capture the exact version used.
- `TH Alerting Policy` remains the only notification-policy authority. D4 defers portal/advanced identity policy; notification delivery is not enabled merely because a policy row exists.
- Owner-controlled checkboxes/radios are the only supported no-code choices where a choice exists. No policy may be embedded only in JavaScript, a Desk Page label, a provider stub, or an operator’s memory.
- Secret material belongs in the approved native secret/configuration mechanism with access control and redaction. It is never placed in fixtures, release notes, archives, logs, or source.
- Missing policy fails closed with a actionable configuration message. It never falls back to zero, an arbitrary percentage, a permissive role, or a made-up threshold.

## 5. API and transaction contract

All new owned RPCs follow `toefl_house.api` and `toefl_house.transactions` rather than creating a parallel executor.

| Concern | Required behavior |
|---|---|
| Transport | Browser mutations use POST with Frappe CSRF protection. GET/HEAD are read-only. Deny-by-default hooks remain authoritative. |
| Request identity | Use the authenticated Frappe user and server-side roles. Never accept a caller-supplied actor, role, company, branch, host, or issuer as proof. |
| Idempotency | `request_key` is a safe 16–96 character key. Bind it to command kind, actor, normalized payload, and result. A different payload with the same key is rejected. |
| Execution | Authorize, lock the applicable aggregate/policy, validate current state, perform owned/native writes, and commit as one retried unit. Duplicate/serialization retries do not duplicate native documents. |
| Replay | Return the consumed stored response. A process-local cache is not durable idempotency. |
| Failure | Expected validation/permission/concurrency failures have a safe message and no partial commit. Unexpected errors are logged with correlation but not secrets or unnecessary PII. |
| Native writes | Use the native adapter and native document submission/payment/stock methods. Direct SQL/background writes do not bypass validation, permissions, or audit. |
| Response | Return native/owned names, version/policy references, and explicit state. Do not return `delivered`, `persisted`, `posted`, or `paid` unless the corresponding durable native fact exists. |
| Permissions | Check command role plus record/branch/company scope. Denials are tested through real HTTP and direct/RPC paths, including stale sessions and role revocation. |
| UI | Desk controls call the same command; hidden buttons are usability, not authorization. No business truth exists only in browser memory. |

## 6. Events and integration jobs

The current candidate does not have an owned realtime event bus or a notification delivery runtime. The following is the compatibility contract for a future approved consumer, not a claim that these events are already emitted:

```text
event_id              durable unique identifier; retries retain it
event_type            versioned, e.g. enrollment.completed.v1
occurred_at           UTC timestamp of the committed business transition
source                 {doctype, name, modified, branch/company as applicable}
policy_snapshot       immutable version/hash used by the transition
payload                minimum non-secret facts required by the consumer
synthetic              true for every synthetic qualification event
```

- An event becomes visible only after the source transaction commits. A consumer must be idempotent by `event_id` and must not change the source-owned outcome.
- Notification jobs must resolve `TH Alerting Policy`, recipient consent/authority, template escaping, provider response, and durable attempt state. Regex validation or an in-memory list is not delivery evidence.
- Financial, payroll, assessment, and guardian payloads require separate minimization/authorization review. A generic placement/admission event must not expose those domains by default.
- No event handler may write GL, stock, Salary Slip, Assessment Result, or a second business master as a side effect.
- Owned realtime subscriptions are intentionally pinned off in Desk Pages; foundation bootstrap/runtime behavior is tested separately.

## 7. Schema and migration contract

1. Prefer additive changes. A rename/type change uses expand → backfill → dual-read verification → contract, with a separately reviewed cleanup release.
2. Patches are idempotent, ordered, resumable where possible, and tested on a fresh site and a migrated/restored site. Re-running migrate is required qualification.
3. Never drop a DocType/field/table or delete rows based only on a developer’s assumption. A destructive cleanup needs a census, backup, proven-unused evidence, and explicit review. The historical unused-carrier cleanup patch is not blanket permission for future drops.
4. Do not rewrite submitted Sales Invoice, Payment Entry, GL Entry, Stock Ledger Entry, Salary Slip, Student Attendance, Assessment Result, or published policy/decision history.
5. Preserve policy snapshots and historical resolver behavior. Qualification must include an old-date case before and after migration and service restart.
6. Back up database and public/private files with the supported tool, verify hashes, restore to an isolated site, run migrations twice, verify policy/native facts, restart the web service, and repeat HTTP/native checks.
7. A backup is not recovery evidence. A hosted isolated restore is not Owner recovery evidence. Owner backup drive, keys, disks, and production configuration are never touched by the integration agent.
8. There is no automatic production downgrade or uninstall path. Do not uninstall the app to resolve a failed migration.

## 8. Qualification and acceptance

A change is integrated only when all applicable evidence exists for its exact full head SHA:

- Owned Python/unit/contract suite and static architectural guards.
- Foundation runtime, real-site security/browser checks, dependency pins, and UI contracts.
- Native Frappe/MariaDB/Redis/HTTP lifecycle, migration, failure, permission, financial, stock, compensation, reporting, restore, and restart checks affected by the change.
- Product Linux/amd64 image build/run and browser/API smoke; package image labels and layer digests must match the source SHA.
- Windows customer package build/signature/SQLite/backup/update/static smoke where applicable. This remains hosted evidence, not real Windows acceptance.
- Independent human review with no unresolved correctness/security finding; GitHub green checks alone are not approval.

The evidence collector must compare the workflow’s source commit, not just its branch name, check conclusion, display SHA, or an artifact from another run. Missing, stale, expired, partial, or superseded evidence fails closed.

## 9. Exclusive engineering ownership

These are integration-review ownership rules, not a substitute for repository access control. The integration lead arbitrates shared files and may reject an otherwise green PR that violates them.

| Owner | Exclusive scope | Required coordination |
|---|---|---|
| Integration lead / release engineer | `docs/engineering/INTEGRATION-*`, `ACCEPTANCE-MATRIX.md`, `RELEASE-CANDIDATE.md`; `tools/release/`; customer allowlist; release tags/evidence | Only this owner creates the consolidated RC, changes gate policy, or publishes evidence. |
| Integration lead + affected domain reviewer | `apps/toefl_house/toefl_house/hooks.py`, `permissions.py`, `fixtures/`, role/workspace JSON, `api.py`, `transactions.py`, shared tests/fixtures, root dependency manifests, `.github/workflows/` | Feature agents propose changes in their PR; no unrelated agent may concurrently rewrite these files. Exact-head integration review is mandatory. |
| Academic/admissions/enrollment/teaching/finance domain owners | Their domain modules, DocTypes, Desk modules, and focused tests | Cross-domain writes go through the target domain adapter; no shared policy defaults. |
| Foundation/security owner | `apps/foundation_security/`, `tools/foundation/secure_*`, security/browser evidence and remediations | Product agents do not weaken a denial or sanitizer to make a feature pass. |
| Native qualification owner | `tools/native/`, disposable native fixtures, restore/restart verifiers | New lifecycle claims require executed receipts and final-report coverage, not merely a unit test name. |
| Windows/package owner | `product/windows/`, `product/` runtime/recovery/package scripts | Must preserve prebuilt-image, no-real-data, and REJECT guards; physical Owner acceptance stays separate. |
| PR #46 updater owner (held) | `product/update_engine.py`, `product/update_entrypoint.sh`, `product/updates/`, updater UI/tests/docs | **Exclusive while held.** Do not merge, cherry-pick, or create a competing updater implementation without explicit authorization. |
| PR #48 notification/portal author (changes required) | Only the proposed PR branch after D4/policy/security redesign | Excluded from this RC. No merge/cherry-pick; no parallel notification policy, portal, provider, or configuration plane on main. |

If two PRs need the same shared file, the integration lead sequences them. The later PR rebases and reruns all exact-head checks. Reviewers must inspect semantic conflicts even when Git merges textually cleanly.

## 10. Merge and release control

1. Confirm scope against this contract, canonical domain decisions D1–D11, and the separate D8 business-requirements record; identify all shared files and downstream gates.
2. Obtain independent review. Same-author comments are useful records but are not formal GitHub approval; do not describe them as such.
3. Require green checks on the exact full head SHA after the last change. A green base branch or earlier head is insufficient.
4. Merge with the repository’s approved method, then run/pin main qualification on the resulting exact SHA.
5. Preserve PR #46’s explicit hold and all NO-GO boundaries. PRs #48–#51 remain excluded until their recorded policy, security, correctness and native-evidence blockers are resolved and each corrected exact head is independently approved; a green earlier head or same-author comment is insufficient.
6. Build the versioned package only from the accepted full SHA and a matching `v*` tag. Record the Product-image run, four gate runs, artifact digest, package SHA-256, image digest, and release URL.
7. Publish only the engineering RC. Production remains REJECT until real Owner Windows, recovery, staff, cashier/stock, download/install, payroll/configuration, and Owner approvals are actually evidenced.
