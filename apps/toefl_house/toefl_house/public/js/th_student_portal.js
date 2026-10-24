/* Student self-service portal — mobile-first, owner-authorized reads only */
(() => {
  "use strict";
  const portal = document.getElementById("student-portal");
  if (!portal) return;

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

  function renderList(el, items, empty) {
    if (!items || !items.length) { el.innerHTML = `<p class="text-muted">${empty}</p>`; return; }
    el.innerHTML = "<ul class='list-group'>" + items.map(i =>
      `<li class="list-group-item">${Object.values(i).slice(0,4).join(" — ")}</li>`
    ).join("") + "</ul>";
  }

  function loadTab(tab) {
    const pane = portal.querySelector(`[data-pane="${tab}"]`);
    if (!pane || pane.dataset.loaded) return;
    let promise;
    if (tab === "schedule") promise = api("toefl_house.operations.student_portal.get_my_schedule");
    else if (tab === "attendance") promise = api("toefl_house.operations.student_portal.get_my_attendance");
    else if (tab === "grades") promise = api("toefl_house.operations.student_portal.get_my_grades");
    else if (tab === "fees") promise = api("toefl_house.operations.student_portal.get_my_fees").then(d => (d.fees || []).concat(d.invoices || []));
    else return;
    promise.then(items => {
      renderList(pane, items, "No records found.");
      pane.dataset.loaded = "1";
    }).catch(e => { pane.innerHTML = `<div class="alert alert-danger">${e.message || "Access denied or portal disabled."}</div>`; });
  }

  // Announcements load immediately
  frappe.call({ method: "toefl_house.operations.student_portal.get_announcements" }).then(r => {
    const el = document.getElementById("portal-announcements");
    if (!el) return;
    const items = r.message || [];
    if (!items.length) { el.innerHTML = ""; return; }
    el.innerHTML = "<h6>Announcements</h6>" + items.map(a => `<div class="alert alert-info"><strong>${frappe.utils.escape_html(a.title||"")}</strong><br>${a.message||""}</div>`).join("");
  });

  // Load initial tab
  loadTab("schedule");
})();
