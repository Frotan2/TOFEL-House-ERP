# Domain Audit and Remediation Plan (principal-owner mandate)

Branch: `arena/01a0c987-tofel-house-erp`. Verdict: **NOT READY**. Production stays **REJECT/BLOCKED**.
This record supersedes nothing: canonical docs keep precedence (§4); this is the working audit trail.

## Method

Read in full: `security.py`, `controllers.py`, `permissions.py`, `hooks.py`, `api.py`
(`_execute` core), `transactions.py`, `finance/__init__.py`, `finance/corrections.py`,
`enrollment/__init__.py`, `admission/__init__.py`, `teaching/__init__.py`,
`teaching/compensation.py`, `academic/__init__.py` (create/mutate surface),
`administration.py`, `install.py`, `desk/__init__.py` + reception/teacher/setup/finance
desks, client JS shape. Grepped: concurrency tests, isolation config, LIKE handling,
guard wiring, stub fidelity. Local suite 1107/1107 green is owned-fakes-only
(NO_FRAPPE_STACK); hosted suite (`tools/placement/native_checks.py`, 2-worker gunicorn)
is the only net for races and native behavior.

## REAL BUGS (legitimate flows break; fix in slices, not owner questions)

| ID | Location | Break | Fix |
|---|---|---|---|
| BUG-INV-01 | `enrollment/__init__.py:58-65` via `finance/__init__.py:61` | `deny_premature_invoice` has no in-command exemption: `issue_placement_fee` and `approve_invoice_correction` credit notes for converted students are ALWAYS refused. Breaks late placement billing and ALL invoice corrections on the mainline path. Zero coverage (local or hosted); hosted payers are standalone customers. | Early-return inside `finance_command_active("Sales Invoice")`. Out-of-band invoices stay denied (containment preserved). |
| BUG-ENR-02 | `enrollment/__init__.py:141-143` | Post-submit `exists(Sales Invoice for customer)` conflates pre-existing invoices with enrollment side effects; false-refuses enrollment when staff link a customer with history (e.g. unifying walk-in payer and student customer). Message misstates cause. | Before/after invoice name-set diff; refuse only on NEW invoices. |
| BUG-PAY-01 | `teaching/compensation.py` `calculate_teaching_compensation` | No locks at all: concurrent different-key calcs over overlapping periods/contracts double-post Additional Salary. Isolation-independent. | Lock overlapping contract rows (deterministic order) + `for_update` existence re-reads before each insert. |
| BUG-PAY-02 | `teaching/compensation.py` adjustment dedup | One-off key is per-contract, not per-adjustment: the first posted adjustment suppresses ALL later adjustments for the contract (silent underpayment). | Dedup per adjustment-row identity. |
| BUG-ADM-01 | `admission/__init__.py` `record_applicant` | Duplicate-applicant `exists` check takes no lock: concurrent same-subject double-submit creates duplicate applicants (no native unique on email). Same-key covered by idempotency; different-key not. | Lock the placement decision row before the check. |
| BUG-ADMIN-01 | `administration.py` `set_managed_role` | Version replay lookup uses unescaped `LIKE %key%` (`_` is a wildcard in valid keys) and never compares `recorded.request_key` exactly: a crafted key can false-replay and silently drop a role change when state drifted natively. | Escape LIKE wildcards + exact key comparison. |
| BUG-INST-01 | `install.py` `_seed_skills` | Bare `except Exception` + rollback masks real seed failures; migrate reports success with missing masters. | Catch `DuplicateEntryError` only. |

Small hardening in passing: currency fail-closed in compensation calc (`None` fallback,
done in S2); `_require_course_owner` missing enabled check (done in S3, plus the
administration actor gates); `set_level_duration` retry errors instead of replaying
receipt (stays: academic commands carry no receipt store — GAP-ACADEMIC-IDEMPOTENCY,
later engineering slice, not owner-gated). Retired TH levels: reclassified — operations
run on native programs and never consume the TH catalog, so retirement has no
operational effect at all (GAP-CATALOG-LINKAGE, S4 design).

## GAPS (missing for real daily use; design slices, some need owner answers)

- **GAP-REENROLL (critical):** no returning-student/continuation path. Applicant email-dup is
  global and permanent; returning explicitly denied (`enrollment_is_eligible`);
  `convert_applicant` refuses `existing_student`. Multi-term students impossible without a
  new email identity per term (identity fragmentation). Needs designed slice.
- **GAP-CONDITIONAL:** Conditional admission is a dead end (convert refuses conditions; no
  satisfy-conditions command). Needs authority design.
