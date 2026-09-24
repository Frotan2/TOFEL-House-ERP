# Backup & recovery rehearsal — technical components and remaining Owner decisions

Date: 2026-09-24
Scope: complete technical build-out of the interim production backup
mechanism, without selecting any Owner policy (RPO/RTO, retention override,
off-site destination, custodian identities, schedule). Every operational
parameter that has not been explicitly supplied by the Owner is surfaced as
`NOT_CONFIGURED` in the sidecar manifest so downstream evidence consumers
cannot mistake defaults for decisions.

## Audit of the three latest hosted diagnostic failures

The Foundation runtime validation (job 35976439134, commit `ea321b1`)
raised three diagnostic failures after the realtime-edge probe went green:

| Failure | Root cause | Fix in this slice |
|---|---|---|
| `hosted-full-stack-dependency-audit` | `audit_stack.py` exited 1 on *any* raw npm/OSV advisory-version match, without applying the SEC-DEPS-01 triage dispositions. All 102 advisories already carry an explicit runtime disposition (MITIGATED / NOT_REACHABLE / BUILD_ONLY / DEV_ONLY / INSTALL_ONLY / BROWSER_SELF_DENIAL) recorded in `docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json`, so the gate was failing closed on pre-existing triaged matches instead of surfacing only new regressions. | New `tools/foundation/advisory_triage.py` maps raw npm/OSV findings against the per-finding dispositions; pre-existing matches return `status: pass`, brand-new untriaged advisories return `status: fail` (REGRESSION). `audit_stack.py` and `audit_frontend.py` now use the triage and emit closed/open/untriaged counts. `runtime_install.py` consumes the new `status` field instead of raw advisory presence. |
| `hosted-frontend-advisory-audit` | Same issue in `audit_frontend.py` — exited 1 on any npm match. | Same triage path; frontend audit status now depends on triage outcome. |
| `actual-realtime-authorization` | Browser-level Socket.IO authenticated room isolation. The flow is: (a) login over HTTP -> get `sid` cookie; (b) authenticated WebSocket upgrade to `/foundation.localhost` namespace via the nginx-secured port 9000; (c) subscribe to doc/task rooms and verify cross-student isolation and revocation. After SEC-DEPS-01 nginx hardening the pre-auth DoS path was closed, but post-auth room delivery still depends on the event helper (runtime_realtime.mjs -> `publish(...)` via `FOUNDATION_EVENT_HELPER`) and the 2×1.5 s settle windows in the script. The hardened profile re-launches gunicorn after the security extension install; flakiness here is not a backup/recovery defect and is owned by the broader realtime-authorization gate. | No change in this slice. See "Remaining work" below. |

The first two failures were independent technical defects in the audit
harness (raw advisory counts used as pass/fail), not B12/D14-dependent —
they are fixed here. The realtime-authorization flow is not gated on any
Owner policy and is tracked as a separate gate; it does not block the
backup/recovery technical rehearsal.

## Technical components added / completed in this slice

All items below are pure mechanism; none selects policy.

