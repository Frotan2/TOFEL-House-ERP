/*
 * Contract for the role-desk product layer (docs/product/ROLE-DESKS.md).
 *
 * Pinned here, offline:
 *
 * 1. The tie-out: the client SURFACES, the shipped Page JSON files, the
 *    Python DESKS registry in desk/__init__.py and the hooks wiring must
 *    agree — the lesson of the command-centre audience incident is that a
 *    surface defined in three places drifts unless one test reads all three.
 * 2. The guided actions: every dialog maps a real, whitelisted owned command
 *    endpoint with exactly its reviewed signature, and a fresh idempotency
 *    key is generated per submit.
 * 3. The behavior: sections render real payload data escaped (a hostile
 *    record name must never become markup), every section has an explicit
 *    empty state, a failed desk load renders an actionable error with a
 *    retry instead of a hanging spinner, and a successful guided action
 *    refreshes the desk.
 * 4. No forbidden read/CRUD primitive: the desks read through their one
 *    whitelisted projection endpoint per desk, nothing else.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "../..");
const APP = path.join(ROOT, "apps/toefl_house/toefl_house");
const SCRIPT = path.join(APP, "public/js/th_role_desks.js");
const HOOKS = path.join(APP, "hooks.py");
const DESK_INIT = path.join(APP, "desk/__init__.py");

const EXPECTED = {
	"th-reception-desk": {
		title: "TOEFL House Reception Desk",
		roles: ["Reception"],
		endpoint: "toefl_house.desk.reception.work",
		python: "toefl_house.desk.reception",
	},
	"th-academic-desk": {
		title: "TOEFL House Academic Desk",
		roles: ["Academic Manager"],
		endpoint: "toefl_house.desk.academic.work",
		python: "toefl_house.desk.academic",
	},
	"th-finance-desk": {
		title: "TOEFL House Finance Desk",
		roles: ["Finance Manager"],
		endpoint: "toefl_house.desk.finance.work",
		python: "toefl_house.desk.finance",
	},
	"th-operations-desk": {
		title: "TOEFL House Operations Desk",
		roles: ["General Manager"],
		endpoint: "toefl_house.desk.operations.work",
		python: "toefl_house.desk.operations",
	},
	"th-owner-cockpit": {
		title: "TOEFL House Owner Cockpit",
		roles: ["Course Owner"],
		endpoint: "toefl_house.desk.owner.cockpit",
		python: "toefl_house.desk.owner",
	},
	"th-academic-setup": {
		title: "TOEFL House Academic Setup",
		roles: ["Course Owner"],
		endpoint: "toefl_house.desk.setup.work",
		python: "toefl_house.desk.setup",
	},
};

/* ------------------------------------------------------------------ loading */

function loadClient(frappeOverrides = {}) {
	const client = {};
	client.__ = (label) => label;
	client.window = { crypto: { getRandomValues(bytes) { for (let i = 0; i < bytes.length; i++) bytes[i] = i + 1; return bytes; } } };
	client.frappe = {
		pages: {},
		provide(dotted) { let target = client; for (const part of dotted.split(".")) target = target[part] ||= {}; },
		require() {},
		msgprint() {},
		set_route() {},
		call() {},
		ui: { make_app_page: () => ({ body: {}, main: { addClass() {} } }), Dialog: class { show() {} hide() {} set_value() {} } },
		...frappeOverrides,
	};
	vm.runInNewContext(fs.readFileSync(SCRIPT, "utf8"), client, { filename: SCRIPT });
	return client;
}

/* ------------------------------------------------------- static tie-out */

const client = loadClient();
const surfaces = client.toefl_house.role_desks.surfaces;
assert.deepStrictEqual(Object.keys(surfaces).sort(), Object.keys(EXPECTED).sort(),
	"the desk surface set changed");

