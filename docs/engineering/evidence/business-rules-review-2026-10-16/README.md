# Business-rule review (Priority 2) — 2026-10-16

Scope: configuration location, backend enforcement, permissions and audit, and
tests for valid, invalid, missing, and unauthorized settings, for the domains
the Course Owner listed. This is a **source inventory with test-presence
evidence**. It is not a per-setting verification. Business values are not
invented here. Where the owner has not decided, the result is **fail-closed** or
**not enforced**, and the owner decision is listed at the end.

Sources: `docs/owner-decisions.json` (`configurable_business_policy`,
`unresolved_business_inputs_not_reinterpreted`, `D6a`, `D6b`),
`apps/toefl_house/toefl_house/**/doctype/th_*_policy*`, and the tests named below.

## Shared configuration rules (verified in source)

- `configuration/rules.py`: versions are append-only and monotone by effective
  date. Ambiguous governing versions raise (no guessing). Readiness is computed
  (incomplete → configured → validated → effective → retired). Authorities are
  declared: only `business_policy` is bound, to the Course Owner. `operations` is
  unbound, and `custody` is never bound to Frappe.
- Tests: `tests/configuration/test_foundation.py` (57), `test_lifecycle.py` (44), `test_contract.py` (44).
  Named fail-closed cases include no governing version, a second policy refused,
  backdated or same-day versions refused, and a disabled owner holding no authority
  (`test_lifecycle.py::test_disabled_owner_holds_no_configuration_authority`).

## Domain inventory

| Domain (owner list) | Configuration location | Backend enforcement | Tests (verified by name or docstring) | Unset / invalid / unauthorized | Status |
|---|---|---|---|---|---|
| Assessment and progression | `academic/doctype/th_assessment_policy*` (status and versions only). Numeric grading terms are **not** stored. | Policy shell only. A guard test forbids numeric grading/cutoff constants in any Python module (`test_foundation.py::test_no_owned_python_module_contains_assessment_numeric_policy`). | `test_foundation.py` (progression evidence and target), `test_desk_contract.py` (progression chain) | No numeric rule exists, so none can be applied. Fail-closed by absence. | **Deferred by owner (D4, D5; unresolved inputs).** Not enforceable yet. |
| Refunds and corrections | `finance/doctype/th_correction_policy*`, `th_adjustment_posting_policy*` | `finance/corrections.py` states it supplies no default term, amount, tax, or refund rule. | `tests/finance/test_corrections.py`, `test_policy.py` (13), `test_containment_hooks.py` | Tested fail-closed for unconfigured corrections. Refund **terms** are not configured. | **Refund-term details deferred.** The mechanism exists; values do not. |
| Tax | Carried only in `th_owner_operations_policy` (tax field). `desk/configuration.py:108`: "tax terms are a decision carrier only and are NOT a live tax authority until a native finance consumer is explicitly implemented and qualified." | **None.** Not enforced anywhere. Tax is native ERPNext behaviour (`finance/__init__.py:214`). | `test_owner_operations_policy.py` checks storage, not tax computation. | No tax is computed, so no tax can be wrongly applied. Fail-closed by absence. | **Not enforced. Owner decision D6a, "tax not configured yet".** |
| Fees and billing | `finance/doctype/th_billing_policy*` (versions, bounds, timing, stage thresholds) | `finance/policy.py` plus billing commands gated by the receipted gate. | `tests/finance/test_billing_policy.py` (23, OD-NEW-03/04): `test_governing_read_fails_closed_without_policy_or_version`, `test_retire_is_the_off_switch`, `test_bad_bounds_are_refused`, `test_released_needs_a_decision`, `test_commands_route_through_the_receipted_gate`. `tests/enrollment/test_billing_guards.py` (9, S1). | Unset or invalid billing terms are refused and cannot silently default. | **Mechanism tested.** The owner's fee and discount values are not supplied (A7). |
| Capacity | `placement/*` allocation policy and owner-operations capacity target field | `tests/placement/test_allocation_policy.py` covers the read-boundary matrix. The owner-operations capacity field is a carrier. | `test_allocation_policy.py` (7), `test_config_policy.py` (22) | Not computed from a capacity target. | **Capacity target deferred (A7).** Not enforced as a limit. |
| Calendar | Carried in `th_owner_operations_policy` (calendar field). No calendar doctype enforces dates. | **None.** | `test_owner_operations_policy.py`, `test_contract.py` (presence only). | No calendar rule is applied. | **Deferred (A7): calendar details.** |
| Transfers | Carried in `th_owner_operations_policy` (transfer field). Exit and roster policies cover withdrawals and roster changes, not transfer rules. | **None** for transfers. | Presence only. | No transfer rule is applied. | **Deferred (A7).** |
| Withdrawals and exits | `enrollment/doctype/th_enrollment_exit_policy*` | `enrollment/exits.py` (stored reference syntax only; "this is not authorization"). | `tests/enrollment/test_exit_policy.py` (19, OD-NEW-07), `test_enrollment_exits.py` | Tested fail-closed for missing policy and invalid references. | **Mechanism tested.** Withdrawal terms are owner-deferred. |
| Enrollment changes | `teaching/doctype/th_roster_change_policy*` | Roster-change policy gating | `tests/teaching/test_roster_policy.py` (9, OD-NEW-05), `test_roster.py` (refuses unknown or disabled students and disabled or terminal classes) | Refused when unknown or disabled. | **Mechanism tested.** |
| Identity and guardian | `admission/doctype/th_returning_student_policy*`, `operations/doctype/th_guardian_lifecycle_policy*` | Returning-student and guardian-lifecycle policy; guardian guard (`foundation/test_guardian_guard.py`). | `tests/admission/test_returning_policy.py` (9, OD-NEW-01/B), `tests/operations/test_guardian_lifecycle_policy.py` (33), `test_guardian_guard.py` | Disabled students refused (`test_returning_lane.py`). | **Advanced guardian policy deferred** by the owner. |
| Attendance correction | `teaching/doctype/th_attendance_correction_policy*` | Correction policy | `tests/teaching/test_attendance_correction_policy.py` (14, OD-NEW-06) | Fail-closed named cases present. | Mechanism tested. |
| Permissions and audit (all of the above) | Roles through Frappe; `configuration/audit.py` hash-chained events | Native Frappe permissions; the configuration plane's audit chain | `tests/configuration/test_foundation.py`, `test_lifecycle.py` | Unauthorized configuration is refused by the bound-authority check. | Verified by tests. |

