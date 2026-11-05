# TOEFL House ERP — Windows Owner Morning Verification

**Status: Engineering candidate only. Production authorization: REJECT / NO-GO.**

This guide separates work an engineer can do in GitHub from the independent physical-Windows acceptance only the Owner/operator can witness. It must never be read as permission to reinstall, update, reset, restore, or activate the existing Owner installation.

## 1. What engineering can demonstrate remotely

For a proposed release **exact full commit SHA**, capture:

- Owned suite, Native lifecycle integration, Foundation runtime, Product image and Windows customer package smoke — all **completed/success on the same exact SHA**.
- Publisher identity, the signed customer installer and its release manifest, and independently verifiable artifact hashes. An unsigned CI TEST EXE is *not* a customer release.
- Isolated test results and failure logs for financial integrity, role separation, Windows startup refusal and safe receipt handling.
- The current PR review and any still-open release blockers; a successful check on an ancestor does not qualify the final image.

### Installed-image receipt protection being verified

The Windows identity writer must:

1. Create a first-install receipt once without overwriting an existing one.
2. Use an atomic replacement with a previous-receipt backup for signed updates.
3. Read back and verify the new receipt before deleting the previous receipt backup.
4. Retain the previous receipt backup when replacement or read-back fails.
5. Refuse to call an incomplete signed-update journal completed.

CI now includes a Windows PowerShell 5.1 synthetic fault-injection test. It never uses the Owner site. This is source/package acceptance, **not** proof of a signed customer update on physical Windows.

## 2. What the Owner may safely do on the preserved Windows PC

**Current preservation/recovery HOLD: read-only only.**

1. Open the *existing* TOEFL House ERP launcher (do not install or download a replacement).
2. Choose **Check This PC**.
3. Use **Copy Safe Support Status** if support requests a summary.
4. Record the local date, and whether the launcher reports a healthy, missing, or inconsistent site/volume. Redact any identifying information before sharing.
5. Stop and report an error. Do **not** attempt an automatic repair, force Docker reset, reinstall, make a backup, change Owner policy, run a restore, start an update, or activate Production as a workaround.

Never share passwords, identity receipts containing private environment details, raw logs, database contents, encrypted backup archives, recovery keys, or screenshots showing secrets.

## 3. Separate disposable Windows acceptance (not the Owner PC)

A provider or authorized tester must use a separate **clean Windows 10/11 + Docker Desktop + WSL2 machine**, with an independently verified test installer and exclusively invented students/transactions.

| Test gate | Required observed evidence | Status |
| --- | --- | --- |
| Installer authenticity | Trusted publisher signature, exact SHA and manifest, clean graphical install | NOT YET PHYSICALLY QUALIFIED |
| Lifecycle | First boot, login, Stop/Start, Windows reboot, safe repair, preserved test identity | NOT YET PHYSICALLY QUALIFIED |
| Roles | Owner, General Manager, Finance Manager, Academic Manager, Receptionist, Instructor plus denied cross-role access | NOT YET PHYSICALLY QUALIFIED |
| Native transactions | Placement, admission, tuition/Fees, receipts, cash handover, book sale/return, refunds, payroll and GL reconciliation | NOT YET PHYSICALLY QUALIFIED |
| Recovery | Approved encrypted separate-drive backup, custody and independent isolated restore with correct authorities | NOT YET PHYSICALLY QUALIFIED |
| Staff access | Real permitted/denied remote clients, Socket.IO/WebSocket, no unintended public ports | NOT YET PHYSICALLY QUALIFIED |
| Release governance | Current-head security/release checks, independent review and explicit Owner sign-off | NOT YET APPROVED |

Record only redacted screenshots and safe gate results in the existing acceptance evidence procedure: [product/windows/VALIDATION.md](../../product/windows/VALIDATION.md). Existing historical synthetic checks are evidence for their **own** recorded revision, not the final release candidate.

## 4. Decision rule

- If the preserved Owner PC reports any mismatch or missing identity/volume, **STOP**. Do not generate a replacement identity by trusting a local image label.
- If any exact-head CI gate, signature, real Windows journey, recovery or security review is not complete, **NO-GO**.
- If production authorization is absent, **NO-GO**, even when the application opens successfully.
- The signed update channel and any public Cloudflare exposure remain disabled until independently qualified and authorized.

Related release trackers: [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12), [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35), [#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36), [#71](https://github.com/Frotan2/TOFEL-House-ERP/issues/71), [#115](https://github.com/Frotan2/TOFEL-House-ERP/issues/115), [#123](https://github.com/Frotan2/TOFEL-House-ERP/issues/123).

**Handoff:** deliver the exact tested SHA, linked CI receipts, code-review decision, the signed artifact verification (if one exists), and a list of remaining real-world gate owners. Never mark a gate PASS on planned action alone.
