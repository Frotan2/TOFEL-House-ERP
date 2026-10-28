/*
 * Contract for the TOEFL House design system and command-response projection.
 *
 * Two behaviours matter enough to pin here.
 *
 * 1. `resultMarkup` builds an HTML *string* that Frappe hands to msgprint, from
 *    values the server returned. Anything built that way must escape those
 *    values, or a record whose name contains markup becomes a script in an
 *    operator's dialog. The tests below assert the escaping directly, because a
 *    projection that looks correct on clean data is not evidence of safety.
 *
 * 2. The projection must not lose information. Staff previously received the
 *    raw payload; they now receive a readable summary. The full response must
 *    still be present so an auditor can see exactly what the server said.
 *
 * No Frappe site is required: the script is executed in a bare sandbox.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "../..");
const APP = path.join(ROOT, "apps/toefl_house/toefl_house");
const SCRIPT = path.join(APP, "public/js/th_command_pages.js");
const STYLESHEET = path.join(APP, "public/css/th_design_system.css");
const PYPROJECT = path.join(ROOT, "apps/toefl_house/pyproject.toml");

function loadModule(frappeOverrides = {}) {
	const client = {};
	client.__ = (label) => label;
	client.window = { crypto: { getRandomValues(bytes) { for (let i = 0; i < bytes.length; i++) bytes[i] = i + 1; return bytes; } } };
	// Pure projection tests must not reach a DOM; fail loudly if one is used.
	client.$ = () => { throw new Error("DOM must not be touched by pure projection tests"); };
	client.frappe = {
		pages: {},
		provide(dotted) { let target = client; for (const part of dotted.split(".")) target = target[part] ||= {}; },
		require() {},
		msgprint() {},
		ui: { make_app_page: () => ({ body: {}, main: { addClass() {} } }), Dialog: class { show() {} hide() {} } },
		user: { has_role: () => false },
		set_route() {},
		call() {},
		...frappeOverrides,
	};
	vm.runInNewContext(fs.readFileSync(SCRIPT, "utf8"), client, { filename: SCRIPT });
	return client;
}

const { resultMarkup, statusTone, stylesheet } = loadModule().toefl_house.command_pages;

/* ------------------------------------------------------------------ escaping */

// The core safety property. A server-returned identifier is not trusted HTML.
const hostile = { name: "<img src=x onerror=alert(1)>", status: "Draft" };
const hostileHtml = resultMarkup("Create item draft", hostile);
assert(!/<img\s/i.test(hostileHtml), "hostile markup must not survive as an element");
assert(hostileHtml.includes("&lt;img"), "hostile markup must be escaped, not dropped");
assert(!hostileHtml.includes("<img src=x"), "raw hostile attribute must not appear");

// Script content specifically: the classic payload for a string-built dialog.
const scripted = resultMarkup("Publish", { name: "<script>alert(1)</script>", status: "Published" });
assert(!/<script>/i.test(scripted), "script tag must be escaped in the projection");
assert(scripted.includes("&lt;script&gt;"), "script tag must remain visible as escaped text");

// Quote and apostrophe breakout, which would otherwise escape the attribute or
// string context the value is placed in.
const quoted = resultMarkup("Publish", { name: `"><svg/onload=alert(1)>`, status: "Published" });
assert(!/<svg/i.test(quoted), "quote breakout must not open a new element");

// A detail string is attacker-influenceable in the same way as a name.
const detail = resultMarkup("Review", { reason: "<b>bold</b>", status: "Conditional" });
assert(!/<b>/.test(detail), "response detail must be escaped too");

/* ------------------------------------------------------------ no information loss */

// Staff no longer see raw JSON first, but the full payload must still be there.
const payload = { name: "ITEM-0001", version: 3, expected_version: 2, status: "Published", content_hash: "abc123" };
const html = resultMarkup("Publish item revision", payload);
assert(html.includes("<details"), "full response must remain available under a disclosure");
assert(html.includes("Full server response"), "disclosure must be labelled");
for (const value of ["ITEM-0001", "abc123"]) {
	assert(html.includes(value), `payload value ${value} must survive in the projection`);
}
// And it must be readable: known fields get human labels, not field names.
assert(html.includes("Record"), "name must be presented with a human label");
assert(html.includes("Version now"), "version must be presented with a human label");
assert(html.includes("Content hash"), "content_hash must be presented with a human label");
assert(!html.includes("<dt>content_hash</dt>"), "raw field name must not be shown as a label");

