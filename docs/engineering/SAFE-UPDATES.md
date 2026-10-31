# Safe updates — engineering design (Issue #40)

Status: hardened implementation under qualification; **not activated for real school data**.
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
  -> HTTPS index
  -> update.json + update.json.sig
  -> engine authorize "preflight"   signature + trust store + compatibility
                                    + host facts + backup/recovery evidence
                                    => allow | refuse, plus a manifest transaction
  -> image archive                  only after the manifest phase allowed
  -> engine authorize "authorize"   re-reads every mutable fact, verifies the
                                    archive identity, issues a 30-minute
                                    `authorized` transaction
Install Update (confirmed)
  -> docker load <archive verified by the installed engine>, with services running
  -> verify candidate image ID, restore the installed Compose image tag
  -> candidate engine preflight/authorize/recheck using the live host observer
  -> docker compose stop web worker scheduler socketio     (never -v)
  -> tag the verified candidate image for Compose
  -> candidate engine apply: loads its `authorized` record from durable state,
     re-verifies the manifest signature, archive hash and identity, backup
     receipt, recovery authorization, installed image identity and labels,
     journal and host state, then records the census, `bench migrate` x2, the
     census again, apps, orphan rows and role desks
  -> guarded docker compose up -d --no-build --no-deps (application services only), HTTP health, journal completed
