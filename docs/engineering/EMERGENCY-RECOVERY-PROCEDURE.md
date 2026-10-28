# Emergency database recovery procedure — TOEFL House ERP

Status: this procedure describes the emergency-recovery gate in
`product/restore.py`. It does not authorize a restore by itself. Every
production restore still needs the two approvals and the evidence described
below, and production activation remains a separate Owner decision.

## Part A — For the Course Owner (plain language)

### When is recovery permitted?

Only when the live system is genuinely broken or its data is lost or
corrupted, and a verified backup exists that is newer than the damage. A
restore is never a routine operation, never a way to "try something", and
never performed on a working system. If the system is working, do not
restore it.

### Who must authorize it?

Two different people, every time:

1. You, the Course Owner, and
2. the General Manager, or a person you have formally designated as a
   recovery authority.

One person alone cannot authorize a production restore, even if that person
holds all the passwords. Each approver signs the exact restore request with
their own key. If only one approver is available, the restore waits.

### What must be verified before anyone touches the live system?

- Which backup, exactly: its name and a fingerprint (SHA-256) of each of its
  three files, so nobody can silently substitute a different or older backup.
- A fresh backup of the live system as it is now, taken immediately before
  the restore, so the current data can be brought back if the restore is
  wrong. A restore without this fresh backup is refused by the system.
- That the restore was first rehearsed on a disposable test site, where
  possible, using the same backup.
- That no earlier restore is still unfinished (the system refuses a new
  production restore while an earlier one is marked unfinished).

### What happens if recovery fails?

The restore stops and the system reports a failure without revealing
passwords or backup keys. The fresh backup taken before the restore is the
way back: support restores that set instead, under a new two-person
authorization. Do not retry the same authorization — a failed or
interrupted restore spends its approval, and a retry needs fresh approvals
from both approvers.

### What you must never share

Backup passwords, database passwords, administrator passwords and recovery
keys are never sent in chat, email, screenshots or logs. Support will ask
for approvals, not for your passwords.

### What this procedure cannot prevent

A person with full administrator access to the host computer or the
containers can bypass the application's restore checks by restoring a
database directly. No application code can prevent that. That is why
administrator access to the host and to Docker must itself be limited to
authorized people and logged by the Owner. If you suspect such access was
used, treat it as a security incident and ask support to review the
audit records described in Part B.

## Part B — For authorized support staff (technical)

### Supported entry point

`product/restore.py` is the only supported restore adapter. It is shipped
in the customer image at `/product/restore.py`. There is no Windows restore
utility and no supported Docker restore command. Do not use `bench restore`
or a direct MariaDB import on a production site: those paths bypass the
gate, the pre-restore backup check, single-use consumption and the audit
log, and they must be treated as emergency-admin actions outside this
procedure, logged at the host level by the Owner.

### Payload

Stdin JSON only; no command-line arguments (any argument is refused).
Fields: `site`, `backup_set`, `encryption_key`, `db_root_password`,
`admin_password`, plus:

- `target`: `"disposable"` or `"production"`. Omitted means production.
  A disposable target is allowed only when the site name contains
  "restore" and is not the configured production site
  (`TOEFL_HOUSE_PRODUCTION_SITE`, default `toeflhouse.localhost`).
- Production only: `pre_restore_backup_set` (a distinct, complete backup
  set already present in the site's backup directory, taken immediately
  before the restore), `authorization` (the emergency-restore document),
  `authorization_signature_1`, `authorization_signature_2` (base64 RSA
  PKCS#1 v1.5 SHA-256 signatures over the canonical document bytes:
  JSON with sorted keys, compact separators, UTF-8).

### Emergency authorization document

Exact keys, no extras: `schema_version` (1), `document_type`
(`"emergency-restore"`), `site`, `target` (`"production"`), `backup_set`,
`backup_sha256` (per-artifact SHA-256 for `database`, `public_files`,
`private_files`, computed from the files actually present), `request_id`
(32 lowercase hex characters, single-use), `issued_utc`, `expires_utc`
(`YYYY-MM-DDTHH:MM:SSZ`), `approvals` (exactly two: one `course-owner`
and one `general-manager` or `recovery-authority`, distinct identities,
roles and key_ids).