/* ------------------------------------------------------------------ status tone */

// The projection must never imply success the server did not state. An
// unrecognised status is neutral, not green - this is the mutation that matters.
assert.strictEqual(statusTone("Published"), "ok");
assert.strictEqual(statusTone("Active"), "ok");
assert.strictEqual(statusTone("Rejected"), "danger");
assert.strictEqual(statusTone("Cancelled"), "danger");
assert.strictEqual(statusTone("Conditional"), "warn");
assert.strictEqual(statusTone("Deferred"), "warn");
assert.strictEqual(statusTone("Draft"), "info");
assert.strictEqual(statusTone("SomeBrandNewState"), "neutral", "unknown status must not read as success");
assert.strictEqual(statusTone(""), "neutral");
assert.strictEqual(statusTone(undefined), "neutral");
// Case and padding are not the server's contract, so tone must not depend on them.
assert.strictEqual(statusTone("  published "), "ok", "tone must ignore case and padding");

// A danger status must change the headline, not just the pill colour.
const failed = resultMarkup("Publish item revision", { name: "ITEM-0002", status: "Rejected" });
assert(failed.includes("did not complete"), "failure must be stated in words");
assert(failed.includes("th-status--danger"), "failure must carry the danger tone");

const succeeded = resultMarkup("Publish item revision", { name: "ITEM-0003", status: "Published" });
assert(succeeded.includes("succeeded"), "success must be stated in words");
assert(!succeeded.includes("did not complete"), "success must not read as failure");

/* ------------------------------------------------------------- absent values */

// A payload with no status must still render, and must not invent one.
const noStatus = resultMarkup("Create item draft", { name: "ITEM-0004", revision: 1 });
assert(!noStatus.includes("th-status"), "no status means no status pill");
assert(noStatus.includes("completed"), "a statusless response still reports completion");

// Empty and null values are omitted rather than shown as blank rows, and an
// empty array is not presented as a fact.
const sparse = resultMarkup("Publish", { name: "ITEM-0005", status: "Published", reason: "", missing: [] });
assert(!sparse.includes("Reason"), "empty string must not produce a fact row");
assert(!sparse.includes("Missing"), "empty array must not produce a fact row");
const withMissing = resultMarkup("Publish", { name: "ITEM-0006", status: "Draft", missing: ["a", "b"] });
assert(withMissing.includes("a, b"), "a non-empty array must render as a readable list");

// The request key is transport, not a business fact, so it stays out of the
// readable list - but it must remain in the raw disclosure.
const keyed = resultMarkup("Publish", { request_key: "AbC123def456GhI789jKl012", name: "ITEM-0007", status: "Draft" });
assert(!keyed.includes("<dt>Request key</dt>"), "request key must not be shown as a business fact");
assert(keyed.includes("AbC123def456GhI789jKl012"), "request key must remain in the raw response");

// Null and non-object payloads must not throw; a malformed response is a real
// possibility and a crash here would mask the underlying server error.
assert.doesNotThrow(() => resultMarkup("Publish", null));
assert.doesNotThrow(() => resultMarkup("Publish", undefined));
assert.doesNotThrow(() => resultMarkup("Publish", "plain string"));

/* ------------------------------------------------------------ asset loading */

// The stylesheet must exist and be shipped, or the design system silently never
// reaches a browser even though every test above passes.
assert(fs.existsSync(STYLESHEET), "design system stylesheet must exist");
assert.strictEqual(stylesheet, "/assets/toefl_house/css/th_design_system.css", "asset path must match the served path");
const pyproject = fs.readFileSync(PYPROJECT, "utf8");
assert(pyproject.includes('"public/css/*.css"'), "stylesheet must be declared in package data");

const css = fs.readFileSync(STYLESHEET, "utf8");

