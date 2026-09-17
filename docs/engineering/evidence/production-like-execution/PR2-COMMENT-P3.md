# Prepared comment for PR #2 — P3 independent-system recovery

Post with:

```sh
gh pr comment 2 --repo Frotan2/TOFEL-House-ERP \
  --body-file docs/engineering/evidence/production-like-execution/PR2-COMMENT-P3.body.md
```

The body is in `PR2-COMMENT-P3.body.md`. It must be posted **verbatim**, not
paraphrased; its byte count and SHA-256 are recorded in `execution-ledger.json`
under `pr_2_update.p3_comment_status`, so any edit to the body invalidates that
record.

## Why this file exists

The GitHub credential in this sandbox expired while the P3 evidence paperwork was
being committed: `gh auth status` reported *"The github.com token in GH_TOKEN is
no longer valid"*, the REST API returned `Bad credentials`, and `git push` failed
with *"could not read Username for 'https://github.com': terminal prompts
disabled"*. That is the same failure mode recorded in
`FINAL-RELEASE-READINESS-EVIDENCE-REPORT.md` §9.4.

Nothing was inferred, fabricated or backdated while the outage was open. The P3
evidence had been fetched from the Checks API **before** the credential expired,
and every identifier added in this paperwork was verified programmatically against
those archives or resolved with `git cat-file`. The unpushed, unposted state was
recorded as an open blocker in `execution-ledger.json` (`outstanding_actions`)
rather than reported as done.

## What the outage cost, and how it was recovered

Two local commits carried this paperwork while the outage was open. When
authentication was restored on a later turn, the sandbox had **also been
re-cloned**: `HEAD` sat at `60c777e` with only two commits reachable
(`60c777e`, `9eccff9`), the ref `origin/arena/01a0aafe-tofel-house-erp` did not
exist locally, and both paperwork commits had ceased to exist as git objects.

Recovery, in the order it was executed:

1. `git ls-remote origin` — confirmed the pushed tip of the active branch was
   intact at `1378ce4`, so no executed work was lost on the remote.
2. `git config --add remote.origin.fetch
   '+refs/heads/arena/01a0aafe-tofel-house-erp:refs/remotes/origin/arena/01a0aafe-tofel-house-erp'`
   — a fresh clone only fetches `main`, so the arena branch had to be re-added.
3. `git fetch origin`, then
   `git reset --mixed origin/arena/01a0aafe-tofel-house-erp` — realigns `HEAD`
   and the index to `1378ce4` **without touching the working tree**, which still
   held the persisted snapshot of the completed paperwork.
4. `git status --porcelain` then listed exactly the eleven paths this paperwork
   covers and nothing else, which is the check that the snapshot and the real tip
   were reconciled rather than assumed to be.
5. Content re-verified before re-committing: all 25 entries in the ledger's
   integrity map match the files on disk; both P3 archive hashes are
   byte-identical to the values fetched before the outage; the prepared body is
   unchanged at 7631 bytes with a matching SHA-256; 511 tests pass;
   `d8_validate.py` exits 0.

The two lost commit SHAs are recorded in `pr_2_update.p3_comment_status` as
history only. They were never pushed and no longer resolve, so nothing in the
evidence cites them as a live reference — the same discipline applied to the
nonexistent commit `d3705e6` named at the start of this pass.

## Remaining steps

1. `git push origin arena/01a0aafe-tofel-house-erp` — verify it fast-forwards
   from exactly `1378ce4`.
2. Post the comment with the command at the top of this file.
3. Record the resulting comment id and URL, and the `d8-operations-contract` run
   id at the new tip, beside the P3 evidence in `execution-ledger.json`.

The earlier `PR2-COMMENT.body.md` / `PR2-COMMENT.md` pair is retained untouched as
the historical record of the previous comment.
