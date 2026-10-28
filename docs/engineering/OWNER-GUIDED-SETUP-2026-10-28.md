# TOEFL House initial setup — customer-ready target and safe preset

**Owner clarification (2026-10-28):** The current Windows PC is a disposable *testing* installation. The eventual course PC must receive a clean, prebuilt installation package and verified, structured policy defaults. Do **not** copy test students, money, passwords, keys, synthetic attendance or the personal-PC database to the course PC.

## What this branch actually implements

- A versioned, checked-in institution preset in `setup_presets/toefl_house_afghanistan_1405.json`.
- Pure structural validation and a non-mutating catalog/price conflict planner (`preset.py`).
- A Course Owner-only, read-only Frappe preview endpoint (`toefl_house.setup_presets.api.preview_owner_initial_setup`). It returns **READ_ONLY_PREVIEW**, `ready_to_apply=false`, existing/missing/conflicting rows, and unresolved decisions. It does **not** execute setup.
- Offline unit tests (`python -m unittest discover -s tests/setup -p 'test_*.py'`).

The Academic Setup Desk now offers **Check TOEFL House setup**, a read-only, Course Owner-scoped comparison of missing, matched and conflicting academic master records. The server produces an exact plan hash and a deterministic command sequence without writing anything.

A guarded native **first-run catalog initializer** also exists internally under `toefl_house.setup_presets.installer.initialize_owner_catalog` (POST), but it is **disabled by default**. It requires BOTH site flags `toefl_house_customer_release_approved=true` and `toefl_house_owner_catalog_install_enabled=true`, a clean site with no student, admission, fees, payment, salary or sales records, Backup Control Off, exactly one Company with a default receivable account, the native Education Fee Component Item Group, an exact preflight plan hash and an explicit Owner confirmation. It calls only six guarded native academic commands, in one request transaction, creates **draft** fee structures and verifies the resulting catalog. It never posts an invoice or salary, approves a policy, enables tax/backup, or declares production ready. These flags must never be set to bypass the existing release HOLD; their eventual use requires separately qualified customer release and a clean-install acceptance.

No tested, owner-facing **Apply** button is shipped yet. The code path requires real Frappe integration and Windows acceptance, including rollback and concurrent-request tests, before it can be exposed in the installer.

**This is a first engineering slice, not an installed wizard, activation, or production approval.** Existing release and Owner recovery holds remain in force. Never silently seed a live site.

## Owner-defined academic and fee defaults (AFN)

| Family | Native level codes in a clean site | Duration | Full course/semester fee |
| --- | --- | ---: | ---: |
| General English | `PRE-STARTER` | 1 month | 500 |
| General English | `STARTER`, `PREP-1`, `PREP-2`, `PREP-3` | 2 months each | 1,000 each |
| English for Academic Purposes | `EAP-1` through `EAP-4` | 2 months each | 2,000 each |
| Special Speaking | `SPECIAL-SPEAKING-2M` | 2 months | 2,000 |
| TOEFL Preparation | `TOEFL-PREP-4M` | 4 months | 7,000 |

The real test PC uses at least `PREP-ONE` and `PREP-TWO` codes; never rename or duplicate these silently. The clean-install canonical codes are a **proposal**, and the wizard must show an explicit mapping/review against any existing site.

The normal General English transition is Pre-Starter -> Starter -> Prep 1 -> Prep 2 -> Prep 3. Cross-family Prep 3 -> EAP 1 is a placement/admission decision, **not** `TH Program Level.next_level`: the current `set_next_level` is correctly same-family only. EAP levels progress sequentially. Special Speaking is independently enrollable alongside EAP or TOEFL Preparation, with independent attendance/Fees. TOEFL Preparation has its own admission/placement criteria; no automatic forced transition or duplicate billing.

Online 1:1 is a **delivery/contract mode**, not a compulsory EAP successor. The Course Owner confirmed these are **negotiated student tuition fees per calendar month**, not teacher salaries: General English approximately AFN 5,000/month; EAP approximately AFN 6,000–7,000/month (exact student-specific agreed amount); TOEFL Preparation approximately AFN 9,000/month. These are guidance amounts only and may vary by approved individual contract; do not create a universal fee, automatically invoice a template, or treat them as on-site semester charges.

**Instructor compensation is independent.** A teacher may receive approximately AFN 3,000–5,000 per assigned one-to-one class/month (possibly less or more), but this is illustrative rather than an authorized pay rate or bound. Native HRMS/Payroll and the instructor's signed agreement are the compensation authority. An approved student contract and monthly tuition schedule must be separate from the instructor payroll agreement and approval. Track both in their native ledgers and report their relationship for management, but `student tuition - teacher salary` is not automatically net profit (other expenses and taxes may apply). No salary, receivable or payment may be posted merely from the setup preset.

