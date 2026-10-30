# TOEFL House initial setup — customer-ready target and safe preset

**Owner's overriding clarification (2026-10-31):** TOEFL House has **no real prior ERP operational history**. Build a **fresh site**, not a legacy migration. The historical Windows evidence below describes an engineering TEST environment and must never be treated as existing institute students, bills, receipts, teaching sessions or approved production configuration. The customer package must include **no test database or demo business records**.

## What this branch actually implements

- A versioned, checked-in institution preset in `setup_presets/toefl_house_afghanistan_1405.json`.
- Pure structural validation and a non-mutating catalog/price conflict planner (`preset.py`).
- A Course Owner-only, read-only Frappe preview endpoint (`toefl_house.setup_presets.api.preview_owner_initial_setup`). It returns **READ_ONLY_PREVIEW**, `ready_to_apply=false`, existing/missing/conflicting rows, and unresolved decisions. It does **not** execute setup.
- Offline unit tests (`python -m unittest discover -s tests/setup -p 'test_*.py'`).

The Academic Setup Desk now offers **Check TOEFL House setup**, a read-only, Course Owner-scoped comparison of missing, matched and conflicting academic master records. The server produces an exact plan hash and a deterministic command sequence without writing anything.

A guarded native **first-run catalog initializer** also exists internally under `toefl_house.setup_presets.installer.initialize_owner_catalog` (POST), but it is **disabled by default**. It requires BOTH site flags `toefl_house_customer_release_approved=true` and `toefl_house_owner_catalog_install_enabled=true`, a clean site with no student, admission, fees, payment, salary or sales records, Backup Control Off, exactly one Company with a default receivable account, the native Education Fee Component Item Group, an exact preflight plan hash and an explicit Owner confirmation. It calls only six guarded native academic commands, in one request transaction, creates **draft** fee structures and verifies the resulting catalog. It never posts an invoice or salary, approves a policy, enables tax/backup, or declares production ready. These flags must never be set to bypass the existing release HOLD; their eventual use requires separately qualified customer release and a clean-install acceptance.

A guarded Owner-facing **Initialize new course catalog** action is now coded in Academic Setup: it is visible only when the server's clean-site, finance, approval-switch and exact-plan preflight succeeds, and always requires Owner confirmation. Real Frappe/Windows acceptance is still required; this is not a production-ready installer.

**This is a first engineering slice, not an installed wizard, activation, or production approval.** Existing release and Owner recovery holds remain in force. Never silently seed a live site.

## Owner-defined academic and fee defaults (AFN)

| Family | Native level codes in a clean site | Duration | Full course/semester fee |
| --- | --- | ---: | ---: |
| General English | `PRE-STARTER` | 1 month | 500 |
| General English | `STARTER`, `PREP-1`, `PREP-2`, `PREP-3` | 2 months each | 1,000 each |
| English for Academic Purposes | `EAP-1` through `EAP-4` | 2 months each | 2,000 each (AFN 1,000/month) |
| Special Speaking | `SPECIAL-SPEAKING-2M` | One two-month semester | 2,000 per semester |
| TOEFL Preparation | `TOEFL-PREP-4M` | 4 months per semester | 7,000 exactly |

**Daily billing authority (latest direct Owner correction, 2026-10-30):** GE is AFN 500 per month, collected per semester: Pre-Starter AFN 500 for one month; Starter and Prep 1–3 AFN 1,000 for two months. Each of EAP's four levels is AFN 2,000 for a two-month semester (AFN 1,000/month). Special Speaking has one two-month semester at AFN 2,000. TOEFL Preparation has a four-month semester at exactly AFN 7,000. These instructions supersede earlier combined GE/EAP AFN 500 and two-month TOEFL claims. Monthly installments, where independently authorized, divide the semester total and never add a second bill. The fresh setup has canonical codes only and no imported historical documents; this correction does not authorize production.

Previous engineering test fixtures may use alternative codes. They are **not** course history and will not be imported. The customer installer uses only the 11 fresh canonical level codes.

The normal General English transition is Pre-Starter -> Starter -> Prep 1 -> Prep 2 -> Prep 3. Cross-family Prep 3 -> EAP 1 is a placement/admission decision, **not** `TH Program Level.next_level`: the current `set_next_level` is correctly same-family only. EAP levels progress sequentially. Special Speaking is independently enrollable alongside EAP or TOEFL Preparation, with independent attendance/Fees. TOEFL Preparation has its own admission/placement criteria; no automatic forced transition or duplicate billing.

