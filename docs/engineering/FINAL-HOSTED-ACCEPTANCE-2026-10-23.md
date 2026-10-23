# Final hosted product acceptance — 2026-10-23

**Decision: NOT AUTHORIZED FOR PRODUCTION (NO-GO).** This is an executable hosted qualification plan, not Owner-machine evidence. No real customer data, Docker volumes, backups, policies or credentials will be touched.

## Tests executed for the same Git SHA

The workflows below are triggered together by this controlled acceptance revision. Each must finish PASS **on this exact SHA** before its hosted gate can be marked qualified.

| Gate | What it actually exercises | What it cannot qualify |
| --- | --- | --- |
| Owned suite | Ruff, full Python tree, Node role-desk and UI tests | Live database or real employee use |
| Native lifecycle | Real disposable Frappe/ERPNext/Education/HRMS/MariaDB/Redis, native commands, HTTP sessions, independent-role negative cases, financial ledgers, teacher compensation, encrypted isolated restore | Owner Windows, customer history or physical drives |
| Final hosted business receipt verifier | Requires executed native check receipts for placement, admission, enrollment, classes, attendance, tuition, role desks, branch permissions, compensation and CSRF/access control; refuses failed, duplicate, absent and cross-SHA evidence | End-user UI ergonomics, book-sales end-to-end, every real-world edge case |
| Foundation runtime | Hardened dependencies, security, permission and runtime probes | Live-user security authorization or guarantee of no vulnerabilities |
| Product image | Docker Compose, real image build, synthetic first boot, restore/restart/rollback and proxy safety contracts | Docker Desktop/WSL2 on Owner PC |
| Windows customer package smoke | Windows host GUI initialization, synthetic installer/launcher, damaged-image refusal, package allowlist | Real Docker Desktop, multi-GB image import and reboot on customer Windows |

## Required Owner and operational gates (not remotely executed)

1. Preserve the current operational installation and every existing backup and password. Only **Check This PC** may be used under the Owner preservation/restore hold.
2. Use a **separate clean/disposable Windows PC**, a provider-approved package and strictly synthetic students/fees to verify install, login, Stop/Start, Windows reboot, non-destructive Repair and persistence.
3. Verify all daily user roles interact correctly on separate staff logins, including enrolment, attendance, payment posting, book sales/inventory and reporting. A synthetic hosted receipt is **not** evidence of these manual end-user interactions.
4. Keep Owner backup/retention, Task Scheduler, physical local backup drive, recovery-key custody and isolated Owner recovery **ON HOLD** until formally authorized; never restore over the working site.
5. Separately verify access from real Tailscale staff devices without internet-public exposure and retain redacted evidence.
6. Obtain explicit release authorization after all gates. Do not mark issue #12 closed based on CI alone.

The evidence file `.foundation/placement-evidence/final-hosted-acceptance.json` is generated only after the native acceptance suite actually ran. It explicitly records Owner Windows NOT_VERIFIED, backup HOLD and production REJECT. The result must be read together with workflow run conclusions; this document itself never claims a pass.
