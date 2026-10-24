# Safe updates — engineering design (Issue #40)

Status: implementation complete and tested; **not activated for real school data**.
The customer channel ships disabled and the release gates from #12/#36 still
govern every production release. Nothing in this document changes the current
hold posture in `README.md`, `VALIDATION.md`, `LAUNCH-RUNBOOK.md` or
`HANDOVER-2026-10-20.md`.

## Threat model

The customer PC is not trusted to build software, and the provider is the only
party allowed to authorize a release. An attacker who controls DNS, the update
server, a downloaded file or a local file may try to:

* substitute a different image or a different version,
* re-sign a modified manifest with their own key,
* downgrade or skip a supported upgrade path,
* make the customer PC rebuild code from untrusted sources,
* destroy data by removing the database volume or restoring over a live site,
* start a migration that cannot be reversed without a verified backup.

The update engine answers all of these by refusing, not by repairing.

## Protocol

```
Windows launcher            product/update_engine.py (inside the image)
----------------            -------------------------------------------
Check for Updates
  -> HTTPS index          \
  -> update.json           >  signature + trust store + image identity
  -> update.json.sig      /   + compatibility + host facts + backup evidence
  -> image archive            => decision allow | refuse
Install Update (confirmed)
  -> engine preflight (again, fresh download)
  -> docker compose stop web worker scheduler socketio     (never -v)
  -> docker load <verified archive>
  -> engine apply: record census, bench migrate x2, census, apps, role desks
  -> docker compose up -d --no-build, HTTP health, journal completed
```

Failures:

| Outcome | Meaning | Host action |
| --- | --- | --- |
| `safe-abort` | the engine refused before the first migration | retag the previous image, start the previous version, journal `rolled-back` |
| `recovery-required` | a migration started, or the database changed | do **not** start the stack; journal `recovery-required`; show recovery steps |
| interrupted | the journal is `prepared`/`applying` on the next run | refuse and show recovery steps |
| `records_lost` / `apps_missing` / `role_desk_missing` | post-migration verification failed | `recovery-required`, never silently continue |

## Documents

| Document | Written by | Verified by |
| --- | --- | --- |
| `update.json` | `tools/release/create_update_bundle.py` | engine, RSA PKCS#1 v1.5 SHA-256 over the exact bytes |
| `update.json.sig` | same tool | engine (key id and algorithm must match the signed manifest) |
| `index.json` | same tool | Windows transport check only; never a trust decision |
| `trust-store.json` | provider, installed separately | engine (`provisioned`, key validity window, RSA key shape) |
| `backup-receipt.json` | `Backup TOEFL House ERP.ps1` | `product/activate.py` receipt validator (shared with activation) |
| `recovery-authorization.json` + `.sig` | Owner + provider support | engine, bound to the receipt SHA-256 |
| `journal.json` | Windows updater | engine (`journal_state` must be terminal) |

`release-manifest.json` (the customer *package* manifest) and `update.json` (the
signed *channel* manifest) are deliberately different documents: the package
manifest describes what the provider built, while `update.json` is the only
artifact the customer engine accepts. `create_update_bundle.py` is the bridge —
it re-reads and cross-checks the package manifest and the archive bytes, then
copies `release_status` and `production_authorization` verbatim, so signing can
never upgrade a test package into a production release.

`release_sequence` is the date-derived build number (`2026.11.01` →
`2026110100`). Both the Python engine and the Windows updater derive it with the
same rule and the same rejection table, pinned by tests on both platforms, so no
extra local state has to be trusted.

## Invariants

* The engine is standard-library only. It runs in the pinned image as
  `/product/update_engine.py`, on provider machines, and in the test suite.
* Preflight is read-only. It opens no network socket (`--network none`) and
  mounts the product folder read-only.
* The customer PC never builds Frappe, Node assets or an image. The only image
  bytes are the signed archive.
* No code path contains `docker compose down -v`, `docker volume rm`,
  `docker system prune`, `git reset --hard` or a restore over a live site.
* A migration failure never reopens the application automatically.
* Every customer-visible message is a stable code with English and Dari text in
  `product/windows/updater-strings.json`; the Windows GUI only renders catalogue
  text and never free text from a log or result file.

## Tests

| Suite | Covers |
| --- | --- |
| `tests/foundation/test_update_engine.py` | trust store, signature, image identity, channel, compatibility, preflight, backup evidence, recovery authorization, apply, protocol, catalogue |
| `tests/foundation/test_update_bundle.py` | provider signing with a real RSA key, index, tampering, wrong key, archive corruption, recovery authorization, packaging allowlists |
| `tests/foundation/test_windows_update_path.py` | GUI wiring, Owner confirmation, read-only preflight, prebuilt-only install, no destructive commands, packaging, bilingual catalogue |
| `.github/workflows/windows-customer-package.yml` | real Windows PowerShell parse, updater `-SmokeTest`, disabled-channel refusal in English and Dari with no download |

Run locally:

```bash
python3 -m unittest tests.foundation.test_update_engine tests.foundation.test_update_bundle tests.foundation.test_windows_update_path
```

Real Windows evidence (GitHub Actions, `windows-2022`): "Windows customer package
smoke" run `40082696503` on revision `28a8d9e` parsed every customer script with
the real PowerShell parser, ran the updater `-SmokeTest`, checked the two new
buttons through the WinForms smoke test, and built a synthetic customer kit where
**Check for Updates** refused the disabled channel with exit 3, printed the
English and Dari explanation, downloaded nothing and wrote a safe
`last-result.json`. "Owned suite" run `40082699700` (pull-request gate) passed on
the same revision.

## What still requires real hardware

* Windows 10/11 + Docker Desktop + WSL 2 with a real signed release on the
  provider channel.
* A real verified backup on a separate drive, with Owner key custody and a
  rehearsal restore, before any migration is allowed.
* Restarting after power loss between `docker load` and `bench migrate`, and
  between migration and the health check.
* Interrupting the HTTP download and re-running Check.
* Confirming that the previous image still starts after a `safe-abort`.

These are the acceptance items in Issue #12 and remain blocked until the owner
runs them on the real machine.
