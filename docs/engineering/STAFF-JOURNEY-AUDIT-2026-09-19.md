# Staff journey audit — 2026-09-19

Owner directive §3. Judged from how staff would actually work, not from
whether a command exists. Source of truth: the six role desks, the guarded
command pages, and `docs/product/ROLE-DESKS.md`. This is a **code-and-contract
audit**. It is not a hosted walkthrough of a live site, and it does not
claim one.

## How a person actually moves through the product

```
Visitor / walk-in
  → Placement command pages (author, invigilator, assessor, reviewer, releaser)
  → Reception desk (find person; released result waiting for intake)
  → Admission commands, guided from Reception / Academic desks
  → Convert to native Student
  → Enroll in program (Enrollment Officer command, guided)
  → Academic desk: create class → activate → schedule session
  → Attendance Recording command page (Attendance Recorder; not a desk)
  → Teaching Scheduling page (assignment + session)
  → Finance desk: issue tuition from the configured fee plan
  → Finance workspace: native payment against Fees / Sales Invoice
  → Correction queue on the Finance desk (full-amount only, per owner policy)
  → Teaching compensation (D12) → native HRMS Salary Slip / Payroll Entry
  → Owner cockpit / GM desk: counts, exceptions, staffing; no invented metrics
```

Every financial value stays on a native document. Desks add context, never a
second ledger.

## What is actually usable today

| Journey step | How staff reach it | Verdict |
|---|---|---|
| Find a person | Reception desk lookup + funnel | Usable. Bounded search, stage, next role, guided action when the viewer also holds that role. |
| Placement sitting | Command pages, not a desk | Usable for the Officer roles the pages are gated to. Deliberate: no per-Officer workspace (ROLE-DESKS U8 / A13). |
| Admission draft → review → decide → accept → convert | Guided from Reception and Academic desks | Usable, provided the viewer holds the acting role. Otherwise the desk names the next role instead of drawing a dead button. |
| Enroll | Guided `enroll_in_program` | Usable. |
| Create / activate class / schedule session | Academic desk, only if the viewer is also Teaching Scheduler; otherwise the Teaching Scheduling page | Usable. Role-gated. An Academic Manager who is not a Scheduler is told who acts next — they do not get a failing button. |
| Record attendance | Attendance Recording command page | Usable via the page. The Academic desk **narrates** "Record attendance after the session" and names Attendance Recorder. It does not offer the command. That is the role boundary, not a missing feature. |
| Issue tuition | Finance desk "Awaiting billing" | Usable. Prefills the configured fee plan; empty/duplicate/missing plans name the Course Owner instead of a button that can only fail. |
| Collect payment | TH Finance workspace (Finance Officer) on the native payment form | Usable through native ERPNext. The Finance desk **does not collect money** — that is native-authority, not a gap to fill with a second payment engine. |
| Corrections | Finance desk queue | Usable when an active correction policy exists. Without a policy the item says so rather than offering an approval that would deny everyone. |
| Academic setup | Course Owner setup desk | Usable: programs, levels, durations, fee plans, discount rules, with integrity faults surfaced. |
| Exceptions / staffing | GM desk and Owner cockpit | Usable as facts. GM does not perform other roles' commands from this desk. |

## What looks like a dead-end and is not

These were inspected because they match the directive's failure modes
(broken navigation, UI action with no backend, backend unreachable from UI).
They are **role boundaries**, already specified in ROLE-DESKS.md:

1. Academic desk session rows have `action: None` for attendance. The next
   role is Attendance Recorder. Inventing a guided `record_attendance` for
   Academic Manager would either fail (wrong role) or require a statuses map
   the desk does not have. The command page is the product.
2. Finance outstanding rows have no guided payment button. Collecting money
   on the desk would be a second payment engine. The next text now says the
   desk does not collect money itself.
3. Teaching assignment rows are facts. Compensation is D12, paid through
   native payroll, not a desk number. ROLE-DESKS forbids invented payroll
   figures on desks.
4. Officer roles have no Workspace. That is A13 containment, not forgotten
   navigation.

## Real gaps (not softened)

1. **Synthetic-only activation is still REQUIRED.** Owned business commands
   refuse to run on a non-synthetic site. Staff cannot run ordinary
   operations against real student data until the Owner authorizes
   activation. This is a policy lock, not a missing screen.
2. **Compensation is not visible on the Finance desk.** D12 is implemented
   and hosted-qualified; the daily finance surface does not show "this
   assignment is awaiting the next payroll." Staff must use native HRMS.
   Adding a payable queue would be legitimate product work; inventing a
   second payroll engine would not. Left as backlog, not built here.
3. **No hosted click-through of this journey on a live site was performed
   in this session.** Desk contract tests execute every `work()` endpoint
   under a frappe stub, including wrong-role refusal. That is not the same
   as a receptionist sitting at the Tailscale URL. Hosted HTTP verification
   remains required for production-critical desk behaviour.
4. **Teacher-facing desk does not exist**, by recorded decision: Instructor
   ↔ User identity is an owner decision that has not been made. A desk
   keyed on an invented link would be fake authority.
5. **Persian/Dari UI is not this product's desk layer.** Legacy D-15
   bilingual/RTL is rejected as architecture to copy; if the Owner wants it
   on Frappe, that is a future product decision.

## Answer to the directive's acceptance question, for the journey only

Can a trained Reception / Academic Manager / Finance Officer / Course Owner
follow the ordinary path on this codebase? **Yes, on a synthetic site, through
desks plus command pages plus native finance/payroll forms.** Can they do it
on real production data, on the selected local + Tailscale deployment, as an
authorized production system? **No** — synthetic-only is REQUIRED, production
is REJECT, and backup-restore has not been rehearsed on the real server.
