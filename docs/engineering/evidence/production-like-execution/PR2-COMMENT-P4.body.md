
## P4 closed by execution — external key custody, retrieval and rotation

Continuing the gap-closure record on the active branch
`arena/01a0aafe-tofel-house-erp`. This PR's head branch is
`arena/01a0a9f7-tofel-house-erp` and this session is fixed to its own branch, so
again **no commit was pushed to this PR's head branch**; this comment records the
result. Prior comments cover the premise corrections (including the nonexistent
commit `d3705e6`), P1, P2 and P3.

P3 deliberately left `bench restore --encryption-key` unused so no key material
travelled, and asserted as an **expected failure** that the source-encrypted
field came back intact but undecryptable (`decrypts_on_target=false`). That
executed failure was the evidence that key custody is a separate requirement.
This is that requirement, executed.

### What was executed

Run **`35179445639`** at commit `252345e`, workflow *Foundation external key
custody* (`.github/workflows/foundation-key-custody.yml`) — conclusion `success`,
**three separate ephemeral VMs**:

| Job | Check run | Checks |
|---|---|---|
| `custodian` | `105068259227` | 10/10 pass |
| `operator` | `105068842511` | 29/29 pass |
| `recovery` | `105069423253` | 37 checks — 34 pass and **3 required failures** |

`mocks_or_simulations_used=false` in all three roles. The 3 non-passing checks
are the negative controls, which are *supposed* to fail.

### The correction that mattered

Frappe has **two** distinct keys, and conflating them would have produced
evidence that looked right and meant nothing:

| Key | Protects | Native mechanism |
|---|---|---|
| `encryption_key` | `__Auth` ciphertext | `frappe.installer.update_site_config` — the same call `get_encryption_key()` makes when it generates one lazily |
| `backup_encryption_key` | the backup artifacts | `bench backup` → `gpg --passphrase <key> -c`; `bench restore --encryption-key` → `gpg -d` |

`bench restore --encryption-key` **decrypts a backup**; it does **not** install a
site key. Verified against `frappe/commands/site.py` `_restore` and
`frappe/utils/backups.py` `decrypt_backup` at the pinned revision `988e54f3`.
An earlier reading assumed the flag installed the site key; untested, that would
have "restored with the source key" while never installing it.

### Retrieval was proved load-bearing *before* it was used

A custody rehearsal where the backup could have been restored anyway proves
nothing, so the recovery VM ran two **required failures** first, both on copies
of the dump:

| Attempt | Result | Frappe's own output |
|---|---|---|
| restore with **no** key | exit `1` | `Encrypted backup file detected. Decrypting using site config.` / `Decryption failed.` |
| restore with a **real key from the wrong epoch** | exit `1` | `Encrypted backup file detected. Decrypting using provided key.` / `Decryption failed.` |

The wrong-epoch control is stronger than a random string: it is a key custody
genuinely issued, same role, one epoch later, and it still cannot open the
artifact. Afterwards the staged dump was digest-verified **byte-identical** —
not a formality, since `decrypt_backup` renames the dump to `.gpg` and renames it
back in a `finally` block. Share-level controls also ran: neither channel alone
reproduces the fingerprint, and shares from different epochs do not either.

### The backup was encrypted at rest — asserted, not assumed

`bench backup --with-files` ran with System Settings `encrypt_backup=1`, and all
three artifacts were checked with `file`, which is the same test `bench restore`
applies before deciding to decrypt:

| Artifact | Bytes | `file` reports |
|---|---|---|
| `database.sql.gz` | 245422 (`0f337270c29dcf5e…`) | `PGP symmetric key encrypted data - AES with 256-bit key salted & iterated - SHA512` |
| `private-files.tar` | 301 | same |
| `public-files.tar` | 298 | same |

That assertion is load-bearing: frappe's `backup_encryption()` catches a gpg
failure, prints *"Files are stored without encryption"* and **continues**, so an
`-enc` filename is not by itself evidence of encryption.

