/* Static contract for the D10 native Page surfaces. No Frappe site is needed. */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "../..");
const APP = path.join(ROOT, "apps/toefl_house/toefl_house");
const SCRIPT = path.join(APP, "public/js/th_command_pages.js");
const HOOKS = path.join(APP, "hooks.py");
const SECURITY = path.join(APP, "security.py");
const PYPROJECT = path.join(ROOT, "apps/toefl_house/pyproject.toml");
const NATIVE_CHECKS = path.join(ROOT, "tools/placement/native_checks.py");

const expected = {
	"th-administration-control-centre": { module: "Placement", roles: ["Course Owner", "General Manager"] },
	"th-command-centre": { module: "Placement", roles: ["Placement Author", "Placement Publisher", "Placement Invigilator", "Placement Assessor", "Placement Reviewer", "Placement Releaser", "Admission Officer", "Admission Reviewer", "Admission Approver", "Enrollment Officer", "Teaching Scheduler", "Attendance Recorder"] },
	"th-placement-author": { module: "Placement", roles: ["Placement Author"] },
	"th-placement-publisher": { module: "Placement", roles: ["Placement Publisher"] },
	"th-placement-invigilation": { module: "Placement", roles: ["Placement Invigilator"] },
	"th-placement-assessment": { module: "Placement", roles: ["Placement Assessor"] },
	"th-placement-review": { module: "Placement", roles: ["Placement Reviewer"] },
	"th-placement-release": { module: "Placement", roles: ["Placement Releaser"] },
	"th-admission-officer": { module: "Admission", roles: ["Admission Officer"] },
	"th-admission-review": { module: "Admission", roles: ["Admission Reviewer"] },
	"th-admission-approval": { module: "Admission", roles: ["Admission Approver"] },
	"th-enrollment": { module: "Enrollment", roles: ["Enrollment Officer"] },
	"th-teaching-scheduling": { module: "Teaching", roles: ["Teaching Scheduler"] },
	"th-attendance-recording": { module: "Teaching", roles: ["Attendance Recorder"] },
};

function walk(dir) {
	return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const file = path.join(dir, entry.name);
		return entry.isDirectory() ? walk(file) : [file];
	});
}

function loadSurfaces(source) {
	const sandbox = { frappe: { pages: {} } };
	sandbox.frappe.provide = (dotted) => {
		let target = sandbox;
		for (const part of dotted.split(".")) target = target[part] ||= {};
	};
	vm.runInNewContext(source, sandbox, { filename: SCRIPT });
	return sandbox.toefl_house.command_pages.surfaces;
}

const source = fs.readFileSync(SCRIPT, "utf8");
const surfaces = loadSurfaces(source);
assert.deepStrictEqual(Object.keys(surfaces).sort(), Object.keys(expected).sort(), "surface set changed");

const roleFixture = new Set(JSON.parse(fs.readFileSync(path.join(APP, "fixtures/role.json"), "utf8")).map((row) => row.name));
for (const [name, shape] of Object.entries(expected)) {
	const file = walk(APP).find((candidate) => candidate.endsWith(`${name.replaceAll("-", "_")}.json`) && candidate.includes(`${path.sep}page${path.sep}`));
	assert(file, `missing native Page JSON for ${name}`);
	const page = JSON.parse(fs.readFileSync(file, "utf8"));
	assert.strictEqual(page.doctype, "Page", name);
	assert.strictEqual(page.name, name, name);
	assert.strictEqual(page.page_name, name, name);
	assert.strictEqual(page.standard, "Yes", name);
	assert.strictEqual(page.module, shape.module, name);
	assert.deepStrictEqual(page.roles.map((row) => row.role), shape.roles, name);
	for (const role of shape.roles) assert(roleFixture.has(role), `${name} references unshipped role ${role}`);
	const surface = surfaces[name];
	assert(surface, `${name} missing client surface`);
	if (surface.landing || surface.admin) assert.deepStrictEqual(Array.from(surface.roles), shape.roles, name);
	else assert.strictEqual(surface.role, shape.roles[0], name);
}

/*
 * The hosted qualification in tools/placement/native_checks.py pins each Page's
 * audience in PAGE_SPEC and asserts it against the installed Page, including a
 * negative control that audit and finance audiences receive no command page at
 * all. Nothing in this suite used to look at that file, so a Page audience could
 * be edited here and pass every local check while breaking hosted evidence.
 *
 * That is not hypothetical: widening th-command-centre to every shipped role
 * passed all 703 local tests and both Node contracts, and would have failed
 * `release-command-pages-configured` and `release-command-page-role-visibility`,
 * invalidating recorded proof. This tie makes that divergence a local failure.
 */
