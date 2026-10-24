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
    el.replaceChildren();
    if (!items || !items.length) {
      const msg = document.createElement("p");
      msg.className = "text-muted";
      msg.textContent = empty;
      el.appendChild(msg);
      return;
    }
    const list = document.createElement("ul");
    list.className = "list-group";
    items.forEach(item => {
      const li = document.createElement("li");
      li.className = "list-group-item";
      li.textContent = Object.values(item).slice(0, 4).map(v => String(v ?? "")).join(" — ");
      list.appendChild(li);
    });
    el.appendChild(list);
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
    }).catch(() => {
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
  });

  // Load initial tab
  loadTab("schedule");
})();
