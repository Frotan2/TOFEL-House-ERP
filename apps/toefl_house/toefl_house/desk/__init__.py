"""Role desk projections: safe daily-work reads over the native authorities.

This package is the product layer described in docs/ROLE-DESKS.md.

Discipline (binding for every module in this package):

- A desk endpoint is a read. It never writes a document, never mutates
  configuration and never grants authority. Guided actions are prefills for
  EXISTING guarded commands, included only when the viewer already holds the
  acting role.
- Every endpoint gates on its declared desk audience before touching the
  database and fails closed with a human-readable message otherwise.
- Every query selects an explicit, per-desk allow-list of fields
  (PROJECTION_FIELDS) and carries an explicit limit. There is no `*` and no
  unbounded read anywhere in this package.
- Scope is native: company-scoped records are filtered through the viewer's
  User Permission on Company (and Branch where a record carries the field).
  The helper refuses to invent a scope the records do not have.
- Elevated reads exist only through _project_rows / _project_count, which
  require the caller to name the desk audience and are covered by the desk
  test suite.
"""
import frappe

DESK_MODULES = ("reception", "academic", "finance", "operations", "owner", "setup",
                "teacher", "configuration")

DESKS = {
    "th-reception-desk": {
        "title": "TOEFL House Reception Desk",
        "description": "Find any person in the admission funnel and see the stage, what is missing and who acts next.",
        "roles": ["Reception"],
        "module": "Operations",
    },
    "th-academic-desk": {
        "title": "TOEFL House Academic Desk",
        "description": "Placement and admission queues, classes, sessions and teaching assignments that need an academic decision.",
        "roles": ["Academic Manager"],
        "module": "Operations",
    },
    "th-finance-desk": {
        "title": "TOEFL House Finance Desk",
        "description": "Today's collections, outstanding receivables, enrollments awaiting billing, teaching assignments for native payroll, teaching contracts and compensation, and the correction queue.",
        "roles": ["Finance Manager"],
        "module": "Operations",
    },
    "th-operations-desk": {
        "title": "TOEFL House Operations Desk",
        "description": "Cross-role funnel, exceptions and staffing across the whole operation.",
        "roles": ["General Manager"],
        "module": "Operations",
    },
    "th-owner-cockpit": {
        "title": "TOEFL House Owner Cockpit",
        "description": "Business state with every definition stated, plus the fail-closed release posture.",
        "roles": ["Course Owner"],
        "module": "Operations",
    },
    "th-academic-setup": {
        "title": "TOEFL House Academic Setup",
        "description": "The Owner's configuration surface: programs, ordered levels, effective-dated durations and progression, feeding every other desk and command.",
        "roles": ["Course Owner"],
        "module": "Operations",
    },
    "th-teacher-desk": {
        "title": "TOEFL House Teacher Desk",
        "description": "My classes, today's sessions, attendance, students, academic work and compensation facts — assigned classes only, resolved through the native identity chain.",
        "roles": ["Instructor"],
        "module": "Operations",
    },
    "th-configuration": {
        "title": "TOEFL House Configuration",
        "description": "The configuration map: every configuration domain with its computed readiness, linking to each domain's own surface. Configuration readiness is shown here; production readiness is separate and is never decided here.",
        "roles": ["Course Owner"],
        "module": "Operations",
    },
}