const deskInit = fs.readFileSync(DESK_INIT, "utf8");
const registryBlock = deskInit.split("DESKS = {")[1].split("\n}\n")[0];
for (const [slug, shape] of Object.entries(EXPECTED)) {
	assert(registryBlock.includes(`"${slug}"`), `${slug} missing from the Python DESKS registry`);
	assert(registryBlock.includes(`"${shape.roles[0]}"`), `${slug} audience missing from DESKS`);
	const pagePath = path.join(APP, "operations/page", slug, `${slug}.json`);
	const page = JSON.parse(fs.readFileSync(pagePath, "utf8"));
	assert.strictEqual(page.doctype, "Page", slug);
	assert.strictEqual(page.module, "Operations", slug);
	assert.strictEqual(page.title, shape.title, slug);
	assert.deepStrictEqual(page.roles.map((row) => row.role), shape.roles, slug);
	assert.strictEqual(surfaces[slug].endpoint, shape.endpoint, slug);
	assert(surfaces[slug].title === shape.title, `${slug} client title drift`);
}

/* D1 recurrence guard: every read endpoint the client calls by name must
 * exist in its desk module AND carry the real @frappe.whitelist decorator —
 * an unexposed function passes every stubbed in-process test and still
 * fails at the API layer on a real bench (the Academic Setup incident). */
