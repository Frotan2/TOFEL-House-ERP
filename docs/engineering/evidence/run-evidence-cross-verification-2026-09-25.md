# Run-evidence cross-verification — 2026-09-25

Read-only audit. No disposition, pin, ledger field or gate assertion was
changed. Question asked: **does every hosted run the current decision
documents cite actually exist, and does its actual conclusion match how the
documents describe it?**

## Scope and method

Files scanned for run ids (regex `\b3\d{10}\b`):

- `docs/engineering/final-closure-register.json`
- `docs/engineering/d8-production-operations-decision-matrix.json`
- `docs/engineering/foundation-production-acceptance-ledger.json`
- `docs/engineering/RELEASE-GAP-MAP.md`

These are the documents that carry the current block, reject and defer
dispositions; older narrative docs (foundation-*.md, PLACEMENT-*.md, etc.)
cite another ~153 run ids as historical chronicle and were out of scope.

Each distinct id was verified live through the GitHub Actions API
(`gh api repos/Frotan2/TOFEL-House-ERP/actions/runs/<id>`), recording
workflow name, conclusion, head SHA and branch. Each citation's surrounding
text (±110 chars, every occurrence, in every engineering doc) was then read
and classified against the actual conclusion.

## Results

| | count |
|---|---:|
| distinct cited run ids in the four documents | 99 |
| runs found via API | 99 |
| runs missing | **0** |
| whose API conclusion is `success` | 63 |
| whose API conclusion is `failure` | 36 |
| citations contradicting the actual conclusion | **0** |

The six register-cited runs checked individually for this audit:

| run | workflow | conclusion | register claim | match |
|---|---|---|---|---|
| 36119457187 | runtime validation | success | hosted fail-closed evidence | yes |
| 35170062251 | independent-system recovery | success | closed, hosted-proven | yes |
| 35179445639 | external key custody | success | closed, hosted-proven | yes |
| 35466677597 | placement synthetic content | success | closed, hosted-proven | yes |
| 35451785714 | runtime validation | failure | "hosted audits fail closed" | yes |
| 35450528487 | runtime validation | failure | "hosted audits fail closed" | yes |

## Role classification of all 36 failure-conclusion citations

Every failed run is cited **as** a failure or rejection of some kind. No
failed run is cited as a pass.

1. **SEC-DEPS-01 rejection provenance / provenance pins (18 runtime
   validation runs):** 34823345078, 35084695840, 35090904508, 35122242581,
   35133062884, 35135793582, 35216709174, 35218007937, 35225331022,
   35384078097, 35450528487, 35451785714, 35744779043, 35748888182,
   35773065186, 35793620749, 35826357964, 35984767187. Each is recorded with
   its rejection (`status: fail` / `fail_reject`, decision matrix, BRANCH-
   RECONCILIATION). Where scoped probes inside such a run are cited
   (e.g. isolation 47/47, upgrade 33/33 in 35122242581; the
   site-encryption-key closure in 35133062884, reproduced in 35135793582),
   the ledger uses the scope-limited status `pass_scoped` and the archived
   evidence files themselves self-record `status: "fail"` — the overall
   rejection and the scoped pass are consistently presented.
2. **Frontend candidate rejections (8):** 34823670550, 34823793929,
   35122242647, 35218007871, 35222291762, 35384077998, 35449025381,
   35744778958 — all cited as `fail` / `fail_reject_not_adopted`, candidate
   never adopted.
3. **Defect-finding failures, later fixed (6 independent recovery runs):**
   35141452778, 35142455523, 35143620884, 35168111875, 35168996127,
   35169957724 — the `defects_found_and_fixed_by_execution` table; each
   failure carries its root cause, and closure is claimed only from the
   later green run 35170062251 (verified success, above).
4. **Superseded attempt (1):** 35178965074 (key custody) — recorded as
   "superseded by 35179445639"; the report states its evidence "is not
   reused as a pass anywhere".
5. **Pre-fix failures (2 operational boundaries):** 35197870620 and
   35214660151 failed identically before the F9 fix; the fix run
   35216709160 (success) is what the green claim rests on.
6. **Diagnostic evidence from a failed run (1):** 35048606232 (placement)
   is cited only for what its diagnostics revealed (the education app
   `after_install` Custom DocPerm mechanism), never as a gate pass.

## One archival quirk, no defect

Run 34823670550 is recorded by the API under its workflow file path
(`.github/workflows/foundation-frontend-review.yml`) rather than a
display name — how GitHub records runs of a workflow that then had no
`name:` key. It is cited as the first of this gate's consecutive
rejections. The preserved record
(`phase-2/frontend-workflow-validation-failure-34823670550.json`) matches
the API. Nothing to fix.

## Deliberate non-actions (documented, owner-decision scope)

- The acceptance ledger's per-branch execution subblock for the previous
  session branch remains itself true as written. Two newer push-triggered
  runtime runs exist on the current session branch (36114770663,
  36119457187 — both `success`, 123/123 checks, `status: "pass"`,
  `security_gate_passed: false`). Advancing the pinned runtime evidence is
  blocked by the enforced `fail_reject` rule
  (`d8_validate.validate_active_branch_qualification`) and is recorded as
  OWNER DECISION REQUIRED in
  `docs/engineering/evidence/active-runtime-state-2026-09-25.md`. This
  audit confirms the divergence is documented, not silent — no unilateral
  ledger or pin edit was made today, matching the standing posture.
- The frontend review gate remains red by design; run-citation integrity
  adds nothing to that verdict.

## Reproducibility

```bash
# extraction (run from repo root, paths joined with \n)
python3 - <<'PY'
import re
from pathlib import Path
targets = ['docs/engineering/final-closure-register.json',
           'docs/engineering/d8-production-operations-decision-matrix.json',
           'docs/engineering/foundation-production-acceptance-ledger.json',
           'docs/engineering/RELEASE-GAP-MAP.md']
found = set()
for t in targets:
    found |= set(re.findall(r'\b(3\d{10})\b', Path(t).read_text()))
print('\n'.join(sorted(found)))
PY

# verification per id (note: ensure the id file ends with a newline;
# a trailing-unterminated line is dropped by 'while read')
while read -r id; do
  gh api "repos/Frotan2/TOFEL-House-ERP/actions/runs/$id" \
    --jq '.name + "|" + (.conclusion // "no-conclusion") + "|" + .status + "|" + .head_branch'
done < ids.txt
```

Verification ran 2026-09-25 with a valid `GH_TOKEN`. Conclusion: **run
citations in the current decision documents are accurate; no register,
matrix, ledger or gap-map correction is required from this audit.**
