# Owner-configurable policy runtime matrix (2026-10-20)

Evidence for the eight owner-configurable policies. Each row names what the
real-site run (`tools/native/native_checks.py`, job *Native lifecycle
integration*) and the unit suite prove. A row marked **gap** is not proven.

Tested head: `df79e75` (native lifecycle `39400276822`, success). Merged to
`main` as `16d4f79` (PR #23). The merge tree equals the tested head.

## What every policy must pass

| Requirement | Evidence |
| --- | --- |
| Owner-only configuration (server-side) | `policy-owner-only-authority-matrix` (real site): the Course Owner creates a shell per policy; ten staff or outside users and the Administrator account (eleven actors in total) are refused on create, version and status with `PermissionError` naming the Course Owner role, before any argument is read. Table counts unchanged; the savepoint rolls back. Static binding: `tests/configuration/test_policy_authority_binding.py` (all 24 commands bound to `business_policy`). |
| Administrator refused | Same matrix (`Administrator` actor). `require_authority` refuses Administrator explicitly. |
| Invalid input rejected | Per-policy journey checks listed below; unit tests under `tests/`. |
| Persistence | Real-site reads after commit within the run. **Not proven across an application restart** (no restart test per policy). |
| Enforcement in the workflow | Per-policy journey checks listed below (unconfigured denial, then configured behavior). |
| Audit | Each command writes a receipt (`TH Configuration Operation`) and a hash-chained event (`TH Configuration Audit Event`). Asserted for the Owner Operations Policy; the other policies share the same `configuration_audit.execute` path. |

## Per policy

| # | Policy (DocType) | Owner commands | Runtime proof (real site) | Unit tests | Enforced consumer | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | TH Owner Operations Policy | `create_owner_operations_policy`, `set_owner_operations_policy_version`, `set_owner_operations_policy_status`, `validate_owner_operations_policy` | `owner-operations-lifecycle-validated-gate-off-switch`: unvalidated version does not resolve; invalid retention behavior and invalid time refused with no write; validation makes the backup terms live; retiring fails closed; receipts exist. | `tests/operations/test_owner_operations_policy.py`, `test_owner_backup_policy.py`, `test_backup_time_roundtrip_2026_10_20.py` | **Backup schedule, retention count, retention behavior and recovery public key only** (`product/backup.py`, `product/activate.py`, desk). | Backup terms **proven**. **Gap:** class capacity target, tax, transfer/withdrawal allowance and calendar notice have **no runtime consumer**; the product document already labels them decision inputs. Tax is native ERPNext authoritative. |
| 2 | TH Catalog Linkage Policy | `create_catalog_linkage_policy`, `set_catalog_linkage_version`, `set_catalog_linkage_status` | `enrollment-linkage-unconfigured-denied`, `enrollment-linkage-fixture`, `enrollment-s12-catalog-linkage-intake-gate` | `tests/academic/test_catalog_linkage.py` | Enrollment intake (`enroll_in_program`). | Proven (unconfigured denial, configured enforcement). |
| 3 | TH Returning Student Policy | `create_returning_student_policy`, `set_returning_student_policy_version`, `set_returning_student_policy_status` | `admission-s7-returning-link-reuse-enroll-bill` | `tests/admission/test_returning_policy.py` | Admission linking and reuse of prior student record. | Proven for the journey. |
| 4 | TH Enrollment Exit Policy | `create_enrollment_exit_policy`, `set_enrollment_exit_policy_version`, `set_enrollment_exit_policy_status` | `enrollment-s10-exit-withdraw-dismiss`: unconfigured denial, approver-role pin, billed/future/early/unknown denials, single-shot exits, dismissal approval/denial, off-switch. | `tests/enrollment/test_exit_policy.py` | Withdrawal and dismissal commands. | Proven, **on a synthetic decision fixture**. The canonical owner decision D5 still defers enrollment exits, so exits are closed in production until the Owner records a superseding decision. |
| 5 | TH Billing Policy | `create_billing_policy`, `set_billing_policy_version`, `set_billing_policy_status` | `finance-billing-unconfigured-denied`, `finance-s11-billing-policy-bounds-timing` | `tests/finance/test_billing_policy.py` | Tuition issuance date bounds and placement-fee timing. | Proven. |
| 6 | TH Roster Change Policy | `create_roster_change_policy`, `set_roster_change_policy_version`, `set_roster_change_policy_status` | `teaching-s8-roster-policy-add-move-offswitch` | `tests/teaching/test_roster_policy.py` | Mid-term add/move in a class. | Proven. |
| 7 | TH Attendance Correction Policy | `create_attendance_correction_policy`, `set_attendance_correction_policy_version`, `set_attendance_correction_policy_status` | `teaching-s9-attendance-correction-pin-window` | `tests/teaching/test_attendance_correction_policy.py` | Attendance correction window and approver role. | Proven. |
| 8 | TH Adjustment Posting Policy | `create_adjustment_posting_policy`, `set_adjustment_posting_version`, `set_adjustment_posting_status` | `teaching-orphan-unconfigured-denied`, `teaching-orphan-fixture`, `teaching-s13-orphan-adjustment-post-skip` | `tests/teaching/test_adjustment_posting.py` | Teacher compensation posting. | Proven. |

Related but not among the eight: the Correction Policy
(`finance-correction-policy-versioning`, `finance-correction-sod-and-window`)
is covered by its own real-site checks.

## What this does not prove

- Persistence across an application restart, per policy (only in-run reads).
- Owner-machine behavior: Windows, Docker Desktop, Task Scheduler and the
  backup helper's use of the Owner Operations terms.
- The Owner's real values. Every policy ships empty and fails closed until the
  Course Owner enters them.
- The gaps in row 1 (capacity, tax, transfer, withdrawal, calendar): these need
  an Owner decision on whether each should be enforced, and then a consumer.