const nativeChecks = fs.readFileSync(NATIVE_CHECKS, "utf8");
const specBlock = /^ {8}PAGE_SPEC=\{([\s\S]*?)\n {8}\}/m.exec(nativeChecks);
assert(specBlock, "could not locate PAGE_SPEC in native_checks.py");
const pageSpec = {};
for (const [, page, module, roleList] of specBlock[1].matchAll(/'([\w-]+)':\('(\w+)',\{([^}]*)\}\)/g)) {
	pageSpec[page] = {
		module,
		roles: roleList.split(",").map((role) => role.trim().replace(/^'|'$/g, "")).filter(Boolean).sort(),
	};
}
// PAGE_SPEC covers the 13 D10 command pages. th-administration-control-centre is
// deliberately absent: it is a governance surface qualified by
// test_governance_surface.py, not a command page, so it must not be forced into
// the command-page contract here.
const ADMIN_PAGE = "th-administration-control-centre";
assert(!(ADMIN_PAGE in pageSpec),
	"the governance page must stay out of the command-page PAGE_SPEC");
assert.strictEqual(Object.keys(pageSpec).length, Object.keys(expected).length - 1,
	"native_checks PAGE_SPEC and the shipped command-page set have diverged in size");

for (const [name, shape] of Object.entries(expected)) {
	if (name === ADMIN_PAGE) continue;
	const spec = pageSpec[name];
	assert(spec, `${name} ships a Page but native_checks.py does not qualify it`);
	assert.strictEqual(spec.module, shape.module, `${name} module differs from PAGE_SPEC`);
	assert.deepStrictEqual([...shape.roles].sort(), spec.roles,
		`${name} audience differs from the audience qualified by native_checks.py`);
}

const hooks = fs.readFileSync(HOOKS, "utf8");
assert(hooks.includes('app_home = "/app/th-command-centre"'), "app home must route to the role-filtered command centre");
for (const name of Object.keys(expected)) {
	assert(hooks.includes(`"${name}"`), `page_js must explicitly map ${name}`);
}
assert(hooks.includes('page_js = {name: "public/js/th_command_pages.js" for name in _COMMAND_PAGES}'), "all pages must use the one reviewed client");

const pyproject = fs.readFileSync(PYPROJECT, "utf8");
assert(pyproject.includes('"*/page/*/*.json"'), "Page JSON must ship in package data");
assert(pyproject.includes('"public/js/*.js"'), "Page JavaScript must ship in package data");

// Every command that a D10 API-first role can dispatch is represented on that
// role's Page. `dispatches` models the concrete command kind for generic
// config endpoints, which select blueprint/policy/course-map only server-side.
const kindRoles = {};
const kindRoleSource = fs.readFileSync(SECURITY, "utf8").split("KINDS = set(KIND_ROLES)", 1)[0];
for (const [, kind, role] of kindRoleSource.matchAll(/^\s+"([a-z_]+)":\s+"([^"]+)",/gm)) kindRoles[kind] = role;
const pageRoles = new Set(Object.values(expected).flatMap((entry) => entry.roles).filter((role) => role !== undefined));
for (const [name, surface] of Object.entries(surfaces)) {
	if (surface.landing || surface.admin) {
		assert(!surface.commands, "navigation/admin page may not dispatch business commands");
		continue;
	}
	assert(Array.isArray(surface.commands) && surface.commands.length, `${name} needs command forms`);
	const kinds = new Set(surface.commands.flatMap((command) => command.dispatches));
	const expectedKinds = Object.entries(kindRoles).filter(([, role]) => role === surface.role).map(([kind]) => kind);
	assert.deepStrictEqual(Array.from(kinds).sort(), expectedKinds.sort(), `${name} command coverage differs from KIND_ROLES`);
	for (const command of surface.commands) {
		assert(/^toefl_house\.(api|admission|enrollment|teaching)(\.[a-z_]+)+$/.test(command.method), `${name} has an unreviewed endpoint`);
		assert(Array.isArray(command.fields), `${name} command needs explicit form fields`);
		for (const kind of command.dispatches) assert.strictEqual(kindRoles[kind], surface.role, `${name} exposes ${kind} for the wrong role`);
	}
}