Online 1:1 is a **delivery/contract mode**, not a compulsory EAP successor. The Course Owner confirmed these are **negotiated student tuition fees per calendar month**, not teacher salaries: General English approximately AFN 5,000/month; EAP approximately AFN 6,000–7,000/month (exact student-specific agreed amount); TOEFL Preparation approximately AFN 9,000/month. These are guidance amounts only and may vary by approved individual contract; do not create a universal fee, automatically invoice a template, or treat them as on-site semester charges.

**Instructor compensation is independent.** A teacher may receive approximately AFN 3,000–5,000 per assigned one-to-one class/month (possibly less or more), but this is illustrative rather than an authorized pay rate or bound. Native HRMS/Payroll and the instructor's signed agreement are the compensation authority. An approved student contract and monthly tuition schedule must be separate from the instructor payroll agreement and approval. Track both in their native ledgers and report their relationship for management, but `student tuition - teacher salary` is not automatically net profit (other expenses and taxes may apply). No salary, receivable or payment may be posted merely from the setup preset.

## Owner-approved academic terms; runtime acceptance remains HOLD

- 40% continuous, 60% final; no midterm. Within 40%: attendance 5%, participation 10%, assignments 10%, short quizzes 15%. Presence is not itself language proficiency; evidence must be recorded and missed assessment must remain incomplete rather than invented zero.
- Six skills weighted Speaking 25, Listening 20, Writing 20, Reading 15, Grammar 10, Vocabulary 10. The 12-component CA/FINAL construction preserves both weight dimensions as existing Frappe policy machinery permits; daily evidence aggregation requires an explicit, tested workflow.
- Owner-approved minimum Pass is 60%; delegated grading scale A >=90, B >=80, C >=70, D >=60, F >=0. Native Grading Scale must be created and linked via an authorized workflow. Do not silently bypass the Course Owner's missing DocType permissions.
- Rubrics should be level-sensitive; Promotion requires published Pass plus Academic Manager approval. `TH Program Level.next_level` and Level Mapping must match actual codes. One retake after >=7 days for an initial failure; best evidenced attempt is the proposed governing outcome, both attempts remain immutable and the native implementation must be verified before activation.
- Policy editing **must** be an “Edit as new version” UI flow: show current configuration and differences, effective date, approval, append-only audit/history; no overwrite of an approved historical record. The backend already carries unchanged assessment facets to appended versions.

## Native finance and tax safety

Semester prices are authoritative, not amounts to charge twice. The Owner approved negotiable unequal installments such as 50/50 or 60/40, with full net tuition due overall; a student may pay the whole semester immediately. The remaining installment's contracted due date may be the 25th of the starting Afghan month or the first of the next month, with five days of grace. No automatic late-join prorating. The current PR #87 release candidate already includes a **Solar Hijri Month** cadence in `finance/installments.py`, with month-first plus configured grace days. It is still conditional on an effective Owner billing policy, native Fees integration and final Windows acceptance; the preset must not automatically enable installments or issue bills. Payment in advance, overdue balances, receipt verification and role separation are mandatory. Books and refunds are separate native stock/GL transactions.

Discount choices 5/10/15/20/50/100% must start **inactive**. A 100% waiver is a *student-specific* exceptional approval with documented cause (staff relative, scholarship or Owner-approved free place) and immutable audit; broad active `TH Discount Rule` rows would currently discount all eligible students automatically. Only one discount on a charge; no stacking, unauthorized cashier overrides or zero-cost billing without approval.

Tax is **not** a single yes/no business fact. The July 2026 announcements reduced certain company income tax rates to 10%, but company income tax is not a 10% tax to add to every student fee. Verify legal entity, licenses, for-profit vs nonprofit status and applicability of BRT/VAT, withholding on wages/rent and tax documentation using current official Afghan Revenue Department and Ministry of Finance publications and a local qualified accountant. Until review, do not automatically add a student-fee tax line; leaving this UI field OFF is not a declaration of tax exemption.

## Backup and Windows deployment

Owner requested 17:00 local backup. The current code already defaults independent Backup Control **OFF** and requires a complete approved policy and qualified recovery. On a powered-off PC, 17:00 backup cannot be assumed to have run. Implement missed-run alert/check, no invented successful status, suitable Task Scheduler configuration, backup-drive presence checks, GPG public-key-only setup and isolated restore rehearsal before activation. Proposed retention: preserve all valid sets initially; deletion-mode keep count of 7 is not seven weeks, and it does not delete in preserve-all mode. Private keys stay outside Frappe; two-person recovery authorization is mandatory, but real independent custody and restoration on a separate device remain unverified and held.

## Required next engineering slices before any production installer is accepted

