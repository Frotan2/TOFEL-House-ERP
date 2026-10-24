# Mission 7 — Independent Security, Data Integrity & Adversarial QA Report (2026-10-24)

## 1. Executive Release Recommendation

- **Production Release Recommendation:** **`REJECT` (NO-GO FOR PRODUCTION)**
- **Pending Feature PRs (#46, #48, #49, #50, #51) & Unmerged Branch (`arena/e281e864-tofel-house-erp`):** **`REJECT` (DO NOT MERGE WITHOUT REQUIRED FIXES)**
- **Audited Repository:** `Frotan2/TOFEL-House-ERP`
- **Audited `main` Baseline SHA:** `c22b9979542c88a2cd179e179a91829d07a79a3a`
- **Adversarial Test Suite Added:** `tests/security/test_adversarial_qa_2026_10_24.py` (`18` tests; full repository suite `1,719` tests passing, `9` platform skips, `0` Ruff errors, `4/4` Node suites passing).

---

## 2. Exact-SHA Audit & Qualification Matrix

| Target / Mission | Branch / PR | Exact Commit SHA | Owned Suite (`ruff` + `unittest` + `node`) | Hosted CI Status (Exact SHA) | QA Disposition |
|---|---|---|---|---|---|
| **Baseline `main`** | `main` | `c22b9979542c88a2cd179e179a91829d07a79a3a` | PASS (`1,701` base / `1,719` with QA additions) | Owned `40087474249` PASS; Native `40087484777` PASS; Runtime `40087486356` PASS; Image `40087474300` PASS; Package `40087487984` PASS | **Engineering RC Baseline Only — Production `REJECT`** (4 Medium/Low findings on `main` + open physical/business blockers `#12`, `#35`, `#36`, `#40`) |
| **Mission 1 (Windows Updater)** | PR #46 (`arena/fa9a38ba-tofel-house-erp`) | `e8145954cdc081e84cc8aa2356e152c5ceda415d` | PASS (`1,849` tests) | Owned `40086886925` PASS; Native `40086885839` PASS; Runtime `40086885878` PASS; Package `40086885895` PASS | **`REJECT` / KEEP UNMERGED** (High: unauthenticated/ephemeral update transaction token bypasses channel/compatibility checks; Medium: `_rebind_apply` `KeyError` & `migration: "none"` failure; `-Action Check` double-downloads archive) |
| **Mission 2 (Academic Assessment & Progression)** | PR #49 (`arena/f83343be-tofel-house-erp`) | `50ca132aa437eb7e491556599e0ea9a12a1f56c5` | PASS (`1,838` tests) | Owned `40091867450` PASS; Native `40091858486` PASS; Runtime `40091858494` PASS | **`REJECT`** (Critical: `TH Progression Decision` lacks `student_group` column causing MariaDB `OperationalError 1054` & broken branch ACL; High: `Instructor + Enrollment Officer` role-union leak, superseded result progression bypass, missing `FOR UPDATE`, unguarded `progression_state`; D1 policy hold) |
| **Mission 3 (Class Operations, Scheduling & Mobility)** | PR #51 (`arena/197fb66a-tofel-house-erp`) | `96330eaec7572094b8826f0045fb98f63ff641fa` | PASS (`1,856` offline tests) | Owned `40092407981` PASS; **Native `40092388242` FAIL** (`KeyError: 'name'` importing `custom_field.json`) | **`REJECT`** (Critical: Native install fails on missing `"name"` in `custom_field.json`; High: `class_availability`/`waiting_list_board` omit `require_operational()` and branch isolation; `move_class_member` steals reserved waiting-list seats; `check_new_session` bypasses suspensions and link checks; `overlapping_suspension` interval bug; AB-BA lock order in transfers; D5 policy hold) |
| **Mission 4 (Finance, Tax, Cashier & Refunds)** | PR #50 (`arena/2537b25b-tofel-house-erp`) | `6a183b5c400555630526166f33bcc8668aab26d7` (prior `e2882fc13b848594a139b44c37a98089224e87c9`) | PASS (`1,783` tests) | Owned `40092778399` PASS; Native `40092775298` pending | **`REJECT`** (High: `refund_allocation_ok` duplicate-line over-refund bypass, unchecked `paid_amount`/`deductions`; `prior_returns_for` duplicate-item overwrite; partial-drawer cashier close & false multi-company `"Closed"` desk state; Medium: cross-company scope leaks & missing `Company` lock) |
| **Mission 5 (Communications & Self-Service Portals)** | PR #48 (`arena/82235d06-tofel-house-erp`) | `d7dffdbacad0926f51aba9e060e1cf1ff04733a4` | **FAIL** (`2` unit test failures) | **Owned `40091218467` FAIL**; Native `40091210180` PASS; Runtime `40091210188` PASS | **`REJECT`** (Critical: CI failures; `try/except: pass` around `require_authority`; DOM XSS via `innerHTML`; Guardian self-consent & `student=None` access check bypass; High: Student scope/email fallback & `extra_filters` overwrite; process-global mutable dicts; fake external delivery; D4 policy hold) |
| **Mission 6 (Role Desks & Executive Analytics)** | Branch `arena/e281e864-tofel-house-erp` (no PR) | `4a9178061981c266768b3d6afe669244e631b76d` | **FAIL** (`4` Ruff errors + `test_role_desks.cjs` crash) | Not opened as PR | **`REJECT`** (High: `th_role_desks.js:527` crashes with `TypeError: secondary.removeClass is not a function`; `PROJECTION_FIELDS` omits `Item`, `Bin`, `Additional Salary`, `Salary Slip` causing `book_stock_metrics` and `payroll_metrics` to always fail to `0`; `Course Owner` granted `payroll_authorized=True`; `drill_path` routes invalid; `analytics.py` swallows schema-strict test failures) |
| **Mission 8 (Consolidated Engineering RC)** | PR #52 (`arena/f3ce64a9-tofel-house-erp`) | `beaf67aa15fb6316e9eb9f401eb4c19991167867` (prior `632be0cff8d3eec4d0ea7ef62e6d0a80fe19c012`) | PASS (`1,710` tests) | Owned `40092827055` PASS; Package `40092808302` PASS (on `632be0c`); `40093213681` running on `beaf67a` | **Engineering RC Packaging Only — Production `REJECT`** (Correctly holds/excludes PRs #46, #48, #49, #50, #51 and enforces exact-SHA 4-gate receipt in `create_customer_package.py`) |

---

## 3. Severity-Ranked Findings Register

### 3.1 Baseline `main` (`c22b9979542c88a2cd179e179a91829d07a79a3a`)

#### `[MAIN-01]` (Medium) — Inactive/Withdrawn Roster Rows Permitted in `record_attendance` and `_roster_read`
- **Location:** `apps/toefl_house/toefl_house/teaching/__init__.py:466-470, 520-523`
- **Description:** Both `_roster_read()` (`select distinct student from tabStudent Group Student where parent = %s`) and `record_attendance()` (`select student from tabStudent Group Student where parent = %s order by group_roll_number asc`) omit `and active = 1`. In addition, `record_attendance()` does not check whether the parent `Student Group` has `disabled = 1` or a terminal `th_class_status` (`Completed` / `Closed`).
- **Impact:** After a student is exited via `enrollment/exits.py` (which sets `Student Group Student.active = 0`), `record_attendance` still accepts and submits `Student Attendance` marks for that withdrawn student, and `_roster_read` still grants temporary `Student` read visibility for inactive roster members.
- **Reproduction:** Tested in `tests/security/test_adversarial_qa_2026_10_24.py::BaselineMainDefectReproductionTests::test_adv_main_02_teaching_record_attendance_and_roster_read_omit_active_filter`.
- **Required Fix:** Add `and active = 1` to both SQL queries in `_roster_read` and `record_attendance`, and verify `Student Group.disabled == 0` and non-terminal `th_class_status` before recording attendance.

#### `[MAIN-02]` (Medium) — `desk._apply_scope` Skips Branch Filter When `"name"` Is in `filters` and Omits `Sales Invoice` in `TH Correction Request` Branch Chain
- **Location:** `apps/toefl_house/toefl_house/desk/__init__.py:555-564, 596-604`
- **Description:**
  1. `_apply_scope(desk, doctype, filters)` checks `if branch_filter is not None and "name" not in filters: filters["name"] = branch_filter` (and similarly `if meta_field and meta_field not in filters:`). If any caller passes `filters={"name": ...}` to `project_rows` / `project_count`, `_apply_scope` skips `branch_filter` instead of intersecting the allowed branch names with the caller-supplied `name` filter.
  2. `_branch_allowed_names("TH Correction Request", branches)` only resolves requests linked via `fees` (`filters={"fees": ("in", fee_names)}`) and omits requests linked via `sales_invoice`, hiding all `Sales Invoice` correction requests from branch-scoped Finance Officers.
- **Reproduction:** Tested in `tests/security/test_adversarial_qa_2026_10_24.py::BaselineMainDefectReproductionTests::test_adv_main_01_desk_apply_scope_skips_branch_filter_when_name_in_filters`.
- **Required Fix:** Intersect caller-supplied `filters["name"]` / `filters[meta_field]` with `branch_filter` / `allowed`, and include `Sales Invoice` rows for ` roster` students in `_branch_allowed_names("TH Correction Request", branches)`.

#### `[MAIN-03]` (Medium) — `administration._require_control_role` Omits `Administrator` Exclusion and `require_operational()`
- **Location:** `apps/toefl_house/toefl_house/administration.py:186-277`
- **Description:** Unlike `toefl_house.security.authorize()`, `_require_control_role()` in `administration.py` does not reject `user == "Administrator"` and does not check `User.enabled` directly. Furthermore, `set_managed_role` relies on an unordered `frappe.get_all("Version", ..., limit_page_length=25)` substring `LIKE` match on `Version.data` for `request_key` idempotency, which can miss prior keys once more than 25 `Version` rows exist on a `User`.
- **Reproduction:** Tested in `tests/security/test_adversarial_qa_2026_10_24.py::BaselineMainDefectReproductionTests::test_adv_main_03_administration_set_managed_role_omits_operational_and_admin_guard`.
- **Required Fix:** Refuse `Administrator` in `set_managed_role` (matching D8 governance rules) and add `order_by="creation desc"` or a dedicated idempotency receipt table for role-assignment operations.

#### `[MAIN-04]` (Medium) — Missing Maker-Checker Self-Approval Refusal in Financial and Attendance Corrections
- **Location:** `apps/toefl_house/toefl_house/finance/corrections.py:124-127, 360-445, 515-575` and `apps/toefl_house/toefl_house/teaching/attendance_corrections.py:249-253, 302-365`
- **Description:** `approve_invoice_correction`, `approve_fees_correction`, and `approve_attendance_correction` verify that `actor` holds the pinned `approver_role`, but never check `if actor == req.owner:` or `if actor == req.requested_by:`. If a policy sets `approver_role = "Finance Officer"` (or `"Attendance Recorder"`), or if a staff user holds both the requester role and the approver role, that user can request and self-approve their own credit note, fee cancellation, or attendance change.
- **Reproduction:** Tested in `tests/security/test_adversarial_qa_2026_10_24.py::BaselineMainDefectReproductionTests::test_adv_main_04_correction_approvals_omit_self_approval_maker_checker_guard`.
- **Required Fix:** Enforce `if actor == req.owner: raise frappe.PermissionError(...)` in `finance/corrections.py` and `if actor == req.requested_by: raise frappe.PermissionError(...)` in `teaching/attendance_corrections.py`.

---

### 3.2 PR #48 — Communications, Notifications & Self-Service Portals (`d7dffdbacad0926f51aba9e060e1cf1ff04733a4`, Mission 5)

#### `[PR48-01]` (Critical / Release Blocker) — Owned Suite CI Failure: Hard-Coded `AGE_PRIVACY_THRESHOLD = 18` and 5 Unguarded `doc_events`
- **Location:** `apps/toefl_house/toefl_house/operations/guardian_portal.py:21` and `apps/toefl_house/toefl_house/hooks.py:135-159`
- **Description:** Hosted CI run `40091218467` and local reproduction fail on:
  1. `test_no_owned_python_module_contains_assessment_numeric_policy`: `AGE_PRIVACY_THRESHOLD = 18` violates the D1/D4 no-invented-threshold contract.
  2. `test_no_unguarded_doctype_events`: `TH Guardian Consent`, `TH Notification`, `TH Portal Announcement`, `TH Portal Configuration`, and `TH Notification Dispatch Rule` were added to `hooks.py` without governance containment wiring.
- **Required Fix:** Remove invented policy constants and unapproved notification/portal DocTypes; align with D4 hold and `TH Alerting Policy`.

#### `[PR48-02]` (Critical) — Authority Gate Bypass via `try: require_authority(...) except Exception: pass`
- **Location:** `apps/toefl_house/toefl_house/operations/portal_policy.py:121-126` and `apps/toefl_house/toefl_house/operations/notifications.py:281-286`
- **Description:** Both `_require_course_owner()` functions wrap `security.require_authority("business_policy")` inside `try: ... except Exception: pass` and then only check `"Course Owner" in roles`. This completely defeats `require_operational()`, `Administrator` exclusion, and `User.enabled` verification, allowing a disabled user or a `REFUSED` site to mutate portal and notification policies.
- **Required Fix:** Remove the `try/except` wrapper and delegate to `toefl_house.security.authorize()` + `configuration_audit.execute()`.

#### `[PR48-03]` (Critical) — Stored / DOM XSS in Student and Guardian Portals via Unescaped `innerHTML`
- **Location:** `apps/toefl_house/toefl_house/public/js/th_student_portal.js:48, 86, 99` and `apps/toefl_house/toefl_house/public/js/th_guardian_portal.js:58, 95`
- **Description:** Both portal scripts interpolate database fields (`s.student_name`, `a.title`, `a.body`, `c.student_name`, `c.student`) directly into `container.innerHTML` without HTML escaping or DOM text-node construction.
- **Required Fix:** Build DOM nodes using `document.createElement` and `.textContent` (matching `th_role_desks.js`).

#### `[PR48-04]` (Critical) — Guardian Self-Attested Consent Privilege Escalation and `student=None` Scope Bypass
- **Location:** `apps/toefl_house/toefl_house/operations/guardian_portal.py:92-125, 224-275, 290-360` and `th_guardian_consent.json:112-135`
- **Description:**
  1. `record_consent()` is `@frappe.whitelist(methods=["POST"])` and allows a user with only the `"Guardian"` role to pass `status="Active"` and self-grant guardian consent for any student linked to them.
  2. `th_guardian_consent.json` grants `"Guardian"` native `create: 1, write: 1, share: 1` permissions on `TH Guardian Consent`.
  3. `get_child_attendance(student=None)`, `get_child_timetable(student=None)`, `get_child_progress(student=None)`, and `get_child_invoices(student=None)` only call `_can_access(guardian, student, ...)` inside `if student:`. When `student` is omitted (`None`), they return data for all linked children (`students = [c["student"] for c in children]`) **without checking consent or age privacy (`_can_access`) at all!**
  4. `_is_consent_valid` treats a blank `expiry_date` as valid forever.
- **Required Fix:** Restrict `record_consent` and native `TH Guardian Consent` writes to authorized staff commands, require `expiry_date`, and enforce `_can_access` on every child returned when `student=None`.

#### `[PR48-05]` (High) — Student Portal Scope Validation Bypass, Mutable Email Fallback, and `extra_filters` Filter Overwrite
- **Location:** `apps/toefl_house/toefl_house/operations/student_portal.py:42-95, 195-215`
- **Description:**
  1. `_get_student_for_user` does not call `foundation_security.guards.validate_student_scope(user)` or `security.require_operational()`, and falls back to `student_email_id`, allowing a multi-linked user or matching mutable email address to resolve a student record.
  2. `_project(doctype, fields, student, extra_filters=None)` runs `filters.update(extra_filters)`, allowing `extra_filters` to overwrite `"student"` or `"docstatus"`.
  3. `get_my_invoices` falls back to `filters={"student": student["name"]}` when `customer` is unset, querying a column (`Sales Invoice.student`) that does not exist on `Sales Invoice` unless custom-added, or returning unfiltered rows in stub environments.
- **Required Fix:** Enforce `validate_student_scope`, `require_operational()`, and immutable `student`/`docstatus` filter binding after `extra_filters`.

#### `[PR48-06]` (High) — Process-Global Mutable State Dicts, Unenforced `VALID_TRANSITIONS`, and Fake External Provider Delivery
- **Location:** `notifications.py:44-46`, `portal_policy.py:39`, `guardian_portal.py:29`, `external_provider.py:82-115`, `th_notification.py:16-38`
- **Description:** Module-level Python dicts (`_DISPATCH_RULES`, `_MEM_NOTIFICATIONS`, `_PORTAL_CONFIG`, `_CONSENT_STORE`) leak state across requests/sites in multi-worker Gunicorn processes; `external_provider.py` returns `"status": "delivered"` via regex validation with no provider transport; `THNotification.validate()` never checks `VALID_TRANSITIONS`.
- **Required Fix:** Remove all process-global state dicts and stubbed external provider claims.

---

### 3.3 PR #49 — Academic Assessment, Grading, Publication & Progression (`50ca132aa437eb7e491556599e0ea9a12a1f56c5`, Mission 2)

#### `[PR49-01]` (Critical) — Broken `TH Progression Decision` Branch Isolation (`OperationalError 1054` on MariaDB & `has_permission` Always `False`)
- **Location:** `apps/toefl_house/toefl_house/permissions.py:219-224, 275-280` and `apps/toefl_house/toefl_house/toefl_house/doctype/th_progression_decision/th_progression_decision.json`
- **Description:** `permissions.py` maps `"TH Progression Decision": "progression_decision"` in `BRANCH_KINDS`, and `_branch_condition` generates `` `tabTH Progression Decision`.student_group IN (...) `` while `_doc_branches` reads `doc.get("student_group")`. However, `TH Progression Decision` has **no `student_group` field in its schema** (only `program_enrollment`, `student`, `academic_result`).
- **Impact:** On MariaDB, any list query on `TH Progression Decision` by a branch-scoped user crashes with `pymysql.err.OperationalError: (1054, "Unknown column 'tabTH Progression Decision.student_group' in 'where clause'")`, and `has_permission` always returns `False` for branch-scoped users because `doc.get("student_group")` is `None`.
- **Required Fix:** Join through `tabTH Academic Result` or `tabProgram Enrollment` in `_branch_condition` and `_doc_branches` (or add a populated, non-nullable `student_group` field to `TH Progression Decision`).

#### `[PR49-02]` (High) — Multi-Role Union Widens `assessment_book` Access for `Instructor + Enrollment Officer` and Omits `emp.status = 'Active'`
- **Location:** `apps/toefl_house/toefl_house/permissions.py:34-49, 408-417, 505-512`
- **Description:**
  1. In `has_permission` (`permissions.py:408-417`), `_instructor_reads` is only called when `not (roles & {"Academic Manager", "Teaching Auditor", "Course Owner", "General Manager"})`. For `kind == "assessment_book"`, `can_read` (`policy.py:610-611`) returns `True` for `"Instructor"` and `"Enrollment Officer"` (where `"Enrollment Officer"` is only supposed to read `"Published"` books). If a user holds both `"Instructor"` and `"Enrollment Officer"`, `can_read` returns `True` for a `Draft` book via `"Instructor"`, and if they also hold any manager/auditor role or in `_query_role`, the role union is not scoped per-role.
  2. `INSTRUCTOR_GROUPS_SQL` (`permissions.py:34-49`) joins `tabEmployee emp` with `emp.user_id = {user}` but omits `AND emp.status = 'Active'`, allowing an Instructor whose `Employee` record is `Left` / `Suspended` to continue reading assessment books and scores.
- **Required Fix:** Add `AND emp.status = 'Active'` to `INSTRUCTOR_GROUPS_SQL` and evaluate role-specific constraints per role rather than taking the union of `can_read` and role exemptions independently.

#### `[PR49-03]` (High) — Superseded Academic Result Does Not Invalidate Existing Progression Decision (`next_level_eligibility` Bypass)
- **Location:** `apps/toefl_house/toefl_house/academic/assessment.py:855-945` and `apps/toefl_house/toefl_house/academic/progression.py:421-440`
- **Description:** When `correct_published_result` marks an original `TH Academic Result` (`RES-1`) as `status = "Superseded"` and creates a replacement result (`RES-2`, e.g., failing), any `TH Progression Decision` (`Advance`) previously recorded against `RES-1` remains untouched. `next_level_eligibility(student, target_program)` (`progression.py:421-440`) checks `TH Progression Decision` without verifying that the linked `academic_result` still has `status == "Published"`. Consequently, a student whose passing result was superseded by a failing correction still passes `assert_enrollment_progression_gate` and can enroll in the next level!
- **Required Fix:** In `next_level_eligibility`, verify that `frappe.db.get_value("TH Academic Result", decision.academic_result, "status") == "Published"`, and mark or supersede linked `TH Progression Decision` rows when `correct_published_result` supersedes a result.

#### `[PR49-04]` (High) — Missing `FOR UPDATE` Lock in `decide_progression` / `override_progression` and Unguarded `frappe.get_all` in `progression_state`
- **Location:** `apps/toefl_house/toefl_house/academic/progression.py:55-68, 183-200, 455-475`
- **Description:**
  1. `_published_result(result_name)` reads `TH Academic Result` via `frappe.get_doc` without `for_update=True`, creating a TOCTOU race with `correct_published_result` (which can supersede the result concurrently while `decide_progression` is inserting a decision).
  2. `progression_state(student)` (`progression.py:455-475`) checks `frappe.has_permission("Student", "read", doc=clean_student)` and then queries `TH Academic Result` and `TH Progression Decision` using `frappe.get_all` (which ignores `permission_query_conditions` and `has_permission`), leaking internal draft/marking/review academic results and progression decisions to any role with `Student` read access (such as Reception / Admission / Finance / Student / Guardian).
- **Required Fix:** Lock `TH Academic Result` with `for_update=True` inside `_published_result`, and enforce role/branch/publication checks in `progression_state`.

---

### 3.4 PR #50 — Billing, Tax, Cashier Close & Book-Commerce (`6a183b5c400555630526166f33bcc8668aab26d7` / `e2882fc13b848594a139b44c37a98089224e87c9`, Mission 4)

#### `[PR50-01]` (High) — Refund Over-Allocation via Duplicate Reference Rows, Unchecked `paid_amount`/`deductions`, and Duplicate-Line Return Overwrite
- **Location:** `apps/toefl_house/toefl_house/finance/refunds.py:95-138, 202-220`
- **Description:**
  1. In `refund_allocation_ok(doc)` (`refunds.py:202-220`), the loop over `doc.get("references")` checks each `ref` row individually against `already + allocated > credit_mag + 0.005` **without accumulating `allocated` across duplicate rows referencing the same `reference_name` in the same `Payment Entry`!** A single `Payment Entry` with two reference rows pointing to the same credit note (`SINV-RET-1`, each for 100% of `credit_mag`) passes `refund_allocation_ok` and refunds 200% of the credit note.
  2. `refund_allocation_ok` never checks `ref.get("reference_doctype") == "Sales Invoice"`, never verifies `float(doc.get("paid_amount")) <= sum(allocated)`, and never forbids non-empty `doc.get("deductions")`.
  3. In `prior_returns_for(invoice_name, exclude_name=None)` (`refunds.py:119-135`), `per_inv[parent][code] = round(abs(qty), 6)` **overwrites** instead of summing (`+=`) when a return invoice contains two line items with the same `item_code`, under-counting prior returned quantities and allowing subsequent over-returns.
  4. When cancelling an already-submitted return invoice (`before_cancel`), `validate_book_return` calls `prior_returns_for(orig_name, exclude_name=getattr(doc, "name", None))` — if `doc` is validated without `exclude_name` matching or during cancellation checks, return reversal must not reject native cancellation.
- **Required Fix:** Accumulate `allocated` per `reference_name` across all rows in `doc.references`, require `reference_doctype == "Sales Invoice"`, assert `round(paid_amount, 2) == round(total_allocated, 2)` and `not doc.get("deductions")`, and use `+=` in `prior_returns_for`.

#### `[PR50-02]` (High) — Partial-Drawer Cashier Close Bypass, False Multi-Company `"Closed"` Desk Status, and Cross-Company Scope Leaks
- **Location:** `apps/toefl_house/toefl_house/finance/cashier.py:194-273`, `apps/toefl_house/toefl_house/desk/finance.py:778-835, 864-869`, `apps/toefl_house/toefl_house/finance/taxes.py:220-265`, and `apps/toefl_house/toefl_house/permissions.py`
- **Description:**
  1. `reconcile_cashier_day(request_key, company, date, counts)` (`cashier.py:194-273`) iterates only over the accounts submitted by the caller in `counts` rather than requiring all active Cash/Bank accounts of `company` (from `expected_balances_for_day`). A cashier can omit a drawer with a shortage and close the day as `"Balanced"`.
  2. `reconcile_cashier_day` does not verify that `actor` has native `Company` permission (`frappe.has_permission("Company", "read", doc=company, user=actor)`) and does not lock the parent `Company` row (`SELECT name FROM tabCompany WHERE name=%s FOR UPDATE`) before checking `frappe.db.exists(RECON, {"company": clean_company, "reconciliation_date": clean_day})`, allowing a concurrent race or cross-company close.
  3. In `desk/finance.py:784-835`, `closed_today = bool(recons_today)` evaluates `True` as soon as **any single company** has a `TH Cashier Reconciliation` for today, displaying `"Cash close today": "Closed"` and hiding open drawers (`if not closed_today:`) for all other companies in a multi-company scope.
  4. `desk/finance.py:778-780, 864-869`, `finance/taxes.py:220-265` (`inspect_tax_template_readiness`), and `permissions.py` (`query_cashier_reconciliation`) do not filter by the viewer's `Company` User Permissions.
  5. `reconcile_cashier_day` reuses `TH Billing Policy.max_backdate_days` instead of a dedicated cashier policy bound, and `cashier_drift` checks `tabGL Entry` across all company accounts rather than the reconciled Cash/Bank accounts.
- **Required Fix:** Require all company Cash/Bank drawers with activity/balance to be included in `counts`, enforce `Company` User Permissions in `reconcile_cashier_day`, `inspect_tax_template_readiness`, `permissions.py`, and `desk/finance.py`, lock `Company` with `FOR UPDATE`, and compute `closed_today` per company.

---

### 3.5 PR #51 — Class Operations, Scheduling, Capacity & Student Mobility (`96330eaec7572094b8826f0045fb98f63ff641fa`, Mission 3)

#### `[PR51-01]` (Critical / CI Failure) — Native Site Install Crashes with `KeyError: 'name'` on `fixtures/custom_field.json`
- **Location:** `apps/toefl_house/toefl_house/fixtures/custom_field.json:401-443`
- **Description:** Confirmed in hosted `native` CI run `40092388242` (`install-placement-test.localhost-toefl_house failed (exit 1)` with `builtins.KeyError: 'name'`). The four new `Custom Field` entries (`th_session_kind`, `th_session_status`, `th_replaces`, `th_session_note` on `Course Schedule`) omit the `"name"` key (`"Course Schedule-th_session_kind"`, etc.), causing Frappe's `import_file_by_path` to crash during app installation and migration.
- **Required Fix:** Add `"name": "Course Schedule-<fieldname>"` (and standard fixture keys) to all four `Custom Field` records in `apps/toefl_house/toefl_house/fixtures/custom_field.json`.

#### `[PR51-02]` (High) — `class_availability` and `waiting_list_board` Omit `require_operational()` and Bypass Branch Isolation
- **Location:** `apps/toefl_house/toefl_house/teaching/capacity.py:666-810`
- **Description:** Both `@frappe.whitelist()` endpoints (`class_availability` and `waiting_list_board`) check role membership via `frappe.get_roles(user)` without calling `security.require_operational()` (so they execute even on a `REFUSED` site and for `Administrator`) and query `Student Group` and `TH Class Waiting List` via `frappe.get_all` (which bypasses `permission_query_conditions`), exposing class capacity and student waiting-list entries across all branches to branch-scoped users.
- **Required Fix:** Call `security.require_operational()`, refuse `Administrator`, and filter `Student Group` and `TH Class Waiting List` by the caller's allowed branches (`permissions._user_branches(user)`).

#### `[PR51-03]` (High) — `move_class_member` Bypasses Waiting-List Seat Reservations (`_require_capacity` vs `assert_seat_available`)
- **Location:** `apps/toefl_house/toefl_house/teaching/__init__.py:751-755`
- **Description:** While `assign_class_roster` (`teaching/__init__.py:438`) and `transfers.py` were updated to call `class_capacity.assert_seat_available(to_group, incoming=1, for_student=...)` (which counts unexpired `"Offered"` waiting-list seats as reserved), `move_class_member` (`teaching/__init__.py:751-755`) still calls the legacy `_require_capacity(to_doc, incoming=1)`, which ignores `TH Class Waiting List` offers. Moving a student via `move_class_member` steals a seat reserved for a waiting-list candidate, causing `accept_waiting_list_offer` to later fail or overfill the class.
- **Required Fix:** Replace `_require_capacity(to_doc, incoming=1)` in `move_class_member` with `class_capacity.assert_seat_available(to_name, incoming=1, for_student=clean_student)`.

#### `[PR51-04]` (High) — `check_new_session` (`generate_timetable`, `postpone_session`, `schedule_replacement_session`) Bypasses Class Suspensions, Link Existence, and `Instructor.status == "Left"`
- **Location:** `apps/toefl_house/toefl_house/teaching/scheduling.py:173-270`
- **Description:** Unlike `schedule_class_session` (`teaching/__init__.py:240-310`), `check_new_session` in `scheduling.py` (used by `generate_timetable`, `postpone_session`, and `schedule_replacement_session`, all of which insert `Course Schedule` with `ignore_links=True`):
  1. Never calls `class_suspensions.assert_scheduling_allowed(group_name, clean_day)`, allowing timetables, postponed sessions, and makeup sessions to be scheduled right in the middle of an active class suspension (`TH Class Suspension`)!
  2. Never verifies that `Instructor` and `Room` exist or that `Instructor.status != "Left"`.
  3. Never validates that `course` belongs to the group's `Program` catalog (`Program Course`).
- **Required Fix:** Call `class_suspensions.assert_scheduling_allowed(group_name, clean_day)` and validate `Instructor` (existence + `status != "Left"`), `Room` existence, and `Program Course` membership inside `check_new_session`.

#### `[PR51-05]` (High) — `overlapping_suspension` Interval Bug Allows Overlapping and Chained Class Suspensions Bypassing `max_days`
- **Location:** `apps/toefl_house/toefl_house/teaching/suspensions.py:70-84, 177-193`
- **Description:**
  1. `overlapping_suspension(student_group, on_date)` only accepts a single date (`start`) and checks `from_date <= start <= until_date`. Inside `_suspend` (`suspensions.py:192`), it calls `overlapping_suspension(clean_group, start)`. If an existing suspension covers `2026-11-10..2026-11-15` and a new suspension is requested for `2026-11-05..2026-11-20`, `start` (`2026-11-05`) is before `2026-11-10`, so `overlapping_suspension` returns `None` and allows the overlapping suspension! Furthermore, adjacent suspensions can be chained back-to-back to bypass `max_days`.
  2. `_suspend` only checks `group.get("th_class_status") in ("Completed", "Closed")` and ignores `int(group.get("disabled") or 0) == 1`.
- **Required Fix:** Check full interval overlap (`from_date <= end AND until_date >= start`) in `overlapping_suspension(student_group, start, end)` and reject `int(group.get("disabled") or 0) == 1`.

#### `[PR51-06]` (Medium) — Unsorted Lock Order (AB-BA Deadlock), Missing `FOR UPDATE` on `TH Class Transfer`, Duplicate Open Transfers, and Out-of-Order Waiting List Offers
- **Location:** `apps/toefl_house/toefl_house/teaching/transfers.py:250-265, 319-320, 344-348, 391-407` and `apps/toefl_house/toefl_house/teaching/capacity.py:486-515`
- **Description:**
  1. `request_class_transfer` and `approve_class_transfer` lock `source_group` then `target_group` in caller order (`_locked_group(source)` then `_locked_group(target)`) rather than `sorted((source, target))` (unlike `move_class_member` in `teaching/__init__.py:725`), creating an AB-BA database deadlock when opposite transfers run concurrently.
  2. `_transfer_row` (`transfers.py:250-258`) reads `TH Class Transfer` via `frappe.get_doc` without `for_update=True`, and `request_class_transfer` does not check for an existing `"Requested"` transfer for the same student/enrollment.
  3. `offer_waiting_list_seat` (`capacity.py:486-515`) allows offering a seat to any `Waiting` row regardless of `priority` order, without checking `Student.enabled == 1` or whether the student is already active on the group's roster.
- **Required Fix:** Lock groups in `sorted((source, target))` order, lock `TH Class Transfer` with `FOR UPDATE`, refuse duplicate `"Requested"` transfers for the same student, and enforce FIFO priority and active-student checks in `offer_waiting_list_seat`.

---

### 3.6 PR #46 — Windows Graphical Update Engine (`e8145954cdc081e84cc8aa2356e152c5ceda415d`, Mission 1)

#### `[PR46-01]` (High) — Forged / Unpersisted `transaction` Token in `apply_update` Bypasses Channel-Disable and Downgrade/Compatibility Guards
- **Location:** `product/update_engine.py:1437-1452, 1821-1895, 1986-2055`
- **Description:** `_issue_transaction()` returns a plain unsigned Python dict (`{"transaction_id": ..., "payload_digest": sha256(...)}`) without persisting it to disk or signing it with a host secret. When `apply_update()` runs, it calls `_rebind_apply()` and `_consume_transaction()`, **neither of which calls `load_channel_config()` or `evaluate_compatibility()`**. A local caller invoking `apply_update()` directly can compute `payload_digest = sha256(canonical_json(claims))` and supply a synthetic `transaction` dict to bypass a disabled update channel or a blocked downgrade/compatibility check. In addition, `_consume_transaction()` writes its replay marker into the caller-supplied per-run `state_dir`.
- **Required Fix:** Re-run `load_channel_config()` and `evaluate_compatibility()` unconditionally inside `apply_update()` / `_rebind_apply()`, and persist transaction issuance/consumption in a fixed host-protected state directory under `product/data`.

#### `[PR46-02]` (Medium) — `_rebind_apply` Crashes with `KeyError: 'backup_dir'` When `backup_dir` Is Omitted and Rejects `migration: "none"` Updates
- **Location:** `product/update_engine.py:1831-1839, 2013-2035`
- **Description:** `apply_update` declares `backup_dir: Path | None = None` as optional for `migration: "none"` updates. However, `_rebind_apply` unconditionally accesses `Path(rebound["backup_dir"])` (`KeyError` when `backup_dir is None`) and rejects `backup_evidence is None` or `recovery_evidence is None` with `apply.evidence_mismatch` regardless of whether `migration == "none"`.
- **Required Fix:** Gate backup/recovery evidence rebinding in `_rebind_apply` on the manifest's `migration` requirement or require `backup_dir` across all update paths consistently.

#### `[PR46-03]` (Medium) — `Update TOEFL House ERP.ps1 -Action Check` Requires a Backup Receipt Up Front and Double-Downloads the Full Image Archive
- **Location:** `product/windows/Update TOEFL House ERP.ps1:707-758, 1126-1137`
- **Description:** Running `-Action Check` (triggered by the "Check for Updates" button) requires a fresh backup receipt before checking if an update exists, downloads the multi-hundred-MB `image_archive` into a temp directory (`New-UpdateTempDirectory`) without cleaning it up in `finally`, and `-Action Install` creates a second temp directory and downloads the entire image archive a second time.
- **Required Fix:** Reuse the verified staged download between `Check` and `Install` (or clean up the temp directory in `finally` and defer full image download until `Install`).

---

### 3.7 Unmerged Branch `arena/e281e864-tofel-house-erp` — Role Desks & Executive Analytics (`4a9178061981c266768b3d6afe669244e631b76d`, Mission 6)

#### `[M6-01]` (High / CI Failure) — `th_role_desks.js` Crashes on Load with `TypeError: secondary.removeClass is not a function` and Ruff Fails with 4 Errors
- **Location:** `apps/toefl_house/toefl_house/public/js/th_role_desks.js:527`, `apps/toefl_house/toefl_house/desk/__init__.py:321`, and `apps/toefl_house/toefl_house/desk/analytics.py:231, 427, 430`
- **Description:**
  1. Running `node tests/foundation/test_role_desks.cjs` crashes immediately at `th_role_desks.js:527`: `secondary.removeClass("btn-primary").addClass("btn-secondary")` because the DOM wrapper in the desk client does not implement `.removeClass()`.
  2. Running `ruff check` fails with 4 errors, including `F601 Dictionary key literal ("finance", "Program Enrollment") repeated` in `desk/__init__.py:321`.
- **Required Fix:** Replace `.removeClass("btn-primary")` with supported class manipulation (`attr("class", ...)` or native `classList`) and fix all 4 Ruff errors.

#### `[M6-02]` (High) — `book_stock_metrics` and `payroll_metrics` Always Fail to `0`, `Course Owner` Granted Payroll Access, Invalid `drill_path` Routes, and Swallowed Schema Assertions
- **Location:** `apps/toefl_house/toefl_house/desk/__init__.py:220-335`, `apps/toefl_house/toefl_house/desk/analytics.py:33-45, 295-355`, `apps/toefl_house/toefl_house/desk/owner.py:80-89, 303`, and `apps/toefl_house/toefl_house/public/js/th_role_desks.js:283`
- **Description:**
  1. `analytics.book_stock_metrics()` and `analytics.payroll_metrics(authorized=True)` call `_project_rows("management", "Item", ...)`, `_project_rows("management", "Bin", ...)`, `_project_rows("management", "Additional Salary", ...)`, and `_project_rows("management", "Salary Slip", ...)`, none of which exist in `PROJECTION_FIELDS` (`desk/__init__.py`). Every call raises `ValidationError("No projection allow-list...")` inside `try/except` and returns `0`!
  2. `owner.py:303` sets `payroll_authorized = bool(set(roles) & {"Finance Manager", "General Manager", "Course Owner"})`, violating `analytics.py:334` and D12 payroll containment (`Course Owner` is not a payroll reader).
  3. `analytics.py` and `owner.py` populate `drill` / `drill_path` with English prose strings (`"tuition fees list"`, `"enrollment list"`, `"student list"`, `"warehouse stock list"`), which `th_role_desks.js:283` passes directly to `frappe.set_route(fact.drill_path)`, breaking navigation.
  4. `owner.py:88`, `academic.py:316`, `finance.py:701`, and `operations.py:537` wrap `analytics.*` calls in `try: ... except Exception: pass`, silently swallowing `AssertionError` raised by `test_desk_contract.py`'s schema-strict `assert_columns_real` guard when `analytics.py` queries unpinned doctypes (`Student Attendance`, `TH Enrollment Exit`).
- **Required Fix:** Add `analytics` to `DESK_MODULES` in `test_desk_contract.py`, remove broad `except Exception:` wrappers that hide schema-strict test failures, remove `"Course Owner"` from `payroll_authorized`, use valid Frappe routes (`["List", "Fees"]`, etc.), and respect D7/D12 projection rules.

---

## 4. Dependency Security & Vulnerability Triage Audit (Requirement 4)

We audited `docs/engineering/foundation-version-matrix.json`, `tools/foundation/advisory_triage.py`, `tools/foundation/audit_stack.py`, `tools/foundation/audit_frontend.py`, `docs/engineering/evidence/sec-deps-01/per-finding-remediation-analysis-2026-09-23.json`, all 11 additive delta registers (`advisory-delta-2026-09-29` through `advisory-delta-2026-10-24`), and `docs/owner-decisions.json`:

1. **Recent Remediations Verified on `main` (`c22b9979542c88a2cd179e179a91829d07a79a3a`):**
   - **PR #39 (`f83d13f`):** `filelock==3.20.3` is installed with `--no-deps` into both isolated Frappe virtualenvs in `product/app.Dockerfile` and `tools/foundation/runtime_install.py`, remediating the `filelock` TOCTOU advisory.
   - **PR #42 (`9ff2b1f`) / `advisory-delta-2026-10-24`:** `py:setuptools@80.9.0` (`GHSA-xmj3-9gf7-h52w`) is dispositioned as `NOT_REACHABLE` with bounded evidence proving that `setuptools.wheel.Wheel.install_as_egg()` is a Windows-native path escape, whereas the TOEFL House Python runtime is containerized on `python:3.11-slim-bookworm` (`linux/amd64`) and the Windows host allowlist contains zero Python/wheel execution paths (`tests/security/test_setuptools_windows_boundary_2026_10_24.py`).
   - **PR #43 (`c638664`):** HRMS frontend Yarn resolutions uplift `fast-uri` to `3.1.9`, `serialize-javascript` to `7.1.3`, and `undici` to `6.29.1`, verified by `tests/security/test_npm_advisory_pins_2026_10_24.py`.
2. **Triage Loader Controls Verified:**
   - `BROWSER_SELF_DENIAL` remains in `OWNER_OPEN_DISPOSITIONS` and is **excluded** from `CLOSED_DISPOSITIONS` (`OD-2026-10-18-A`).
   - `OWNER_ACCEPTED_RISKS` (`showdown` `GHSA-rmmh-p597-ppvv` under `OD-2026-10-20-A`, capped at 2,000 chars by `secure_markdown.py`; `@tiptap/core` `GHSA-cp6q-959q-f8rh` under `OD-2026-10-19-B`) require an explicit `ACCEPT` decision in `docs/owner-decisions.json` and report as `OWNER_ACCEPTED_RISK` (never falsely marked fixed/closed).
   - `disposition_for_finding` scopes lookups by normalized package name (`by_package`), preventing an advisory disposition on one package from closing the same GHSA/CVE on a different package.
   - Additive deltas (`advisory-delta-*/delta-dispositions.json`) fail closed with `SystemExit` on any duplicate/redefined advisory ID.

---

## 5. Verification Evidence Boundary Matrix

| Verification Tier | What Was Executed & Verified | What It Does **NOT** Prove |
|---|---|---|
| **1. Source-Code & Local Runtime/Adversarial Verification (`arena/aef07999-tofel-house-erp`)** | Full line-by-line audit of `main`, PRs #46, #48, #49, #50, #51, #52, and branch `arena/e281e864-tofel-house-erp`; Ruff `0.16.8` (`0` errors on `main`); Python suite (`1,719` tests passing, `9` Windows-only skips); 4 Node suites (`test_realtime_guard.cjs`, `test_command_pages.cjs`, `test_design_system.cjs`, `test_role_desks.cjs` all passing); new `tests/security/test_adversarial_qa_2026_10_24.py` (`18` tests). | Does not replace a live MariaDB/Redis/Frappe site or physical Windows host qualification. |
| **2. Disposable Hosted Linux Integration (`native.yml`, `foundation-runtime.yml`, `product-image.yml`)** | Verified exact-SHA runs on `main` (`c22b997`): Owned `40087474249` (PASS), Native `40087484777` (PASS, 638+ native checks across MariaDB/Redis/Frappe), Foundation Runtime `40087486356` (PASS), Product Image `40087474300` (PASS). Verified CI failures on PR #48 (`40091218467` Owned FAIL) and PR #51 (`40092388242` Native FAIL). | Disposable Linux CI containers use synthetic fixtures and do not prove real institutional policy, real payroll statutory accuracy, or physical Windows machine operation. |
| **3. Simulated / Hosted Windows Packaging Checks (`windows-customer-package.yml`)** | Verified exact-SHA run `40087487984` (PASS on `main`) and `40092808302` (PASS on PR #52 `632be0c`): PowerShell syntax/contract checks, GUI `-SmokeTest`, and customer ZIP/manifest assembly. | Hosted Windows Server runner without Docker Desktop/WSL2 runtime does not prove real customer Windows 11/10 Pro installation, USB backup drive rotation, or power-loss recovery. |
| **4. Real Customer Hardware & Operational Acceptance** | **NOT EXECUTED / BLOCKED** (`#12`, `#35`, `#36`, `#40`). | Requires physical Owner Windows PC, encrypted external backup drive, physical key custody, staff devices, and Owner-signed institutional configuration. |

---

## 6. Final QA Verdict

**FINAL RECOMMENDATION: `REJECT` FOR PRODUCTION RELEASE AND `REJECT` (CHANGES REQUIRED) FOR FEATURE PRs #46, #48, #49, #50, #51 AND BRANCH `arena/e281e864-tofel-house-erp`.**

1. **Do not merge PRs #46, #48, #49, #50, #51, or branch `arena/e281e864-tofel-house-erp`** until every Critical, High, and Medium defect documented in Section 3 is remediated by the responsible domain owner, covered by regression tests, and re-qualified on the new exact head SHA across all four canonical CI workflows.
2. **Remediate `main` findings `[MAIN-01]` through `[MAIN-04]`** (`teaching/__init__.py` active roster filter, `desk/__init__.py` scope filter intersection & `Sales Invoice` correction request branch chain, `administration.py` `Administrator` refusal, and `finance/corrections.py` + `teaching/attendance_corrections.py` maker-checker self-approval refusal).
3. **Maintain `production_authorization = REJECT`** until all physical hardware, recovery, cashier/stock, payroll, and Owner policy gates (`#12`, `#35`, `#36`, `#40`, `D1`–`D7`) are evidenced and approved.

---

## Integration update — 2026-10-24 (after the baseline audit)

The original report above is a historical snapshot of `main` at `c22b997`, not a current all-branches release decision. The integration lead merged PR #59 into `main` at `aa49db9717fa5d22c01b7d457121187a41947f10` to remediate the **baseline** inactive-roster check, branch filter intersection, protected-account role controls, and requester self-approval gaps. The four formerly exploit-presence assertions have been converted into positive regression contracts. The Sales Invoice branch-chain case still depends on a verified native relation and must be qualified on a live schema; do not claim broad correction-read parity without that evidence. The outstanding severity findings on #46/#48/#49/#50/#51/#58 remain until independently retested on their respective latest heads and integrated revision. No Owner Windows/production acceptance is implied.