// The dialog schema must be an exact transport adapter for the reviewed
// whitelisted function signatures. Request keys come from the shared dialog
// helper and therefore are intentionally not a visible business-data field.
const endpointFiles = {
	api: path.join(APP, "api.py"),
	admission: path.join(APP, "admission/__init__.py"),
	enrollment: path.join(APP, "enrollment/__init__.py"),
	teaching: path.join(APP, "teaching/__init__.py"),
	"teaching.compensation": path.join(APP, "teaching/compensation.py"),
};
function endpointSignature(method) {
	const parts = method.split(".");
	const func = parts.pop();
	const module = parts.slice(1).join(".");
	const endpointSource = fs.readFileSync(endpointFiles[module], "utf8");
	const found = new RegExp(`^def\\s+${func}\\(([^)]*)\\):`, "m").exec(endpointSource);
	assert(found, `could not resolve ${method} in its owned endpoint module`);
	const position = found.index;
	assert(endpointSource.slice(Math.max(0, position - 500), position).includes("@frappe.whitelist"), `${method} must remain whitelisted`);
	return found[1].split(",").map((arg) => arg.trim().split("=")[0]).filter(Boolean);
}
for (const [name, surface] of Object.entries(surfaces)) {
	if (surface.landing || surface.admin) continue;
	for (const command of surface.commands) {
		const signature = endpointSignature(command.method);
		assert.strictEqual(signature[0], "request_key", `${command.method} must be idempotent`);
		assert.deepStrictEqual(
			Array.from(command.fields, (field) => field.fieldname), signature.slice(1),
			`${name} field schema must exactly match ${command.method}`,
		);
	}
}

// No DocType/read endpoint is introduced by the UI. The sole remote primitive
// is frappe.call, pointed at the reviewed endpoint registry above.
for (const forbidden of [/frappe\.db\b/, /frappe\.client\b/, /frappe\.get_doc\b/, /frappe\.get_list\b/, /\bfetch\s*\(/, /XMLHttpRequest/, /frappe\.set_route\(\s*["']List/]) {
	assert(!forbidden.test(source), `command page contains forbidden read/CRUD primitive: ${forbidden}`);
}
assert(source.includes("frappe.call({"), "command page must use guarded RPC rather than direct document writes");
assert(source.includes("request_key"), "command page must preserve idempotent request-key input");
assert(source.includes("fieldtype: \"Data\""), "identifier inputs must remain plain Data controls, not Link lookups");

console.log(`D10 command-page contract OK (${Object.keys(surfaces).length} pages)`);

// Client smoke: load one Page in a minimal native-Frappe façade, invoke its
// first button, and retry after an RPC error. This proves the registered page
// handler constructs a native Dialog and preserves the same idempotency key
// rather than falling back to a document API or generating a new key.
const buttons = [];
const dialogs = [];
const calls = [];
function jq(markup) {
	const chain = {
		on(event, callback) { if (event === "click" && String(markup).startsWith("<button")) buttons.push(callback); return chain; },
		prop() { return chain; }, attr() { return chain; }, addClass() { return chain; },
		text() { return chain; }, appendTo() { return chain; }, empty() { return chain; }, append() { return chain; },
	};
	return chain;
}
class Dialog {
	constructor(options) { this.options = options; dialogs.push(this); }
	show() { this.shown = true; }
	hide() { this.hidden = true; }
	get_values() {
		return Object.fromEntries(this.options.fields.map((field) => [field.fieldname, field.default ?? (field.fieldtype === "Check" ? 1 : `SYN-${field.fieldname}`)]));
	}
}
const client = {
	__: (label) => label,
	window: { crypto: { getRandomValues(bytes) { for (let i = 0; i < bytes.length; i++) bytes[i] = i + 1; return bytes; } } },
	$: jq,
	frappe: {
		pages: {}, user_roles: ["Placement Invigilator"],
		provide(dotted) { let target = client; for (const part of dotted.split(".")) target = target[part] ||= {}; },
		// Frappe's real signature is require(paths, callback?) - the callback is
		// optional, and app asset loading legitimately passes none.
		require(_paths, callback) { if (callback) callback(); },
		ui: { make_app_page() { return { main: jq("<main") }; }, Dialog },
		msgprint() { throw new Error("authorized invigilator should render actions"); },
		show_alert() {},
		call(options) { calls.push(options); },
	},
};
vm.runInNewContext(source, client, { filename: SCRIPT });
client.frappe.pages["th-placement-invigilation"].on_page_load({});
assert.strictEqual(buttons.length, 4, "invigilation Page must render its four guarded actions");
buttons[0]();
assert.strictEqual(dialogs.length, 1, "action must open a native Dialog");
assert(dialogs[0].shown, "native Dialog must be shown");
dialogs[0].options.primary_action(dialogs[0].get_values());
dialogs[0].options.primary_action(dialogs[0].get_values());
assert.strictEqual(calls.length, 2, "failed action must remain retryable");
assert.strictEqual(calls[0].method, "toefl_house.api.verify_attempt");
assert.strictEqual(calls[0].args.request_key, calls[1].args.request_key, "retry must preserve request_key");
assert(/^[A-Za-z0-9]{24}$/.test(calls[0].args.request_key), "generated request_key must meet server safe-key shape");
assert(!dialogs[0].hidden, "RPC error must not close a retryable command dialog");

console.log("D10 native-dialog client smoke OK");
