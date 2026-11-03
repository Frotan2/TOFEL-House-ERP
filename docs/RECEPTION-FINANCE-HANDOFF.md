# TOEFL House — Reception ↔ Finance controlled daily handoff

**Status:** Draft code qualification on PR #124; **NO REAL DATA** and no Owner release approval. These steps describe the intended controlled workflow; they are NOT evidence that a Windows employee has completed it.

## Front-counter decision sequence

1. **Register inquiry (Reception):** Search first by name, Inquiry ID, student ID or permitted phone. Record real name, authorised Branch, optional phone, preferred course/mode and optional learner country/time zone. An Inquiry is never a Student, approved admission, seat reservation, tuition debt or paid receipt. An online prospect may live abroad, but the staff member's Branch permissions still apply.
2. **Release placement and approve admission (academic authorities):** The placement, applicant, approval and native Student/Program Enrollment links must all be independently verified. Reception cannot invent Student IDs, course eligibility, accounts or email addresses.
3. **Issue tuition bill (Finance Officer):** Only a submitted Program Enrollment and Owner-configured approved Fee Structure and billing policy can produce a submitted native Education **Fees** document. Native Fees, Payment Entry and GL are financial authorities; a draft Fees record is not collectible money. Finance must resolve a draft or an incomplete Fees read before issuing. If there is one non-cancelled bill/plan, the duplicate-issue command refuses another bill. Never calculate a debt from an Inquiry or a class preference.
4. **Take physical cash only against a real outstanding bill (Reception):** Verify the exact student, branch, fee ID, company and outstanding amount; count actual cash, use the staff member's *own* Owner-assigned Cash counter and record one guarded **Payment Entry Receive** receipt. The amount must be positive, within the bill's current remaining balance, and in the company/accounting currency. Print the current numbered issued receipt only after successful native posting. Do not label a draft, screenshot, transfer promise or pending bank payment as collected.
5. **Independent cash handover (Finance Officer/Manager):** The collector cannot accept their own handover. Finance selects explicit unhanded receipts from one collector, company, Cash counter and currency. Counted physical money must exactly match the selected issued receipts; do not paper over a variance. An authorised native Internal Transfer moves custody from the separate Reception Cash counter to main Cash. Before **any** receipt is marked handed over, the transfer must be **Submitted**, have the authorized company/source/destination Cash accounts, the matching currency on both legs and the **exact** counted amount in both debit/credit legs. If it fails, the transaction must be refused (not treated as successful). **It does not charge the student twice.**
6. **Corrections/refunds:** An Owner-authorised correction may void/reissue an *unhanded* receipt with a written reason and the same amount, subject to original bill/currency guards. Once handed over, refer to the independently approved accounting reversal/refund process; do not edit the historical Payment Entry. Refund decision and payout remain separated between General Manager and Finance Manager.
7. **Online learners abroad:** International phone +country-code is contact information, **not a payment channel**. The current Reception cash command is local Cash-account collection; it does not establish a cross-border card, bank, wallet or online checkout. A third-party transfer screenshot or message is not a valid collected receipt. Finance must approve a legal, supported settlement method and reconcile the actual bank/cash entry before advertising global online fees as payable.

## Privacy and financial truth safeguards

- A receptionist may see **their own** issued numbered receipts while their authenticated, permitted Branch and individual collection scope remain valid. Revoking Branch access must revoke prior own-receipt read access as well. Cross-branch students or another collector's receipt must not be exposed through a guessed URL.
- A native Fees **Draft (docstatus 0)** blocks new issuance but has no submitted receivable. Show **Draft fee needs review**, not simply hide the enrollment from the billing work list. An incomplete bounded bill read means **Billing status needs review** and must not offer an Issue action.
- Submitted Fees and outstanding balances are current native accounting facts, not an invented financial ledger or proof of cash physically held by Reception. A prior month debt remains a debt until actual allocations settle it; do not call an advance a refund or double-charge a second month's Fees.
- Real international online tuition settlement, live payroll, refund/recovery acceptance, windows database migration and independent audit remain separate release gates.

## Mandatory isolated Windows/MariaDB acceptance

| Scenario | Expected result |
| --- | --- |
| Inquiry before placement/admission | No Fees, invoice, Payment Entry or Cash movement |
| Student with approved submitted enrollment and proper fee policy | One valid submitted Fees/authorised installment plan, no duplicate bill |
| Existing unsubmitted Fees draft | Finance queue flags draft, no collector-facing debt and no duplicate Issue button |
| At-cap billing-read projection | Finance sees review-needed, no automatic Issue action |
| Reception without an assigned counter | Cannot issue receipt; Owner assignment needed |
| Genuine cash partial payment and final payment | Each receipt is one native posted allocation; remaining outstanding reconciles exactly |
| Multiple Receptionists use separate counters | Collector and receipt company/currency remain immutable |
| Same receipt submitted or handover batch replayed | Idempotent result, no duplicate ledger posting or transfer |
| Physical handover amount differs from listed issued receipts | Handover refused; discrepancy investigated |
| Finance accepts complete same-counter batch | One native internal Cash transfer, source receipts marked handed over |
| Reception role without Branch permission after revocation | Previously issued own receipt no longer opens |
| Another collector's receipt or other-Branch bill | Reception is denied |
| Owner correction before handover | Original cancelled, replacement posted with written reason and audit |
| Correction after handover | Refused; use independently approved reversal/refund |
| Foreign learner pays by unverified screenshot | No cash receipt; separate Finance-approved payment processing required |

**Release status:** PR #124 remains Draft until exact-head CI succeeds, independent security/accounting review completes, the isolated MariaDB+Windows six-role journeys and recovery pass, and the Owner authorises release. Keep the installed Owner site untouched.
