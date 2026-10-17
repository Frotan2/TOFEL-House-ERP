# Gate replay — 2026-10-16

Replays the CI-style advisory snapshot (`advisory-delta-2026-10-09/replay-snapshot.json`,
47 groups, 170 rows) through the current register and deltas, using `load_triage()` and
`CLOSED_DISPOSITIONS` from `tools/foundation/advisory_triage.py`.

Result on head `391c9ca` (register with the 2026-10-15 deltas):

- rows: 170
- untriaged: **0** (the PYSEC-2026-4311 and PYSEC-2026-4312 mirrors now resolve)
- non-closed: **1**, GHSA-VHRC-HGRQ-X75R at BLOCKED (ERRATUM E6)
- dispositions: BROWSER_SELF_DENIAL 5, BLOCKED 1, NOT_REACHABLE 63, BUILD_ONLY 59, MITIGATED 20, DEV_ONLY 20, INSTALL_ONLY 2

Foundation run `38901735807` on `391c9ca` failed in `Install and validate the pinned foundation`
with `hosted-full-stack-dependency-audit: exit 1; hosted-frontend-advisory-audit: exit 1`, and no
untriaged annotation was reported. This matches the replay: the only remaining red cause is the
intended BLOCKED GHSA-VHRC. The replay does not replace the live audit.

BROWSER_SELF_DENIAL is a closed disposition in the current policy. Its record review (including
`th_command_pages.js:564`) is still open in the release plan.

## Foundation run history for this head series

| Head | Foundation run | Result | Reason |
|---|---|---|---|
| `61c4c42` | `38899033333` | failure | Two untriaged PyPA mirror IDs (PYSEC-2026-4311, PYSEC-2026-4312). Fixed by `391c9ca`. |
| `391c9ca` | `38901735807` | failure | `hosted-full-stack-dependency-audit` and `hosted-frontend-advisory-audit` exit 1. No untriaged rows in this replay. The expected cause is GHSA-VHRC BLOCKED (the only non-closed row). |
| `f6b3b46` | `38904134007` | failure | **New reason: `get-app-hrms: exit 1`**, which runs before the audits. No file on the install path changed between `391c9ca` and `f6b3b46`. The same install passed through the audit step at `391c9ca`. Log retrieval is blocked from this sandbox (blob host not allowed). A rerun returned HTTP 403 (`rerun-failed-jobs`). The likely cause is a transient fetch failure, but this is **not verified**. |
| `10353c6d` | (none) | - | The Foundation workflow path filter does not include the owner package. No Foundation run exists for this head. |

Re-run this record on each new head, and do not treat an older run as proof for newer code.
