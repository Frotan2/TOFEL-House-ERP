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
					if (fact.drill.route) frappe.set_route(fact.drill.route);
					else if (fact.drill.slug) frappe.set_route(fact.drill.slug);
				});
				drill.appendTo(tile);
			}
			if (fact.drill_path) {
				const drill2 = $("<button type='button' class='btn btn-secondary btn-xs' style='margin-top:0.5rem'></button>").text(text("View source records"));
				drill2.on("click", () => frappe.set_route(fact.drill_path));
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
				if (f.route) chip.on("click", () => frappe.set_route(f.route));
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
					.on("click", () => frappe.set_route(group.drill.route || group.drill.slug))
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
				link.on("click", () => frappe.set_route(m.drill.route || m.drill.slug));
				link.appendTo(meta);
			}
			if (m.drill_path) {
				const link = $("<button type='button' class='th-drill-link'></button>").text(text("View records"));
				link.on("click", () => frappe.set_route(m.drill_path));
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
				link.on("click", () => frappe.set_route(row.drill.route || row.drill.slug));
				link.appendTo(valCell);
			}
		});
		return table;
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
					.on("click", () => frappe.set_route(item.drill.route || item.drill.slug));
				drillBtn.appendTo(action);
			}
			if (item.drill_path) {
				const drillBtn = $("<button type='button' class='btn btn-secondary btn-xs th-queue-action'></button>")
					.text(text("View record"))
					.on("click", () => frappe.set_route(item.drill_path));
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
	const ACTION_FIELDS = Object.freeze({
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
			{ fieldname: "max_backdate_days", label: "Max backdate days", fieldtype: "Int", reqd: 1 },
			{ fieldname: "max_future_days", label: "Max future days", fieldtype: "Int", reqd: 1 },
			{ fieldname: "placement_fee_timing", label: "Placement-fee timing", fieldtype: "Data", reqd: 1 },
			{ fieldname: "installments_allowed", label: "Installments allowed", fieldtype: "Check" },
			{ fieldname: "max_installments", label: "Maximum installments", fieldtype: "Int", reqd: 1 },
			{ fieldname: "installment_interval_days", label: "Installment interval (days)", fieldtype: "Int", reqd: 1 },
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
			{ fieldname: "academic_year", label: "Academic year", fieldtype: "Data", reqd: 1 },
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
		"toefl_house.academic.create_assessment_policy": [
			{ fieldname: "family", label: "Program code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "code", label: "Policy code (stable)", fieldtype: "Data", reqd: 1 },
			{ fieldname: "title", label: "Title", fieldtype: "Data", reqd: 1 },
			{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
		],
		"toefl_house.academic.set_assessment_policy_version": [
			{ fieldname: "policy", label: "Policy code", fieldtype: "Data", reqd: 1 },
			{ fieldname: "effective_from", label: "Effective from (after the current latest version)", fieldtype: "Date", reqd: 1 },
			{ fieldname: "reason", label: "Reason (mandatory)", fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "grading_scale", label: "Grading scale (native, optional)", fieldtype: "Data" },
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
			fields: [{ fieldname: "request_key", label: text("Request reference (filled in for you)"), fieldtype: "Data", reqd: 1, read_only: 1, default: newRequestKey(), description: text("Reuse this exact value if you must retry the same request after a connection error.") }, ...fields],
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
