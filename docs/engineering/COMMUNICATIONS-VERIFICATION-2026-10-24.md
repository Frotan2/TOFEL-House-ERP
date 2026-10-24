# Mission 5 — Verification evidence (synthetic)

**Date:** 2026-10-24  
**Branch:** `arena/82235d06-tofel-house-erp`  
**Suite:** `python -m unittest tests.operations.test_notifications_portals` (48 tests, OK)

Portals and external channels ship **disabled by default**. Enabling a portal or
channel is an Owner action (`TH Portal Configuration` / `portal_policy.set_portal_flags`).
Configuring a dispatch rule does not deliver anything until the rule is enabled
and a delivery attempt succeeds against a real provider.

## Configuration (Owner)

| Control | Default | Where |
|---|---|---|
| Student portal | **off** | `TH Portal Configuration.student_portal_enabled` |
| Guardian portal | **off** | `TH Portal Configuration.guardian_portal_enabled` |
| Dashboard channel | on (toggleable) | `dashboard_enabled` |
| Email channel | **off** | `email_enabled` |
| SMS channel | **off** | `sms_enabled` — stub provider until Owner-approved binding |
| WhatsApp Business | **off** | `whatsapp_enabled` — stub provider until Owner-approved binding |
| Per-event dispatch | **disabled**, no recipients | `TH Notification Dispatch Rule` (one row per event type) |

Event types: `overdue_tuition`, `pending_academic_approval`,
`incomplete_attendance`, `class_change`, `low_book_stock`,
`scheduling_conflict`, `system_alert`.

Each dispatch rule independently sets recipients, severity (`info` /
`warning` / `critical`), channel, delivery delay, max retries, retry delay,
escalation delay, and escalation recipients.

SMS/WhatsApp never assume credentials. `external_provider` exposes
`NotificationProvider.send()`; the built-in stubs return **failed**, not
delivered. A future approved provider is bound with
`register_provider("sms", impl)` after out-of-band credential provisioning.

## Durable notification states

Explicit only: `queued` → `delivered` | `failed` → `acknowledged`.

- New records always start `queued`.
- `delivered` is written only after the provider returns True.
- Failed deliveries increment `retry_count` up to `max_retries`, then stay `failed`.
- Acknowledgement is refused unless status is `delivered`.

## Portal journeys (synthetic)

| Journey | Result |
|---|---|
| Student portal disabled | PermissionError before any lookup |
| Authenticated student, own schedule/attendance/approved grades/fees/announcements | Scoped to verified `Student` for session user |
| Explicit `student=` IDOR (`STU-BOB`, predictable IDs, SQL-looking strings) | PermissionError |
| Guest | PermissionError |
| Guardian portal disabled | PermissionError |
| Verified children only | Other families never listed |
| Access without consent | PermissionError |
| `record_consent` then child attendance/fees/grades | Allowed for that child only |
| `revoke_consent` | Immediate deny on next read |
| Adult student (≥18) | Consent required even with verified relationship |
| Other guardian's child via ID | PermissionError |

Website routes `/student_portal` and `/guardian_portal` re-check enablement
server-side. When enabled, Guest is redirected to `/login`. Data never loads
from the page without the whitelisted, ownership-checked APIs.

## Privacy adversarial

- Caller-supplied student filters cannot widen scope.
- Allow-listed fields only (no contact dumps, no private files).
- Approved grades only (`Assessment Result.docstatus = 1`).
- Guardian finance/grades require verified `Student Guardian` + valid consent.

## What this does **not** claim

- No hosted Frappe site, no real SMS/WhatsApp credentials, no Owner-PC proof.
- Observability remains delivery-free (`RECEIVER BOUNDARY`).
- `SEC-GUARDIAN-01` containment is unchanged; the lifecycle policy still does
  not grant access by itself.
- Production authorization remains REJECT.

## Commands / modules

- `toefl_house.operations.notifications`
- `toefl_house.operations.portal_policy`
- `toefl_house.operations.external_provider`
- `toefl_house.operations.student_portal`
- `toefl_house.operations.guardian_portal`
