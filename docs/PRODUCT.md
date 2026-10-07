# TOEFL House ERP — product and architecture

This is the single current description of the product: what it manages, what
is native, what is TOEFL House-specific, and where each rule lives. It replaces
the earlier capability map, domain closure records, roadmaps and baselines
(still available in Git history). Decisions and their rationale are in
[DECISIONS.md](DECISIONS.md); owner business decisions are in
[owner-decisions.json](owner-decisions.json).

## 1. What it is

A Course Management ERP for the TOEFL House language institute. It runs the
student lifecycle from first enquiry to progression, the teaching operation
around it, and the money on both sides (tuition in, teacher compensation out).

**Foundation (native, authoritative, pinned, never patched):** Frappe,
ERPNext, Education, Payments, HRMS. Exact commits and digests:
[engineering/foundation-version-matrix.json](engineering/foundation-version-matrix.json).

**Owned apps:**

| App | Purpose |
| --- | --- |
| `apps/foundation_security` | Deny-by-default hardening of the foundation (realtime subscription authorizer, file/guest guards). No business logic. |
| `apps/toefl_house` | The TOEFL House extensions below: thin guarded commands over native DocTypes, owner-configurable policy records, placement, and the role desks. |

**Principle: native-first.** A native DocType is the system of record wherever
one exists. `toefl_house` adds a DocType only for a proven native gap, and it
never adds a second student, teacher, course, class, enrollment, invoice,
payment, attendance, payroll or workflow master.

## 2. Lifecycle and ownership

```
Applicant ─► Placement ─► Admission ─► Enrollment ─► Class / Schedule ─► Attendance ─► Assessment ─► Progression
                │             │            │               │                  │
                │             │            ├─► Tuition fees (native Fees)     └─► Teacher compensation (native Additional Salary)
                └─► Placement fee (native Sales Invoice)
```

| Step | System of record (native) | TOEFL House extension | Status |
| --- | --- | --- | --- |
| Applicant / Student | Student Applicant, Student, Guardian | `admission.record_applicant`, `convert_applicant` | Implemented |
| Placement | — (native gap: governed test bank, delivery, scoring) | `TH Placement *` (15 DocTypes), level/course recommendation | Implemented, bounded — see [PLACEMENT-SPEC.md](PLACEMENT-SPEC.md) |
| Admission | Student Applicant | `TH Admission Decision` (review → decide → conditions → offer → convert), `TH Returning Student Policy` | Implemented |
| Enrollment | Program Enrollment, Course Enrollment | `enrollment.enroll_in_program`; `TH Enrollment Exit` (+ policy) for withdrawal/dismissal | Implemented |
| Course / Program / Level | Program, Course, Academic Year/Term | `TH Academic Program`, `TH Program Level`, `TH Level Duration`, `TH Catalog Linkage Policy` (configuration over native Program/Course) | Implemented |
| Class / Roster | Student Group | `create_student_group`, `add/move_class_member`, `TH Roster Change Policy` | Implemented |
| Teacher | Instructor, Employee | `TH Instructor Contract`, `TH Teaching Assignment`, `TH Skill` | Implemented |
| Schedule | Course Schedule (native overlap validation) | `schedule_session` | Implemented |
| Attendance | Student Attendance (submitted, native statuses) | `record_attendance`; `TH Attendance Correction Request` (+ policy) | Implemented |
| Assessment | Assessment Plan / Result / Grading Scale | `TH Assessment Policy` (owner-versioned components, weights, pass and progression rules) | Configuration implemented; grading values owner-supplied |
| Progression | Program Enrollment (next level) | `set_next_level`, assessment-policy progression facet | Configuration implemented |
| Fees / Payments | Fee Structure, Fees, Sales Invoice, Payment Entry, Pricing Rule | `issue_tuition_fees`, `issue_placement_fee`, `TH Billing Policy`, `TH Discount Rule`, `TH Correction Request` (+ policy) | Implemented; prices are native configuration |
| Teacher compensation | Additional Salary → Salary Slip / Payroll Entry | `calculate_teaching_compensation`, `TH Contract Adjustment`, `TH Adjustment Posting Policy` | Calculation implemented; posting gated by owner policy |
| Reporting | Native reports, Query Reports, dashboards | Role desks (read-only projections) | Native; no derived metrics defined |
| Configuration | — | Policy records (§3), Configuration desk, `TH Configuration Operation` / `TH Configuration Audit Event` (receipted, hash-chained audit) | Implemented |
| Guardians / alerting | Guardian | `TH Guardian Lifecycle Policy`, `TH Alerting Policy` | Carriers implemented; values NOT CONFIGURED |

Never built (native covers it, or it is out of scope): portals, online payments,
CRM, a custom accounting, HR or payroll engine, a custom workflow engine.

## 3. Business policy: configuration, never code

Tuition amounts, salary and skill rates, taxes, refunds, discounts, attendance
and progression thresholds, class capacities, guardian rules and report
definitions are **owner-entered configuration**. They live either in native
records (Fee Structure, Price List, Pricing Rule, Salary Component) or in
versioned `TH * Policy` records. Every policy record works the same way:

- versions are append-only and effective-dated; a newer version supersedes, never rewrites;
- every change goes through a receipted command gated to the Course Owner or the relevant manager, and leaves a hash-chained audit event;
- a consumer with no effective version **fails closed** (`NOT CONFIGURED`) instead of assuming a default.

Specification: [CONFIGURATION-PLANE.md](CONFIGURATION-PLANE.md).

