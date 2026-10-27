/* Shared, explicitly labeled and text-only learner/guardian projections. */
(() => {
  "use strict";
  // Solar dates are computed by the server using the same bounded calendar
  // as class periods; the native Gregorian date remains visible as well.
  const fields = {
    schedule: [
      ["course", "Course"], ["student_group", "Class"],
      ["schedule_date_shamsi", "Date (Solar Hijri)", "Unavailable"],
      ["schedule_date", "Date (Gregorian)"], ["from_time", "Start"],
      ["to_time", "End"], ["room", "Room"], ["instructor", "Instructor"],
      ["th_session_status", "Session status", "Scheduled"]
    ],
    attendance: [
      ["student_group", "Class"], ["course_schedule", "Session"],
      ["date_shamsi", "Date (Solar Hijri)", "Unavailable"],
      ["date", "Date (Gregorian)"], ["status", "Attendance status"]
    ],
    grades: [["assessment_plan", "Assessment"], ["grade", "Grade"], ["posting_date", "Date (Gregorian)"]],
    fees: [
      ["name", "Record"], ["program", "Program"], ["academic_year", "Academic year"],
      ["grand_total", "Total"], ["outstanding_amount", "Outstanding"],
      ["due_date", "Due date (Gregorian)"], ["status", "Status"]
    ]
  };

  function renderList(el, items, kind, empty) {
    el.replaceChildren();
    if (!Array.isArray(items) || !items.length) {
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
      (fields[kind] || []).forEach(([key, label, fallback]) => {
        const value = item[key] === null || item[key] === undefined || item[key] === ""
          ? fallback : item[key];
        if (value === null || value === undefined || value === "") return;
        const line = document.createElement("div");
        const heading = document.createElement("strong");
        heading.textContent = label + ": ";
        line.appendChild(heading);
        line.appendChild(document.createTextNode(String(value)));
        li.appendChild(line);
      });
      list.appendChild(li);
    });
    el.appendChild(list);
  }

  window.TH_PORTAL_VIEW = { renderList };
})();
