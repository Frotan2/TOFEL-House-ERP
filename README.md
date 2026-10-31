# TOEFL House ERP

**Status: Release candidate — NOT APPROVED FOR PRODUCTION.**  
**Production authorization: REJECT / NO-GO.**  
**Customer data: TEST PACKAGE — NO REAL DATA.**

The TOEFL House ERP is a native-first institute management system based on
Frappe, ERPNext, Education and HRMS. The integration and review branch is
`work`; `main` is not yet the approved customer release. Review is tracked
in [draft PR #120](https://github.com/Frotan2/TOFEL-House-ERP/pull/120).

> **Existing Owner installation:** Preserve the existing Frappe site,
> `product/data`, Docker volumes, credentials, encrypted backups, and
> recovery keys. Routine use during the release hold is limited to documented
> read-only status checks. The Owner has separately authorized preserved,
> backed-up configuration and isolated synthetic acceptance on this PC;
> engineering must retain the authorization and evidence for each operation.
> Do not reinstall, reset, delete volumes or activate production on that computer.

## Product scope

The product coordinates applicant intake, placement, admission, enrollment,
programs and levels, scheduling, attendance, assessment, progression, tuition,
collections, books, instructor compensation and management reporting.

**Native system of record:** Frappe users/permissions; Education students,
programs, courses, groups, attendance and assessment; ERPNext invoice, stock,
cash, general-ledger and payment records; HRMS employees and payroll. The
`toefl_house` extension implements controlled processes and configurable
business policies around these native records. It must not keep a second
financial ledger, a duplicate student identity or an independent payroll.

The existence of an API or desk does **not** prove it is active, accepted,
licensed, correctly permissioned or authorized for real operation. Certain
advanced processes and integrations deliberately fail closed pending explicit
Owner policy and independent site acceptance.

## Customer delivery target

**The final customer must receive one verified, offline, provider-signed
Windows Setup EXE.** The customer opens it graphically, completes supported
Windows permission/restart prompts, and configures the institute using
ordinary English forms. They must not download dependencies separately,
extract nested ZIPs, build Docker images, use Git, PowerShell or edit JSON.

The repository contains the **provider-side builder and engineering test
components** for that target. A final signed installer, independent Windows
installation test, offline prerequisite acceptance, update/rollback rehearsal
and encrypted recovery verification have **not yet been certified here**.
Do not present a source ZIP, historical CI artifact or VBS fallback as the
finished customer installer. See
[Customer delivery](docs/CUSTOMER-DELIVERY.md) and
[Single-file delivery requirements](docs/engineering/SINGLE-FILE-CUSTOMER-DELIVERY.md).

### Fresh institute setup

This is a **new ERP deployment with no historical institute transactions**.
The customer package must contain no real or demonstration students,
enrollments, attendance, tuition invoices, payment entries, salary slips,
assessment results or practice databases. Synthetic acceptance fixtures
are isolated and are never transferred into the live site.

The Owner configures programs and levels, semester fees and allowed payment
schedules, assessment/passing rules, timetable, capacities, rooms, instructors,
staff roles and financial controls from guarded pages. Approved business
values are sourced from [Owner decisions](docs/owner-decisions.json), not
hard-coded guesses or obsolete dated reports. Operational policies must be
editable through controlled **no-code forms**, with review, effective dates,
permissions and an audit trail.

The approved initial account plan comprises **six operational logins
including the existing Owner**. The remaining users are the General Manager,
Finance Manager, Academic Manager, Receptionist and one Instructor. Business
ownership is distinct from unrestricted application access. Official email
addresses must not be invented; no invitations are sent to unknown addresses.

## Daily operation and support

Each staff member uses an authorized role desk, with server-side permission
checks and an auditable action. The institute uses English, left-to-right
customer interfaces. Staff must not see developer codes, raw policy JSON,
secret material or unrelated private employee and student information as
ordinary tasks.

- [Owner Handbook](product/windows/OWNER%20HANDBOOK.txt) — graphical
  operation, safety boundaries and staff responsibilities
- [Daily Use Guide](product/windows/DAILY%20USE%20GUIDE.txt) — concise staff
  workflow
- [Customer updates](docs/CUSTOMER-UPDATES.md) — signed channel requirements;
  update operations remain held
- [Windows validation](product/windows/VALIDATION.md) — recorded test
  acceptance on a **disposable** machine; read-only guidance for a preserved
  existing installation

Never reset Docker, remove `product/data`, install over an existing site or
restore a backup over live records as a workaround. Use **Check This PC** and
**Copy Safe Support Status** when the launcher is available.

## Source layout

| Directory | Responsibility |
| --- | --- |
| `apps/toefl_house/` | TOEFL House business commands, policy control, role desks, validation |
| `apps/foundation_security/` | Native-stack security hardening |
| `product/` | Container runtime, Windows launcher, offline installer inputs, encrypted recovery tools |
| `tools/native/` | Real Frappe/Education/ERPNext/HRMS integration acceptance |
| `tools/foundation/` | Pinned dependencies, security and runtime checks |
| `tools/release/` | Provider-side packaging, integrity and signed-release mechanisms |
| `tests/` | Synthetic offline, contract and regression tests |
| `docs/` | Current specifications, owner decisions and separated engineering evidence |

Exact upstream versions are specified in
[foundation-version-matrix.json](docs/engineering/foundation-version-matrix.json).

## Developer verification

Use an isolated checkout and disposable test environment. Local static
verification does not substitute for native integration, installed Windows
or release acceptance.

```bash
python3 -m unittest discover -s tests -t .
ruff check .
for f in tests/foundation/*.cjs; do node "$f"; done
```

The required release checks are **Owned suite**, **Native lifecycle
integration**, **Foundation runtime**, **Product image** and **Windows
customer package smoke**, all for the **exact proposed source commit**.
Real financial reconciliation, independent role/security review, real Windows
click-through acceptance, separate encrypted backup and tested two-person
isolated restore are additional mandatory release gates. A queued, failed,
skipped or stale check does not qualify the release.

**Do not merge `work` to `main`, delete evidence, enable an update channel
or change production authorization until all applicable gates pass and the
Owner gives explicit written approval.**

## Documentation authority

Start with [Documentation and release authority](docs/DOCUMENTATION.md).
It identifies maintained customer instructions, engineering specifications,
the Owner's policy record and retained **dated audit evidence**. Old reports
and synthetic histories are not the institute's operational history, and
their older pass/fail claims must not override the current exact-head result.

License: [MIT](LICENSE). Do not commit credentials, student records,
payment data, payroll data, database dumps, recovery keys or backups.