## 4. Enforcement model

- **Commands, not raw CRUD.** Guarded DocTypes (Program Enrollment, Student Group,
  Course Schedule, Student Attendance, Fees, Sales Invoice, Additional Salary…)
  change only through `toefl_house` commands. `validate`, `before_cancel` and
  `before_update_after_submit` hooks refuse every other route: REST, RPC, Desk
  cancel, copy/amend (decision A13).
- **Roles.** 24 roles ship as fixtures: the institute roles (Course Owner,
  General Manager, Academic Manager, Finance Manager, Reception, Instructor) and
  per-domain duty roles (Admission, Enrollment, Teaching, Finance and Placement
  officers, reviewers and auditors) with separation of duties.
- **Role desks.** Eight read-only daily-work pages (Owner, Reception, Academic,
  Teacher, Finance, Operations, Academic Setup, Configuration) project native data
  per role and link to guided command pages. Spec: [ROLE-DESKS.md](ROLE-DESKS.md).
- **Realtime.** Owned code emits no realtime events (pinned by
  `tests/security/test_realtime_non_emission.py`); `foundation_security`
  authorizes socket subscriptions deny-by-default.

## 5. Runtime

One runtime: Docker Compose (`product/`). It runs `web` (gunicorn plus the
idempotent first-run bootstrap), `worker`, `scheduler`, `socketio`, MariaDB
and two Redis services. The MariaDB and Redis service images are
digest-pinned; the application image is built locally from pinned upstream
commits (the exact pin set and what is locked are recorded in
[engineering/foundation-version-matrix.json](engineering/foundation-version-matrix.json)).
All six services use the `unless-stopped` restart policy, so a Docker
Desktop restart recovers the whole stack; the Stop script's `compose down`
is an explicit stop and still wins.

The product is bound to `127.0.0.1` only — no interface is opened for the
LAN or the internet. The selected multi-user deployment (owner decision
D15) reaches the ERP from authorized staff PCs through the owner's
Tailscale tailnet: Tailscale Serve on the central PC terminates TLS and proxies to
`127.0.0.1:8000`, tailnet-only (no Funnel, no public exposure). The current
Tailscale Serve instructions route web traffic and `/socket.io`
through the same HTTPS origin; the raw Socket.IO port remains loopback-only
and Funnel/public exposure is prohibited. Owned CI verifies an HTTP proxy-style
foreign-host request and the local Socket.IO healthcheck, but does not run
Tailscale Serve or prove an actual tailnet/WebSocket upgrade. Record that
real central-PC check as Owner/non-engineering evidence before claiming the
Tailscale path qualified.
The exact setup is in
[engineering/LAUNCH-RUNBOOK.md](engineering/LAUNCH-RUNBOOK.md), section
"Multi-user access (central server + Tailscale)".

The owner uses double-click scripts in `product/windows/`: Install, Start,
Stop, Backup and Repair for daily use, and Activate / Deactivate for the
guarded operational site-mode switch and rollback. A dedicated native
Course Owner user (not the built-in Administrator) configures policies in the
Configuration desk. `Activate TOEFL House ERP.cmd` first verifies the external
backup set, manifest, current Owner policy and scheduled task on the Windows
host; only then does it run `product/activate.py` inside the container for the
site-mode and business-policy mirror checks. Any failed site-mode verification
restores the previous settings. A failed deactivation verification restores
the previous settings the same way (the site stays ACTIVE rather than
half-deactivated).

## 6. Current state and open items

- The implemented lifecycle above is covered by the owned unit suite and by the
  real-site `Native lifecycle integration` workflow.
- **Owner values are not configured yet.** Every policy record ships empty and
  fails closed until the Course Owner enters it through the Configuration and
  Academic Setup desks. Backup activation additionally requires the Owner's
  local schedule, retention count, public recovery key and out-of-ERP custody
  plan.
- **Pinned dependency advisories (SEC-DEPS-01).** The pinned upstream stack
  carries known advisory matches, with per-finding dispositions in
  `engineering/evidence/sec-deps-01/`. The `Foundation runtime` audit fails
  closed on a newly untriaged match; it may pass while documented upstream
  fixes remain unavailable. A green audit therefore proves disposition
  coverage/runtime checks, not that every vendor advisory is patched or that
  production is ready. SEC-DEPS-01 remains the gate before any public-internet
  exposure. The selected desktop deployment is loopback-only with private
  Tailscale access, so public-edge exposure is not a current launch gate.
- **Backup** is a current local requirement: the Windows host script creates
  three native Frappe encrypted database/files artifacts and a fourth
  OpenPGP-encrypted site-config recovery artifact, verifies/copies the four
  artifacts plus manifest to a separate fixed local drive on the same
  computer, and checks Owner policy, Task Scheduler, hashes and retention.
  The unencrypted native site-config sidecar is never copied to the external
  backup set. Owned Product-image CI uses a disposable synthetic Owner key and
  a loop-backed separate filesystem to qualify artifact encryption/recovery,
  copy/return and restore into clean public/private file trees when that
  workflow passes (pinned Frappe restore otherwise overlays files without
  removing post-backup extras); it cannot qualify a real Windows drive,
  PowerShell/GPG installation, Task Scheduler, Owner key custody or the actual
  restore ceremony. Off-site/NAS/second-device/cloud backup is
  explicitly deferred future scope and is not a current release gate.
- **Production authorization remains REJECT.** The operational site-mode
  transition to PRODUCTION is a guarded mechanism, not release/launch approval.
