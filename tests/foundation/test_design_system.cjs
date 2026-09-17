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

console.log("Design system and response-projection contract OK");