## Academic policy proposal; do not assume runtime accepted

- 40% continuous, 60% final; no midterm. Within 40%: attendance 5%, participation 10%, assignments 10%, short quizzes 15%. Presence is not itself language proficiency; evidence must be recorded and missed assessment must remain incomplete rather than invented zero.
- Six skills weighted Speaking 25, Listening 20, Writing 20, Reading 15, Grammar 10, Vocabulary 10. The 12-component CA/FINAL construction preserves both weight dimensions as existing Frappe policy machinery permits; daily evidence aggregation requires an explicit, tested workflow.
- Proposed pass threshold 65%; native grading scale A >=90, B >=80, C >=70, D >=65, F >=0. Native Grading Scale must be created and linked via an authorized workflow. Do not silently bypass the Course Owner's missing DocType permissions.
- Rubrics should be level-sensitive; Promotion requires published Pass plus Academic Manager approval. `TH Program Level.next_level` and Level Mapping must match actual codes. One retake after >=7 days, latest result governs, if academic policy approved.
- Policy editing **must** be an “Edit as new version” UI flow: show current configuration and differences, effective date, approval, append-only audit/history; no overwrite of an approved historical record. The backend already carries unchanged assessment facets to appended versions.

## Native finance and tax safety

Semester prices are authoritative, not amounts to charge twice. Optional installments should be 500x2 (GE), 1,000x2 (EAP and Speaking), 1,750x4 (TOEFL), and 500x1 (Pre-Starter). The current PR #87 release candidate already includes a **Solar Hijri Month** cadence in `finance/installments.py`, with month-first plus configured grace days. It is still conditional on an effective Owner billing policy, native Fees integration and final Windows acceptance; the preset must not automatically enable installments or issue bills. Payment in advance, overdue balances, receipt verification and role separation are mandatory. Books and refunds are separate native stock/GL transactions.

Discount choices 5/10/15/20/50/100% must start **inactive**. A 100% waiver is a *student-specific* exceptional approval with documented cause (staff relative, scholarship or Owner-approved free place) and immutable audit; broad active `TH Discount Rule` rows would currently discount all eligible students automatically. Only one discount on a charge; no stacking, unauthorized cashier overrides or zero-cost billing without approval.

Tax is **not** a single yes/no business fact. The July 2026 announcements reduced certain company income tax rates to 10%, but company income tax is not a 10% tax to add to every student fee. Verify legal entity, licenses, for-profit vs nonprofit status and applicability of BRT/VAT, withholding on wages/rent and tax documentation using current official Afghan Revenue Department and Ministry of Finance publications and a local qualified accountant. Until review, do not automatically add a student-fee tax line; leaving this UI field OFF is not a declaration of tax exemption.

## Backup and Windows deployment

Owner requested 17:00 local backup. The current code already defaults independent Backup Control **OFF** and requires a complete approved policy and qualified recovery. On a powered-off PC, 17:00 backup cannot be assumed to have run. Implement missed-run alert/check, no invented successful status, suitable Task Scheduler configuration, backup-drive presence checks, GPG public-key-only setup and isolated restore rehearsal before activation. Proposed retention: preserve all valid sets initially; deletion-mode keep count of 7 is not seven weeks, and it does not delete in preserve-all mode. Private keys stay outside Frappe; two-custodian approval is a proposal awaiting verified ceremony.

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

## 2026-10-28 continued safety fixes

- All setup catalog reads now request explicit bounded page lengths rather than Frappe's implicit 20-row default; an over-limit result fails closed.
- Duplicate program and level codes refuse; inconsistent or multiple draft Fee Structures yield explicit conflict rather than a false missing tuition.
- Historical level duration versions remain valid, with the latest version inspected. Missing native program anchors and wrong next-level links are flagged.
- Offline synthetic snapshot tests cover more than 20 programs, over-limit/duplicate rows, malformed fee plans and superseded duration versions.
- Course Owner site initialization is still disabled by default and has no live Apply button. This draft is not an authorized installer or finished academic/finance workflow.

**Release decision remains HOLD / NO-GO.** Do not merge this draft PR into main as customer-ready, clear an existing backup hold, turn tax on, or use customer PII as test data.

## Verification commands (offline; no local site mutation)

```powershell
python -m unittest discover -s tests/setup -p "test_*.py" -v
```

Reference: `apps/toefl_house/toefl_house/academic/__init__.py`, `academic/rules.py`, `academic/assessment.py`, `academic/progression.py`, `finance/installments.py`, `finance/policies.py`, `operations/owner_configuration.py`, and `docs/engineering/LAUNCH-RUNBOOK.md`.