// Namespace discipline: this sheet must not redeclare a platform selector, or a
// Frappe upgrade and this file will fight over the whole desk. Every rule must
// therefore be namespaced under `th-` or scoped inside `.th-page`.
//
// Parse by stripping comments first and matching balanced selector/block pairs.
// A naive "everything up to the next brace" scan treats a closing `}` as part
// of the following selector, which produces false failures.
// @keyframes bodies contain percentage stops ("0%", "100%") which are not
// selectors, so those blocks are removed before the selector scan.
const rules = (css
	.replace(/\/\*[\s\S]*?\*\//g, "")
	.replace(/@keyframes\s+[\w-]+\s*\{(?:[^{}]|\{[^{}]*\})*\}/g, "")
	.match(/([^{}]+)\{/g) || [])
	.map((rule) => rule.replace(/\{$/, "").trim())
	.filter((selector) => selector && !selector.startsWith("@"));
assert(rules.length > 20, "stylesheet must contain a meaningful rule set");

// Split on top-level commas only: a selector list may contain functional
// pseudo-classes such as `:is(a, button)` whose inner commas are not list
// separators, and splitting on those would mistake `button` for a bare
// element selector.
function splitSelectorList(selector) {
	const parts = [];
	let depth = 0;
	let current = "";
	for (const character of selector) {
		if (character === "(") depth += 1;
		else if (character === ")") depth -= 1;
		if (character === "," && depth === 0) { parts.push(current); current = ""; continue; }
		current += character;
	}
	parts.push(current);
	return parts.map((piece) => piece.trim()).filter(Boolean);
}

for (const selector of rules) {
	for (const part of splitSelectorList(selector)) {
		if (part === ":root") continue; // custom properties only
		assert(
			/(^|[\s>+~:.#\[])th-/.test(part),
			`stylesheet must not target platform selector: ${part}`,
		);
		assert(!/^\.(btn|alert|form-control|table|modal|row|col)([^-]|$)/.test(part),
			`stylesheet must not override Bootstrap class: ${part}`);
	}
}

// Tokens the design language claims to provide must actually be defined.
for (const token of ["--th-space-4", "--th-fs-body", "--th-ink", "--th-accent", "--th-ok", "--th-danger", "--th-focus-ring"]) {
	assert(css.includes(`${token}:`), `design token ${token} must be defined`);
}

// The three states that distinguish "thinking" from "broken" must exist.
for (const state of [".th-loading", ".th-empty", ".th-skeleton", ".th-spinner", ".th-alert--danger"]) {
	assert(css.includes(state), `state style ${state} must exist`);
}

// Accessibility is a daily requirement for keyboard-driven reception work, not
// an optional extra, and motion must be reducible.
assert(/:focus-visible/.test(css), "focus must be visible for keyboard users");
assert(/prefers-reduced-motion/.test(css), "animation must be reducible");

/* ----------------------------------------------------------- stylesheet wiring */

// Loading must be idempotent: revisiting a page in one session must not queue
// the same asset repeatedly.
function chained() {
	const api = {};
	for (const method of ["appendTo", "prependTo", "append", "text", "empty", "find", "closest", "attr", "prop", "on", "addClass"]) {
		api[method] = () => api;
	}
	return api;
}

const requests = [];
const wired = loadModule({ require(asset) { requests.push(asset); } });
wired.$ = chained;
wired.frappe.ui = { make_app_page: () => ({ body: {}, main: chained() }), Dialog: class { show() {} } };
const page = wired.frappe.pages["th-placement-invigilation"];
page.on_page_load({});
page.on_page_load({});
assert.deepStrictEqual(requests, ["/assets/toefl_house/css/th_design_system.css"],
	"stylesheet must load once per session, from the page handler");

// Every registered surface must load the stylesheet, not just one of them, or
// most of the desk renders unstyled.
for (const name of Object.keys(wired.frappe.pages)) {
	const perPage = [];
	const scoped = loadModule({ require(asset) { perPage.push(asset); } });
	scoped.$ = chained;
	scoped.frappe.ui = { make_app_page: () => ({ body: {}, main: chained() }), Dialog: class { show() {} } };
	scoped.frappe.pages[name].on_page_load({});
	assert.deepStrictEqual(perPage, ["/assets/toefl_house/css/th_design_system.css"],
		`${name} must load the design system`);
}

/* ---------------------------------------------------- terminology consistency */

// The same business concept must carry one human label everywhere, or staff
// have to learn that "Class" on one screen and "Student group" on another mean
// the same thing. This is the defect that motivated the check: the response
// projection labelled `student_group` as "Class" while every command form
// labelled it "Student group".
const { factLabels, surfaces } = loadModule().toefl_house.command_pages;

// Some fieldnames carry genuinely different meanings in a request and in a
// response, so no single label can be correct for both:
//   - generic transport parameters reused per endpoint (`name` is the item
//     revision in one command and the admission decision in another);
//   - `missing`, which is a Check instruction ("mark this as missing") in the
//     form but a list of missing items in the response.
// Every other field denotes one concept and must read identically in both.
const CONTEXT_DEPENDENT_FIELDNAMES = new Set([
	"name", "reason", "status", "content", "definition", "code", "revision", "expected_version", "missing",
]);

// The exclusion set is pinned to its exact contents. Without this, widening the
// list silently switches the check off for any field - a loophole confirmed by
// mutation rather than hypothesised. Adding an entry must be a deliberate,
// reasoned act, not a way to make a failure disappear.
assert.deepStrictEqual(
	[...CONTEXT_DEPENDENT_FIELDNAMES].sort(),
	["code", "content", "definition", "expected_version", "missing", "name", "reason", "revision", "status"],
	"context-dependent exclusion set changed; each entry needs a stated reason above",
);

const formLabels = new Map();
const conflicting = new Set();
for (const surface of Object.values(surfaces)) {
	for (const command of surface.commands || []) {
		for (const field of command.fields || []) {
			const existing = formLabels.get(field.fieldname);
			if (existing === undefined) formLabels.set(field.fieldname, field.label);
			else if (existing !== field.label) conflicting.add(field.fieldname);
		}
	}
}
assert(formLabels.size > 20, "command forms must expose a meaningful set of labelled fields");

// A fieldname may only be ambiguous if it is genuinely context-dependent. This
// stops the pinned exclusion set from hiding a real inconsistency.
for (const fieldname of conflicting) {
	assert(CONTEXT_DEPENDENT_FIELDNAMES.has(fieldname),
		`${fieldname} is labelled inconsistently across forms but is not a known context-dependent field`);
}

let overlap = 0;
for (const [fieldname, formLabel] of formLabels) {
	// Covers `missing`, which has a single form label and so never appears in
	// `conflicting`, yet still cannot share one label with its response form.
	if (conflicting.has(fieldname) || CONTEXT_DEPENDENT_FIELDNAMES.has(fieldname)) continue;
	if (!(fieldname in factLabels)) continue;
	overlap += 1;
	assert.strictEqual(
		factLabels[fieldname], formLabel,
		`${fieldname} reads "${factLabels[fieldname]}" in results but "${formLabel}" in the form`,
	);
}
assert(overlap > 0, "results and forms must share labelled fields for this check to mean anything");

// Where a concept has a native Frappe authority, the label must follow it
// rather than invent a friendlier synonym. "Instructor", "Student Group" and
// "Program" are native doctypes, so "Teacher", "Class" and "Programme" would be
// parallel vocabulary for the same thing - exactly the duplication this app is
// built to avoid.
assert.strictEqual(factLabels.student_group, "Student group",
	"label must match the native Student Group authority, not a synonym");
assert.strictEqual(factLabels.instructor, "Instructor",
	"label must match the native Instructor authority, not a synonym");
assert.strictEqual(factLabels.program, "Program",
	"label must match the native Program authority, not a synonym");
assert.strictEqual(factLabels.student_applicant, "Student applicant",
	"label must match the native Student Applicant authority, not a synonym");

/* --------------------------------------------------------- landing behaviour */

/*
 * The chainable stub above proves wiring but cannot prove rendering: every
 * method returns the same object, so structure is invisible to it. These tests
 * use a recording fake that keeps parent/child links and text, which is what
 * makes the landing page's two real outcomes assertable.
 */
function recording() {
	const nodes = [];
	function element(markup) {
		const node = {
			markup: String(markup),
			children: [],
			texts: [],
			classes: [],
			handlers: {},
			// Matches the shape the client chains on.
			text(value) { if (value !== undefined) node.texts.push(String(value)); return node; },
			addClass(name) { node.classes.push(String(name)); return node; },
			appendTo(parent) { if (parent && parent.children) parent.children.push(node); return node; },
			prependTo(parent) { if (parent && parent.children) parent.children.unshift(node); return node; },
			append(child) { if (child && child.children) node.children.push(child); return node; },
			empty() { node.children.length = 0; return node; },
			on(event, callback) { (node.handlers[event] ||= []).push(callback); return node; },
			attr() { return node; },
			prop() { return node; },
			find() { return element("<div>"); },
			closest() { return element("<div>"); },
		};
		nodes.push(node);
		return node;
	}
	const dollar = (markup) => element(markup);
	dollar.nodes = nodes;
	return dollar;
}

// Collect every text node below a subtree, which is how we assert on what a
// person would actually read rather than on which methods were called.
function allText(node) {
	return [node.texts.join(" "), ...node.children.map(allText)].join(" ").replace(/\s+/g, " ").trim();
}
// Match a whole class token, not a substring: "th-card" is otherwise also
// matched inside "th-card-title", "th-card-hint" and "th-card-footer", which
// inflates every count fourfold.
function countByClass(node, token) {
	const classes = (node.markup.match(/class='([^']*)'/) || [, ""])[1].split(/\s+/);
	const own = classes.includes(token) ? 1 : 0;
	return own + node.children.reduce((total, child) => total + countByClass(child, token), 0);
}

function loadLanding(roles) {
	const scoped = loadModule({ user: { has_role: (role) => roles.includes(role) } });
	scoped.$ = recording();
	const body = scoped.$("<body>");
	scoped.frappe.ui = {
		make_app_page: () => ({ body, main: scoped.$("<main>") }),
		Dialog: class { show() {} },
	};
	scoped.frappe.pages["th-command-centre"].on_page_load({});
	return { root: body, scoped };
}

// A role with work areas must see one card per work area, each carrying the
// role it belongs to - that label is what stops a manager mistaking one
// placement stage for another.
const invigilator = loadLanding(["Placement Invigilator"]);
assert.strictEqual(countByClass(invigilator.root, "th-card"), 1,
	"an invigilator must see exactly one work area card");
assert(allText(invigilator.root).includes("Placement Invigilator"),
	"the card must name the role it is gated by");
assert(allText(invigilator.root).includes("Open page"),
	"the card must offer the action");
assert(countByClass(invigilator.root, "th-role-chip") === 1, "the role chip must render");

// Course Owner and General Manager reach the administration surface, which is
// gated by two roles and must label itself with both.
const owner = loadLanding(["Course Owner"]);
assert.strictEqual(countByClass(owner.root, "th-card"), 1,
	"a Course Owner must see the administration control centre");
assert(allText(owner.root).includes("Course Owner / General Manager"),
	"the shared surface must name both roles that can open it");

// The empty state is the outcome nine shipped roles actually hit. It must not
// claim the account has no role - the auditors and Finance Officer have desk
// workspaces, so that wording sends them to ask for something they already have.
const auditor = loadLanding(["Finance Auditor"]);
assert.strictEqual(countByClass(auditor.root, "th-card"), 0,
	"an auditor has no command page and must not be shown one");
assert(countByClass(auditor.root, "th-empty") === 1, "an empty state must render instead of a blank page");
const emptyText = allText(auditor.root);
assert(!/no TOEFL House operational role/i.test(emptyText),
	"must not claim the account has no role - it has one, just no command page");
assert(/workspace/i.test(emptyText), "must point to the Desk sidebar workspaces that remain available");

// An account with genuinely no role still gets a clear, non-blank outcome.
const none = loadLanding([]);
assert(countByClass(none.root, "th-empty") === 1, "a roleless account must see the empty state");

console.log("Design system and response-projection contract OK");