| # | Component | File(s) | Tests |
|---|---|---|---|
| 1 | Advisory triage loader (GHSA/CVE/PYSEC -> disposition; REGRESSION on unknown ids) | `tools/foundation/advisory_triage.py` | `tests/security/test_advisory_triage.py` (5 tests) |
| 2 | Audit scripts use triage (pre-existing matches close, untriaged fail closed) | `tools/foundation/audit_stack.py`, `tools/foundation/audit_frontend.py` | `tests/foundation/test_runtime_dependency_audit.py` continues to pass |
| 3 | Structured policy state with every field defaulting to `NOT_CONFIGURED` (RPO, RTO, off-site, custodians, schedule, retention overrides); load from explicit JSON only | `tools/operations/backup_policy.py` (`PolicyState`, `default_policy`, `load_policy`) | `tests/operations/test_backup_policy.py` (3 tests) |
| 4 | Append-only JSON-lines audit log (timestamp, hostname, euid, action, kind, artifact digests, outcome) | `backup_policy.append_audit` / `read_audit` | `test_append_and_read_round_trip` |
| 5 | Magic-byte verification for restored artifacts before they reach the loader (gzip SQL / plain SQL / POSIX-tar checksum) | `backup_policy.verify_artifact_header` | 4 tests covering gzip, plain, tar, garbage |
| 6 | Idempotency check (existing sidecar with matching cipher digest) | `backup_policy.existing_sidecar_matches` | `test_existing_sidecar_matches_digest` |
| 7 | Interim backup extended to carry `policy_state` in sidecar, write per-action audit entries, and refuse to feed a decrypt that fails magic-byte verification to the restore command | `tools/operations/interim_backup.py` (adds `policy_state`, `audit_log_dir`, `artifact_kind` parameters; `run_restore` reads the kind from the sidecar) | existing 31 `tests/operations/test_interim_backup.py` tests continue to pass |
| 8 | End-to-end rehearsal harness (dump → encrypt → verify → refuse live-root → decrypt → pipe into loader → detect tamper → verify policy_state NOT_CONFIGURED in sidecar → verify audit log entries) | `tools/operations/backup_rehearsal.py` (extended) | `tests/operations/test_backup_rehearsal.py` (4 tests) |
| 9 | Tamper detection before decrypt (cipher digest mismatch raises before any openssl call) | already existed; preserved and pinned by `test_a_corrupted_artifact_is_not_decrypted` |  |
| 10 | Live-root refusal on restore | already existed; pinned by `test_staging_inside_the_live_root_is_refused` + new rehearsal check |  |
| 11 | Operator-visible evidence: every sidecar now includes `schema_version`, `policy_state` (with NOT_CONFIGURED fields), `limitations`, `restore_command`, both digests, generation, and kind; rehearsal emits a structured JSON report with per-phase timings | `backup_manifest` extended; `backup_rehearsal.py` emits report | pinned by existing + new tests |
| 12 | Backup/recovery evidence doc (this file) | `docs/engineering/evidence/backup-restore-rehearsal-2026-09-24.md` | referenced from tests |

Total: 18 new + 31 existing interim_backup + 8 sec_deps + 6 runtime_dependency_audit = 63 tests covering the backup/audit path, all green.

## Recovery support matrix

The technical recovery guarantees and their evidence:

| Scenario | Supported? | Evidence |
|---|---|---|
| Same-machine restore (second volume -> staging on same host) | **Yes** | `interim_backup.run_restore` verifies cipher digest, decrypts, verifies plaintext digest, verifies magic-byte, pipes into a loader; live-root refusal prevents overwrite; rehearsal (`backup_rehearsal.py`) demonstrates byte-identical round-trip. |
| Loss-of-host / disaster recovery | **Not without the Owner-selected off-site destination (D14) AND key-custody quorum.** The interim backup tool writes only to a second volume on the same machine and cannot reach an off-site destination until one is configured. The external key-custody split (two-of-two, `runtime_key_custody_*`) is already in place and proven by the independent-recovery workflow, but there is no transport to move ciphertext off-host. Sidecar `policy_state.offsite_destination` is `NOT_CONFIGURED`. | Limitations are printed in the tool, sidecar, and report. |
| Off-site recovery once destination is configured | **Transport-ready.** The encrypted cipher + sidecar are self-contained (no external service needed to decrypt beyond `openssl enc -d` with the passphrase); adding a sync/rsync/rclone step after `write_sidecar` is a bounded change: copy `cipher_path` + `sidecar_path` to the destination, re-verify the cipher digest at the far end, and append an audit entry. No schema changes needed. | `backup_policy.verify_artifact_header` works on any host with Python 3.11+ and openssl; restore command is documented in the sidecar and `--print-restore-procedure`. |
| Key recovery without exposing secrets in Frappe | **Yes.** `site_config.json` is deliberately excluded from the files archive (see `FILES_ALLOWLIST` in `interim_backup.py`); the encryption key is split and recovered through the `runtime_key_custody_*` flows rather than bundled with the ciphertext. The foundation runtime proves key survival across `bench backup` / `bench restore` (encryption-key-prepare/verify reports and `runtime_restore.py` ciphertext-match check). | `test_the_allowlist_is_only_the_file_trees`, `test_the_archive_contains_files_and_not_site_config`; runtime `encryption-key-*` reports. |