- **GAP-ROSTER:** roster immutable after class creation (no late-joiner/transfer/sectioning).
- **GAP-ATT-CORRECT:** submitted attendance has no correction path. Needs authority design.
- **GAP-EXIT:** no post-conversion revocation, unenroll, withdraw, or exit flows.
- **GAP-DATES:** billing dates unbounded (future posting allowed natively; backdate bounded
  only by fiscal year). Policy needed.
- **GAP-FEE-TIMING:** placement fee billable at any case state (correct iff the fee is an
  upfront entry fee — intent unverified).
- **GAP-BREAKGLASS:** withdraw/revoke paths have no admin override if the actor leaves.
- **GAP-ADJUST-ORPHAN (found during S2):** the calc only evaluates adjustments for
  instructors with in-period assignments; a due adjustment in an assignment-free
  period is silently skipped. Posting vs skipping is contract semantics — owner
  question, not invented (OD-NEW-08).
- **GAP-CATALOG-LINKAGE (reclassified during S3):** admission/enrollment/billing
  run on native programs and never consult the TH academic catalog; retiring a TH
  level changes no operational behavior. Whether the catalog must govern
  operations is S4 design (may need an owner answer on the catalog's authority).
- **GAP-ACADEMIC-IDEMPOTENCY (recorded during S3):** academic control-plane
  commands validate request keys but keep no receipt store, so a retried call
  errors instead of replaying. Safe (monotone-version rules refuse the duplicate),
  but confusing after a timeout. Later engineering slice: route academic commands
  through receipt semantics. Not owner-gated.

## Owner-decision list (added; no invention)

- OD-NEW-01 returning-student identity + continuation rules (new placement per term?).
- OD-NEW-02 conditional-satisfaction authority + upgrade path.
- OD-NEW-03 billing date bounds (future/backdate policy).
- OD-NEW-04 placement-fee timing (upfront vs on-delivery) + one-customer-per-person guidance.
- OD-NEW-05 roster-change authority (who may add/move students post-creation).
- OD-NEW-06 attendance-correction authority + window.
- OD-NEW-07 student exit/unenroll policy + financial consequences.
- OD-NEW-08 whether contract adjustments post in periods with no assignments
  (GAP-ADJUST-ORPHAN).

## Isolation note (settled empirically; mechanism unproven)

Hosted first-writer races (2-worker gunicorn, stock MariaDB, forced lock overlap) are
green with anchor-lock + plain-exists checks, which is only consistent with
statement-current (RC-effective) worker connections. No in-repo probe asserts the
effective level, and two `native_checks.py` comments attribute runner-side staleness to
REPEATABLE READ (more likely Frappe value-cache/lock phenomena). Rule: new money paths
use lock + locking re-read (safe under BOTH isolations). Recommend a hosted probe
(`SELECT @@SESSION.transaction_isolation`) plus overlap-asserting race tests.

## Remediation slices (priority order)

- **S1 billing/enrollment correctness:** BUG-INV-01 + BUG-ENR-02. Local mock-based
  regression tests (guard context behavior; invoice diff) + hosted checks
  (bill-then-convert-then-correct; customer-with-history enrollment). Unblocks late
  placement billing, invoice corrections, customer unification.
- **S2 payroll correctness:** BUG-PAY-01 + BUG-PAY-02 + currency fail-closed. Local
  mock-based tests (lock queries issued; per-adjustment dedup) + hosted concurrency
  check for the calc.
- **S3 hardening:** BUG-ADM-01 + BUG-ADMIN-01 + BUG-INST-01 + isolation probe +
  enabled-actor gates. (Retired-level guard reclassified to GAP-CATALOG-LINKAGE.)
- **S4 lifecycle design (gated on OD answers):** GAP-REENROLL, GAP-CONDITIONAL,
  GAP-ROSTER, GAP-ATT-CORRECT, GAP-EXIT, GAP-CATALOG-LINKAGE. Design docs first,
  then slices. Plus later engineering slice GAP-ACADEMIC-IDEMPOTENCY (not gated).

## Stub-fidelity warning (permanent)

Local DB-backed harnesses ignore `for_update`, return `[]` for all raw SQL, do not model
operator filters (`in`/`!=`/`like`), and raise `KeyError` instead of `DoesNotExistError`.
Local tests therefore cover happy paths + validator rejections only. Locking, races,
duplicate-denial, and native behavior are hosted-only. Every remediation slice ships BOTH
mock-based local tests (call-shape assertions, per `tests/placement/test_transactions.py`
precedent) AND hosted `native_checks.py` checks; the hosted proof executes on push CI.