for (const [slug, shape] of Object.entries(EXPECTED)) {
	const parts = shape.endpoint.split(".");
	const func = parts.pop();
	const deskModule = parts.pop();
	assert.strictEqual(parts.join("."), "toefl_house.desk", `${slug}: unexpected endpoint path`);
	const py = fs.readFileSync(path.join(APP, "desk", `${deskModule}.py`), "utf8");
	const found = new RegExp(`^def\\s+${func}\\(`, "m").exec(py);
	assert(found, `${shape.endpoint}: function is missing from desk/${deskModule}.py`);
	assert(py.slice(Math.max(0, found.index - 200), found.index).includes("@frappe.whitelist"),
		`${shape.endpoint} must stay whitelisted for the browser to call it`);
}
assert(/@frappe\.whitelist\([^\n]*\)\ndef available\(/.test(deskInit),
	"the desk registry read (toefl_house.desk.available) must stay whitelisted");
for (const [, method] of fs.readFileSync(SCRIPT, "utf8").matchAll(/"(toefl_house\.desk\.[\w.]+)"/g)) {
	const tail = method.split(".")[2];
	assert(["reception", "academic", "finance", "operations", "owner", "setup", "available"]
		.includes(tail), `desk client names an unresolvable module path: ${method}`);
}

const hooks = fs.readFileSync(HOOKS, "utf8");
for (const slug of Object.keys(EXPECTED)) {
	assert(hooks.includes(`"${slug}"`), `${slug} is not wired in hooks.py`);
}
assert(hooks.includes(`_DESK_PAGES = (`), "hooks must declare _DESK_PAGES for the desk pages");
assert(hooks.includes(`page_js.update({name: "public/js/th_role_desks.js" for name in _DESK_PAGES})`),
	"desk pages must use the reviewed desk client");

/* ------------------------------------------------- guided action tie-out */

const actionFields = client.toefl_house.role_desks.actionFields;
assert(Object.keys(actionFields).length >= 8, "guided actions went missing");

const endpointFiles = {
	"toefl_house.admission": ["admission/__init__.py"],
	"toefl_house.enrollment": ["enrollment/__init__.py"],
	"toefl_house.api": ["api.py"],
	"toefl_house.finance": ["finance/__init__.py"],
	"toefl_house.finance.corrections": ["finance/corrections.py"],
	"toefl_house.academic": ["academic/__init__.py"],
};
function signatureOf(method) {
	const parts = method.split(".");
	const func = parts.pop();
	const moduleKey = parts.join(".");
	const file = (endpointFiles[moduleKey] || [])[0];
	assert(file, `${method} does not resolve to a reviewed owned endpoint module`);
	const source = fs.readFileSync(path.join(APP, file), "utf8");
	const found = new RegExp(`^def\\s+${func}\\(([^)]*)\\):`, "m").exec(source);
	assert(found, `could not resolve ${func} in ${file}`);
	const position = found.index;
	assert(source.slice(Math.max(0, position - 500), position).includes("@frappe.whitelist"),
		`${method} must remain whitelisted`);
	return found[1].split(",").map((arg) => arg.trim().split("=")[0]).filter(Boolean);
}

for (const [method, fields] of Object.entries(actionFields)) {
	const signature = signatureOf(method);
	assert.strictEqual(signature[0], "request_key", `${method} must be idempotent`);
	// Array.from: `fields` comes from the vm realm and map() would keep its realm prototype.
	assert.deepStrictEqual(Array.from(fields, (field) => field.fieldname), signature.slice(1),
		`${method} dialog fields drift from the reviewed signature`);
}

/* Courtesy guards may only exist for real actions, and the one shipped must
 * mirror the server rule that conditions belong to Conditional outcomes. */
const actionGuards = client.toefl_house.role_desks.actionGuards;
for (const method of Object.keys(actionGuards)) {
	assert(actionFields[method], `a guard exists for an unknown action: ${method}`);
}
const decideGuard = actionGuards["toefl_house.admission.decide_admission"];
assert(decideGuard, "the decide_admission conditions guard went missing");
assert.strictEqual(decideGuard({ outcome: "Approved", conditions: "x" }),
	"Conditions are only recorded for Conditional outcomes.",
	"the guard must refuse conditions for a non-Conditional outcome");
assert.strictEqual(decideGuard({ outcome: "Conditional", conditions: "x" }), null);
assert.strictEqual(decideGuard({ outcome: "Approved", conditions: "" }), null);

/* The client may only call the desk projection endpoints and the registry. */
const source = fs.readFileSync(SCRIPT, "utf8");
for (const forbidden of [/frappe\.db\b/, /frappe\.client\b/, /frappe\.get_doc\b/, /frappe\.get_list\b/, /\bfetch\s*\(/, /XMLHttpRequest/, /frappe\.set_route\(\s*["']List/]) {
	assert(!forbidden.test(source), `desk client contains a forbidden primitive: ${forbidden}`);
}
assert(source.includes("frappe.call({"), "desk client must talk to the server over guarded RPC");
const allowedCalls = new Set([...Object.values(EXPECTED).map((shape) => shape.endpoint),
	client.toefl_house.role_desks.registry,
	...Object.keys(actionFields)]);
for (const method of Object.keys(actionFields)) {
	// The projection endpoint must resolve to a real owned module file.
	const parts = method.split(".");
	if (parts[1] === "desk") {
		const file = (endpointFiles[`toefl_house.desk.${parts[3]}`] || [])[0];
		assert(file || ["reception", "academic", "finance", "operations", "owner", "setup"]
			.includes(parts[3]), `unknown desk module ${method}`);
	}
}
for (const [, method] of source.matchAll(/method:\s*"([\w.]+)"/g)) {
	assert(allowedCalls.has(method), `desk client calls an unreviewed endpoint: ${method}`);
}

/* ------------------------------------------------------- behavior smoke */

const HOSTILE = "<img src=x onerror=alert(1)>";

/* A deliberately small DOM: each node is its own jQuery-like chain and keeps
 * its text plus raw appended HTML, so tests can assert content AND escaping. */
function makeNode(tag = "#fragment") {
	const node = {
		tag,
		children: [],
		texts: [],
		htmls: [],
		handlers: {},
		attrs: {},
		classes: [],
		__isNode: true,
		length: 1,
	};
	node.parentNodeData = null;
	node.parent = () => node.parentNodeData || makeNode("#orphan");
	node.appendTo = (parent) => { parent.children.push(node); node.parentNodeData = parent; return node; };
	node.append = (child) => {
		if (typeof child === "string") node.htmls.push(child);
		else if (child && child.children) { node.children.push(child); child.parentNodeData = node; }
		return node;
	};
	node.text = (value) => { if (value !== undefined) { node.texts.push(String(value)); return node; } return node.texts.join(""); };
	node.addClass = (name) => { node.classes.push(name); return node; };
	node.attr = (name, value) => { if (value !== undefined) { node.attrs[name] = value; return node; } return node.attrs[name]; };
	node.on = (event, callback) => { (node.handlers[event] = node.handlers[event] || []).push(callback); return node; };
	node.find = (selector) => {
		const byTag = !selector.startsWith(".");
		const needle = byTag ? selector : selector.slice(1);
		const found = [];
		(function walk(from) {
			for (const child of from.children) {
				if (byTag ? child.tag === needle : child.classes.includes(needle)) found.push(child);
				walk(child);
			}
		})(node);
		if (found[0]) return found[0];
		const missing = makeNode("#missing");
		missing.length = 0; // behave like an empty jQuery set
		return missing;
	};
	node.empty = () => { node.children = []; node.texts = []; node.htmls = []; return node; };
	node.remove = () => {
		if (node.parentNodeData) {
			const index = node.parentNodeData.children.indexOf(node);
			if (index >= 0) node.parentNodeData.children.splice(index, 1);
		}
		return node;
	};
	node.val = (value) => { if (value !== undefined) { node.attrs.value = value; return node; } return node.attrs.value || ""; };
	node.click = () => { (node.handlers.click || []).forEach((handler) => handler({ preventDefault() {} })); return node; };
	node.trigger = (type, data) => { (node.handlers[type] || []).forEach((handler) => handler(data || { preventDefault() {} })); return node; };
	return node;
}

/* Only the raw interpolated markup matters for XSS: .text() content is
 * escaped by the DOM by construction, so it is excluded here. */
function serializeRaw(start) {
	let out = "";
	(function walk(node) {
		for (const chunk of node.htmls) out += chunk;
		for (const child of node.children) walk(child);
	})(start);
	return out;
}

function findAll(start, classname) {
	const found = [];
	(function walk(node) { for (const child of node.children) { if (child.classes.includes(classname)) found.push(child); walk(child); } })(start);
	return found;
}

function serialize(start) {
	let out = "";
	(function walk(node) {
		out += node.texts.join("");
		for (const chunk of node.htmls) out += chunk;
		for (const child of node.children) walk(child);
	})(start);
	return out;
}

/* Minimal HTML parser so static markup like "<table><thead></thead>…" gets
 * a real tree: the client builds tables as static HTML and then .find()s into
 * them, exactly like it would against jQuery. */
function parseHtml(html) {
	const root = makeNode("#fragment");
	const stack = [root];
	const pattern = /<(\/)?([\w-]+)((?:[^>"]|"[^"]*")*)>/g;
	let last = 0;
	let match;
	while ((match = pattern.exec(html))) {
		const before = html.slice(last, match.index);
		if (before) stack[stack.length - 1].htmls.push(before);
		const [, closing, tag, attrs] = match;
		if (closing) {
			for (let i = stack.length - 1; i > 0; i--) {
				if (stack[i].tag === tag) { stack.length = i; break; }
			}
		} else {
			const node = makeNode(tag);
			const classes = /class=['"]([^'"]+)['"]/.exec(attrs);
			if (classes) node.classes.push(...classes[1].split(" "));
			const parent = stack[stack.length - 1];
			parent.children.push(node);
			node.parentNodeData = parent;
			stack.push(node);
		}
		last = pattern.lastIndex;
	}
	if (last < html.length) stack[stack.length - 1].htmls.push(html.slice(last));
	return root.children[0] || root;
}

function $(arg) {
	if (typeof arg === "string" && arg.startsWith("<")) return parseHtml(arg);
	if (arg && arg.__isNode) return arg;
	return makeNode();
}

function payloadWith(queueItems, factValue) {
	return {
		desk: "th-reception-desk",
		title: "TOEFL House Reception Desk",
		sections: [
			{
				id: "funnel", title: "Applicant funnel", kind: "facts",
				facts: [
					{ label: "Results awaiting intake", definition: `Released results for ${HOSTILE}`, value: factValue, owner: "Admission Officer" },
				],
				empty: { title: "empty-title", body: "empty-body" },
			},
			{
				id: "people", title: "People in the funnel", kind: "queue",
				items: queueItems,
				empty: { title: "No open applicants", body: "No applicant is in Applied status right now." },
			},
			{
				id: "handover", title: "Ready for admission intake", kind: "queue",
				items: [],
				empty: { title: "No released result is waiting", body: "Every released placement result is attached." },
			},
		],
	};
}

function runScenario({ workPayload, failFirstWork = false, failLookup = false }) {
	const calls = [];
	const dialogs = [];
	const routed = [];
	const printed = [];
	const body = $("body").appendTo({ children: [] });
	let workCalls = 0;
	const frappe = {
		pages: {},
		provide() {},
		require() {},
		set_route(route) { routed.push(route); },
		msgprint(opts) { printed.push(opts); },
		ui: {
			make_app_page() { return { body, main: { addClass() {} } }; },
			Dialog: class {
				constructor(opts) { this.opts = opts; this.values = {}; dialogs.push(this); }
				set_value(field, value) { this.values[field] = value; }
				show() {}
				hide() {}
				submit(values) { this.opts.primary_action(values); }
			},
		},
		call(opts) {
			calls.push(opts);
			if (opts.method === "toefl_house.desk.available") {
				opts.callback({ message: { desks: [{ slug: "th-finance-desk", title: "TOEFL House Finance Desk" }] } });
				return;
			}
			if (opts.method === "toefl_house.desk.reception.work") {
				workCalls += 1;
				if (failFirstWork && workCalls === 1) { opts.error(); return; }
				opts.callback({ message: workPayload });
				return;
			}
			if (opts.method === "toefl_house.desk.reception.lookup") {
				if (failLookup) { opts.error(); return; }
				opts.callback({ message: { items: [hostileItem], students: [] } });
				return;
			}
			if (opts.method === "toefl_house.admission.review_admission") {
				opts.callback({ message: { name: HOSTILE, status: HOSTILE } });
				return;
			}
			throw new Error(`unexpected call ${opts.method}`);
		},
	};
	const sandbox = {
		$: (arg) => $(arg),
		__: (label) => label,
		window: { crypto: { getRandomValues(bytes) { for (let i = 0; i < bytes.length; i++) bytes[i] = i + 1; return bytes; } } },
		frappe,
	};
	frappe.provide = (dotted) => { let target = sandbox; for (const part of dotted.split(".")) target = target[part] ||= {}; };
	vm.runInNewContext(fs.readFileSync(SCRIPT, "utf8"), sandbox, { filename: SCRIPT });
	frappe.pages["th-reception-desk"].on_page_load(body);
	return { calls, dialogs, routed, printed, body, frappe, get workCalls() { return workCalls; } };
}

const hostileItem = {
	id: "ADM-0001",
	person: HOSTILE,
	detail: "Program X",
	status: HOSTILE,
	stage: "Admission review",
	stage_definition: "Waiting for the approver",
	next: `Record the outcome for ${HOSTILE}`,
	next_role: "Admission Approver",
	waiting_since: "2026-09-17",
	action: {
		role: "Admission Reviewer",
		endpoint: "toefl_house.admission.review_admission",
		label: "Send for review",
		args: { name: "ADM-0001", expected_version: 2 },
	},
	actions: [
		{
			role: "Admission Reviewer",
			endpoint: "toefl_house.academic.set_next_level",
			label: `Set progression for ${HOSTILE}`,
			args: { level: "ADM-0001", next_level: "" },
		},
	],
};

{
	const scenario = runScenario({ workPayload: payloadWith([hostileItem], HOSTILE) });

	// The registry strip rendered the other desk and routes on click.
	assert.deepStrictEqual(scenario.routed, [], "no navigation before a click");
	const stripLinks = findAll(scenario.body, "th-desk-link");
	assert.strictEqual(stripLinks.length, 1, "the desk strip must render the registry answer");
	stripLinks[0].click();
	assert.deepStrictEqual(scenario.routed, ["th-finance-desk"], "the desk strip must route to the other desk");

	// Escaping: no hostile markup may survive as markup anywhere in the desk.
	const rendered = serialize(scenario.body);
	const renderedMarkup = serializeRaw(scenario.body);
	assert(!/<img\s/i.test(renderedMarkup), "hostile markup must never become an element");
	assert(rendered.includes("<img src=x onerror=alert(1)>"), "hostile text must still be shown (escaped, via .text)");
	assert(rendered.includes("Results awaiting intake"), "fact labels render");
	assert(rendered.includes("No released result is waiting"), "empty state renders for the empty section");
	assert(rendered.includes("Your desks:"), "the desk strip renders the registry answer");

	// Queue actions: the primary plus the contextual secondary the server
	// authorized; both are real mapped commands.
	const actionButtons = findAll(scenario.body, "th-queue-action");
	assert.strictEqual(actionButtons.length, 2,
		"exactly the server-authorized actions render (primary + secondary)");
	const before = scenario.calls.filter((call) => call.method === "toefl_house.admission.review_admission").length;
	actionButtons[0].click();
	assert.strictEqual(scenario.dialogs.length, 1, "the guided action opens one dialog");
	const dialog = scenario.dialogs[0];
	const fieldNames = Array.from(dialog.opts.fields, (field) => field.fieldname);
	assert.deepStrictEqual(fieldNames, ["request_key", "name", "expected_version"],
		"dialog must mirror the reviewed endpoint signature plus the request key");
	const requestKeyField = dialog.opts.fields[0];
	assert(requestKeyField.default && requestKeyField.default.length >= 16,
		"a fresh idempotency key must be pre-generated");
	assert.strictEqual(dialog.values.name, "ADM-0001", "the server prefill must reach the dialog");
	assert.strictEqual(dialog.values.expected_version, 2, "the version prefill must reach the dialog");
	dialog.submit({ request_key: requestKeyField.default, name: "ADM-0001", expected_version: 2 });
	const commandCalls = scenario.calls.filter((call) => call.method === "toefl_house.admission.review_admission");
	assert.strictEqual(commandCalls.length, before + 1, "the guarded command is submitted once");
	assert.strictEqual(commandCalls[0].args.request_key, requestKeyField.default,
		"the same idempotency key must be submitted");
	// The result dialog must escape a hostile server response too.
	assert.strictEqual(scenario.printed.length, 1, "the result projection prints once");
	const resultMessage = scenario.printed[0].message;
	assert(!/<img\s/i.test(resultMessage), "a hostile result must not become markup");
	assert(resultMessage.includes("&lt;img"), "a hostile result must be escaped");
	// A successful guided action refreshes the desk.
	assert(scenario.workCalls >= 2, "a successful guided action refreshes the desk");

	// The contextual secondary action opens its own mapped dialog with the
	// server's prefill (proving multi-action rows don't dead-end the Owner).
	actionButtons[1].click();
	assert.strictEqual(scenario.dialogs.length, 2, "the secondary action opens one dialog");
	const secondary = scenario.dialogs[1];
	assert.deepStrictEqual(
		Array.from(secondary.opts.fields, (field) => field.fieldname),
		["request_key", "level", "next_level"],
		"the secondary dialog mirrors its reviewed signature");
	assert.strictEqual(secondary.values.level, "ADM-0001",
		"the secondary prefill reaches the dialog");
}

{
	// Error path: a failed desk load renders an explicit error with retry,
	// and the retry recovers into the normal sections.
	const scenario = runScenario({ workPayload: payloadWith([], "3"), failFirstWork: true });
	const alerts = findAll(scenario.body, "th-alert--danger");
	assert(alerts.length >= 1, "a failed load must show an error alert");
	const rendered = serialize(scenario.body);
	assert(rendered.includes("could not be loaded"), "the error must say what happened");
	assert(rendered.includes("Retry"), "the error must offer a retry");
	const retryButtons = [];
	(function walk(node) {
		for (const child of node.children) {
			if (child.tag === "button" && serialize(child).includes("Retry")) retryButtons.push(child);
			walk(child);
		}
	})(scenario.body);
	assert.strictEqual(retryButtons.length, 1, "exactly one retry button");
	retryButtons[0].click();
	assert.strictEqual(scenario.workCalls, 2, "retry re-requests the desk");
	const renderedAfter = serialize(scenario.body);
	assert(renderedAfter.includes("Applicant funnel"), "the retry renders the desk");
}

{
	// Empty desk: every section explains itself instead of showing nothing.
	const scenario = runScenario({ workPayload: payloadWith([], "0") });
	const rendered = serialize(scenario.body);
	assert(rendered.includes("No open applicants"), "queue empty states render");
	assert(rendered.includes("No released result is waiting"), "handover empty state renders");
}

{
	// Reception search: the lookup renders into its own results container,
	// refuses short queries with guidance, and escapes hostile matches.
	const scenario = runScenario({ workPayload: payloadWith([], "0") });
	const searchInputs = findAll(scenario.body, "th-search-input");
	assert.strictEqual(searchInputs.length, 1, "the reception desk has one search box");
	const resultsBoxes = findAll(scenario.body, "th-search-results");
	assert.strictEqual(resultsBoxes.length, 1, "the search must own a persistent results container");
	const searchButtons = [];
	(function walk(node) {
		for (const child of node.children) {
			if (child.tag === "button" && serialize(child).includes("Search")) searchButtons.push(child);
			walk(child);
		}
	})(scenario.body);
	assert.strictEqual(searchButtons.length, 1, "one search button");

	// Too short: explicit guidance, no server call.
	searchInputs[0].attrs.value = "M";
	searchButtons[0].click();
	assert(serialize(scenario.body).includes("Type more of the name"),
		"a too-short query explains itself");
	assert(!scenario.calls.some((call) => call.method === "toefl_house.desk.reception.lookup"),
		"a too-short query must not reach the server");

	// Real query: server called with the trimmed value, results rendered.
	searchInputs[0].attrs.value = "  Mercedes  ";
	searchButtons[0].click();
	const lookups = scenario.calls.filter((call) => call.method === "toefl_house.desk.reception.lookup");
	assert.strictEqual(lookups.length, 1, "the lookup runs once");
	assert.strictEqual(lookups[0].args.query, "Mercedes", "the query must be trimmed before it is sent");
	const after = serialize(scenario.body);
	assert(after.includes("In the admission funnel"), "the funnel grouping renders");
	assert(after.includes("Send for review"), "a matching applicant offers its next action");

	// Failed lookup: honest note, nothing changed.
	const failed = runScenario({ workPayload: payloadWith([], "0"), failLookup: true });
	const failedInputs = findAll(failed.body, "th-search-input");
	const failedButtons = [];
	(function walk(node) {
		for (const child of node.children) {
			if (child.tag === "button" && serialize(child).includes("Search")) failedButtons.push(child);
			walk(child);
		}
	})(failed.body);
	failedInputs[0].attrs.value = "Mercedes";
	failedButtons[0].click();
	assert(serialize(failed.body).includes("Search failed"), "a failed lookup says so");
}

/* --------------------------------------------------------------- design */

const stylesheet = fs.readFileSync(path.join(APP, "public/css/th_design_system.css"), "utf8");
for (const rule of (".th-fact-grid", ".th-fact-definition", ".th-queue", ".th-queue-action-cell",
	".th-desk-strip", ".th-search-bar")) {
	assert(stylesheet.includes(rule), `design system is missing ${rule}`);
}
const narrow = /@media \(max-width: 767\.98px\)[\s\S]*$/.exec(stylesheet);
assert(narrow && narrow[0].includes(".th-queue"), "queue tables must reflow on narrow screens");
assert(narrow && /display: block/.test(narrow[0]), "the narrow layout must stack, not squish");
assert(stylesheet.includes(":focus-visible"), "keyboard focus must stay visible");

console.log(`Role desk contract OK (${Object.keys(EXPECTED).length} desks, ` +
	`${Object.keys(actionFields).length} guided actions)`);