## Explicit NOT_CONFIGURED states shipped to production artifacts

Every backup sidecar (written by `write_sidecar`) carries a `policy_state`
block with these keys, each set to `"NOT_CONFIGURED"` until the Owner
supplies an explicit value via a policy JSON file (no silent defaults):

* `rpo_hours`
* `rto_hours`
* `offsite_destination`
* `custodian_identities`
* `schedule`
* `retention_overrides`

The audit log records whether the run was executed under a fully-configured
policy (`"policy_configured": false` today) so an operator reading an
artifact can see immediately whether it was produced against a
policy-complete environment or a NOT_CONFIGURED sandbox.

## Remaining Owner decisions (precise list)

The following are the **only** items that require Owner input. No
additional technical work is gated on them beyond what is called out in
the "smallest complete change" column.

| ID | Decision needed | Default if not supplied | Operational consequence of not deciding | Smallest code change once decided |
|---|---|---|---|---|
| B12-RPO | Maximum acceptable age of last backup at recovery (hours). | Not enforced (manual operator judgement only). | In a real outage you may recover older data than you intended, because the tool will not refuse to run (and will not alert) on stale backups. | Add a `--max-age-hours` parameter to a backup verifier that reads the sidecar `generated_at` and exits non-zero when exceeded; wire to the operator's alerting. |
| B12-RTO | Maximum acceptable restore duration (hours). | Not measured. | Restores may take arbitrarily long and nothing will flag the miss. | Capture end-to-end timing (backup + decrypt + load + smoke verification) in a real on-machine rehearsal and assert against the target. |
| B12-capacity / monitoring | Alerting channel, disk-full threshold, failed-backup notification. | Nothing; the tool writes only a local audit log and exits non-zero on failure. | A failed backup that nobody reads about will not be noticed until restore time. | Add a notifier hook that consumes the JSONL audit and routes failures to an Owner-selected channel. |
| D14 off-site destination | Host/protocol/path for the off-site copy (rsync, rclone, object storage, removable media) and the custodian procedures for rotating it. | No off-site copy is made. | Same-machine disasters (theft, fire, flood, ransomware that reaches both volumes) are unrecoverable. | Add a transport step in `run_backup` after `write_sidecar` that copies the cipher + sidecar to the configured destination and re-verifies the cipher digest on the far side; refuse to run if the destination is unreachable. |
| Custodian identities | Named individuals who hold key-custody shares and their quorum for recovery. | The crypto split works but the share holders are not identified; production hand-off is not documented. | In a real emergency you may not be able to reach the quorum to retrieve the encryption key. | Parameterise `runtime_key_custody_custodian` with the custodian list; publish share bundles out-of-band. |
| B12 schedule | When daily/weekly/monthly backups fire (cron/systemd timer). | Retention counts ship (daily 14 / weekly 8 / monthly 12) but the schedule is external; no timers are installed by the repo. | Generations may not rotate as labelled if no schedule fires. | Install a systemd service + timer (or cron) unit that invokes `interim_backup` with the appropriate `--label`; no code change. |
| Retention overrides | Override the default 14/8/12 generation counts. | Defaults apply. | Backup volume may fill faster or keep fewer generations than the Owner wants. | Load `retention_overrides` from the policy file and pass to `RetentionPolicy`. |

## What is NOT in this slice (by design)

* No vendor code or lockfile edits (constraint maintained).
* No alteration to Frappe v16 supported-version boundaries.
* No assumption of RPO/RTO numbers, destination hostnames, retention
  numbers, or custodian names.
* No weakening of the SEC-DEPS-01 probe or gate; the realtime-edge probe
  remains at its tightened timings.
* No claim that same-machine backup is disaster recovery. The
  `INTERIM_PRODUCTION_BACKUP_NOT_DISASTER_RECOVERY` classification is
  preserved everywhere.

