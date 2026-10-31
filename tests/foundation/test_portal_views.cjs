/* Offline DOM/promise harness, not a real browser or native Frappe test. */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const app = path.resolve(__dirname, "../../apps/toefl_house/toefl_house");
const script = name => fs.readFileSync(path.join(app, "public/js", name), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.handlers = {};
    this._text = "";
    this.id = "";
    this.value = "";
    const names = new Set();
    this.classList = {
      add: name => names.add(name),
      remove: name => names.delete(name),
      toggle: (name, force) => force ? names.add(name) : names.delete(name)
    };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this.children = []; this._text = ""; this.append(...children); }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  dispatch(name) { this.handlers[name]({ target: this }); }
}

function setup(kind) {
  const tabs = {}, panes = {};
  const root = new Element("div");
  root.id = kind + "-portal";
  for (const name of ["schedule", "attendance", "grades", "fees"]) {
    tabs[name] = new Element("a"); tabs[name].dataset.tab = name;
    panes[name] = new Element("div"); panes[name].dataset.pane = name;
    root.append(tabs[name], panes[name]);
  }
  root.querySelectorAll = selector => selector === "[data-tab]" ? Object.values(tabs) : Object.values(panes);
  root.querySelector = selector => {
    if (selector === "[data-pane]") return panes.schedule;
    const match = selector.match(/^\[data-pane="([^"]+)"\]$/);
    return match ? panes[match[1]] : null;
  };
  const roots = [root];
  const addRoot = id => { const el = new Element("div"); el.id = id; roots.push(el); return el; };
  if (kind === "student") addRoot("portal-announcements");
  else {
    addRoot("guardian-children"); addRoot("guardian-consent-status"); addRoot("guardian-announcements");
  }
  function find(el, id) {
    if (el.id === id) return el;
    for (const child of el.children) { const match = find(child, id); if (match) return match; }
    return null;
  }
  const document = {
    getElementById(id) { for (const el of roots) { const found = find(el, id); if (found) return found; } return null; },
    createElement: tag => new Element(tag),
    createTextNode: text => { const node = new Element("#text"); node.textContent = text; return node; }
  };
  const calls = [];
  const frappe = { call({ method, args }) {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    calls.push({ method, args: args || {}, resolve, reject });
    return promise;
  } };
  const context = { document, frappe, window: {}, console };
  vm.createContext(context);
  vm.runInContext(script("th_portal_view.js"), context);
  vm.runInContext(script("th_" + kind + "_portal.js"), context);
  const call = (suffix, student, index = 0) => {
    const result = calls.filter(c => c.method.endsWith(suffix) && (student === undefined || c.args.student === student))[index];
    assert(result, `missing ${suffix} for ${student}`);
    return result;
  };
  return { tabs, panes, document, calls, call };
}

async function studentTest() {
  const ui = setup("student");
  ui.call("get_announcements").resolve({ message: [] });
  ui.call("get_my_schedule").resolve({ message: [{
    name: "SESSION", student_group: "CLASS", course: "<img onerror=bad>", room: "R1",
    schedule_date: "2026-10-24", schedule_date_shamsi: "02 عقرب 1405",
    from_time: "09:00", to_time: "10:00", th_session_status: "Cancelled"
  }] });
  await flush();
  const text = ui.panes.schedule.textContent;
  for (const value of ["<img onerror=bad>", "02 عقرب 1405", "2026-10-24", "09:00", "10:00", "Cancelled"])
    assert(text.includes(value), `missing schedule ${value}`);
  assert(!ui.panes.schedule.children.some(child => child.tagName === "img"), "content must remain text");

  ui.tabs.attendance.dispatch("click");
  ui.call("get_my_attendance").resolve({ message: [{ date: "2026-10-24", date_shamsi: "02 عقرب 1405", status: "Present" }] });
  await flush();
  assert(ui.panes.attendance.textContent.includes("Attendance status: Present"));

  // Revisit twice: the newer result wins even if the old promise resolves last.
  ui.tabs.schedule.dispatch("click");
  ui.tabs.attendance.dispatch("click");
  ui.tabs.schedule.dispatch("click");
  ui.call("get_my_schedule", undefined, 2).resolve({ message: [{ th_session_status: "Scheduled" }] });
  await flush();
  ui.call("get_my_schedule", undefined, 1).resolve({ message: [{ th_session_status: "Cancelled" }] });
  await flush();
  assert(ui.panes.schedule.textContent.includes("Session status: Scheduled"));
  assert(!ui.panes.schedule.textContent.includes("Cancelled"));
}

async function guardianTest() {
  const ui = setup("guardian");
  ui.call("get_announcements_for_guardian").resolve({ message: [] });
  ui.call("get_my_children").resolve({ message: [{ name: "A", student_name: "Alice" }, { name: "B", student_name: "Bob" }] });
  await flush();
  ui.call("get_child_schedule", "A").resolve({ message: [{ course: "Alice class", th_session_status: "Postponed" }] });
  await flush();
  assert(ui.panes.schedule.textContent.includes("Alice class"));
  assert(ui.panes.schedule.textContent.includes("Postponed"));

  ui.tabs.attendance.dispatch("click"); // leave A's request and consent unresolved
  const select = ui.document.getElementById("child-select");
  select.value = "B"; select.dispatch("change");
  assert(!ui.panes.schedule.textContent.includes("Alice class"), "hidden panes must clear immediately");
  assert(ui.call("get_child_attendance", "B"), "the selected attendance tab must reload for B");
  assert(!ui.calls.some(c => c.method.endsWith("get_child_schedule") && c.args.student === "B"), "must not load hidden schedule");
  ui.call("get_child_attendance", "B").resolve({ message: [{ date: "2026-10-24", date_shamsi: "02 عقرب 1405", status: "Present" }] });
  ui.call("get_consent_status", "B").resolve({ message: { has_consent: true, expiry_date: "2027-01-01" } });
  await flush();
  ui.call("get_child_attendance", "A").resolve({ message: [{ status: "Absent", student_group: "Alice private class" }] });
  ui.call("get_consent_status", "A").resolve({ message: { has_consent: false } });
  await flush();
  assert(ui.panes.attendance.textContent.includes("Attendance status: Present"));
  assert(!ui.panes.attendance.textContent.includes("Absent"));
  assert(!ui.panes.attendance.textContent.includes("Alice"));
  assert(ui.document.getElementById("guardian-consent-status").textContent.includes("Consent active"));
}

async function main() {
  for (const kind of ["student", "guardian"]) {
    const html = fs.readFileSync(path.join(app, "www", kind + "_portal.html"), "utf8");
    assert(html.indexOf("th_portal_view.js") >= 0 && html.indexOf("th_portal_view.js") < html.indexOf("th_" + kind + "_portal.js"));
  }
  await studentTest();
  await guardianTest();
  console.log("Portal DOM/promise contracts OK (student rendering, guardian switch/consent races)");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
