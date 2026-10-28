# TOEFL House — decision closure packet (2026-10-28)

## Owner follow-up — decisions received on 2026-10-28 (authoritative addendum)

The current Course Owner supplied and confirmed the following decisions after the original open-question review. They are saved as an immutable-facing `owner_policy_addenda_2026_10_28` in `docs/owner-decisions.json` and as source defaults in `setup_presets/toefl_house_afghanistan_1405.json`.

- GE/EAP: pass >=60%; proposed A >=90, B >=80, C >=70, D >=60, F <60. 40 continuous points (attendance 5, participation 10, assignments 10, quizzes 15) + 60 final.
- One retake for a student failing the first term result, no earlier than seven days. Engineering proposal: **best** of the two evidenced scores governs; both attempts must remain independently auditable. The native runtime still needs proof of actual best-attempt selection.
- Special Speaking and TOEFL Preparation are independent specialist courses with competency/progress feedback, **not mandatory automatic pass/fail or progression**. Their template omits pass/progression facets and cannot be silently activated as a formal grading book until a separate progress-report workflow is verified.
- Placement is not free: AFN 100 **per placement attempt**, Reception registers and charges through a native receipted payment, with paper/written assessment and in-person Speaking evidence reviewed by authorized academic staff.
- Late joiners owe the **full** course/semester tuition, never automatic time-based proration. Only an authorized discount may reduce it.
- Optional installment amounts are contractual and variable (e.g. 50%/50% or 60%/40%), must equal full net tuition, with due-date choice of the 25th of the starting Afghan month or first of the following Afghan month (preferred), plus five days' grace. The present native installment engine still needs tested unequal shares and owner-specific due dates; do not imply the current preset enables this.
- Same-level class transfers are approved in principle, conditional on capacity and authorized Academic Manager approval, with full history. This is a **new scope-limited supersession** of D5; other program/branch transfer and advanced withdrawal decisions stay held.
- Withdrawal/refund authorization: General Manager approves ordinary claims; Finance Manager makes the independently recorded actual payment. Refund eligibility, timing and amount formula **not yet specified**; no autonomous refund must be issued.
- Discount choices 5, 10, 15, 20% require General Manager approval, 50 and 100% require Course Owner approval; 100% staff-relative eligibility includes spouse, children and parents, excluding siblings; named beneficiary and evidence are mandatory.
- Actual class capacity adjustable per class within 15–30, with engineering-proposed default 20 only, never an institution-wide fixed cap without per-class approval.
- One-to-one online fee is monthly from each student's actual start/renewal anniversary, not automatically at the start of an Afghan calendar month; teacher payroll remains separate.
- The entity is registered in an **individual natural person's name** as a language teaching center. Owner supplied English text **The Tofel House** and Dari **خانه موفقیت**. Verify exact licensed company name and spelling before generating legal receipts or creating the live ERPNext Company. Tuition tax remains disabled pending current legal classification; not a tax-exemption declaration.

**Outstanding questions now reduced to two consequential policy details:** (1) refund eligibility/amount formula and time window, (2) exact official English spelling as shown on the registered education license. A small additional month-end edge case is engineering configuration and can be set to the last valid date of a shorter month, unless the Owner objects.

**Operational release remains HOLD.** Owner statements permit policy design, not unsafe bypass of D1/D5 runtime gates, historical edits, Company registration or live financial postings. Tests and a Windows-native release remain required.

**Status: PARTIALLY RESOLVED — REVIEW THE 2026-10-28 OWNER ADDENDUM ABOVE.** This packet is an analysis, not an operative policy. Do not mark decisions in `docs/owner-decisions.json` approved until the Course Owner explicitly answers. Do not disable any existing release or policy guard. All real/synthetic data on the personal test PC remain isolated from the eventual clean course-PC installer.

## Recorded owner facts — do not ask again

- Four physical programs: General English (Pre-Starter 1 month AFN 500; Starter, Prep 1–3 each 2 months AFN 1,000), EAP 1–4 each 2 months AFN 2,000, Special Speaking 2 months AFN 2,000, TOEFL Preparation 4 months AFN 7,000.
- GE progression Pre-Starter -> Starter -> Prep 1 -> Prep 2 -> Prep 3; EAP 1 -> 2 -> 3 -> 4. Special Speaking is optional and concurrent with EAP/TOEFL preparation, not a mandatory successor.
- Negotiated **monthly student tuition** for online 1:1: suggested GE AFN 5,000, EAP AFN 6,000–7,000, TOEFL preparation AFN 9,000. Instructor pay is separately agreed, native HRMS/Payroll; do not automatically calculate it from student fees.
- Assessment structure is 40% continuous + 60% final; **the detailed subdivisions and pass threshold remain unapproved proposals**. Correct native academic results must remain evidence-based.
- Approved discount template **choices** 5%, 10%, 15%, 20%, 50%, 100%; 100% allowed for staff relatives, scholarships and exceptional free places, but identity, eligibility and approval conditions remain undecided. No global active rule or automatic waiver.
- Owner wants preset installation on a new course PC, not transfer of personal-PC testing data. Company, staff, roles, cash/GL, backups and recovery require independent actual-site validation.
- Proposed backup hour 17:00 local with OFF/ON switch; off means no backup attempt. Encryption, separate disk and a qualified isolated restore remain mandatory before production activation.
- Current Tailscale/local staff access, Afghan Solar Hijri calendar, cashier collection reduces student balance at receipt issuance and internal Finance handover does not issue a second student payment, two-person recovery and RPO 24h / RTO 8h requirements already recorded. No payment gateway at launch.

