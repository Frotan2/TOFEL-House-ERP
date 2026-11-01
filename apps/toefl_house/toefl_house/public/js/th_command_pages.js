/*
 * Role-scoped Desk command pages.
 *
 * This is deliberately a thin client over existing POST command endpoints.
 * It contains no business-document query, no direct CRUD and no client-side
 * authority decision: the server-side KIND_ROLES checks and command contexts
 * remain authoritative for every action. Identifier fields are plain Data
 * controls so opening a page does not perform a Link search/read.
 */
frappe.provide("toefl_house.command_pages");

(() => {
	"use strict";

	const text = (label) => __(label);
	const data = (fieldname, label, options = {}) => ({ fieldname, label, fieldtype: "Data", ...options });
	const integer = (fieldname, label, options = {}) => ({ fieldname, label, fieldtype: "Int", ...options });
	const date = (fieldname, label, options = {}) => ({ fieldname, label, fieldtype: "Date", ...options });
	const time = (fieldname, label, options = {}) => ({ fieldname, label, fieldtype: "Time", ...options });
	const json = (fieldname, label, options = {}) => ({
		fieldname,
		label,
		fieldtype: "Code",
		options: "JSON",
		...options,
	});
	const note = (fieldname, label, options = {}) => ({ fieldname, label, fieldtype: "Small Text", ...options });
	const select = (fieldname, label, values, options = {}) => ({
		fieldname,
		label,
		fieldtype: "Select",
		options: values.join("\n"),
		...options,
	});

	const CONFIG_TYPES = ["blueprint", "policy", "course_map"];
	const ADMISSION_OUTCOMES = ["Approved", "Conditional", "Deferred", "Rejected"];
	const DELIVERY_MODES = ["On-site", "Online", "Hybrid"];
	const CLASS_TRANSITIONS = ["Active", "Completed", "Cancelled"];
	const ATTENDANCE_MARKS = ["Present", "Absent", "Leave"];
	/* Teaching skills are configured server-side in TH Skill (Active only).
	 * The client fetches them at page open; if the fetch fails the field
	 * falls back to a free-text Data input so the server (which authoritatively
	 * validates the code) remains in control of vocabulary. */
	let TEACHING_SKILLS = [];
	const ADMIN_MANAGED_ROLES = [
		"General Manager", "Academic Manager", "Finance Manager", "Reception",
		"Placement Author", "Placement Publisher", "Placement Auditor",
		"Placement Invigilator", "Placement Assessor", "Placement Reviewer",
		"Placement Releaser", "Admission Officer", "Admission Reviewer",
		"Admission Approver", "Admission Auditor", "Enrollment Officer",
		"Enrollment Auditor", "Teaching Scheduler", "Attendance Recorder",
		"Teaching Auditor", "Finance Officer", "Finance Auditor",
	];

	const PAGE_SURFACES = Object.freeze({
		"th-administration-control-centre": {
			admin: true,
			roles: ["Course Owner", "General Manager"],
			title: "TOEFL House Administration Control Centre",
			description: "Review fail-closed release attention and navigate to native identity, role, branch and permission authorities. This surface grants no permission and creates no parallel ledger.",
		},
		"th-command-centre": {
			title: "TOEFL House Command Centre",
			landing: true,
			roles: [
				"Placement Author", "Placement Publisher", "Placement Invigilator",
				"Placement Assessor", "Placement Reviewer", "Placement Releaser",
				"Admission Officer", "Admission Reviewer", "Admission Approver",
				"Enrollment Officer", "Teaching Scheduler", "Attendance Recorder",
			],
			description: "Choose the role-specific command page for a role assigned to this account. These pages open no business-document list or report.",
		},
		"th-placement-author": {
			role: "Placement Author",
			title: "TOEFL House Placement Authoring",
			description: "Create and revise question-bank and exam-configuration drafts. A different authorized employee must approve publication.",
			commands: [
				{
					label: "Create item draft",
					method: "toefl_house.api.create_draft",
					dispatches: ["create_draft"],
					fields: [data("family", "Question family", { reqd: 1 }), integer("revision", "Revision", { reqd: 1 }), json("content", "Content JSON", { reqd: 1 })],
				},
				{
					label: "Revise item draft",
					method: "toefl_house.api.revise_draft",
					dispatches: ["revise_draft"],
					fields: [data("item_name", "Item revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), json("content", "Content JSON", { reqd: 1 })],
				},
				{
					label: "Create configuration draft",
					method: "toefl_house.api.create_draft_config",
					dispatches: ["create_blueprint", "create_policy", "create_course_map"],
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("code", "Configuration code", { reqd: 1 }), integer("revision", "Revision", { reqd: 1 }), json("definition", "Definition JSON", { reqd: 1 })],
				},
				{
					label: "Revise configuration draft",
					method: "toefl_house.api.revise_draft_config",
					dispatches: ["revise_blueprint", "revise_policy", "revise_course_map"],
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("name", "Configuration revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), json("definition", "Definition JSON", { reqd: 1 })],
				},
			],
		},
		"th-placement-publisher": {
			role: "Placement Publisher",
			title: "TOEFL House Placement Publication",
			description: "Publish reviewed exam material and allocate placement attempts. The server enforces independent roles and verifies the candidate and Branch.",
			commands: [
				{
					label: "Publish item revision",
					method: "toefl_house.api.publish",
					dispatches: ["publish"],
					fields: [data("item_name", "Item revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })],
				},
				{
					label: "Review configuration",
					method: "toefl_house.api.review_config",
					dispatches: ["review_blueprint", "review_policy", "review_course_map"],
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("name", "Configuration revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })],
				},
				{
					label: "Publish configuration",
					method: "toefl_house.api.publish_config",
					dispatches: ["publish_blueprint", "publish_policy", "publish_course_map"],
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("name", "Configuration revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })],
				},
				{
					label: "Retire configuration",
					method: "toefl_house.api.retire_config",
					dispatches: ["retire_blueprint", "retire_policy", "retire_course_map"],
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("name", "Configuration revision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })],
				},
				{
					label: "Create placement case",
					method: "toefl_house.api.create_case",
					dispatches: ["create_case"],
					fields: [data("subject", "Synthetic test User (optional for real visitors)", { description: "Leave blank for real visitors. The server issues a unique internal candidate reference from the Reception inquiry." }), data("purpose", "Purpose"),
                        data("branch", "Branch", { reqd: 1, description: "Select the authorized placement branch for this candidate. The branch is immutable after case creation." }),
                        data("inquiry", "Reception inquiry reference", { description: "Required for real candidates. Reception must mark this visitor Awaiting Placement. This link is not proof of identity." })],
				},
				{
					label: "Allocate placement attempt",
					method: "toefl_house.api.allocate_attempt",
					dispatches: ["allocate_attempt"],
					fields: [data("case", "Placement case", { reqd: 1 }), data("blueprint", "Published blueprint", { reqd: 1 }), integer("blueprint_version", "Blueprint version", { reqd: 1 }), data("policy", "Published policy", { reqd: 1 }), integer("policy_version", "Policy version", { reqd: 1 })],
				},
			],
		},
		"th-placement-invigilation": {
			role: "Placement Invigilator",
			title: "TOEFL House Placement Invigilation",
			description: "Run the existing supervised digital-session commands. The server verifies the assigned operator and current attempt state.",
			commands: [
				{ label: "Verify attempt", method: "toefl_house.api.verify_attempt", dispatches: ["verify_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
				{ label: "Deliver attempt", method: "toefl_house.api.deliver_attempt", dispatches: ["deliver_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
				{ label: "Save response", method: "toefl_house.api.save_response", dispatches: ["save_response"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), integer("occurrence", "Occurrence", { reqd: 1 }), integer("expected_revision", "Expected response revision", { reqd: 1 }), data("option_id", "Option ID"), { fieldname: "missing", label: "Mark as missing", fieldtype: "Check", default: 0 }] },
				{ label: "Seal attempt", method: "toefl_house.api.seal_attempt", dispatches: ["seal_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), note("reason", "Seal reason", { reqd: 1 })] },
			],
		},
		"th-placement-assessment": {
			role: "Placement Assessor",
			title: "TOEFL House Placement Assessment",
			description: "Score sealed digital exam answers. Only the server loads confidential answer keys.",
			commands: [
				{ label: "Score attempt", method: "toefl_house.api.score_attempt", dispatches: ["score_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-placement-review": {
			role: "Placement Reviewer",
			title: "TOEFL House Placement Review",
			description: "Perform the existing independent review and finalization transitions. The server rejects prohibited self-review or self-finalization.",
			commands: [
				{ label: "Review marked attempt", method: "toefl_house.api.review_attempt", dispatches: ["review_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
				{ label: "Finalize reviewed attempt", method: "toefl_house.api.finalize_attempt", dispatches: ["finalize_attempt"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-placement-release": {
			role: "Placement Releaser",
			title: "TOEFL House Placement Release",
			description: "Release a finalized placement decision after independent scoring, review and finalization. Production level mapping remains blocked until academically approved.",
			commands: [
				{ label: "Release placement decision", method: "toefl_house.api.release_decision", dispatches: ["release_decision"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-admission-officer": {
			role: "Admission Officer",
			title: "TOEFL House Admission Intake",
			description: "Run the thin admission intake and officer transitions over native Student Applicant and Student authorities. The page does not create an enrollment or a billing record.",
			commands: [
				{ label: "Record applicant", method: "toefl_house.admission.record_applicant", dispatches: ["record_applicant"], fields: [data("placement_decision", "Released placement decision", { reqd: 1 }), data("first_name", "First name", { reqd: 1 }), data("program", "Program", { reqd: 1 }), data("academic_year", "Academic year", { reqd: 1 }), data("branch", "Branch", { description: "Blank: the recording officer's own branch." }), data("last_name", "Family name (optional)")] },
				{ label: "Create admission decision", method: "toefl_house.admission.create_admission", dispatches: ["create_admission"], fields: [data("student_applicant", "Student applicant", { reqd: 1 }), data("placement_decision", "Released placement decision", { reqd: 1 }), data("existing_student", "Existing student"), data("program", "Program", { description: "Returning journeys only; blank inherits the applicant record." }), data("academic_year", "Academic year", { description: "Returning journeys only; blank inherits the applicant record." }), data("academic_term", "Academic term", { description: "Returning journeys only; blank inherits the applicant record." })] },
				{ label: "Accept offer", method: "toefl_house.admission.accept_offer", dispatches: ["accept_offer"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
				{ label: "Withdraw admission", method: "toefl_house.admission.withdraw_admission", dispatches: ["withdraw_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Expire admission", method: "toefl_house.admission.expire_admission", dispatches: ["expire_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-admission-review": {
			role: "Admission Reviewer",
			title: "TOEFL House Admission Review",
			description: "Move an existing thin admission decision into review through the guarded server command.",
			commands: [
				{ label: "Review admission", method: "toefl_house.admission.review_admission", dispatches: ["review_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-admission-approval": {
			role: "Admission Approver",
			title: "TOEFL House Admission Approval",
			description: "Run the existing admission decision, condition satisfaction, revocation and native Student conversion commands. Eligibility and transition controls remain server-side.",
			commands: [
				{ label: "Decide admission", method: "toefl_house.admission.decide_admission", dispatches: ["decide_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), select("outcome", "Outcome", ADMISSION_OUTCOMES, { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), note("conditions", "Conditions")] },
				{ label: "Satisfy conditions", method: "toefl_house.admission.satisfy_conditions", dispatches: ["satisfy_conditions"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), note("evidence", "Verification evidence", { reqd: 1 })] },
				{ label: "Revoke admission", method: "toefl_house.admission.revoke_admission", dispatches: ["revoke_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Convert applicant", method: "toefl_house.admission.convert_applicant", dispatches: ["convert_applicant"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-enrollment": {
			role: "Enrollment Officer",
			title: "TOEFL House Enrollment",
				description: "Submit one eligible native Program Enrollment through the guarded enrollment command. The server enforces actor separation from the admission decision. Withdrawals and dismissal decisions end a registration through the guarded exit commands.",
			commands: [
				{ label: "Enroll in program", method: "toefl_house.enrollment.enroll_in_program", dispatches: ["enroll_in_program"], fields: [data("admission_decision", "Admission decision", { reqd: 1 })] },
				{ label: "Withdraw enrollment", method: "toefl_house.enrollment.exits.withdraw_enrollment", dispatches: ["withdraw_enrollment"], fields: [data("program_enrollment", "Program enrollment", { reqd: 1 }), date("exit_date", "Exit date", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Request enrollment dismissal", method: "toefl_house.enrollment.exits.request_enrollment_dismissal", dispatches: ["request_enrollment_dismissal"], fields: [data("program_enrollment", "Program enrollment", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Approve enrollment dismissal", method: "toefl_house.enrollment.exits.approve_enrollment_dismissal", dispatches: ["approve_enrollment_dismissal"], fields: [data("exit", "Enrollment exit", { reqd: 1 })] },
				{ label: "Deny enrollment dismissal", method: "toefl_house.enrollment.exits.deny_enrollment_dismissal", dispatches: ["deny_enrollment_dismissal"], fields: [data("exit", "Enrollment exit", { reqd: 1 })] },
			],
		},
		"th-teaching-scheduling": {
			role: "Teaching Scheduler",
			title: "TOEFL House Teaching Scheduling",
			description: "Create native class, session, roster and skill-assignment facts through guarded commands. The page performs no native list or link lookup.",
			commands: [
				{ label: "Create student group", method: "toefl_house.teaching.create_student_group", dispatches: ["create_student_group"], fields: [data("group_name", "Synthetic group name", { reqd: 1 }), data("program", "Program", { reqd: 1 }), data("academic_year", "Academic year", { reqd: 1 }), data("academic_term", "Academic term"), integer("max_strength", "Maximum strength", { reqd: 1 }), date("class_start_date", "Class start date"), date("class_end_date", "Class end date (blank = use level duration policy)"), select("delivery_mode", "Delivery mode", DELIVERY_MODES, { default: "On-site" }), data("branch", "Branch"), data("students", "Student IDs (optional)", { description: "Comma-separated Student IDs with submitted enrollments; leave blank for the full intake." })] },
				{ label: "Add class member", method: "toefl_house.teaching.add_class_member", dispatches: ["add_class_member"], fields: [data("student_group", "Student group", { reqd: 1 }), data("student", "Student", { reqd: 1 }), data("override", "Capacity override (only when full)")] },
				{ label: "Move class member", method: "toefl_house.teaching.move_class_member", dispatches: ["move_class_member"], fields: [data("student_group", "Student group", { reqd: 1 }), data("student", "Student", { reqd: 1 }), data("to_group", "Target student group", { reqd: 1 })] },
				{ label: "Remove class member", method: "toefl_house.teaching.remove_class_member", dispatches: ["remove_class_member"], fields: [data("student_group", "Student group", { reqd: 1 }), data("student", "Student", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Transition class", method: "toefl_house.teaching.transition_class", dispatches: ["transition_class"], fields: [data("student_group", "Student group", { reqd: 1 }), select("to_status", "New status", CLASS_TRANSITIONS, { reqd: 1 })] },
				{ label: "Schedule session", method: "toefl_house.teaching.schedule_session", dispatches: ["schedule_session"], fields: [data("student_group", "Student group", { reqd: 1 }), date("schedule_date", "Schedule date", { reqd: 1 }), time("from_time", "From time", { reqd: 1 }), time("to_time", "To time", { reqd: 1 }), data("instructor", "Instructor", { reqd: 1 }), data("room", "Room", { reqd: 1 }), data("course", "Course", { reqd: 1 })] },
				{ label: "Assign teaching skill", method: "toefl_house.teaching.compensation.assign_teaching_skill", dispatches: ["assign_teaching_skill"], fields: [data("student_group", "Student group", { reqd: 1 }), select("skill", "Skill (code)", TEACHING_SKILLS, { reqd: 1, placeholder: "Loading skills…" }), data("instructor", "Instructor", { reqd: 1 }), data("contract", "Instructor contract", { reqd: 1 }), date("effective_start", "Effective start", { reqd: 1 }), date("effective_end", "Effective end"), data("course_schedule", "Course schedule")] },
				{ label: "End teaching assignment", method: "toefl_house.teaching.compensation.end_teaching_assignment", dispatches: ["end_teaching_assignment"], fields: [data("assignment", "Teaching assignment", { reqd: 1 }), date("effective_end", "Effective end", { reqd: 1 })] },
				{ label: "Generate timetable", method: "toefl_house.teaching.scheduling.generate_timetable", dispatches: ["generate_timetable"], fields: [data("student_group", "Student group", { reqd: 1 }), data("template", "Timetable template", { reqd: 1 }), date("start_date", "First day", { reqd: 1 }), date("end_date", "Last day", { reqd: 1 })] },
				{ label: "Postpone session", method: "toefl_house.teaching.scheduling.postpone_session", dispatches: ["postpone_session"], fields: [data("course_schedule", "Course schedule", { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), date("new_date", "New date", { reqd: 1 }), time("from_time", "From time"), time("to_time", "To time"), data("room", "Room"), data("instructor", "Instructor")] },
				{ label: "Schedule make-up session", method: "toefl_house.teaching.scheduling.schedule_replacement_session", dispatches: ["schedule_replacement_session"], fields: [data("course_schedule", "Course schedule", { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), date("schedule_date", "Schedule date", { reqd: 1 }), time("from_time", "From time", { reqd: 1 }), time("to_time", "To time", { reqd: 1 }), data("room", "Room"), data("instructor", "Instructor")] },
				{ label: "Cancel session", method: "toefl_house.teaching.scheduling.cancel_session", dispatches: ["cancel_session"], fields: [data("course_schedule", "Course schedule", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Suspend class", method: "toefl_house.teaching.suspensions.suspend_class", dispatches: ["suspend_class"], fields: [data("student_group", "Student group", { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), date("from_date", "From date", { reqd: 1 }), date("until_date", "Until date", { reqd: 1 })] },
				{ label: "Suspend student membership", method: "toefl_house.teaching.suspensions.suspend_student_membership", dispatches: ["suspend_student_membership"], fields: [data("student_group", "Student group", { reqd: 1 }), data("student", "Student", { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), date("from_date", "From date", { reqd: 1 }), date("until_date", "Until date", { reqd: 1 })] },
				{ label: "Resume suspension", method: "toefl_house.teaching.suspensions.resume_suspension", dispatches: ["resume_suspension"], fields: [data("suspension", "Suspension", { reqd: 1 }), note("reason", "Why it ended early")] },
				{ label: "Offer waiting-list seat", method: "toefl_house.teaching.capacity.offer_waiting_list_seat", dispatches: ["offer_waiting_list_seat"], fields: [data("entry", "Waiting-list entry", { reqd: 1 }), date("expires_on", "Hold until (blank = policy)")] },
				{ label: "Admit from waiting list", method: "toefl_house.teaching.capacity.admit_from_waiting_list", dispatches: ["admit_from_waiting_list"], fields: [data("entry", "Waiting-list entry", { reqd: 1 }), data("override", "Capacity override (only when full)")] },
				{ label: "Request class transfer", method: "toefl_house.teaching.transfers.request_class_transfer", dispatches: ["request_class_transfer"], fields: [data("student", "Student", { reqd: 1 }), data("from_group", "From class", { reqd: 1 }), data("to_group", "Target student group", { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), date("effective_date", "Effective date", { reqd: 1 })] },
				{ label: "Cancel class transfer", method: "toefl_house.teaching.transfers.cancel_class_transfer", dispatches: ["cancel_class_transfer"], fields: [data("transfer", "Transfer", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
			],
		},
		"th-attendance-recording": {
			role: "Attendance Recorder",
			title: "TOEFL House Attendance Recording",
			description: "Record submitted native Student Attendance facts for a scheduled session through the guarded command. Supply the complete status JSON required by the server. Corrections run as request/approve/deny inside the owner policy window.",
			commands: [
				{ label: "Record attendance", method: "toefl_house.teaching.record_attendance", dispatches: ["record_attendance"], fields: [data("course_schedule", "Course schedule", { reqd: 1 }), json("statuses", "Statuses JSON", { reqd: 1 })] },
				{ label: "Request attendance correction", method: "toefl_house.teaching.attendance_corrections.request_attendance_correction", dispatches: ["request_attendance_correction"], fields: [data("attendance", "Student attendance", { reqd: 1 }), select("requested_status", "Requested mark", ATTENDANCE_MARKS, { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Approve attendance correction", method: "toefl_house.teaching.attendance_corrections.approve_attendance_correction", dispatches: ["approve_attendance_correction"], fields: [data("request", "Correction request", { reqd: 1 })] },
				{ label: "Deny attendance correction", method: "toefl_house.teaching.attendance_corrections.deny_attendance_correction", dispatches: ["deny_attendance_correction"], fields: [data("request", "Correction request", { reqd: 1 })] },
			],
		},
	});

	function newRequestKey() {
		const alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
		const bytes = new Uint32Array(24);
		window.crypto.getRandomValues(bytes);
		return Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
	}

	function requestKeyField() {
		return data("request_key", "Request key", {
			reqd: 1,
			default: newRequestKey(),
			description: "Keep this exact value when retrying the same request.",
		});
	}

	function manageAdminRole() {
		const dialog = new frappe.ui.Dialog({
			title: text("Manage TOEFL role assignment"),
			fields: [
				requestKeyField(),
				data("user", "User", { reqd: 1, description: "Native User name or email; no user search is performed." }),
				select("role", "Managed role", ADMIN_MANAGED_ROLES, { reqd: 1 }),
				{ fieldname: "enabled", label: "Assign role", fieldtype: "Check", default: 1 },
			],
			primary_action_label: text("Apply native role change"),
			primary_action(values) {
				frappe.call({
					method: "toefl_house.administration.set_managed_role",
					args: {
						request_key: values.request_key,
						user: values.user,
						role: values.role,
						enabled: values.enabled ? 1 : 0,
					},
					freeze: true,
					callback(response) {
						dialog.hide();
						resultMessage("Role change", response.message);
					},
				});
			},
		});
		dialog.show();
	}

	/*
	 * Response projection.
	 *
	 * Command responses used to be handed to staff as raw JSON inside a <pre>.
	 * That is legible to an engineer and unusable to a receptionist, and it
	 * forced every operator to learn the server's field names to know whether
	 * an action succeeded. The payload is now projected into a headline, one
	 * status pill and an ordered fact list. The original response is still
	 * shown in full inside a collapsed section, so an auditor sees exactly what
	 * the server returned - this changes the reading order, never the record.
	 *
	 * Presentation only: no value here is computed, defaulted or reinterpreted.
	 * Anything the server did not send is simply absent from the list rather
	 * than invented, and an unrecognised status falls back to a neutral tone.
	 */
	const FACT_LABELS = Object.freeze({
		name: "Record",
		attempt: "Attempt",
		item: "Item",
		item_name: "Item revision",
		revision: "Revision",
		version: "Version now",
		expected_version: "Expected version",
		status: "Status",
		subject: "Verified candidate User",
		purpose: "Purpose",
		reason: "Reason",
		program: "Program",
		course: "Course",
		academic_year: "Academic year",
		student_applicant: "Student applicant",
		student_group: "Student group",
		student_email_id: "Student email",
		customer: "Customer",
		placement_decision: "Released placement decision",
		blueprint: "Published blueprint",
		policy: "Published policy",
		config: "Configuration type",
		content_hash: "Content hash",
		skill_terms: "Skill terms",
		ordinal: "Ordinal",
		option_id: "Option ID",
		missing: "Missing",
		instructor: "Instructor",
		to_time: "To time",
		from_time: "From time",
	});

	/* Tones are presentational. They must never imply an outcome the server did
	 * not state, so an unmapped status is neutral rather than assumed good. */
	const STATUS_TONES = Object.freeze({
		active: "ok", approved: "ok", completed: "ok", passed: "ok",
		published: "ok", released: "ok", submitted: "ok", success: "ok", verified: "ok",
		draft: "info", pending: "info", open: "info", review: "info",
		scheduled: "info", "in progress": "info",
		conditional: "warn", deferred: "warn", partial: "warn", warning: "warn",
		hold: "warn", "on hold": "warn",
		reject: "danger", rejected: "danger", refused: "danger",
		cancelled: "danger", canceled: "danger",
		failed: "danger", blocked: "danger", error: "danger", expired: "danger",
		withdrawn: "danger",
	});

	/* Keys are stable identifiers, not prose, so they are never translated and
	 * stay comparable with the raw payload below. */
	const UNTRANSLATED_KEYS = Object.freeze(Object.keys(FACT_LABELS).concat(["request_key"]));

	function escapeText(value) {
		return String(value)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
	}

	function isShown(fieldname, value) {
		if (value === undefined || value === null || value === "") return false;
		if (Array.isArray(value)) return value.length > 0;
		// The request key is transport, not a business fact the operator asked
		// about, so it stays out of the readable summary.
		return !UNTRANSLATED_KEYS.includes(fieldname) || fieldname !== "request_key";
	}

	function factLabel(fieldname) {
		return FACT_LABELS[fieldname] || fieldname
			.replace(/_/g, " ")
			.replace(/^./, (character) => character.toUpperCase());
	}

	function statusTone(value) {
		const key = String(value).trim().toLowerCase();
		return STATUS_TONES[key] || "neutral";
	}

	function statusMarkup(value) {
		const tone = statusTone(value);
		return `<span class="th-status th-status--${tone}">${escapeText(value)}</span>`;
	}

	/* Lists such as `missing` read better as a sentence than as JSON syntax. */
	function factValue(value) {
		if (Array.isArray(value)) return escapeText(value.join(", "));
		if (typeof value === "boolean") return escapeText(value ? "Yes" : "No");
		if (typeof value === "object") return escapeText(JSON.stringify(value));
		return escapeText(value);
	}

	function factRows(payload) {
		if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
		return Object.entries(payload)
			.filter(([fieldname, value]) => fieldname !== "status" && isShown(fieldname, value))
			.map(([fieldname, value]) =>
				`<dt>${escapeText(factLabel(fieldname))}</dt><dd>${factValue(value)}</dd>`)
			.join("");
	}

	/* The headline answers "did that work?" before any detail is read. */
	function resultHeadline(label, payload) {
		const status = payload && typeof payload === "object" && !Array.isArray(payload)
			? payload.status : undefined;
		if (status === undefined) return text(label) + " " + text("completed.");
		const tone = statusTone(status);
		if (tone === "danger") return text(label) + " " + text("did not complete.") + " " + escapeText(status) + ".";
		if (tone === "warn") return text(label) + " " + text("needs attention.") + " " + escapeText(status) + ".";
		return text(label) + " " + text("succeeded.") + " " + escapeText(status) + ".";
	}

	function resultMarkup(label, payload) {
		const hasFacts = Boolean(factRows(payload));
		const status = payload && typeof payload === "object" && !Array.isArray(payload)
			? payload.status : undefined;
		return [
			"<div class='th-result'>",
			"<div class='th-result-heading'>",
			status === undefined ? "" : statusMarkup(status),
			`<p class='th-result-summary'>${resultHeadline(label, payload)}</p>`,
			"</div>",
			hasFacts ? `<dl class='th-facts'>${factRows(payload)}</dl>` : "",
			"<details class='th-result-raw'>",
			`<summary>${text("Full server response")}</summary>`,
			`<pre>${escapeText(JSON.stringify(payload, null, 2))}</pre>`,
			"</details>",
			"</div>",
		].join("");
	}

	function resultMessage(label, result) {
		frappe.msgprint({ title: text(label + " result"), message: resultMarkup(label, result), wide: true });
	}

	function resolveFields(fields) {
		// Defer options lookup to open-time so that asynchronously loaded
		// vocabularies (e.g. TH Skill codes) reflect current configuration.
		return fields.map((field) => {
			if (field.fieldname === "skill" && field.fieldtype === "Select") {
				return { ...field, options: TEACHING_SKILLS.join("\n") || (field.placeholder || "") };
			}
			return field;
		});
	}

	function runCommand(command) {
		const dialog = new frappe.ui.Dialog({
			title: text(command.label),
			fields: [requestKeyField(), ...resolveFields(command.fields)],
			primary_action_label: text("Run command"),
			primary_action(values) {
				const args = { request_key: values.request_key };
				command.fields.forEach((field) => {
					const value = field.fieldtype === "Check" ? (values[field.fieldname] ? 1 : 0) : values[field.fieldname];
					args[field.fieldname] = value;
				});
				frappe.call({
					method: command.method,
					args,
					freeze: true,
					freeze_message: text("Submitting guarded command"),
					callback(response) {
						dialog.hide();
						resultMessage(command.label, response.message);
					},
				});
			},
		});
		dialog.show();
	}

	/*
	 * Asset loading.
	 *
	 * The stylesheet is pulled through frappe.require rather than an
	 * `app_include_css` hook on purpose: require is lazy, is already the
	 * platform's asset mechanism, and cannot break application boot if the file
	 * is absent, whereas a bad include hook fails every page load for every
	 * user. Loading is idempotent because a page may be revisited in one
	 * session.
	 */
	const STYLESHEET = "/assets/toefl_house/css/th_design_system.css";
	let stylesheetLoaded = false;

	function ensureStyleSheet() {
		if (stylesheetLoaded) return;
		stylesheetLoaded = true;
		if (typeof frappe.require === "function") frappe.require(STYLESHEET);
	}

	/*
	 * Page header.
	 *
	 * Every surface answers the same three questions in the same place: what is
	 * this, why am I here, and what does this page not do. Repeating that
	 * structure across all fourteen pages is what makes the app read as one
	 * product instead of fourteen unrelated screens.
	 */
	function renderHeader(page, surface) {
		const header = $("<div class='th-page-header'></div>").appendTo(page.body);
		$("<p class='th-eyebrow'></p>").text(text("TOEFL House")).appendTo(header);
		$("<h1 class='th-page-title'></h1>").text(text(surface.title)).appendTo(header);
		$("<p class='th-page-purpose'></p>").text(text(surface.description)).appendTo(header);
		$("<p class='th-page-assurance'></p>")
			.text(text("This page grants no permission. The server validates the assigned role, request key, state and separation controls for every action."))
			.appendTo(header);
	}

	function section(parent, title) {
		const block = $("<section class='th-section'></section>").appendTo(parent);
		$("<h2 class='th-section-title'></h2>").text(text(title)).appendTo(block);
		return block;
	}

	/* An action card. One primary button per card, always last, so scanning
	 * title -> purpose -> action is the same motion on every page.
	 *
	 * The optional chip is rendered by the builder rather than inserted by the
	 * caller reaching back into the DOM, because climbing from the returned
	 * button with closest()/find() is both harder to read and impossible for the
	 * static contract suite to exercise - a no-op fake would pass it silently. */
	function actionCard(grid, title, hint, buttonLabel, onClick, chipLabel) {
		const card = $("<article class='th-card'></article>").appendTo(grid);
		$("<h3 class='th-card-title'></h3>").text(text(title)).appendTo(card);
		if (hint) $("<p class='th-card-hint'></p>").text(text(hint)).appendTo(card);
		const footer = $("<div class='th-card-footer'></div>").appendTo(card);
		if (chipLabel) {
			$("<span class='th-role-chip'></span>").text(text(chipLabel)).appendTo(footer);
		}
		$("<button type='button' class='btn btn-primary btn-sm th-action'></button>")
			.text(text(buttonLabel))
			.on("click", onClick)
			.appendTo(footer);
		return card;
	}

	function loadActiveSkills() {
		// Populate the skill select with codes fetched from the server.
		// A failure leaves the field as a Data entry (the server authoritatively
		// validates), so the page stays usable offline and never invents skills.
		frappe.call({
			method: "toefl_house.teaching.active_skills",
			callback(response) {
				const list = (response.message || []).map((r) => r.code);
				if (list.length) {
					TEACHING_SKILLS = list;
					// Patch any already-rendered selects so the user sees options
					// without needing to reload. Dialogs read options at open time,
					// so they will already use the fresh list.
					$("select[data-fieldname='skill']").each((_, el) => {
						const current = el.value;
						el.innerHTML = list.map((c) =>
							`<option value="${escapeText(c)}"${c === current ? " selected" : ""}>${escapeText(c)}</option>`
						).join("");
					});
				}
			},
		});
	}

	/*
	 * Invigilator-operated answer workstation. This is intentionally NOT a
	 * candidate kiosk: a candidate must never be given an authenticated
	 * Frappe staff session, its navigation, or command cards.
	 *
	 * The read API exposes only a protected question projection and latest
	 * response revisions. It never includes item keys, seed or manifest data.
	 */
	function mountSupervisedPlacement(page) {
		const block = section(page.body, text("Supervised digital exam workspace"));
		block.addClass("th-placement-console").attr("lang", "en").attr("dir", "ltr");
		$("<p class='th-card-hint'></p>").text(text(
			"Staff-operated only. Check the candidate's identity and branch before starting. " +
			"Never hand a Frappe staff login to an examinee. Saved answers can be recovered after refreshing."
		)).appendTo(block);
		const toolbar = $("<div class='th-placement-toolbar'></div>").appendTo(block);
		const idLabel = $("<label class='th-placement-label'></label>")
			.text(text("Attempt reference")).appendTo(toolbar);
		const attemptField = $("<input type='text' class='form-control' autocomplete='off' maxlength='140'>")
			.attr("aria-label", text("Attempt reference")).appendTo(idLabel);
		const load = $("<button type='button' class='btn btn-primary'></button>")
			.text(text("Check exam status")).appendTo(toolbar);
		const suggestions = $("<datalist id='th-placement-attempt-choices'></datalist>").appendTo(block);
		attemptField.attr("list", "th-placement-attempt-choices");
		let choicesPending = false;
		attemptField.on("focus", () => {
			if (choicesPending) return;
			choicesPending = true;
			frappe.call({
				method: "toefl_house.api.supervised_attempt_choices", type: "GET",
				callback(reply) {
					choicesPending = false;
					suggestions.empty();
					const rows = Array.isArray(reply.message) ? reply.message : [];
					rows.forEach((item) => {
						if (!item || !item.attempt) return;
						$("<option></option>").attr("value", item.attempt)
							.attr("label", String(item.status || "") + " · " +
								String(item.candidate_reference || "")).appendTo(suggestions);
					});
				},
				error() {
					choicesPending = false;
					inform("The Branch attempt list is unavailable. You may enter an exact Attempt reference.");
				},
			});
		});
		const notice = $("<p class='th-placement-notice' role='status' aria-live='polite'></p>").appendTo(block);
		const content = $("<div class='th-placement-content'></div>").appendTo(block);
		let active = null;
		let position = 0;
		let pending = false;
		let pendingWrite = null;

		function inform(message) { notice.text(text(message)); }
		function setBusy(value) {
			pending = value;
			load.prop("disabled", value);
			content.find("button,input").prop("disabled", value);
		}
		function currentResponse(question) {
			return (active.responses || []).find((answer) =>
				Number(answer.occurrence) === Number(question.order)) ||
				{ occurrence: question.order, revision: 0, option_id: "", missing: 0 };
		}
		function draw() {
			content.empty();
			if (!active) return;
			const items = active.projection.items;
			if (!items.length) {
				inform("No valid questions were returned. Ask the Academic Manager to review this exam.");
				return;
			}
			position = Math.min(Math.max(0, position), items.length - 1);
			const question = items[position];
			const saved = currentResponse(question);
			const answered = (active.responses || []).filter((r) => r.option_id && !r.missing).length;
			$("<p class='th-placement-progress'></p>").text(text(
				"Question " + (position + 1) + " of " + items.length +
				" · " + answered + " saved · " + (items.length - answered) + " unanswered"
			)).appendTo(content);
			$("<p class='th-placement-deadline'></p>").text(text(
				"Server deadline: " + active.deadline_at + " (course-site time). " +
				"The server enforces time limits; this display is not a timer."
			)).appendTo(content);
			let unsavedSelection = false;
			const form = $("<fieldset class='th-placement-question'></fieldset>").appendTo(content);
			$("<legend></legend>").text(text(question.skill + " · " + question.question_type)).appendTo(form);
			$("<p class='th-placement-prompt'></p>").text(question.prompt).appendTo(form);
			const optionName = "th-exam-" + question.order;
			(question.options || []).forEach((option) => {
				const label = $("<label class='th-placement-option'></label>").appendTo(form);
				const radio = $("<input type='radio'>").attr("name", optionName).val(option.id).appendTo(label);
				if (!saved.missing && option.id === saved.option_id) radio.prop("checked", true);
				radio.on("change", () => { unsavedSelection = true; });
				$("<span></span>").text(option.text).appendTo(label);
			});
			const actions = $("<div class='th-placement-controls'></div>").appendTo(content);
			$("<button type='button' class='btn btn-secondary'></button>").text(text("Previous"))
				.prop("disabled", position === 0).on("click", () => {
					if (unsavedSelection) { inform("Save or clear the selected answer before changing questions."); return; }
					position -= 1; draw();
				}).appendTo(actions);
			$("<button type='button' class='btn btn-secondary'></button>").text(text("Next"))
				.prop("disabled", position === items.length - 1)
				.on("click", () => {
					if (unsavedSelection) { inform("Save or clear the selected answer before changing questions."); return; }
					position += 1; draw();
				}).appendTo(actions);
			const save = $("<button type='button' class='btn btn-primary'></button>")
				.text(text("Save selected answer")).appendTo(actions);
			const clear = $("<button type='button' class='btn btn-secondary'></button>")
				.text(text("Clear saved answer")).appendTo(actions);
			function sendAnswer(missing) {
				if (pending || pendingWrite) return;
				const selected = form.find("input[type='radio']:checked").val();
				if (!missing && !selected) {
					inform("Choose an option before saving, or use Clear saved answer.");
					return;
				}
				pendingWrite = {
					request_key: newRequestKey(),
					attempt: active.attempt,
					expected_version: Number(active.version),
					occurrence: Number(question.order),
					expected_revision: Number(saved.revision),
					option_id: missing ? "" : selected,
					missing: missing ? 1 : 0,
				};
				setBusy(true);
				inform("Saving this answer securely.");
				frappe.call({
					method: "toefl_house.api.save_response", type: "POST", args: pendingWrite,
					callback(response) {
						const result = response.message || {};
						if (result.status === "Sealed") {
							// The response arrived after the authoritative server
							// deadline, so the command sealed unanswered items.
							active = null;
							pendingWrite = null;
							setBusy(false);
							draw();
							inform("The server timed out and sealed this exam. No further answers can be saved.");
							return;
						}
						if (result.occurrence !== question.order || !Number.isInteger(Number(result.revision))) {
							inform("Unconfirmed answer save. Reload this attempt before doing anything else.");
							setBusy(false);
							return;
						}
						active.responses = active.responses.filter((r) => Number(r.occurrence) !== Number(question.order));
						active.responses.push({
							occurrence: question.order, revision: Number(result.revision),
							option_id: missing ? "" : selected, missing: missing ? 1 : 0,
						});
						pendingWrite = null;
						setBusy(false);
						inform("Answer saved. You can move to the next question.");
						draw();
					},
					error() {
						inform("Save outcome is unknown. Reload the exam to confirm it; do not assume the answer was saved.");
						setBusy(false);
					},
				});
			}
			save.on("click", () => sendAnswer(false));
			clear.on("click", () => sendAnswer(true));
			const submit = $("<button type='button' class='btn btn-danger'></button>")
				.text(text("Submit and close exam")).appendTo(actions);
			submit.on("click", () => {
				if (unsavedSelection) {
					inform("Your selected answer is not saved. Save or clear it before submitting.");
					return;
				}
				if (pending || pendingWrite) {
					inform("Reload the exam to resolve an uncertain save before submitting.");
					return;
				}
				const count = active.responses.filter((r) => r.option_id && !r.missing).length;
				frappe.confirm(text(
					"Submit and permanently seal this attempt? " + (items.length - count) +
					" question(s) are unanswered. No more changes will be accepted."
				), () => {
					if (pending) return;
					setBusy(true);
					const args = {
						request_key: newRequestKey(), attempt: active.attempt,
						expected_version: Number(active.version), reason: "Submitted",
					};
					frappe.call({
						method: "toefl_house.api.seal_attempt", type: "POST", args,
						callback(response) {
							const result = response.message || {};
							if (result.status !== "Sealed") {
								inform("Seal confirmation was not returned. Reload and check the attempt state.");
								setBusy(false);
								return;
							}
							active = null;
							pendingWrite = null;
							setBusy(false);
							draw();
							inform("Exam sealed. Answers are locked. Continue with independent scoring and review.");
						},
						error() {
							setBusy(false);
							inform("Seal status is unknown. Ask the invigilator to verify the attempt before retrying.");
						},
					});
				});
			});
		}

		function reload() {
			if (pending) return;
			const attempt = attemptField.val().trim();
			if (!attempt) {
				inform("Enter an attempt reference issued by the placement team.");
				return;
			}
			pendingWrite = null;
			active = null;
			draw();
			setBusy(true);
			inform("Checking session access and recovering confirmed answers.");
			frappe.call({
				method: "toefl_house.api.supervised_attempt_view", type: "GET",
				args: { attempt },
				callback(response) {
					const result = response.message || {};
					if (!result.projection || !Array.isArray(result.projection.items) ||
							!Array.isArray(result.responses) || result.status !== "In Progress") {
						setBusy(false);
						inform("No active supervised exam was returned. Check its status with the invigilator.");
						return;
					}
					active = result;
					position = 0;
					setBusy(false);
					inform("Active exam loaded. Only confirmed server responses are marked saved.");
					draw();
				},
				error() {
					setBusy(false);
					inform("Exam unavailable or permission denied. Check branch, attempt state and deadline.");
				},
			});
		}

		/*
		 * A key-free server status check drives the preparation and delivery
		 * stages. Never infer the attempt version or station authority locally.
		 * Each POST is still a separate, idempotent domain command.
		 */
		function checkStatus() {
			if (pending) return;
			const attempt = attemptField.val().trim();
			if (!attempt) {
				inform("Enter an attempt reference issued by the placement team.");
				return;
			}
			pendingWrite = null;
			active = null;
			content.empty();
			setBusy(true);
			inform("Checking the current, branch-authorized attempt status.");
			frappe.call({
				method: "toefl_house.api.supervised_attempt_status", type: "GET",
				args: { attempt },
				callback(response) {
					const state = response.message || {};
					setBusy(false);
					if (state.attempt !== attempt || !Number.isInteger(Number(state.version))) {
						inform("Attempt status could not be verified. Ask an Academic Manager to review it.");
						return;
					}
					if (state.status === "In Progress" && !state.deadline_reached) {
						reload();
						return;
					}
					if (state.deadline_reached) {
						inform("The server deadline has passed. No new answers can be entered.");
						const timeoutSeal = $("<button type='button' class='btn btn-danger'></button>")
							.text(text("Seal timed-out exam")).appendTo(content);
						timeoutSeal.on("click", () => {
							if (pending) return;
							frappe.confirm(text(
								"Permanently seal the timed-out exam now? All unanswered questions will be marked missing."
							), () => {
								if (pending) return;
								setBusy(true);
								frappe.call({
									method: "toefl_house.api.seal_attempt", type: "POST",
									args: {
										request_key: newRequestKey(), attempt: state.attempt,
										expected_version: Number(state.version), reason: "Timeout",
									},
									callback(reply) {
										setBusy(false);
										if ((reply.message || {}).status === "Sealed") checkStatus();
										else inform("Timeout seal was not confirmed. Recheck the current attempt status.");
									},
									error() {
										setBusy(false);
										inform("Timeout seal outcome is unknown. Recheck status before retrying.");
									},
								});
							});
						});
						return;
					}
					if (state.status === "Allocated") {
						inform("This attempt is allocated. Check the real candidate's identity and branch before verification.");
						const approval = $("<label class='th-placement-option'></label>").appendTo(content);
						const check = $("<input type='checkbox'>").appendTo(approval);
						$("<span></span>").text(text(
							"I personally checked the candidate's identity, the correct Branch and the supervised station."
						)).appendTo(approval);
						const verify = $("<button type='button' class='btn btn-primary'></button>")
							.text(text("Verify candidate and attempt")).prop("disabled", true).appendTo(content);
						check.on("change", () => verify.prop("disabled", !check.prop("checked")));
						verify.on("click", () => {
							if (pending || !check.prop("checked")) return;
							setBusy(true);
							inform("Verifying attempt with the server.");
							frappe.call({
								method: "toefl_house.api.verify_attempt", type: "POST",
								args: {
									request_key: newRequestKey(), attempt: state.attempt,
									expected_version: Number(state.version),
								},
								callback(reply) {
									setBusy(false);
									if ((reply.message || {}).status === "Verified") checkStatus();
									else inform("Server verification was not confirmed. Check attempt status before retrying.");
								},
								error() {
									setBusy(false);
									inform("Verification outcome is unknown. Check current status; do not retry blindly.");
								},
							});
						});
						return;
					}
					if (state.status === "Verified") {
						inform("Candidate verified. Start the timed session only when the candidate is seated and ready.");
						const start = $("<button type='button' class='btn btn-primary'></button>")
							.text(text("Start supervised timed exam")).appendTo(content);
						start.on("click", () => {
							if (pending) return;
							frappe.confirm(text(
								"Start the timed exam now? The server deadline begins immediately and cannot be paused."
							), () => {
								if (pending) return;
								setBusy(true);
								frappe.call({
									method: "toefl_house.api.deliver_attempt", type: "POST",
									args: {
										request_key: newRequestKey(), attempt: state.attempt,
										expected_version: Number(state.version),
									},
									callback(reply) {
										setBusy(false);
										if ((reply.message || {}).status === "In Progress") reload();
										else inform("Exam start was not confirmed. Check current server status.");
									},
									error() {
										setBusy(false);
										inform("Start outcome is unknown. Check status before any retry.");
									},
								});
							});
						});
						return;
					}
					inform("This attempt is " + (state.status || "unavailable") +
						". No further supervised answers can be entered on this screen.");
				},
				error() {
					setBusy(false);
					inform("Attempt unavailable or access denied. Check the exact ID and assigned Branch.");
				},
			});
		}
		load.on("click", checkStatus);
		attemptField.on("keydown", (event) => {
			if (event.key === "Enter") { event.preventDefault(); checkStatus(); }
		});
		inform("Enter an allocated, verified or in-progress attempt to review its next allowed step.");
	}

	function renderActionPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		ensureStyleSheet();
		if (page.main && page.main.addClass) page.main.addClass("th-page");
		renderHeader(page, surface);

		// Load server-configured vocabularies before rendering action cards so
		// that the first opened dialog can populate selects correctly. Skills
		// are the only config-driven select on the command pages today.
		if (surface.role === "Teaching Scheduler") loadActiveSkills();
		if (surface.role === "Placement Invigilator") mountSupervisedPlacement(page);

		const block = section(page.body, text("Available actions"));
		const grid = $("<div class='th-grid'></div>").appendTo(block);
		surface.commands.forEach((command) => {
			actionCard(
				grid,
				command.label,
				"Opens the guarded command form. No document search is performed.",
				"Open command",
				() => runCommand(command),
			);
		});
	}

	/*
	 * The attention list is the only part of the desk that shows state a person
	 * must act on, so it needs the states a live call can actually produce.
	 * Before this it rendered a single "Loading..." line that stayed on screen
	 * forever if the call failed, which is indistinguishable from a hang.
	 */

	/* DOM counterpart of statusMarkup(). Both exist because msgprint takes an
	 * HTML string while the desk body is built with jQuery; neither trusts the
	 * server's text, so both go through escapeText() or .text(). */
	function statusElement(value) {
		return $("<span class='th-status'></span>")
			.addClass("th-status--" + statusTone(value))
			.text(text(String(value)));
	}

	function alertVariant(state) {
		const tone = statusTone(state);
		if (tone === "danger") return "danger";
		if (tone === "warn") return "warn";
		return "info";
	}

	function renderAttention(attention, snapshot) {
		attention.empty();
		$("<h2 class='th-section-title'></h2>").text(text("System attention")).appendTo(attention);

		const states = $("<p class='th-page-purpose'></p>").appendTo(attention);
		states.append(text("Site mode: "));
		statusElement(snapshot.site_mode || "REFUSED").appendTo(states);
		states.append(text(" · Production authorization: "));
		statusElement(snapshot.production_authorization || "REJECT").appendTo(states);
		states.append(text(" · Deployment: "));
		statusElement(snapshot.deployment_phase || "UNVERIFIED").appendTo(states);

		const items = snapshot.operational_attention || [];
		if (!items.length) {
			const empty = $("<div class='th-empty'></div>").appendTo(attention);
			$("<p class='th-empty-title'></p>").text(text("Nothing needs attention")).appendTo(empty);
			$("<p class='th-empty-body'></p>")
				.text(text("No release attention items were reported for your roles."))
				.appendTo(empty);
			return;
		}
		items.forEach((item) => {
			const alert = $("<div class='th-alert th-alert--" + alertVariant(item.state) + "'></div>")
				.appendTo(attention);
			const body = $("<div></div>").appendTo(alert);
			$("<p class='th-alert-title'></p>")
				.text(text(item.id + " — " + item.state))
				.appendTo(body);
			$("<p class='th-alert-body'></p>").text(text(item.detail)).appendTo(body);
		});
	}

	function renderAdminPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		ensureStyleSheet();
		if (page.main && page.main.addClass) page.main.addClass("th-page");
		renderHeader(page, surface);

		const attention = section(page.body, text("System attention"));
		// A real loading state: the previous version printed static text that
		// never changed if the projection call failed.
		const loading = $("<div class='th-loading'></div>").appendTo(attention);
		$("<span class='th-spinner' aria-hidden='true'></span>").appendTo(loading);
		$("<span></span>").text(text("Loading the role-scoped readiness projection…")).appendTo(loading);
		$("<span class='th-visually-hidden' role='status'></span>")
			.text(text("Loading"))
			.appendTo(loading);

		frappe.call({
			method: "toefl_house.administration.get_control_center_snapshot",
			callback(response) {
				renderAttention(attention, response.message || {});
			},
			error() {
				// Say what failed instead of leaving a spinner that implies the
				// server is merely slow.
				attention.empty();
				$("<h2 class='th-section-title'></h2>").text(text("System attention")).appendTo(attention);
				const alert = $("<div class='th-alert th-alert--danger'></div>").appendTo(attention);
				$("<div></div>").appendTo(alert);
				$("<p class='th-alert-title'></p>")
					.text(text("Readiness projection unavailable"))
					.appendTo(alert);
				$("<p class='th-alert-body'></p>")
					.text(text("The attention list could not be loaded. Existing permissions are unaffected; reload this page to retry."))
					.appendTo(alert);
			},
		});

		const controls = section(page.body, text("Native control routes"));
		$("<p class='th-card-hint'></p>")
			.text(text("These open the native authorities that own identity, role and branch scope. This page creates no parallel record."))
			.appendTo(controls);
		const group = $("<div class='th-route-group'></div>").appendTo(controls);
		const routes = [
			["Users", ["List", "User"]], ["Roles", ["List", "Role"]],
			["User Permissions", ["List", "User Permission"]],
			["Companies", ["List", "Company"]], ["Branches", ["List", "Branch"]],
			["System Settings", ["Form", "System Settings"]],
		];
		routes.forEach(([label, route]) => {
			$("<button type='button' class='btn btn-secondary btn-sm'></button>")
				.text(text(label))
				.on("click", () => frappe.set_route(...route))
				.appendTo(group);
		});
		$("<button type='button' class='btn btn-primary btn-sm'></button>")
			.text(text("Manage TOEFL role assignment"))
			.on("click", manageAdminRole)
			.appendTo(group);
	}

	function renderLandingPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		ensureStyleSheet();
		if (page.main && page.main.addClass) page.main.addClass("th-page");
		renderHeader(page, surface);

		const block = section(page.body, text("Your work areas"));
		const grid = $("<div class='th-grid'></div>").appendTo(block);

		const available = Object.entries(PAGE_SURFACES).filter(([, candidate]) => !candidate.landing && (
			candidate.admin
				? candidate.roles.some((role) => frappe.user.has_role(role))
				: candidate.role && frappe.user.has_role(candidate.role)
		));

		/* An account with no assigned operational role used to get a blank page
		 * with no explanation, which reads as a broken system rather than as a
		 * permissions fact. Name the cause and the remedy instead. */
		if (!available.length) {
			const empty = $("<div class='th-empty'></div>").appendTo(block);
			$("<p class='th-empty-title'></p>")
				.text(text("No command pages for your role"))
				.appendTo(empty);
			/*
			 * Wording matters here and the previous version was wrong. Reaching
			 * this page with no cards does not mean the account has no role: the
			 * auditor roles and Finance Officer have desk workspaces rather than
			 * command pages, and the management roles coordinate rather than
			 * dispatch guarded commands. Saying "no role" would have sent those
			 * users to ask for something they already have.
			 *
			 * Native workspaces stay reachable from the Desk sidebar, so point
			 * there rather than implying the account is unprovisioned.
			 */
			$("<p class='th-empty-body'></p>")
				.text(text("Your role has no guarded command page. Registers and reports remain available from the Desk sidebar workspaces. If you expected a command page here, ask a Course Owner or General Manager to review your role assignment."))
				.appendTo(empty);
			return;
		}

		available.forEach(([name, candidate]) => {
			actionCard(
				grid,
				candidate.title,
				candidate.description || "",
				"Open page",
				() => frappe.set_route(name),
				candidate.admin ? candidate.roles.join(" / ") : candidate.role,
			);
		});

		/*
		 * Role desks (docs/ROLE-DESKS.md). The registry read is
		 * server-authoritative: the client never decides from session data
		 * which desks an account holds. The landing page's own audience is
		 * unchanged and stays pinned to the hosted qualification.
		 */
		const deskBlock = section(page.body, text("Your desks"));
		const deskLoading = $("<div class='th-loading'></div>").appendTo(deskBlock);
		$("<span class='th-spinner' aria-hidden='true'></span>").appendTo(deskLoading);
		$("<span></span>").text(text("Checking which desks your roles can open…")).appendTo(deskLoading);
		frappe.call({
			method: "toefl_house.desk.available",
			callback(response) {
				deskLoading.remove();
				const desks = (response.message || {}).desks || [];
				if (!desks.length) return;
				const group = $("<div class='th-route-group'></div>").appendTo(deskBlock);
				desks.forEach((desk) => {
					$("<button type='button' class='btn btn-primary btn-sm'></button>")
						.text(text(desk.title))
						.on("click", () => frappe.set_route(desk.slug))
						.appendTo(group);
				});
			},
			error() {
				deskLoading.remove();
				/* The command areas above remain fully usable; the desks are
				 * an additional surface, so their failure is a quiet note. */
				$("<p class='th-card-hint'></p>")
					.text(text("Desk availability could not be checked. The command areas above are unaffected."))
					.appendTo(deskBlock);
			},
		});
	}

	toefl_house.command_pages.surfaces = PAGE_SURFACES;
	// Presentation helpers are exported for the static contract suite, in the
	// same spirit as `surfaces` above. They carry no authority: every command
	// still resolves through the whitelisted server endpoints.
	toefl_house.command_pages.resultMarkup = resultMarkup;
	toefl_house.command_pages.statusTone = statusTone;
	toefl_house.command_pages.stylesheet = STYLESHEET;
	toefl_house.command_pages.factLabels = FACT_LABELS;
	Object.entries(PAGE_SURFACES).forEach(([name, surface]) => {
		// Attach only to a native Page wrapper; unopened-page placeholders
		// prevent Frappe's router from constructing the destination page.
		if (!frappe.pages[name] || !frappe.pages[name].tagName) return;
		frappe.pages[name].on_page_load = (wrapper) => {
			if (surface.admin) {
				renderAdminPage(wrapper, surface);
			} else if (surface.landing) {
				renderLandingPage(wrapper, surface);
			} else {
				renderActionPage(wrapper, surface);
			}
		};
	});
})();
