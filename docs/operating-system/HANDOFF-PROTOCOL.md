# TOEFL House ERP — Handoff Protocol

Date: 2026-09-22 · Location: `docs/operating-system/HANDOFF-PROTOCOL.md`
Status: **authoritative continuation procedure**. Follow it exactly every
time an agent starts, pauses, or resumes work, so the next agent continues
without reconstructing the project from conversation history.

---

## The 18-step handoff (normative)

### Starting / resuming work

1. **Establish HEAD and clean/dirty state.**
   `git status` · `git branch --show-current` (must be the session branch) ·
   `git log --oneline -5`. Record HEAD SHA + subject + tree state. If dirty,
   identify every changed file before reading further.

2. **Read the current baseline.**
   `docs/operating-system/CURRENT-BASELINE.md` — branch/HEAD/tests/blockers/
   next slice/posture. If HEAD differs from the baseline's HEAD, the baseline
   is stale: re-verify tests + tree state and update it before proceeding.

3. **Inspect relevant decision records.**
   `DECISION-REGISTER.md` entries for the slice + the canonical owner record
   (`docs/engineering/canonical-owner-decision-record.json`) +
   `OWNER-DECISIONS.md` projection. Confirm every required decision is
   RESOLVED; if any is OWNER DECISION REQUIRED / DEFERRED / missing → STOP.

4. **Inspect the domain contract.**
   `docs/domain/DOMAIN-CONTRACT.md` section + `ARCHITECTURE-DECISIONS.md`
   ruling (A01–A13) + `ARCHITECTURE-CONSTITUTION.md` pattern + applicable
   closure/plane/desk contract. Cite section IDs in the work plan.

5. **Inspect native ground truth.**
   Pinned sources per `docs/engineering/foundation-version-matrix.json`
   (Frappe v16.33.1 / ERPNext v16.34.2 / Education v16.1.0 / HRMS v16.18.1):
   doctypes, controllers, hooks, permission flows actually read — never from
   memory. Note file + behavior.

6. **Inspect the existing implementation.**
   Owned commands, controllers, guards, desk projections, fixtures, hooks,
   and their tests for the slice. Identify the exact carrier → readiness →
   consumer position of the work.

7. **Perform a read-only dependency/design audit.**
   Map predecessors (roadmap), policy carriers, readiness facts, audit
   streams, permission scopes, and alternate writers (RPC/REST/Desk/import/
   job/cancel/export/file). No code changes during the audit.

8. **Identify one authorized implementation slice.**
   Exactly one: named, dependency-satisfied, decision-backed, evidence-
   scoped. If none qualifies → remain in audit/evidence phase or STOP with a
   recorded blocker.

9. **State exact scope.**
   Write it down before coding: files to create/modify, commands/endpoints,
   doctypes/fields (or "none"), tests to add/run, evidence to produce, and
   explicit non-goals. If scope cannot be stated exactly → keep auditing.

### Doing the work

10. **Implement.**
    One slice only. Guarded commands, effective dating, idempotency, locks,
    hash-chained audit, business-language refusals, native-first reuse.
    No unrelated cleanup; no broad refactor; no invented values.

11. **Run targeted tests.**
    The slice's own suites first (contract + lifecycle + client where
    applicable). Fix failures in the implementation, not the assertions.

12. **Run canonical full suites.**
    `python3 -m unittest discover -s tests -t .` · `ruff check .` · Node
    suites where touched · `d8_validate.py` (must stay exit 0 with D8
    BLOCKED / production REJECT unless a recorded authorization changed it).
    Hosted suites only where the slice contract requires them — never claim
    unexecuted hosted evidence.

13. **Perform a read-only diff audit.**
    `git diff` + `git status`: every hunk must belong to the stated scope;
    check for hidden policy literals, security/production drift, weakened
    assertions, artifacts, and history rewrites.

14. **Verify no scope creep.**
    Anything outside the stated scope is removed or isolated into a separate
    change with its own review. Re-run affected suites after removal.

### Closing the work

15. **Commit only after SAFE TO COMMIT.**
    All `SKILL.md` §J commit gates hold: tests green, diff audited, scope
    exact, no hidden policy, no drift, history preserved, no artifacts, no
    weakened assertions. Commit message states slice + authority IDs +
    evidence (tests/hosted runs).

16. **Push only after commit authorization / normal project procedure.**
    Push to the session branch only. Never switch to, create, or push to any
    other branch. Never rewrite history. Never push secrets, data, or dumps.

17. **Update the baseline.**
    `CURRENT-BASELINE.md`: HEAD, test results, completed evidence, blockers,
    next slice, posture, + one append-only update-log line. Update
    `DOMAIN-ROADMAP.md` / `DECISION-REGISTER.md` rows the slice actually
    changed (no speculative status flips).

18. **Hand off the exact next state.**
    A short note the next agent can act on without archaeology:
    (a) HEAD + tree state; (b) what was completed + evidence IDs;
    (c) what is next (one slice) + its authority/dependency citations;
    (d) open blockers + owners; (e) anything intentionally left dirty and why.
    Then stop — do not start the next slice in the same breath.

---

## Handoff note template (copy/paste)

```text
HANDOFF — <date>
Branch: <branch> · HEAD: <sha> <subject> · Tree: clean|dirty(<files>)
Completed: <slice> · Evidence: <tests runs / hosted run+checks+hash>
Baseline/roadmap/register updated: yes (see <files>)
Next authorized slice: <name> · Authority: <decision IDs> · Depends on: <rows>
Blockers: <ID — owner — what unblocks> | none new
Left dirty (if any): <files + reason> | none
Posture: production <REJECT|…> · D8 <BLOCKED|…> · SEC-DEPS-01 <…>
```