## Conflicts / unclosed authorization gates in canonical decisions

- **D1:** Canonical record still says DEFER; owner has since described broad 40/60 assessments, but the 65% pass floor, CA weighting (attendance 5 / participation 10 / assignments 10 / short quizzes 15), retake maximum 2 attempts with 7-day wait, and grading scale A 90 / B 80 / C 70 / D 65 / F 0 remain **proposed, not approved**. Do not silently supersede the D1 deferral.
- **D3:** Native correction/refund framework exists, but late-join pricing, partial refund eligibility and approved reason-window rules are not fixed.
- **D5:** Basic lifecycle selected, advanced transfer/withdrawal deferred. `allow_transfers` and related controls **cannot** bypass the separate superseding Owner decision; transfer scope remains fail closed.
- **D7:** Raw reports allowed; derived retention/conversion/ranking KPIs deferred until named stewards, numerator/denominator and disclosure terms are approved. Do not show invented or false-zero analytics.
- **D6a/tax:** Not configured. Do not equate company income taxation, tax-withholding, and possible student-fee indirect taxes. The owner must identify legal type/registration and qualified advice; never silently mark exempt.
- **Capacity & scheduling:** Existing program/level durations and timetable shift patterns are known, but **actual approved class capacity**, teacher availability and conditional overbooking limits are not. Never create fictional teacher accounts or salaries.
- **Native Grading Scale:** The new narrowed Course Owner creation path is in draft PR #113, not installed. The native Education DocType grants direct rights to Academics User; do not add the broad role to a Course Owner account.
- **Policy revision UX:** The existing effective-dated backend protects history. The Owner needs a reviewed prefilled 'Edit as New Version' flow; an optional *blank grading scale* currently intentionally clears the new version's link (tested), so it **must be prefilled** and prominently explained instead of silently losing the scale.
- **Setup installer:** Current preset and gated initializer are incomplete and not a signed/accepted customer installation. No public Apply button or release authorization. All five hosted PR #87 checks passing on 26cedb5 is necessary but **not sufficient** physical Windows/backup/role acceptance.
- **Release/governance:** PR #87 and PR #113 remain Draft / Production HOLD; main branch protection / independent approval remains an administrator-side action.

## Questions requiring Owner decision (recommended, editable defaults)

1. Academic pass/retakes: approve 65% minimum, proposed 40-point breakdown 5/10/10/15 (attendance/participation/assignments/quizzes), grade thresholds 90/80/70/65/0, and **one** retake after >=7 days with **latest score** governing? Or specify different percentages/eligibility.
2. Placement: is initial placement free? May Reception register an applicant while an Academic assessor alone sets a recommended level? Can placement be waived for external evidence, and by which approver?
3. Tuition and late joins: for someone joining an active 2- or 4-month class, charge the full remaining semester, a proportional amount for remaining time, or the full standard semester? Confirm due at the first of each Solar Hijri month with a suggested 5-day grace; Pre-Starter is one monthly charge.
4. Withdrawal/refunds: approve an auditable window for withdrawal and unused-fee refund (e.g., before start full less documented nonrefundable costs, first week prorated, later case-by-case)? **Do not invent refund entitlements**.
5. Discount approvals: who may approve 5–20%, 50% and 100%; which staff-relative relationships count? Discounts remain student-specific with reason, never stacking and never payable as cash by default.
6. Class capacity and transfers: default seats/class (e.g. 20), allowed extra seats and approver; keep D5 transfers disabled, or authorize restricted same-program/class transfers under an explicit superseding policy? If allowed, decide 7/14/30 days from enrollment as the window.
7. Registered legal entity for tax classification: private training center registered as individual/business/company, or nonprofit? Has a qualified accountant confirmed which tuition tax, business income, withholding and reporting duties apply? No tax ID/document number is requested in this packet.
8. D7 analytic KPI: continue raw factual reports only (recommended for launch) or explicitly authorize derived retention/completion metrics with agreed steward and definitions?
9. Online 1:1 first/last partial month: charge full calendar month, pro-rata daily, or by contracted sessions? Who approves changing a negotiated student's monthly fee?

## Engineering next actions after answers

Record explicit superseding approved decisions (with date, scope and approver) without erasing prior versions. Implement Owner policy UI with prefilled effective-dated revision and diff. Configure grading/assessment, billing, class capacity, academic admissions and discounts only from approved values. Run native Frappe and real Windows end-to-end tests under distinct staff roles plus isolated encrypted backup/recovery. Merge only after independent release/governance gates and explicit final Owner signoff.