1. Integrate a guided `Owner Initial Setup` page into the launcher/Desk: inspect -> display differences -> owner approve each proposed section -> execute guarded native commands idempotently -> verify exact expected records. Existing test data must not be treated as final course data.
2. Qualify the new guarded native Grading Scale creation/action with real Frappe integration, native submit and denial tests; separately test linking it in a new assessment policy version and do not broaden Owner permissions.
3. Build an effective-dated, editable-as-new-version policy editor for academic, fees, classes and owner operations. An approved snapshot remains immutable. The owner backup policy must remain held until real-machine gates are satisfied.
4. Qualify the release-candidate Solar-Hijri monthly cadence in actual billed native Fees, including late joins, partial payments, reversals, outstanding invoice reporting and precise GL totals against one authoritative semester price. Prevent automatic discount grants and cross-family progression.
5. Add capacity, schedules, per-gender shifts and two-instructor GE mapping **from actual site staffing**, never fictional employees. Validate Student Group, Instructor, Payroll/HRMS, permissions and teacher attendance.
6. Bundle an installable signed/offline Windows product, run fresh customer-PC E2E acceptance with synthetic records, roles (Reception/Finance/Academic/Instructor/Owner), cashier/books/refunds/payroll and isolated backup/restore; deliver only after protected CI and explicit Owner approval.

## Owner Grading Scale access — native and governed

The pinned Education Grading Scale DocType grants the native `Academics User` role full CRUD/submit access; the Course Owner does **not** inherit this broad native permission. The new `toefl_house.setup_presets.native_grading_scale.create_owner_grading_scale` POST command uses the existing `business_policy` Course Owner command gate, validates a bounded list of unique native grade codes/thresholds (mandatory 0%), creates a **new** native scale with a mandatory change reason, submits the native document and writes a configuration audit receipt. It refuses duplicate scale names, never patches an older submitted scale, and never grants the Owner generic Academics User or Page permission.

The Academic Setup read-only preview now offers a prefilled **Create new grading scale** action, requiring an explicit reason and user submission. Approved changes to thresholds require a **new unique scale name**, followed by separately reviewed `set_assessment_policy_version` linking to the new scale; earlier assessment versions retain the old link. Native Frappe/Windows acceptance for actual insert/submit, permission denial and resulting grade evaluation **remains mandatory before merge or production**. The new role-scoped route is not live on the personal test PC until a qualified update is installed.

## Direct Student Pay release containment (2026-10-28)

The existing `finance.refunds.guard_payment_entry` guarded Customer Pay against unrelated/non-credit-note book refunds, but it **did not** forbid unapproved native `Payment Entry(payment_type="Pay", party_type="Student")` disbursements. This was an unapproved bypass of the new tuition refund policy. The guarded Payment Entry event now rejects **new/edited Student Pay** until a properly approved, independently tested tuition Fees refund posting path exists. The correction exception is **cancellation of an already-submitted Student Pay**, which must remain possible under native reversal controls. Native `Receive/Student` tuition receipts, supplier payments, customer book credit-note refunds and internal cash transfers are unaffected.

The policy is pure `finance/student_payout_policy.py`, enforced in `finance/refunds.py`, with negative tests `tests/setup/test_student_payout_hold.py` for validate/write/edit denial, cancellation, and unaffected native operations. These changes must pass exact-head CI plus native Frappe and Windows event-gate acceptance. **Do not turn on a bypass flag or treat this containment as a complete tuition refund workflow.** The actual approved GM -> independent Finance Manager payout with exact native GL reconciliation is still blocked by issue #115.

## Final refund and registered-name decision (Owner-confirmed)

The **official English spelling as reported by the Owner** is **The TOEFL House**, with **خانه موفقیت** in Dari, and the business is registered as a language center under an individual natural person. Match the original license and individual holder independently before creating the legal ERPNext Company/first live receipt; no tax exemption is inferred.

Ordinary student tuition withdrawal refunds are **case-by-case**, with documented reason and an AFN amount approved by General Manager. A different Finance Manager independently posts/pays the authorized amount; routine Course Owner approval is not required. Cumulative completed refunds against a student's same company and original paid Fees must never exceed verified submitted, non-cancelled collections less previously completed refunds. Cancelled/draft amounts and unrelated student/company/Fees records do not count. No automatic refund, fixed time window, percentage, or time proration is authorized.

The pure `setup_presets/tuition_refund_review.py` implements a **read-only, fail-closed monetary ceiling and separation-of-duties preflight**. Its evidence must come from an authoritative, scoped and transactionally locked native ledger in a future Finance implementation; arbitrary client JSON is not proof. It returns `payment_permitted=false` and never calls Frappe or issues a Payment Entry. `finance/refunds.py` presently handles native **book return credit notes**, not a qualified tuition Fees credit/payout mechanism. The tuition refund approval and native posting/GL integration remain **HOLD** until they pass actual Frappe/Windows and role-based tests; a passed pure ceiling test is not authorization to pay money.