The payload left through an explicit five-file allowlist. Frappe also writes
`…-site_config_backup-enc.json` beside the dumps; **gpg does not cover it**, so
despite its `-enc` name it holds `db_password` and both keys in clear text, and
it was excluded. Seven generated secrets were scanned across every staged byte:
zero leaks.

### The limitation P3 asserted is closed

| | P3 run `35170062251` | P4 run `35179445639` |
|---|---|---|
| `decrypts_on_target` | **`false`** | **`true`** |
| why | no key travelled with the backup | key retrieved from separate custody channels |

Ciphertext sha256 `3ecadda32e98f718…` is **identical** to the operator's record,
the plaintext digest matches, and `plaintext_published=false` — the value is
compared by digest, never recorded. Also recovered: 6 ToDo and 6 Note records
with matching name digests, the private (547 B) and public (546 B) files with
matching on-disk digests and their File documents. The recovery VM set its **own**
Administrator credential with native `bench set-admin-password`
(`operator_admin_password_transferred=false`), and confirmed it did not already
hold the operator's database.

### Rotation, composed because Frappe has no command for it

1. **Native consequence first.** After installing the epoch 2 site key, epoch 1
   ciphertext stopped decrypting with frappe's own message: `Encryption key is
   invalid! Please check site_config.json … If you have recently restored the
   site, you may need to copy the site_config.`
2. **Re-encryption** through `decrypt(…, encryption_key=old)` →
   `set_encrypted_password` → `update_site_config`: ciphertext changed
   (`3ecadda3…` → `33a39055…`), plaintext digest unchanged, value reads back.
3. **Boundaries, three ways.** Epoch 1 fails · epoch 2 succeeds with matching
   digest · a key custody never issued fails.
4. **Backup key too**, then proved cryptographically instead of paying for a
   second full restore: a new backup under epoch 2 is detected as AES, opens with
   the **epoch 2 key** (gpg exit 0, 245301 bytes) and is **rejected by epoch 1**
   (gpg exit 2).

### Destruction left no plaintext key behind

The operator destroyed itself with native `bench drop-site --no-backup` (database
`_9b96f4509c396e9c` present then absent, site directory and both files gone),
then went further than P3: `drop-site` archives the site directory, and that
archived `site_config.json` holds **both plaintext keys**, so the archive was
removed and the removal verified. The whole lab and `.foundation` tree were then
scanned for all four keys: `survivors=[]`, `clean=true`. Keys were masked with
`::add-mask::` before any command could echo them and passed to in-bench scripts
by environment, never argv.

### Three separate machines, verified rather than assumed

| Identifier | Custodian | Operator | Recovery | Role |
|---|---|---|---|---|
| `kernel_boot_id` | `ada63831-…` | `98d290d1-…` | `963ba2b7-…` | **REQUIRED** — differs |
| `runner_name` | `…1000002471` | `…1000002472` | `…1000002473` | **REQUIRED** — differs |
| `dmi_product_uuid` | `9eef88c7-…` | `44738f95-…` | `08428be9-…` | corroborating — differs, all 3 pairs |
| `hostname` | `runnervmlun5p` | `runnervmlun5p` | `runnervmlun5p` | OBSERVATION ONLY — matches (`35143620884`) |
| `docker_daemon_id` | absent | `a4efb8b6-…` | `a4efb8b6-…` | OBSERVATION ONLY — shared (`35168111875`) |

Verdict `SEPARATE MACHINES`, all three pairs, no missing required identifier.

### What this does **not** prove

Custody here is a **bounded split-share model, not a trust boundary**, and the
evidence says so in those words. Repository Actions secrets are inaccessible to
this session's credential (`gh secret list` → HTTP 403 *Resource not accessible by
integration*, no admin permission), so no KMS, HSM or owner-provisioned secret
store could be provisioned. That is recorded as **ENVIRONMENT-BLOCKED** rather
than worked around by weakening the model. Both channels live in the same
artifact system, so any job able to download both can reconstruct the keys:
**retrieval is proven; authorization of key release is not.**

Still unproven: rotation ceremony separated in time from issuance; revocation,
custodian-side destruction, custody audit log; channel durability beyond the
14-day artifact retention window; no versioned or off-site key store; no HTTP
usability *after* rotation; no second full restore under the rotated backup key;
no session revocation on recovery; no RPO/RTO against an owner objective (none
exists, none invented); a frappe-only rehearsal site with no product app; three
GitHub-hosted runners from one pool, which proves three separate VMs and not
three providers, regions or datacentres. Every key, record, file and credential
is synthetic.

### Two defects execution found

1. **`-enc` naming (fixed).** Run `35178965074` died on `max() iterable argument
   is empty` *after* a successful backup: `set_backup_file_name()` appends `-enc`
   to every artifact name when `encrypt_backup` is on, so globs written for
   unencrypted names matched nothing. Fixed in `252345e`. That failed run is
   preserved as provenance and is **not** reused as a pass anywhere.
2. **Unquoted gpg passphrase (mitigated *and* reported to the owner).**
   `backup_encryption()` interpolates the key into a shell command unquoted. The
   url-safe base64 alphabet includes `-`, so a key beginning with a dash is
   parsed by gpg as an option, gpg fails, and frappe prints *"Files are stored
   without encryption"* and continues — leaving a **plaintext backup under an
   `-enc` filename**. About **one generated key in 64** would hit this. The
   generator now refuses a leading dash (≈0.02 bits), the custodian asserts every
   issued key is safe to pass unquoted, and the AES assertion would catch it
   regardless. Reported rather than only mitigated locally: an operator who lets
   Frappe generate its own backup key carries that 1-in-64 risk. No upstream
   change was proposed or made.

### Gate states — unchanged

| Gate | State |
|---|---|
| `production-authorization` | **REJECT** (`production_enabled=false`) |
| overall D8 | **BLOCKED** |
| `recovery` | **BLOCKED** |
| `backup-restore` | **BLOCKED** |
| `durability` | **BLOCKED** |
| `SEC-DEPS-01` | **UPSTREAM-BLOCKED / REJECT** — nothing forced, overridden, forked, suppressed or downgraded |
| `capacity-availability` | **NOT SELECTED** — no numeric objective invented |

`encryption_key_custody_reference` and `site_configuration_custody_reference`
remain **NOT SELECTED**: executing a custody *model* is not an owner selection of
a custody *destination*. `release_gate_state.recovery` and `.backup_restore` were
regenerated from their generator because the old wording now overstated the gap;
both still begin with `BLOCKED`, and the test that pins those strings was
**strengthened**, not relaxed — it now asserts every gate state keeps a
fail-closed prefix. Full suite 578 tests pass; `d8_validate.py` exits 0.

### Evidence

Archived in the ledger's canonical form (`json.dumps(d, indent=2, sort_keys=True)`
+ newline) and pinned by hash in the integrity map, which now holds 28 artifacts
all verified against disk:

- `docs/engineering/evidence/production-like-execution/hosted-key-custodian-35179445639.json`
- `docs/engineering/evidence/production-like-execution/hosted-key-operator-35179445639.json`
- `docs/engineering/evidence/production-like-execution/hosted-key-recovery-35179445639.json`
- `execution-ledger.json` § `key_custody_execution` (+ appended `outstanding_actions`)
- report §11, `RELEASE-GAP-MAP.md` §1.6 (new *Key custody* row), D8 matrix
  `backup-restore` and `durability` evidence fields, acceptance ledger
  `production_like_gap_closure.p4_key_custody`

```sh
gh run view 35179445639 --repo Frotan2/TOFEL-House-ERP
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105069423253 --jq '.output.text'
python3 -m unittest tests.foundation.test_key_custody_contract -q   # 67 tests
python tools/foundation/d8_validate.py
```

Next is P5 — the intended TLS/Tailscale boundary, monitoring and alert delivery
with retention, and rollback using real versioned artifacts — kept clearly
separated from this executed evidence and from the bounded synthetic harness,
which is not upgraded by any of it.
