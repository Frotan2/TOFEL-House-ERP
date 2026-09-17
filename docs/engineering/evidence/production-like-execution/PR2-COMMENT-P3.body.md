
## P3 closed by execution — recovery onto a genuinely independent system

Continuing the gap-closure record on the active branch
`arena/01a0aafe-tofel-house-erp`. This PR's head branch is
`arena/01a0a9f7-tofel-house-erp` and this session is fixed to its own branch, so
again **no commit was pushed to this PR's head branch**; this comment records the
result. Prior comments on this PR cover the premise corrections (including the
nonexistent commit `d3705e6`), P1 and P2.

### What was executed

Run **`35170062251`** at commit `1378ce4`, workflow *Foundation independent-system
recovery* — both jobs `success`:

| Job | Check run | Checks |
|---|---|---|
| `independent-source` | `105041393483` | 29/29 pass |
| `independent-target` | `105042127143` | 31/31 pass |

`mocks_or_simulations_used=false` on both halves.

**A real destructive trigger ran first.** The source VM took a genuine
`bench backup --with-files`, then destroyed its own site with
`bench drop-site --no-backup`: database `_0da0781ed64f67b4` present `"1"` then
`"0"`, site directory gone, both files gone, nothing archived to fall back on.

**A second, provably separate machine recovered it.** The target VM rebuilt bench
from scratch at the identical pinned revisions (frappe `988e54f3…`, erpnext
`4048fb70…`) and restored from the transferred backup alone:

- **Database** — 12 ToDo and 12 Note records, name-digest matched against the
  source manifest.
- **Files** — private `independent-recovery-private.txt` (552 bytes,
  `is_private=1`) and public `independent-recovery-public.txt` (551 bytes,
  `is_private=0`), on-disk SHA-256 matched, File documents recovered.
- **Application** — `frappe 16.33.1` and `erpnext 16.34.2`.
- **Usability over real HTTP** through nginx in front of Gunicorn, configured as
  the pinned bench template configures production: `ping` → `pong`; login HTTP
  **200** as `Administrator` with a session cookie; source-created record
  `56uqdlb6cp` readable with content matching the manifest and all 12 listed;
  both files served with digests matching; and the **privacy boundary survived
  recovery** — private file HTTP **403** anonymously, public file HTTP **200**
  anonymously from nginx.

### Independence was verified, not assumed

`kernel_boot_id`, Actions `runner_name` (`…1000002465` vs `…1000002466`) and
`dmi_product_uuid` all differ; filesystem, volumes and containers are not shared;
the only shared channel is the GitHub Actions artifact. The target then positively
confirmed it was not looking at the source's machine: source lab path absent,
source archived site absent, source database absent, source schema count `"0"`.

Two identifiers were **disproved as discriminators by execution** and are now
recorded as observations only, each annotated with the run that disproved it:
`hostname` (run `35143620884` — the platform reuses generated hostnames across
separate VMs) and Docker daemon id (run `35168111875` — the runner image ships a
pre-generated `/etc/docker/key.json`). Neither will be reintroduced as a
requirement.

This is a separate **machine**, not a separate cloud, region or datacentre, and it
is reported as such.

### Six defects this workflow forced to be fixed

Each was found by running the recovery, not by inspection: `35141452778`,
`35142455523`, `35143620884`, `35168111875` (independence model),
`35168996127` (`bench restore --admin-password` is a no-op on the restore path at
pinned frappe `988e54f3`, because `install_app(force=False, set_as_patched=not
source_sql)` means `after_install` never runs — login returned HTTP 401; fixed
with native `bench set-admin-password`, and recovery now sets the target's *own*
credential so it never depends on a source secret), and `35169957724` (private
file HTTP 500 because `send_private_file` answers `X-Use-X-Accel-Redirect` with
`X-Accel-Redirect: /protected/private/files/<name>` and the generated nginx had no
`internal /protected/` location; fixed in `1378ce4` and pinned by contract tests).

### Secret hygiene, and the limitation asserted rather than hidden

The site-config backup Frappe writes beside the dumps — which holds the database
password and the site encryption key — is excluded from staging by an explicit
five-file allowlist; the staged text is scanned for every generated secret;
`bench restore --encryption-key` exists and is **deliberately unused**; and only
SHA-256 fingerprints appear in any artifact.

The consequence is recorded as an **expected failure**: the field the source
encrypted came back with ciphertext intact but is **undecryptable on the target**
(source key `433059bd…`, target key `249d33a6…`, `decrypts_on_target=false`). That
is the concrete executed evidence that **P4 — separately controlled external key
custody with rotation and proven key retrieval — is a distinct outstanding
requirement**, and it is the next item of work.

### Gate states: unchanged, and not weakened

| Control | State |
|---|---|
| D8 `recovery` | **BLOCKED** (unchanged) |
| D8 `backup-restore` | **BLOCKED** (unchanged) |
| D8 overall | **BLOCKED** |
| Production authorization | **REJECT** |
| `production_enabled` | **false** |
| SEC-DEPS-01 | **UPSTREAM-BLOCKED / REJECT** (untouched; nothing forced, overridden, forked, suppressed or downgraded) |
| Capacity/availability | **NOT SELECTED** — no numeric objective invented |
| This PR | **OPEN, unmerged** |

`D8-BACKUP-RECOVERY` requires more than a successful separate-system restore: key
retrieval, session revocation and a measured RPO/RTO. None is proven, so no gate
moved. No RPO/RTO figure was invented, because no owner objective is selected.

`release-readiness-evidence.json` was **regenerated from its generator**
(`tools/foundation/release_readiness_evidence.py`) rather than hand-edited, so
`release_gate_state.recovery` now reads `BLOCKED / SEPARATE-SYSTEM REHEARSAL
EXECUTED; KEY RETRIEVAL, SESSION REVOCATION AND MEASURED RPO/RTO NOT PROVEN`
instead of the stale `BLOCKED / INDEPENDENT PRODUCTION-LIKE EVIDENCE NOT PROVEN`.
It still begins with `BLOCKED`, as `tools/foundation/d8_validate.py` requires. The
archived bounded snapshot `local-bounded-release-readiness-evidence.json` was
deliberately **not** edited — it is historical provenance pinned by hash.

### Evidence and reproduction

Archived in `docs/engineering/evidence/production-like-execution/`, in the
ledger's canonical form, and added to its integrity map (23 → 25 entries, all
verified against disk):

| Artifact | SHA-256 |
|---|---|
| `hosted-independent-source-35170062251.json` | `9c054dd6e41f57d5f073bbe06e2116bf1ec66b9a48fab1d30b7ec48f9f7df1b5` |
| `hosted-independent-target-35170062251.json` | `ea23e9f922eb736eea21437a06db1e5ca0a4d0c223b1ea001268a8720de48cb1` |

Machine-readable detail: `execution-ledger.json` §
`independent_recovery_execution`. Narrative: `FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md`
§10, with §1 and §4 corrected where execution had made them stale, and
`RELEASE-GAP-MAP.md` §1.6 moving only the cells execution actually moved.

```sh
gh run view 35170062251 --repo Frotan2/TOFEL-House-ERP
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105041393483 --jq '.output.text'
gh api repos/Frotan2/TOFEL-House-ERP/check-runs/105042127143 --jq '.output.text'
python -m unittest discover -s tests -q      # 511 tests, OK
python tools/foundation/d8_validate.py       # exit 0
```

Still outstanding after P3: **P4** external key custody with rotation and proven
key retrieval, and **P5** the TLS/Tailscale boundary, monitoring and alert
delivery with retention, and rollback using real versioned artifacts.
