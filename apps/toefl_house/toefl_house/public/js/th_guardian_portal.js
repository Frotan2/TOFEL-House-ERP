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
    el.replaceChildren();
    if (!children || !children.length) {
      const msg = document.createElement("p");
      msg.className = "text-muted";
      msg.textContent = "No verified children linked to your guardian profile.";
      el.appendChild(msg);
      return;
    }
    const label = document.createElement("label");
    label.textContent = "Select child:";
    const select = document.createElement("select");
    select.id = "child-select";
    select.className = "form-control";
    children.forEach(child => {
      const option = document.createElement("option");
      option.value = String(child.name || "");
      option.textContent = String(child.student_name || child.name || "");
      select.appendChild(option);
    });
    el.append(label, select);
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
    const alert = document.createElement("div");
    alert.className = "alert alert-danger";
    alert.textContent = "Guardian verification failed.";
    document.getElementById("guardian-children").replaceChildren(alert);
  });

  function loadConsent(student) {
    api("toefl_house.operations.guardian_portal.get_consent_status", { student }).then(s => {
      const el = document.getElementById("guardian-consent-status");
      const badge = document.createElement("span");
      badge.className = (s && s.has_consent) ? "badge badge-success" : "badge badge-warning";
      badge.textContent = (s && s.has_consent)
        ? "Consent active — expires " + String(s.expiry_date || "unknown")
        : "Consent required or expired for " + String(student);
      el.replaceChildren(badge);
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
    const loading = document.createElement("em");
    loading.textContent = "Loading…";
    pane.replaceChildren(loading);
    api(method, { student: currentStudent }).then(data => {
      let items = data;
      if (tab === "fees") items = (data.fees||[]).concat(data.invoices||[]);
      renderList(pane, items, "No records found or access requires valid consent.");
    }).catch(() => {
      const alert = document.createElement("div");
      alert.className = "alert alert-danger";
      alert.textContent = "Access denied.";
      pane.replaceChildren(alert);
    });
  }

  // Announcements
  frappe.call({ method: "toefl_house.operations.guardian_portal.get_announcements_for_guardian" }).then(r => {
    const el = document.getElementById("guardian-announcements");
    const items = r.message || [];
    if (!items.length) return;
    el.replaceChildren();
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
})();
