# Prepared comment for PR #2 — P4 external key custody

Post with:

```sh
gh pr comment 2 --repo Frotan2/TOFEL-House-ERP \
  --body-file docs/engineering/evidence/production-like-execution/PR2-COMMENT-P4.body.md
```

The body is in `PR2-COMMENT-P4.body.md`. It must be posted **verbatim**, not
paraphrased; its byte count and SHA-256 are recorded in `execution-ledger.json`
under `pr_2_update.p4_comment_status`, so any edit to the body invalidates that
record.

## Why this file exists

The GitHub credential in this sandbox expired again while the P4 evidence
paperwork was being pushed: `gh auth status` reported *"The github.com token in
GH_TOKEN is no longer valid"*, the REST API returned `Bad credentials`, and
`git push` failed with *"could not read Username for 'https://github.com':
terminal prompts disabled"*. That is the same failure mode recorded in
`FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md` §9.4 and in `PR2-COMMENT-P3.md`.

This time the outage began **after** the executed work was already published. The
important distinction from the P3 outage:

- The custody code and workflow were pushed and executed as commits `9a19e83` and
  `252345e`, and run `35179445639` completed `success` on GitHub. **That
  evidence is on the remote and cannot be lost.**
- The three evidence payloads were fetched from the Checks API and archived to
  `docs/engineering/evidence/production-like-execution/hosted-key-*-35179445639.json`
  **before** the credential expired, and all three were hash-verified against the
  ledger's integrity map.
- Only the paperwork commit `6c22a7c` was unpushed when the outage began, and it
  remains intact locally.

Nothing was inferred, fabricated or backdated while the outage was open. Every
identifier in the paperwork was verified programmatically against the archived
payloads or resolved with `git rev-parse` / `git cat-file`, and the push was
retried rather than reported as done.

## State at the time of writing

| Item | State |
|---|---|
| Run `35179445639` (P4 custody, three jobs) | `success` — **published on GitHub** |
| Commits `9a19e83`, `252345e` | pushed |
| Commit `6c22a7c` (P4 evidence paperwork) | **committed locally, not pushed** |
| Prepared comment body | written, not posted |
| Full test suite | 578 tests pass locally |
| `d8_validate.py` | exits 0 locally |

## Remaining steps

1. `git push origin arena/01a0aafe-tofel-house-erp` — verify it fast-forwards
   from exactly `252345e` to `6c22a7c` (plus the commit adding these two files).
2. Post the comment with the command at the top of this file.
3. Record the resulting comment id and URL, and the run ids of the workflows that
   validate the new tip, beside the P4 evidence in `execution-ledger.json`
   (`pr_2_update.p4_comment_status`).
4. If the sandbox was re-cloned while the outage was open, follow the recovery
   sequence recorded in `PR2-COMMENT-P3.md` §"What the outage cost": `git
   ls-remote origin`, re-add the arena refspec, `git fetch`, then `git reset
   --mixed origin/arena/01a0aafe-tofel-house-erp` so the working-tree snapshot is
   reconciled with the real tip rather than assumed to be, and re-verify the
   integrity map before re-committing.

The earlier `PR2-COMMENT.body.md` / `PR2-COMMENT.md` and `PR2-COMMENT-P3.body.md`
/ `PR2-COMMENT-P3.md` pairs are retained untouched as the historical record of
the previous two comments.
