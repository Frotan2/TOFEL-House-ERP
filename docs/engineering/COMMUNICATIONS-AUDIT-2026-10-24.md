# Mission 5 — Communications, Notifications & Secure Self-Service Portals
## Audit of Existing TH Alerting Policy, Guardian Lifecycle, Native Permissions & Event Sources
**Date:** 2026-10-24  
**Branch:** arena/82235d06-tofel-house-erp  
**Auditor:** Senior Product Engineer (Institutional Notifications)

### 1. TH Alerting Policy — Existing Surface

- **Doctype:** `TH Alerting Policy` + child `TH Alerting Policy Version` (versioned, append-only, hash-chained via `TH Configuration Operation`/`TH Configuration Audit Event`).
- **Authority:** `business_policy` → Course Owner only (fixture: `Role` Course Owner write; General Manager/Academic Manager read).
- **Governing resolver:** `toefl_house.operations.alerting.governing_alerting_policy(on_date)` — fail-closed (no row / Retired / no effective version → `{}`).
- **Version terms:** `channel_kind` (Email/Webhook/Dashboard — SMS absent deliberately), `receiver_reference` (≤140 chars), `retention_days` (1–3650), optional `escalate_after_minutes` (1–525600), `reason`.
- **Controller:** `operations/doctype/th_alerting_policy/th_alerting_policy.py` — refuses any write outside `configuration.rules.command_context`, validates `code/title/status`, validates every row via `alerting.validate_terms`, enforces no duplicate `effective_from` and `superseded_on` > `effective_from`.
- **Operational gap:** Single receiver per version; no per-event-type routing, no severity model, no timing/retries/escalation/disabling per event, no durable notification ledger, no delivery state machine. Observability module (`toefl_house.observability`) is receiver-free by design (RECEIVER BOUNDARY) — generates conditions, never delivers.
- **Native delivery mechanisms available but not wired:** Frappe Notification/email, Webhooks, `publish_realtime` (blocked by `foundation_security.realtime` guard — deny-by-default authorization). SMS/WhatsApp have no native mechanism — absent correctly.

### 2. Guardian Lifecycle Configuration

- **Doctype:** `TH Guardian Lifecycle Policy` + `TH Guardian Lifecycle Policy Version` — same versioning/audit pattern as Alerting.
- **Version terms:** `delegation_window_days` (1–3650), `pre_admission_proxy` (Allowed/Refused), `consent_evidence` (Link/Attachment/Both), `consent_expiry_days` (1–3650), `records_recording_rights` (≤2000 chars).
- **Resolver:** `governing_guardian_lifecycle(on_date)` — fail-closed.
- **Current posture:** Configuration carrier only — no runtime consumer. Advanced guardian features deliberately deferred via `SEC-GUARDIAN-01` containment (`foundation_security.guards.validate_guardian_scope` enforces single Guardian identity, exact Student Guardian links, exact User Permission on Guardian/Student/Customer, strict Website/Education/System Settings, no DocShare). Tests pin zero policy-carrier references in `foundation_security`.
- **Operational gap:** No portal, no consent ledger, no revocation, no age-privacy enforcement, no record-level guardian authorization.

### 3. Native User Permissions & Identity

- **Student link:** `Student.customer` (mandatory for guardian scope), `Student` child table `guardians` (Student Guardian: `guardian` → Guardian, `parenttype`=Student). `Guardian.user` → `User`.
- **Branch isolation:** `permissions._user_branches` / `_branch_condition` / `branch_has_permission` / `query_*` — users with `User Permission` on `Branch` are scoped; Administrator is unrestricted. Roster truth is `Student Group Student` (active=1) → `Student Group.th_branch`. Branch scoping composes with synthetic guards.
- **Student scope guard:** `foundation_security.guards.validate_student_scope` / `validate_guardian_scope` — strict session validation. `validate_user_enabled` revokes disabled users on every request (no Frappe native re-check).
- **Portal-relevant natives:** `Student`, `Student Applicant`, `Program Enrollment`, `Student Group`, `Course Schedule`, `Student Attendance`, `Fees`, `Sales Invoice` (via custom `th_placement_case`), `Item`/`Bin` (book stock via `Item Group`=Books), `Assessment Result` (grades), `Course Enrollment`, `TH Announcement` (new).
- **Finding:** No Student ↔ User direct binding exists natively; reception resolved this via email/customer. Student portal must resolve `student` from session user via `User.email` → `Student.student_email_id` + verified `Customer` + roster membership + active Branch permissions — all fail-closed.

### 4. Native Event Sources for Operational Notifications

| Required notification | Native source (pinned) | Current generation |
|---|---|---|
| Overdue tuition | `Fees` (outstanding_amount, due_date, docstatus=1), `Sales Invoice` outstanding | None — desk shows counts, no condition |
| Pending academic approvals | `TH Admission Decision` (status Draft/Review/Approved/Conditional), `TH Assessment Policy` readiness incomplete | None |
| Incomplete attendance | `Course Schedule` (schedule_date ≤ today) with missing `Student Attendance` per roster | None |
| Class changes | `Student Group` (`th_class_start_date`, `th_class_end_date`, `th_branch`, `th_class_status` transitions), `Course Schedule` (from_time/to_time/room/instructor changes via Version) | None |
| Low book stock | `Item` (item_group=Books, disabled=0) + `Bin` (actual_qty vs reorder_level) | None |
| Scheduling conflicts | Overlapping `Course Schedule` for same `student_group` or same `instructor`/`room` on same `schedule_date` | None |
| Authorized system alerts | `Error Log` (unseen), `RQ Job` (failed), `Scheduled Job Type` (stopped), `Scheduled Job Log` (Failed), ping_ok | `observability.summarize_snapshot` + `evaluate_alert_conditions` — already generates conditions (RECEIVER BOUNDARY preserved) |

### 5. Decisions for Mission 5

- Preserve fail-closed receivers: new notification dispatch is disabled until Owner configures dispatch rules and notification `status` workflow is validated. External SMS/WhatsApp channels remain no-op providers until Owner enables them and supplies credentials out-of-band (never stored in code/fixtures).
- Preserve `SEC-GUARDIAN-01` containment: Guardian portal runs *behind* `validate_guardian_scope` + per-record consent/revocation checks; portal disabled by default (Owner approval + verified Guardian identity required).
- Student portal similarly disabled by default; activation requires Owner enable + valid student linkage.
- All new access paths are deny-by-default; every read allow-lists fields and scopes by verified student ownership, never by caller-supplied `student` filter.
- New DocTypes are configuration/operational only — no HRMS/Finance payroll side-effects, no synthetic-record leakage.

