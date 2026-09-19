# Evidence re-observability sweep — 2026-09-19 (§5)

Horizontal pass over every already-claimed number in the D8 decision matrix
and the 2026-09-17 production-readiness closure. Method: each cited run,
check, digest, SHA and count was re-observed either from a committed file in
this repository or live from the read-only GitHub API. No evidence file was
edited to fit a claim; the only new files are dated retrieval archives
pulled byte-for-byte through the repository's sanctioned Checks-API
transport, each carrying its own provenance and digest verdict.

## Verdict: zero falsifications, zero corrections, one stated limitation

- **25/25 cited workflow runs** re-observed live: conclusion and head SHA
  match the claims in every case (10 re-verified this pass at
  `35222291712`, `35222291725`, `35222291762`, `35224205616`,
  `35225331022`, `35225331195`, `35225330998`, `35218007814`,
  `35218007835`, `35218008053`; 15 older runs likewise).
- **16/16 cited check runs** re-observed live: name, head SHA and conclusion
  match (full ID list in the archive provenance records).
- **19/19 cited long digests/SHAs**: the two archived-evidence file digests
  match the committed bytes exactly; all 15 run-value digests appear in the
  committed `hosted-*.json` they are cited from; the full `da8b36a…` SHA is
  the live head of run `35225331022` and the commit exists on
  `arena/01a0aef4-tofel-house-erp`.
- **Every cited short SHA** resolves to a real commit.
- **Ledger integrity**: all 28 `archived_evidence_sha256` entries match the
  committed files.
- **Old-run counts** re-observed from committed `hosted-*.json`:
  542/542 native (+101/101 runner exit-0), isolation-recovered 47/47,
  restore 5/5, restore-secured 7/7, source 29/29, target 31/31, readiness
  54/54, realtime 4/4, upgrade 33/33, guardian_browser 6/6, custodian 10/10.
- **09-17 reconciliation counts** (previously GitHub-only) re-observed via
  the Checks-API transport and now ARCHIVED in
  `evidence/production-like-execution/checks-api-*.json`:
  542/542, 101/101, 119/121 (failing checks exactly the two named audit
  checks), 4/4, 6/6, 33/33, 54/54, 31/31, 20/20, 38/38, 18/18, frontend
  20/22 with both audits exit 1 and 1 introduced / 35 removed advisories,
  `production_pins_changed` false, advisory census 57/21/255, key-operator
  18/19 with `bench-init` exit 167 and the verbatim HTTP 503, 4 matched
  keys plus the three negative controls.
- **D8 run `35224205616`**: both cited steps
  (`Validate D8 contract and fail-closed release invariants`,
  `Run D8 contract tests`) confirmed success by name via the jobs API.
- **"702 owned tests pass" at `da8b36a`**: reproduced exactly — 702 tests
  discovered in a worktree at that commit, 702/702 pass once the worktree
  carries the real branch name (the 3 detached-HEAD failures are the
  branch-identity guards working as designed, not product failures).
- `foundation-test-results.json` is dated 2026-09-14 and describes that
  checkpoint; nothing cites it as current, so no correction is owed.

## The one limitation (stated, not hidden)

`checks-api-105215912617-key-operator.json` is the single archive whose
summary digest does NOT verify against the stored bytes: the published
report embeds raw `uv` stderr with an invalid escape (the same defect the
09-17 closure pass repaired for parsing). The archive retains the original
transport text verbatim, documents the repair, and claims content
corroboration only — not byte integrity. All other nine archives are
byte-verified (`digest_verified: true`).

## Claim → source index

| Claimed number | Re-observed from |
|---|---|
| 542/542, 101/101 (old) | `hosted-placement-native-checks-35122242728.json`, `hosted-placement-runner-35122242728.json` (exit_code 0 × 101) |
| 47/47, 5/5, 7/7 (old) | `hosted-runtime-35122242581.json` (`isolation-recovered_result`, `restore_result`, `restore-secured_result`) |
| 29/29, 31/31 (old) | `hosted-independent-source-35170062251.json`, `hosted-independent-target-35170062251.json` |
| 54/54, 4/4, 33/33, 6/6 (old) | `hosted-remaining-gates-35122242581.json` |
| 10/10 custodian | `hosted-key-custodian-35179445639.json` |
| 542/542, 101/101 (09-17) | `checks-api-105208726304-placement-native.json`, `checks-api-105208729385-placement-runner.json` |
| 119/121 + named audit failures | `checks-api-105222593207-runtime-evidence.json` |
| 4/4, 6/6, 33/33, 54/54 (09-17) | `checks-api-105222597982-remaining-gates.json` |
| 31/31 recovery target | `checks-api-105193158969-recovery-target.json` |
| 20/20 durability | `checks-api-105191267035-durability.json` |
| 38/38 TLS edge | `checks-api-105191973507-tls-edge.json` |
| 18/18 runner | `checks-api-105205384326-runner-evidence.json` |
| 20/22, 1/35, pins flag, 57/21/255 | `checks-api-105205441744-frontend-evidence.json` |
| 18/19, exit 167, 503, keys, controls | `checks-api-105215912617-key-operator.json` (content-verified; digest open per above) |
| Run/check conclusions + SHAs | Live GitHub API, 2026-09-19 (read-only; IDs listed in archive provenance) |
| 702/702 at `da8b36a` | Worktree reproduction on branch `arena/01a0aef4-tofel-house-erp` |
