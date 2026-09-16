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
	const TEACHING_SKILLS = ["Speaking & Listening", "Writing & Grammar", "Reading & Vocabulary"];
	const COMPENSATION_MODELS = ["Fixed Salary", "Skill-Based", "Hybrid"];

	const PAGE_SURFACES = Object.freeze({
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
				{ label: "Create student group", method: "toefl_house.teaching.create_student_group", dispatches: ["create_student_group"], fields: [data("group_name", "Synthetic group name", { reqd: 1 }), data("program", "Program", { reqd: 1 }), data("academic_year", "Academic year", { reqd: 1 }), data("academic_term", "Academic term"), integer("max_strength", "Maximum strength", { reqd: 1 })] },
				{ label: "Schedule session", method: "toefl_house.teaching.schedule_session", dispatches: ["schedule_session"], fields: [data("student_group", "Student group", { reqd: 1 }), date("schedule_date", "Schedule date", { reqd: 1 }), time("from_time", "From time", { reqd: 1 }), time("to_time", "To time", { reqd: 1 }), data("instructor", "Instructor", { reqd: 1 }), data("room", "Room", { reqd: 1 }), data("course", "Course", { reqd: 1 })] },
				{ label: "Assign teaching skill", method: "toefl_house.teaching.compensation.assign_teaching_skill", dispatches: ["assign_teaching_skill"], fields: [data("student_group", "Student group", { reqd: 1 }), select("skill", "Skill", TEACHING_SKILLS, { reqd: 1 }), data("instructor", "Instructor", { reqd: 1 }), data("contract", "Instructor contract", { reqd: 1 }), date("effective_start", "Effective start", { reqd: 1 }), date("effective_end", "Effective end"), data("course_schedule", "Course schedule")] },
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

	function resultMessage(label, result) {
		const message = $("<pre class='small mb-0'></pre>").text(JSON.stringify(result, null, 2)).prop("outerHTML");
		frappe.msgprint({ title: text(label + " result"), message, wide: true });
	}

	function runCommand(command) {
		const dialog = new frappe.ui.Dialog({
			title: text(command.label),
			fields: [requestKeyField(), ...command.fields],
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

	function addDescription(page, description) {
		$("<p class='text-muted mb-3'></p>").text(text(description)).appendTo(page.body);
		$("<p class='small text-muted mb-3'></p>")
			.text(text("This UI does not grant permission. The server validates the assigned role, request key, state and separation controls for every command."))
			.appendTo(page.body);
	}

	function renderActionPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		addDescription(page, surface.description);
		const actions = $("<div class='row'></div>").appendTo(page.body);
		surface.commands.forEach((command) => {
			const column = $("<div class='col-sm-6 col-lg-4 mb-3'></div>").appendTo(actions);
			const card = $("<div class='border rounded p-3 h-100'></div>").appendTo(column);
			$("<h5 class='mb-2'></h5>").text(text(command.label)).appendTo(card);
			$("<p class='small text-muted'></p>")
				.text(text("Opens the existing guarded command form; no document search is performed."))
				.appendTo(card);
			$("<button type='button' class='btn btn-primary btn-sm'></button>")
				.text(text("Open command"))
				.on("click", () => runCommand(command))
				.appendTo(card);
		});
	}

	function renderLandingPage(wrapper, surface) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
		addDescription(page, surface.description);
		const actions = $("<div class='row'></div>").appendTo(page.body);
		Object.entries(PAGE_SURFACES)
			.filter(([, candidate]) => !candidate.landing && frappe.user.has_role(candidate.role))
			.forEach(([name, candidate]) => {
				const column = $("<div class='col-sm-6 col-lg-4 mb-3'></div>").appendTo(actions);
				const card = $("<div class='border rounded p-3 h-100'></div>").appendTo(column);
				$("<h5 class='mb-2'></h5>").text(text(candidate.title)).appendTo(card);
				$("<p class='small text-muted'></p>").text(text(candidate.role)).appendTo(card);
				$("<button type='button' class='btn btn-primary btn-sm'></button>")
					.text(text("Open page"))
					.on("click", () => frappe.set_route(name))
					.appendTo(card);
			});
	}

	toefl_house.command_pages.surfaces = PAGE_SURFACES;
	Object.entries(PAGE_SURFACES).forEach(([name, surface]) => {
		frappe.pages[name] = frappe.pages[name] || {};
		frappe.pages[name].on_page_load = (wrapper) => {
			if (surface.landing) {
				renderLandingPage(wrapper, surface);
			} else {
				renderActionPage(wrapper, surface);
			}
		};
	});
})();