```

`apply` accepts nothing but an `authorized` transaction, and a transaction can
be used once. Authority is **not** carried in the caller's document. When a
phase allows, the engine writes an HMAC-authenticated record into a durable
state folder (`data/updates/engine-state`) that every update run on this PC
shares. `authorize` and `apply` load the record back by identifier and verify
the engine's own authentication tag, so a fabricated or edited `authorized`
document is refused (`transaction.unknown` / `transaction.tampered`) before any
migration runs. The one-use marker is written to the same durable folder, so a
replay from a later run folder is refused (`transaction.replayed`).

The installed engine can use the earlier transaction protocol. Its signed
archive authorization is only permission to import candidate image bytes; it
does not authorize a migration. For every Check, the Windows launcher pins the
installed image by immutable ID and executes a restricted, offline, read-only
file-presence probe to distinguish legacy engines from broker-capable engines.
Only a broker-capable image receives the Docker socket mount; this distinction
is preserved for its second archive authorization at Install. Unexpected
probe failures refuse the operation, never silently downgrade to legacy mode.
The update engine entrypoint may repair its private request/transaction
directories, but must not chown mounted customer sites or logs before the
independent preflight. The candidate must issue a fresh transaction
after independently observing the running Docker containers, database volume,
image, journal and site files. It then rechecks immediately before service
stop. The previous image ID is retained for a held recovery path. Any import,
identity or tag failure records a recovery hold and never starts Compose.

At apply time the engine re-reads signed release, image and recovery evidence.
Host facts are obtained through the authenticated local broker described below,
not through the request's earlier `host`, `installed` or `journal_state` fields.
Those fields are rejected in apply requests. Changed evidence refuses the
update before migration; a failure after migration starts requires recovery.

### Independent live host observation (2026-10-25)

`product/update_host.py` runs a small root broker inside the ephemeral engine
container. It accepts only a fresh nonce over a fixed Unix socket; Linux peer
credentials authenticate the root process. It exposes no API URL, shell command,
Docker mutation or caller-selected path. Its fixed GET requests inspect the
seven existing product containers, the original web image, the current image
tag and the exact database volume/mount. The actual journal and site files are
read from the fixed, read-only `/product-root` mount. No credential contents or
raw Docker inspect documents are returned or logged.

The raw Docker socket is mounted only for this broker. A `readonly` mount
**does not** restrict Docker API operations. The broker therefore refuses to
start unless socket ownership and permissions deny the frappe engine account
access. The broker socket remains root-owned and restricted to that account's
group; the client also checks the server's actual root UID via `SO_PEERCRED`.
It is private to the ephemeral container and is not exposed over TCP. This
privileged boundary requires independent security review and Docker Desktop
qualification; unit tests are not authorization to enable the channel.

Transaction schema 2 binds storage/container/mount identity and hashes of
`db.env` and `site_config.json` to the authenticated authorization. Old schema
1 transactions cannot be applied; a fresh complete check is required. All
services must still be running at preflight/authorize and at the new `recheck`
phase immediately before any host mutation. After the intentional stop/import,
the actual original application containers must be stopped, the DB/Redis must
still run, the loaded tag must match the verified candidate config digest and
labels, and the on-disk journal must say `applying` for this exact transaction
and target version. Docker containers for engine steps are selected by immutable
image ID after the check. Missing/unavailable observations never fall back to
caller-supplied booleans. Host state is queried after evidence hashing, before
each migrate replay, and after data/role verification.

A structured apply exit 5 must reach the launcher's failure handler. It is not
an engine transport error that can be discarded. Any stop/import/apply failure
leaves `recovery-required`; even `safe-abort` does not automatically restart
Compose, since the refusal may mean storage vanished or was replaced. A
best-effort tag restoration is not recovery proof. The journal `rolled-back`
phase and the catalogue entries `updater.rollback_done` /
`updater.rollback_blocked` are reserved for a future support-directed recovery
step; no current code path restarts services automatically or reports an
automatic rollback. Only a successful apply can
reach the guarded Start path, which repeats the existing-installation preflight
before Compose. It starts only the four application services with `--no-deps`,
so bootstrap and DB/Redis are not recreated after the verified census. The
current image ID must still match the verified candidate. No restore or
deletion is performed automatically.

Evidence added for this boundary: independent host-state mutation tests, a
real Unix HTTP transport on unrestricted Linux runners, and a root/nobody
privilege probe using a synthetic Docker HTTP socket. That probe proves raw
socket denial and the restricted broker protocol. The Product-image pipeline
also runs a read-only probe against the actual Docker daemon of its disposable
synthetic deployment. Release-critical `fix/**` branches qualify through the
same image pipeline before integration. These checks are **not real Docker
Desktop, Windows update, Owner backup/restore, or production qualification**.

Failures:

| Outcome | Meaning | Host action |
| --- | --- | --- |
| `safe-abort` | the engine refused before the first migration | best-effort retag of the previous image, **no automatic restart**, journal `recovery-required`, bilingual recovery steps; support directs recovery from the retained image and the verified backup |
| `recovery-required` | a migration started, or the database changed | do **not** start the stack; journal `recovery-required`; show recovery steps |
| interrupted | the journal is `prepared`/`applying` on the next run | refuse and show recovery steps |
| `records_lost` / `apps_missing` / `role_desk_missing` | post-migration verification failed | `recovery-required`, never silently continue |
| `identity_mismatch` | orphaned child rows grew across the migration | `recovery-required`, never silently continue |
| `counts_unavailable` | a mandatory count or integrity query was unreadable | refused before the first migration; a missing count is never evidence of preserved data |

## Documents

| Document | Written by | Verified by |
| --- | --- | --- |
| `update.json` | `tools/release/create_update_bundle.py` | engine, RSA PKCS#1 v1.5 SHA-256 over the exact bytes |
| `update.json.sig` | same tool | engine (key id and algorithm must match the signed manifest) |
| `index.json` | same tool | Windows transport check only; never a trust decision |
| `trust-store.json` | provider, installed separately | engine (`provisioned`, key validity window, RSA key shape) |
| `backup-receipt.json` | `Backup TOEFL House ERP.ps1` | `product/activate.py` receipt validator (shared with activation) |
| `recovery-authorization.json` + `.sig` + `-2.sig` | Course Owner **and** General Manager / designated recovery authority, each with their own offline key | engine, two-person schema-2: both signatures over identical bytes, bound to site, operation, backup receipt SHA-256 and a single-use request id |
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
  bytes are the signed archive. `Install TOEFL House ERP.cmd` and
  `Repair TOEFL House ERP.cmd` refuse with a bilingual `:packagemissing`
  message when the verified archive is absent; neither contains a source-build
  fallback any more, and a contract test pins that.
* A release cannot waive its own safety requirements. A migrating manifest that
  does not require a verified backup and a restore rehearsal, that excuses
  `requires_verified_backup`, that switches recovery authorization off, or that
  claims a migration is reversible is rejected as `release.manifest.invalid`.
  Backup evidence must be at most 24 hours old and a recovery authorization at
  most 168 hours old, whatever the manifest says.
* No code path contains `docker compose down -v`, `docker volume rm`,
  `docker system prune`, `git reset --hard` or a restore over a live site.
* Authority is engine-issued and durable. The caller carries only an
  identifier between phases; `authorize` and `apply` load the record the engine
  wrote into `data/updates/engine-state` and verify its HMAC tag. A forged or
  edited `authorized` document, a changed installed image, a changed journal or
  volume, and a replay from another run folder each stop the update before the
  first `bench migrate`.
* A migration failure never reopens the application automatically.
* Two-person recovery authorization is enforced, not recorded.  A migrating
  update requires a schema-2 recovery document signed by two distinct
  trusted keys, bound in the trust store to one Course Owner and one General
  Manager or designated recovery authority, over identical document bytes
  bound to the site, the `site-update` operation, the verified backup
  receipt and a single-use `request_id`.  A single-signature (schema-1)
  document, a self-approval, two Owners, a swapped or forged signature, an
  unbound recovery key, an altered document, an expired window or a replayed
  request id is refused before any migration.  The request id is consumed
  when apply starts, so a failed or interrupted apply needs fresh approvals
  from both approvers.  The recovery request is marked consumed **before**
  the transaction-use marker is written, so a crash between the two writes
  cannot leave the same signed approval reusable with a new transaction.
  Provisioning a second recovery key with its approver
  binding is a migration requirement for existing single-key installations:
  until then, migrating updates are refused, by design.
* Emergency administrator recovery is separately controlled and is **not**
  two-person approved.  Direct use of `product/restore.py` on the production
  site, or any OS/container-level restore, bypasses application approvals
  by construction; it must be treated as an emergency-admin action, performed
  only under a separately documented Owner procedure, logged outside the
  application, and never presented as an approved two-person recovery.
  `product/restore.py` remains un-authenticated at its own layer and is used
  in CI only against disposable synthetic sites; production recovery must go
  through the two-person update-engine gate plus a disposable rehearsal.
* Every customer-visible message is a stable code with English and Dari text in
  `product/windows/updater-strings.json`; the Windows GUI only renders catalogue
  text and never free text from a log or result file.

## Tests

| Suite | Covers |
| --- | --- |
| `tests/foundation/test_update_engine.py` | trust store, signature, image identity, channel, compatibility, preflight, backup evidence, recovery authorization, manifest invariants (no waivers, evidence age), phase A/B authorization, authenticated authorization (forged/tampered/replayed records, changed installed image, journal and volume), strict census and orphan checks, apply, protocol, catalogue |
| `tests/foundation/test_update_bundle.py` | provider signing with a real RSA key, index, tampering, wrong key, archive corruption, recovery authorization, packaging allowlists |
| `tests/foundation/test_windows_update_path.py` | GUI wiring, Owner confirmation, read-only preflight, download-after-allow ordering, authorized-transaction-only apply, durable engine state mount, prebuilt-only install, no destructive commands, packaging, bilingual catalogue |
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
