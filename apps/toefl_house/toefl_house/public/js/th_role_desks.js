/*
 * Role desk client (docs/product/ROLE-DESKS.md).
 *
 * Five daily-work surfaces over one whitelisted read endpoint each. The desks
 * contain no document query, no CRUD and no authority decision of their own:
 * every fact, queue item and guided action arrives from the server projection,
 * which has already applied the desk audience, field allow-lists and bounds.
 * Guided actions pre-fill the EXISTING guarded command dialogs; the server
 * that owns each command remains the only authority.
 *
 * Every server value is escaped through escapeText() before it reaches
 * markup; nothing from the server is ever interpolated raw.
 */
frappe.provide("toefl_house.role_desks");

(() => {
	"use strict";

	const text = (label) => __(label);

	const SURFACES = Object.freeze({
		"th-reception-desk": {
			endpoint: "toefl_house.desk.reception.work",
			title: "TOEFL House Reception Desk",
			description: "Find any person in the admission funnel and see the stage, what is missing and who acts next.",
			search: { endpoint: "toefl_house.desk.reception.lookup", placeholder: "Name or email of the person in front of you" },
		},
		"th-academic-desk": {
			endpoint: "toefl_house.desk.academic.work",
			title: "TOEFL House Academic Desk",
			description: "Placement and admission queues, classes, sessions and teaching assignments that need an academic decision.",
		},
		"th-finance-desk": {
			endpoint: "toefl_house.desk.finance.work",
			title: "TOEFL House Finance Desk",
			description: "Today's collections, outstanding receivables, enrollments awaiting billing and the correction queue.",
		},
		"th-operations-desk": {
			endpoint: "toefl_house.desk.operations.work",
			title: "TOEFL House Operations Desk",
			description: "Cross-role funnel, exceptions and staffing across the whole operation.",
		},
		"th-owner-cockpit": {
			endpoint: "toefl_house.desk.owner.cockpit",
			title: "TOEFL House Owner Cockpit",
			description: "Business state with every definition stated, plus the fail-closed release posture.",
		},
		"th-academic-setup": {
			endpoint: "toefl_house.desk.setup.work",
			title: "TOEFL House Academic Setup",
			description: "Programs, ordered levels, effective-dated durations and progression — the configuration the whole institution runs on.",
		},
	});

	const DESK_REGISTRY = "toefl_house.desk.available";

	/* Same five tones and the same meaning as the command pages: the tone is
	 * presentation only and an unmapped status falls back to neutral. */
	const STATUS_TONES = Object.freeze({
		active: "ok", approved: "ok", completed: "ok", submitted: "ok",
		paid: "ok", settled: "ok", received: "ok", released: "ok",
		finalized: "ok", posted: "ok", "credit note issued": "ok",
		draft: "info", review: "info", open: "info", applied: "info",
		allocated: "info", verified: "info", "in progress": "info",
		sealed: "info", marking: "info", outstanding: "info",
		unpaid: "info", unbilled: "info", student: "info",
		requested: "warn", conditional: "warn", deferred: "warn",
		overdue: "warn", unstaffed: "warn", expired: "warn",
		rejected: "danger", cancelled: "danger", canceled: "danger",
		revoked: "danger", withdrawn: "danger", return: "danger",
	});

	function escapeText(value) {
		if (value === undefined || value === null) return "";
		return String(value)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
	}

	function statusTone(value) {
		const key = String(value === undefined || value === null ? "" : value).trim().toLowerCase();
		return STATUS_TONES[key] || "neutral";
	}

	function statusMarkup(value) {
		if (value === undefined || value === null || value === "") return "";
		const tone = statusTone(value);
		return `<span class="th-status th-status--${tone}">${escapeText(value)}</span>`;
	}

	function dateLabel(value) {
		if (!value) return "";
		const parsed = new Date(value);
		if (Number.isNaN(parsed.getTime())) return escapeText(String(value));
		return escapeText(parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }));
	}

	function newRequestKey() {
		const alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
		const bytes = new Uint32Array(24);
		window.crypto.getRandomValues(bytes);
		return Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
	}

	const STYLESHEET = "/assets/toefl_house/css/th_design_system.css";
	let stylesheetLoaded = false;
	/* Set while a desk is mounted so a guided action can refresh it. */
	let currentReload = null;

	function ensureStyleSheet() {
		if (stylesheetLoaded) return;
		stylesheetLoaded = true;
		if (typeof frappe.require === "function") frappe.require(STYLESHEET);
	}

	function renderHeader(page, surface) {
		const header = $("<div class='th-page-header'></div>").appendTo(page.body);
		$("<p class='th-eyebrow'></p>").text(text("TOEFL House")).appendTo(header);
		$("<h1 class='th-page-title'></h1>").text(text(surface.title)).appendTo(header);
		$("<p class='th-page-purpose'></p>").text(text(surface.description)).appendTo(header);
		$("<p class='th-page-assurance'></p>")
			.text(text("This desk is a read-only projection. Every action it offers opens the existing guarded command; the server validates role, state and separation for each one."))
			.appendTo(header);
		$("<nav class='th-desk-strip' aria-label='Your desks'></nav>").appendTo(header);
	}

	function renderDeskStrip(wrapper, desks) {
		const strip = wrapper.find(".th-desk-strip").empty();
		if (!desks || !desks.length) return;
		$("<span class='th-desk-strip-label'></span>").text(text("Your desks:")).appendTo(strip);
		desks.forEach((desk) => {
			$("<button type='button' class='btn btn-secondary btn-xs th-desk-link'></button>")
				.text(text(desk.title))
				.on("click", () => frappe.set_route(desk.slug))
				.appendTo(strip);
		});
	}

	function sectionShell(parent, title) {
		const block = $("<section class='th-section'></section>").appendTo(parent);
		$("<h2 class='th-section-title'></h2>").text(text(title)).appendTo(block);
		const body = $("<div class='th-section-body'></div>").appendTo(block);
		return body;
	}

	function loadingState(body, message) {
		const loading = $("<div class='th-loading'></div>").appendTo(body);
		$("<span class='th-spinner' aria-hidden='true'></span>").appendTo(loading);
		$("<span></span>").text(text(message || "Loading…")).appendTo(loading);
		$("<span class='th-visually-hidden' role='status'></span>").text(text("Loading")).appendTo(loading);
		return loading;
	}

	function emptyState(body, empty) {
		const emptyBox = $("<div class='th-empty'></div>").appendTo(body);
		$("<p class='th-empty-title'></p>").text(text(empty.title || "Nothing here yet")).appendTo(emptyBox);
		$("<p class='th-empty-body'></p>").text(text(empty.body || "")).appendTo(emptyBox);
	}

	function errorState(body, retry) {
		const alert = $("<div class='th-alert th-alert--danger'></div>").appendTo(body);
		const box = $("<div></div>").appendTo(alert);
		$("<p class='th-alert-title'></p>").text(text("This section could not be loaded")).appendTo(box);
		$("<p class='th-alert-body'></p>")
			.text(text("The server did not return this section. Nothing was changed; use Retry, and if it keeps failing ask an administrator to check the error log."))
			.appendTo(box);
		$("<button type='button' class='btn btn-secondary btn-sm'></button>")
			.text(text("Retry"))
			.on("click", retry)
			.appendTo(box);
	}

	function factsMarkup(facts) {
		const grid = $("<div class='th-fact-grid'></div>");
		(facts || []).forEach((fact) => {
			const tile = $("<div class='th-fact'></div>").appendTo(grid);
			const head = $("<div class='th-fact-head'></div>").appendTo(tile);
			$("<span class='th-fact-value'></span>").text(text(fact.value)).appendTo(head);
			if (fact.owner) $("<span class='th-role-chip'></span>").text(text(fact.owner)).appendTo(head);
			$("<p class='th-fact-label'></p>").text(text(fact.label)).appendTo(tile);
			$("<p class='th-fact-definition'></p>").text(text(fact.definition || "")).appendTo(tile);
		});
		return grid;
	}

	function actionButton(action) {
		if (!action) return null;
		return $("<button type='button' class='btn btn-primary btn-xs th-queue-action'></button>")
			.text(text(action.label))
			.on("click", () => openGuidedAction(action));
	}

	function queueMarkup(items, columns) {
		const table = $("<table class='th-queue'><thead></thead><tbody></tbody></table>");
		const head = $("<tr></tr>").appendTo(table.find("thead"));
		columns.forEach((column) => {
			$("<th scope='col'></th>").text(text(column)).appendTo(head);
		});
		const body = table.find("tbody");
		(items || []).forEach((item) => {
			const row = $("<tr class='th-queue-row'></tr>").appendTo(body);
			const identity = $("<td class='th-queue-identity'></td>").appendTo(row);
			$("<p class='th-queue-person'></p>").text(text(item.person || item.id)).appendTo(identity);
			$("<p class='th-queue-id'></p>").text(text(item.id)).appendTo(identity);
			if (item.detail) $("<p class='th-queue-detail'></p>").text(text(item.detail)).appendTo(identity);
			const state = $("<td class='th-queue-state'></td>").appendTo(row);
			state.append(statusMarkup(item.status));
			if (item.stage) $("<p class='th-queue-stage'></p>").text(text(item.stage)).appendTo(state);
			const next = $("<td class='th-queue-next'></td>").appendTo(row);
			$("<p class='th-queue-next-action'></p>").text(text(item.next || "")).appendTo(next);
			if (item.next_role) $("<span class='th-role-chip'></span>").text(text(item.next_role)).appendTo(next);
			const when = $("<td class='th-queue-when'></td>").appendTo(row);
			if (item.age) $("<p class='th-queue-age'></p>").text(text(item.age)).appendTo(when);
			if (item.waiting_since) $("<p class='th-queue-date'></p>").text(dateLabel(item.waiting_since)).appendTo(when);
			const action = $("<td class='th-queue-action-cell'></td>").appendTo(row);
			const button = actionButton(item.action);
			if (button) button.appendTo(action);
			(item.actions || []).forEach((extra) => {
				const secondary = actionButton(extra);
				if (secondary) secondary.appendTo(action);
			});
		});
		return table;
	}

	function linksMarkup(items) {
		const group = $("<div class='th-route-group'></div>");
		(items || []).forEach((link) => {
			$("<button type='button' class='btn btn-secondary btn-sm'></button>")
				.text(text(link.title || link.slug))
				.on("click", () => frappe.set_route(link.slug))
				.appendTo(group);
		});
		return group;
	}

	function renderSectionBody(body, payload) {
		body.empty();
		const kind = payload.kind;
		if (kind === "facts") {
			body.append(factsMarkup(payload.facts));
		} else if (kind === "links") {
			body.append(linksMarkup(payload.items));
		} else {
			body.append(queueMarkup(payload.items, ["Record", "Status", "Next action", "Waiting", "Act"]));
		}
	}

	/*
	 * Guided actions. The server projection embedded the endpoint and the
	 * prefill values; the dialog only mirrors the command's reviewed
	 * signature, adds a fresh idempotency key and submits to the same
	 * whitelisted, guarded command the command pages use.
	 */
	const ACTION_FIELDS = Object.freeze({
		"toefl_house.admission.review_admission": [
			{ fieldname: "name", label: "Admission decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "expected_version", label: "Expected version", fieldtype: "Int", reqd: 1 },
		],
		"toefl_house.admission.decide_admission": [
			{ fieldname: "name", label: "Admission decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "expected_version", label: "Expected version", fieldtype: "Int", reqd: 1 },
			{ fieldname: "outcome", label: "Outcome", fieldtype: "Select", options: "Approved\nConditional\nDeferred\nRejected", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "conditions", label: "Conditions", fieldtype: "Small Text" },
		],
		"toefl_house.admission.accept_offer": [
			{ fieldname: "name", label: "Admission decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "expected_version", label: "Expected version", fieldtype: "Int", reqd: 1 },
		],
		"toefl_house.admission.convert_applicant": [
			{ fieldname: "name", label: "Admission decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "expected_version", label: "Expected version", fieldtype: "Int", reqd: 1 },
		],
		"toefl_house.admission.create_admission": [
			{ fieldname: "student_applicant", label: "Student applicant", fieldtype: "Data", reqd: 1 },
			{ fieldname: "placement_decision", label: "Released placement decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "existing_student", label: "Existing student", fieldtype: "Data" },
		],
		"toefl_house.admission.record_applicant": [
			{ fieldname: "placement_decision", label: "Released placement decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "first_name", label: "First name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "program", label: "Program", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.enrollment.enroll_in_program": [
			{ fieldname: "admission_decision", label: "Admission decision", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.api.release_decision": [
			{ fieldname: "attempt", label: "Attempt", fieldtype: "Data", reqd: 1 },
			{ fieldname: "expected_version", label: "Expected version", fieldtype: "Int", reqd: 1 },
		],
		"toefl_house.finance.issue_tuition_fees": [
			{ fieldname: "program_enrollment", label: "Program enrollment", fieldtype: "Data", reqd: 1 },
			{ fieldname: "fee_structure", label: "Fee structure", fieldtype: "Data", reqd: 1 },
			{ fieldname: "posting_date", label: "Posting date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "due_date", label: "Due date", fieldtype: "Date", reqd: 1 },
		],
		"toefl_house.finance.corrections.approve_invoice_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.corrections.approve_fees_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.corrections.deny_fees_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.corrections.request_fees_correction": [
			{ fieldname: "fees", label: "Fees", fieldtype: "Data", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Data", reqd: 1 },
			{ fieldname: "requested_amount", label: "Requested amount", fieldtype: "Float", reqd: 1 },
		],
		"toefl_house.academic.create_program": [
			{ fieldname: "code", label: "Program code (stable, e.g. GEN-ENG)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
		],
		"toefl_house.academic.create_level": [
			{ fieldname: "family", label: "Program code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "code", label: "Level code (stable, e.g. PREP-1)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "sequence", label: "Position (1 = first)", fieldtype: "Int", reqd: 1 },
			{ fieldname: "duration_value", label: "Duration", fieldtype: "Float", reqd: 1 },
			{ fieldname: "duration_unit", label: "Unit", fieldtype: "Select", options: "Month\nWeek\nDay", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "next_level", label: "Next level code (optional)", fieldtype: "Data" },
		],
		"toefl_house.academic.set_level_duration": [
			{ fieldname: "level", label: "Level code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "duration_value", label: "New duration", fieldtype: "Float", reqd: 1 },
			{ fieldname: "duration_unit", label: "Unit", fieldtype: "Select", options: "Month\nWeek\nDay", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text" },
		],
		"toefl_house.academic.set_next_level": [
			{ fieldname: "level", label: "Level code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "next_level", label: "Next level code (same program, empty to clear)", fieldtype: "Data" },
		],
		"toefl_house.academic.set_program_status": [
			{ fieldname: "program", label: "Program code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Select", options: "1\n0", reqd: 1, description: "0 retires the program (only once no active level depends on it)." },
		],
		"toefl_house.academic.set_level_status": [
			{ fieldname: "level", label: "Level code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Select", options: "1\n0", reqd: 1, description: "0 retires the level; refused while submitted enrollments still run on it." },
		],
		"toefl_house.academic.create_academic_year": [
			{ fieldname: "name", label: "Academic year name (e.g. 2026-27)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "start_date", label: "Start date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "end_date", label: "End date", fieldtype: "Date", reqd: 1 },
		],
		"toefl_house.academic.create_fee_type": [
			{ fieldname: "name", label: "Fee type name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
		],
		"toefl_house.academic.set_level_fee_component": [
			{ fieldname: "level", label: "Level code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", reqd: 1 },
			{ fieldname: "fee_category", label: "Fee type", fieldtype: "Data", reqd: 1 },
			{ fieldname: "amount", label: "Amount (upsert; same type replaces its amount)", fieldtype: "Float", reqd: 1 },
			{ fieldname: "company", label: "Company (only when several exist)", fieldtype: "Data" },
		],
		"toefl_house.academic.remove_level_fee_component": [
			{ fieldname: "level", label: "Level code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", reqd: 1 },
			{ fieldname: "fee_category", label: "Fee type to remove", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.academic.create_discount_rule": [
			{ fieldname: "code", label: "Rule code (stable, e.g. SCHOLARSHIP-10)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "discount_percentage", label: "Discount percent", fieldtype: "Float", reqd: 1 },
			{ fieldname: "precedence", label: "Precedence (higher wins)", fieldtype: "Int", reqd: 1 },
			{ fieldname: "fee_category", label: "Fee type (optional)", fieldtype: "Data" },
			{ fieldname: "program", label: "Program family (optional)", fieldtype: "Data" },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
		],
		"toefl_house.academic.set_discount_rule_status": [
			{ fieldname: "code", label: "Rule code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Select", options: "1\n0", reqd: 1, description: "0 retires the rule for new charges." },
		],
	});

	/* Client-side courtesy guards for rules the server enforces anyway
	 * (the server stays the authority); they only spare the actor a
	 * round-trip for a mistake the dialog could catch immediately. */
	const ACTION_GUARDS = Object.freeze({
		"toefl_house.admission.decide_admission"(values) {
			if (values.conditions && values.outcome !== "Conditional") {
				return "Conditions are only recorded for Conditional outcomes.";
			}
			return null;
		},
	});

	function resultMessage(label, result) {
		const payload = result && typeof result === "object" ? result : {};
		const status = payload.status !== undefined ? payload.status : "Completed";
		const facts = Object.entries(payload)
			.filter(([, value]) => value !== undefined && value !== null && value !== "" && !Array.isArray(value))
			.slice(0, 8)
			.map(([key, value]) => `<dt>${escapeText(key.replace(/_/g, " "))}</dt><dd>${escapeText(value)}</dd>`)
			.join("");
		const markup = [
			"<div class='th-result'>",
			"<div class='th-result-heading'>",
			statusMarkup(status),
			`<p class='th-result-summary'>${escapeText(label)} ${escapeText(String(status))}.</p>`,
			"</div>",
			facts ? `<dl class='th-facts'>${facts}</dl>` : "",
			"</div>",
		].join("");
		frappe.msgprint({ title: text(label), message: markup, wide: true });
	}

	function openGuidedAction(action) {
		const fields = ACTION_FIELDS[action.endpoint];
		if (!fields) return;
		const dialog = new frappe.ui.Dialog({
			title: text(action.label),
			fields: [{ fieldname: "request_key", label: text("Request key"), fieldtype: "Data", reqd: 1, default: newRequestKey(), description: text("Keep this exact value when retrying the same request.") }, ...fields],
			primary_action_label: text("Run command"),
			primary_action(values) {
				const guard = ACTION_GUARDS[action.endpoint];
				if (guard) {
					const problem = guard(values);
					if (problem) {
						frappe.msgprint({ title: text(action.label), message: text(problem), indicator: "red" });
						return;
					}
				}
				const args = { request_key: values.request_key };
				fields.forEach((field) => { args[field.fieldname] = values[field.fieldname]; });
				frappe.call({
					method: action.endpoint,
					args,
					freeze: true,
					freeze_message: text("Submitting guarded command"),
					callback(response) {
						dialog.hide();
						resultMessage(action.label, response.message);
						if (typeof action.refresh === "function") action.refresh();
						else if (typeof currentReload === "function") currentReload();
					},
				});
			},
		});
		const values = action.args || {};
		fields.forEach((field) => {
			if (values[field.fieldname] !== undefined && values[field.fieldname] !== null && values[field.fieldname] !== "") {
				dialog.set_value(field.fieldname, values[field.fieldname]);
			}
		});
		dialog.show();
	}

	function loadSections(container, payload) {
		container.empty();
		(payload.sections || []).forEach((sectionPayload) => {
			const body = sectionShell(container, sectionPayload.title);
			const items = sectionPayload.items || sectionPayload.facts || [];
			if (!items.length) {
				emptyState(body, sectionPayload.empty || {});
				return;
			}
			renderSectionBody(body, sectionPayload);
		});
	}

	function loadDesk(page, surface, slug) {
		const body = page.body;
		/* Sections live in their own container so a refresh never wipes the
		 * page header, the desk strip or the search bar, and never
		 * accumulates empty containers across reloads. */
		let sections = body.find(".th-desk-sections");
		if (!sections.length) sections = $("<div class='th-desk-sections'></div>").appendTo(body);
		currentReload = () => loadDesk(page, surface, slug);
		const loading = loadingState($("<div class='th-section'></div>").appendTo(sections),
			"Loading your work…");
		frappe.call({
			method: surface.endpoint,
			callback(response) {
				loading.parent().remove();
				loadSections(sections, response.message || {});
			},
			error() {
				loading.parent().remove();
				const block = $("<section class='th-section'></section>").appendTo(sections);
				$("<h2 class='th-section-title'></h2>").text(text("Your work")).appendTo(block);
				const sectionBody = $("<div class='th-section-body'></div>").appendTo(block);
				errorState(sectionBody, () => {
					sectionBody.empty();
					loadingState(sectionBody, "Loading your work…");
					frappe.call({
						method: surface.endpoint,
						callback(response) {
							sectionBody.parent().remove();
							loadSections(sections, response.message || {});
						},
						error() {
							sectionBody.empty();
							/* Last resort: remount the whole desk cleanly. */
							errorState(sectionBody, () => currentReload());
						},
					});
				});
			},
		});
	}

	function mountSearch(page, surface) {
		if (!surface.search) return;
		const block = $("<section class='th-section'></section>").appendTo(page.body);
		$("<h2 class='th-section-title'></h2>").text(text("Find a person")).appendTo(block);
		const body = $("<div class='th-section-body'></div>").appendTo(block);
		const bar = $("<div class='th-search-bar'></div>").appendTo(body);
		$("<div class='th-search-results' aria-live='polite'></div>").appendTo(body);
		const input = $("<input type='search' class='form-control th-search-input' />")
			.attr("placeholder", text(surface.search.placeholder))
			.attr("aria-label", text("Name or email"))
			.appendTo(bar);
		$("<button type='button' class='btn btn-primary btn-sm'></button>")
			.text(text("Search"))
			.on("click", () => runSearch(surface, body, input.val()))
			.appendTo(bar);
		input.on("keydown", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				runSearch(surface, body, input.val());
			}
		});
	}

	function runSearch(surface, body, query) {
		const results = body.find(".th-search-results").empty();
		const text_ = String(query || "").trim();
		if (text_.length < 2) {
			results.append(`<div class='th-alert th-alert--info'><div><p class='th-alert-title'>${escapeText(text("Type more of the name"))}</p><p class='th-alert-body'>${escapeText(text("Enter at least two characters of the person's name or email."))}</p></div></div>`);
			return;
		}
		const loading = loadingState(results, "Searching…");
		frappe.call({
			method: surface.search.endpoint,
			args: { query: text_ },
			callback(response) {
				loading.remove();
				renderSearchResults(results, response.message || {});
			},
			error() {
				loading.remove();
				results.append(`<div class='th-alert th-alert--danger'><div><p class='th-alert-title'>${escapeText(text("Search failed"))}</p><p class='th-alert-body'>${escapeText(text("The lookup could not be completed. Nothing was changed; try again."))}</p></div></div>`);
			},
		});
	}

	function renderSearchResults(results, payload) {
		const applicants = payload.items || [];
		const students = payload.students || [];
		if (!applicants.length && !students.length) {
			results.append(`<div class='th-empty'><p class='th-empty-title'>${escapeText(text("No match found"))}</p><p class='th-empty-body'>${escapeText(text("No open applicant or active student matches that name or email. Check the spelling, or start them through the placement workflow."))}</p></div>`);
			return;
		}
		if (applicants.length) {
			$("<h3 class='th-search-heading'></h3>").text(text("In the admission funnel")).appendTo(results);
			results.append(queueMarkup(applicants, ["Record", "Status", "Next action", "Waiting", "Act"]));
		}
		if (students.length) {
			$("<h3 class='th-search-heading'></h3>").text(text("Enrolled students")).appendTo(results);
			results.append(queueMarkup(students, ["Record", "Status", "Next action", "Waiting", "Act"]));
		}
	}

	Object.entries(SURFACES).forEach(([slug, surface]) => {
		frappe.pages[slug] = frappe.pages[slug] || {};
		frappe.pages[slug].on_page_load = (wrapper) => {
			const page = frappe.ui.make_app_page({ parent: wrapper, title: text(surface.title), single_column: true });
			ensureStyleSheet();
			if (page.main && page.main.addClass) page.main.addClass("th-page");
			renderHeader(page, surface);
			frappe.call({
				method: DESK_REGISTRY,
				callback(response) {
					renderDeskStrip($(page.body), (response.message || {}).desks);
				},
			});
			mountSearch(page, surface);
			loadDesk(page, surface, slug);
		};
	});

	/* Exported for the static contract suite only; carries no authority. */
	toefl_house.role_desks.surfaces = SURFACES;
	toefl_house.role_desks.actionFields = ACTION_FIELDS;
	toefl_house.role_desks.actionGuards = ACTION_GUARDS;
	toefl_house.role_desks.registry = DESK_REGISTRY;
	toefl_house.role_desks.stylesheet = STYLESHEET;
	toefl_house.role_desks.escapeText = escapeText;
	toefl_house.role_desks.statusTone = statusTone;
})();
