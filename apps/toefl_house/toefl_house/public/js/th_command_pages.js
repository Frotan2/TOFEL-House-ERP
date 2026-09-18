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
			description: "Create or revise synthetic item and configuration drafts. Publication stays with a different command authority.",
			commands: [
				{
					label: "Create item draft",
					method: "toefl_house.api.create_draft",
					dispatches: ["create_draft"],
					fields: [data("family", "Synthetic family", { reqd: 1 }), integer("revision", "Revision", { reqd: 1 }), json("content", "Content JSON", { reqd: 1 })],
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
					fields: [select("config", "Configuration type", CONFIG_TYPES, { reqd: 1 }), data("code", "Synthetic code", { reqd: 1 }), integer("revision", "Revision", { reqd: 1 }), json("definition", "Definition JSON", { reqd: 1 })],
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
			description: "Publish item revisions, govern configuration revisions, and create or allocate synthetic placement cases. Server-side separation checks still apply.",
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
					fields: [data("subject", "Synthetic subject", { reqd: 1 }), data("purpose", "Purpose")],
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
			description: "Run objective scoring for a sealed synthetic attempt. The scoring command, not this page, loads protected key material.",
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
			description: "Release an already finalized synthetic placement decision. The server independently checks scorer, reviewer and finalizer separation.",
			commands: [
				{ label: "Release placement decision", method: "toefl_house.api.release_decision", dispatches: ["release_decision"], fields: [data("attempt", "Attempt", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-admission-officer": {
			role: "Admission Officer",
			title: "TOEFL House Admission Intake",
			description: "Run the thin admission intake and officer transitions over native Student Applicant and Student authorities. The page does not create an enrollment or a billing record.",
			commands: [
				{ label: "Record applicant", method: "toefl_house.admission.record_applicant", dispatches: ["record_applicant"], fields: [data("placement_decision", "Released placement decision", { reqd: 1 }), data("first_name", "Synthetic first name", { reqd: 1 }), data("program", "Program", { reqd: 1 }), data("academic_year", "Academic year", { reqd: 1 })] },
				{ label: "Create admission decision", method: "toefl_house.admission.create_admission", dispatches: ["create_admission"], fields: [data("student_applicant", "Student applicant", { reqd: 1 }), data("placement_decision", "Released placement decision", { reqd: 1 }), data("existing_student", "Existing student")] },
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
			description: "Run the existing admission decision, revocation and native Student conversion commands. Eligibility and transition controls remain server-side.",
			commands: [
				{ label: "Decide admission", method: "toefl_house.admission.decide_admission", dispatches: ["decide_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), select("outcome", "Outcome", ADMISSION_OUTCOMES, { reqd: 1 }), note("reason", "Reason", { reqd: 1 }), note("conditions", "Conditions")] },
				{ label: "Revoke admission", method: "toefl_house.admission.revoke_admission", dispatches: ["revoke_admission"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 }), note("reason", "Reason", { reqd: 1 })] },
				{ label: "Convert applicant", method: "toefl_house.admission.convert_applicant", dispatches: ["convert_applicant"], fields: [data("name", "Admission decision", { reqd: 1 }), integer("expected_version", "Expected version", { reqd: 1 })] },
			],
		},
		"th-enrollment": {
			role: "Enrollment Officer",
			title: "TOEFL House Enrollment",
			description: "Submit one eligible native Program Enrollment through the guarded enrollment command. The server enforces actor separation from the admission decision.",
			commands: [
				{ label: "Enroll in program", method: "toefl_house.enrollment.enroll_in_program", dispatches: ["enroll_in_program"], fields: [data("admission_decision", "Admission decision", { reqd: 1 })] },
			],
		},
		"th-teaching-scheduling": {
			role: "Teaching Scheduler",
			title: "TOEFL House Teaching Scheduling",
			description: "Create native class, session and skill-assignment facts through guarded commands. The page performs no native list or link lookup.",
			commands: [
				{ label: "Create student group", method: "toefl_house.teaching.create_student_group", dispatches: ["create_student_group"], fields: [data("group_name", "Synthetic group name", { reqd: 1 }), data("program", "Program", { reqd: 1 }), data("academic_year", "Academic year", { reqd: 1 }), data("academic_term", "Academic term"), integer("max_strength", "Maximum strength", { reqd: 1 }), date("class_start_date", "Class start date"), date("class_end_date", "Class end date (blank = use level duration policy)"), select("delivery_mode", "Delivery mode", DELIVERY_MODES, { default: "On-site" }), data("branch", "Branch")] },
				{ label: "Transition class", method: "toefl_house.teaching.transition_class", dispatches: ["transition_class"], fields: [data("student_group", "Student group", { reqd: 1 }), select("to_status", "New status", CLASS_TRANSITIONS, { reqd: 1 })] },
				{ label: "Schedule session", method: "toefl_house.teaching.schedule_session", dispatches: ["schedule_session"], fields: [data("student_group", "Student group", { reqd: 1 }), date("schedule_date", "Schedule date", { reqd: 1 }), time("from_time", "From time", { reqd: 1 }), time("to_time", "To time", { reqd: 1 }), data("instructor", "Instructor", { reqd: 1 }), data("room", "Room", { reqd: 1 }), data("course", "Course", { reqd: 1 })] },
				{ label: "Assign teaching skill", method: "toefl_house.teaching.compensation.assign_teaching_skill", dispatches: ["assign_teaching_skill"], fields: [data("student_group", "Student group", { reqd: 1 }), select("skill", "Skill (code)", TEACHING_SKILLS, { reqd: 1, placeholder: "Loading skills…" }), data("instructor", "Instructor", { reqd: 1 }), data("contract", "Instructor contract", { reqd: 1 }), date("effective_start", "Effective start", { reqd: 1 }), date("effective_end", "Effective end"), data("course_schedule", "Course schedule")] },
				{ label: "End teaching assignment", method: "toefl_house.teaching.compensation.end_teaching_assignment", dispatches: ["end_teaching_assignment"], fields: [data("assignment", "Teaching assignment", { reqd: 1 }), date("effective_end", "Effective end", { reqd: 1 })] },
			],
		},
		"th-attendance-recording": {
			role: "Attendance Recorder",
			title: "TOEFL House Attendance Recording",
			description: "Record submitted native Student Attendance facts for a scheduled session through the guarded command. Supply the complete status JSON required by the server.",
			commands: [
				{ label: "Record attendance", method: "toefl_house.teaching.record_attendance", dispatches: ["record_attendance"], fields: [data("course_schedule", "Course schedule", { reqd: 1 }), json("statuses", "Statuses JSON", { reqd: 1 })] },
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
		subject: "Synthetic subject",
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
		rejected: "danger", cancelled: "danger", canceled: "danger",
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

	function renderActionPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		ensureStyleSheet();
		if (page.main && page.main.addClass) page.main.addClass("th-page");
		renderHeader(page, surface);

		// Load server-configured vocabularies before rendering action cards so
		// that the first opened dialog can populate selects correctly. Skills
		// are the only config-driven select on the command pages today.
		if (surface.role === "Teaching Scheduler") loadActiveSkills();

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
		states.append(text("Production: "));
		statusElement(snapshot.production_state || "REJECT").appendTo(states);
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
		 * Role desks (docs/product/ROLE-DESKS.md). The registry read is
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
		frappe.pages[name] = frappe.pages[name] || {};
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