## 2026-10-28 continued safety fixes

- All setup catalog reads now request explicit bounded page lengths rather than Frappe's implicit 20-row default; an over-limit result fails closed.
- Duplicate program and level codes refuse; inconsistent or multiple draft Fee Structures yield explicit conflict rather than a false missing tuition.
- Historical level duration versions remain valid, with the latest version inspected. Missing native program anchors and wrong next-level links are flagged.
- Offline synthetic snapshot tests cover more than 20 programs, over-limit/duplicate rows, malformed fee plans and superseded duration versions.
- Course Owner site initialization remains release-gated; the new guarded GUI button stays hidden until clean-install and finance preflight pass. This draft is not an authorized installer or finished academic/finance workflow.

**Release decision remains HOLD / NO-GO.** Do not merge this draft PR into main as customer-ready, clear an existing backup hold, turn tax on, or use customer PII as test data.

## Verification commands (offline; no local site mutation)

```powershell
python -m unittest discover -s tests/setup -p "test_*.py" -v
```

Reference: `apps/toefl_house/toefl_house/academic/__init__.py`, `academic/rules.py`, `academic/assessment.py`, `academic/progression.py`, `finance/installments.py`, `finance/policies.py`, `operations/owner_configuration.py`, and `docs/engineering/LAUNCH-RUNBOOK.md`.


## Test-only Windows checkpoint — not the institute database

Prior engineering notes described a disposable test-site catalog, simulated
staff accounts with reserved invalid identifiers and synthetic finance evidence.
Those were **test fixture activities**, not TOEFL House operating history.
The Owner confirmed the institute has **not operated this ERP yet**; do not
copy, restore, migrate, or seed those test databases, staff samples, payments,
students or receipts into the customer package.

The clean release creates approved academic and financial **masters only**:
4 programs, 11 levels, required native Course links, an academic year and
draft tuition plans, after explicit Owner action on a qualified clean site.
No imported legacy aliases. No starting student, enrollment, attendance,
posted Fees, collection, payroll or assessment result.
Both synthetic testing and future legitimate audit logs remain supported
without inventing historical business transactions.

## Initial assessment configuration and latest timetable — 2026-10-31

A new policy can now supply all seven explicit `initial_facets` to the existing
`set_assessment_policy_version` command together with its native grading scale.
This creates one effective-dated, audited version instead of requiring seven
artificial dates. Existing policies cannot use this initialization path; their
history and strict increasing effective dates remain unchanged. Calls without
this optional argument retain their original audit payload and replay identity.
Native criteria, scale grade codes, program-family level mapping, progression
policy and approval-role references are validated before the version is saved.

The real Windows MariaDB-backed synthetic qualification verified a complete
initial version, same-key replay, non-Owner denial, foreign-family and unknown
grade refusal, refusal to initialize an already versioned policy, and old audit
payload compatibility. All fixture writes rolled back and exact table hashes
matched. This source-helper evidence does not certify the installed candidate.
The same qualification is now mandatory in Native CI.

The Owner-confirmed timetable is below, in Asia/Kabul local time. Morning
female classes start ten minutes after the male classes; afternoon female
classes start ten minutes before. Each session is seventy minutes. The first
morning break is twenty minutes; the remaining adjacent-session breaks are ten.
Lunch is 12:00–13:00; other midday time stays unallocated.

| Session | Male | Female |
|---|---|---|
| S001 | 06:20–07:30 | 06:30–07:40 |
| S002 | 07:50–09:00 | 08:00–09:10 |
| S003 | 09:10–10:20 | 09:20–10:30 |
| S004 | 10:30–11:40 | 10:40–11:50 |
| S005 | 14:00–15:10 | 13:50–15:00 |
| S006 | 15:20–16:30 | 15:10–16:20 |
| S007 | 16:40–17:50 | 16:30–17:40 |

Friday remains the sole weekly holiday. These are institutional period patterns,
not scheduled classes or instructor assignments. Overlapping male/female classes
need distinct available instructors/rooms under the existing native conflict
checks. Sixteen rooms numbered 2–17 were created with an explicitly documented
conservative operating limit of fifteen, the lower bound of the Owner-confirmed
15–30 range. Individual measured capacities were not supplied. Eleven existing
native Programs now link to their native integrated Course; program identifiers
and history were retained. No classes, sessions or financial documents were
created. Approved retakes keep the higher score.
