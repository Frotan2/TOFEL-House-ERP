# Documentation and release authority

**Documentation language:** English. Customer-facing screens, installation
guides, labels, support instructions, and maintained product documentation
must use English. Approved legal names or immutable identifiers in another
script can remain in the Owner's restricted decision record; they must not
be mistaken for user-interface language.

**Current release state:** **REJECT / NO-GO — TEST PACKAGE, NO REAL DATA.**
The integration candidate lives on `work`; `main` is not an independently
approved release. Branch names, CI results for older commits, old screenshots,
and source-level tests do not authorize live use.

## Sources of truth (in precedence order)

| Question | Authoritative source | Interpretation |
| --- | --- | --- |
| What is in the running product? | Installed immutable build, native Frappe/ERPNext/Education/HRMS schema and guarded application code | Documentation is not a substitute for a real-site acceptance test |
| What did the Owner approve? | `docs/owner-decisions.json` and any explicit, newer approved addendum therein | Later approved decisions prevail over superseded draft figures; proposals cannot become active merely by being packaged |
| What may staff do? | Server-enforced roles, approvals and effective policy versions | The desk is a projection, not an authorization authority |
| What must the customer receive? | [Customer delivery](CUSTOMER-DELIVERY.md), [Single-file delivery contract](engineering/SINGLE-FILE-CUSTOMER-DELIVERY.md), and the verified signed artifact | The accepted distribution target is **one offline Windows Setup EXE**; ZIPs, VBS launchers and source checkouts are engineering/development fallbacks, not the final customer experience |
| How do safe updates work? | [Customer updates](CUSTOMER-UPDATES.md) and the updater implementation | The update channel stays disabled until release, backup and two-person recovery acceptance |
| What is safe to run today? | [Windows validation](../product/windows/VALIDATION.md) and [Launch runbook](engineering/LAUNCH-RUNBOOK.md) | Read-only checks for an existing preserved Owner installation; destructive operations remain forbidden during the release hold |
| Can production be approved? | Exact-HEAD GitHub checks **and** independent native, Windows, role, financial, encrypted-backup and isolated-restore acceptance, followed by written Owner authorization | Default **NO**; test receipts for other commits do not count |

## Maintained reading path

**Customer/operator:** [Owner Handbook](../product/windows/OWNER%20HANDBOOK.txt),
[Daily Use Guide](../product/windows/DAILY%20USE%20GUIDE.txt),
[Customer delivery](CUSTOMER-DELIVERY.md), and
[Customer updates](CUSTOMER-UPDATES.md).

**Engineering:** [Product and native ownership](PRODUCT.md),
[Architecture decisions](DECISIONS.md),
[Configuration plane](CONFIGURATION-PLANE.md),
[Role-based work desks](ROLE-DESKS.md),
[Academic assessment](ACADEMIC-ASSESSMENT.md),
[Class operations](CLASS-OPERATIONS.md),
[Placement specification](PLACEMENT-SPEC.md),
and [Integration contracts](engineering/INTEGRATION-CONTRACTS.md).

**Release acceptance:** [Release candidate scope](engineering/RELEASE-CANDIDATE.md),
[Acceptance criteria](engineering/ACCEPTANCE.md),
[Acceptance matrix](engineering/ACCEPTANCE-MATRIX.md),
[Owner no-code setup](engineering/CUSTOMER-NO-CODE-OPERATING-SETUP.md),
[Customer delivery requirements](engineering/SINGLE-FILE-CUSTOMER-DELIVERY.md),
and [Safe updates](engineering/SAFE-UPDATES.md).
The candidate scope/matrix may include dated baseline findings: **the current
release decision must be recomputed from the actual installed build and
exact-head evidence**, never copied from a dated matrix.

## Historical engineering records (not customer instructions)

Dated reports under `docs/engineering/*-20*.md` and evidence under
`docs/engineering/evidence/` document experiments, adversarial findings,
prior release candidates, and reproducible security/finance checks. They
are retained for provenance and independent review, **not** interpreted as
the live Owner database or as a description of the latest branch head.
In particular, references to legacy migrations, imported cohorts, old prices
or synthetic invoices do **not** imply that this institute has any historical
ERP records. The fresh customer package must contain **zero** student,
enrollment, attendance, invoice, payment, salary, grading and demo records.

Do not delete the underlying audit evidence, Git history, security regression
fixtures, migration compatibility code or recovery protocols merely to make
the repository appear short. Remove or consolidate only content with verified
replacement coverage and verified absence of runtime/test references.

## Editorial and implementation standards

1. **One purpose per guide.** Write current behavior and bounded limitations;
   do not append dated status updates or contradictory progress diaries to
   customer-facing manuals.
2. **Operational truth before aspiration.** Explicitly distinguish designed,
   implemented, statically tested, native-integration tested, Windows-accepted,
   and production-authorized features.
3. **No fake business history.** Test data belongs only in disposable fixtures
   and isolated acceptance environments, never in customer initial datasets.
4. **No code for ordinary policies.** Customer workflows use forms, numeric
   inputs, controlled choices and reviewed effective dates; internal JSON and
   identifiers must not be exposed as mandatory operator steps.
5. **Native financial and academic authorities.** Do not create parallel
   ledgers or rewrite submitted financial records or earlier grade snapshots.
6. **Traceable changes.** Source edits require focused regression tests,
   exact-head checks and review; do not force-update `main` or clear the
   production hold to hide a failing gate.
7. **No invented facts.** Do not invent staff email addresses, classrooms,
   stock balances, signed installers, physical restore results, timestamps,
   financial amounts or success metrics.

For documentation defects, update the authoritative guide and the
regression contract rather than adding a new dated report that restates it.
