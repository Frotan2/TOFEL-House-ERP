"use strict";
// Course assessment page smoke: run the shipped page in a minimal Frappe
// facade. Proves teachers see student names next to IDs, and that Academic
// staff can correct one recorded mark (submitted/reviewed books only) through
// the guarded correct_assessment_mark command with a mandatory reason.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SCRIPT = path.join(__dirname, "../../apps/toefl_house/toefl_house/public/js/th_course_assessment.js");
const source = fs.readFileSync(SCRIPT, "utf8");

function makeHarness(roles, state) {
	const buttons = [];
	const cells = [];
	const prompts = [];
	const posts = [];
	function jq(markup) {
		let label = "";
		const chain = {
			0: { contains: () => true },
			text(value) {
				if (value === undefined) return label;
				label = String(value);
				if (String(markup).startsWith("<td")) cells.push(label);
				return chain;
			},
			on(event, callback) {
				if (event === "click" && String(markup).startsWith("<button")) buttons.push({ label, click: callback });
				return chain;
			},
			appendTo() { return chain; }, prependTo() { return chain; }, addClass() { return chain; },
			attr() { return chain; }, prop() { return chain; }, val() { return chain; },
			empty() { return chain; }, remove() { return chain; }, find() { return chain; },
		};
		return chain;
	}
	const flush = () => new Promise((resolve) => setImmediate(resolve));
	const context = {
		__: (text, args) => (args || []).reduce((out, value, index) => out.replace(`{${index}}`, value), text),
		$: jq,
		crypto: { randomUUID: () => "11111111-2222-3333-4444-555555555555" },
		fetch: async (url, options) => {
			posts.push({ url, body: JSON.parse(options.body) });
			return { status: 200, ok: true, json: async () => ({ message: { name: state.name } }) };
		},
		frappe: {
			pages: { "th-course-assessment": {} },
			user_roles: roles,
			csrf_token: "token",
			ui: {
				make_app_page: () => ({ body: jq("<div") }),
				form: { make_control: () => ({ get_value: () => state.name, set_value: async () => {} }) },
				Dialog: class { show() {} },
			},
			call: async () => ({ message: state }),
			prompt: (fields, callback, title) => prompts.push({ fields, callback, title }),
			confirm: () => {},
		},
	};
	vm.runInNewContext(source, context, { filename: SCRIPT });
	context.frappe.pages["th-course-assessment"].on_page_load({});
	return { buttons, cells, prompts, posts, flush };
}

(async () => {
	const book = {
		name: "TH-AB-0001", status: "Submitted", student_group: "SYN-GRP-1", policy: "SYN-POL",
		policy_effective_from: "2026-09-01",
		students: ["STU-1", "STU-2"], student_names: { "STU-1": "Ahmad Karimi" },
		components: [{ code: "FINAL", maximum_score: 100 }],
		marks: [{ student: "STU-1", component: "FINAL", mark: 70, missing_reason: "" },
			{ student: "STU-2", component: "FINAL", mark: 50, missing_reason: "" }],
		results: [],
	};

	const manager = makeHarness(["Academic Manager"], book);
	manager.buttons.find((button) => button.label === "Load book").click();
	await manager.flush();
	assert(manager.cells.includes("Ahmad Karimi (STU-1)"), "named students show name and ID");
	assert(manager.cells.includes("STU-2"), "a student without a roster name shows by ID");
	const corrections = manager.buttons.filter((button) => button.label === "Correct");
	assert.strictEqual(corrections.length, 2, "each recorded mark offers one correction action");
	corrections[0].click();
	const prompt = manager.prompts.at(-1);
	assert.strictEqual(JSON.stringify(prompt.fields.map((field) => field.fieldname)), JSON.stringify(["mark", "missing_reason", "reason"]));
	assert(prompt.fields.find((field) => field.fieldname === "reason").reqd, "a correction reason is mandatory");
	prompt.callback({ mark: 150, reason: "Typo" });
	prompt.callback({ mark: 80, missing_reason: "Absent", reason: "Typo" });
	assert.strictEqual(manager.posts.length, 0, "out-of-range or ambiguous corrections never reach the server");
	prompt.callback({ mark: 0, reason: "Re-marked paper" });
	await manager.flush();
	assert.strictEqual(manager.posts.length, 1);
	assert.strictEqual(manager.posts[0].url, "/api/method/toefl_house.academic.assessment.correct_assessment_mark");
	const { request_key: key, ...args } = manager.posts[0].body;
	assert(/^[A-Za-z0-9_-]{16,96}$/.test(key), "request key meets the server safe-key shape");
	assert.deepStrictEqual(args, { book: "TH-AB-0001", student: "STU-1", component: "FINAL",
		mark: 0, missing_reason: "", reason: "Re-marked paper" });

	const teacher = makeHarness(["Instructor"], book);
	teacher.buttons.find((button) => button.label === "Load book").click();
	await teacher.flush();
	assert(!teacher.buttons.some((button) => button.label === "Correct"), "instructors cannot correct a submitted book");

	const approved = makeHarness(["Academic Manager"], { ...book, status: "Approved" });
	approved.buttons.find((button) => button.label === "Load book").click();
	await approved.flush();
	assert(!approved.buttons.some((button) => button.label === "Correct"), "approved books use the published correction process");

	const published = makeHarness(["Academic Manager"], { ...book, status: "Published",
		results: [{ name: "RES-1", student: "STU-1", status: "Published", outcome: "Pass", overall_percent: 70 },
			{ name: "RES-0", student: "STU-2", status: "Superseded", outcome: "Fail", overall_percent: 40 }] });
	published.buttons.find((button) => button.label === "Load book").click();
	await published.flush();
	const fixes = published.buttons.filter((button) => button.label === "Correct published result");
	assert.strictEqual(fixes.length, 1, "only the current published revision can be corrected");
	fixes[0].click();
	const fix = published.prompts.at(-1);
	fix.callback({ component: "FINAL", mark: 101, reason: "Re-marked" });
	assert.strictEqual(published.posts.length, 0, "out-of-range published corrections never reach the server");
	fix.callback({ component: "FINAL", mark: 75, reason: "Re-marked" });
	await published.flush();
	assert.strictEqual(published.posts[0].url, "/api/method/toefl_house.academic.assessment.correct_published_result");
	const { request_key: _key, ...fixArgs } = published.posts[0].body;
	assert.deepStrictEqual(fixArgs, { book: "TH-AB-0001", student: "STU-1",
		marks: [{ component: "FINAL", mark: 75 }], reason: "Re-marked" });

	console.log("Course assessment page smoke OK");
})().catch((error) => {
	console.error(error);
	process.exit(1);
});