### Trust store

The trust store is installation-controlled and is read only from the
`RESTORE_TRUST_STORE` environment variable — never from a path supplied
in the restore payload. If it is absent or unprovisioned, production
restores are refused. It uses the update trust-store format
(`toefl-house-erp-update-trust-store`, schema 1, `modulus_b64` /
`exponent_b64` keys, `approver_identity` / `approver_role` bindings),
and a restore key must carry the purpose `"emergency-restore"`. Update
keys (purpose `recovery-authorization`) do not authorize a restore.
Provisioning restore keys is an Owner decision: until both approvers'
keys are provisioned with that purpose, production restores are refused
by design.

### Order of checks (all before any mutation)

1. Payload shape, site equals the configured site, backup-set name safe.
2. Target classification (disposable sites never equal the production site).
3. Target backup artifacts present, regular files, inside the site's
   backup directory, no symlinks.
4. Production only: distinct pre-restore backup set present and complete.
5. Production only: authorization document, window, approvals, trust-store
   bindings, key purposes and validity, both signatures over the
   canonical document, artifact hashes matching the files present.
6. Production only: request_id not already consumed; no in-progress
   marker from an unfinished restore.
7. Only then: consume the request_id (exclusive file), write the
   in-progress marker and the `started` audit record, stage artifacts
   (hash-verified copies in a 0700 temporary directory; originals are
   never mutated by native decrypt), run native Frappe restore with
   `force=True` on the declared target only, then remove the marker and
   write `completed` or `failed`.

### Audit log

State directory: `RESTORE_STATE_DIR/<site>/` if set, otherwise
`<sites>/<site>/private/restore-requests/` (0700). Contents:
`audit.jsonl` (hash-chained JSON lines, 0600), one consumed file per
request_id, and `in-progress.json` while a production restore runs.
Audit records contain site, target, backup set, artifact hashes,
pre-restore set, request_id, approver identities/roles/key_ids and
outcome — never encryption keys, database passwords or administrator
passwords, and never signatures. Verify the chain by recomputing each
line's hash from the previous line; a rewritten or deleted line breaks
the chain.

### Interrupted, failed or repeated recovery

- A failed or interrupted restore still consumes its request_id. Retry
  only with a fresh authorization signed by both approvers.
- If `in-progress.json` remains after a process was killed, do not start
  another production restore. First verify no restore process is running
  (the native `site_restore` filelock is held only during a live
  restore), inspect the site's state, and only then remove the marker —
  that removal is an Owner/support decision, recorded outside the
  application audit log, since the adapter that would log it is the one
  being recovered.
- A repeated restore of the same backup after new data has been entered
  destroys that newer data. That is why request_ids are single-use and
  why the pre-restore backup is mandatory: the way back is the
  pre-restore set, under a new authorization.

### Independent verification after a restore

1. Confirm the audit log shows `completed` for the request_id, with the
   expected backup hashes and both approvers.
2. Confirm the target backup set files are unchanged (hashes match the
   audit record) and the pre-restore set is intact.
3. Confirm the site starts and staff can log in with their normal roles;
   spot-check a small number of known recent records (admissions,
   receipts, attendance) against the backup's date — a restore can only
   return data up to the backup, never data entered after it.
4. If any check fails, stop, preserve the pre-restore set, and escalate
   to the Owner before attempting another restore.

### Secrets handling

Secrets travel only on stdin (payload) and, inside the adapter, through
the existing safe GPG stdin transport and mode-0600 MariaDB option file.
Never put a secret in a command argument, a log line, a screenshot, a
ticket or a Git commit. Failure output is sanitized by the adapter; it
reports only safe exception classes, frames and path classes.
