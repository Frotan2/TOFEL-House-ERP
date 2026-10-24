/* Guardian self-service portal — verified relationship + consent gating */
(() => {
  "use strict";
  const portal = document.getElementById("guardian-portal");
  if (!portal) return;

  let currentStudent = null;

  function api(method, args) {
    return frappe.call({ method, args }).then(r => r.message);
  }

  // Load children
  api("toefl_house.operations.guardian_portal.get_my_children").then(children => {
    const el = document.getElementById("guardian-children");
    if (!children || !children.length) { el.innerHTML = "<p class='text-muted'>No verified children linked to your guardian profile.</p>"; return; }
    el.innerHTML = "<label>Select child:</label><select id='child-select' class='form-control'>" +
      children.map(c => `<option value="${c.name}">${frappe.utils.escape_html(c.student_name||c.name)}</option>`).join("") + "</select>";
    currentStudent = children[0].name;
    loadConsent(currentStudent);
    loadTab("schedule");
    document.getElementById("child-select").addEventListener("change", e => {
      currentStudent = e.target.value;
      document.querySelectorAll("[data-pane]").forEach(p => { delete p.dataset.loaded; });
      loadConsent(currentStudent);
      loadTab("schedule");
    });
  }).catch(e => {
    document.getElementById("guardian-children").innerHTML = `<div class="alert alert-danger">${e.message || "Guardian verification failed."}</div>`;
  });

  function loadConsent(student) {
    api("toefl_house.operations.guardian_portal.get_consent_status", { student }).then(s => {
      const el = document.getElementById("guardian-consent-status");
      if (s && s.has_consent) el.innerHTML = `<span class="badge badge-success">Consent active — expires ${s.expiry_date||"unknown"}</span>`;
      else el.innerHTML = `<span class="badge badge-warning">Consent required/expired for ${student}</span>`;
    });
  }

  const tabs = portal.querySelectorAll("[data-tab]");
  tabs.forEach(t => t.addEventListener("click", () => {
    const tab = t.dataset.tab;
    tabs.forEach(x => x.classList.remove("active"));
    portal.querySelectorAll("[data-pane]").forEach(p => p.classList.toggle("d-none", p.dataset.pane !== tab));
    t.classList.add("active");
    loadTab(tab);
  }));

  function renderList(el, items, empty) {
    if (!items || !items.length) { el.innerHTML = `<p class="text-muted">${empty}</p>`; return; }
    el.innerHTML = "<ul class='list-group'>" + items.map(i =>
      `<li class="list-group-item">${Object.values(i).slice(0,4).join(" — ")}</li>`
    ).join("") + "</ul>";
  }

  function loadTab(tab) {
    if (!currentStudent) return;
    const pane = portal.querySelector(`[data-pane="${tab}"]`);
    if (!pane) return;
    const methodMap = {
      schedule: "toefl_house.operations.guardian_portal.get_child_schedule",
      attendance: "toefl_house.operations.guardian_portal.get_child_attendance",
      grades: "toefl_house.operations.guardian_portal.get_child_grades",
      fees: "toefl_house.operations.guardian_portal.get_child_fees"
    };
    const method = methodMap[tab];
    if (!method) return;
    pane.innerHTML = "<em>Loading…</em>";
    api(method, { student: currentStudent }).then(data => {
      let items = data;
      if (tab === "fees") items = (data.fees||[]).concat(data.invoices||[]);
      renderList(pane, items, "No records found or access requires valid consent.");
    }).catch(e => { pane.innerHTML = `<div class="alert alert-danger">${e.message || "Access denied."}</div>`; });
  }

  // Announcements
  frappe.call({ method: "toefl_house.operations.guardian_portal.get_announcements_for_guardian" }).then(r => {
    const el = document.getElementById("guardian-announcements");
    const items = r.message || [];
    if (!items.length) return;
    el.innerHTML = "<h6>Announcements</h6>" + items.map(a => `<div class="alert alert-info"><strong>${frappe.utils.escape_html(a.title||"")}</strong><br>${a.message||""}</div>`).join("");
  });
})();
