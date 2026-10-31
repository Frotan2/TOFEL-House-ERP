/* Guardian self-service portal — verified relationship + consent gating */
(() => {
  "use strict";
  const portal = document.getElementById("guardian-portal");
  const childContainer = document.getElementById("guardian-children");
  if (!portal || !childContainer) return; // disabled page has no data controls

  let currentStudent = null;
  let selectedTab = "schedule";
  let tabRequest = 0;
  let consentRequest = 0;

  function api(method, args) {
    return frappe.call({ method, args }).then(r => r.message);
  }

  function clearChildPanes() {
    // Remove all old-child content immediately, including hidden tabs.
    portal.querySelectorAll("[data-pane]").forEach(pane => {
      const prompt = document.createElement("em");
      prompt.textContent = "Select a child to view records.";
      pane.replaceChildren(prompt);
    });
  }

  function loadConsent(student) {
    const request = ++consentRequest;
    const el = document.getElementById("guardian-consent-status");
    el.textContent = "Checking consent…";
    api("toefl_house.operations.guardian_portal.get_consent_status", { student }).then(s => {
      if (request !== consentRequest || student !== currentStudent) return;
      const badge = document.createElement("span");
      badge.className = (s && s.has_consent) ? "badge badge-success" : "badge badge-warning";
      badge.textContent = (s && s.has_consent)
        ? "Consent active — expires " + String(s.expiry_date || "unknown")
        : "Consent required or expired for " + String(student);
      el.replaceChildren(badge);
    }).catch(() => {
      if (request !== consentRequest || student !== currentStudent) return;
      el.textContent = "Unable to check consent. Please retry or contact staff.";
    });
  }

  const tabs = portal.querySelectorAll("[data-tab]");
  tabs.forEach(t => t.addEventListener("click", () => {
    selectedTab = t.dataset.tab;
    tabs.forEach(x => x.classList.remove("active"));
    portal.querySelectorAll("[data-pane]").forEach(p => p.classList.toggle("d-none", p.dataset.pane !== selectedTab));
    t.classList.add("active");
    loadTab(selectedTab);
  }));

  function loadTab(tab) {
    const pane = portal.querySelector(`[data-pane="${tab}"]`);
    if (!pane) return;
    const request = ++tabRequest;
    const student = currentStudent;
    if (!student) {
      pane.textContent = "Select a child to view records.";
      return;
    }
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
    api(method, { student }).then(data => {
      if (request !== tabRequest || student !== currentStudent || tab !== selectedTab) return;
      let items = data;
      if (tab === "fees") items = (data.fees || []).concat(data.invoices || []);
      window.TH_PORTAL_VIEW.renderList(pane, items, tab, "No records found or access requires valid consent.");
    }).catch(() => {
      if (request !== tabRequest || student !== currentStudent || tab !== selectedTab) return;
      const alert = document.createElement("div");
      alert.className = "alert alert-danger";
      alert.textContent = "Access denied or unable to load records.";
      pane.replaceChildren(alert);
    });
  }

  api("toefl_house.operations.guardian_portal.get_my_children").then(children => {
    childContainer.replaceChildren();
    if (!children || !children.length) {
      const msg = document.createElement("p");
      msg.className = "text-muted";
      msg.textContent = "No verified children linked to your guardian profile.";
      childContainer.appendChild(msg);
      return;
    }
    const label = document.createElement("label");
    label.textContent = "Select child:";
    label.htmlFor = "child-select";
    const select = document.createElement("select");
    select.id = "child-select";
    select.className = "form-control";
    children.forEach(child => {
      const option = document.createElement("option");
      option.value = String(child.name || "");
      option.textContent = String(child.student_name || child.name || "");
      select.appendChild(option);
    });
    childContainer.append(label, select);
    currentStudent = String(children[0].name || "");
    loadConsent(currentStudent);
    loadTab(selectedTab);
    select.addEventListener("change", e => {
      currentStudent = e.target.value;
      clearChildPanes();
      loadConsent(currentStudent);
      // Retain the selected tab, not a hidden schedule, on child switches.
      loadTab(selectedTab);
    });
  }).catch(() => {
    const alert = document.createElement("div");
    alert.className = "alert alert-danger";
    alert.textContent = "Guardian verification failed.";
    childContainer.replaceChildren(alert);
  });

  frappe.call({ method: "toefl_house.operations.guardian_portal.get_announcements_for_guardian" }).then(r => {
    const el = document.getElementById("guardian-announcements");
    const items = r.message || [];
    if (!el || !items.length) return;
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
  }).catch(() => {
    // A failed announcement must not block separately authorized child reads.
  });
})();
