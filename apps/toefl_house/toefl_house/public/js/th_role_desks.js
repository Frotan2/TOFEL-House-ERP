/*
 * Role desk client — Executive Analytics Edition (Mission 6).
 *
 * Eight surfaces (seven daily-work desks plus the Configuration map) over
 * one whitelisted read endpoint each. The desks
 * contain no document query, no CRUD and no authority decision of their own:
 * every fact, queue item and guided action arrives from the server projection,
 * which has already applied the desk audience, field allow-lists and bounds.
 * Guided actions pre-fill the EXISTING guarded command dialogs; the server
 * that owns each command remains the only authority.
 *
 * Every server value is escaped through escapeText() before it reaches
 * markup; nothing from the server is ever interpolated raw.
 *
 * Mission 6 enhancements:
 * - Executive analytics: every figure carries explicit definition, permission
 *   scope, source records, and drill-down path.
 * - Authorized comparisons by branch, course, program, level, instructor, period
 *   where underlying data permits — rendered as comparison tables and CSS bar charts.
 * - Clear task queues, actionable alerts, contextual actions, validation messages,
 *   loading skeletons, empty states with next steps, and error recovery with retry.
 * - Consistent professional design system: improved hierarchy, contrast, responsive.
 * - Accessible: keyboard navigation, focus rings, ARIA live regions, reduced motion.
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
			description: "Today's collections, outstanding receivables, enrollments awaiting billing, teaching assignments for native payroll, and the correction queue.",
		},
		"th-operations-desk": {
			endpoint: "toefl_house.desk.operations.work",
			title: "TOEFL House Operations Desk",
			description: "Cross-role funnel, exceptions and staffing across the whole operation.",
		},
		"th-owner-cockpit": {
			endpoint: "toefl_house.desk.owner.cockpit",
			title: "TOEFL House Owner Cockpit",
			description: "Executive overview: enrollments, admissions, attendance, tuition, staffing and operational health — every figure with its definition and drill-down.",
		},
		"th-academic-setup": {
			endpoint: "toefl_house.desk.setup.work",
			title: "TOEFL House Academic Setup",
			description: "Programs, ordered levels, effective-dated durations and progression — the configuration the whole institution runs on.",
		},
		"th-teacher-desk": {
			endpoint: "toefl_house.desk.teacher.work",
			title: "TOEFL House Teacher Desk",
			description: "My classes, today's sessions, attendance, students, academic work and compensation facts — assigned classes only, resolved through the native identity chain.",
		},
		"th-configuration": {
			endpoint: "toefl_house.desk.configuration.work",
			title: "TOEFL House Configuration",
			description: "The configuration map: every configuration domain with its computed readiness, linking to each domain's own surface. Configuration readiness is shown here; production readiness is separate and is never decided here.",
		},
	});

	const DESK_REGISTRY = "toefl_house.desk.available";

	const SOURCE_DOCTYPES = Object.freeze({
		"enrollment records list": "Program Enrollment",
		"enrollment list": "Program Enrollment",
		"admission decision list": "TH Admission Decision",
		"attendance list": "Student Attendance",
		"class schedule list": "Course Schedule",
		"tuition fees list": "Fees",
		"enrollment exits list": "TH Enrollment Exit",
		"correction request list": "TH Correction Request",
	});

	function routeToSource(reference) {
		const route = Object.prototype.hasOwnProperty.call(SOURCE_DOCTYPES, reference) ? ["List", SOURCE_DOCTYPES[reference]] :
			(Array.isArray(reference) ? reference : String(reference || "").split("/"));
		if (["List", "Form", "Tree"].includes(route[0]) && route[1]) {
			// Native list routes are registered only for readable doctypes. A
			// descriptive label is provenance, never a custom Page name. This
			// check only controls navigation; native row permissions still apply.
			if (frappe.model && frappe.model.can_read && frappe.model.can_read(route[1])) {
				frappe.set_route(route);
				return;
			}
			frappe.msgprint({ title: text("Source access required"),
				message: text("Detailed source records require a staff role with permission for") + " " + escapeText(route[1]) + ".",
				indicator: "blue" });
			return;
		}
		if (route.length === 1 && /^th-[a-z0-9-]+$/.test(route[0])) {
			frappe.set_route(route[0]);
			return;
		}
		frappe.msgprint({ title: text("Source reference"),
			message: text("This metric names its source, but no record preview is available from this desk. Open the relevant work desk with an authorized staff account."),
			indicator: "blue" });
	}

	/* Same five tones and the same meaning as the command pages: the tone is
	 * presentation only and an unmapped status falls back to neutral. */
	const STATUS_TONES = Object.freeze({
		active: "ok", approved: "ok", completed: "ok", submitted: "ok",
		paid: "ok", settled: "ok", received: "ok", released: "ok",
		finalized: "ok", posted: "ok", "credit note issued": "ok",
		effective: "ok", validated: "ok", configured: "ok",
		draft: "info", review: "info", open: "info", applied: "info",
		allocated: "info", verified: "info", "in progress": "info",
		sealed: "info", marking: "info", outstanding: "info",
		unpaid: "info", unbilled: "info", student: "info",
		scheduled: "info", planned: "info", defined: "info",
		requested: "warn", conditional: "warn", deferred: "warn",
		overdue: "warn", unstaffed: "warn", expired: "warn",
		pending: "warn", awaiting: "warn", attention: "warn",
		rejected: "danger", cancelled: "danger", canceled: "danger",
		revoked: "danger", withdrawn: "danger", return: "danger",
		failed: "danger", blocked: "danger", error: "danger",
		archived: "neutral", retired: "neutral", empty: "neutral",
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

	function dateTimeLabel(value) {
		if (!value) return "";
		const parsed = new Date(value);
		if (Number.isNaN(parsed.getTime())) return escapeText(String(value));
		return escapeText(parsed.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }));
	}

	function numberLabel(value) {
		if (value === undefined || value === null || value === "") return "0";
		const num = Number(value);
		if (Number.isNaN(num)) return escapeText(String(value));
		return escapeText(num.toLocaleString());
	}

	function currencyLabel(amount, currency) {
		if (amount === undefined || amount === null) return "";
		const num = Number(amount);
		if (Number.isNaN(num)) return escapeText(String(amount));
		const code = currency || "";
		return escapeText(num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (code ? " " + code : ""));
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
			.text(text("Review your work and choose an available action. Each action opens a form; your account's permissions apply when you save."))
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
				.attr("aria-label", text("Open " + desk.title))
				.on("click", () => frappe.set_route(desk.slug))
				.appendTo(strip);
		});
	}

	function sectionShell(parent, title, kind) {
		const block = $("<section class='th-section'></section>").appendTo(parent);
		if (kind) block.attr("data-kind", kind);
		const headerRow = $("<div class='th-section-header-row'></div>").appendTo(block);
		$("<h2 class='th-section-title'></h2>").text(text(title)).appendTo(headerRow);
		const body = $("<div class='th-section-body'></div>").appendTo(block);
		return body;
	}

	function loadingState(body, message) {
		const loading = $("<div class='th-loading' role='status' aria-live='polite'></div>").appendTo(body);
		$("<span class='th-spinner' aria-hidden='true'></span>").appendTo(loading);
		$("<span></span>").text(text(message || "Loading…")).appendTo(loading);
		$("<span class='th-visually-hidden'></span>").text(text("Loading")).appendTo(loading);
		return loading;
	}

	function skeletonGrid(body, count) {
		const grid = $("<div class='th-skeleton-grid' aria-hidden='true'></div>").appendTo(body);
		const n = count || 4;
		for (let i = 0; i < n; i++) {
			$("<div class='th-skeleton'></div>").appendTo(grid);
		}
		return grid;
	}

	function emptyState(body, empty) {
		const emptyBox = $("<div class='th-empty' role='status'></div>").appendTo(body);
		$("<p class='th-empty-title'></p>").text(text(empty.title || "Nothing here yet")).appendTo(emptyBox);
		$("<p class='th-empty-body'></p>").text(text(empty.body || "")).appendTo(emptyBox);
		if (empty.action) {
			const actionBtn = $("<button type='button' class='btn btn-primary btn-sm th-empty-action'></button>")
				.text(text(empty.action.label))
				.on("click", () => {
					if (empty.action.route) frappe.set_route(empty.action.route);
					else if (empty.action.endpoint) openGuidedAction(empty.action);
				})
				.appendTo(emptyBox);
			if (empty.action.description) actionBtn.attr("title", text(empty.action.description));
		}
	}

	function errorState(body, retry) {
		const alert = $("<div class='th-alert th-alert--danger' role='alert'></div>").appendTo(body);
		const box = $("<div></div>").appendTo(alert);
		$("<p class='th-alert-title'></p>").text(text("This section could not be loaded")).appendTo(box);
		$("<p class='th-alert-body'></p>")
			.text(text("The server did not return this section. Nothing was changed; use Retry, and if it keeps failing ask an administrator to check the error log."))
			.appendTo(box);
		$("<button type='button' class='btn btn-secondary btn-sm'></button>")
			.text(text("Retry"))
			.attr("aria-label", text("Retry loading this section"))
			.on("click", retry)
			.appendTo(box);
	}

	function validationMarkup(message, tone) {
		if (!message) return null;
		const t = tone || "info";
		const toneClass = { error: "th-validation--error", warn: "th-validation--warn", info: "th-validation--info", success: "th-validation--success" }[t] || "th-validation--info";
		return $(`<div class='th-validation ${toneClass}' role='status'></div>`).text(text(message));
	}

	/* ------------------------------------------------------------------
	 * Fact rendering — every figure carries explicit definition, scope,
	 * source and drill-down. A number without its definition is not evidence.
	 */

	function factsMarkup(facts) {
		const grid = $("<div class='th-fact-grid'></div>");
		(facts || []).forEach((fact) => {
			const tile = $("<div class='th-fact'></div>").appendTo(grid);
			if (fact.highlight) tile.addClass("th-fact--highlight");
			const head = $("<div class='th-fact-head'></div>").appendTo(tile);
			$("<span class='th-fact-value'></span>").text(text(String(fact.value))).appendTo(head);
			if (fact.trend) {
				const trendClass = fact.trend === "up" ? "th-fact-trend--up" : fact.trend === "down" ? "th-fact-trend--down" : "th-fact-trend--flat";
				const trendIcon = fact.trend === "up" ? "↑" : fact.trend === "down" ? "↓" : "→";
				$("<span class='th-fact-trend " + trendClass + "'></span>").text(trendIcon + " " + text(fact.trend_label || "")).appendTo(head);
			}
			if (fact.owner) $("<span class='th-role-chip'></span>").text(text(fact.owner)).appendTo(head);
			else if (fact.scope) $("<span class='th-fact-scope'></span>").text(text(fact.scope)).appendTo(head);
			$("<p class='th-fact-label'></p>").text(text(fact.label)).appendTo(tile);
			$("<p class='th-fact-definition'></p>").text(text(fact.definition || "")).appendTo(tile);
			if (fact.source) $("<p class='th-fact-source'></p>").text(text("Source: " + fact.source)).appendTo(tile);
			if (fact.scope && fact.owner) $("<span class='th-fact-scope'></span>").text(text(fact.scope)).appendTo(tile);
			if (fact.drill) {
				const drill = $("<a class='th-fact-drill' href='#'></a>").text(text(fact.drill.label || fact.drill.title || "View records"));
				drill.on("click", (e) => {
					e.preventDefault();
					if (fact.drill.route) routeToSource(fact.drill.route);
					else if (fact.drill.slug) routeToSource(fact.drill.slug);
				});
				drill.appendTo(tile);
			}
			if (fact.drill_path) {
				const drill2 = $("<button type='button' class='btn btn-secondary btn-xs' style='margin-top:0.5rem'></button>").text(text("View source records"));
				drill2.on("click", () => {
					if (fact.attendance_source === true) openAttendanceRecords({});
					else if (fact.enrollment_source) openEnrollmentRecords(fact.enrollment_source === "waiting");
					else routeToSource(fact.drill_path);
				});
				drill2.appendTo(tile);
			}
		});
		return grid;
	}

	function analyticsMarkup(payload) {
		// New in Mission 6: analytics kind — richer metric cards with provenance.
		const container = $("<div class='th-analytics-container'></div>");
		if (payload.hero) {
			const hero = $("<div class='th-exec-band'></div>").appendTo(container);
			const heroHeader = $("<div class='th-exec-band-header'></div>").appendTo(hero);
			$("<p class='th-exec-band-title'></p>").text(text(payload.hero.title || "Executive overview")).appendTo(heroHeader);
			if (payload.hero.updated) $("<span class='th-exec-band-updated'></span>").text(text(payload.hero.updated)).appendTo(heroHeader);
			const heroGrid = $("<div class='th-exec-grid'></div>").appendTo(hero);
			(payload.hero.metrics || []).forEach((m) => {
				const cell = $("<div class='th-exec-metric'></div>").appendTo(heroGrid);
				$("<div class='th-exec-metric-value'></div>").text(text(String(m.value))).appendTo(cell);
				$("<div class='th-exec-metric-label'></div>").text(text(m.label)).appendTo(cell);
				if (m.definition) $("<div class='th-exec-metric-definition'></div>").text(text(m.definition)).appendTo(cell);
			});
		}
		if (payload.filters && payload.filters.length) {
			const bar = $("<div class='th-filter-bar' role='toolbar'></div>").appendTo(container);
			$("<span class='th-filter-bar-label'></span>").text(text("Filter by:")).appendTo(bar);
			payload.filters.forEach((f) => {
				const chip = $("<button type='button' class='th-filter-chip'></button>").text(text(f.label));
				if (f.active) chip.addClass("th-filter-chip--active");
				chip.attr("aria-pressed", f.active ? "true" : "false");
				if (f.route) chip.on("click", () => routeToSource(f.route));
				chip.appendTo(bar);
			});
		}
		(payload.groups || []).forEach((group) => {
			const section = $("<div class='th-exec-section'></div>").appendTo(container);
			const header = $("<div class='th-exec-section-header'></div>").appendTo(section);
			const headerText = $("<div></div>").appendTo(header);
			$("<h3 class='th-exec-section-title'></h3>").text(text(group.title)).appendTo(headerText);
			if (group.subtitle) $("<p class='th-exec-section-subtitle'></p>").text(text(group.subtitle)).appendTo(headerText);
			if (group.drill) {
				$("<button type='button' class='th-drill-link'></button>").text(text(group.drill.label || "View all"))
					.on("click", () => routeToSource(group.drill.route || group.drill.slug))
					.appendTo(header);
			}
			const body = $("<div class='th-exec-section-body'></div>").appendTo(section);
			if (group.facts) body.append(factsMarkup(group.facts));
			if (group.metrics) body.append(metricCardsMarkup(group.metrics));
			if (group.comparison) body.append(comparisonMarkup(group.comparison));
			if (group.chart) body.append(barChartMarkup(group.chart));
			if (group.provenance) {
				const prov = $("<div class='th-provenance'></div>").appendTo(body);
				group.provenance.forEach((p) => {
					const item = $("<span class='th-provenance-item'></span>").appendTo(prov);
					if (p.label) $("<strong></strong>").text(text(p.label + ": ")).appendTo(item);
					item.append(document.createTextNode(text(p.value || "")));
				});
			}
			if (group.alerts) {
				group.alerts.forEach((a) => {
					body.append(alertMarkup(a.message || a.body || a.text || "", a.tone || "info", a.title, a.action));
				});
			}
		});
		// Fallback: if payload also carries flat facts (backwards compat)
		if (payload.facts && !payload.groups) {
			container.append(factsMarkup(payload.facts));
		}
		return container;
	}

	function metricCardsMarkup(metrics) {
		const grid = $("<div class='th-analytics-grid'></div>");
		(metrics || []).forEach((m) => {
			const card = $("<div class='th-metric-card'></div>").appendTo(grid);
			if (m.tone === "warn") card.addClass("th-metric-card--warn");
			else if (m.tone === "danger") card.addClass("th-metric-card--danger");
			else if (m.tone === "ok") card.addClass("th-metric-card--ok");
			else if (m.highlight) card.addClass("th-metric-card--highlight");
			const header = $("<div class='th-metric-card-header'></div>").appendTo(card);
			$("<span class='th-metric-card-value'></span>").text(text(String(m.value))).appendTo(header);
			if (m.badge) {
				const tone = statusTone(m.badge);
				$(`<span class='th-status th-status--${tone}'></span>`).text(text(m.badge)).appendTo(header);
			} else if (m.owner) {
				$("<span class='th-role-chip'></span>").text(text(m.owner)).appendTo(header);
			}
			$("<p class='th-metric-card-label'></p>").text(text(m.label)).appendTo(card);
			if (m.definition) $("<p class='th-metric-card-definition'></p>").text(text(m.definition)).appendTo(card);
			const meta = $("<div class='th-metric-card-meta'></div>").appendTo(card);
			if (m.scope) $("<span class='th-metric-card-scope'></span>").text(text(m.scope)).appendTo(meta);
			if (m.source) $("<span class='th-metric-card-source'></span>").text(text("Source: " + m.source)).appendTo(meta);
			if (m.drill) {
				const link = $("<button type='button' class='th-drill-link'></button>").text(text(m.drill.label || "View records"));
				link.on("click", () => routeToSource(m.drill.route || m.drill.slug));
				link.appendTo(meta);
			}
			if (m.drill_path) {
				const link = $("<button type='button' class='th-drill-link'></button>").text(text("View records"));
				link.on("click", () => routeToSource(m.drill_path));
				link.appendTo(meta);
			}
		});
		return grid;
	}

	function comparisonMarkup(comparison) {
		const rows = comparison.rows || comparison.items || [];
		if (!rows.length) return $("<div></div>");
		const table = $("<table class='th-comparison'></table>");
		if (comparison.title) $("<caption></caption>").text(text(comparison.title)).appendTo(table);
		const thead = $("<thead></thead>").appendTo(table);
		const headRow = $("<tr></tr>").appendTo(thead);
		(comparison.columns || ["Name", "Value"]).forEach((col) => {
			$("<th scope='col'></th>").text(text(col)).appendTo(headRow);
		});
		const tbody = $("<tbody></tbody>").appendTo(table);
		const maxVal = Math.max(...rows.map((r) => Number(r.value) || 0), 1);
		rows.forEach((row) => {
			const tr = $("<tr></tr>").appendTo(tbody);
			const labelCell = $("<td></td>").appendTo(tr);
			$("<span></span>").text(text(row.label || row.name || row.person || "")).appendTo(labelCell);
			if (row.bar !== false) {
				const pct = Math.round(((Number(row.value) || 0) / maxVal) * 100);
				const bar = $("<span class='th-comparison-bar'></span>").appendTo(labelCell);
				bar.css("inline-size", pct + "%");
				if (row.tone) bar.addClass("th-comparison-bar--" + row.tone);
			}
			const valCell = $("<td class='th-num'></td>").appendTo(tr);
			valCell.text(text(String(row.value)));
			if (row.drill) {
				const link = $("<button type='button' class='th-drill-link' style='margin-left:0.5rem'></button>").text(text("View"));
				link.on("click", () => {
					if (Object.prototype.hasOwnProperty.call(row.drill, "attendance_group")) openAttendanceRecords({ student_group: row.drill.attendance_group });
					else routeToSource(row.drill.route || row.drill.slug);
				});
				link.appendTo(valCell);
			}
		});
		return table;
	}

	function openAttendanceRecords(args) {
		frappe.call({ method: "toefl_house.desk.academic.attendance_records", args,
			callback(response) {
				const columns = ["name", "student", "student_group", "date", "status", "course_schedule"];
				showAcademicSourceRecords(response, columns, "Attendance source records");
			},
			error() { frappe.msgprint({ title: text("Attendance unavailable"), message: text("Attendance records could not be loaded. Your permissions still apply; try again."), indicator: "red" }); },
		});
	}

	function openEnrollmentRecords(waiting) {
		frappe.call({ method: "toefl_house.desk.academic.enrollment_records", args: { waiting_only: waiting ? 1 : 0 },
			callback(response) { showAcademicSourceRecords(response, ["name", "student", "student_name", "program", "academic_year", "enrollment_date"], waiting ? "Enrollments awaiting a class" : "Enrollment source records"); },
			error() { frappe.msgprint({ title: text("Enrollments unavailable"), message: text("Enrollment records could not be loaded. Your permissions still apply; try again."), indicator: "red" }); },
		});
	}

	function showAcademicSourceRecords(response, columns, title) {
				const result = response.message || {};
				const heading = columns.map((key) => "<th>" + escapeText(key.replace(/_/g, " ")) + "</th>").join("");
				const rows = (result.rows || []).map((row) => "<tr>" + columns.map((key) => "<td>" + escapeText(String(row[key] || "")) + "</td>").join("") + "</tr>").join("");
				const note = result.truncated ? text("This bounded preview has more records; use the class or branch scope to narrow the result.") : text("Submitted source records within your permitted branch scope.");
				const markup = "<p>" + escapeText(note) + "</p>" + (rows ? "<div class='table-responsive'><table class='table'><thead><tr>" + heading + "</tr></thead><tbody>" + rows + "</tbody></table></div>" : "<p>" + escapeText(text("No source records in this scope.")) + "</p>");
				new frappe.ui.Dialog({ title: text(title), fields: [{ fieldname: "records", fieldtype: "HTML", options: markup }] }).show();
	}

	function barChartMarkup(chart) {
		const rows = chart.rows || chart.items || chart.data || [];
		if (!rows.length) return $("<div></div>");
		const container = $("<div class='th-bar-chart'></div>");
		if (chart.title) $("<h4 class='th-bar-chart-title' style='font-size:var(--th-fs-body);font-weight:600;margin:0 0 0.5rem'></h4>").text(text(chart.title)).appendTo(container);
		const maxVal = Math.max(...rows.map((r) => Number(r.value) || 0), 1);
		rows.forEach((row) => {
			const rowEl = $("<div class='th-bar-chart-row'></div>").appendTo(container);
			$("<span class='th-bar-chart-label'></span>").text(text(row.label || row.name || "")).appendTo(rowEl);
			const track = $("<div class='th-bar-chart-track'></div>").appendTo(rowEl);
			const pct = Math.round(((Number(row.value) || 0) / maxVal) * 100);
			const fill = $("<div class='th-bar-chart-fill'></div>").appendTo(track);
			fill.css("inline-size", pct + "%");
			if (row.tone) fill.addClass("th-bar-chart-fill--" + row.tone);
			$("<span class='th-bar-chart-value'></span>").text(text(String(row.value))).appendTo(rowEl);
		});
		if (chart.provenance) {
			const prov = $("<div class='th-provenance'></div>").appendTo(container);
			$("<span class='th-provenance-item'></span>").text(text(chart.provenance)).appendTo(prov);
		}
		return container;
	}

	function alertMarkup(message, tone, title, action) {
		const toneClass = {
			warn: "th-alert--warn", danger: "th-alert--danger", info: "th-alert--info", ok: "th-alert--ok", exec: "th-alert--exec"
		}[tone] || "th-alert--info";
		const alert = $(`<div class='th-alert ${toneClass}' role='alert'></div>`);
		const box = $("<div></div>").appendTo(alert);
		if (title) $("<p class='th-alert-title'></p>").text(text(title)).appendTo(box);
		$("<p class='th-alert-body'></p>").text(text(message)).appendTo(box);
		if (action) {
			const actions = $("<div class='th-alert-actions'></div>").appendTo(box);
			const btn = $("<button type='button' class='btn btn-sm'></button>").text(text(action.label));
			btn.addClass(tone === "danger" ? "btn-danger" : tone === "warn" ? "btn-warning" : "btn-primary");
			btn.on("click", () => {
				if (action.route) frappe.set_route(action.route);
				else if (action.endpoint) openGuidedAction(action);
			});
			btn.appendTo(actions);
			if (action.secondary) {
				const btn2 = $("<button type='button' class='btn btn-secondary btn-sm'></button>").text(text(action.secondary.label));
				btn2.on("click", () => {
					if (action.secondary.route) frappe.set_route(action.secondary.route);
					else if (action.secondary.endpoint) openGuidedAction(action.secondary);
				});
				btn2.appendTo(actions);
			}
		}
		return alert;
	}

	function actionButton(action, variant = "primary") {
		if (!action) return null;
		const buttonClass = variant === "secondary" ? "btn-secondary" : "btn-primary";
		const btn = $(`<button type='button' class='btn ${buttonClass} btn-xs th-queue-action'></button>`)
			.text(text(action.label))
			.attr("aria-label", text(action.label))
			.on("click", () => openGuidedAction(action));
		return btn;
	}

	function queueMarkup(items, columns) {
		const table = $("<table class='th-queue'><thead></thead><tbody></tbody></table>");
		table.attr("aria-label", text("Task queue"));
		const head = $("<tr></tr>").appendTo(table.find("thead"));
		columns.forEach((column) => {
			$("<th scope='col'></th>").text(text(column)).appendTo(head);
		});
		const body = table.find("tbody");
		(items || []).forEach((item) => {
			const row = $("<tr class='th-queue-row'></tr>").appendTo(body);
			if (item.priority === "urgent") row.addClass("th-queue-row--urgent");
			const identity = $("<td class='th-queue-identity'></td>").appendTo(row);
			$("<p class='th-queue-person'></p>").text(text(item.person || item.id)).appendTo(identity);
			$("<p class='th-queue-id'></p>").text(text(item.id)).appendTo(identity);
			if (item.detail) $("<p class='th-queue-detail'></p>").text(text(item.detail)).appendTo(identity);
			if (item.meta) {
				const meta = $("<div class='th-queue-meta'></div>").appendTo(identity);
				(item.meta || []).forEach((badge) => $("<span class='th-queue-badge'></span>").text(text(badge)).appendTo(meta));
			}
			if (item.validation) {
				const tone = item.validation.tone || "info";
				validationMarkup(item.validation.message || item.validation.text, tone).appendTo(identity);
			}
			const state = $("<td class='th-queue-state'></td>").appendTo(row);
			state.append(statusMarkup(item.status));
			if (item.stage) $("<p class='th-queue-stage'></p>").text(text(item.stage)).appendTo(state);
			const next = $("<td class='th-queue-next'></td>").appendTo(row);
			$("<p class='th-queue-next-action'></p>").text(text(item.next || "")).appendTo(next);
			if (item.next_role) $("<span class='th-role-chip'></span>").text(text(item.next_role)).appendTo(next);
			const when = $("<td class='th-queue-when'></td>").appendTo(row);
			if (item.age) $("<p class='th-queue-age'></p>").text(text(item.age)).appendTo(when);
			if (item.waiting_since) $("<p class='th-queue-date'></p>").text(dateLabel(item.waiting_since)).appendTo(when);
			if (item.sla) {
				const slaTone = item.sla.tone || "info";
				$(`<span class='th-status th-status--${slaTone}' style='margin-top:0.25rem'></span>`).text(text(item.sla.label || item.sla.text)).appendTo(when);
			}
			const action = $("<td class='th-queue-action-cell'></td>").appendTo(row);
			const button = actionButton(item.action);
			if (button) button.appendTo(action);
			(item.actions || []).forEach((extra) => {
				const secondary = actionButton(extra, "secondary");
				if (secondary) {
					secondary.appendTo(action);
				}
			});
			if (item.drill) {
				const drillBtn = $("<button type='button' class='btn btn-secondary btn-xs th-queue-action'></button>")
					.text(text(item.drill.label || "View"))
					.on("click", () => routeToSource(item.drill.route || item.drill.slug));
				drillBtn.appendTo(action);
			}
			if (item.drill_path) {
				const drillBtn = $("<button type='button' class='btn btn-secondary btn-xs th-queue-action'></button>")
					.text(text("View record"))
					.on("click", () => routeToSource(item.drill_path));
				drillBtn.appendTo(action);
			}
		});
		return table;
	}

	function linksMarkup(items) {
		const group = $("<div class='th-route-group'></div>");
		(items || []).forEach((link) => {
			$("<button type='button' class='btn btn-secondary btn-sm'></button>")
				.text(text(link.title || link.slug))
				.attr("aria-label", text("Open " + (link.title || link.slug)))
				.on("click", () => routeToSource(link.slug))
				.appendTo(group);
		});
		return group;
	}

	function renderSectionBody(body, payload) {
		body.empty();
		const kind = payload.kind;
		if (kind === "facts") {
			body.append(factsMarkup(payload.facts));
			if (payload.comparison) body.append(comparisonMarkup(payload.comparison));
			if (payload.chart) body.append(barChartMarkup(payload.chart));
			if (payload.alerts) {
				(payload.alerts || []).forEach((a) => {
					body.append(alertMarkup(a.message || a.body || a.text || "", a.tone || "info", a.title, a.action));
				});
			}
			if (payload.provenance) {
				const prov = $("<div class='th-provenance'></div>").appendTo(body);
				(payload.provenance || []).forEach((p) => {
					const item = $("<span class='th-provenance-item'></span>").appendTo(prov);
					if (p.label) $("<strong></strong>").text(text(p.label + ": ")).appendTo(item);
					item.append(document.createTextNode(text(p.value || "")));
				});
			}
		} else if (kind === "analytics") {
			body.append(analyticsMarkup(payload));
		} else if (kind === "comparison") {
			body.append(comparisonMarkup(payload.comparison || payload));
		} else if (kind === "chart") {
			body.append(barChartMarkup(payload.chart || payload));
		} else if (kind === "metrics") {
			body.append(metricCardsMarkup(payload.metrics || payload.items));
		} else if (kind === "alerts") {
			(payload.alerts || payload.items || []).forEach((a) => {
				body.append(alertMarkup(a.message || a.body || a.text || "", a.tone || "info", a.title, a.action));
			});
		} else if (kind === "links") {
			body.append(linksMarkup(payload.items));
		} else {
			body.append(queueMarkup(payload.items, [text("Record"), text("Status"), text("Next action"), text("Waiting"), text("Act")]));
			if (payload.comparison) body.append(comparisonMarkup(payload.comparison));
			if (payload.chart) body.append(barChartMarkup(payload.chart));
		}
		// Inline contextual actions below queue
		if (payload.actions) {
			const actionsBar = $("<div class='th-route-group' style='margin-top:1rem'></div>").appendTo(body);
			payload.actions.forEach((act) => {
				$("<button type='button' class='btn btn-secondary btn-sm'></button>")
					.text(text(act.label))
					.on("click", () => {
						if (act.route) frappe.set_route(act.route);
						else if (act.endpoint) openGuidedAction(act);
					})
					.appendTo(actionsBar);
			});
		}
	}

	/*
	 * Guided actions. The server projection embedded the endpoint and the
	 * prefill values; the dialog only mirrors the command's reviewed
	 * signature, adds a fresh idempotency key and submits to the same
	 * whitelisted, guarded command the command pages use.
	 */
	const OWNER_POLICY_VERSION_FIELDS = [
		{ fieldname: "policy", label: "Owner policy", fieldtype: "Data", reqd: 1, read_only: 1 },
		{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
		{ fieldname: "reason", label: "Change reason", fieldtype: "Small Text", reqd: 1 },
		{ fieldname: "reporting_review_days", label: "Reporting review interval (decision input only; days)", description: "No current report runner consumes this value.", fieldtype: "Int", reqd: 1 },
		{ fieldname: "capacity_target", label: "Class capacity target (decision input only)", description: "Planning target only. Class membership enforcement uses native Student Group max_strength, not this value.", fieldtype: "Int", reqd: 1 },
		{ fieldname: "tax_enabled", label: "Tax enabled (decision input only)", description: "No current tax runtime reads these fields. Native ERPNext tax configuration remains authoritative.", fieldtype: "Select", options: "\nYes\nNo", reqd: 1 },
		{ fieldname: "tax_rate", label: "Tax rate (decision input only; %)", description: "No current tax runtime reads this value. Native ERPNext tax configuration remains authoritative.", fieldtype: "Percent", reqd: 1 },
		{ fieldname: "tax_inclusive", label: "Tax inclusive (decision input only)", description: "No current tax runtime reads this value. Native ERPNext tax configuration remains authoritative.", fieldtype: "Select", options: "\nYes\nNo", reqd: 1 },
		{ fieldname: "transfer_allowed", label: "Transfers allowed (decision input only)", description: "No current transfer command reads this value; it does not enable transfer behavior.", fieldtype: "Select", options: "\nYes\nNo", reqd: 1 },
		{ fieldname: "withdrawal_allowed", label: "Withdrawals allowed (decision input only)", description: "Withdrawals and dismissals are governed by TH Enrollment Exit Policy; this field is not consumed by that resolver.", fieldtype: "Select", options: "\nYes\nNo", reqd: 1 },
		{ fieldname: "calendar_notice_days", label: "Calendar notice (decision input only; days)", description: "No current calendar or lifecycle scheduler enforces this value.", fieldtype: "Int", reqd: 1 },
		{ fieldname: "backup_schedule_time", label: "Nightly backup time (local)", fieldtype: "Time", reqd: 1 },
		{ fieldname: "backup_retention_versions", label: "Backup keep count for deletion mode (minimum 2)", description: "Used only if the Owner explicitly authorizes deletion beyond the count. Preservation mode retains all valid sets and does not rotate them.", fieldtype: "Int", reqd: 1 },
		{ fieldname: "backup_retention_behavior", label: "Backup retention behavior (Owner decision; no default)", description: "Choose explicitly to preserve all valid sets on the separate local drive or authorize deletion of valid older sets on that drive beyond the keep count. Leaving this unset keeps backup and activation fail-closed.", fieldtype: "Select", options: "\nPreserve all valid backup sets\nDelete valid older sets beyond keep count", reqd: 1 },
		{ fieldname: "backup_recovery_public_key", label: "Recovery public key (ASCII-armored; public only)", fieldtype: "Small Text", reqd: 1 },
		{ fieldname: "custody_requirement", label: "Key custody requirement", fieldtype: "Small Text", reqd: 1 },
		{ fieldname: "recovery_quorum", label: "Recovery quorum", fieldtype: "Int", reqd: 1 },
	];
	// Same reviewed numeric weights for first setup and later revisions.
	const ACADEMIC_WEIGHT_FIELDS = Object.freeze([
		{ fieldname: "speaking", label: "Speaking share (%)", fieldtype: "Percent", default: 25, reqd: 1 },
		{ fieldname: "listening", label: "Listening share (%)", fieldtype: "Percent", default: 20, reqd: 1 },
		{ fieldname: "writing", label: "Writing share (%)", fieldtype: "Percent", default: 20, reqd: 1 },
		{ fieldname: "reading", label: "Reading share (%)", fieldtype: "Percent", default: 15, reqd: 1 },
		{ fieldname: "grammar", label: "Grammar share (%)", fieldtype: "Percent", default: 10, reqd: 1 },
		{ fieldname: "vocabulary", label: "Vocabulary share (%)", fieldtype: "Percent", default: 10, reqd: 1,
			description: "All six skill percentages must add up to exactly 100." },
		{ fieldname: "continuous_percent", label: "Continuous assessment share (%)", fieldtype: "Percent", default: 40, reqd: 1,
			description: "Final exam receives the remainder. For 40, the final is 60%. This changes future grading only." },
	]);

	const ACTION_FIELDS = Object.freeze({
		"toefl_house.finance.cashier.reconcile_cashier_day": [
			{ fieldname: "company", label: "Company", fieldtype: "Data", read_only: 1, reqd: 1 },
			{ fieldname: "date", label: "Business day", fieldtype: "Date", read_only: 1, reqd: 1 },
		],
		"toefl_house.setup_presets.native_grading_scale.create_owner_grading_scale": [
			{ fieldname: "grading_scale_name", label: "New grading scale version name", fieldtype: "Data", reqd: 1,
				description: "Use a new unique name for a later version. Historical scales are not overwritten." },
			{ fieldname: "grade_a", label: "A grade — minimum score (%)", fieldtype: "Percent", default: 90, reqd: 1 },
			{ fieldname: "grade_b", label: "B grade — minimum score (%)", fieldtype: "Percent", default: 80, reqd: 1 },
			{ fieldname: "grade_c", label: "C grade — minimum score (%)", fieldtype: "Percent", default: 70, reqd: 1 },
			{ fieldname: "grade_d", label: "D grade / pass — minimum score (%)", fieldtype: "Percent", default: 60, reqd: 1,
				description: "F is automatically assigned to scores below this minimum, down to zero." },
			{ fieldname: "reason", label: "Reason for this grading scale", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.collections.record_reception_collection": [
			{ fieldname: "fees", label: "Tuition bill", fieldtype: "Data", read_only: 1, reqd: 1 },
			{ fieldname: "amount", label: "Cash received", fieldtype: "Currency", reqd: 1, description: "Issue only after counting the cash. The student's balance falls immediately." },
		],
		"toefl_house.finance.collections.accept_reception_handover": [
			{ fieldname: "payment_entries", label: "Selected receipts", fieldtype: "Small Text", hidden: 1, read_only: 1, reqd: 1 },
			{ fieldname: "counted_amount", label: "Cash physically counted", fieldtype: "Currency", reqd: 1 },
		],
		"toefl_house.finance.collections.configure_reception_counter": [
			{ fieldname: "user", label: "Receptionist's sign-in email", fieldtype: "Data", reqd: 1 },
			{ fieldname: "company", label: "Company", fieldtype: "Data", reqd: 1 },
			{ fieldname: "counter_label", label: "Separate counter name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "reason", label: "Assignment reason", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.collections.correct_reception_collection": [
			{ fieldname: "payment_entry", label: "Unhanded receipt number", fieldtype: "Data", reqd: 1 },
			{ fieldname: "fees", label: "Correct tuition bill", fieldtype: "Data", reqd: 1 },
			{ fieldname: "reason", label: "Correction reason", fieldtype: "Small Text", reqd: 1 },
		],
		// This command is ONLY for a separately authorized Attendance
		// Recorder, not for any Instructor. The existing server role gate
		// stays intact until a securely own-session-scoped instructor
		// workflow is delivered and independently tested.
		"toefl_house.teaching.record_instructor_attendance": [
			{ fieldname: "course_schedule", label: "My scheduled session", fieldtype: "Data", read_only: 1, reqd: 1 },
			// Exact native command signature; value is generated from
			// per-student selects below, never manually typed.
			{ fieldname: "statuses", label: "Submitted marks", fieldtype: "Small Text", hidden: 1, read_only: 1 },
		],
		"toefl_house.teaching.record_attendance": [
			{ fieldname: "course_schedule", label: "Scheduled session", fieldtype: "Data", read_only: 1, reqd: 1 },
			{ fieldname: "statuses", label: "Student attendance (JSON)", fieldtype: "Small Text", reqd: 1, description: "Enter a JSON object of Student IDs and Present, Absent or Leave (example: {\"EDU-STU-00001\":\"Present\"}). Only on-roster students are accepted." },
		],
		"toefl_house.operations.owner_configuration.create_owner_operations_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.operations.owner_configuration.set_backup_enabled": [
			{ fieldname: "enabled", label: "Backup On / Off", description: "Off stops future TOEFL House backup runs without deleting existing backup files. On still requires the verified backup configuration and separate recovery disk.", fieldtype: "Check" },
		],
		"toefl_house.operations.owner_configuration.set_owner_operations_policy_version": OWNER_POLICY_VERSION_FIELDS,
		"toefl_house.operations.owner_configuration.validate_owner_operations_policy": [
			{ fieldname: "policy", label: "Owner policy", fieldtype: "Data", reqd: 1, read_only: 1 },
		],
		"toefl_house.operations.owner_configuration.set_owner_operations_policy_status": [
			{ fieldname: "policy", label: "Owner policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],

		"toefl_house.academic.catalog_linkage.create_catalog_linkage_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.catalog_linkage.set_catalog_linkage_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "enforcement", label: "Enforcement", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.academic.catalog_linkage.set_catalog_linkage_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.admission.policies.create_returning_student_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.admission.policies.set_returning_student_policy_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "mode", label: "Mode", fieldtype: "Select", options: "placement_per_term", reqd: 1 },
		],
		"toefl_house.admission.policies.set_returning_student_policy_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.enrollment.exits.create_enrollment_exit_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.enrollment.exits.set_enrollment_exit_policy_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "approver_role", label: "Approver role", fieldtype: "Link", options: "Role", reqd: 1 },
			{ fieldname: "superseding_owner_decision_reference", label: "Superseding Owner decision reference (D5-SUPERSESSION:<record-id>)", description: "Must resolve to a DECIDED Course Owner record in the immutable release ledger, explicitly supersede D5, name toefl_house.enrollment.exits, and authorize both withdrawal and dismissal. A reason or well-formed fabricated ID cannot activate exits.", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.enrollment.exits.set_enrollment_exit_policy_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.finance.installments.issue_tuition_installment_plan": [
			{ fieldname: "program_enrollment", label: "Program enrollment", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "fee_structure", label: "Fee plan", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "posting_date", label: "Posting date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "first_due_date", label: "First due date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "installments", label: "Installments (owner policy)", fieldtype: "Int", reqd: 1 },
			{ fieldname: "shares", label: "Contractual shares % (optional, owner policy)", fieldtype: "Small Text", description: "Leave empty for an equal split. Negotiated unequal installments such as 60,40 must total 100% and are refused unless the governing Owner billing policy authorizes them. The plan always totals the full net tuition." },
		],
		"toefl_house.finance.cashier.reconcile_cashier_day": [
			{ fieldname: "company", label: "Company", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "date", label: "Business date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "counts", label: "Counted drawers", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.policies.create_billing_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.policies.set_billing_policy_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "max_backdate_days", label: "Maximum days allowed for earlier billing", fieldtype: "Int", default: 0, reqd: 1 },
			{ fieldname: "max_future_days", label: "Maximum days allowed for future billing", fieldtype: "Int", default: 0, reqd: 1 },
			{ fieldname: "placement_fee_timing", label: "When to charge placement fee", fieldtype: "Select",
				options: "any\nAllocated\nVerified\nIn Progress\nSealed\nMarking\nReview\nFinalized\nreleased", default: "any", reqd: 1,
				description: "any = charge when a new placement case begins; released = after its decision is released." },
			{ fieldname: "installments_allowed", label: "Installments allowed", fieldtype: "Check" },
			{ fieldname: "max_installments", label: "Maximum tuition installments", fieldtype: "Int", default: 2, reqd: 1 },
			{ fieldname: "installment_interval_days", label: "Days between payments (only if not monthly)", fieldtype: "Int", default: 0, reqd: 1 },
			{ fieldname: "installment_cadence", label: "Installment schedule", fieldtype: "Select", options: "Solar Hijri Month\nDays", default: "Solar Hijri Month", reqd: 1, description: "Solar Hijri Month follows the Afghan calendar; it is not a guessed 30-day interval." },
			{ fieldname: "payment_grace_days", label: "Payment grace period (days)", fieldtype: "Int", default: 5, reqd: 1, description: "Only for Solar Hijri Month; valid range 0 to 15." },
			{ fieldname: "installment_due_day", label: "Due day of Afghan month", fieldtype: "Select", options: "1\n25", default: "1", reqd: 1, description: "1 = first day of the Afghan month; 25 = 25th. The server checks that this is compatible with the selected billing policy." },
			{ fieldname: "allow_unequal_installments", label: "Allow unequal installments", fieldtype: "Check", default: 0, description: "Authorizes contractual unequal shares such as 60/40 that must still total the full net tuition. Off by default." },
		],
		"toefl_house.finance.policies.set_billing_policy_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.teaching.policies.create_roster_change_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.teaching.policies.set_roster_change_policy_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "changes_allowed_until", label: "Changes allowed until", fieldtype: "Date", reqd: 1 },
		],
		"toefl_house.teaching.policies.set_roster_change_policy_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.teaching.attendance_corrections.create_attendance_correction_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.teaching.attendance_corrections.set_attendance_correction_policy_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "approver_role", label: "Approver role", fieldtype: "Link", options: "Role", reqd: 1 },
			{ fieldname: "correction_window_days", label: "Correction window days", fieldtype: "Int", reqd: 1 },
		],
		"toefl_house.teaching.attendance_corrections.set_attendance_correction_policy_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],
		"toefl_house.teaching.adjustment_posting.create_adjustment_posting_policy": [
			{ fieldname: "code", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Policy title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.teaching.adjustment_posting.set_adjustment_posting_version": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "orphan_posting", label: "Orphan posting", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.teaching.adjustment_posting.set_adjustment_posting_status": [
			{ fieldname: "policy", label: "Policy", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Check" },
		],

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
				{ fieldname: "program", label: "Program", fieldtype: "Data", description: "Returning journeys only; blank inherits the applicant record." },
				{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", description: "Returning journeys only; blank inherits the applicant record." },
				{ fieldname: "academic_term", label: "Academic term", fieldtype: "Data", description: "Returning journeys only; blank inherits the applicant record." },
			],
		"toefl_house.admission.record_applicant": [
			{ fieldname: "placement_decision", label: "Released placement decision", fieldtype: "Data", reqd: 1 },
			{ fieldname: "first_name", label: "First name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "program", label: "Program", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_year", label: "Choose the academic year", fieldtype: "Link", options: "Academic Year", reqd: 1 },
			{ fieldname: "branch", label: "Branch", fieldtype: "Data", description: "Blank: the recording officer's own branch." },
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
		"toefl_house.finance.corrections.configure_correction_policy": [
			{ fieldname: "approver_role", label: "Approver role", fieldtype: "Link", options: "Role", reqd: 1 },
			{ fieldname: "correction_window_days", label: "Correction window (days)", fieldtype: "Int", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Change reason", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.corrections.set_correction_policy_status": [
			{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Active\nRetired", reqd: 1 },
		],
		"toefl_house.finance.corrections.validate_correction_policy": [],
		"toefl_house.finance.corrections.approve_invoice_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.corrections.approve_fees_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.corrections.deny_fees_correction": [
			{ fieldname: "request", label: "Correction request", fieldtype: "Data", reqd: 1 },
		],
		"toefl_house.finance.tuition_refund_commands.request_tuition_refund": [
			{ fieldname: "student", label: "Student", fieldtype: "Link", options: "Student", reqd: 1 },
			{ fieldname: "company", label: "Company", fieldtype: "Link", options: "Company", reqd: 1 },
			{ fieldname: "fees", label: "Original tuition bill", fieldtype: "Data", reqd: 1 },
			{ fieldname: "requested_amount", label: "Amount to return (AFN, maximum two decimal places)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "reason", label: "Reason for this case", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "evidence", label: "Supporting evidence", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.tuition_refund_commands.approve_tuition_refund": [
			{ fieldname: "request", label: "Refund case", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "evidence", label: "General Manager approval evidence", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.finance.tuition_refund_commands.deny_tuition_refund": [
			{ fieldname: "request", label: "Refund case", fieldtype: "Data", reqd: 1, read_only: 1 },
		],
		"toefl_house.finance.tuition_refund_commands.pay_tuition_refund": [
			{ fieldname: "request", label: "Approved refund case", fieldtype: "Data", reqd: 1, read_only: 1 },
		],
		"toefl_house.finance.tuition_refund_commands.void_tuition_refund": [
			{ fieldname: "request", label: "Unpaid approved refund case", fieldtype: "Data", reqd: 1, read_only: 1 },
			{ fieldname: "reason", label: "Reason for withdrawing this approval", fieldtype: "Small Text", reqd: 1 },
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
			{ fieldname: "family", label: "Choose the program", fieldtype: "Select", options: "__owner_choice:program__", reqd: 1 },
			{ fieldname: "code", label: "Level code (stable, e.g. PREP-1)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "sequence", label: "Position (1 = first)", fieldtype: "Int", reqd: 1 },
			{ fieldname: "duration_value", label: "Duration", fieldtype: "Float", reqd: 1 },
			{ fieldname: "duration_unit", label: "Unit", fieldtype: "Select", options: "Month\nWeek\nDay\nSolar Hijri Month", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from", fieldtype: "Date", reqd: 1 },
			{ fieldname: "next_level", label: "Next level code (optional)", fieldtype: "Data" },
		],
		"toefl_house.academic.set_level_duration": [
			{ fieldname: "level", label: "Choose the level", fieldtype: "Link", options: "TH Program Level", reqd: 1 },
			{ fieldname: "duration_value", label: "New duration", fieldtype: "Float", reqd: 1 },
			{ fieldname: "duration_unit", label: "Unit", fieldtype: "Select", options: "Month\nWeek\nDay\nSolar Hijri Month", reqd: 1 },
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
		"toefl_house.setup_presets.owner_policy_forms.revise_grading_weights": [
			{ fieldname: "policy", label: "Academic grading policy", fieldtype: "Data", read_only: 1, reqd: 1 },
			...ACADEMIC_WEIGHT_FIELDS,
			{ fieldname: "effective_from", label: "Effective date for these new weights", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason for changing skill shares", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.setup_presets.owner_policy_forms.configure_initial_assessment": [
			{ fieldname: "policy", label: "Academic grading policy", fieldtype: "Data", read_only: 1, reqd: 1 },
			{ fieldname: "grading_scale", label: "Grade scale (choose the A–F scale)", fieldtype: "Select", options: "__owner_choice:grading_scale__", reqd: 1,
				description: "First create your grading scale with the A, B, C and D numeric form." },
			{ fieldname: "passing_score", label: "Minimum passing mark (%)", fieldtype: "Percent", default: 60, reqd: 1 },
			{ fieldname: "retake_wait_days", label: "Minimum days before one failed-exam retake", fieldtype: "Int", default: 7, reqd: 1 },
			...ACADEMIC_WEIGHT_FIELDS,
			{ fieldname: "effective_from", label: "Start date for this policy", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Why this policy is being approved", fieldtype: "Small Text", reqd: 1,
				description: "One original exam and one retake are permitted. The higher valid score is retained. Academic Manager approves promotion." },
		],
		"toefl_house.academic.create_assessment_policy": [
			{ fieldname: "family", label: "Choose an active program", fieldtype: "Select", options: "__owner_choice:program__", reqd: 1 },
			{ fieldname: "code", label: "Policy code (stable)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
		],
		"toefl_house.academic.create_room": [
			{ fieldname: "room_name", label: "Room name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "seating_capacity", label: "Maximum students", fieldtype: "Int", reqd: 1 },
			{ fieldname: "reason", label: "Reason", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_policy_version": [
			{ fieldname: "policy", label: "Grading policy", fieldtype: "Data", read_only: 1, reqd: 1 },
			{ fieldname: "passing_score", label: "New passing mark (%) — leave blank to keep current", fieldtype: "Percent" },
			{ fieldname: "retake_wait_days", label: "New retake wait (days) — leave blank to keep current", fieldtype: "Int" },
			{ fieldname: "effective_from", label: "Date when the revised values take effect", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Why the grading rule is changing", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "grading_scale", label: "New grade scale (optional; blank keeps the old one)", fieldtype: "Select", options: "__owner_choice:grading_scale__" },
		],
		"toefl_house.academic.set_assessment_components": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "components", label: "Components (JSON list of code, title, maximum score, optional native criteria; empty list withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_weights": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "weights", label: "Weights (JSON list of component code with a non-negative number; empty list withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_pass_rules": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "pass_rules", label: "Pass rules (JSON object with per-component and overall minima, each a percent or a grade code; empty object withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_rubrics": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "rubrics", label: "Rubrics (JSON list of code, title, optional component, required evidence list, optional rating levels; empty list withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_progression": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "progression", label: "Progression (JSON object with required evidence list and target level; empty object withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_retakes": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "retakes", label: "Retakes (JSON object with attempt limit, wait, scope and governing attempt, all explicit; empty object withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_mapping": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "mapping", label: "Level mapping (JSON object with the governed level codes; empty object withdraws)", fieldtype: "Small Text", reqd: 1 },
		],
		"toefl_house.academic.set_assessment_policy_status": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Select", options: "1\n0", reqd: 1, description: "0 retires the policy; it governs nothing while retired." },
		],
		"toefl_house.academic.validate_assessment_policy": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
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
			{ fieldname: "level", label: "Choose the level", fieldtype: "Select", options: "__owner_choice:level__", reqd: 1 },
			{ fieldname: "academic_year", label: "Choose the academic year", fieldtype: "Select", options: "__owner_choice:academic_year__", reqd: 1 },
			{ fieldname: "fee_category", label: "Choose the fee type", fieldtype: "Select", options: "__owner_choice:fee_category__", reqd: 1 },
			{ fieldname: "amount", label: "Tuition amount (AFN)", fieldtype: "Currency", reqd: 1, description: "This is the full semester amount, not a second monthly bill. Changing it only affects future bills." },
			{ fieldname: "company", label: "Company (optional)", fieldtype: "Select", options: "__owner_choice:company__" },
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
			{ fieldname: "description", label: "Description / Owner justification (required for 100% waiver)", fieldtype: "Small Text" },
			{ fieldname: "student", label: "Eligible Student (required for 100% waiver)", fieldtype: "Link", options: "Student" },
		],
		"toefl_house.academic.set_discount_rule_status": [
			{ fieldname: "code", label: "Rule code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "active", label: "Active", fieldtype: "Select", options: "1\n0", reqd: 1, description: "0 retires the rule for new charges." },
		],
		/* U1: the class-lifecycle commands, mirrored from the teaching module
		 * exactly as its command pages run them — same guards, same rules. */
		"toefl_house.teaching.create_student_group": [
			{ fieldname: "group_name", label: "Class name", fieldtype: "Data", reqd: 1 },
			{ fieldname: "program", label: "Program (level)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", reqd: 1 },
			{ fieldname: "academic_term", label: "Academic term (optional)", fieldtype: "Data" },
			{ fieldname: "max_strength", label: "Capacity", fieldtype: "Int", reqd: 1 },
			{ fieldname: "class_start_date", label: "First day", fieldtype: "Date" },
			{ fieldname: "class_end_date", label: "Last day (blank = from the level's duration)", fieldtype: "Date" },
			{ fieldname: "delivery_mode", label: "Delivery mode", fieldtype: "Select", options: "On-site\nOnline\nHybrid", default: "On-site" },
			{ fieldname: "branch", label: "Branch (optional)", fieldtype: "Data" },
			{ fieldname: "students", label: "Student IDs (optional, comma-separated)", fieldtype: "Data",
			  description: "Use submitted enrollment students only. Blank selects the full intake." },
		],
		"toefl_house.teaching.add_class_member": [
			{ fieldname: "student_group", label: "Class", fieldtype: "Data", reqd: 1 },
			{ fieldname: "student", label: "Student ID", fieldtype: "Data", reqd: 1 },
			{ fieldname: "override", label: "Capacity override (only when full)", fieldtype: "Data" },
		],
		"toefl_house.teaching.transition_class": [
			{ fieldname: "student_group", label: "Class", fieldtype: "Data", reqd: 1 },
			{ fieldname: "to_status", label: "New status", fieldtype: "Select", options: "Active\nCompleted\nCancelled", reqd: 1 },
		],
		"toefl_house.teaching.schedule_session": [
			{ fieldname: "student_group", label: "Class", fieldtype: "Data", reqd: 1 },
			{ fieldname: "schedule_date", label: "Date", fieldtype: "Date", reqd: 1 },
			{ fieldname: "from_time", label: "Start time", fieldtype: "Time", reqd: 1 },
			{ fieldname: "to_time", label: "End time", fieldtype: "Time", reqd: 1 },
			{ fieldname: "instructor", label: "Instructor", fieldtype: "Data", reqd: 1 },
			{ fieldname: "room", label: "Room", fieldtype: "Data", reqd: 1 },
			{ fieldname: "course", label: "Course", fieldtype: "Data", reqd: 1 },
		],
		/* The Finance Officer's compensation commands (P1-6): the finance
		 * desk's Teaching compensation section prefills these dialogs from
		 * the native contract/instructor facts. The dialogs mirror the
		 * reviewed command signatures; the server validates everything.
		 * Skill terms and adjustments are structured owner-entered JSON
		 * (max 10 rows each); the default empty list is what a Fixed Salary
		 * contract records. */
		"toefl_house.teaching.compensation.create_teaching_contract": [
			{ fieldname: "instructor", label: "Instructor", fieldtype: "Data", reqd: 1 },
			{ fieldname: "employee", label: "Employee (payroll record)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "compensation_model", label: "Compensation model", fieldtype: "Select", options: "Fixed Salary\nSkill-Based\nHybrid", reqd: 1 },
			{ fieldname: "assignment_basis", label: "Assignment basis", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "payment_frequency", label: "Payment frequency", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_start", label: "Effective start", fieldtype: "Date", reqd: 1 },
			{ fieldname: "effective_end", label: "Effective end (blank = open)", fieldtype: "Date" },
			{ fieldname: "conditions", label: "Conditions", fieldtype: "Small Text" },
			{ fieldname: "skill_terms", label: "Skill terms (JSON list: skill, unit_of_payment, rate, payable_quantity, optional minimum_amount/maximum_amount; required for Skill-Based and Hybrid, empty list for Fixed Salary)", fieldtype: "Small Text", default: "[]" },
			{ fieldname: "adjustments", label: "Adjustments (JSON list: adjustment_type Bonus or Deduction, amount, effective_date, approver, reason)", fieldtype: "Small Text", default: "[]" },
			{ fieldname: "earning_basis", label: "Skill earning basis", fieldtype: "Select", options: "One-off\nSolar Hijri Monthly", default: "One-off", reqd: 1 },
		],
		"toefl_house.teaching.compensation.revise_teaching_contract": [
			{ fieldname: "contract", label: "Instructor contract", fieldtype: "Data", reqd: 1 },
			{ fieldname: "compensation_model", label: "Compensation model", fieldtype: "Select", options: "Fixed Salary\nSkill-Based\nHybrid", reqd: 1 },
			{ fieldname: "assignment_basis", label: "Assignment basis", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "payment_frequency", label: "Payment frequency", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_start", label: "Effective start (must start after the replaced contract)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "effective_end", label: "Effective end (blank = open)", fieldtype: "Date" },
			{ fieldname: "conditions", label: "Conditions", fieldtype: "Small Text" },
			{ fieldname: "skill_terms", label: "Skill terms (JSON list: skill, unit_of_payment, rate, payable_quantity, optional minimum_amount/maximum_amount; required for Skill-Based and Hybrid, empty list for Fixed Salary)", fieldtype: "Small Text", default: "[]" },
			{ fieldname: "adjustments", label: "Adjustments (JSON list: adjustment_type Bonus or Deduction, amount, effective_date, approver, reason)", fieldtype: "Small Text", default: "[]" },
			{ fieldname: "earning_basis", label: "Skill earning basis (blank keeps the existing basis)", fieldtype: "Select", options: "\nOne-off\nSolar Hijri Monthly" },
		],
		"toefl_house.teaching.compensation.calculate_teaching_compensation": [
			{ fieldname: "period_start", label: "Period start", fieldtype: "Date", reqd: 1 },
			{ fieldname: "period_end", label: "Period end", fieldtype: "Date", reqd: 1 },
			{ fieldname: "company", label: "Company", fieldtype: "Data", reqd: 1 },
			{ fieldname: "salary_component", label: "Salary component (earning)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "deduction_component", label: "Deduction component (optional)", fieldtype: "Data" },
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
		if (payload.receipt) {
			// Command receipts are immutable snapshots. A retry after an
			// Owner amendment must not print the old saved "Issued" status.
			loadCollectionReceipt(payload.receipt.number, true);
			return;
		}
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

	function loadCollectionReceipt(number, postingSaved = false) {
		const failed = () => frappe.msgprint({ title: text("Numbered cash receipt"), indicator: "red",
			message: text(postingSaved
				? "The posting was saved, but the current receipt could not be loaded. Retry with the same request reference or open the receipt from your desk."
				: "The current receipt could not be loaded. Check your access and try again.") });
		frappe.call({ method: "toefl_house.finance.collections.get_collection_receipt", type: "GET",
			args: { payment_entry: number },
			callback(response) {
				const receipt = response.message;
				if (!receipt || receipt.number !== number || !["Issued", "Void"].includes(receipt.status)) { failed(); return; }
				showCollectionReceipt(receipt);
			}, error: failed });
	}

	function showCollectionReceipt(receipt) {
		const keys = ["number", "status", "date", "student_name", "student", "fees", "company", "amount", "currency", "collector", "counter_account", "handover", "replaces"];
		const facts = keys.filter((key) => receipt[key] !== null && receipt[key] !== undefined && receipt[key] !== "")
			.map((key) => `<dt>${escapeText(key.replace(/_/g, " "))}</dt><dd>${escapeText(receipt[key])}</dd>`).join("");
		const heading = (receipt.status === "Void" ? "VOID RECEIPT — " : "") +
			(receipt.synthetic ? "SYNTHETIC TEST RECEIPT" : "TOEFL House cash receipt");
		const markup = `<h2>${escapeText(heading)}</h2><dl>${facts}</dl>`;
		const dialog = new frappe.ui.Dialog({ title: text("Numbered cash receipt"),
			fields: [{ fieldname: "receipt", fieldtype: "HTML", options: markup }],
			primary_action_label: text(receipt.status === "Void" ? "Print void record" : "Print receipt"),
			primary_action() {
				const paper = window.open("about:blank", "_blank");
				if (!paper) { frappe.msgprint(text("Allow the print window and try again.")); return; }
				paper.opener = null;
				paper.document.write(`<!doctype html><html><head><title>Cash receipt</title><style>body{font:16px sans-serif;margin:32px}dt{font-weight:bold;margin-top:12px}dd{margin-left:0}</style></head><body>${markup}</body></html>`);
				paper.document.close();
				paper.focus();
				paper.print();
			},
		});
		dialog.show();
	}

	function openGuidedAction(action) {
		if (action.endpoint === "toefl_house.finance.collections.get_collection_receipt") {
			loadCollectionReceipt(action.args.payment_entry);
			return;
		}
		const ownAttendance = action.endpoint === "toefl_house.teaching.record_instructor_attendance";
		const cashClose = action.endpoint === "toefl_house.finance.cashier.reconcile_cashier_day";
		let fields = ACTION_FIELDS[action.endpoint];
		if (cashClose) {
			const drawers = action.args && action.args.drawers;
			const accounts = Array.isArray(drawers) ? drawers.map((row) => row && row.account) : [];
			if (!accounts.length || accounts.length > 25 ||
				accounts.some((name) => typeof name !== "string" || !name || name.length > 140) ||
				new Set(accounts).size !== accounts.length) {
				frappe.msgprint(text("Cash drawer list is invalid. Refresh the Finance Desk; no close was recorded."));
				return;
			}
			fields = [...fields, ...drawers.flatMap((drawer, index) => [
				{ fieldname: "drawer_name_" + index, label: "Count drawer " + (index + 1),
					fieldtype: "Data", read_only: 1, default: drawer.account },
				{ fieldname: "drawer_expected_" + index, label: "Native ledger balance (AFN, view only)",
					fieldtype: "Currency", read_only: 1, default: drawer.expected },
				{ fieldname: "drawer_counted_" + index, label: "Actual counted amount (AFN) — use 0 if empty",
					fieldtype: "Currency", description: "Enter your own physical count, never an assumed ledger amount." },
				{ fieldname: "drawer_note_" + index, label: "Explanation of a difference",
					fieldtype: "Small Text" },
			])];
		}
		if (ownAttendance) {
			// The roster is a teacher-only server projection of the selected
			// session. Never use it as authorization: the POST command
			// rechecks native Employee/Instructor, active assignment,
			// schedule and roster under its transaction lock.
			const roster = action.args && action.args.roster;
			const students = Array.isArray(roster) ? roster : [];
			const ids = students.map((item) => item && item.student);
			if (!students.length || students.length > 100 ||
					ids.some((id) => typeof id !== "string" || !id || id.length > 140) ||
					new Set(ids).size !== ids.length) {
				frappe.msgprint({ title: text(action.label),
					message: text("This session has no valid active roster. No marks were submitted. Ask Academic to check the class roster."),
					indicator: "red" });
				return;
			}
			// The legacy raw-status field is never shown or required.
			// Only these per-student dropdowns produce the server payload.
			fields = [...fields.filter((field) => field.fieldname !== "statuses"),
				...students.map((item, index) => ({
				fieldname: "mark_" + index,
				label: text(item.name || item.student) + " (" + text(item.student) + ")",
				fieldtype: "Select",
				options: "\nPresent\nAbsent\nLeave",
				reqd: 1,
			}))];
		}
		if (!fields) {
			// Never expose a clickable no-op. The server remains the only
			// write authority; no dynamic unrestricted command form is made.
			frappe.msgprint({
				title: text(action.label),
				message: text("This command has no supported form yet. Nothing was submitted. Ask your administrator to complete the role-specific workflow."),
				indicator: "red",
			});
			return;
		}
		// New program and policy identifiers belong to the application, not
		// to staff. If a short English label is necessary, the Owner supplies
		// ordinary words; the ID is derived and validated before guarded POST.
		const automaticCode = /^toefl_house\..*\.create_[a-z_]+$/.test(action.endpoint) &&
			!(action.args && action.args.code) &&
			fields.some((field) => field.fieldname === "code") &&
			fields.some((field) => field.fieldname === "title");
		if (automaticCode) {
			fields = fields.filter((field) => field.fieldname !== "code").concat([{
				fieldname: "short_name", label: "Short English name (only if the title is in Dari)",
				fieldtype: "Data", description: "Optional. Use a simple English name such as SPEAKING or ACADEMIC. The system creates the internal ID.",
			}]);
		}
		// Finance enters instructor contracts as ordinary rows. The native
		// contract API still receives its reviewed structure, assembled by
		// the application only after every entered row passes basic checks.
		const teachingContractForm = [
			"toefl_house.teaching.compensation.create_teaching_contract",
			"toefl_house.teaching.compensation.revise_teaching_contract",
		].includes(action.endpoint);
		if (teachingContractForm) {
			fields = fields.filter((field) => !["skill_terms", "adjustments"].includes(field.fieldname));
			for (let index = 1; index <= 6; index += 1) {
				fields = fields.concat([
					{ fieldname: "skill_" + index, label: "Pay skill " + index + " — optional", fieldtype: "Link", options: "TH Skill" },
					{ fieldname: "skill_unit_" + index, label: "Skill " + index + " — payment unit (e.g. Class)", fieldtype: "Data" },
					{ fieldname: "skill_rate_" + index, label: "Skill " + index + " — AFN per unit", fieldtype: "Currency" },
					{ fieldname: "skill_quantity_" + index, label: "Skill " + index + " — units payable", fieldtype: "Float" },
					{ fieldname: "skill_min_" + index, label: "Skill " + index + " — minimum AFN (optional)", fieldtype: "Currency" },
					{ fieldname: "skill_max_" + index, label: "Skill " + index + " — maximum AFN (optional)", fieldtype: "Currency" },
				]);
			}
			for (let index = 1; index <= 2; index += 1) {
				fields = fields.concat([
					{ fieldname: "adjustment_type_" + index, label: "Adjustment " + index + " — optional", fieldtype: "Select", options: "\nBonus\nDeduction" },
					{ fieldname: "adjustment_amount_" + index, label: "Adjustment " + index + " — AFN", fieldtype: "Currency" },
					{ fieldname: "adjustment_date_" + index, label: "Adjustment " + index + " — date", fieldtype: "Date" },
					{ fieldname: "adjustment_approver_" + index, label: "Adjustment " + index + " — approved by", fieldtype: "Link", options: "User" },
					{ fieldname: "adjustment_reason_" + index, label: "Adjustment " + index + " — reason", fieldtype: "Small Text" },
				]);
			}
		}
		if (action.endpoint === "toefl_house.teaching.compensation.revise_teaching_contract" &&
			!action._contract_prefill) {
			const contract = action.args && action.args.contract;
			if (typeof contract !== "string" || !contract || contract.length > 140) {
				frappe.msgprint(text("Choose the active contract to revise."));
				return;
			}
			frappe.call({
				method: "toefl_house.teaching.compensation.get_contract_revision_form",
				type: "GET",
				args: { contract },
				callback(response) {
					const current = response.message;
					if (!current || current.contract !== contract ||
						!Array.isArray(current.skill_terms) ||
						!Array.isArray(current.adjustments) ||
						current.skill_terms.length > 6 ||
						current.adjustments.length > 2) {
						frappe.msgprint(text("The current contract cannot be safely loaded into the guided form. No terms were changed."));
						return;
					}
					openGuidedAction(Object.assign({}, action, { _contract_prefill: current }));
				},
				error() {
					frappe.msgprint(text("Current contract terms could not be loaded with your Finance permissions. Nothing was changed."));
				},
			});
			return;
		}
		// Course Owner cannot be handed broad native Accounts/Education read
		// permissions just to populate a dropdown. Resolve only approved
		// master names through a guarded read-only server projection.
		const pickerFields = fields.filter((field) => typeof field.options === "string" &&
			/^__owner_choice:[a-z_]+__$/.test(field.options));
		if (pickerFields.length) {
			if (!action._owner_choices) {
				frappe.call({
					method: "toefl_house.setup_presets.owner_policy_forms.owner_form_options",
					type: "GET",
					callback(response) {
						const options = response.message;
						if (!options || typeof options !== "object") {
							frappe.msgprint(text("Owner settings could not load the approved choices. Nothing was changed."));
							return;
						}
						openGuidedAction(Object.assign({}, action, { _owner_choices: options }));
					},
					error() {
						frappe.msgprint(text("The approved options could not be loaded with your current permissions. Nothing was changed."));
					},
				});
				return;
			}
			for (const field of pickerFields) {
				const kind = field.options.slice("__owner_choice:".length, -2);
				const allowed = action._owner_choices[kind];
				if (!Array.isArray(allowed) || allowed.length > 100 ||
					allowed.some((name) => typeof name !== "string" ||
						!name || name.length > 140 || /[\r\n]/.test(name))) {
					frappe.msgprint(text("Approved master choices are invalid. No changes were submitted."));
					return;
				}
			}
			fields = fields.map((field) => {
				if (typeof field.options !== "string" ||
					!/^__owner_choice:[a-z_]+__$/.test(field.options)) return field;
				const kind = field.options.slice("__owner_choice:".length, -2);
				return Object.assign({}, field, {
					fieldtype: "Select",
					options: ["", ...action._owner_choices[kind]].join("\n"),
				});
			});
		}
		const contextKeys = ["outstanding", "expected_amount", "currency", "receipt_list",
			"recipient", "tuition_bill", "refund_amount", "refund_reason", "supporting_evidence", "approved_by", "approval_evidence"];
		const contextFacts = contextKeys.filter((key) => action.args && action.args[key] !== undefined)
			.map((key) => `<dt>${escapeText(key.replace(/_/g, " "))}</dt><dd style="white-space:pre-wrap">${escapeText(action.args[key])}</dd>`).join("");
		const contextFields = contextFacts ? [{ fieldname: "cash_context", fieldtype: "HTML", options: `<dl>${contextFacts}</dl>` }] : [];
		// One key per opened form, reused on a retry; do not rely on
		// hidden Frappe inputs appearing in get_values().
		const requestKey = newRequestKey();
		const dialog = new frappe.ui.Dialog({
			title: text(action.label),
			fields: [{ fieldname: "request_key", label: text("Request reference"), fieldtype: "Data", hidden: 1, read_only: 1, default: requestKey }, ...contextFields, ...fields],
			primary_action_label: text(action.label),
			primary_action(values) {
				const guard = ACTION_GUARDS[action.endpoint];
				if (guard) {
					const problem = guard(values);
					if (problem) {
						frappe.msgprint({ title: text(action.label), message: text(problem), indicator: "red" });
						return;
					}
				}
				const args = { request_key: requestKey };
				fields.forEach((field) => {
					if (field.fieldname) args[field.fieldname] = values[field.fieldname];
				});
				if (cashClose) {
					const counts = [];
					for (const [index, drawer] of action.args.drawers.entries()) {
						const raw = values["drawer_counted_" + index];
						if (raw === undefined || raw === null || raw === "" ||
							!Number.isFinite(Number(raw)) || Number(raw) < 0 ||
							!/^\\d+(?:\\.\\d{1,2})?$/.test(String(raw))) {
							frappe.msgprint(text("Enter every physical count in AFN with at most two decimals; enter 0 for empty drawers."));
							return;
						}
						const counted = Number(raw);
						const expected = Number(drawer.expected);
						const note = String(values["drawer_note_" + index] || "").trim();
						if (!Number.isFinite(expected) || (Math.abs(counted - expected) > 0.005 && !note)) {
							frappe.msgprint(text("Explain the difference between the physical count and the ledger balance."));
							return;
						}
						if (note.length > 500) {
							frappe.msgprint(text("The drawer explanation must not exceed 500 characters."));
							return;
						}
						counts.push({ account: drawer.account, counted_amount: counted, note });
						["drawer_name_", "drawer_expected_", "drawer_counted_", "drawer_note_"].forEach(
							(key) => delete args[key + index]);
					}
					// Frappe form transport uses a JSON string for complex arrays.
					// The guarded POST parses it with bounds and rechecks every
					// account and variance against the native ledger.
					args.counts = JSON.stringify(counts);
					delete args.drawers;
				}
				if (teachingContractForm) {
					const terms = [];
					const adjustments = [];
					for (let index = 1; index <= 6; index += 1) {
						const skill = String(values["skill_" + index] || "").trim();
						const unit = String(values["skill_unit_" + index] || "").trim();
						const rate = values["skill_rate_" + index];
						const quantity = values["skill_quantity_" + index];
						const minimum = values["skill_min_" + index];
						const maximum = values["skill_max_" + index];
						const hasMin = minimum !== undefined && minimum !== null && minimum !== "";
						const hasMax = maximum !== undefined && maximum !== null && maximum !== "";
						const hasRate = rate !== undefined && rate !== null && rate !== "";
						const hasQuantity = quantity !== undefined && quantity !== null && quantity !== "";
						if (skill || unit || hasRate || hasQuantity) {
							if (!skill || !unit || !hasRate || !hasQuantity ||
								!Number.isFinite(Number(rate)) || Number(rate) <= 0 ||
								!Number.isFinite(Number(quantity)) || Number(quantity) <= 0) {
								frappe.msgprint(text("For each paid skill, choose the skill, payment unit, positive AFN rate and positive quantity."));
								return;
							}
							if ((hasMin && (!Number.isFinite(Number(minimum)) || Number(minimum) < 0)) ||
								(hasMax && (!Number.isFinite(Number(maximum)) || Number(maximum) < 0)) ||
								(hasMin && hasMax && Number(minimum) > Number(maximum))) {
								frappe.msgprint(text("Skill minimum/maximum must be valid AFN amounts, with minimum not greater than maximum."));
								return;
							}
							const term = { skill, unit_of_payment: unit,
								rate: Number(rate), payable_quantity: Number(quantity) };
							if (hasMin) term.minimum_amount = Number(minimum);
							if (hasMax) term.maximum_amount = Number(maximum);
							terms.push(term);
						}
						["skill_", "skill_unit_", "skill_rate_", "skill_quantity_",
							"skill_min_", "skill_max_"].forEach((name) =>
							delete args[name + index]);
					}
					if (new Set(terms.map((row) => row.skill)).size !== terms.length) {
						frappe.msgprint(text("The same skill was entered twice. Choose each skill only once."));
						return;
					}
					if ((values.compensation_model === "Fixed Salary" && terms.length) ||
						(values.compensation_model !== "Fixed Salary" && !terms.length)) {
						frappe.msgprint(text("Fixed Salary must have no skill rates. Skill-Based and Hybrid contracts require at least one paid skill."));
						return;
					}
					for (let index = 1; index <= 2; index += 1) {
						const type = String(values["adjustment_type_" + index] || "").trim();
						const amount = values["adjustment_amount_" + index];
						const date = values["adjustment_date_" + index];
						const approver = values["adjustment_approver_" + index];
						const reason = values["adjustment_reason_" + index];
						const filled = [type, amount, date, approver, reason]
							.some((v) => v !== undefined && v !== null && v !== "");
						if (filled) {
							if (!["Bonus", "Deduction"].includes(type) || !Number.isFinite(Number(amount)) ||
								Number(amount) <= 0 || !date || !approver || !String(reason || "").trim()) {
								frappe.msgprint(text("A salary adjustment needs Bonus/Deduction, a positive AFN amount, date, approver and reason."));
								return;
							}
							adjustments.push({ adjustment_type: type, amount: Number(amount),
								effective_date: date, approver, reason: String(reason).trim() });
						}
						["adjustment_type_", "adjustment_amount_", "adjustment_date_",
							"adjustment_approver_", "adjustment_reason_"].forEach((name) =>
							delete args[name + index]);
					}
					args.skill_terms = JSON.stringify(terms);
					args.adjustments = JSON.stringify(adjustments);
				}
				if (automaticCode) {
					const source = String(values.short_name || values.title || "");
					const slug = source.normalize("NFKD").toUpperCase()
						.replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "");
					const family = action.endpoint === "toefl_house.academic.create_level"
						? String(values.family || "").toUpperCase().replace(/[^A-Z0-9-]/g, "") + "-"
						: "";
					const code = (family + slug).slice(0, 32).replace(/-+$/g, "");
					if (slug.length < 2 || !/^[A-Z0-9][A-Z0-9-]{0,30}[A-Z0-9]$/.test(code) || code.includes("--")) {
						frappe.msgprint(text("Enter a short English name for this program or policy; the system will generate its identifier."));
						return;
					}
					args.code = code;
					delete args.short_name;
				}
				if (action.endpoint === "toefl_house.setup_presets.native_grading_scale.create_owner_grading_scale") {
					const thresholds = ["grade_a", "grade_b", "grade_c", "grade_d"].map((key) =>
						Number(values[key]));
					if (thresholds.some((n) => !Number.isFinite(n) || n <= 0 || n > 100) ||
						!thresholds.every((n, index) => index === 0 || thresholds[index - 1] > n)) {
						frappe.msgprint(text("Enter four descending minimum scores: A > B > C > D > 0, each at most 100."));
						return;
					}
					args.intervals = JSON.stringify(["A", "B", "C", "D", "F"].map((grade_code, index) => ({
						grade_code, threshold: index === 4 ? 0 : thresholds[index],
					})));
					["grade_a", "grade_b", "grade_c", "grade_d"].forEach((key) => delete args[key]);
				}
				if (["toefl_house.setup_presets.owner_policy_forms.revise_grading_weights",
					"toefl_house.setup_presets.owner_policy_forms.configure_initial_assessment"].includes(action.endpoint)) {
					const keys = ["speaking", "listening", "writing",
						"reading", "grammar", "vocabulary"];
					const values_ = keys.map((key) => Number(values[key]));
					const continuous = Number(values.continuous_percent);
					if (values_.some((n) => !Number.isInteger(n) || n < 0 || n > 100) ||
						values_.reduce((sum, value) => sum + value, 0) !== 100 ||
						!Number.isInteger(continuous) || continuous < 1 || continuous > 99) {
						frappe.msgprint(text(
							"Enter six whole-number skill percentages totaling 100, plus a continuous assessment percentage between 1 and 99."));
						return;
					}
				}
				if (action.endpoint === "toefl_house.academic.set_assessment_policy_version") {
					const scoreSet = values.passing_score !== undefined &&
						values.passing_score !== null && values.passing_score !== "";
					const waitSet = values.retake_wait_days !== undefined &&
						values.retake_wait_days !== null && values.retake_wait_days !== "";
					if (!scoreSet && !waitSet) {
						frappe.msgprint(text("Change at least one number: passing mark or retake wait."));
						return;
					}
					if (scoreSet && (!Number.isInteger(Number(values.passing_score)) ||
						Number(values.passing_score) < 1 || Number(values.passing_score) > 100)) {
						frappe.msgprint(text("The passing mark must be a whole percent from 1 to 100."));
						return;
					}
					if (waitSet && (!Number.isInteger(Number(values.retake_wait_days)) ||
						Number(values.retake_wait_days) < 7 || Number(values.retake_wait_days) > 365)) {
						frappe.msgprint(text("The retake waiting period must be 7 to 365 whole days."));
						return;
					}
					if (!scoreSet) delete args.passing_score;
					if (!waitSet) delete args.retake_wait_days;
				}
				if (action.endpoint === "toefl_house.finance.policies.set_billing_policy_version") {
					const monthly = values.installment_cadence === "Solar Hijri Month";
					const due = Number(values.installment_due_day);
					if (monthly && ![1, 25].includes(due)) {
						frappe.msgprint(text("Choose the first or 25th day of the Afghan month."));
						return;
					}
					// Day-based schedules have no Afghan-month grace or due-day
					// semantics. Do not submit these month-only fields to that mode.
					args.installment_due_day = monthly ? due : 0;
					args.payment_grace_days = monthly ? Number(values.payment_grace_days) : 0;
					args.installment_interval_days = monthly ? 0 : Number(values.installment_interval_days);
				}
				if (action.endpoint === "toefl_house.academic.set_assessment_policy_version" &&
					!args.initial_facets) delete args.initial_facets;
				if (ownAttendance) {
					const statuses = {};
					action.args.roster.forEach((member, index) => {
						const key = "mark_" + index;
						statuses[member.student] = values[key];
						delete args[key];
					});
					// No status is defaulted to Present, and this JSON is
					// generated from selected human-friendly dropdowns.
					args.statuses = JSON.stringify(statuses);
				}
				const submitAction = () => frappe.call({
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
					error(response) {
						// Direct ValidationError responses need not carry native
						// _server_messages. Retain the entered form and retry key.
						// Pinned Frappe passes parsed JSON directly for HTTP 417;
						// accept an XHR wrapper as well for compatible callers.
						const body = response && (response.responseJSON || response) || {};
						let detail = text("The action could not be saved. Check the entered values and your permissions, then retry.");
						if (body.exc_type === "ValidationError" && typeof body.exception === "string") {
							const separator = body.exception.indexOf(": ");
							if (separator >= 0) detail = body.exception.slice(separator + 2, separator + 502);
						}
						frappe.msgprint({ title: text(action.label), message: escapeText(detail), indicator: "red" });
					},
				});
				if (cashClose) {
					frappe.confirm(text(
						"Submit the actual counts and close this company's entire business day? This close cannot be edited; no payment or cash movement is created."
					), submitAction);
				} else if (teachingContractForm) {
					frappe.confirm(text(
						action.endpoint === "toefl_house.teaching.compensation.revise_teaching_contract"
							? "This replaces the complete instructor contract from the new effective date. Re-enter ALL approved skills, rates, quantities and adjustments; omitted items will not carry over. Continue?"
							: "Save these instructor contract terms? This records an approved contract, not a salary payment."
					), submitAction);
				} else {
					submitAction();
				}
			},
		});
		const values = Object.assign({}, action.args || {});
		if (teachingContractForm && action._contract_prefill) {
			const contract = action._contract_prefill;
			["compensation_model", "assignment_basis", "payment_frequency",
				"conditions", "earning_basis", "effective_end"].forEach((key) => {
				if (contract[key] !== undefined && contract[key] !== null)
					values[key] = contract[key];
			});
			// A revised contract must have its own new effective start.
			// Never silently reuse the previous contract's starting date.
			contract.skill_terms.forEach((row, index) => {
				const i = index + 1;
				values["skill_" + i] = row.skill;
				values["skill_unit_" + i] = row.unit_of_payment;
				values["skill_rate_" + i] = row.rate;
				values["skill_quantity_" + i] = row.payable_quantity;
				if (row.minimum_amount !== undefined && row.minimum_amount !== null)
					values["skill_min_" + i] = row.minimum_amount;
				if (row.maximum_amount !== undefined && row.maximum_amount !== null)
					values["skill_max_" + i] = row.maximum_amount;
			});
			contract.adjustments.forEach((row, index) => {
				const i = index + 1;
				values["adjustment_type_" + i] = row.adjustment_type;
				values["adjustment_amount_" + i] = row.amount;
				values["adjustment_date_" + i] = row.effective_date;
				values["adjustment_approver_" + i] = row.approver;
				values["adjustment_reason_" + i] = row.reason;
			});
		}
		// The native grading API uses structured intervals, but the customer
		// only sees four familiar numeric grades, never a JSON editor.
		if (action.endpoint === "toefl_house.setup_presets.native_grading_scale.create_owner_grading_scale" &&
			typeof values.intervals === "string") {
			try {
				const rows = JSON.parse(values.intervals);
				if (Array.isArray(rows) && rows.length === 5 &&
					["A", "B", "C", "D", "F"].every((grade, i) => rows[i] && rows[i].grade_code === grade)) {
					["grade_a", "grade_b", "grade_c", "grade_d"].forEach((key, i) => {
						if (Number.isFinite(Number(rows[i].threshold))) values[key] = Number(rows[i].threshold);
					});
				}
			} catch (_error) {
				// A malformed template cannot be a reason to expose raw JSON.
			}
		}
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
			const body = sectionShell(container, sectionPayload.title, sectionPayload.kind);
			const items = sectionPayload.items || sectionPayload.facts || [];
			// Analytics sections may carry hero/groups even with no flat items
			const hasAnalytics = sectionPayload.kind === "analytics" && (sectionPayload.hero || sectionPayload.groups);
			if (!items.length && !hasAnalytics && sectionPayload.kind !== "analytics") {
				emptyState(body, sectionPayload.empty || {});
				return;
			}
			if (sectionPayload.kind === "analytics" && !items.length && !hasAnalytics) {
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
		const loadingWrap = $("<div class='th-section'></div>").appendTo(sections);
		loadingState(loadingWrap, "Loading your work…");
		skeletonGrid(loadingWrap, 4);
		frappe.call({
			method: surface.endpoint,
			callback(response) {
				loadingWrap.remove();
				loadSections(sections, response.message || {});
				// Announce completion to screen readers
				const announcement = $("<div class='th-visually-hidden' role='status' aria-live='polite'></div>")
					.text(text("Your work has loaded. " + ((response.message || {}).sections || []).length + " sections available."));
				sections.append(announcement);
				if (typeof setTimeout === "function") {
					setTimeout(() => announcement.remove(), 2000);
				}
			},
			error() {
				loadingWrap.remove();
				const block = $("<section class='th-section'></section>").appendTo(sections);
				$("<h2 class='th-section-title'></h2>").text(text("Your work")).appendTo(block);
				const sectionBody = $("<div class='th-section-body'></div>").appendTo(block);
				errorState(sectionBody, () => {
					sectionBody.empty();
					const retryLoading = loadingState(sectionBody, "Loading your work…");
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
			.attr("aria-label", text("Search for person"))
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
			results.append(queueMarkup(applicants, [text("Record"), text("Status"), text("Next action"), text("Waiting"), text("Act")]));
		}
		if (students.length) {
			$("<h3 class='th-search-heading'></h3>").text(text("Enrolled students")).appendTo(results);
			results.append(queueMarkup(students, [text("Record"), text("Status"), text("Next action"), text("Waiting"), text("Act")]));
		}
		(payload.collection_sections || []).forEach((part) => {
			const body = sectionShell(results, part.title, part.kind);
			if ((part.items || []).length) renderSectionBody(body, part);
			else emptyState(body, part.empty || {});
		});
	}

	/* The first-run review never issues a configuration mutation.  Existing
	 * data, alternate level codes and release blockers must remain visible. */
	function mountOwnerSetupPreview(page) {
		const section = $("<section class='th-section th-setup-preview'></section>").appendTo(page.body);
		$("<h2 class='th-section-title'></h2>").text(text("Review first-run setup")).appendTo(section);
		const body = $("<div class='th-section-body'></div>").appendTo(section);
		$("<p></p>").text(text(
			"Compare the proposed course setup with this site's existing configuration. " +
			"This is a read-only check: nothing is installed, changed, billed or approved."
		)).appendTo(body);
		$("<h3></h3>").text(text("Start your course in simple steps")).appendTo(body);
		const steps = [
			["1. Courses and tuition", "Check the four programs, eleven levels and approved full-semester AFN prices.", "th-academic-setup"],
			["2. Academic and billing rules", "Choose percentages, waiting days, billing options and approval roles using forms.", "th-configuration"],
			["3. Rooms, teachers and timetables", "Enter verified capacity and staff assignments; review sessions before students join.", "th-academic-desk"],
			["4. Finance and daily work", "Use guided receivables, collections and approved instructor contracts, never source files.", "th-finance-desk"],
			["5. Review before opening", "Check each staff role, backup recovery and operational readiness with the Owner.", "th-owner-cockpit"],
		];
		const guide = $("<div class='th-route-group'></div>").appendTo(body);
		steps.forEach(([label, description, route]) => {
			const item = $("<div class='th-step'></div>").appendTo(guide);
			$("<strong></strong>").text(text(label)).appendTo(item);
			$("<p></p>").text(text(description)).appendTo(item);
			$("<button type='button' class='btn btn-secondary btn-sm'></button>")
				.text(text("Open")).on("click", () => routeToSource(route))
				.appendTo(item);
		});
		$("<p class='text-muted'></p>").text(text(
			"Some steps require a verified staff identity or release approval. A missing approval means Stop — it is never a request to edit JSON, scripts or database tables."
		)).appendTo(body);
		const actions = $("<div class='th-setup-actions'></div>").appendTo(body);
		const button = $("<button type='button' class='btn btn-primary btn-sm'></button>")
			.text(text("Check TOEFL House setup")).appendTo(actions);
		const output = $("<div class='th-setup-result' aria-live='polite'></div>").appendTo(body);
		button.on("click", () => {
			button.prop("disabled", true);
			output.empty();
			$("<p></p>").text(text("Checking current configuration…")).appendTo(output);
			frappe.call({
				method: "toefl_house.setup_presets.api.preview_owner_initial_setup",
				callback(response) {
					button.prop("disabled", false);
					output.empty();
					const data = response.message || {};
					if (data.mode !== "READ_ONLY_PREVIEW" || data.ready_to_apply !== false ||
						!data.counts || !Array.isArray(data.actions)) {
						$("<p class='text-danger'></p>").text(text(
							"Setup preview returned an unexpected response. No configuration was changed."
						)).appendTo(output);
						return;
					}
					$("<h3></h3>").text(text("Your course setup status")).appendTo(output);
					$("<p></p>").text(
						text("Still to set up") + ": " + Number(data.counts.create || 0) + "  ·  " +
						text("Already correct") + ": " + Number(data.counts.match || 0) + "  ·  " +
						text("Needs a decision") + ": " + Number(data.counts.review || 0)
					).appendTo(output);
					const timetable = data.daily_timetable;
					if (timetable && timetable.status === "OWNER_CONFIRMED" &&
						Array.isArray(timetable.sessions) && timetable.sessions.length === 7) {
						$("<h4></h4>").text(text("Daily sessions — Kabul time")).appendTo(output);
						const periods = $("<table class='table table-bordered table-condensed'></table>").appendTo(output);
						const headings = $("<thead><tr></tr></thead>").appendTo(periods).find("tr");
						[text("Session"), text("Male classes"), text("Female classes")].forEach(
							(label) => $("<th></th>").text(label).appendTo(headings)
						);
						const rows = $("<tbody></tbody>").appendTo(periods);
						timetable.sessions.forEach((period) => {
							const row = $("<tr></tr>").appendTo(rows);
							$("<td></td>").text(String(period.code || "")).appendTo(row);
							["male", "female"].forEach((track) => {
								const window = period[track] || {};
								$("<td></td>").text(String(window.start || "") + "–" + String(window.end || "")).appendTo(row);
							});
						});
						$("<p></p>").text(text(
							"Friday is the weekly day off. These periods do not assign classes, rooms or teachers."
						)).appendTo(output);
					}
					const scale = data.grading_scale_suggestion;
					if (scale && typeof scale.grading_scale_name === "string" &&
						typeof scale.intervals === "string" && scale.intervals.length < 4096) {
						const status = scale.exists ? text("Existing scale found") :
							text("Native grading scale is not yet created");
						$("<p></p>").text(status + ": " + scale.grading_scale_name).appendTo(output);
						$("<button type='button' class='btn btn-secondary btn-sm'></button>")
							.text(text("Create a new native grading scale version"))
							.on("click", () => openGuidedAction({
								label: "Create new grading scale",
								endpoint: "toefl_house.setup_presets.native_grading_scale.create_owner_grading_scale",
								args: {
									grading_scale_name: scale.exists ? "" : scale.grading_scale_name,
									intervals: scale.intervals,
								},
							}))
							.appendTo(output);
						$("<p></p>").text(text(
							"Creating a scale submits a new native document with an audit trail. " +
							"Link it to the assessment policy in a separately reviewed policy version."
						)).appendTo(output);
					}
					// Keep internal record IDs and operation names optional.
					const advanced = $("<details class='th-advanced-setup'></details>").appendTo(output);
					$("<summary></summary>").text(text("Show technical setup details")).appendTo(advanced);
					if (Number.isInteger(data.planned_actions_count) &&
						data.planned_actions_count >= 0 && data.counts.review === 0) {
						$("<p></p>").text(text("First-run actions proposed, not executed") +
							": " + data.planned_actions_count).appendTo(output);
						const operations = data.planned_operation_counts || {};
						const list = $("<ul></ul>").appendTo(advanced);
						Object.entries(operations).slice(0, 20).forEach(([name, count]) => {
							$("<li></li>").text(String(name) + ": " + Number(count || 0)).appendTo(list);
						});
					}
					// Fresh installs do not have prior course records. This control
					// only appears when the SERVER has verified the two release
					// switches, clean-site guard, finance prerequisites and plan.
					// The POST independently rechecks all of them under a lock.
					const fresh = data.fresh_installation || {};
					if (fresh.profile === "FRESH_SITE_NO_PRIOR_COURSE_HISTORY") {
						$("<p></p>").text(text(fresh.message || "")).appendTo(output);
					}
					if (fresh.can_initialize === true &&
						fresh.profile === "FRESH_SITE_NO_PRIOR_COURSE_HISTORY" &&
						data.counts.review === 0 && data.planned_actions_count > 0 &&
						typeof data.plan_hash === "string" && data.plan_hash.length > 0) {
						const apply = $("<button type='button' class='btn btn-primary btn-sm'></button>")
							.text(text("Initialize new course catalog")).appendTo(output);
						apply.on("click", () => {
							frappe.confirm(
								text("Create the approved TOEFL House course catalog and draft fees on this fresh, empty site? No students, receipts or payments will be created."),
								() => {
									apply.prop("disabled", true);
									frappe.call({
										method: "toefl_house.setup_presets.installer.initialize_owner_catalog",
										type: "POST",
										args: {
											expected_plan_hash: data.plan_hash,
											confirmation: "APPLY_TO_NEW_COURSE_SITE",
										},
										callback(response) {
											const result = response.message || {};
											if (result.status !== "CATALOG_DRAFTS_INITIALIZED" &&
												result.status !== "ALREADY_MATCHED") {
												apply.prop("disabled", false);
												frappe.msgprint(text("Catalog setup did not confirm success. Review the configuration before retrying."));
												return;
											}
											frappe.msgprint(text("Approved course catalog initialized. Refreshing configuration review."));
											button.trigger("click");
										},
										error() {
											apply.prop("disabled", false);
											frappe.msgprint(text("Catalog initialization was denied or failed. No production use is authorized."));
										},
									});
								}
							);
						});
					}
					const table = $("<table class='table table-bordered table-condensed'></table>").appendTo(advanced);
					const head = $("<thead><tr></tr></thead>").appendTo(table).find("tr");
					[text("Area"), text("Code"), text("Status"), text("Next step")].forEach(
						(label) => $("<th></th>").text(label).appendTo(head)
					);
					const tbody = $("<tbody></tbody>").appendTo(table);
					data.actions.slice(0, 100).forEach((item) => {
						const tr = $("<tr></tr>").appendTo(tbody);
						[item.kind, item.code, item.status, item.details].forEach(
							(value) => $("<td></td>").text(String(value || "")).appendTo(tr)
						);
					});
					if (Array.isArray(data.pending_decisions) && data.pending_decisions.length) {
						$("<h4></h4>").text(text("Still requires Owner review")).appendTo(output);
						const list = $("<ul></ul>").appendTo(output);
						data.pending_decisions.slice(0, 30).forEach(
							(value) => $("<li></li>").text(String(value || "")).appendTo(list)
						);
					}
					$("<p class='text-warning'></p>").text(text(
						"This site has not been initialized by the preview. " +
						"Do not use live student or finance records until release acceptance is complete."
					)).appendTo(output);
				},
				error() {
					button.prop("disabled", false);
					output.empty();
					$("<p class='text-danger'></p>").text(text(
						"Setup inspection was denied or unavailable; no data was changed."
					)).appendTo(output);
				},
			});
		});
	}

	Object.entries(SURFACES).forEach(([slug, surface]) => {
		// Native Page creates its DOM wrapper BEFORE evaluating page_js.
		// Never create placeholders for unopened pages: pageview.show treats
		// any truthy entry as already constructed and would show a blank page.
		if (!frappe.pages[slug] || !frappe.pages[slug].tagName) return;
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
			if (slug === "th-academic-setup") mountOwnerSetupPreview(page);
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