# Fields each desk may project. This allow-list is the read boundary for the
# elevated projection reads: anything not listed here cannot leave the server
# through a desk, including sensitive internals (answers, hashes, seeds, keys,
# payroll detail, result_json). Tested by tests/desk.
PROJECTION_FIELDS = {
    ("finance", "TH Tuition Refund Request"): [
        "name", "student", "company", "fees", "requested_amount", "approved_amount",
        "reason", "evidence", "approval_evidence", "status", "requested_by",
        "approved_by", "paying_user", "credit_journal", "payment_entry", "modified", "voided_by", "void_reason", "voided_on",
    ],
    ("management", "TH Tuition Refund Request"): [
        "name", "student", "company", "fees", "requested_amount", "approved_amount",
        "reason", "evidence", "approval_evidence", "status", "requested_by",
        "approved_by", "paying_user", "credit_journal", "payment_entry", "modified", "voided_by", "void_reason", "voided_on",
    ],
    # Preliminary walk-in records are visible ONLY through this bounded,
    # role-gated, branch-filtered desk (no native DocType read grants).
    ("reception", "TH Reception Inquiry"): [
        "name", "person_name", "phone", "program_interest", "th_branch",
        "status", "notes", "recorded_by", "version", "creation",
    ],
    ("reception", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
        "course_code", "internal_level",
    ],
    ("reception", "TH Placement Attempt"): [
        "name", "case_name", "status",
    ],
    ("reception", "TH Placement Case"): [
        "name", "subject", "status", "th_branch", "reception_inquiry",
    ],
    ("reception", "Student"): [
        "name", "student_name", "student_email_id", "th_candidate_ref", "student_applicant", "enabled", "creation",
    ],
    # Cohort truth for the walk-in lookup: the class lifecycle lives on the
    # governed th_class_status custom field (planned/active classes open a
    # cohort; completed/cancelled ones do not). No `active` column exists on
    # the pinned native Student Group (education 93bc70757533).
    # Front-counter class lookup: class and timetable facts may only derive
    # from an in-scope Student, submitted Program Enrollment, and this
    # Student's own active native roster membership. A class merely existing
    # for the same program is NOT proof the learner belongs to that class.
    ("reception", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "academic_term", "th_branch", "disabled", "th_class_status",
    ],
    ("reception", "Student Group Student"): [
        "name", "parent", "student", "active",
    ],
    ("reception", "Course Schedule"): [
        "name", "student_group", "instructor", "course", "room",
        "from_time", "to_time", "schedule_date", "th_session_status",
    ],
    ("reception", "TH Teaching Assignment"): [
        "name", "student_group", "instructor", "course_schedule",
        "effective_start", "effective_end",
    ],
    ("reception", "Instructor"): [
        "name", "instructor_name", "status",
    ],
    ("reception", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "academic_term", "enrollment_date", "docstatus",
    ],
    ("reception", "Student Applicant"): [
        # `title` is the pinned native full-name column (education
        # 93bc70757533); Student Applicant has no `applicant_name` column.
        "name", "title", "student_email_id", "th_candidate_ref", "th_reception_inquiry", "program",
        "academic_year", "application_status", "creation",
    ],
    ("reception", "TH Admission Decision"): [
        "name", "student_applicant", "program", "academic_year",
        "placement_decision", "status", "accepted", "native_student",
        "version", "modified",
    ],
    ("academic", "TH Placement Attempt"): [
        "name", "case_name", "ordinal", "status", "version", "mode",
        "deadline_at",
    ],
    ("academic", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
        "course_code", "internal_level",
    ],
    ("academic", "TH Admission Decision"): [
        "name", "student_applicant", "program", "academic_year",
        "status", "accepted", "native_student", "version", "modified",
        "drafted_by",
    ],
    # The class lifecycle fact is the governed th_class_status custom field;
    # the pinned native Student Group (education 93bc70757533) has no
    # `active` column — `disabled` is its native archive flag.
    ("academic", "Student Group"): [
        "name", "student_group_name", "program", "academic_year", "academic_term",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    ("academic", "Student Group Student"): [
        "name", "parent", "student", "active",
    ],
    ("academic", "Course Schedule"): [
        "name", "student_group", "instructor", "course", "room",
        "from_time", "to_time", "schedule_date", "th_session_status",
    ],
    ("academic", "TH Teaching Assignment"): [
        "name", "student_group", "skill", "instructor", "contract",
        "course_schedule", "effective_start", "effective_end",
    ],
    ("academic", "Student Attendance"): [
        "name", "student", "student_group", "course_schedule", "date",
        "status", "docstatus",
    ],
    ("academic", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year", "academic_term",
        "enrollment_date", "docstatus",
    ],
    ("finance", "Fees"): [
        "name", "student", "student_name", "program", "program_enrollment",
        "academic_year", "posting_date", "due_date", "grand_total",
        "outstanding_amount", "currency", "company", "docstatus",
    ],
    ("finance", "Sales Invoice"): [
        "name", "customer", "customer_name", "th_placement_case",
        "posting_date", "due_date", "grand_total", "outstanding_amount",
        "currency", "company", "status", "is_return", "docstatus",
    ],
    # Payment Entry carries no flat `currency` column on the pinned
    # authority; the paying account's currency is the native fact.
    ("finance", "Payment Entry"): [
        "name", "payment_type", "party_type", "party", "paid_amount",
        "received_amount", "paid_from_account_currency", "company",
        "posting_date", "docstatus", "paid_to", "paid_to_account_currency",
        "th_reception_collector", "th_collection_fees", "th_collection_handover",
    ],
    ("finance", "TH Correction Request"): [
        "name", "sales_invoice", "fees", "correction_policy", "reason",
        "requested_amount", "status",
        "approved_by", "credit_note", "modified",
    ],
    ("finance", "TH Correction Policy"): [
        "name", "approver_role", "correction_window_days", "effective_from",
        "reason", "set_by", "set_on", "superseded_on", "status", "synthetic",
    ],
    # Validation evidence is matched by count, never projected: the hash
    # stays in the filter (read-boundary discipline, same as the
    # configuration desk).
    ("finance", "TH Placement Audit Event"): [
        "name",
    ],
    ("finance", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    # §18 consumption: the finance desk resolves the Owner's configured fee
    # plan (control plane) into the issuance prefill — one source of truth.
    ("finance", "Fee Structure"): [
        "name", "program", "academic_year", "company", "docstatus",
    ],
    ("finance", "Fee Component"): [
        "name", "parent", "parenttype", "fees_category", "amount", "idx",
    ],
    # D12 visibility: assignment identity and window only. No rate, no
    # payable amount, no Additional Salary — native payroll stays the
    # money authority. A count of rows is a record count, not a payroll figure.
    ("finance", "TH Teaching Assignment"): [
        "name", "student_group", "skill", "instructor", "contract",
        "course_schedule", "effective_start", "effective_end",
    ],
    # Compensation readiness (P1-6): identity + window only. No rate, term
    # or amount is projected — the desk points at the guarded command, it
    # never calculates pay (D12).
    ("finance", "TH Instructor Contract"): [
        "name", "instructor", "employee", "compensation_model",
        "effective_start", "effective_end",
    ],
    ("finance", "Instructor"): [
        "name", "instructor_name", "employee", "status",
    ],
    # Cashier day closes: the control record the finance desk summarises.
    # Counted cash, the ledger-derived expectation and the variance are the
    # record's own facts; nothing ledger-shaped is projected here.
    ("finance", "TH Cashier Day"): [
        "name", "date", "company", "cashier", "total_expected",
        "total_counted", "total_variance", "reconciled_on", "docstatus",
    ],
    # Owner cockpit counts enabled Students; the projection carries the key
    # only — no student detail leaves the store through the cockpit.
    ("management", "Student"): [
        "name",
    ],
    ("management", "TH Correction Request"): [
        "name", "sales_invoice", "fees", "reason", "requested_amount", "status",
        "modified",
    ],
    ("management", "TH Admission Decision"): [
        "name", "student_applicant", "program", "status", "version",
        "accepted", "native_student", "modified",
    ],
    ("management", "TH Placement Attempt"): [
        "name", "case_name", "status", "deadline_at",
    ],
    ("management", "TH Placement Decision"): [
        "name", "attempt", "status", "released_at", "expires_at",
    ],
    ("management", "Program Enrollment"): [
        "name", "student", "student_name", "program", "academic_year",
        "enrollment_date", "docstatus",
    ],
    ("management", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    # Staffing coverage reads the native role assignment rows and the enabled
    # flag of the native User; nothing else about a user is projected.
    ("management", "Has Role"): [
        "name", "parent", "role", "parenttype",
    ],
    ("management", "User"): [
        "name",
    ],
    # Existing command receipts, facts only. Hashes, keys and result_json
    # stay off the desk; auditors still read the full trail on TH Receipts.
    ("management", "TH Placement Audit Event"): [
        "name", "actor", "action", "target", "item_revision", "creation",
    ],
    # Operational visibility (native Frappe authorities, pinned 988e54f3c4c2).
    # Row identity + native state only: the Error Log text, job tracebacks
    # (exc_info) and worker internals stay on the native forms. RQ
    # Worker.status is free text with no native vocabulary, so it is echoed
    # verbatim and never interpreted into an alert condition.
    ("management", "Error Log"): [
        "name", "method", "seen", "creation",
    ],
    # RQ Job is VIRTUAL on the pinned version and its controller gates
    # every read on has_permission("RQ Job"), ignoring ignore_permissions;
    # desk audiences read the same registry facts through the fallback in
    # operations._rq_failed_jobs, still confined to these fields.
    ("management", "RQ Job"): [
        "name", "job_name", "queue", "status", "started_at", "ended_at",
    ],
    ("management", "RQ Worker"): [
        "name", "worker_name", "queue", "queue_type", "status",
        "failed_job_count", "successful_job_count", "last_heartbeat",
    ],
    ("management", "Scheduled Job Type"): [
        "name", "method", "frequency", "stopped", "last_execution",
    ],
    ("management", "Scheduled Job Log"): [
        "name", "scheduled_job_type", "status", "creation",
    ],
    # Executive analytics (Mission 6): auditable metrics grounded in native
    # records. Each projection is bounded, permission-scoped and carries an
    # explicit definition + drill path on the desk. Payroll is authorization-
    # gated (see desk/analytics.py) — no payroll figure leaves the server
    # unless the viewer holds the payroll role.
    ("management", "Fees"): [
        "name", "student", "student_name", "program", "program_enrollment",
        "academic_year", "posting_date", "due_date", "grand_total",
        "outstanding_amount", "currency", "company", "docstatus",
    ],
    ("management", "Sales Invoice"): [
        "name", "customer", "customer_name", "th_placement_case",
        "posting_date", "due_date", "grand_total", "outstanding_amount",
        "currency", "company", "status", "is_return", "docstatus",
    ],
    ("management", "Payment Entry"): [
        "name", "payment_type", "party_type", "party", "paid_amount",
        "received_amount", "paid_from_account_currency",
        "paid_to_account_currency", "company", "posting_date", "docstatus",
    ],
    ("management", "Student Attendance"): [
        "name", "student", "student_group", "course_schedule", "date",
        "status", "docstatus",
    ],
    ("management", "Course Schedule"): [
        "name", "student_group", "instructor", "course", "room",
        "from_time", "to_time", "schedule_date",
    ],
    ("management", "TH Enrollment Exit"): [
        "name", "program_enrollment", "student", "exit_kind", "exit_date",
        "reason", "status", "creation",
    ],
    ("finance", "Student Attendance"): [
        "name", "student", "student_group", "course_schedule", "date",
        "status", "docstatus",
    ],
    ("finance", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    ("reception", "Fees"): [
        "name", "student", "program", "due_date", "grand_total",
        "outstanding_amount", "currency", "company", "docstatus",
    ],
    ("reception", "Payment Entry"): [
        "name", "party", "received_amount", "paid_to", "paid_to_account_currency",
        "company", "posting_date", "docstatus", "th_reception_collector",
        "th_collection_fees", "th_collection_handover",
    ],
    ("reception", "Sales Invoice"): [
        "name", "customer", "grand_total", "outstanding_amount",
        "currency", "status", "docstatus",
    ],
    # Academic Setup (Course Owner): configuration masters, their effective-
    # dated duration versions, and the enrollment usage counts that guard
    # deactivation. No student detail beyond the enrollment link.
    ("setup", "TH Academic Program"): [
        "name", "code", "title", "status", "modified",
    ],
    ("setup", "TH Program Level"): [
        "name", "family", "code", "title", "sequence", "status",
        "native_program", "next_level", "modified",
    ],
    ("setup", "TH Level Duration"): [
        "name", "parent", "parenttype", "duration_value", "duration_unit",
        "effective_from", "superseded_on", "reason", "set_by",
    ],
    ("setup", "TH Discount Rule"): [
        "name", "code", "title", "discount_percentage", "precedence",
        "status", "fee_category", "program", "student", "description", "modified",
        "modified_by",
    ],
    # D1 configuration plane: assessment policies, their effective-dated
    # versions with the owned facet structures, and the validation audit
    # events behind computed readiness. Facets stay empty until the Course
    # Owner defines them through the guarded facet commands.
    ("setup", "TH Assessment Policy"): [
        "name", "family", "code", "title", "status", "description",
        "modified",
    ],
    ("setup", "TH Assessment Policy Version"): [
        "name", "parent", "parenttype", "effective_from", "grading_scale",
        "components", "weights", "pass_rules", "rubrics", "progression",
        "retakes", "level_mapping", "reason", "set_by", "set_on",
        "superseded_on",
    ],
    # Validation evidence is matched by count, never projected: desks ask
    # "does a validation event commit to this snapshot" via project_count,
    # so hashes never enter a projection (read-boundary discipline).
    ("setup", "TH Configuration Audit Event"): [
        "name",
    ],
    ("setup", "Program Enrollment"): [
        "name", "program", "enrollment_date", "docstatus",
    ],
    # Integrity audit: native Program identity/display only, to surface
    # records defined outside the control plane.
    ("setup", "Program"): [
        "name", "program_name",
    ],
    # Fee configuration (control plane slice 2): native fee masters and the
    # editable plans per level. No GL detail beyond the resolved receivable.
    ("setup", "Academic Year"): [
        "name", "year_start_date", "year_end_date",
    ],
    ("setup", "Fee Category"): [
        "name", "category_name", "description", "item",
    ],
    ("setup", "Fee Structure"): [
        "name", "program", "academic_year", "company", "receivable_account",
        "docstatus", "total_amount",
    ],
    ("setup", "Fee Component"): [
        "name", "parent", "parenttype", "fees_category", "amount", "idx",
    ],
    # Configuration map (Course Owner): the same D1 reference reads, for the
    # computed configuration-readiness rollup. No other domain has any
    # configuration records in Phase 1.
    ("configuration", "TH Owner Operations Policy"): [
        "name", "code", "title", "status", "description", "modified",
    ],
    # Native Course Owner policy masters are projected here only as a
    # configuration index; their guarded commands remain the write authority.
    ("configuration", "TH Catalog Linkage Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Returning Student Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Enrollment Exit Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Billing Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Roster Change Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Attendance Correction Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Adjustment Posting Policy"): ["name", "code", "title", "status", "description", "modified"],
    ("configuration", "TH Assessment Policy"): [
        "name", "family", "code", "title", "status", "description",
        "modified",
    ],
    ("configuration", "TH Assessment Policy Version"): [
        "name", "parent", "parenttype", "effective_from", "grading_scale",
        "components", "weights", "pass_rules", "rubrics", "progression",
        "retakes", "level_mapping", "reason", "set_by", "set_on",
        "superseded_on",
    ],
    ("configuration", "TH Configuration Audit Event"): [
        "name",
    ],
    # Alerting/receiver policy (track 2): same projection discipline — the
    # owner-provided receiver_reference destination stays on the document;
    # the desk names the channel kind, the ownership terms and the dates.
    ("configuration", "TH Alerting Policy"): [
        "name", "code", "title", "status", "description", "modified",
    ],
    ("configuration", "TH Alerting Policy Version"): [
        "name", "parent", "parenttype", "effective_from", "channel_kind",
        "escalate_after_minutes", "retention_days", "reason", "set_by",
        "set_on", "superseded_on",
    ],
    # Guardian lifecycle policy (track 4): policy enumerations and the
    # window/expiry numbers are projected; the owner-authored records/
    # recording rights text stays document-only (projection discipline).
    ("configuration", "TH Guardian Lifecycle Policy"): [
        "name", "code", "title", "status", "description", "modified",
    ],

    # Notification dispatch (Mission 5): each event type's recipients,
    # severity, timing, channel, retries, escalation, enabled — all
    # owner-configurable, no defaults invented.
    ("configuration", "TH Notification Dispatch Rule"): [
        "name", "event_type", "enabled", "severity", "channel",
        "timing_delay_minutes", "max_retries", "retry_delay_minutes",
        "escalate_after_minutes",
    ],
    ("configuration", "TH Portal Configuration"): [
        "name", "code", "title", "status", "student_portal_enabled",
        "guardian_portal_enabled", "dashboard_enabled", "email_enabled",
        "sms_enabled", "whatsapp_enabled", "modified",
    ],
    ("configuration", "TH Guardian Consent"): [
        "name", "guardian", "student", "consent_date", "expiry_date",
        "evidence_type", "status", "revoked_at", "revoked_by",
    ],
    ("configuration", "TH Portal Announcement"): [
        "name", "title", "audience", "status", "publish_date", "message",
    ],
    # Notification ledger — readable by managers, not deletable by anyone.
    ("configuration", "TH Notification"): [
        "name", "event_type", "title", "severity", "channel", "status",
        "related_doctype", "related_name", "retry_count", "max_retries",
        "created_at", "delivered_at", "acknowledged_at",
    ],
    ("configuration", "TH Guardian Lifecycle Policy Version"): [
        "name", "parent", "parenttype", "effective_from",
        "delegation_window_days", "pre_admission_proxy",
        "consent_evidence", "consent_expiry_days", "reason", "set_by",
        "set_on", "superseded_on",
    ],
    # Teacher desk (Instructor): the teacher's own classes only, resolved
    # through session User -> Employee.user_id -> Instructor.employee ->
    # TH Teaching Assignment. Identity + window + recorded facts only: no
    # rates, no payable amounts, no payroll rows (ROLE-DESKS). Assessment
    # rows are recorded facts (score/max/grade as recorded); grading policy
    # itself stays the owner decision D1 and is not projected.
    ("teacher", "Employee"): [
        "name", "employee_name", "status", "user_id",
    ],
    ("teacher", "Instructor"): [
        "name", "instructor_name", "employee", "status",
    ],
    ("teacher", "TH Teaching Assignment"): [
        "name", "student_group", "skill", "instructor", "contract",
        "course_schedule", "effective_start", "effective_end",
    ],
    ("teacher", "TH Skill"): [
        "name", "code", "title", "status",
    ],
    ("teacher", "Student Group"): [
        "name", "student_group_name", "program", "academic_year",
        "max_strength", "course", "disabled", "th_class_status",
    ],
    ("teacher", "Course Schedule"): [
        "name", "student_group", "instructor", "course", "room",
        "from_time", "to_time", "schedule_date", "th_session_status",
    ],
    ("teacher", "Student Group Student"): [
        "name", "parent", "student", "student_name", "group_roll_number",
        "active",
    ],
    ("teacher", "Student Attendance"): [
        "name", "student", "student_group", "course_schedule", "date",
        "status", "docstatus",
    ],
    ("teacher", "Assessment Result"): [
        "name", "student", "student_name", "student_group", "course",
        "total_score", "maximum_score", "grade", "docstatus",
    ],
    ("teacher", "TH Instructor Contract"): [
        "name", "instructor", "employee", "compensation_model",
        "assignment_basis", "payment_frequency", "effective_start",
        "effective_end", "status",
    ],
}

# Hard upper bounds. A desk section never silently grows with the data.
LIMIT_QUEUES = 25
LIMIT_TODAY = 25
LIMIT_LOOKUP = 10
BOUNCE_WINDOW = 400


def require_desk_audience(slug):
    """Gate: the viewer must hold at least one of the desk's roles.

    Desks are separately authorized aggregate views (the sanctioned concept in
    docs/ROLE-DESKS.md): read-only, minimal-field, role-gated. A
    desk read is therefore gated on the desk audience and on an enabled,
    non-guest, non-administrator user — the same viewer invariants
    toefl_house.security.authorize enforces for commands — but deliberately
    NOT on the site activation gate, exactly like the governance
    surface in toefl_house.administration. The operational hard stop in
    security.py continues to confine every business command to the synthetic
    qualification sites and the D16-activated production site; a desk cannot
    mutate anything and adds no path around it.
    """
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if user in (None, "Guest", "Administrator") or not roles.intersection(DESKS[slug]["roles"]):
        frappe.throw(
            f"The {DESKS[slug]['title']} is limited to the "
            f"{DESKS[slug]['roles'][0]} role. Ask a Course Owner or General "
            "Manager to review your role assignment if you expected access.",
            frappe.PermissionError,
        )
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw("This account has been disabled.", frappe.PermissionError)
    if slug == "th-reception-desk" and not frappe.db.get_value(
            "User Permission", {"user": user, "allow": "Branch"}, "for_value"):
        frappe.throw(
            "Reception needs an assigned Branch before customer records can be viewed. "
            "Ask the Course Owner to assign your branch.", frappe.PermissionError)
    return user


def viewer_roles():
    return set(frappe.get_roles(frappe.session.user))


def scope_filters(desk):
    """Native scope: the viewer's User Permission on Company/Branch, applied
    only to fields the projected doctypes really carry. Returns a dict of
    {fieldname: allowed_values} that callers merge into their filters.
    Branch matches the native `branch` field where present and this app's
    `th_branch` field (Student Group, Student Applicant) otherwise."""
    scopes = {}
    for allow, fieldnames in (("Company", ("company",)), ("Branch", ("branch", "th_branch"))):
        allowed = frappe.get_all(
            "User Permission",
            filters={"user": frappe.session.user, "allow": allow},
            pluck="for_value",
            limit_page_length=100,
        )
        if allowed:
            for fieldname in fieldnames:
                scopes[fieldname] = allowed
    return scopes


# Projected doctypes whose branch fact is not a direct field, resolved
# through records the product already maintains: the class roster
# (Student Group Student, active rows), the class branch
# (Student Group.th_branch) and the applicant branch
# (Student Applicant.th_branch). Each doctype's allowed document names are
# resolved through the same sanctioned get_all seam every desk read uses
# (no raw SQL), and the filter is applied on `name`, so an empty result set
# matches nothing (fail closed). Doctypes without an entry (placement
# content, configuration, system records, identity) are intentionally
# branch-wide.
BRANCH_CHAIN_FILTERS = ("TH Reception Inquiry", "Student", "Student Group Student", "Student Attendance",
                        "Course Schedule", "Program Enrollment", "Fees",
                        "TH Enrollment Exit", "TH Teaching Assignment",
                        "TH Correction Request", "TH Admission Decision")
_CHAIN_LIMIT = 10000  # bounded scope resolution; truncation is fail-closed


def _branch_allowed_names(doctype, branches, *, require_complete=False):
    """Document names a branch-scoped viewer may see, resolved through the
    class -> branch and roster -> student chains."""
    # Enrollment queues make numeric/roster claims. A truncated scope chain
    # must report an error, not masquerade as an exact empty intake.
    strict = require_complete or doctype in ("Program Enrollment", "Student")

    def checked(rows):
        if strict and len(rows) >= _CHAIN_LIMIT:
            raise frappe.ValidationError(
                "Branch enrollment scope exceeds the safe read limit; narrow the scope or contact an administrator")
        return rows

    if doctype == "TH Reception Inquiry":
        rows = frappe.get_all(
            doctype, filters={"th_branch": ("in", branches)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)
        if len(rows) >= _CHAIN_LIMIT:
            raise frappe.ValidationError("Reception inquiry branch scope exceeds the safe read limit")
        return [row["name"] for row in rows]

    groups = [row["name"] for row in checked(frappe.get_all(
        "Student Group", filters={"th_branch": ("in", branches)},
        fields=["name"], limit_page_length=_CHAIN_LIMIT))]
    if doctype == "Student Group Student":
        if not groups:
            return []
        return [row["name"] for row in frappe.get_all(
            doctype, filters={"parent": ("in", groups), "active": 1},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)]
    if doctype in ("Student Attendance", "Course Schedule", "TH Teaching Assignment"):
        if not groups:
            return []
        return [row["name"] for row in frappe.get_all(
            doctype, filters={"student_group": ("in", groups)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)]
    roster = [row["student"] for row in checked(frappe.get_all(
        "Student Group Student", filters={"parent": ("in", groups), "active": 1},
        fields=["student"], limit_page_length=_CHAIN_LIMIT))] if groups else []
    if doctype == "Student":
        # A converted learner exists BEFORE first Program Enrollment or
        # Student Group roster assignment. For Reception, that is the exact
        # moment a Student lookup must work. Admit an unrostered Student only
        # through a branch-visible converted Admission and their exact native
        # Applicant link; a matching email, name or household phone proves
        # nothing. A student rostered in a foreign/branchless group must
        # never leak through a historical admission in another branch.
        admissible = _branch_allowed_names(
            "TH Admission Decision", branches, require_complete=True)
        intake_rows = checked(frappe.get_all(
            "TH Admission Decision",
            filters={"name": ("in", admissible)},
            fields=["name", "student_applicant", "native_student"],
            limit_page_length=_CHAIN_LIMIT)) if admissible else []
        verified = {(row.get("native_student"), row.get("student_applicant"))
                    for row in intake_rows
                    if row.get("native_student") and row.get("student_applicant")}
        candidates = sorted(set(roster) | {pair[0] for pair in verified})
        if not candidates:
            return []
        students = checked(frappe.get_all(
            "Student", filters={"name": ("in", candidates)},
            fields=["name", "student_applicant"], limit_page_length=_CHAIN_LIMIT))
        all_memberships = checked(frappe.get_all(
            "Student Group Student",
            filters={"student": ("in", candidates), "active": 1},
            fields=["student", "parent"], limit_page_length=_CHAIN_LIMIT))
        parents = sorted({row.get("parent") for row in all_memberships if row.get("parent")})
        all_groups = checked(frappe.get_all(
            "Student Group", filters={"name": ("in", parents)},
            fields=["name", "th_branch"], limit_page_length=_CHAIN_LIMIT)) if parents else []
        by_parent = {group["name"]: group.get("th_branch") for group in all_groups}
        membership_branches = {}
        for row in all_memberships:
            membership_branches.setdefault(row["student"], set()).add(
                by_parent.get(row.get("parent")))
        allowed = set(branches)
        result = []
        for student in students:
            name = student["name"]
            memberships = membership_branches.get(name, set())
            if memberships and (not memberships <= allowed):
                continue
            if ((name in roster and memberships) or
                    (name, student.get("student_applicant")) in verified):
                result.append(name)
        return sorted(result)
    if doctype == "Program Enrollment":
        # A new/late learner may have a submitted enrollment before any class
        # roster exists. Authorize that intake only through an already
        # branch-checked admission for the *same* student, program, year and
        # term. A student's old applicant branch cannot authorize a different
        # intake or a student now rostered in a foreign branch.
        # Finding one in-scope roster is insufficient when the same learner
        # also has an active foreign or branchless roster. Re-read *all*
        # memberships before using roster-based enrollment evidence.
        all_roster = checked(frappe.get_all(
            "Student Group Student", filters={"student": ("in", roster), "active": 1},
            fields=["student", "parent"], limit_page_length=_CHAIN_LIMIT)) if roster else []
        parents = sorted({r["parent"] for r in all_roster if r.get("parent")})
        parent_rows = checked(frappe.get_all(
            "Student Group", filters={"name": ("in", parents)},
            fields=["name", "th_branch"], limit_page_length=_CHAIN_LIMIT)) if parents else []
        parent_branch = {row["name"]: row.get("th_branch") for row in parent_rows}
        memberships = {}
        for row in all_roster:
            memberships.setdefault(row["student"], set()).add(parent_branch.get(row.get("parent")))
        confined = {student for student, facts in memberships.items()
                    if facts and facts <= set(branches)}
        names = {row["name"] for row in checked(frappe.get_all(
            doctype, filters={"student": ("in", sorted(confined))},
            fields=["name"], limit_page_length=_CHAIN_LIMIT))} if confined else set()
        admissions = _branch_allowed_names("TH Admission Decision", branches, require_complete=True)
        if admissions:
            rows = checked(frappe.get_all(
                "TH Admission Decision", filters={"name": ("in", admissions)},
                fields=["native_student", "program", "academic_year", "academic_term"],
                limit_page_length=_CHAIN_LIMIT))
            intakes = {(r.get("native_student"), r.get("program"), r.get("academic_year"),
                        r.get("academic_term") or "") for r in rows if r.get("native_student")}
            students = sorted({r[0] for r in intakes})
            candidates = checked(frappe.get_all(
                doctype, filters={"student": ("in", students)},
                fields=["name", "student", "program", "academic_year", "academic_term"],
                limit_page_length=_CHAIN_LIMIT)) if students else []
            names.update(r["name"] for r in candidates
                         if (r.get("student"), r.get("program"), r.get("academic_year"),
                             r.get("academic_term") or "") in intakes)
        return sorted(names)
    if doctype in ("Fees", "TH Enrollment Exit"):
        if not roster:
            return []
        return [row["name"] for row in frappe.get_all(
            doctype, filters={"student": ("in", roster)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)]
    if doctype == "TH Correction Request":
        if not roster:
            return []
        fee_names = [row["name"] for row in frappe.get_all(
            "Fees", filters={"student": ("in", roster)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)]
        # A correction may reference native Fees OR a native Sales Invoice.
        # The latter must also be traced back to branch-owned students.
        invoice_names = [row["name"] for row in frappe.get_all(
            "Sales Invoice", filters={"student": ("in", roster)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT)] if frappe.get_meta(
                "Sales Invoice").has_field("student") else []
        names = set()
        for link, allowed in (("fees", fee_names),
                              ("sales_invoice", invoice_names)):
            if allowed:
                names |= {row["name"] for row in frappe.get_all(
                    doctype, filters={link: ("in", allowed)},
                    fields=["name"], limit_page_length=_CHAIN_LIMIT)}
        return sorted(names)
    if doctype == "TH Admission Decision":
        applicants = [row["name"] for row in checked(frappe.get_all(
            "Student Applicant", filters={"th_branch": ("in", branches)},
            fields=["name"], limit_page_length=_CHAIN_LIMIT))]
        names = set()
        for field, values in (("student_applicant", applicants),
                              ("existing_student", roster),
                              ("native_student", roster)):
            if values:
                names |= {row["name"] for row in checked(frappe.get_all(
                    doctype, filters={field: ("in", values)},
                    fields=["name"], limit_page_length=_CHAIN_LIMIT))}
        if not names:
            return []
        candidate_rows = checked(frappe.get_all(
            doctype, filters={"name": ("in", sorted(names))},
            fields=["name", "student_applicant", "existing_student", "native_student"],
            limit_page_length=_CHAIN_LIMIT))
        # All linked student memberships matter, not merely the branch whose
        # roster caused this admission to appear in the candidate set.
        linked_students = sorted({
            row.get(field) for row in candidate_rows
            for field in ("existing_student", "native_student") if row.get(field)
        })
        roster_rows = checked(frappe.get_all(
            "Student Group Student",
            filters={"student": ("in", linked_students), "active": 1},
            fields=["student", "parent"], limit_page_length=_CHAIN_LIMIT
        )) if linked_students else []
        if len(roster_rows) >= _CHAIN_LIMIT:
            return []  # Truncation must never hide a foreign membership.
        parent_names = sorted({row["parent"] for row in roster_rows if row.get("parent")})
        parent_rows = checked(frappe.get_all(
            "Student Group", filters={"name": ("in", parent_names)},
            fields=["name", "th_branch"], limit_page_length=_CHAIN_LIMIT
        )) if parent_names else []
        if len(parent_rows) >= _CHAIN_LIMIT:
            return []
        parent_branch = {row["name"]: row.get("th_branch") for row in parent_rows}
        student_branches = {}
        for row in roster_rows:
            student_branches.setdefault(row["student"], set()).add(
                parent_branch.get(row.get("parent")))
        allowed_applicants = set(applicants)
        allowed_branches = set(branches)
        eligible = []
        for row in candidate_rows:
            applicant = row.get("student_applicant")
            if applicant and applicant not in allowed_applicants:
                continue
            related = set()
            for field in ("existing_student", "native_student"):
                student = row.get(field)
                if student:
                    related.update(student_branches.get(student, set()))
            if related - allowed_branches:
                continue
            # A valid intake branch can authorize a first enrollment before
            # any class exists, but no branch-less candidate is exposed.
            if applicant in allowed_applicants or related:
                eligible.append(row["name"])
        return sorted(eligible)
    return []


def _branch_name_filter(desk, doctype):
    """The ``(name, in, allowed_names)`` filter for branch-scoped viewers,
    or None when no branch filter applies: the doctype is branch-wide by
    design, or the viewer carries no Branch User Permission (HQ). A viewer
    scoped to no branch gets an empty set, which matches nothing."""
    if doctype not in BRANCH_CHAIN_FILTERS:
        return None
    rows = frappe.get_all(
        "User Permission",
        filters={"user": frappe.session.user, "allow": "Branch"},
        pluck="for_value",
        limit_page_length=100,
    )
    if not rows:
        return None
    seen, branches = set(), []
    for value in rows:
        if value and value not in seen:
            seen.add(value)
            branches.append(value)
    if not branches:
        return ("in", [])
    return ("in", _branch_allowed_names(doctype, branches))


def _intersect_scope_filter(existing, permitted):
    """Never let a caller-supplied filter override a mandatory permission scope.

    Only equality and membership are acceptable for a scoped field. Reject
    other operators rather than silently broadening the query.
    """
    allowed = set(permitted)
    if isinstance(existing, (tuple, list)):
        if len(existing) != 2 or existing[0] not in ("in", "=", "=="):
            raise frappe.ValidationError("Unsupported filter on a scope-limited field")
        values = existing[1] if existing[0] == "in" else [existing[1]]
        if not isinstance(values, (list, tuple, set)):
            raise frappe.ValidationError("Scope membership requires a list")
    else:
        values = [existing]
    return ("in", [value for value in values if value in allowed])


def _apply_scope(desk, doctype, filters):
    for fieldname, allowed in scope_filters(desk).items():
        meta_field = fieldname if frappe.get_meta(doctype).has_field(fieldname) else None
        if meta_field:
            filters[meta_field] = (
                _intersect_scope_filter(filters[meta_field], allowed)
                if meta_field in filters else ("in", allowed))
    branch_filter = _branch_name_filter(desk, doctype)
    if branch_filter is not None:
        allowed = branch_filter[1]
        filters["name"] = (
            _intersect_scope_filter(filters["name"], allowed)
            if "name" in filters else branch_filter)
    return filters


def _assert_projection(desk, doctype, fields):
    allow = PROJECTION_FIELDS.get((desk, doctype))
    if not allow:
        raise frappe.ValidationError(f"No projection allow-list for {desk}/{doctype}")
    if [field for field in fields if field not in allow]:
        raise frappe.ValidationError(f"Fields outside the {desk}/{doctype} projection allow-list")
    return allow


def collection_schema_ready():
    """Hide cash actions until the supported field migration has completed."""
    check = getattr(frappe.db, "has_column", None)
    return callable(check) and check("Payment Entry", "th_collection_handover")


def refund_case_rows(desk, fields):
    """Normal native read/list authority, including the refund Branch chain.

    A refund has no flat Branch column. Never route these case/evidence reads
    through an elevated get_all projection that cannot enforce that chain.
    """
    slugs = {"finance": "th-finance-desk", "management": "th-operations-desk"}
    if desk not in slugs:
        raise frappe.PermissionError("Refund cases require the Finance or General Manager desk")
    require_desk_audience(slugs[desk])
    _assert_projection(desk, "TH Tuition Refund Request", fields)
    check = getattr(frappe.db, "has_column", None)
    if (not callable(check) or not check("TH Tuition Refund Request", "credit_journal")
            or not check("TH Tuition Refund Request", "voided_on")):
        return None
    rows = frappe.get_list("TH Tuition Refund Request", fields=list(fields),
                           order_by="modified desc, name desc", limit_page_length=LIMIT_QUEUES + 1)
    # Recheck the same command scope before exposing evidence or prefills.
    # A native list permission alone must never become action authority.
    from toefl_house.command_scope import authorize_command_scope
    visible = []
    for row in rows:
        try:
            authorize_command_scope("approve_tuition_refund", {"request": row["name"]}, frappe.session.user)
        except frappe.PermissionError:
            continue
        visible.append(row)
    return visible


def project_rows(desk, doctype, fields, filters=None, order_by=None, limit=LIMIT_QUEUES,
                 scope=True):
    """Elevated, allow-listed, bounded read for a desk projection.

    This is the only sanctioned way for a desk to read records its audience
    does not hold natively. It enforces the field allow-list and the limit
    before touching the database, so a caller cannot widen the projection.
    Native Company/Branch user-permission scope applies by default; pass
    scope=False only for self-filtered identity resolution (rows keyed to
    the viewer's own login, which no permission can unsee without unlinking
    the viewer). The field allow-list is never negotiable either way.
    """
    _assert_projection(desk, doctype, fields)
    filters = _apply_scope(desk, doctype, dict(filters or {})) if scope else dict(filters or {})
    return frappe.get_all(
        doctype,
        filters=filters,
        fields=list(fields),
        order_by=order_by or "modified desc",
        limit_page_length=int(limit),
    )


def project_count(desk, doctype, filters=None):
    _assert_projection(desk, doctype, ["name"])
    filters = _apply_scope(desk, doctype, dict(filters or {}))
    return frappe.db.count(doctype, filters)


def section(sid, title, kind, *, items=None, facts=None, empty_title="", empty_body="", notes=None, actions=None):
    """A desk section envelope. The client renders these uniformly."""
    payload = {"id": sid, "title": title, "kind": kind}
    if facts is not None:
        payload["facts"] = facts
    if items is not None:
        payload["items"] = items
    payload["empty"] = {"title": empty_title, "body": empty_body}
    if notes:
        payload["notes"] = notes
    if actions:
        payload["actions"] = actions
    return payload


def guided_action(role, endpoint, label, args):
    """Prefill for an existing guarded command, included only when the viewer
    holds the acting role. The server decides; the client only renders."""
    if role in viewer_roles():
        return {"role": role, "endpoint": endpoint, "label": label, "args": args}
    return None


# The class lifecycle is the governed th_class_status fact (planned → active
# → completed/cancelled, maintained by toefl_house.teaching.transition_class
# alone). A cohort is OPEN while a class is planned or active and not
# archived; completed and cancelled classes never satisfy the cohort
# requirement again. These sets are reads of that single authority — no
# parallel status is invented or maintained here.
COHORT_OPEN_STATUSES = ("Planned", "Active")
COHORT_ACTIVE_STATUSES = ("Active",)


def cohort_state(group_row):
    """Lifecycle state of one Student Group row from its governed facts."""
    if int(group_row.get("disabled") or 0):
        return "Archived"
    return group_row.get("th_class_status") or "Planned"


def open_cohort_keys(group_rows):
    """(program, academic_year) pairs whose class is planned or active."""
    return {(row.get("program"), row.get("academic_year"))
            for row in group_rows
            if cohort_state(row) in COHORT_OPEN_STATUSES}


def active_cohort_rows(group_rows):
    return [row for row in group_rows if cohort_state(row) in COHORT_ACTIVE_STATUSES]


# Fee-plan readiness is ONE rule everywhere: the guided billing text (finance
# desk), the Owner's configuration health (setup desk) and the issuance
# command must never disagree about what "configured" means. issue_tuition_fees
# consumes a structure by name and checks program/year match and components
# (U9): the desk rule mirrors exactly that, over cancelled-free plans. Editing
# stays a Draft-only act (toefl_house.academic manages Draft structures), so
# the setup desk offers edit buttons only where they can succeed.
def issuable_plans(plans_by_key, program, academic_year):
    """Plans for (program, year) that the issuance command would accept,
    split into those with components and empty drafts awaiting completion."""
    candidates = [plan for plan in plans_by_key.get((program, academic_year or ""), [])
                  if int(plan.get("docstatus") or 0) != 2]
    return candidates


def plan_with_components(candidates, rows_by_plan):
    return [plan for plan in candidates if rows_by_plan.get(plan["name"])]


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def available():
    """Registry read: which desks the SERVER believes this viewer may open.

    The client never guesses roles from its own session data; every desk and
    the command-centre landing page render their links from this answer.
    Guests get an explicit empty answer rather than an error, so a shared
    machine never sees a stack trace on the landing page.
    """
    user = frappe.session.user
    if user in (None, "Guest", "Administrator"):
        return {"desks": []}
    if not frappe.db.get_value("User", user, "enabled"):
        return {"desks": []}
    held = viewer_roles()
    return {"desks": [
        {"slug": slug, "title": spec["title"], "description": spec["description"]}
        for slug, spec in DESKS.items()
        if set(spec["roles"]) & held
    ]}