## Gaps found (action needed)

- **G1. Tax and calendar and transfer carriers are not enforced.** Their values can be stored in the Owner Operations policy, but nothing reads them. This is safe while the owner supplies no values, and it becomes a defect if an owner stores a value and expects it to apply. Mitigation: state in the owner package that these fields are carriers only. Test to add when a consumer exists: a stored tax, calendar, or transfer value must not change any billing or enrollment result until the consumer is qualified.
- **G2. No named unconfigured-value tests for tax, transfers, calendar, or capacity limits.** The billing and exit suites test unset values for those mechanisms. The carrier fields have no refusal tests because nothing consumes them.
- **G3. Owner decisions are not recorded for the deferred domains.** The register defers them, but no decision record names the values to supply. The owner package item A7 covers this.

No code change was made for G1 to G3. Adding behaviour for a deferred domain would invent a business rule, which the brief forbids.

## Owner decisions required (not invented here)

1. **Assessment and progression:** grading scale, pass marks, cutoffs, retake and progression rules (D4, D5).
2. **Tax:** whether tax applies, the rate and basis, and which native ERPNext consumer enforces it (D6a).
3. **Fees and discounts:** course, level, skill, and term pricing (A7; D6b confirms no online payment gateway at launch).
4. **Refund terms:** eligibility, deadlines, and amounts (A7).
5. **Capacity:** class capacity target and enforcement (A7).
6. **Calendar and transfers:** calendar details and transfer rules (A7).
7. **Withdrawals:** withdrawal terms and effective dates (A7).
8. **Identity and guardian:** advanced guardian rules beyond the current lifecycle (deferred).
9. **Enrollment changes:** roster-change rules and approval levels (A7).

Until each decision is recorded and a consumer is qualified, the corresponding domain is **not enforced**, and the release stays blocked for any domain the owner expects to run.
