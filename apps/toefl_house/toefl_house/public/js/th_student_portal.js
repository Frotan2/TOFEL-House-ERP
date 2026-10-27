/* Student self-service portal — mobile-first, owner-authorized reads only */
(() => {
  "use strict";
  const portal = document.getElementById("student-portal");
  if (!portal || !portal.querySelector("[data-pane]")) return;

  let tabRequest = 0;
  const tabs = portal.querySelectorAll("[data-tab]");
  const panes = portal.querySelectorAll("[data-pane]");

  tabs.forEach(t => t.addEventListener("click", () => {
    const tab = t.dataset.tab;
    tabs.forEach(x => x.classList.remove("active"));
    panes.forEach(p => p.classList.toggle("d-none", p.dataset.pane !== tab));
    t.classList.add("active");
    loadTab(tab);
  }));

  function api(method, args) {
    return frappe.call({ method, args }).then(r => r.message);
  }

  function loadTab(tab) {
    const pane = portal.querySelector(`[data-pane="${tab}"]`);
    if (!pane) return;
    const request = ++tabRequest;
    const loading = document.createElement("em");
    loading.textContent = "Loading…";
    pane.replaceChildren(loading);
    let promise;
    if (tab === "schedule") promise = api("toefl_house.operations.student_portal.get_my_schedule");
    else if (tab === "attendance") promise = api("toefl_house.operations.student_portal.get_my_attendance");
    else if (tab === "grades") promise = api("toefl_house.operations.student_portal.get_my_grades");
    else if (tab === "fees") promise = api("toefl_house.operations.student_portal.get_my_fees").then(d => (d.fees || []).concat(d.invoices || []));
    else return;
    promise.then(items => {
      if (request !== tabRequest) return;
      window.TH_PORTAL_VIEW.renderList(pane, items, tab, "No records found.");
    }).catch(() => {
      if (request !== tabRequest) return;
      const alert = document.createElement("div");
      alert.className = "alert alert-danger";
      alert.textContent = "Access denied or portal disabled.";
      pane.replaceChildren(alert);
    });
  }

  // Announcements load immediately
  frappe.call({ method: "toefl_house.operations.student_portal.get_announcements" }).then(r => {
    const el = document.getElementById("portal-announcements");
    if (!el) return;
    const items = r.message || [];
    el.replaceChildren();
    if (!items.length) return;
    const heading = document.createElement("h6");
    heading.textContent = "Announcements";
    el.appendChild(heading);
    items.forEach(item => {
      const alert = document.createElement("div");
      alert.className = "alert alert-info";
      const title = document.createElement("strong");
      title.textContent = String(item.title || "");
      alert.appendChild(title);
      alert.appendChild(document.createElement("br"));
      alert.appendChild(document.createTextNode(String(item.message || "")));
      el.appendChild(alert);
    });
  }).catch(() => {
    // Portal reads remain independently authorized; an announcement failure
    // must not prevent schedule or attendance from loading.
  });

  // Load initial tab
  loadTab("schedule");
})();
