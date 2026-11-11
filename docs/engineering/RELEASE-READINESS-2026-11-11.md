# Release-readiness checkpoint — 2026-11-11

**Decision: GO for isolated synthetic training; NO-GO / REJECT for institute production.**
**Scope: GitHub engineering evidence at `main@1f821155445f1a7df630343f65c7681d1d0a6464`; local qualification evidence explicitly separated.**

This is a dated checkpoint, not a mutable claim that a later `main` still has these results. The exact installed artifact, license/signer identity, host acceptance and written Owner authorization remain separate requirements. See [release candidate contract](RELEASE-CANDIDATE.md), [launch runbook](LAUNCH-RUNBOOK.md), and [current owner policies](../owner-decisions.json).

## Independently verifiable GitHub state

- PRs [#155](https://github.com/Frotan2/TOFEL-House-ERP/pull/155) through [#161](https://github.com/Frotan2/TOFEL-House-ERP/pull/161) are merged. In particular, #159 scopes tuition-plan catalog checks by company; #160 adds staff assessment Desk and corrects progression timestamp serialization; #161 fixes Reception linked-applicant branch projection and the Owner preview HTTP method.
- Exact final `main` SHA: `1f821155445f1a7df630343f65c7681d1d0a6464`. All five required GitHub workflows succeeded:
  - [Owned suite](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983325)
  - [Native lifecycle integration](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983248)
  - [Foundation runtime](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983429)
  - [Product image](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983281)
  - [Windows customer package smoke](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983309)
- [Exact-revision offline TEST installer artifact](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/42961983281/artifacts/13831865834) exists. Its GitHub Actions *outer archive* size was 2,139,942,601 bytes; this is **not** the raw EXE size. Its classification is **TEST PACKAGE — NO REAL DATA**, not a signed or approved institute release.
- At this checkpoint, GitHub had no open pull requests, no published Releases, and seven unchanged old `fix/` branch refs from already-merged PRs (#155–#161). The `main` branch reported `protected: false`. Eight release/audit issues remained open; some contain older, superseded snapshots.

## HP ENVY qualification evidence — supplied by the Work operator, not independently inspected here

The Work handover reports actual Edge/isolated MariaDB transactions with synthetic records: the linked learner journey from placement to tuition, attendance, marks, published grade B/82% and completion; collection and cash handover; book sale/return; refund roles; teaching compensation and payroll. It also reports 48 route-access checks, six sign-outs, Company/Branch isolation, and recovery of nine acceptance records into a **separate** database. Work reports read-only verification of archive, EXE hashes and GitHub provenance on HP ENVY, with **Windows Authenticode `NotSigned` and no timestamp**.

The Work evidence lives at **operator-local** paths, including `Windows development release handover.md`, `Final TEST installer verification.json`, and `Linked learner acceptance evidence.md`. These paths were **not uploaded to or inspected from this GitHub repository**. Do not cite this section as independent GitHub proof of host acceptance, and do not carry its conclusions over to another install.

The development installation is preserved in `REFUSED` mode. The rejected four-service lab restart was **not** performed; older HP ENVY lifecycle evidence does not convert that specific test to PASS.

## Remaining hard release gates — not waived by green CI

1. **Publisher signing and delivery:** independently reviewed, signed and timestamped Windows installer; legal publisher identity/certificate, artifact verification and an immutable, supported distribution channel. GitHub has no customer Release; TEST artifacts may not be relabeled as production.
2. **Prerequisite rights:** verify redistributability/licensing and acceptable delivery terms for each bundled Windows prerequisite. Do not assume public download availability grants redistribution rights.
3. **Independent supported Windows acceptance:** authorized clean-host install of the exact signed release, role login, Start/Stop/reboot/Repair, safe upgrade and rollback, data-preserving uninstall and interruption/failure-path tests. Preserve any existing institute installation, databases and Docker volumes.
4. **Private staff network:** authorize and verify Tailscale Serve HTTPS, `/socket.io` WebSocket, access from real staff devices and denial outside the tailnet. No public Funnel or accidental exposure.
5. **Owner recovery:** approved separate backup target, off-device encrypted backup, retained recovery material/two-person custody and an independently observed restore on a separate target with explicit recovery approvals. Do not perform an in-place production restore as a test.
6. **Governance and security:** independent code/release review, required checks/branch protection or ruleset enforced by a GitHub administrator, current dependency/security triage, and reconciliation of open release issues to fresh evidence. Do not close issues based only on stale snapshots.
7. **Authorization:** written Owner approval for the *particular* institute host, signed release and cutover plan. Until then production authorization remains `REJECT`, regardless of site mode.

### Current tracking that must not be falsely closed

- [#12](https://github.com/Frotan2/TOFEL-House-ERP/issues/12) Owner-host lifecycle and recovery;
  [#36](https://github.com/Frotan2/TOFEL-House-ERP/issues/36) signed/independent Windows delivery;
  [#40](https://github.com/Frotan2/TOFEL-House-ERP/issues/40) safe signed updater;
  [#71](https://github.com/Frotan2/TOFEL-House-ERP/issues/71) branch governance;
  [#123](https://github.com/Frotan2/TOFEL-House-ERP/issues/123) remaining release and legacy-install findings.
- [#35](https://github.com/Frotan2/TOFEL-House-ERP/issues/35), [#91](https://github.com/Frotan2/TOFEL-House-ERP/issues/91), and [#115](https://github.com/Frotan2/TOFEL-House-ERP/issues/115) require evidence reconciliation. Later HP ENVY synthetic successes materially supersede old statements in their descriptions but **do not by themselves prove clean-host signed-release acceptance**.
- **Correction to issue #123, finding F3:** in current `main`, `Verify Package Image.ps1` now deletes the previous receipt backup **only when `$committed` is true**, after exact read-back; `tests/foundation/test_windows_identity_receipt.ps1` covers read-back failure and isolated original-receipt recovery. F3's old source assertion is no longer accurate. Other findings in #123 remain open.

### Repository hygiene

The seven old `fix/` branch refs were not removed. They match merged PR heads but require a fresh exact-ref/PR check immediately before deletion; no connected tool in this checkpoint had branch-delete privileges. Keep their merge history, and never rewrite `main` to make the branch list look clean. Administrator ruleset activation is also not available through the connected application.

**Next decision:** finish the physical release and governance gates; do not repeat synthetic business journeys unless release code, host or policy changes invalidate the earlier evidence.
