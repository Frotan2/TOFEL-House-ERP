# TOEFL House ERP — setup identity, policy and duplicate-safety review

**Date:** 2026-10-31  
**Scope:** `work` first-run catalog and Owner setup, not an installed-site sign-off.  
**Release:** **REJECT / TEST DATA ONLY**. `main` must remain untouched pending exact-head gates and independent approval.

## Policy precedence (do not resurrect superseded numbers)

The 2026-10-30 direct Owner clarification recorded in
`docs/owner-decisions.json.owner_policy_addenda_2026_10_30_daily_setup`
**supersedes** the earlier combined GE/EAP AFN 500/month and two-month
TOEFL statements. Use these exact current **configuration** values:

| Family | Native level codes | Months/level | Approved price | Registration / progression |
| --- | --- | ---: | ---: | --- |
| General English | `PRE-STARTER` | 1 | AFN 500 | Sequential |
| General English | `STARTER`, `PREP-1`–`PREP-3` | 2 each | AFN 1,000 per level | Sequential |
| EAP | `EAP-1`–`EAP-4` | 2 each | AFN 2,000 per level | Sequential |
| Special Speaking | `SPECIAL-SPEAKING-2M` | 2 | AFN 2,000 per semester | Concurrent independent track; no mandatory pass/promotion |
| TOEFL Preparation | `TOEFL-PREP-4M` | 4 | AFN 7,000 per semester | Independent track; no official TOEFL-score claim |

Eleven levels across four families. Preset fee amounts are **semester
totals**, not a second monthly charge. The authorized billing engine partitions
one net tuition amount into distinct **native Fees** installments only after an
effective Owner billing policy is configured. An advance payment may settle the
whole tuition. `TOEFL-PREP-2M`, `PREP-ONE`, `PREP-TWO`, etc. are existing-site
aliases needing explicit mapping — **never create parallel canonical levels**.
An installed legacy TOEFL 2M code may have a new effective-dated 4-month
duration; preserve its identifier, history and existing contracts.

Other Owner values: AFN currency, Asia/Kabul, Friday-only weekly closure,
seven confirmed daily sessions with separate male/female starts, assessment
40 continuous + 60 final, pass >=60, maximum one retake after >=7 days and
best result. Six initial operational logins **including the existing Owner**,
without invented real email addresses or additional unrestricted Owner
accounts. Business owners and system roles are separate concepts.

## Native identity and anti-duplication invariants

| Data | Source of truth | Refusal / review condition |
| --- | --- | --- |
| Program family | `TH Academic Program.code` | Duplicate code; retired or mismatched family |
| Level | `TH Program Level.code` → immutable native `Program` | Legacy alias exists; duplicate level code/sequence; two levels use the same native Program |
| Curriculum | `Program` → `Program Course` → `Course` | Existing Program with no Course, dangling or duplicate Course links, or orphan native Program/Course title: Owner preview marks **review**, no second native identity |
| Fiscal/academic year | Native `Academic Year` | Dates mismatch; never silently amend |
| Tuition category | Native `Fee Category` and its accounting `Item` | Missing linked Item, duplicate/malformed price rows, unexpected extra components |
| Price | Native `Fee Structure` with exactly one matching category / level / academic year | Unexpected company, submitted/duplicate/malformed structures, amount mismatch; preserve existing posted Fees |
| Invoices | Native `Fees` and GL/Payment Ledger | Duplicate active bill for an enrollment or conflicts between one-bill and installment paths; no second charge for the same semester |
| Class/attendance | Native `Student Group`, `Course Schedule`, `Student Attendance` | Missing Course/room, overlapping instructor or room, unauthorized roster change, Friday session or inaccessible branch |
| Room | Native `Room` | Same room label exists, invalid capacity; never overwrite an existing room or assume the room's actual seating |
| Assessment policy | `TH Assessment Policy` effective-dated versions + native Grading Scale | Existing version history cannot be overwritten; initial seven-facet snapshot only for an unversioned policy |
| Payroll | Native HRMS, Employee and salary documents | No automatic salary posting from tuition / setup; require approved teacher terms |

### This review's new source safeguards

- `setup_presets/api.py` checks that an existing native Program really has
  linked, existing Courses; it also detects duplicate native Program anchors
  and native Program/Course title collisions with unmapped prospective levels.
- `setup_presets/preset.py` flags such inconsistencies for **manual review**.
  It never repairs old identity relationships by creating a second Program.
- `setup_presets/installer.py` serializes first-run initializers under a
  native DocType row lock, then rereads the snapshot/plan. Its clean-site
  refusal now includes teaching, attendance, assessment, payroll and refund
  records, not merely student invoices.
- Offline tests cover missing, duplicated, dangling and orphan curricula,
  repeated Program anchors, first-run serialization order and expanded
  nonempty-site refusals.

These are **source changes needing exact-head Owned, Native, Foundation,
Windows and Product Image CI**. No Owner-machine data was changed and the
mere presence of tests is not proof of a real database race or recovery result.

## What remains necessary before everyday operational use

1. **Preview rather than seed:** inspect native Company/Branch, chart and default
   receivable, Education Fee Component Item Group, all eleven levels, existing
   aliases, Courses, academic years, native Fee Structures and any legacy
   submitted tuition records. Resolve each `review` item without rewriting
   historical records. Do not run the first-run initializer on a used site.
2. **Academic/room scheduling:** verify real rooms 2–17 and each measured
   capacity; apply the seven confirmed timetable windows without automatically
   assigning instructors or creating overlapping lessons. Create actual
   class rosters, skill assignments and calendars only from vetted live staff.
3. **Policies:** explicitly configure and approve each applicable billing,
   roster, assessment, placement, retention/recovery and permission policy
   version, with start dates and append-only audit. Friday, Solar Hijri year
   rollover, enrollment/transfer and authorized arrears handling need real
   working calendar coverage. A stored policy proposal is not active policy.
4. **Fees:** confirm Company currency and tax classification, semester-total
   tuition vs. two monthly due dates, grace period, optional discounts and
   configured payment allocation; accept one real native Fees/GL bill or one
   bounded installment plan, not both. Reconcile cashier counter handovers,
   credits, books and returns against native balances.
5. **Six users:** retain the existing Owner, then create the five named
   operating logins only with valid verified identity/email handling; enforce
   Academic/GM/Finance/Reception/Instructor roles and company/branch boundaries.
   Do not invent real email addresses or send test invitations to third parties.
6. **Independent delivery:** finish five exact-SHA hosted gates, real offline
   signed EXE and Windows installer acceptance, normal Start/Stop/reboot,
   staff-browser role journeys, safe update/rollback, isolated encrypted
   restore and two-person recovery approval. Protect `main`, obtain an
   independent review and a separate Owner production authorization.

**Never:** merge duplicate fee plans, generate replacement student invoices,
erase policy histories, blindly rename the legacy TOEFL Program, reset the
Owner's Windows database, or bypass a failed release/backup gate.
